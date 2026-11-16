"""Train one Ridge model per product (batch). Failures are isolated per product."""
import json
import logging
import time
from pathlib import Path

import joblib
import pandas as pd
from joblib import Parallel, delayed

from demand_agent.features import REQUIRED_INPUT_COLUMNS
from demand_agent.training.ridge_trainer import NUMERIC, train_product

log = logging.getLogger(__name__)


def load_all_series(db, collection: str, region_id: str, exclude_synthetic: bool = True,
                    exclude_partial: bool = True, product_ids: list[str] | None = None) -> dict[str, pd.DataFrame]:
    """One bulk query for every product (training rows only)."""
    q = {"region_id": region_id, "split": {"$in": ["train", "validation", "test"]}}
    if exclude_partial:
        q["is_partial_week"] = False
    if exclude_synthetic:
        q["is_synthetic_record"] = False
    if product_ids:
        q["product_id"] = {"$in": product_ids}
    proj = {"_id": 0, "product_id": 1, "split": 1, **{c: 1 for c in REQUIRED_INPUT_COLUMNS}}
    df = pd.DataFrame(list(db[collection].find(q, proj)))
    if df.empty:
        raise ValueError("no training rows found")
    df["week_start_date"] = pd.to_datetime(df["week_start_date"])
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return {pid: g.sort_values("week_start_date").reset_index(drop=True)
            for pid, g in df.groupby("product_id")}


def gate_preview(ridge_wape, best_baseline_wape, bias, max_wape_pct, min_improvement, max_abs_bias_pct):
    """Report-only preview of the model quality gate (not enforced in this step)."""
    reasons = []
    if ridge_wape > max_wape_pct:
        reasons.append(f"WAPE {ridge_wape:.1f}% > {max_wape_pct:.0f}%")
    improvement = (best_baseline_wape - ridge_wape) / best_baseline_wape if best_baseline_wape > 0 else 0.0
    if improvement < min_improvement:
        reasons.append(f"improvement vs best baseline {improvement * 100:.0f}% < {min_improvement * 100:.0f}%")
    if abs(bias) > max_abs_bias_pct:
        reasons.append(f"|bias| {abs(bias):.1f}% > {max_abs_bias_pct:.0f}%")
    return ("PASS" if not reasons else "FAIL"), "; ".join(reasons), improvement * 100.0


def _train_one(product_id: str, series: pd.DataFrame, region_id: str, out_dir: str, gate: dict) -> dict:
    t0 = time.time()
    try:
        artifact, r = train_product(series, product_id, region_id)
        path = Path(out_dir) / f"{product_id}.joblib"
        joblib.dump(artifact, path)
        meta = {k: v for k, v in artifact.items() if k != "model"}
        (Path(out_dir) / f"{product_id}.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

        best_base = min(r["median"]["WAPE_pct"], r["seasonal"]["WAPE_pct"])
        verdict, reasons, improvement = gate_preview(
            r["ridge"]["WAPE_pct"], best_base, r["ridge"]["Bias_pct"],
            gate["max_wape_pct"], gate["min_improvement"], gate["max_abs_bias_pct"])
        return {
            "product_id": product_id, "status": "TRAINED",
            "mean_units": round(float(series.units_sold.mean()), 1), "weeks": r["weeks"],
            "alpha": artifact["best_alpha"],
            "val_WAPE": round(artifact["metrics"]["validation_WAPE_pct"], 2),
            "ridge_WAPE": round(r["ridge"]["WAPE_pct"], 2),
            "median_WAPE": round(r["median"]["WAPE_pct"], 2),
            "seasonal_WAPE": round(r["seasonal"]["WAPE_pct"], 2),
            "improvement_vs_best_baseline_pct": round(improvement, 1),
            "bias_pct": round(r["ridge"]["Bias_pct"], 2),
            "coverage_p10_p90_pct": round(r["coverage"], 1), "test_n": r["ridge"]["n"],
            "gate_preview": verdict, "gate_reasons": reasons, "error": "",
            "seconds": round(time.time() - t0, 1),
        }
    except Exception as e:                                   # noqa: BLE001 - isolate per product
        return {"product_id": product_id, "status": "FAILED", "error": f"{type(e).__name__}: {e}",
                "seconds": round(time.time() - t0, 1)}


def train_all(series_by_product: dict[str, pd.DataFrame], region_id: str, out_dir: str,
              gate: dict, n_jobs: int = 4) -> pd.DataFrame:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    rows = Parallel(n_jobs=n_jobs)(
        delayed(_train_one)(pid, df, region_id, out_dir, gate) for pid, df in series_by_product.items())
    summary = pd.DataFrame(rows).sort_values("product_id").reset_index(drop=True)
    summary.to_csv(Path(out_dir) / "_training_summary.csv", index=False)
    return summary