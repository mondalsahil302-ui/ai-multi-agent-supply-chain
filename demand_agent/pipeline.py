"""
pipeline.py – Master orchestrator for the Demand Intelligence Agent training pipeline.

Execution order:
  1.  Load raw dataset (read-only)
  2.  Data preparation: correct target, gap detection, encoding
  3.  Feature engineering: lags, rolling stats, region aggs, calendar, festival,
      stockout/promo, price, product stats
  4.  Leakage verification
  5.  Baseline models (last-week, 4-week MA)
  6.  LightGBM training with early stopping
  7.  CatBoost training with early stopping
  8.  Walk-forward evaluation over test set
  9.  Compute all metrics (regression + ranking)
  10. Generate evaluation charts
  11. Save models, metrics, and feature list
  12. Print limitation notices and final report

Usage:
  python -m demand_agent.pipeline
  python demand_agent/pipeline.py
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

# ─── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")

# ─── Project path bootstrap ───────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from demand_agent.config import (
    RAW_CSV, TARGET_COL, TIME_COL, ENTITY_COLS,
    MODELS_DIR, METRICS_DIR, CHARTS_DIR,
    RANK_K_AVAILABLE, RANK_K_REQUESTED,
)
from demand_agent.data_prep import load_raw, prepare, get_splits
from demand_agent.features import build_features, get_feature_columns, verify_no_leakage
from demand_agent.baselines import (
    predict_last_week, predict_moving_average, evaluate_baseline,
)
from demand_agent.train import (
    train_lightgbm, train_catboost,
    predict_lgb, predict_cb,
    walk_forward_evaluate, save_models,
)
from demand_agent.evaluate import (
    regression_metrics, ranking_metrics_per_group,
    compute_all_metrics,
    walk_forward_metrics,
    plot_actual_vs_predicted, plot_residuals, plot_walk_forward_mae,
    plot_feature_importance, plot_metrics_comparison,
    plot_top10_demand_by_region,
    save_metrics, LimitationError,
    EFFECTIVE_K,
)


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def run_pipeline(dry_run: bool = False) -> dict:
    """
    Execute the full training pipeline end-to-end.
    Returns a summary dict with key metrics and file paths.
    """
    t_start = time.time()
    summary = {}

    logger.info("=" * 65)
    logger.info("DEMAND INTELLIGENCE AGENT — TRAINING PIPELINE")
    logger.info("=" * 65)

    # ─── Step 1: Load ─────────────────────────────────────────────────────────
    logger.info("[1/12] Loading raw dataset...")
    df_raw = load_raw(RAW_CSV)
    logger.info("Loaded %d rows, %d columns.", len(df_raw), len(df_raw.columns))
    summary["raw_rows"] = len(df_raw)

    # ─── Step 2: Data preparation ─────────────────────────────────────────────
    logger.info("[2/12] Data preparation: correct target + gap detection...")
    df_prep, prep_meta = prepare(df_raw)
    summary["prep_meta"] = {
        k: v for k, v in prep_meta.items()
        if k not in ("gap_detail", "validation")
    }
    logger.info("Prepared rows (with valid targets): %d", len(df_prep))

    # ─── Step 3: Feature engineering ──────────────────────────────────────────
    logger.info("[3/12] Feature engineering...")
    train_mask = df_prep["split"] == "train"
    df_feat = build_features(df_prep, train_mask)
    logger.info("Feature engineering done. Shape: %s", df_feat.shape)

    # ─── Step 4: Leakage verification ─────────────────────────────────────────
    logger.info("[4/12] Leakage verification...")
    feature_cols = get_feature_columns(df_feat)
    verify_no_leakage(feature_cols)
    logger.info("%d feature columns verified leak-free.", len(feature_cols))
    summary["n_features"] = len(feature_cols)

    # ─── Step 5: Train/val/test split ─────────────────────────────────────────
    logger.info("[5/12] Temporal train/val/test split...")
    df_train, df_val, df_test = get_splits(df_feat)
    logger.info(
        "Split sizes — Train: %d, Val: %d, Test: %d",
        len(df_train), len(df_val), len(df_test),
    )
    summary["split_sizes"] = {
        "train": len(df_train), "val": len(df_val), "test": len(df_test),
    }

    if dry_run:
        logger.info("DRY RUN — stopping before model training.")
        return summary

    # ─── Step 6: Baselines ────────────────────────────────────────────────────
    logger.info("[6/12] Computing baselines on test set...")
    df_test_base = df_test.copy()
    df_test_base["pred_last_week"] = predict_last_week(df_test_base)
    df_test_base["pred_ma4w"]      = predict_moving_average(df_test_base, window=4)

    baseline_results = []
    for name, col in [("Last-Week Naive", "pred_last_week"), ("4-Week MA", "pred_ma4w")]:
        res = evaluate_baseline(
            name,
            df_test_base[TARGET_COL],
            df_test_base[col],
        )
        baseline_results.append(res)

    # ─── Step 7: LightGBM ─────────────────────────────────────────────────────
    logger.info("[7/12] Training LightGBM...")
    model_lgb = train_lightgbm(df_train, df_val, feature_cols)
    logger.info("LightGBM training complete.")

    # ─── Step 8: CatBoost ─────────────────────────────────────────────────────
    logger.info("[8/12] Training CatBoost...")
    model_cb = train_catboost(df_train, df_val, feature_cols)
    logger.info("CatBoost training complete.")

    # ─── Step 9: Walk-forward evaluation ──────────────────────────────────────
    logger.info("[9/12] Walk-forward evaluation over test weeks...")
    df_wf = walk_forward_evaluate(df_feat, model_lgb, model_cb, feature_cols)
    # Add baseline predictions to walk-forward frame too
    df_wf["pred_last_week"] = predict_last_week(df_wf)
    df_wf["pred_ma4w"]      = predict_moving_average(df_wf, window=4)

    # ─── Step 10: Metrics ─────────────────────────────────────────────────────
    logger.info("[10/12] Computing evaluation metrics...")

    model_configs = [
        ("Last-Week Naive",  "pred_last_week"),
        ("4-Week MA",        "pred_ma4w"),
        ("LightGBM",         "pred_lgb"),
        ("CatBoost",         "pred_cb"),
        ("Ensemble (avg)",   "pred_ensemble"),
    ]

    all_metrics, limitation_notice = compute_all_metrics(df_wf, model_configs)

    # Print limitation notice prominently
    if limitation_notice:
        logger.warning("=" * 65)
        logger.warning("RANKING METRIC LIMITATION NOTICE")
        logger.warning(limitation_notice)
        logger.warning(
            "Ranking metrics are computed at @%d (not @%d) due to dataset scope.",
            EFFECTIVE_K, RANK_K_REQUESTED,
        )
        logger.warning("=" * 65)
    summary["limitation_notice"] = limitation_notice

    # Print metrics table
    print("\n" + "=" * 65)
    print("EVALUATION RESULTS (test set, walk-forward)")
    print("=" * 65)
    df_metrics = pd.DataFrame(all_metrics)
    print(df_metrics.to_string(index=False))
    print("=" * 65 + "\n")

    # ─── Step 11: Charts ──────────────────────────────────────────────────────
    logger.info("[11/12] Generating evaluation charts...")
    chart_paths = []

    for model_name, pred_col in model_configs:
        if pred_col not in df_wf.columns:
            continue
        safe = model_name.lower().replace(" ", "_").replace("(", "").replace(")", "")

        p = plot_actual_vs_predicted(df_wf, pred_col, model_name)
        chart_paths.append(str(p))

        p = plot_residuals(df_wf, pred_col, model_name)
        chart_paths.append(str(p))

    # Walk-forward MAE over time
    wf_records = []
    for model_name, pred_col in model_configs:
        if pred_col not in df_wf.columns:
            continue
        wf_df = walk_forward_metrics(df_wf, pred_col, model_name)
        if not wf_df.empty:
            wf_records.append(wf_df)

    if wf_records:
        p = plot_walk_forward_mae(wf_records)
        chart_paths.append(str(p))

    # Feature importance
    p = plot_feature_importance(model_lgb, feature_cols)
    chart_paths.append(str(p))

    # Metrics comparison bar chart
    p = plot_metrics_comparison(all_metrics)
    chart_paths.append(str(p))

    # Top-K demand by region (LightGBM and CatBoost)
    for model_name, pred_col in [("LightGBM", "pred_lgb"), ("CatBoost", "pred_cb")]:
        p = plot_top10_demand_by_region(df_wf, pred_col, model_name)
        if p:
            chart_paths.append(str(p))

    summary["chart_paths"] = chart_paths

    # ─── Step 12: Save models & metrics ───────────────────────────────────────
    logger.info("[12/12] Saving models, metrics, and feature list...")
    save_models(
        model_lgb, model_cb, feature_cols,
        meta={
            "pipeline_version": "1.0.0",
            "dataset": str(RAW_CSV),
            "target_col": TARGET_COL,
            "n_train_rows": len(df_train),
            "n_val_rows": len(df_val),
            "n_test_rows": len(df_test),
            "limitation_notice": limitation_notice,
        },
    )

    save_metrics(all_metrics, limitation_notice)

    elapsed = time.time() - t_start
    logger.info("Pipeline complete in %.1f seconds.", elapsed)
    summary["elapsed_seconds"] = round(elapsed, 1)

    # ─── Final printed summary ─────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("DEMAND INTELLIGENCE AGENT — PIPELINE SUMMARY")
    print("=" * 65)
    print(f"  Dataset rows         : {summary['raw_rows']:,}")
    print(f"  Features used        : {summary['n_features']}")
    print(f"  Train / Val / Test   : {len(df_train)} / {len(df_val)} / {len(df_test)}")
    print(f"  Models saved to      : {MODELS_DIR}")
    print(f"  Metrics saved to     : {METRICS_DIR}")
    print(f"  Charts saved to      : {CHARTS_DIR}")
    print(f"  Elapsed time         : {elapsed:.1f}s")
    print()
    print("  *** DATASET LIMITATION NOTICE ***")
    print(f"  Dataset contains only {RANK_K_AVAILABLE} products per region-week.")
    print(f"  Requested Precision@{RANK_K_REQUESTED}/NDCG@{RANK_K_REQUESTED}/DemandCapture@{RANK_K_REQUESTED} CANNOT be validly computed.")
    print(f"  Metrics were computed at @{EFFECTIVE_K} (the actual assortment depth).")
    print(f"  To enable @{RANK_K_REQUESTED} metrics, ingest full 200-product dataset.")
    print("=" * 65)

    return summary


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Demand Intelligence Agent pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Prepare data only, skip training")
    args = parser.parse_args()
    run_pipeline(dry_run=args.dry_run)

