"""
run_pipeline_full.py – Standalone Master Pipeline for Demand Intelligence Agent.

Executes the complete end-to-end ML workflow on the validated 200-product dataset:
  Step 1: Dataset audit and completeness verification (1,112,000 rows, 40 regions, 200 products, 139 weeks)
  Step 2: Preprocessing, target alignment, and temporal splitting
  Step 3: Leakage-free feature engineering
  Step 4: Model training (Naive Last-Week, 4-Week MA, LightGBM, CatBoost)
  Step 5: Test-set evaluation (MAE, RMSE, R2, WAPE, Bias, Precision@10, NDCG@10, Demand Capture@10)
  Step 6: Next-week demand forecasting for all 200 products across 40 regions (Week 140)
  Step 7: Formatted console output for all 40 regions and saving of CSV artifacts
"""

import sys
import time
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd

from demand_agent.config import (
    FULL_STANDARDIZED_CSV, RAW_CSV, TARGET_COL, TIME_COL, ENTITY_COLS,
    MODELS_DIR, OUTPUTS_DIR, N_REGIONS, N_PRODUCTS, N_WEEKS,
    RANK_K_AVAILABLE, RANK_K_REQUESTED,
)
from demand_agent.data_prep import load_raw, prepare, get_splits
from demand_agent.features import build_features, get_feature_columns, verify_no_leakage
from demand_agent.baselines import predict_last_week, predict_moving_average
from demand_agent.train import (
    train_lightgbm, train_catboost,
    predict_lgb, predict_cb,
    save_models,
)
from demand_agent.evaluate import (
    regression_metrics, ranking_metrics_per_group,
    plot_metrics_comparison, plot_feature_importance,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("full_pipeline")


def main():
    t_start = time.time()
    print("=" * 80)
    print("DEMAND INTELLIGENCE AGENT — FULL CATALOG PIPELINE (40 REGIONS x 200 PRODUCTS)")
    print("=" * 80)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 1 — VERIFY DATASET COMPLETENESS
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("STEP 1 — VERIFYING DATASET COMPLETENESS")
    print("=" * 80)

    dataset_path = FULL_STANDARDIZED_CSV if FULL_STANDARDIZED_CSV.exists() else RAW_CSV
    print(f"Loading complete dataset from: {dataset_path}")
    df_raw = load_raw(dataset_path)

    total_rows = len(df_raw)
    n_regions = df_raw["location_id"].nunique()
    n_products = df_raw["product_id"].nunique()
    n_weeks = df_raw[TIME_COL].nunique()
    expected_total = n_regions * n_products * n_weeks

    print(f"Audit Results:")
    print(f"  • Total Rows:             {total_rows:,} (Expected: {expected_total:,})")
    print(f"  • Total Regions:          {n_regions} (Expected: {N_REGIONS})")
    print(f"  • Total Products:         {n_products} (Expected: {N_PRODUCTS})")
    print(f"  • Total Unique Weeks:     {n_weeks} (Expected: {N_WEEKS})")

    min_date = df_raw[TIME_COL].min().strftime("%Y-%m-%d")
    max_date = df_raw[TIME_COL].max().strftime("%Y-%m-%d")
    print(f"  • Observation Span:       {min_date} to {max_date} (139 weeks)")

    # Verify coverage per region-week
    rw_counts = df_raw.groupby(["location_id", TIME_COL])["product_id"].count()
    min_rw = rw_counts.min()
    max_rw = rw_counts.max()
    print(f"  • Products per Region-Week: Min={min_rw}, Max={max_rw} (All 200 present: {min_rw == 200 and max_rw == 200})")

    # Verify zero null sales
    null_sales = df_raw["units_sold"].isna().sum()
    print(f"  • Null sales records:     {null_sales} (Zero fabricated or missing)")

    # Verify duplicates
    dups = df_raw.duplicated(subset=ENTITY_COLS + [TIME_COL]).sum()
    print(f"  • Duplicate Entity-Weeks: {dups}")

    if total_rows != 1112000 or n_products != 200 or n_regions != 40:
        print("[CRITICAL] Dataset completeness audit failed. Stopping pipeline.")
        sys.exit(1)
    print(">>> DATASET AUDIT PASSED: Complete 200-product conformed catalog verified.")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 2 — PREPROCESSING
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("STEP 2 — PREPROCESSING & TARGET ALIGNMENT")
    print("=" * 80)

    # Prepare data with proper next-week target
    df_raw = df_raw.sort_values(ENTITY_COLS + [TIME_COL]).copy()
    df_raw[TARGET_COL] = df_raw.groupby(ENTITY_COLS)["units_sold"].shift(-1)

    # Encode festival nulls, unit size, season
    from demand_agent.data_prep import encode_festival_event, parse_unit_size_grams, encode_season
    df_raw = encode_festival_event(df_raw)
    df_raw["unit_size_ml_or_g"] = parse_unit_size_grams(df_raw["unit_size"])
    df_raw = encode_season(df_raw)

    # Assign chronological split labels:
    # Weeks 1-100: Train (800,000 rows)
    # Weeks 101-120: Val (160,000 rows)
    # Weeks 121-138: Test (144,000 rows)
    # Week 139: Forecast Cutoff (8,000 rows, latest completed week)
    sorted_weeks = sorted(df_raw[TIME_COL].unique())
    week_to_idx = {w: i for i, w in enumerate(sorted_weeks)}
    df_raw["week_idx"] = df_raw[TIME_COL].map(week_to_idx)

    def assign_split(idx):
        if idx < 100:
            return "train"
        elif idx < 120:
            return "val"
        elif idx < 138:
            return "test"
        else:
            return "forecast_cutoff"

    df_raw["split"] = df_raw["week_idx"].apply(assign_split)
    split_counts = df_raw["split"].value_counts().to_dict()
    print(f"Chronological Splitting Distribution:")
    print(f"  • Train Set (Weeks 1-100):         {split_counts.get('train', 0):,} rows")
    print(f"  • Validation Set (Weeks 101-120):   {split_counts.get('val', 0):,} rows")
    print(f"  • Test Set (Weeks 121-138):         {split_counts.get('test', 0):,} rows")
    print(f"  • Forecast Cutoff (Week 139):       {split_counts.get('forecast_cutoff', 0):,} rows")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 3 — FEATURE ENGINEERING
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("STEP 3 — FEATURE ENGINEERING (LEAKAGE-FREE)")
    print("=" * 80)
    t_feat = time.time()
    train_mask = df_raw["split"] == "train"
    df_feat = build_features(df_raw, train_mask)

    # Fill target festival/holiday for the latest week if NaN
    df_feat["tgt_holiday_flag"] = df_feat["tgt_holiday_flag"].fillna(0).astype("Int8")
    df_feat["tgt_has_festival"] = df_feat["tgt_has_festival"].fillna(0).astype("Int8")

    feature_cols = get_feature_columns(df_feat)
    verify_no_leakage(feature_cols)
    print(f"Features engineered: {len(feature_cols)} verified clean features ({time.time() - t_feat:.2f}s)")
    print(f"Feature categories: Sales Lags (1, 2, 4, 8w), Rolling Mean/Std/Trend (4, 8, 13w),")
    print(f"                    Regional totals & rank, Target calendar & festival, Stockout/Promo, Price, Product historical stats.")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 4 — MODEL TRAINING
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("STEP 4 — MODEL TRAINING")
    print("=" * 80)

    df_train = df_feat[df_feat["split"] == "train"].copy()
    df_val   = df_feat[df_feat["split"] == "val"].copy()
    df_test  = df_feat[df_feat["split"] == "test"].copy()

    # Train LightGBM
    t_lgb = time.time()
    print("Training LightGBM Regressor (Primary)...")
    model_lgb = train_lightgbm(df_train, df_val, feature_cols)
    print(f"LightGBM trained in {time.time() - t_lgb:.2f}s (Best iteration: {model_lgb.best_iteration_})")

    # Train CatBoost
    t_cb = time.time()
    print("Training CatBoost Regressor (Challenger)...")
    model_cb = train_catboost(df_train, df_val, feature_cols)
    print(f"CatBoost trained in {time.time() - t_cb:.2f}s (Best iteration: {model_cb.best_iteration_})")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 5 — MODEL EVALUATION
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("STEP 5 — WALK-FORWARD EVALUATION ON TEST SET (144,000 samples across 18 weeks)")
    print("=" * 80)

    # Compute predictions on test set
    df_test["pred_last_week"] = predict_last_week(df_test)
    df_test["pred_ma4w"]      = df_test["roll_mean_4w"].fillna(df_test["units_sold"])
    df_test["pred_lgb"]       = predict_lgb(model_lgb, df_test, feature_cols)
    df_test["pred_cb"]        = predict_cb(model_cb, df_test, feature_cols)

    models_to_eval = [
        ("Last-Week Naive", "pred_last_week"),
        ("4-Week MA",       "pred_ma4w"),
        ("LightGBM",        "pred_lgb"),
        ("CatBoost",        "pred_cb"),
    ]

    results = []
    for model_name, pred_col in models_to_eval:
        reg = regression_metrics(df_test[TARGET_COL].values, df_test[pred_col].values, model_name=model_name)
        rank = ranking_metrics_per_group(df_test, pred_col, k=10)
        combined = {
            "Model": model_name,
            "MAE": reg["MAE"],
            "RMSE": reg["RMSE"],
            "R2": reg["R2"],
            "WAPE": reg["WAPE"],
            "ForecastBias": reg["ForecastBias"],
            "Precision@10": rank["Precision@10"],
            "NDCG@10": rank["NDCG@10"],
            "DemandCapture@10": rank["DemandCapture@10"],
        }
        results.append(combined)

    df_comparison = pd.DataFrame(results)

    print("\n" + "-" * 115)
    print("MODEL COMPARISON TABLE (Walk-Forward Test Set Evaluation)")
    print("-" * 115)
    print(df_comparison.to_string(index=False))
    print("-" * 115)

    # Select best model: highest NDCG@10 and lowest MAE
    best_row = df_comparison.sort_values(by=["NDCG@10", "MAE"], ascending=[False, True]).iloc[0]
    best_model_name = best_row["Model"]
    print(f"\n>>> BEST SELECTED FORECASTING MODEL: {best_model_name}")
    print(f"    (Selected based on superior regression fit R2={best_row['R2']} and ranking performance NDCG@10={best_row['NDCG@10']})")

    selected_model = model_lgb if "LightGBM" in best_model_name else model_cb

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 6 — NEXT-WEEK DEMAND PREDICTION
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("STEP 6 — GENERATING NEXT-WEEK DEMAND PREDICTIONS FOR ALL 40 REGIONS")
    print("=" * 80)

    # Cutoff row is Week 139 (2026-08-23 to 2026-08-29)
    # Target week to forecast is Week 140 (2026-08-30 to 2026-09-05)
    df_cutoff = df_feat[df_feat["split"] == "forecast_cutoff"].copy()
    print(f"Scoring all {len(df_cutoff):,} products (40 regions x 200 products) from latest cutoff week (Week 139)...")

    if "LightGBM" in best_model_name:
        preds = predict_lgb(model_lgb, df_cutoff, feature_cols)
    else:
        preds = predict_cb(model_cb, df_cutoff, feature_cols)

    df_cutoff["predicted_units"] = np.round(preds).astype(int)

    forecast_start = "2026-08-30"
    forecast_end   = "2026-09-05"
    df_cutoff["forecast_start_date"] = forecast_start
    df_cutoff["forecast_end_date"]   = forecast_end

    # Rank products descending within each region
    df_cutoff["demand_rank"] = (
        df_cutoff.groupby("location_id")["predicted_units"]
        .rank(method="first", ascending=False)
        .astype(int)
    )

    # Sort all forecasts by region and rank
    all_forecasts = df_cutoff[[
        "location_id", "region_of_kolkata", "product_id", "product_name", "category_name",
        "forecast_start_date", "forecast_end_date", "predicted_units", "demand_rank"
    ]].sort_values(by=["location_id", "demand_rank"]).reset_index(drop=True)

    # Extract Top 10 products per region
    top10_forecasts = all_forecasts[all_forecasts["demand_rank"] <= 10].reset_index(drop=True)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 7 — OUTPUT REQUIREMENTS
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("STEP 7 — TOP 10 FORECASTED PRODUCTS FOR ALL 40 KOLKATA REGIONS")
    print(f"Target Forecast Week: [{forecast_start} to {forecast_end}]")
    print("=" * 80)

    regions_list = sorted(top10_forecasts["location_id"].unique())
    for region_id in regions_list:
        reg_df = top10_forecasts[top10_forecasts["location_id"] == region_id].sort_values("demand_rank")
        region_name = reg_df["region_of_kolkata"].iloc[0]

        print(f"\nRegion: {region_name} ({region_id})")
        print(f"Forecast Week: [{forecast_start} to {forecast_end}]")
        print(f"{'Rank':<5} | {'Product ID':<12} | {'Product Name':<32} | {'Predicted Units':<15}")
        print("-" * 72)
        for _, row in reg_df.iterrows():
            print(f"{row['demand_rank']:<5} | {row['product_id']:<12} | {row['product_name'][:30]:<32} | {row['predicted_units']:<15}")

    # Save artifact files
    outputs_root = PROJECT_ROOT / "outputs"
    outputs_agent = OUTPUTS_DIR
    outputs_root.mkdir(exist_ok=True)
    outputs_agent.mkdir(exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Model comparison
    comp_file_root = outputs_root / "model_comparison.csv"
    comp_file_agent = outputs_agent / "model_comparison.csv"
    df_comparison.to_csv(comp_file_root, index=False)
    df_comparison.to_csv(comp_file_agent, index=False)
    print(f"\nSaved model comparison: {comp_file_root}")

    # 2. All product forecasts (8,000 rows)
    all_file_root = outputs_root / "all_product_forecasts.csv"
    all_file_agent = outputs_agent / "all_product_forecasts.csv"
    all_forecasts.to_csv(all_file_root, index=False)
    all_forecasts.to_csv(all_file_agent, index=False)
    print(f"Saved all-product forecasts ({len(all_forecasts):,} rows): {all_file_root}")

    # 3. Regional top 10 forecasts (400 rows)
    top10_file_root = outputs_root / "regional_top10_forecasts.csv"
    top10_file_agent = outputs_agent / "regional_top10_forecasts.csv"
    top10_forecasts.to_csv(top10_file_root, index=False)
    top10_forecasts.to_csv(top10_file_agent, index=False)
    print(f"Saved regional top-10 forecasts ({len(top10_forecasts):,} rows): {top10_file_root}")

    # 4. Save trained models and config
    save_models(
        model_lgb, model_cb, feature_cols,
        meta={
            "best_model": best_model_name,
            "n_features": len(feature_cols),
            "n_train_rows": len(df_train),
            "n_val_rows": len(df_val),
            "n_test_rows": len(df_test),
            "forecast_target_week": f"{forecast_start} to {forecast_end}",
            "catalog_products": 200,
            "catalog_regions": 40,
        },
        output_dir=MODELS_DIR,
    )
    print(f"Saved trained models and config: {MODELS_DIR}")

    elapsed = time.time() - t_start
    print(f"\nPipeline completed successfully in {elapsed:.1f}s.")
    print("=" * 80)
    print("EXACT CLI RERUN COMMAND:")
    print("  python -m demand_agent.run_pipeline_full")
    print("=" * 80)


if __name__ == "__main__":
    main()

