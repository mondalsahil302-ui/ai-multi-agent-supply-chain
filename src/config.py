"""Configuration settings for Demand Dataset ETL Pipeline.
Defines input source paths, master entities, target schemas, and processing rules.
"""

from pathlib import Path
import os

# Project root and output directory paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
STAGED_DIR = DATA_DIR / "staged"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = DATA_DIR / "reports"

for dir_path in [RAW_DIR, STAGED_DIR, PROCESSED_DIR, REPORTS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Default Source File Paths
DOWNLOADS_DIR = Path(r"D:\Downloads")
DOCUMENTS_DIR = Path(os.path.expanduser(r"~\Documents"))

RAW_DEMAND_FILE = (
    DOWNLOADS_DIR / "Demand of last 2 years.xlsx"
    if (DOWNLOADS_DIR / "Demand of last 2 years.xlsx").exists()
    else RAW_DIR / "Demand of last 2 years.xlsx"
)

RAW_DEMAND_SHEET_NAME = "demand_training_data"

LOCATION_MASTER_FILE = (
    DOWNLOADS_DIR / "Location_ID_Master_40_For_Sharing.csv"
    if (DOWNLOADS_DIR / "Location_ID_Master_40_For_Sharing.csv").exists()
    else RAW_DIR / "Location_ID_Master_40_For_Sharing.csv"
)

PRODUCT_MASTER_FILE = (
    DOWNLOADS_DIR / "Product_ID_Master_200_For_Sharing.csv"
    if (DOWNLOADS_DIR / "Product_ID_Master_200_For_Sharing.csv").exists()
    else RAW_DIR / "Product_ID_Master_200_For_Sharing.csv"
)

TARGET_TEMPLATE_FILE = DOCUMENTS_DIR / "demand agent sheet.xlsx"

# Standard Target Schema for Demand Agent
DEMAND_AGENT_COLUMNS = [
    "location_id",
    "region_of_kolkata",
    "product_id",
    "category_code",
    "category_name",
    "brand",
    "quality_level",
    "date",
    "units_demanded",
    "day_of_week",
    "is_weekend",
    "is_public_holiday",
    "unfulfilled_demand",
    "unit_size",
    "selling_price",
]

# Audit/Reference metadata columns in raw Excel to exclude during clean staging
AUDIT_METADATA_COLUMNS = [
    "selling_unit_workbook",
    "selling_unit_sheet",
    "selling_unit_source_row",
    "selling_unit_lookup_hint",
    "reference_layer",
    "anchor_status",
    "data_source",
    "rank_scope",
    "rank_basis",
    "recorded_at",
]
