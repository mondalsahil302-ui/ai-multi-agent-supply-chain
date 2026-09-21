"""
Integration of updated datasets:
1. Sales History: SELL_of_past_2_years_COMBINED.csv -> unblocks FACT_SALES
2. Inventory Transactions: Inventory_Transactions_417000_Reconstructed.csv -> unblocks FACT_INVENTORY_TRANSACTION
3. Warehouse Pickers: Warehouse_Picker_IDs_Only.csv -> DIM_PICKER & BRIDGE_WAREHOUSE_PICKER
"""

import pandas as pd
import numpy as np
import json, re, shutil
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(r"D:\ai-multi-agent-supply-chain")
RAW  = BASE / "data" / "01_raw"
STG  = BASE / "data" / "03_staging"
STD  = BASE / "data" / "04_standardized"
CUR  = BASE / "data" / "06_curated"
FEAT = BASE / "data" / "07_features"
VAL  = BASE / "data" / "08_validation"
AGT  = BASE / "data" / "09_agent_ready"
DOC  = BASE / "data" / "10_documentation"
NOW  = datetime.now(timezone.utc).isoformat()

def snake(s):
    s = str(s).strip()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^\w]", "", s)
    return s.lower()

# ==============================================================================
# 1. WAREHOUSE-PICKER INTEGRATION
# ==============================================================================
print("1. Integrating Warehouse-Picker dataset...")
raw_picker = pd.read_csv(RAW / "Warehouse_Picker_IDs_Only.csv")

# Staging: exact 1:1 copy with audit metadata
stg_picker = raw_picker.copy()
stg_picker["_row_id"] = np.arange(1, len(stg_picker) + 1)
stg_picker["_source_file"] = "Warehouse_Picker_IDs_Only.csv"
stg_picker["_source_sheet"] = "default"
stg_picker["_staged_at"] = NOW
stg_picker.to_csv(STG / "stg_warehouse_pickers.csv", index=False)

# Standardized: map WH-XXX to canonical WH-KOL-XXX
std_picker = raw_picker.copy()
std_picker.columns = ["warehouse_id", "picker_id"]
std_picker["warehouse_id_raw"] = std_picker["warehouse_id"]
std_picker["warehouse_id"] = std_picker["warehouse_id"].apply(
    lambda x: re.sub(r"^WH-(\d+)$", r"WH-KOL-\1", str(x).strip())
)
std_picker["picker_id"] = std_picker["picker_id"].str.strip()
std_picker["standardized_at"] = NOW
std_picker.to_csv(STD / "std_warehouse_pickers.csv", index=False)

# Curated: DIM_PICKER and BRIDGE_WAREHOUSE_PICKER
dim_picker = std_picker[["picker_id", "warehouse_id"]].copy()
dim_picker["source_file"] = "Warehouse_Picker_IDs_Only.csv"
dim_picker["pipeline_timestamp"] = NOW
dim_picker.to_csv(CUR / "DIM_PICKER.csv", index=False)
dim_picker.to_csv(AGT / "DIM_PICKER.csv", index=False)

bridge_picker = std_picker[["warehouse_id", "picker_id"]].copy()
bridge_picker["source_file"] = "Warehouse_Picker_IDs_Only.csv"
bridge_picker["pipeline_timestamp"] = NOW
bridge_picker.to_csv(CUR / "BRIDGE_WAREHOUSE_PICKER.csv", index=False)
bridge_picker.to_csv(AGT / "BRIDGE_WAREHOUSE_PICKER.csv", index=False)
print(f"  DIM_PICKER & BRIDGE_WAREHOUSE_PICKER created ({len(dim_picker)} rows)")

# Enrich WAREHOUSE_FEATURES with assigned_picker_count
wh_feat = pd.read_csv(CUR / "DIM_WAREHOUSE.csv")
pkr_counts = bridge_picker.groupby("warehouse_id")["picker_id"].count().reset_index()
pkr_counts.rename(columns={"picker_id": "assigned_picker_count"}, inplace=True)

wh_features_file = FEAT / "WAREHOUSE_FEATURES.csv"
if wh_features_file.exists():
    wh_features = pd.read_csv(wh_features_file)
    if "assigned_picker_count" in wh_features.columns:
        wh_features.drop(columns=["assigned_picker_count"], inplace=True)
    wh_features = wh_features.merge(pkr_counts, on="warehouse_id", how="left")
    wh_features["assigned_picker_count"] = wh_features["assigned_picker_count"].fillna(0).astype(int)
    wh_features.to_csv(FEAT / "WAREHOUSE_FEATURES.csv", index=False)
    wh_features.to_csv(AGT / "WAREHOUSE_FEATURES.csv", index=False)
    print("  WAREHOUSE_FEATURES enriched with assigned_picker_count")

# ==============================================================================
# 2. INVENTORY TRANSACTIONS INTEGRATION (Replacing Blocked Pointer)
# ==============================================================================
print("2. Integrating Inventory Transactions dataset (chunked)...")
src_inv = RAW / "Inventory_Transactions_417000_Reconstructed.csv"

# Stream into staging
stg_inv_path = STG / "stg_inventory_transactions.csv"
std_inv_path = STD / "std_inventory_transactions.csv"
cur_inv_path = CUR / "FACT_INVENTORY_TRANSACTION.csv"

# Process in chunks of 50,000 for token and memory efficiency
chunk_size = 50000
row_offset = 1

first_chunk = True
for chunk in pd.read_csv(src_inv, chunksize=chunk_size):
    # Staging
    chunk_stg = chunk.copy()
    chunk_stg["_row_id"] = np.arange(row_offset, row_offset + len(chunk))
    chunk_stg["_source_file"] = "Inventory_Transactions_417000_Reconstructed.csv"
    chunk_stg["_staged_at"] = NOW
    chunk_stg.to_csv(stg_inv_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)

    # Standardized
    chunk_std = chunk.copy()
    chunk_std.columns = [snake(c) for c in chunk_std.columns]
    chunk_std["transaction_id"] = chunk_std["transaction_id"].str.strip()
    chunk_std["warehouse_id"] = chunk_std["warehouse_id"].str.strip()
    chunk_std["product_id"] = chunk_std["product_id"].str.strip()
    chunk_std["week_start_date"] = pd.to_datetime(chunk_std["week_start_date"]).dt.date
    chunk_std["week_end_date"] = pd.to_datetime(chunk_std["week_end_date"]).dt.date
    chunk_std["sold_units"] = pd.to_numeric(chunk_std["sold_units"], errors="coerce")
    chunk_std["standardized_at"] = NOW
    chunk_std.to_csv(std_inv_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)

    # Curated FACT_INVENTORY_TRANSACTION
    chunk_cur = chunk_std[[
        "transaction_id", "warehouse_product_week_key", "week_id",
        "week_start_date", "week_end_date", "warehouse_id", "product_id",
        "product_name", "unit_size", "sold_units", "transaction_type",
        "direction", "source_basis", "record_status"
    ]].copy()
    chunk_cur["pipeline_timestamp"] = NOW
    chunk_cur.to_csv(cur_inv_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)

    row_offset += len(chunk)
    first_chunk = False

# Copy to agent-ready
shutil.copy2(cur_inv_path, AGT / "FACT_INVENTORY_TRANSACTION.csv")

# Remove blocked marker files
for d in [CUR, AGT]:
    bf = d / "FACT_INVENTORY_TRANSACTION__BLOCKED.csv"
    if bf.exists():
        bf.unlink()
print("  FACT_INVENTORY_TRANSACTION.csv created (417,000 rows), blocked marker removed")

# ==============================================================================
# 3. SALES HISTORY INTEGRATION (Replacing Blocked Pointer)
# ==============================================================================
print("3. Integrating Sales History dataset (chunked)...")
src_sales = RAW / "SELL_of_past_2_years_COMBINED.csv"

stg_sales_path = STG / "stg_sales_history.csv"
std_sales_path = STD / "std_sales_history.csv"
cur_sales_path = CUR / "FACT_SALES.csv"

first_chunk = True
row_offset = 1
for chunk in pd.read_csv(src_sales, chunksize=chunk_size):
    # Staging
    chunk_stg = chunk.copy()
    chunk_stg["_row_id"] = np.arange(row_offset, row_offset + len(chunk))
    chunk_stg["_source_file"] = "SELL_of_past_2_years_COMBINED.csv"
    chunk_stg["_staged_at"] = NOW
    chunk_stg.to_csv(stg_sales_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)

    # Standardized
    chunk_std = chunk.copy()
    chunk_std.columns = [snake(c) for c in chunk_std.columns]
    chunk_std["region_product_week_key"] = chunk_std["region_product_week_key"].str.strip()
    chunk_std["region_id"] = chunk_std["region_id"].str.strip()
    chunk_std["product_id"] = chunk_std["product_id"].str.strip()
    chunk_std["week_start_date"] = pd.to_datetime(chunk_std["week_start_date"]).dt.date
    chunk_std["week_end_date"] = pd.to_datetime(chunk_std["week_end_date"]).dt.date
    for nc in ["units_sold", "opening_inventory_units", "closing_inventory_units",
               "available_inventory_units", "avg_selling_price_rs", "sales_value_rs",
               "promotion_flag", "discount_pct", "stockout_flag", "holiday_flag"]:
        if nc in chunk_std.columns:
            chunk_std[nc] = pd.to_numeric(chunk_std[nc], errors="coerce")
    chunk_std["standardized_at"] = NOW
    chunk_std.to_csv(std_sales_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)

    # Curated FACT_SALES
    chunk_cur = chunk_std[[
        "region_product_week_key", "region_week_key", "week_number",
        "week_start_date", "week_end_date", "region_id", "region_of_kolkata",
        "product_id", "product_name", "category_name", "brand", "quality_level",
        "unit_size", "opening_inventory_units", "replenishment_units",
        "available_inventory_units", "units_sold", "closing_inventory_units",
        "avg_selling_price_rs", "sales_value_rs", "promotion_flag", "discount_pct",
        "stockout_flag", "holiday_flag", "festival_event", "season",
        "temperature_c", "rainfall_mm", "humidity_pct", "weather_condition",
        "demand_score", "demand_rank_200", "top5_flag", "data_source"
    ]].copy()
    chunk_cur["pipeline_timestamp"] = NOW
    chunk_cur.to_csv(cur_sales_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)

    row_offset += len(chunk)
    first_chunk = False

# Copy to agent-ready
shutil.copy2(cur_sales_path, AGT / "FACT_SALES.csv")

# Remove blocked marker files
for d in [CUR, AGT]:
    bf = d / "FACT_SALES__BLOCKED.csv"
    if bf.exists():
        bf.unlink()
print("  FACT_SALES.csv created (448,000 rows), blocked marker removed")

# ==============================================================================
# 4. UPDATE ENTITY MAPPING
# ==============================================================================
print("4. Updating entity mapping...")
em_path = BASE / "data" / "05_entity_mapping" / "entity_mapping.csv"
em_df = pd.read_csv(em_path)

# Add new mappings
new_mappings = [
    {
        "source_table": "Warehouse_Picker_IDs_Only.csv",
        "source_field": "picker_id",
        "canonical_entity": "DIM_PICKER",
        "canonical_field": "picker_id",
        "relationship_type": "PK",
        "target_table": "DIM_PICKER",
        "target_field": "picker_id",
        "confidence": "HIGH",
        "transformation_required": "None",
        "notes": "750 unique pickers"
    },
    {
        "source_table": "Warehouse_Picker_IDs_Only.csv",
        "source_field": "warehouse_id",
        "canonical_entity": "BRIDGE_WAREHOUSE_PICKER",
        "canonical_field": "warehouse_id",
        "relationship_type": "FK",
        "target_table": "DIM_WAREHOUSE",
        "target_field": "warehouse_id",
        "confidence": "HIGH",
        "transformation_required": "Mapped WH-XXX -> WH-KOL-XXX to align with canonical warehouse IDs",
        "notes": "15 warehouses x 50 pickers"
    },
    {
        "source_table": "Inventory_Transactions_417000_Reconstructed.csv",
        "source_field": "transaction_id",
        "canonical_entity": "FACT_INVENTORY_TRANSACTION",
        "canonical_field": "transaction_id",
        "relationship_type": "PK",
        "target_table": "FACT_INVENTORY_TRANSACTION",
        "target_field": "transaction_id",
        "confidence": "HIGH",
        "transformation_required": "snake_case columns, date casting",
        "notes": "417,000 transaction records (unblocked)"
    },
    {
        "source_table": "SELL_of_past_2_years_COMBINED.csv",
        "source_field": "region_product_week_key",
        "canonical_entity": "FACT_SALES",
        "canonical_field": "region_product_week_key",
        "relationship_type": "PK",
        "target_table": "FACT_SALES",
        "target_field": "region_product_week_key",
        "confidence": "HIGH",
        "transformation_required": "snake_case columns, date casting",
        "notes": "448,000 sales records (unblocked)"
    }
]
em_df = pd.concat([em_df, pd.DataFrame(new_mappings)], ignore_index=True).drop_duplicates(subset=["source_table", "source_field", "canonical_entity", "canonical_field"])
em_df.to_csv(em_path, index=False)
em_df.to_json(BASE / "data" / "05_entity_mapping" / "entity_mapping.json", orient="records", indent=2)
print(f"  Entity mapping updated: {len(em_df)} rules")

print("Stage 03B execution finished.")

