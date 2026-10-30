"""
config.py – Central configuration for the Demand Intelligence Agent pipeline.

All paths, constants, and feature lists live here so every module
imports from a single source of truth.
"""

from pathlib import Path

# ─── Project roots ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(r"c:\Users\SAMSUNG\ai-multi-agent-supply-chain")
AGENT_DIR    = PROJECT_ROOT / "demand_agent"
OUTPUTS_DIR  = AGENT_DIR / "outputs"

# ─── Data paths ───────────────────────────────────────────────────────────────
FULL_STANDARDIZED_CSV = (
    PROJECT_ROOT
    / "Datasets" / "standardized"
    / "std_sales_demand.csv"
)
SOURCE_WORKBOOK_PATH = (
    PROJECT_ROOT
    / "Datasets" / "raw_dataset" / "01_RAW_SOURCE"
    / "sales_history_source.xlsx"
)
RAW_TOP5_CSV = (
    PROJECT_ROOT
    / "Datasets" / "raw_dataset" / "01_RAW_SOURCE"
    / "demand_agent_training.csv"
)
# Prefer complete 200-product standardized data (1,112,000 rows)
RAW_CSV = FULL_STANDARDIZED_CSV if FULL_STANDARDIZED_CSV.exists() else RAW_TOP5_CSV

FESTIVAL_CSV = (
    PROJECT_ROOT
    / "Datasets" / "raw_dataset" / "01_RAW_SOURCE"
    / "festival_calendar.csv"
)

# ─── Output paths ─────────────────────────────────────────────────────────────
MODELS_DIR  = OUTPUTS_DIR / "models"
CHARTS_DIR  = OUTPUTS_DIR / "charts"
METRICS_DIR = OUTPUTS_DIR / "metrics"

# ─── Dataset constants ────────────────────────────────────────────────────────
ENTITY_COLS = ["location_id", "product_id"]   # defines a time-series entity
TIME_COL    = "week_start_date"
TARGET_COL  = "units_sold_next_week"           # our constructed target (shift-1)
RAW_TARGET  = "next_week_demand_target_units"  # original synthetic target (DO NOT use as feature)

N_REGIONS   = 40
N_PRODUCTS  = 200         # full conformed catalog
N_WEEKS     = 139
ROWS_PER_RW = 200         # all 200 products appear per region-week
TOTAL_RECORDS_EXPECTED = N_REGIONS * N_PRODUCTS * N_WEEKS  # 1,112,000

# ─── Temporal split thresholds (week index, 0-based, after sorting) ───────────
# 139 weeks → 138 usable (last week 139 has no forward target, used for forecast)
# Train: weeks 0–99  (100 weeks ≈ 72%)
# Val  : weeks 100–119 (20 weeks ≈ 14%)
# Test : weeks 120–137 (18 weeks ≈ 13%)
TRAIN_END_IDX = 100   # exclusive upper bound for training weeks
VAL_END_IDX   = 120   # exclusive upper bound for validation weeks
# weeks >= VAL_END_IDX → test set

# ─── Lag / rolling window config ──────────────────────────────────────────────
LAG_WEEKS       = [1, 2, 4, 8]
ROLLING_WINDOWS = [4, 8, 13]    # in weeks (4 ≈ month, 8 ≈ 2 months, 13 ≈ quarter)

# ─── Leakage blacklist – NEVER include these as model features ────────────────
LEAKAGE_COLS = {
    RAW_TARGET,                    # original synthetic forward value
    "forecast_target_start",       # future date boundary
    "forecast_target_end",         # future date boundary
    "demand_rank",                 # precomputed rank
    "demand_rank_200",             # current week target-derived rank
    "top5_flag",                   # current week rank flag
    "demand_id",                   # arbitrary row identifier
    "region_week_key",             # string encoding of region + date
    "region_product_week_key",     # string encoding of region + date + product
    "selling_unit_workbook",       # source-file provenance
    "selling_unit_sheet",          # encodes week identity → temporal leakage
    "selling_unit_source_row",     # encodes row position → positional leakage
    "selling_unit_lookup_hint",    # cell address in source workbook
    "reference_layer",             # metadata
    "anchor_status",               # metadata
    "data_source",                 # metadata
    "recorded_at",                 # metadata
    "rank_scope",                  # metadata
    "rank_basis",                  # metadata
    "assortment_size",             # metadata
    "week_end_date",               # deterministic from week_start_date
    "sales_value_rs",              # units_sold * price (same-period target leak)
    "opening_inventory_units",     # operational stock snapshot
    "replenishment_units",         # operational stock snapshot
    "available_inventory_units",   # operational stock snapshot
    "closing_inventory_units",     # operational stock snapshot
    "demand_score",                # same-period sales proxy
    "record_hash",                 # ETL hash
    "source_file",                 # ETL provenance
    "source_row_number",           # ETL provenance
    "ingestion_timestamp",         # ETL timestamp
    "standardization_timestamp",   # ETL timestamp
    "standardization_rule_version",# ETL metadata
    "demand_agent_ref",            # provenance
    "demand_agent_source_row",     # provenance
    "demand_agent_lookup_hint",    # provenance
    # Target itself:
    TARGET_COL,
}

# ─── Categorical columns (for encoding and CatBoost) ─────────────────────────
CAT_COLS = [
    "location_id",
    "product_id",
    "region_of_kolkata",
    "category_name",
    "brand",
    "quality_level",
    "unit_size",
    "weather_condition",
    "season",
    "festival_event",   # filled nulls → "none"
]

# ─── Season ordinal mapping ───────────────────────────────────────────────────
SEASON_ORDER = {"Winter": 0, "Summer": 1, "Monsoon": 2, "Post-Monsoon": 3}

# ─── Ranking K ────────────────────────────────────────────────────────────────
RANK_K_AVAILABLE = 200  # full 200 products per region-week
RANK_K_REQUESTED = 10   # requested Top 10 products per region

