import json
import logging
import os
import time
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.features import FEATURE_COLUMNS
from demand_agent.training.gate import evaluate_gate, thresholds_from_env
from demand_agent.training.lgbm_trainer import (
    LGBM_FEATURES, build_pooled_dataset, calibrate_from_validation, final_refit,
    fit_global, now_utc, predict_units)
from demand_agent.training.ridge_trainer import bias_pct, wape
from demand_agent.training.train_all import load_all_series

if __name__ == "__main__":
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s | %(message)s")
    pd.set_option("display.width", 200)
    env = os.environ.get
    seed = int(env("TRAIN_RANDOM_SEED", "42"))
    t = thresholds_from_env(env)
    model_root = Path(env("MODEL_ARTIFACT_DIR", "./artifacts/models"))
    out_dir = model_root / "lightgbm"
    out_dir.mkdir(parents=True, exist_ok=True)

    ridge_csv = model_root / "ridge" / "_training_summary.csv"
    if not ridge_csv.exists():
        raise SystemExit(f"Ridge summary not found: {ridge_csv} (run Step 4.2 first)")
    ridge = pd.read_csv(ridge_csv)

    db = get_db(s)
    t0 = time.time()
    series = load_all_series(
        db, s.collections["demand_features"], s.region_id,
        exclude_synthetic=env("TRAIN_EXCLUDE_SYNTHETIC", "true").lower() == "true",
        exclude_partial=env("TRAIN_EXCLUDE_PARTIAL_WEEKS", "true").lower() == "true")
    df, category_map, base_prices = build_pooled_dataset(series)
    print(f"Pooled dataset: {len(df)} rows, {df.product_id.nunique()} products, {len(category_map)} categories "
          f"| splits {df.split.value_counts().to_dict()} | built in {time.time() - t0:.0f}s")

    t0 = time.time()
    booster, params, n_fit, n_val = fit_global(df, seed)
    cal = calibrate_from_validation(booster, df)
    print(f"Global fit on {n_fit} rows, early-stopped on {n_val} validation rows: "
          f"best iteration {booster.best_iteration} ({time.time() - t0:.1f}s)")
    print("Calibration (relative log residuals):", {k: round(v, 4) if isinstance(v, float) else v for k, v in cal.items()})

    # ---- per-product test evaluation (same test weeks as Ridge, stockout weeks excluded) ----
    test = df[df.split.eq("test") & df.stockout.eq(0)].copy()
    test = test.join(predict_units(booster, test, cal, booster.best_iteration))
    rows = []
    for pid, g in test.groupby("product_id"):
        rows.append({"product_id": pid, "lgbm_n": len(g), "lgbm_WAPE": wape(g.units, g.expected),
                     "lgbm_bias_pct": bias_pct(g.units, g.expected),
                     "lgbm_coverage_pct": float(((g.units >= g.p10) & (g.units <= g.p90)).mean() * 100)})
    ev = ridge.merge(pd.DataFrame(rows), on="product_id", how="left")
    ev["best_baseline_WAPE"] = ev[["median_WAPE", "seasonal_WAPE"]].min(axis=1)
    mismatch = int((ev.lgbm_n != ev.test_n).sum())

    def verdict(w, b, base):
        m = {"test_ridge": {"WAPE_pct": w, "Bias_pct": b},   # gate reads this key for the candidate model
             "test_moving_median": {"WAPE_pct": base}, "test_seasonal_naive": {"WAPE_pct": base}}
        g = evaluate_gate(m, t)
        return g["verdict"], "; ".join(g["reasons"])

    lg = [verdict(r.lgbm_WAPE, r.lgbm_bias_pct, r.best_baseline_WAPE) for r in ev.itertuples()]
    rd = [verdict(r.ridge_WAPE, r.bias_pct, r.best_baseline_WAPE) for r in ev.itertuples()]
    ev["lgbm_gate"] = [x[0] for x in lg]
    ev["ridge_gate"] = [x[0] for x in rd]
    ev["route_if_ridge_not_approved"] = np.where(ev.lgbm_gate.eq("PASS"), "LIGHTGBM", "BASELINE")
    ev.to_csv(out_dir / "_lgbm_per_product_eval.csv", index=False)

    n = len(ev)
    print(f"\nTest weeks comparable to Ridge for all products: {'yes' if mismatch == 0 else f'NO - {mismatch} products differ'}")
    print(f"Median test WAPE: LightGBM {ev.lgbm_WAPE.median():.2f}% | Ridge {ev.ridge_WAPE.median():.2f}% | "
          f"trailing median {ev.median_WAPE.median():.2f}% | seasonal naive {ev.seasonal_WAPE.median():.2f}%")
    print(f"LightGBM beats Ridge on {int((ev.lgbm_WAPE < ev.ridge_WAPE).sum())} of {n} products")
    print(f"Gate rule C pass: LightGBM {int(ev.lgbm_gate.eq('PASS').sum())} | Ridge {int(ev.ridge_gate.eq('PASS').sum())} (of {n})")
    nr = ev[ev.ridge_gate.eq("FAIL")]
    print(f"\nProducts Ridge does NOT pass: {len(nr)}")
    print(f"  LightGBM standby passes the gate for {int(nr.lgbm_gate.eq('PASS').sum())} -> route LIGHTGBM")
    print(f"  Neither passes for {int(nr.lgbm_gate.eq('FAIL').sum())} -> route BASELINE")
    print(f"  median WAPE on these: LightGBM {nr.lgbm_WAPE.median():.2f}% | Ridge {nr.ridge_WAPE.median():.2f}% | best baseline {nr.best_baseline_WAPE.median():.2f}%")
    print(f"Median P10-P90 coverage: LightGBM {ev.lgbm_coverage_pct.median():.0f}% | Ridge {ev.coverage_p10_p90_pct.median():.0f}%")
    ev["volume"] = pd.cut(ev.mean_units, [0, 20, 60, 1e9], labels=["low (<20/wk)", "mid (20-60)", "high (>60)"])
    by = ev.groupby("volume", observed=True).agg(
        products=("product_id", "count"), lgbm_WAPE=("lgbm_WAPE", "median"), ridge_WAPE=("ridge_WAPE", "median"),
        best_baseline=("best_baseline_WAPE", "median"),
        lgbm_pass=("lgbm_gate", lambda x: int(x.eq("PASS").sum())), ridge_pass=("ridge_gate", lambda x: int(x.eq("PASS").sum())))
    print("\nBy volume band:")
    print(by.round(2).to_string())

    # ---- final refit on all eligible weeks, then save ----
    rounds = max(50, int(booster.best_iteration * 1.1))
    final, n_final = final_refit(df, params, rounds)
    artifact = {
        "model_type": "lightgbm_global", "model_str": final.model_to_string(),
        "feature_columns": list(LGBM_FEATURES), "shared_feature_columns": list(FEATURE_COLUMNS),
        "categorical_features": ["category_code"], "category_map": category_map,
        "target": "log1p(units) - demand_level_log1p", "base_list_prices": base_prices,
        "q10_log_residual": cal["q10"], "q50_log_residual": cal["q50"], "q90_log_residual": cal["q90"],
        "smearing_factor": cal["smearing"], "best_iteration": int(booster.best_iteration), "final_rounds": rounds,
        "params": params, "seed": seed, "products": sorted(series), "training_rows": n_final,
        "training_cutoff": str(df.week_start_date.max().date()), "feature_schema_version": "v1",
        "trained_at_utc": now_utc(), "weather_training_mode": "historical_observed_weather",
        "metrics": {"test_median_WAPE_lgbm": float(ev.lgbm_WAPE.median()),
                    "test_median_WAPE_ridge": float(ev.ridge_WAPE.median()),
                    "gate_pass_lgbm": int(ev.lgbm_gate.eq("PASS").sum()),
                    "median_coverage_pct": float(ev.lgbm_coverage_pct.median())},
    }
    path = out_dir / "global_standby.joblib"
    joblib.dump(artifact, path)
    meta = {k: v for k, v in artifact.items() if k not in ("model_str", "base_list_prices")}
    (out_dir / "global_standby.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    loaded = joblib.load(path)
    reb = lgb.Booster(model_str=loaded["model_str"])
    probe = df.loc[df.split.eq("test"), LGBM_FEATURES].head(5)
    assert np.allclose(reb.predict(probe), final.predict(probe)), "reloaded model differs"
    assert loaded["feature_columns"] == LGBM_FEATURES and len(loaded["base_list_prices"]) == len(series)
    print(f"\nOK    artifact saved and reload check passed: {path}")
    print(f"      final refit rows: {n_final} | rounds: {rounds} | products covered: {len(loaded['products'])}")
    print(f"      per-product evaluation: {out_dir / '_lgbm_per_product_eval.csv'}")
