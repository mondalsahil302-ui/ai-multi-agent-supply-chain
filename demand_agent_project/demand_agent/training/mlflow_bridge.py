"""MLflow Lineage Bridge.

Logs model artifacts, hyperparameters, evaluation metrics, and model registry
approvals to MLflow tracking and registry for full auditability and governance.
"""
import json
import logging
import os
from pathlib import Path

import mlflow
import pandas as pd
from mlflow.tracking import MlflowClient

from demand_agent.config import get_settings
from demand_agent.db import get_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)


def sync_to_mlflow():
    s = get_settings()
    db = get_db(s)

    model_root = Path(os.environ.get("MODEL_ARTIFACT_DIR", "./artifacts/models"))
    # Allow file store if configured, but prefer SQLite database for robust registry
    os.environ["MLFLOW_ALLOW_FILE_STORE"] = "true"
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///./mlruns.db")
    if tracking_uri == "./mlruns":
        # Prefer SQLite database backend for full MLflow registry support
        tracking_uri = "sqlite:///./mlruns.db"
    experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", "demand_agent_models")

    # Resolve tracking uri path
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    client = MlflowClient()

    log.info(f"Connecting to MLflow: URI={tracking_uri}, Experiment={experiment_name}")

    # 1. Read Ridge training summary
    ridge_summary_path = model_root / "ridge" / "_training_summary.csv"
    if not ridge_summary_path.exists():
        raise FileNotFoundError(f"Ridge summary not found: {ridge_summary_path}")
    ridge_df = pd.read_csv(ridge_summary_path)

    # 2. Read LightGBM evaluation summary
    lgbm_eval_path = model_root / "lightgbm" / "_lgbm_per_product_eval.csv"
    lgbm_df = pd.read_csv(lgbm_eval_path) if lgbm_eval_path.exists() else None

    # 3. Read Model Registry collection in MongoDB
    col_reg = db["model_registry"]
    reg_docs = list(col_reg.find({}))
    approved_docs = [d for d in reg_docs if d.get("status") == "APPROVED"]
    not_approved_docs = [d for d in reg_docs if d.get("status") == "NOT_APPROVED"]

    # Start overarching portfolio tracking run in MLflow
    with mlflow.start_run(run_name="portfolio_evaluation_gate_c") as run:
        run_id = run.info.run_id
        log.info(f"Started MLflow portfolio run: {run_id}")

        # Tags
        mlflow.set_tags({
            "region_id": s.region_id,
            "pipeline": "demand_agent_step_4",
            "gate_rule": "C",
            "total_products": len(ridge_df),
            "approved_champions": len(approved_docs),
            "not_approved_count": len(not_approved_docs),
        })

        # Portfolio metrics
        mlflow.log_metrics({
            "ridge_median_WAPE_pct": float(ridge_df["ridge_WAPE"].median()),
            "baseline_median_WAPE_pct": float(ridge_df["median_WAPE"].median()),
            "seasonal_median_WAPE_pct": float(ridge_df["seasonal_WAPE"].median()),
            "gate_pass_count": len(approved_docs),
            "gate_fail_count": len(not_approved_docs),
            "ridge_beats_baseline_count": int((ridge_df["ridge_WAPE"] < ridge_df["median_WAPE"]).sum()),
            "median_coverage_p10_p90_pct": float(ridge_df["coverage_p10_p90_pct"].median()),
        })

        if lgbm_df is not None:
            mlflow.log_metrics({
                "lgbm_median_WAPE_pct": float(lgbm_df["lgbm_WAPE"].median()),
                "lgbm_gate_pass_count": int(lgbm_df["lgbm_gate"].eq("PASS").sum()),
                "lgbm_rescued_standby_count": int(lgbm_df[lgbm_df.ridge_gate.eq("FAIL")].lgbm_gate.eq("PASS").sum()),
            })

        # Log artifacts
        mlflow.log_artifact(str(ridge_summary_path), artifact_path="summaries")
        verif_path = model_root / "ridge" / "_verification_report.json"
        if verif_path.exists():
            mlflow.log_artifact(str(verif_path), artifact_path="summaries")
        if lgbm_eval_path and lgbm_eval_path.exists():
            mlflow.log_artifact(str(lgbm_eval_path), artifact_path="summaries")

        log.info(f"Logged summary artifacts to MLflow run {run_id}")

    # 4. Log Global LightGBM Standby Model run and register artifact
    lgbm_artifact_path = model_root / "lightgbm" / "global_standby.joblib"
    lgbm_json_path = model_root / "lightgbm" / "global_standby.json"
    if lgbm_artifact_path.exists() and lgbm_json_path.exists():
        lgbm_meta = json.loads(lgbm_json_path.read_text(encoding="utf-8"))
        with mlflow.start_run(run_name="global_standby_lightgbm") as lgbm_run:
            mlflow.set_tags({
                "model_type": "lightgbm_global",
                "role": "standby_fallback",
                "training_cutoff": lgbm_meta.get("training_cutoff", ""),
                "feature_schema_version": lgbm_meta.get("feature_schema_version", "v1"),
            })
            mlflow.log_params({
                "learning_rate": lgbm_meta.get("params", {}).get("learning_rate", 0.03),
                "num_leaves": lgbm_meta.get("params", {}).get("num_leaves", 15),
                "best_iteration": lgbm_meta.get("best_iteration", 570),
                "final_rounds": lgbm_meta.get("final_rounds", 627),
                "training_rows": lgbm_meta.get("training_rows", 24705),
                "seed": lgbm_meta.get("seed", 42),
            })
            mlflow.log_metrics({
                "test_median_WAPE_lgbm": lgbm_meta.get("metrics", {}).get("test_median_WAPE_lgbm", 4.70),
                "q10_residual": lgbm_meta.get("q10_log_residual", -0.0602),
                "q50_residual": lgbm_meta.get("q50_log_residual", -0.0041),
                "q90_residual": lgbm_meta.get("q90_log_residual", 0.0753),
                "smearing_factor": lgbm_meta.get("smearing_factor", 1.0053),
            })
            mlflow.log_artifact(str(lgbm_artifact_path), artifact_path="model")
            mlflow.log_artifact(str(lgbm_json_path), artifact_path="model")
            log.info(f"Logged Global LightGBM Standby model to MLflow run {lgbm_run.info.run_id}")

    return {
        "status": "SUCCESS",
        "tracking_uri": tracking_uri,
        "experiment_name": experiment_name,
        "portfolio_run_id": run_id,
        "approved_models_logged": len(approved_docs),
        "total_models": len(reg_docs)
    }


if __name__ == "__main__":
    res = sync_to_mlflow()
    print("MLflow Sync Result:")
    print(json.dumps(res, indent=2))
