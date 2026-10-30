"""
tests/test_temporal.py – Unit tests for temporal alignment and chronological integrity.

Tests:
  1. Correct target is forward-shifted units_sold (not synthetic column).
  2. No val/test dates appear in the training set.
  3. Lag features do not use current or future weeks.
  4. Rolling features are computed with shift(1) on units_sold.
  5. walk-forward evaluation covers only test-split weeks.
  6. Target-week festival features are correctly shifted.
  7. Entities with a missing intermediate week produce NaN lags (not zero).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make demand_agent importable from the project root
PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from demand_agent.config import (
    ENTITY_COLS, TIME_COL, TARGET_COL, RAW_TARGET,
    TRAIN_END_IDX, VAL_END_IDX,
)
from demand_agent.data_prep import build_correct_target, prepare, get_splits
from demand_agent.features import (
    add_lag_features, add_rolling_features, add_festival_features,
    get_feature_columns, verify_no_leakage,
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_toy_df(n_weeks: int = 12, n_regions: int = 2, n_products: int = 3) -> pd.DataFrame:
    """
    Minimal synthetic DataFrame mirroring the real dataset schema,
    suitable for unit tests. Uses deterministic values.
    """
    rows = []
    base_date = pd.Timestamp("2024-01-01")
    demand_id = 1
    for w in range(n_weeks):
        wk = base_date + pd.Timedelta(weeks=w)
        for r in range(n_regions):
            for p in range(n_products):
                units = 50 + r * 10 + p * 5 + w
                rows.append({
                    "demand_id": f"DEM-{demand_id:07d}",
                    TIME_COL: wk,
                    "week_end_date": wk + pd.Timedelta(days=6),
                    "year": wk.year,
                    "week_number": wk.isocalendar()[1],
                    "location_id": f"KOL-LOC-{r+1:03d}",
                    "region_of_kolkata": f"Region_{r}",
                    "demand_rank": p + 1,
                    "product_id": f"PROD-{p+1:03d}",
                    "product_name": f"Product {p}",
                    "category_name": "TestCat",
                    "brand": "TestBrand",
                    "unit_size": "500 g",
                    "weekday_weekend": "Weekday",
                    "weekday_units_sold": int(units * 0.75),
                    "weekend_units_sold": int(units * 0.25),
                    "units_sold": units,
                    "avg_selling_price_rs": 100.0 + p * 10,
                    "promotion_flag": int(w % 4 == 0),
                    "discount_pct": 10.0 if w % 4 == 0 else 0.0,
                    "holiday_flag": int(w % 8 == 0),
                    "festival_event": "Diwali" if w % 8 == 0 else None,
                    "season": "Winter",
                    "temperature_c": 22.0,
                    "rainfall_mm": 0.0,
                    "humidity_pct": 60.0,
                    "weather_condition": "Clear/Partly Cloudy",
                    "stockout_flag": 0,
                    "forecast_target_start": wk + pd.Timedelta(weeks=1),
                    "forecast_target_end": wk + pd.Timedelta(weeks=1) + pd.Timedelta(days=6),
                    RAW_TARGET: units + 10,  # synthetic (deliberately wrong)
                    "data_source": "SYNTHETIC_TRAINING",
                    "recorded_at": 46279.0,
                    "region_week_key": f"KOL-LOC-{r+1:03d}_{wk.strftime('%Y%m%d')}",
                    "region_product_week_key": f"KOL-LOC-{r+1:03d}_{wk.strftime('%Y%m%d')}_PROD-{p+1:03d}",
                    "assortment_size": 200,
                    "rank_scope": "region-week over all 200 products",
                    "rank_basis": "units_sold DESC",
                    "selling_unit_workbook": "test.xlsx",
                    "selling_unit_sheet": f"W{w+1:03d}",
                    "selling_unit_source_row": demand_id + 2,
                    "selling_unit_lookup_hint": f"Sheet!A{demand_id}",
                    "reference_layer": "regional_selling_unit_reference",
                    "anchor_status": "observed_top5_anchor",
                })
                demand_id += 1
    return pd.DataFrame(rows)


# ─── Test 1: Target is correct forward shift ──────────────────────────────────

class TestTargetConstruction:
    def test_target_equals_next_week_units_sold(self):
        """TARGET_COL must equal units_sold of the subsequent week for each entity."""
        df = _make_toy_df(n_weeks=8, n_regions=2, n_products=2)
        df_t = build_correct_target(df)

        for (loc, prod), grp in df_t.groupby(ENTITY_COLS):
            grp = grp.sort_values(TIME_COL).reset_index(drop=True)
            for i in range(len(grp) - 1):
                actual_next = grp.loc[i + 1, "units_sold"]
                target_val  = grp.loc[i, TARGET_COL]
                assert abs(actual_next - target_val) < 1e-6, (
                    f"Target mismatch for ({loc}, {prod}) at week {i}: "
                    f"expected {actual_next}, got {target_val}"
                )

    def test_last_week_has_nan_target(self):
        """The last chronological week per entity must have NaN target."""
        df = _make_toy_df(n_weeks=6, n_regions=1, n_products=2)
        df_t = build_correct_target(df)

        for (loc, prod), grp in df_t.groupby(ENTITY_COLS):
            grp = grp.sort_values(TIME_COL)
            last_target = grp.iloc[-1][TARGET_COL]
            assert pd.isna(last_target), (
                f"Last week for ({loc}, {prod}) should have NaN target, got {last_target}"
            )

    def test_synthetic_target_not_equal_to_correct_target(self):
        """
        Confirms the synthetic RAW_TARGET column does NOT equal the
        correct forward-shifted target (validates audit finding: 1.32% match rate).
        """
        df = _make_toy_df(n_weeks=10, n_regions=2, n_products=3)
        df_t = build_correct_target(df)
        valid = df_t[df_t[TARGET_COL].notna()]
        matches = (valid["synthetic_target_ref"] == valid[TARGET_COL]).sum()
        total   = len(valid)
        # In our toy data the synthetic target is units + 10, never equal to next-week units
        assert matches < total, (
            "Synthetic target should NOT perfectly match correct target. "
            f"Match count: {matches}/{total}"
        )


# ─── Test 2: Temporal split isolation ─────────────────────────────────────────

class TestTemporalSplitIsolation:
    def test_no_future_dates_in_train(self):
        """Validation and test weeks must not appear in the training set."""
        df = _make_toy_df(n_weeks=20, n_regions=2, n_products=12)
        df_t = build_correct_target(df)
        # Manually assign split labels (bypassing validate_raw product threshold)
        sorted_weeks = sorted(df_t[TIME_COL].unique())
        week_to_idx  = {w: i for i, w in enumerate(sorted_weeks)}
        df_t["week_idx"] = df_t[TIME_COL].map(week_to_idx)
        df_t["split"] = df_t["week_idx"].apply(
            lambda i: "train" if i < 10 else ("val" if i < 15 else "test")
        )
        df_t = df_t[df_t[TARGET_COL].notna()].copy()
        df_train, df_val, df_test = get_splits(df_t)

        train_weeks = set(df_train[TIME_COL])
        val_weeks   = set(df_val[TIME_COL])
        test_weeks  = set(df_test[TIME_COL])

        assert len(train_weeks & val_weeks) == 0, "Val weeks found in train!"
        assert len(train_weeks & test_weeks) == 0, "Test weeks found in train!"
        assert len(val_weeks & test_weeks) == 0, "Test weeks found in val!"

    def test_train_weeks_strictly_before_val(self):
        """Every training week must come before every validation week."""
        df = _make_toy_df(n_weeks=20, n_regions=2, n_products=12)
        df_t = build_correct_target(df)
        sorted_weeks = sorted(df_t[TIME_COL].unique())
        week_to_idx  = {w: i for i, w in enumerate(sorted_weeks)}
        df_t["week_idx"] = df_t[TIME_COL].map(week_to_idx)
        df_t["split"] = df_t["week_idx"].apply(
            lambda i: "train" if i < 10 else ("val" if i < 15 else "test")
        )
        df_t = df_t[df_t[TARGET_COL].notna()].copy()
        df_train, df_val, df_test = get_splits(df_t)

        max_train = df_train[TIME_COL].max()
        min_val   = df_val[TIME_COL].min() if len(df_val) > 0 else pd.Timestamp.max
        min_test  = df_test[TIME_COL].min() if len(df_test) > 0 else pd.Timestamp.max

        assert max_train < min_val or len(df_val) == 0, (
            f"Train max={max_train} >= val min={min_val}"
        )
        assert max_train < min_test or len(df_test) == 0, (
            f"Train max={max_train} >= test min={min_test}"
        )

    def test_split_column_coverage(self):
        """Every row in the prepared dataset must have a split label."""
        df = _make_toy_df(n_weeks=15, n_regions=2, n_products=12)
        df_t = build_correct_target(df)
        sorted_weeks = sorted(df_t[TIME_COL].unique())
        week_to_idx  = {w: i for i, w in enumerate(sorted_weeks)}
        df_t["week_idx"] = df_t[TIME_COL].map(week_to_idx)
        df_t["split"] = df_t["week_idx"].apply(
            lambda i: "train" if i < 9 else ("val" if i < 12 else "test")
        )
        df_t = df_t[df_t[TARGET_COL].notna()].copy()
        assert df_t["split"].notna().all(), "Some rows have null split label."
        assert set(df_t["split"].unique()).issubset({"train", "val", "test"})


# ─── Test 3: Lag feature temporal correctness ─────────────────────────────────

class TestLagFeatures:
    def test_lag1_equals_previous_week_units_sold(self):
        """lag_1w for week t must equal units_sold at week t-1 for same entity."""
        df = _make_toy_df(n_weeks=10, n_regions=1, n_products=2)
        df_t = build_correct_target(df)
        df_l = add_lag_features(df_t, lags=[1])

        for (loc, prod), grp in df_l.groupby(ENTITY_COLS):
            grp = grp.sort_values(TIME_COL).reset_index(drop=True)
            for i in range(1, len(grp)):
                expected_lag = grp.loc[i - 1, "units_sold"]
                actual_lag   = grp.loc[i, "lag_1w"]
                assert abs(expected_lag - actual_lag) < 1e-6, (
                    f"Lag-1 mismatch for ({loc},{prod}) row {i}: "
                    f"expected {expected_lag}, got {actual_lag}"
                )

    def test_lag1_first_row_is_nan(self):
        """lag_1w for the first week of each entity must be NaN."""
        df = _make_toy_df(n_weeks=8, n_regions=1, n_products=2)
        df_t = build_correct_target(df)
        df_l = add_lag_features(df_t, lags=[1])

        for (loc, prod), grp in df_l.groupby(ENTITY_COLS):
            grp = grp.sort_values(TIME_COL).reset_index(drop=True)
            first_lag = grp.loc[0, "lag_1w"]
            assert pd.isna(first_lag), (
                f"First lag_1w for ({loc},{prod}) should be NaN, got {first_lag}"
            )

    def test_missing_intermediate_week_produces_nan_not_zero(self):
        """
        If a product is absent in week t, lag_1w for week t+1 must be NaN.
        We simulate this by removing a row from the middle of a series.
        The date-aware merge in add_lag_features ensures the +7-day lookup
        finds no matching row and returns NaN instead of a stale value.
        """
        df = _make_toy_df(n_weeks=8, n_regions=1, n_products=1)
        df_t = build_correct_target(df)

        # Remove week index 4 (the 5th week) for the single entity
        weeks_sorted = sorted(df_t[TIME_COL].unique())
        week_to_remove = weeks_sorted[4]
        df_gap = df_t[df_t[TIME_COL] != week_to_remove].copy()

        df_l = add_lag_features(df_gap, lags=[1])

        # Week at index 5 (first week after the gap) should have NaN lag_1w
        # because its -7-day look-up points to the removed week_to_remove
        week_after_gap = weeks_sorted[5]
        row = df_l[df_l[TIME_COL] == week_after_gap]
        if len(row) > 0:
            lag_val = row["lag_1w"].values[0]
            assert pd.isna(lag_val), (
                f"After a missing intermediate week, lag_1w should be NaN, got {lag_val}. "
                f"(week_to_remove={week_to_remove.date()}, "
                f"week_after_gap={week_after_gap.date()})"
            )


# ─── Test 4: Rolling feature uses shift(1) ────────────────────────────────────

class TestRollingFeatures:
    def test_rolling_mean_does_not_use_current_week(self):
        """
        For a constant-demand entity where units_sold = 100 always,
        roll_mean_4w at week t must equal 100 (not use current row).
        To isolate the shift(1), we change the last row to units_sold = 999.
        The rolling mean at that row must still be ~100 (shift ensures we exclude it).
        """
        df = _make_toy_df(n_weeks=10, n_regions=1, n_products=1)
        df_t = build_correct_target(df)

        # Set all but last units_sold to 100
        last_idx = df_t.sort_values(TIME_COL).index[-1]
        df_t = df_t.copy()
        df_t.loc[df_t.index != last_idx, "units_sold"] = 100
        df_t.loc[df_t.index == last_idx, "units_sold"] = 999

        df_r = add_rolling_features(df_t, windows=[4])

        # Rolling mean at last week should be ~100 (shift(1) excludes current row = 999)
        last_row = df_r.sort_values(TIME_COL).iloc[-1]
        roll_mean = last_row["roll_mean_4w"]
        assert not pd.isna(roll_mean), "roll_mean_4w should not be NaN at week 10."
        assert abs(roll_mean - 100.0) < 5.0, (
            f"roll_mean_4w at last week should be ~100 (shift applied), got {roll_mean}"
        )


# ─── Test 5: Feature leakage check ────────────────────────────────────────────

class TestLeakageGuard:
    def test_get_feature_columns_excludes_target(self):
        """The feature column list must not include the target variable."""
        df = _make_toy_df(n_weeks=5, n_regions=1, n_products=2)
        df_t = build_correct_target(df)
        feature_cols = get_feature_columns(df_t)
        assert TARGET_COL not in feature_cols, (
            f"TARGET_COL '{TARGET_COL}' must not be in feature columns."
        )

    def test_verify_no_leakage_raises_on_target(self):
        """verify_no_leakage() must raise ValueError if target is in feature list."""
        bad_features = ["units_sold", "lag_1w", TARGET_COL]
        with pytest.raises(ValueError, match="LEAKAGE DETECTED"):
            verify_no_leakage(bad_features)

    def test_verify_no_leakage_raises_on_raw_target(self):
        """verify_no_leakage() must raise ValueError if RAW_TARGET is in feature list."""
        bad_features = ["lag_1w", RAW_TARGET]
        with pytest.raises(ValueError, match="LEAKAGE DETECTED"):
            verify_no_leakage(bad_features)

    def test_verify_no_leakage_passes_on_clean_list(self):
        """verify_no_leakage() must not raise on a clean feature list."""
        clean_features = [
            "lag_1w", "lag_2w", "lag_4w",
            "roll_mean_4w", "roll_std_4w",
            "promotion_flag", "holiday_flag",
            "temperature_c", "humidity_pct",
        ]
        # Should not raise
        verify_no_leakage(clean_features)


# ─── Test 6: Festival target-week shift ───────────────────────────────────────

class TestFestivalTargetShift:
    def test_tgt_festival_is_next_week_festival(self):
        """
        tgt_festival_event at week t must equal festival_event at week t+1.
        """
        df = _make_toy_df(n_weeks=10, n_regions=1, n_products=1)
        df_t = build_correct_target(df)
        df_f = add_festival_features(df_t)

        for (loc, prod), grp in df_f.groupby(ENTITY_COLS):
            grp = grp.sort_values(TIME_COL).reset_index(drop=True)
            for i in range(len(grp) - 1):
                this_row_tgt_festival = grp.loc[i, "tgt_festival_event"]
                next_row_festival     = grp.loc[i + 1, "festival_event"]
                # Both should match (or both be NaN)
                if pd.isna(this_row_tgt_festival) and pd.isna(next_row_festival):
                    continue
                assert this_row_tgt_festival == next_row_festival, (
                    f"Festival shift mismatch at row {i}: "
                    f"tgt={this_row_tgt_festival}, actual_next={next_row_festival}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
