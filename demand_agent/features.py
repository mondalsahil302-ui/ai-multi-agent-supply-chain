"""
features.py – Feature engineering for the Demand Intelligence Agent.

All features are computed using only past/current-week information.
The temporal ordering is enforced by groupby + shift operations.

Feature groups:
  A. Lag features        : units_sold at t-1, t-2, t-4, t-8 weeks
  B. Rolling statistics  : mean, std, trend over 4/8/13-week windows
  C. Region aggregates   : region-level weekly totals and ranks (current week)
  D. Calendar features   : week_number, month, quarter, is_year_end, etc.
  E. Festival / holiday  : target-week flags (from forecast_target_start)
  F. Historical stockout & promotion: lag and rolling stockout/promo rates
  G. Price sensitivity   : avg_selling_price_rs lags and relative price
  H. Product-level stats : overall product mean demand (computed from train only)
"""

from __future__ import annotations

import logging
import warnings
from typing import List, Optional

import numpy as np
import pandas as pd
import scipy.signal as signal

from demand_agent.config import (
    ENTITY_COLS, TIME_COL, TARGET_COL,
    LAG_WEEKS, ROLLING_WINDOWS,
    LEAKAGE_COLS,
)

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=FutureWarning)


# ─── A. Lag features ──────────────────────────────────────────────────────────

def add_lag_features(df: pd.DataFrame, lags: List[int] = LAG_WEEKS) -> pd.DataFrame:
    """
    Add lagged units_sold features within each (location_id, product_id) entity.
    Uses a date-aware merge so that missing intermediate weeks produce NaN
    rather than carrying over a non-adjacent prior week's value.
    """
    df = df.sort_values(ENTITY_COLS + [TIME_COL]).copy()
    ref = df[ENTITY_COLS + [TIME_COL, "units_sold"]].copy()

    for lag in lags:
        col = f"lag_{lag}w"
        lag_ref = ref.copy()
        lag_ref[TIME_COL] = lag_ref[TIME_COL] + pd.Timedelta(weeks=lag)
        lag_ref = lag_ref.rename(columns={"units_sold": col})
        df = df.merge(lag_ref, on=ENTITY_COLS + [TIME_COL], how="left")
        logger.debug("Lag feature %s: %d non-null values", col, df[col].notna().sum())
    return df


# ─── B. Rolling statistics ────────────────────────────────────────────────────

def add_rolling_features(
    df: pd.DataFrame,
    windows: List[int] = ROLLING_WINDOWS,
    min_periods_frac: float = 0.5,
) -> pd.DataFrame:
    """
    Rolling mean, std, and linear trend of units_sold.
    Uses shift(1) to avoid using the current week's value.
    Vectorized over regular entity-week grids for maximum performance.
    """
    df = df.sort_values(ENTITY_COLS + [TIME_COL]).copy()
    n_entities = df[ENTITY_COLS].drop_duplicates().shape[0]
    n_weeks = df[TIME_COL].nunique()
    is_regular_grid = (len(df) == n_entities * n_weeks)

    if is_regular_grid:
        arr = df["units_sold"].values.reshape(n_entities, n_weeks).astype(float)
        shifted = np.full_like(arr, np.nan)
        shifted[:, 1:] = arr[:, :-1]

        cs = np.pad(np.nan_to_num(shifted, nan=0.0), ((0, 0), (1, 0)), mode="constant")
        cs = np.cumsum(cs, axis=1)
        cs2 = np.pad(np.nan_to_num(shifted ** 2, nan=0.0), ((0, 0), (1, 0)), mode="constant")
        cs2 = np.cumsum(cs2, axis=1)

        for window in windows:
            # Mean
            roll_mean = np.full_like(shifted, np.nan)
            roll_mean[:, window:] = (cs[:, window + 1:] - cs[:, 1: n_weeks - window + 1]) / window
            df[f"roll_mean_{window}w"] = roll_mean.ravel()

            # Std
            roll_std = np.full_like(shifted, np.nan)
            mean_sq = (cs2[:, window + 1:] - cs2[:, 1: n_weeks - window + 1]) / window
            var = np.maximum(0.0, (mean_sq - roll_mean[:, window:] ** 2) * window / (window - 1))
            roll_std[:, window:] = np.sqrt(var)
            df[f"roll_std_{window}w"] = roll_std.ravel()

            # Trend (linear slope)
            x = np.arange(window, dtype=float)
            xc = x - x.mean()
            denom = (xc * xc).sum()
            kernel = (xc / denom).reshape(1, -1)
            valid_trend = signal.convolve(shifted, kernel[:, ::-1], mode="valid", method="direct")
            roll_trend = np.full_like(shifted, np.nan)
            roll_trend[:, window - 1:] = valid_trend
            df[f"roll_trend_{window}w"] = roll_trend.ravel()
    else:
        for window in windows:
            min_p = max(2, int(window * min_periods_frac))
            df[f"roll_mean_{window}w"] = (
                df.groupby(ENTITY_COLS)["units_sold"]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=min_p).mean())
            )
            df[f"roll_std_{window}w"] = (
                df.groupby(ENTITY_COLS)["units_sold"]
                .transform(lambda x: x.shift(1).rolling(window, min_periods=min_p).std())
            )
            df[f"roll_trend_{window}w"] = (
                df.groupby(ENTITY_COLS)["units_sold"]
                .transform(lambda x: _rolling_slope(x.shift(1), window, min_p))
            )

    return df


def _rolling_slope(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    """Fallback rolling OLS slope for irregular grids."""
    result = np.full(len(series), np.nan)
    vals = series.values
    for i in range(len(vals)):
        start = max(0, i - window + 1)
        segment = vals[start : i + 1]
        non_nan = segment[~np.isnan(segment)]
        if len(non_nan) < min_periods:
            continue
        x = np.arange(len(non_nan), dtype=float)
        xm = x - x.mean()
        ym = non_nan - non_nan.mean()
        denom = (xm * xm).sum()
        if denom == 0:
            result[i] = 0.0
        else:
            result[i] = (xm * ym).sum() / denom
    return pd.Series(result, index=series.index)


# ─── C. Region-level aggregate features ───────────────────────────────────────

def add_region_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute region-level demand aggregates for the CURRENT week.
    """
    df = df.copy()
    region_week_agg = (
        df.groupby(["location_id", TIME_COL])["units_sold"]
        .agg(region_total_demand_w="sum", region_mean_demand_w="mean")
        .reset_index()
    )
    df = df.merge(region_week_agg, on=["location_id", TIME_COL], how="left")

    df["region_rank_w"] = (
        df.groupby(["location_id", TIME_COL])["units_sold"]
        .rank(method="min", ascending=False)
        .astype("Int16")
    )

    df["share_of_region_demand"] = (
        df["units_sold"] / df["region_total_demand_w"].replace(0, np.nan)
    )

    df["entity_expanding_mean"] = (
        df.groupby(ENTITY_COLS)["units_sold"]
        .transform(lambda x: x.shift(1).expanding().mean())
    )

    return df


# ─── D. Calendar features ─────────────────────────────────────────────────────

def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract calendar-based features from the target week.
    """
    df = df.copy()

    if "forecast_target_start" in df.columns:
        tgt = pd.to_datetime(df["forecast_target_start"])
    else:
        tgt = pd.to_datetime(df[TIME_COL]) + pd.Timedelta(days=7)

    df["tgt_week_number"] = tgt.dt.isocalendar().week.astype("Int16")
    df["tgt_month"]       = tgt.dt.month.astype("Int8")
    df["tgt_quarter"]     = tgt.dt.quarter.astype("Int8")
    df["tgt_year"]        = tgt.dt.year.astype("Int16")
    df["tgt_is_jan"]      = (tgt.dt.month == 1).astype("int8")
    df["tgt_is_dec"]      = (tgt.dt.month == 12).astype("int8")
    df["tgt_is_q1"]       = (tgt.dt.quarter == 1).astype("int8")

    obs = pd.to_datetime(df[TIME_COL])
    df["obs_week_number"] = obs.dt.isocalendar().week.astype("Int16")
    df["obs_month"]       = obs.dt.month.astype("Int8")
    df["obs_quarter"]     = obs.dt.quarter.astype("Int8")

    min_date = obs.min()
    df["weeks_since_start"] = ((obs - min_date).dt.days // 7).astype("Int16")

    return df


# ─── E. Festival and holiday features for target week ─────────────────────────

def add_festival_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    festival_event and holiday_flag already reflect the CURRENT observation week.
    We also need to know whether the TARGET week (next week) has a festival.

    We construct target-week festival flags by shifting current-week flags
    backward by 1 within each entity (i.e. the next week's festival is
    the current week's festival shifted -1, which is the same as looking at
    the row that will become 'next week').

    Correctly: target_holiday_flag = holiday_flag at t+1
    We shift holiday_flag and festival_event forward by -1 (one step ahead).
    """
    df = df.sort_values(ENTITY_COLS + [TIME_COL]).copy()

    # Next-week (target-week) festival info – shift -1 within entity
    df["tgt_holiday_flag"] = (
        df.groupby(ENTITY_COLS)["holiday_flag"].shift(-1).astype("Int8")
    )
    df["tgt_festival_event"] = (
        df.groupby(ENTITY_COLS)["festival_event"].shift(-1)
    )
    df["tgt_has_festival"] = (
        (df["tgt_festival_event"] != "none")
        & df["tgt_festival_event"].notna()
    ).astype("Int8")

    # Observation week festival features (already encoded)
    df["obs_has_festival"] = (
        (df["festival_event"] != "none")
        & df["festival_event"].notna()
    ).astype("Int8")

    return df


# ─── F. Historical stockout and promotion features ────────────────────────────

def add_stockout_promo_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lag and rolling stockout/promotion features.
    These capture historical supply disruptions and promotional lift.
    """
    df = df.sort_values(ENTITY_COLS + [TIME_COL]).copy()

    for col, prefix in [("stockout_flag", "stockout"), ("promotion_flag", "promo")]:
        # Lag-1
        df[f"{prefix}_lag1"] = (
            df.groupby(ENTITY_COLS)[col].shift(1).astype("Int8")
        )
        # Rolling 4-week rate (fraction of past 4 weeks with stockout/promo)
        df[f"{prefix}_rate_4w"] = (
            df.groupby(ENTITY_COLS)[col]
            .transform(lambda x: x.shift(1).rolling(4, min_periods=1).mean())
        )
        # Rolling 8-week rate
        df[f"{prefix}_rate_8w"] = (
            df.groupby(ENTITY_COLS)[col]
            .transform(lambda x: x.shift(1).rolling(8, min_periods=2).mean())
        )

    # Discount lag
    df["discount_lag1"] = (
        df.groupby(ENTITY_COLS)["discount_pct"].shift(1)
    )

    return df


# ─── G. Price features ────────────────────────────────────────────────────────

def add_price_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lagged price and price relative to the product's historical average.
    """
    df = df.sort_values(ENTITY_COLS + [TIME_COL]).copy()

    df["price_lag1"]    = df.groupby(ENTITY_COLS)["avg_selling_price_rs"].shift(1)
    df["price_roll4w"]  = (
        df.groupby(ENTITY_COLS)["avg_selling_price_rs"]
        .transform(lambda x: x.shift(1).rolling(4, min_periods=1).mean())
    )
    # Price relative to entity's expanding historical mean (price index)
    df["price_vs_hist_mean"] = (
        df["avg_selling_price_rs"] /
        df.groupby(ENTITY_COLS)["avg_selling_price_rs"]
          .transform(lambda x: x.shift(1).expanding().mean())
          .replace(0, np.nan)
    )

    return df


# ─── H. Product-level encoding statistics ─────────────────────────────────────

def add_product_stats(df: pd.DataFrame, train_mask: pd.Series) -> pd.DataFrame:
    """
    Compute product-level and region-product-level statistics from
    TRAINING ROWS ONLY, then join to all rows (prevents test leakage).

    Features:
      - product_global_mean : mean units_sold across all regions in train
      - product_global_std  : std of units_sold across all regions in train
      - rp_mean             : mean units_sold for (region, product) in train
      - rp_std              : std of units_sold for (region, product) in train
    """
    df = df.copy()

    train_df = df[train_mask.values if hasattr(train_mask, 'values') else train_mask]

    # Product-level stats
    prod_stats = (
        train_df.groupby("product_id")["units_sold"]
        .agg(product_global_mean="mean", product_global_std="std")
        .reset_index()
    )
    # Region-product stats
    rp_stats = (
        train_df.groupby(["location_id", "product_id"])["units_sold"]
        .agg(rp_mean="mean", rp_std="std")
        .reset_index()
    )

    df = df.merge(prod_stats, on="product_id", how="left")
    df = df.merge(rp_stats, on=["location_id", "product_id"], how="left")

    # Demand relative to product global mean (z-score style)
    df["demand_vs_product_mean"] = (
        df["units_sold"] - df["product_global_mean"]
    ) / df["product_global_std"].replace(0, np.nan)

    return df


# ─── Master feature builder ───────────────────────────────────────────────────

def build_features(df: pd.DataFrame, train_mask: pd.Series) -> pd.DataFrame:
    """
    Run all feature engineering steps in order.
    train_mask: boolean Series aligned with df.index identifying train rows.
                Used only for stats that must be fit on train only.
    """
    logger.info("Building lag features...")
    df = add_lag_features(df)

    logger.info("Building rolling statistics...")
    df = add_rolling_features(df)

    logger.info("Building region aggregate features...")
    df = add_region_features(df)

    logger.info("Building calendar features...")
    df = add_calendar_features(df)

    logger.info("Building festival/holiday target-week features...")
    df = add_festival_features(df)

    logger.info("Building stockout and promotion features...")
    df = add_stockout_promo_features(df)

    logger.info("Building price features...")
    df = add_price_features(df)

    logger.info("Building product-level stats (train-only fit)...")
    # Re-compute train_mask on the current df (index may have changed after merges)
    train_mask_recomputed = df["split"] == "train"
    df = add_product_stats(df, train_mask_recomputed)

    logger.info("Feature engineering complete. DataFrame shape: %s", df.shape)
    return df


# ─── Feature matrix builder ───────────────────────────────────────────────────

def get_feature_columns(df: pd.DataFrame) -> List[str]:
    """
    Return the list of feature columns to pass to the model.
    Excludes: target, leakage columns, split label, raw ID columns.
    """
    exclude = LEAKAGE_COLS | {
        TARGET_COL,
        "synthetic_target_ref",
        "split",
        "week_idx",
        "region_id",
        # Also exclude raw date columns (already encoded into calendar features)
        "week_end_date",
        "product_name",
        "tgt_festival_event",
        # Target-week festival shift columns already consumed
        # Keep location_id, product_id as categorical features for tree models
    }
    # Also exclude string columns that are not encoded
    feature_cols = [
        c for c in df.columns
        if c not in exclude
        and c != TIME_COL          # raw date → already encoded as week_number etc.
        and c != "forecast_target_start"   # in leakage set but check anyway
        and c != "forecast_target_end"
    ]
    return feature_cols


def verify_no_leakage(feature_cols: List[str]) -> None:
    """Assert that no leakage column made it into the feature list."""
    leakage_found = [c for c in feature_cols if c in LEAKAGE_COLS]
    # Also check for the target
    if TARGET_COL in feature_cols:
        leakage_found.append(TARGET_COL)
    if leakage_found:
        raise ValueError(
            f"LEAKAGE DETECTED: The following columns are in the feature list "
            f"but should be excluded: {leakage_found}"
        )
    logger.info("Leakage check passed. %d feature columns verified clean.", len(feature_cols))
