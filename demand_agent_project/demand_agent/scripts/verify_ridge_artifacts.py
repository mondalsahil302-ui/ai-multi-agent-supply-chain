"""Verify the per-product Ridge artifacts written by run_step_4_2. Read-only."""
import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from demand_agent.features import FEATURE_COLUMNS
from demand_agent.training.ridge_trainer import ALPHA_GRID

REQUIRED_KEYS = ["model_type", "model", "product_id", "region_id", "series_id", "feature_columns",
                 "best_alpha", "base_list_price", "q10_log_residual", "q50_log_residual",
                 "q90_log_residual", "smearing_factor", "training_cutoff", "training_rows", "metrics"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected", type=int, default=200)
    args = ap.parse_args()

    out_dir = Path(os.environ.get("MODEL_ARTIFACT_DIR", "./artifacts/models")) / "ridge"
    joblibs = sorted(p for p in out_dir.glob("*.joblib"))
    jsons = sorted(p for p in out_dir.glob("*.json") if not p.name.startswith("_"))
    problems = []

    probe = pd.DataFrame(np.zeros((1, len(FEATURE_COLUMNS))), columns=FEATURE_COLUMNS)
    for p in joblibs:
        try:
            a = joblib.load(p)
            missing = [k for k in REQUIRED_KEYS if k not in a]
            if missing:
                problems.append((p.stem, f"missing keys {missing}")); continue
            if a["product_id"] != p.stem:
                problems.append((p.stem, f"product_id mismatch: {a['product_id']}"))
            if a["feature_columns"] != FEATURE_COLUMNS or len(a["feature_columns"]) != 34:
                problems.append((p.stem, "feature_columns differ from the 34-feature contract"))
            if a["model_type"] != "ridge":
                problems.append((p.stem, f"model_type {a['model_type']}"))
            if a["best_alpha"] not in ALPHA_GRID:
                problems.append((p.stem, f"alpha {a['best_alpha']} not in grid"))
            if not (a["q10_log_residual"] <= a["q50_log_residual"] <= a["q90_log_residual"]):
                problems.append((p.stem, "residual quantiles not ordered q10<=q50<=q90"))
            if not (a["smearing_factor"] > 0 and a["base_list_price"] > 0):
                problems.append((p.stem, "smearing_factor/base_list_price not positive"))
            pred = float(a["model"].predict(probe)[0])
            if not np.isfinite(pred):
                problems.append((p.stem, "non-finite prediction on probe row"))
        except Exception as e:                                # noqa: BLE001
            problems.append((p.stem, f"{type(e).__name__}: {e}"))

    summary_path = out_dir / "_training_summary.csv"
    status = {}
    if summary_path.exists():
        s = pd.read_csv(summary_path)
        status = {k: int(v) for k, v in s.status.value_counts().items()}
        gate = {k: int(v) for k, v in s.gate_preview.value_counts().items()} if "gate_preview" in s else {}
    else:
        s, gate = None, {}
        problems.append(("_training_summary.csv", "missing"))

    checks = {
        "joblib_files": len(joblibs), "json_files": len(jsons), "expected": args.expected,
        "summary_status": status, "gate_preview": gate, "problems": len(problems),
    }
    ok = (len(joblibs) == args.expected and len(jsons) == args.expected and not problems
          and status.get("TRAINED", 0) == args.expected)
    report = {"ok": ok, **checks, "problem_details": problems[:20]}
    (out_dir / "_verification_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(("OK    " if ok else "FAIL  ") + f"{len(joblibs)} artifacts, {len(jsons)} metadata files (expected {args.expected})")
    print("      summary status:", status, "| gate preview:", gate)
    print(f"      artifact problems: {len(problems)}")
    for name, msg in problems[:10]:
        print(f"        - {name}: {msg}")
    print("      report:", out_dir / "_verification_report.json")
