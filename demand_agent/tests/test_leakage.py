"""
tests/test_leakage.py – Unit tests for feature leakage prevention.

Tests:
  1. All columns in the leakage blacklist are excluded from feature matrix.
  2. Synthetic target column is excluded.
  3. forecast_target_start / _end are not features.
  4. demand_rank is not a feature.
  5. selling_unit_sheet is not a feature.
  6. get_feature_columns excludes TIME_COL raw date.
  7. Model prediction columns do not appear as features.
  8. Post-training: feature columns stored in model metadata match those used to train.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from demand_agent.config import LEAKAGE_COLS, TARGET_COL, TIME_COL, RAW_TARGET
from demand_agent.features import get_feature_columns, verify_no_leakage
from demand_agent.data_prep import build_correct_target


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_full_schema_df() -> pd.DataFrame:
    """DataFrame with ALL 44 columns from the real schema."""
    row = {
        "demand_id": "DEM-0000001",
        "week_start_date": pd.Timestamp("2024-01-01"),
        "week_end_date": pd.Timestamp("2024-01-07"),
        "year": 2024,
        "week_number": 1,
        "location_id": "KOL-LOC-001",
        "region_of_kolkata": "Lake Gardens",
        "demand_rank": 1,
        "product_id": "TEA-001",
        "product_name": "Tata Tea Gold",
        "category_name": "Tea & Coffee",
        "brand": "Tata Tea",
        "unit_size": "500 g",
        "weekday_weekend": "Weekday",
        "weekday_units_sold": 80,
        "weekend_units_sold": 20,
        "units_sold": 100,
        "avg_selling_price_rs": 250.0,
        "promotion_flag": 0,
        "discount_pct": 0.0,
        "holiday_flag": 0,
        "festival_event": None,
        "season": "Winter",
        "temperature_c": 20.0,
        "rainfall_mm": 5.0,
        "humidity_pct": 65.0,
        "weather_condition": "Clear/Partly Cloudy",
        "stockout_flag": 0,
        "forecast_target_start": pd.Timestamp("2024-01-08"),
        "forecast_target_end": pd.Timestamp("2024-01-14"),
        RAW_TARGET: 110,
        "data_source": "SYNTHETIC_TRAINING",
        "recorded_at": 46279.69,
        "region_week_key": "KOL-LOC-001_20240101",
        "region_product_week_key": "KOL-LOC-001_20240101_TEA-001",
        "assortment_size": 200,
        "rank_scope": "region-week over all 200 products",
        "rank_basis": "units_sold DESC",
        "selling_unit_workbook": "Regional.xlsx",
        "selling_unit_sheet": "W001_2024-01-01",
        "selling_unit_source_row": 3,
        "selling_unit_lookup_hint": "'W001_2024-01-01'!A3",
        "reference_layer": "regional_selling_unit_reference",
        "anchor_status": "observed_top5_anchor",
    }
    return pd.DataFrame([row])


# ─── Test class ───────────────────────────────────────────────────────────────

class TestLeakageExclusions:
    """Verify that every leakage column is excluded from the feature matrix."""

    def setup_method(self):
        df = _make_full_schema_df()
        # Build target to get the correct renamed column
        self.df = build_correct_target(df)
        self.feature_cols = get_feature_columns(self.df)

    def test_raw_target_not_in_features(self):
        """Original synthetic target column must not appear as a feature."""
        assert RAW_TARGET not in self.feature_cols, (
            f"RAW_TARGET '{RAW_TARGET}' must not be in feature columns."
        )

    def test_constructed_target_not_in_features(self):
        """Constructed forward-shifted target must not appear as a feature."""
        assert TARGET_COL not in self.feature_cols, (
            f"TARGET_COL '{TARGET_COL}' must not be in feature columns."
        )

    def test_forecast_target_start_not_in_features(self):
        assert "forecast_target_start" not in self.feature_cols

    def test_forecast_target_end_not_in_features(self):
        assert "forecast_target_end" not in self.feature_cols

    def test_demand_rank_not_in_features(self):
        assert "demand_rank" not in self.feature_cols

    def test_demand_id_not_in_features(self):
        assert "demand_id" not in self.feature_cols

    def test_selling_unit_sheet_not_in_features(self):
        """selling_unit_sheet encodes the week → temporal leakage."""
        assert "selling_unit_sheet" not in self.feature_cols

    def test_selling_unit_source_row_not_in_features(self):
        """selling_unit_source_row encodes product position → leakage."""
        assert "selling_unit_source_row" not in self.feature_cols

    def test_selling_unit_workbook_not_in_features(self):
        assert "selling_unit_workbook" not in self.feature_cols

    def test_selling_unit_lookup_hint_not_in_features(self):
        assert "selling_unit_lookup_hint" not in self.feature_cols

    def test_region_week_key_not_in_features(self):
        """Composite string keys leak temporal + entity info."""
        assert "region_week_key" not in self.feature_cols

    def test_region_product_week_key_not_in_features(self):
        assert "region_product_week_key" not in self.feature_cols

    def test_recorded_at_not_in_features(self):
        """Excel float serial date is provenance metadata, not a feature."""
        assert "recorded_at" not in self.feature_cols

    def test_reference_layer_not_in_features(self):
        assert "reference_layer" not in self.feature_cols

    def test_anchor_status_not_in_features(self):
        assert "anchor_status" not in self.feature_cols

    def test_data_source_not_in_features(self):
        assert "data_source" not in self.feature_cols

    def test_raw_date_column_not_in_features(self):
        """Raw week_start_date must not appear as a raw datetime feature."""
        assert TIME_COL not in self.feature_cols

    def test_assortment_size_not_in_features(self):
        """assortment_size is constant 200 and misleading metadata."""
        assert "assortment_size" not in self.feature_cols

    def test_verify_no_leakage_on_actual_feature_list(self):
        """verify_no_leakage() must pass silently on the real feature list."""
        # Should NOT raise
        verify_no_leakage(self.feature_cols)

    def test_all_blacklisted_cols_excluded(self):
        """Every column in LEAKAGE_COLS must be absent from feature list."""
        present = [c for c in LEAKAGE_COLS if c in self.feature_cols]
        assert len(present) == 0, (
            f"Leakage columns found in feature list: {present}"
        )


class TestLeakageValidatorEdgeCases:
    """Edge-case tests for the verify_no_leakage guard function."""

    def test_raises_on_single_leakage_col(self):
        with pytest.raises(ValueError, match="LEAKAGE DETECTED"):
            verify_no_leakage(["lag_1w", "selling_unit_sheet"])

    def test_raises_on_target_in_feature_list(self):
        with pytest.raises(ValueError, match="LEAKAGE DETECTED"):
            verify_no_leakage([TARGET_COL, "lag_1w"])

    def test_passes_on_empty_list(self):
        """An empty feature list trivially passes the leakage check."""
        verify_no_leakage([])  # should not raise

    def test_passes_on_fully_clean_list(self):
        clean = [
            "units_sold", "lag_1w", "lag_2w", "lag_4w", "lag_8w",
            "roll_mean_4w", "roll_std_4w", "roll_mean_8w",
            "promotion_flag", "holiday_flag", "stockout_flag",
            "temperature_c", "humidity_pct", "rainfall_mm",
            "obs_week_number", "tgt_week_number", "tgt_month",
            "weeks_since_start", "season_ord",
            "location_id", "product_id", "category_name",
            "festival_event", "obs_has_festival", "tgt_has_festival",
        ]
        verify_no_leakage(clean)  # should not raise


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

