import argparse
import logging
import os
import time
from pathlib import Path

import pandas as pd

from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.training.train_all import load_all_series, train_all

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="train only the first N products (testing)")
    ap.add_argument("--products", type=str, default="", help="comma-separated product ids")
    ap.add_argument("--n-jobs", type=int, default=0, help="parallel workers (default: MAX_TASK_WORKERS)")
    args = ap.parse_args()

    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s | %(message)s")
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)

    env = os.environ.get
    gate = {"max_wape_pct": float(env("GATE_MAX_WAPE", "0.35")) * 100.0,
            "min_improvement": float(env("GATE_MIN_IMPROVEMENT_VS_BASELINE", "0.05")),
            "max_abs_bias_pct": float(env("GATE_MAX_ABS_BIAS_PCT", "0.10")) * 100.0}
    n_jobs = args.n_jobs or int(env("MAX_TASK_WORKERS", "4"))
    out_dir = str(Path(env("MODEL_ARTIFACT_DIR", "./artifacts/models")) / "ridge")

    db = get_db(s)
    wanted = [p.strip() for p in args.products.split(",") if p.strip()] or None
    series = load_all_series(
        db, s.collections["demand_features"], s.region_id,
        exclude_synthetic=env("TRAIN_EXCLUDE_SYNTHETIC", "true").lower() == "true",
        exclude_partial=env("TRAIN_EXCLUDE_PARTIAL_WEEKS", "true").lower() == "true",
        product_ids=wanted)
    if args.limit:
        series = dict(list(series.items())[: args.limit])
    print(f"Products to train: {len(series)} | workers: {n_jobs} | output: {out_dir}")
    print(f"Gate preview thresholds (report-only): {gate}\n")

    t0 = time.time()
    summary = train_all(series, s.region_id, out_dir, gate, n_jobs=n_jobs)
    total = time.time() - t0

    ok = summary[summary.status == "TRAINED"].copy()
    bad = summary[summary.status == "FAILED"]
    print(f"Finished in {total / 60:.1f} min | trained: {len(ok)} | failed: {len(bad)}")
    if len(bad):
        print(bad[["product_id", "error"]].to_string(index=False))

    if len(ok):
        print(f"\nGate preview: PASS {int((ok.gate_preview == 'PASS').sum())} | FAIL {int((ok.gate_preview == 'FAIL').sum())}")
        print(f"Median test WAPE: Ridge {ok.ridge_WAPE.median():.1f}% | trailing median {ok.median_WAPE.median():.1f}% | seasonal naive {ok.seasonal_WAPE.median():.1f}%")
        print(f"Ridge beats trailing-median baseline on {int((ok.ridge_WAPE < ok.median_WAPE).sum())} of {len(ok)} products")
        print(f"Median P10-P90 coverage: {ok.coverage_p10_p90_pct.median():.0f}% (nominal 80%)")
        ok["volume"] = pd.cut(ok.mean_units, [0, 20, 60, 1e9], labels=["low (<20/wk)", "mid (20-60)", "high (>60)"])
        by = ok.groupby("volume", observed=True).agg(
            products=("product_id", "count"), gate_pass=("gate_preview", lambda x: int((x == "PASS").sum())),
            ridge_WAPE=("ridge_WAPE", "median"), median_WAPE=("median_WAPE", "median"))
        print("\nBy volume band:")
        print(by.round(1).to_string())
        print("\nAlpha chosen (count):", ok.alpha.value_counts().sort_index().to_dict())
        print("\nTop fail reasons:")
        print(ok[ok.gate_preview == "FAIL"].gate_reasons.str.split("; ").explode().str.replace(r"[\d.]+", "#", regex=True).value_counts().head(5).to_string())
        print("\nWorst 5 by Ridge WAPE:")
        print(ok.sort_values("ridge_WAPE", ascending=False).head(5)[["product_id", "mean_units", "alpha", "ridge_WAPE", "median_WAPE", "gate_preview"]].to_string(index=False))
    print(f"\nSummary saved: {Path(out_dir) / '_training_summary.csv'}")