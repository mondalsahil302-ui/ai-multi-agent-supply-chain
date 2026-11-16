import json
import logging
import os
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.features import FEATURE_COLUMNS
from demand_agent.training.ridge_trainer import load_product_series, train_product

if __name__ == "__main__":
    product_id = sys.argv[1] if len(sys.argv) > 1 else "BAB-001"
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s | %(message)s")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    excl_syn = os.environ.get("TRAIN_EXCLUDE_SYNTHETIC", "true").lower() == "true"
    excl_par = os.environ.get("TRAIN_EXCLUDE_PARTIAL_WEEKS", "true").lower() == "true"

    db = get_db(s)
    series = load_product_series(db, s.collections["demand_features"], s.region_id, product_id,
                                 exclude_synthetic=excl_syn, exclude_partial=excl_par)
    print(f"Series {s.region_id}_{product_id}: {len(series)} weeks "
          f"({series.week_start_date.min().date()} -> {series.week_start_date.max().date()}) | "
          f"splits: {series.split.value_counts().to_dict()} | stockout weeks: {int(series.stockout_flag.sum())}")

    t0 = time.time()
    artifact, r = train_product(series, product_id, s.region_id)
    print(f"Training finished in {time.time() - t0:.1f}s\n")

    print("Alpha tuning (validation only):")
    print(r["alpha_table"].round(3).to_string(index=False))
    print(f"\nSelected alpha: {artifact['best_alpha']}")
    print("Calibration:", {k: round(v, 4) if isinstance(v, float) else v for k, v in r["calibration"].items()})

    print("\nTest comparison (stockout weeks excluded):")
    table = pd.DataFrame([
        {"Model": "Ridge expected demand", **r["ridge"]},
        {"Model": "Trailing 4-week median", **r["median"]},
        {"Model": "52-week seasonal naive", **r["seasonal"]},
    ])
    print(table.round(2).to_string(index=False))
    print(f"P10-P90 coverage on test: {r['coverage']:.1f}% (nominal 80%)")
    print("\nTest forecasts:")
    show = r["test"][["week_start_date", "actual_units", "stockout_flag", "p10", "expected", "p90"]].copy()
    show["week_start_date"] = show["week_start_date"].dt.strftime("%Y-%m-%d")
    print(show.round(1).to_string(index=False))

    out_dir = Path(os.environ.get("MODEL_ARTIFACT_DIR", "./artifacts/models")) / "ridge"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{product_id}.joblib"
    joblib.dump(artifact, path)
    meta = {k: v for k, v in artifact.items() if k != "model"}
    (out_dir / f"{product_id}.json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")

    loaded = joblib.load(path)
    assert loaded["feature_columns"] == FEATURE_COLUMNS and len(loaded["feature_columns"]) == 34
    assert loaded["base_list_price"] == artifact["base_list_price"]
    probe = pd.DataFrame(np.zeros((1, 34)), columns=FEATURE_COLUMNS)
    assert np.allclose(loaded["model"].predict(probe), artifact["model"].predict(probe))
    print(f"\nOK    artifact saved and reload check passed: {path}")
    print(f"      final fit rows: {artifact['training_rows']} | base_list_price: {artifact['base_list_price']}")