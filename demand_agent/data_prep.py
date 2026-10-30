"""
data_prep.py – Data loading, target construction, and temporal scaffolding.

Design principles:
  - Target is constructed by forward-shifting units_sold (not from synthetic column).
  - Missing weeks for an entity produce NaN lags (never zero-filled automatically).
  - No row is fabricated; rows without a verifiable forward week are flagged/dropped.
  - All transformations are deterministic and reproducible.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from demand_agent.config import (
    RAW_CSV, ENTITY_COLS, TIME_COL, TARGET_COL, RAW_TARGET,
    LEAKAGE_COLS, CAT_COLS, SEASON_ORDER,
    TRAIN_END_IDX, VAL_END_IDX,
)

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=FutureWarning)


# ─── 1. Raw Load ──────────────────────────────────────────────────────────────

def load_raw(path: Path = RAW_CSV) -> pd.DataFrame:
    """Load CSV with minimal dtype coercion; no column is dropped here."""
    logger.info("Loading raw dataset from %s", path)
    df = pd.read_csv(path, low_memory=False)
    if "location_id" not in df.columns and "region_id" in df.columns:
        df["location_id"] = df["region_id"]
    df[TIME_COL] = pd.to_datetime(df[TIME_COL])
    if "week_end_date" in df.columns:
        df["week_end_date"] = pd.to_datetime(df["week_end_date"])
    if "forecast_target_start" in df.columns:
        df["forecast_target_start"] = pd.to_datetime(df["forecast_target_start"])
    else:
        df["forecast_target_start"] = df[TIME_COL] + pd.Timedelta(days=7)
    if "forecast_target_end" in df.columns:
        df["forecast_target_end"] = pd.to_datetime(df["forecast_target_end"])
    elif "week_end_date" in df.columns:
        df["forecast_target_end"] = df["week_end_date"] + pd.Timedelta(days=7)
    logger.info("Loaded %d rows × %d columns", len(df), len(df.columns))
    return df


# ─── 2. Pre-validation ────────────────────────────────────────────────────────

def validate_raw(df: pd.DataFrame) -> dict:
    """
    Lightweight structural checks.  Returns a dict of findings.
    Raises ValueError if a blocker condition is detected.
    """
    findings = {}

    # Uniqueness of the entity-time key
    dup_key = df.duplicated(subset=ENTITY_COLS + [TIME_COL]).sum()
    findings["duplicate_entity_time_keys"] = int(dup_key)
    if dup_key > 0:
        raise ValueError(f"Found {dup_key} duplicate (location_id, product_id, week_start_date) rows.")

    # Product coverage check
    n_products = df["product_id"].nunique()
    findings["distinct_products"] = n_products
    if n_products < 2:
        raise ValueError(f"Fewer than 2 distinct product_ids ({n_products}). Dataset may be corrupt.")

    # Leakage columns still present in source (expected – we strip them later)
    leakage_present = [c for c in LEAKAGE_COLS if c in df.columns]
    findings["leakage_cols_present_in_raw"] = leakage_present

    # Rows per region-week
    rw_counts = df.groupby(["location_id", TIME_COL])["product_id"].count()
    findings["min_products_per_rw"] = int(rw_counts.min())
    findings["max_products_per_rw"] = int(rw_counts.max())

    logger.info("Validation findings: %s", findings)
    return findings


# ─── 3. Target Construction ────────────────────────────────────────────────────

def build_correct_target(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construct the correct next-week demand target by forward-shifting
    units_sold within each (location_id, product_id) group.

    Rules:
      - Sort by (location_id, product_id, week_start_date).
      - For each entity, TARGET = units_sold of the immediately following week.
      - Rows where the following week is absent (last observed week per entity,
        or genuine gap in the time series) receive NaN → must not be trained on.
      - The original synthetic RAW_TARGET column is preserved for reference
        but renamed to avoid accidental use.

    Returns augmented DataFrame with new column TARGET_COL.
    """
    logger.info("Building correct forward-shifted target...")
    df = df.sort_values(ENTITY_COLS + [TIME_COL]).copy()

    # Shift units_sold forward by 1 within each entity
    df[TARGET_COL] = (
        df.groupby(ENTITY_COLS)["units_sold"].shift(-1)
    )

    # Verify the forward shift aligns to the next consecutive week
    if "week_number" in df.columns:
        df["_next_week_num"] = df.groupby(ENTITY_COLS)["week_number"].shift(-1)
        misaligned = (
            df["_next_week_num"].notna()
            & (df["_next_week_num"] != df["week_number"] + 1)
        )
        df.drop(columns=["_next_week_num"], inplace=True)
    else:
        df["_next_week_date"] = df.groupby(ENTITY_COLS)[TIME_COL].shift(-1)
        diff_days = (df["_next_week_date"] - df[TIME_COL]).dt.days
        misaligned = df["_next_week_date"].notna() & (~diff_days.between(6, 8))
        df.drop(columns=["_next_week_date"], inplace=True)

    n_misaligned = misaligned.sum()
    if n_misaligned > 0:
        logger.warning(
            "%d rows have a next-week observation that is NOT consecutive. "
            "These will get NaN targets to avoid week-skip leakage.",
            n_misaligned,
        )
        df.loc[misaligned, TARGET_COL] = np.nan

    n_with_target = df[TARGET_COL].notna().sum()
    n_missing_target = df[TARGET_COL].isna().sum()
    logger.info(
        "Target built: %d rows have a valid target, %d rows have no target "
        "(last week per entity or week-gap rows).",
        n_with_target, n_missing_target,
    )

    # Also keep the synthetic target for comparison – renamed to avoid confusion
    if RAW_TARGET in df.columns:
        df.rename(columns={RAW_TARGET: "synthetic_target_ref"}, inplace=True)

    return df


# ─── 4. Missing-week scaffold ──────────────────────────────────────────────────

def detect_week_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Identify (entity, week) pairs that are absent from the dataset.
    Returns a DataFrame with columns: location_id, product_id, week_start_date,
    gap_type = 'missing_entity_week'.

    We do NOT fill these gaps with zero sales. Instead, we flag them so that
    lag feature computation correctly produces NaN rather than a false zero.
    """
    all_weeks = sorted(df[TIME_COL].unique())
    all_entities = df[ENTITY_COLS].drop_duplicates()
    expected_total = len(all_entities) * len(all_weeks)

    if len(df) == expected_total and df.duplicated(subset=ENTITY_COLS + [TIME_COL]).sum() == 0:
        logger.info(
            "Week-gap scan: %d entities × %d weeks = %d rows. Perfectly complete grid with 0 gaps.",
            len(all_entities), len(all_weeks), len(df),
        )
        return pd.DataFrame(columns=["location_id", "product_id", TIME_COL, "gap_type"])

    # Full Cartesian: every entity × every week
    full_index = pd.MultiIndex.from_product(
        [all_entities["location_id"].unique(),
         all_entities["product_id"].unique(),
         all_weeks],
        names=["location_id", "product_id", TIME_COL],
    )
    full_df = pd.DataFrame(index=full_index).reset_index()

    # Left-join to find missing rows
    merged = full_df.merge(
        df[ENTITY_COLS + [TIME_COL, "units_sold"]],
        on=ENTITY_COLS + [TIME_COL],
        how="left",
    )
    gaps = merged[merged["units_sold"].isna()].drop(columns=["units_sold"])
    gaps["gap_type"] = "missing_entity_week"

    logger.info(
        "Week-gap scan: %d (entity, week) pairs are absent from the dataset "
        "(these are NOT imputed with zero sales).",
        len(gaps),
    )
    return gaps


# ─── 5. Festival-event encoding ───────────────────────────────────────────────

def encode_festival_event(df: pd.DataFrame) -> pd.DataFrame:
    """
    Replace NaN in festival_event with 'none'.
    78.4% of rows are NaN (structurally correct – most weeks have no festival).
    """
    df = df.copy()
    df["festival_event"] = df["festival_event"].fillna("none")
    return df


# ─── 6. Unit-size normalization ───────────────────────────────────────────────

_UNIT_RE_G  = r"(\d+(?:\.\d+)?)\s*g$"
_UNIT_RE_KG = r"(\d+(?:\.\d+)?)\s*kg$"
_UNIT_RE_ML = r"(\d+(?:\.\d+)?)\s*ml$"
_UNIT_RE_L  = r"(\d+(?:\.\d+)?)\s*[lL]$"


def parse_unit_size_grams(unit_size: pd.Series) -> pd.Series:
    """
    Parse unit_size strings to a numeric base-unit value in grams (solid)
    or millilitres (liquid), stored as `unit_size_ml_or_g`.
    Returns NaN for unrecognised formats.
    This is used as a numeric feature, NOT as a replacement for the
    original `unit_size` categorical column.
    """
    s = unit_size.str.strip()
    result = pd.Series(np.nan, index=unit_size.index, dtype=float)

    g_match  = s.str.extract(_UNIT_RE_G,  expand=False).astype(float)
    kg_match = s.str.extract(_UNIT_RE_KG, expand=False).astype(float) * 1000
    ml_match = s.str.extract(_UNIT_RE_ML, expand=False).astype(float)
    l_match  = s.str.extract(_UNIT_RE_L,  expand=False).astype(float) * 1000

    result = result.where(g_match.isna(),  g_match)
    result = result.where(kg_match.isna(), kg_match)
    result = result.where(ml_match.isna(), ml_match)
    result = result.where(l_match.isna(),  l_match)
    return result


# ─── 7. Season ordinal encoding ───────────────────────────────────────────────

def encode_season(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["season_ord"] = df["season"].map(SEASON_ORDER).astype("Int8")
    return df


# ─── 8. Full preparation pipeline ─────────────────────────────────────────────

def prepare(df_raw: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    """
    Run full data preparation:
      1. Pre-validate raw data
      2. Build correct forward-shifted target
      3. Detect week gaps (no imputation)
      4. Encode festival_event nulls
      5. Parse unit_size to numeric
      6. Encode season ordinally
      7. Assign temporal split labels

    Returns:
      df_prepared : DataFrame ready for feature engineering
      meta        : dict of preparation metadata (gap counts, target stats, etc.)
    """
    meta = {}

    # Step 1 – Validate
    meta["validation"] = validate_raw(df_raw)

    # Step 2 – Correct target
    df = build_correct_target(df_raw)

    # Step 3 – Gap detection (informational; gaps stay as absent rows)
    gaps = detect_week_gaps(df)
    meta["n_missing_entity_weeks"] = len(gaps)
    meta["gap_detail"] = gaps

    # Step 4 – Festival encoding
    df = encode_festival_event(df)

    # Step 5 – Unit-size numeric
    df["unit_size_ml_or_g"] = parse_unit_size_grams(df["unit_size"])

    # Step 6 – Season ordinal
    df = encode_season(df)

    # Step 7 – Assign temporal split label
    sorted_weeks = sorted(df[TIME_COL].unique())
    week_to_idx  = {w: i for i, w in enumerate(sorted_weeks)}
    df["week_idx"] = df[TIME_COL].map(week_to_idx)

    def _split_label(idx):
        if idx < TRAIN_END_IDX:
            return "train"
        elif idx < VAL_END_IDX:
            return "val"
        else:
            return "test"

    df["split"] = df["week_idx"].apply(_split_label)

    # Remove rows with no valid target (last week per entity, week-gap entities)
    before = len(df)
    df_trainable = df[df[TARGET_COL].notna()].copy()
    after = len(df_trainable)
    meta["rows_dropped_no_target"] = before - after
    meta["rows_with_valid_target"] = after

    # Split counts
    split_counts = df_trainable["split"].value_counts().to_dict()
    meta["split_counts"] = split_counts
    logger.info("Data preparation complete. Split counts: %s", split_counts)

    return df_trainable, meta


# ─── 9. Chronological train/val/test extractor ────────────────────────────────

def get_splits(df: pd.DataFrame):
    """
    Return (df_train, df_val, df_test) based on pre-assigned 'split' column.
    Integrity check: ensure no val/test week appears in train.
    """
    df_train = df[df["split"] == "train"].copy()
    df_val   = df[df["split"] == "val"].copy()
    df_test  = df[df["split"] == "test"].copy()

    train_weeks = set(df_train[TIME_COL])
    val_leak    = set(df_val[TIME_COL]) & train_weeks
    test_leak   = set(df_test[TIME_COL]) & train_weeks

    if val_leak or test_leak:
        raise RuntimeError(
            f"Temporal leakage detected! Val/test weeks overlap with train: "
            f"val_overlap={val_leak}, test_overlap={test_leak}"
        )

    logger.info(
        "Splits: train=%d rows (%d weeks), val=%d rows (%d weeks), test=%d rows (%d weeks)",
        len(df_train), df_train[TIME_COL].nunique(),
        len(df_val),   df_val[TIME_COL].nunique(),
        len(df_test),  df_test[TIME_COL].nunique(),
    )
    return df_train, df_val, df_test
