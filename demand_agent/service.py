"""
service.py – Demand Intelligence Agent Service Layer.

Handles model loading, feature preparation, inference, SHAP explanations,
and region ranking for downstream supply chain agents.
"""

from __future__ import annotations

import json
import logging
import pickle
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

from demand_agent.config import (
    RAW_CSV, MODELS_DIR, METRICS_DIR,
    CAT_COLS, RANK_K_AVAILABLE, RANK_K_REQUESTED,
)
from demand_agent.data_prep import load_raw, prepare
from demand_agent.features import build_features
from demand_agent.schemas import (
    DemandDriver, ProductForecastItem, RegionForecast,
    ForecastResponse, EvaluationMetricsResponse, UncertaintyEstimate,
)
from demand_agent.train import _safe_cat_cols

logger = logging.getLogger(__name__)


# Friendly human descriptions for common predictive features
FEATURE_DESCRIPTIONS = {
    "lag_1w": "Sales volume in the prior week",
    "lag_2w": "Sales volume 2 weeks ago",
    "lag_4w": "Sales volume 4 weeks ago",
    "roll_mean_4w": "4-week moving average demand baseline",
    "roll_std_4w": "Demand volatility over recent 4 weeks",
    "roll_trend_4w": "Recent 4-week sales trajectory / momentum",
    "region_total_demand_w": "Overall regional market activity in prior week",
    "region_mean_demand_w": "Average product demand across region in prior week",
    "share_of_region_demand": "Product's volume share in its local market",
    "avg_selling_price_rs": "Current retail selling price",
    "discount_pct": "Promotional discount percentage",
    "promotion_flag": "Active marketing promotion",
    "holiday_flag": "Public holiday timing",
    "tgt_has_festival": "Upcoming festival or cultural event in target week",
    "tgt_holiday_flag": "Upcoming public holiday in target week",
    "temperature_c": "Regional ambient temperature",
    "humidity_pct": "Atmospheric humidity level",
    "rainfall_mm": "Seasonal rainfall volume",
    "season": "Seasonal climate phase (Winter, Summer, Monsoon, Post-Monsoon)",
    "category_name": "Product category consumption archetype",
    "unit_size_ml_or_g": "Standardized package unit size",
    "weeks_since_start": "Long-term secular market trend",
    "rp_mean": "Product's historical baseline in this specific region",
}


class DemandIntelligenceService:
    """Singleton service for Demand Intelligence Agent."""

    def __init__(self):
        self.is_initialized = False
        self.cb_model: Optional[CatBoostRegressor] = None
        self.lgb_model = None
        self.feature_cols: List[str] = []
        self.metadata: Dict[str, Any] = {}
        self.evaluation_metrics: Dict[str, Any] = {}

        # Cached prepared dataset and lookup dictionaries
        self.df_feat: Optional[pd.DataFrame] = None
        self.region_name_to_id: Dict[str, str] = {}
        self.location_id_to_name: Dict[str, str] = {}
        self.min_date: Optional[pd.Timestamp] = None
        self.max_date: Optional[pd.Timestamp] = None

    def initialize(self) -> None:
        """Load models, metrics, and precompute feature scaffold."""
        if self.is_initialized:
            return

        logger.info("Initializing Demand Intelligence Service...")

        # 1. Load model metadata
        meta_path = MODELS_DIR / "model_metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(
                f"Model metadata not found at {meta_path}. Please train models first using pipeline.py."
            )
        with open(meta_path, "r", encoding="utf-8") as f:
            self.metadata = json.load(f)
        self.feature_cols = self.metadata["feature_cols"]

        # 2. Load CatBoost model (best validated)
        cb_path = MODELS_DIR / "catboost_model.cbm"
        if cb_path.exists():
            self.cb_model = CatBoostRegressor()
            self.cb_model.load_model(str(cb_path))
            logger.info("Loaded CatBoost model from %s", cb_path)

        # 3. Load LightGBM model
        lgb_path = MODELS_DIR / "lightgbm_model.pkl"
        if lgb_path.exists():
            with open(lgb_path, "rb") as f:
                self.lgb_model = pickle.load(f)
            logger.info("Loaded LightGBM model from %s", lgb_path)

        # 4. Load offline evaluation metrics
        metrics_path = METRICS_DIR / "evaluation_metrics.json"
        if metrics_path.exists():
            with open(metrics_path, "r", encoding="utf-8") as f:
                self.evaluation_metrics = json.load(f)

        # 5. Load and prepare feature dataset up to available data
        df_raw = load_raw(RAW_CSV)
        df_prep, _ = prepare(df_raw)
        train_mask = df_prep["split"] == "train"
        self.df_feat = build_features(df_prep, train_mask)

        # Region lookups
        regions_df = df_raw[["location_id", "region_of_kolkata"]].drop_duplicates()
        self.region_name_to_id = dict(zip(regions_df["region_of_kolkata"].str.lower(), regions_df["location_id"]))
        self.location_id_to_name = dict(zip(regions_df["location_id"], regions_df["region_of_kolkata"]))

        self.min_date = self.df_feat["week_start_date"].min()
        self.max_date = self.df_feat["week_start_date"].max()

        self.is_initialized = True
        logger.info(
            "Service initialized. Date range: %s to %s. Regions: %d",
            self.min_date.date(), self.max_date.date(), len(self.location_id_to_name)
        )

    def get_supported_regions(self) -> List[Dict[str, str]]:
        """Return all supported Kolkata locations with codes and names."""
        self._ensure_initialized()
        return [
            {"location_id": loc_id, "region_name": name}
            for loc_id, name in sorted(self.location_id_to_name.items())
        ]

    def get_evaluation_metrics(self) -> EvaluationMetricsResponse:
        """Return the precomputed offline evaluation metrics."""
        self._ensure_initialized()
        return EvaluationMetricsResponse(
            metrics=self.evaluation_metrics.get("metrics", []),
            ranking_k_requested=self.evaluation_metrics.get("ranking_k_requested", RANK_K_REQUESTED),
            ranking_k_available=self.evaluation_metrics.get("ranking_k_available", RANK_K_AVAILABLE),
            ranking_k_used=self.evaluation_metrics.get("ranking_k_used", RANK_K_AVAILABLE),
            limitation_notice=self.evaluation_metrics.get("limitation_notice", ""),
        )

    def predict_demand(
        self,
        target_week_start: str,
        region: Optional[str] = None,
        top_k: int = 10,
        include_drivers: bool = True,
        model_name: Optional[str] = "catboost",
    ) -> ForecastResponse:
        """
        Execute next-week demand forecast and ranking for specified week and region(s).
        """
        self._ensure_initialized()

        target_date = date.fromisoformat(target_week_start)
        target_end_date = target_date + timedelta(days=6)

        # Cutoff date: the latest available observation week prior to the target forecast week
        # In a weekly Monday-to-Sunday cycle, cutoff is target_date - 7 days
        expected_cutoff = target_date - timedelta(days=7)
        target_ts = pd.Timestamp(target_date)
        cutoff_ts = pd.Timestamp(expected_cutoff)

        # Enforce temporal cutoff: filter available data strictly <= cutoff_ts
        # This completely prevents any future-data leakage
        data_available = self.df_feat[self.df_feat["week_start_date"] <= cutoff_ts]

        if data_available.empty:
            raise ValueError(
                f"No historical data available prior to cutoff date {expected_cutoff.isoformat()}. "
                f"Earliest available date in dataset is {self.min_date.date().isoformat()}."
            )

        # Determine the latest observation week available to forecast from
        actual_cutoff_ts = data_available["week_start_date"].max()

        # Extract features for the observation week
        obs_df = self.df_feat[self.df_feat["week_start_date"] == actual_cutoff_ts].copy()

        # Filter by region if requested
        if region:
            norm_region = region.strip().lower()
            target_loc_id = None
            if norm_region in self.region_name_to_id:
                target_loc_id = self.region_name_to_id[norm_region]
            else:
                # Check if it was provided as location_id
                upper_region = region.strip().upper()
                if upper_region in self.location_id_to_name:
                    target_loc_id = upper_region

            if not target_loc_id:
                valid_regions = sorted(list(self.location_id_to_name.values())[:5])
                raise ValueError(
                    f"Unknown region '{region}'. Must be a valid Kolkata region name (e.g. {valid_regions}) "
                    f"or location ID (e.g. 'KOL-LOC-001')."
                )
            obs_df = obs_df[obs_df["location_id"] == target_loc_id]

        if obs_df.empty:
            raise ValueError(
                f"No product observations found for cutoff date {actual_cutoff_ts.date()} in region '{region}'."
            )

        # Reset index and record positional index matching X and shap_values
        obs_df = obs_df.reset_index(drop=True)
        obs_df["_obs_pos"] = np.arange(len(obs_df))

        # ─── Feature Matrix ───────────────────────────────────────────────────
        cat_cols = _safe_cat_cols(self.feature_cols)
        X = obs_df[self.feature_cols].copy()

        for c in cat_cols:
            if c in X.columns:
                X[c] = X[c].astype(str).fillna("__missing__")

        # ─── Model Inference ──────────────────────────────────────────────────
        selected_model = (model_name or "catboost").lower()
        if selected_model == "lightgbm" and self.lgb_model is not None:
            # Prepare categorical types for LightGBM
            X_lgb = X.copy()
            for c in cat_cols:
                X_lgb[c] = X_lgb[c].astype("category")
            preds = np.maximum(self.lgb_model.predict(X_lgb), 0)
            model_display_name = "LightGBM Regressor"
            shap_values = None  # CatBoost provides fast native TreeSHAP
        else:
            cat_indices = [X.columns.tolist().index(c) for c in cat_cols if c in X.columns]
            pool = Pool(X, cat_features=cat_indices)
            preds = np.maximum(self.cb_model.predict(pool), 0)
            model_display_name = "CatBoost Regressor (Best Validated)"

            # Compute SHAP values if requested
            if include_drivers:
                shap_matrix = self.cb_model.get_feature_importance(data=pool, type="ShapValues")
                shap_values = shap_matrix[:, :-1]  # drop the base value column
            else:
                shap_values = None

        obs_df["pred_demand"] = preds

        # ─── Group and Rank per Region ────────────────────────────────────────
        region_forecasts: List[RegionForecast] = []

        for loc_id, grp in obs_df.groupby("location_id"):
            region_name = self.location_id_to_name.get(loc_id, grp["region_of_kolkata"].iloc[0])
            grp_sorted = grp.sort_values(by="pred_demand", ascending=False).reset_index(drop=True)

            total_evaluated = len(grp_sorted)
            top_slice = grp_sorted.head(top_k)

            product_items: List[ProductForecastItem] = []
            for rank_idx, row in top_slice.iterrows():
                # Extract SHAP drivers if available
                drivers: Optional[List[DemandDriver]] = None
                if shap_values is not None:
                    # Find top 4 impactful features for this specific product observation
                    pos = int(row["_obs_pos"])
                    row_shap = shap_values[pos]
                    sorted_driver_indices = np.argsort(np.abs(row_shap))[::-1][:4]
                    drivers = []
                    for d_idx in sorted_driver_indices:
                        feat = self.feature_cols[d_idx]
                        s_val = float(row_shap[d_idx])
                        direction = "positive" if s_val >= 0 else "negative"
                        desc = FEATURE_DESCRIPTIONS.get(
                            feat, f"{feat.replace('_', ' ').capitalize()} influence"
                        )
                        drivers.append(
                            DemandDriver(
                                feature_name=feat,
                                shap_value=round(s_val, 2),
                                impact_direction=direction,
                                description=f"{desc} ({direction} impact: {s_val:+.1f} units)",
                            )
                        )

                # Requirement 8: Return forecast uncertainty ONLY if a calibrated uncertainty model exists.
                # Since the current model is a point estimator, we set uncertainty to None and
                # document that no calibrated uncertainty model exists.
                uncertainty_field = None

                product_items.append(
                    ProductForecastItem(
                        product_id=str(row["product_id"]),
                        product_name=str(row["product_name"]),
                        category_name=str(row["category_name"]),
                        brand=str(row["brand"]),
                        unit_size=str(row["unit_size"]),
                        predicted_demand_units=round(float(row["pred_demand"]), 2),
                        demand_rank=rank_idx + 1,
                        uncertainty=uncertainty_field,
                        demand_drivers=drivers,
                    )
                )

            assortment_note = (
                f"Returned {len(product_items)} products (maximum available in regional top-5 anchor dataset: {total_evaluated}). "
                f"Requested top_k={top_k}. To rank across all 200 catalog SKUs, ingest full workbook."
            )

            total_units = round(float(top_slice["pred_demand"].sum()), 2)
            region_forecasts.append(
                RegionForecast(
                    location_id=loc_id,
                    region_name=region_name,
                    target_week_start=target_date.isoformat(),
                    target_week_end=target_end_date.isoformat(),
                    forecast_cutoff_date=actual_cutoff_ts.date().isoformat(),
                    total_predicted_units=total_units,
                    products_evaluated=total_evaluated,
                    returned_count=len(product_items),
                    top_products=product_items,
                    assortment_coverage_note=assortment_note,
                )
            )

        # Sort regions alphabetically by region_name
        region_forecasts.sort(key=lambda x: x.region_name)

        return ForecastResponse(
            agent_id="Demand_Intelligence_Agent_v1",
            target_week_start=target_date.isoformat(),
            target_week_end=target_end_date.isoformat(),
            forecast_cutoff_date=actual_cutoff_ts.date().isoformat(),
            model_name=model_display_name,
            status="success",
            total_regions_processed=len(region_forecasts),
            regions=region_forecasts,
            governance_metadata={
                "leakage_prevention": "Strict cutoff filter enforced; only observations <= cutoff_date utilized.",
                "calibrated_uncertainty_model_exists": False,
                "uncertainty_policy": "Uncertainty intervals omitted because no calibrated conformal/quantile model is trained.",
                "assortment_depth": "Top-5 regional anchor items per region-week (53 unique SKUs total).",
                "ranking_granularity": "Grouped by region × target week start.",
                "downstream_interfaces": [
                    "Inventory_Intelligence_Agent",
                    "Decision_Coordinator",
                ],
            },
        )

    def _ensure_initialized(self) -> None:
        if not self.is_initialized:
            self.initialize()


# Global singleton instance
demand_service = DemandIntelligenceService()

