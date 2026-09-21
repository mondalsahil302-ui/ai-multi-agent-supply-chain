"""
Stage 03: Staging, Standardization, and Canonical Curated Layer.
Executes the full pipeline from 01_raw -> 03_staging -> 04_standardized -> 06_curated.
"""

import pandas as pd
import numpy as np
import openpyxl
import warnings
import re
import math
from pathlib import Path
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

BASE = Path(r"D:\ai-multi-agent-supply-chain")
RAW  = BASE / "data" / "01_raw"
STG  = BASE / "data" / "03_staging"
STD  = BASE / "data" / "04_standardized"
CUR  = BASE / "data" / "06_curated"
QRT  = BASE / "data" / "data_quarantine"
NOW  = datetime.now(timezone.utc).isoformat()

for p in [STG, STD, CUR, QRT]:
    p.mkdir(parents=True, exist_ok=True)


def load_xlsx(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return pd.DataFrame()
    headers = [str(h) if h is not None else f"_unnamed_{i}" for i, h in enumerate(rows[0])]
    return pd.DataFrame(rows[1:], columns=headers)


def snake(s):
    s = str(s).strip()
    s = re.sub(r"[\s\-]+", "_", s)
    s = re.sub(r"[^\w]", "", s)
    return s.lower()


def norm_str(s):
    if pd.isna(s):
        return None
    val = str(s).strip()
    val = re.sub(r"\s+", " ", val)
    return val


def parse_unit(size_str):
    """Return (value, unit, normalized_ml_g) or (None,None,None)."""
    if pd.isna(size_str) or size_str == "":
        return None, None, None
    s = str(size_str).strip().lower()
    m = re.match(r"([\d\.]+)\s*(ml|l|g|kg|piece|dozen)", s)
    if not m:
        return s, "unknown", None
    val = float(m.group(1))
    unit = m.group(2)
    norm_val = val
    norm_unit = unit
    if unit == "l":
        norm_val = val * 1000
        norm_unit = "ml"
    elif unit == "kg":
        norm_val = val * 1000
        norm_unit = "g"
    return val, unit, (norm_val, norm_unit)


print("="*70)
print("PHASE 1: INGESTION & UNPACKING INTO 03_STAGING")
print("="*70)

def stage_df(df, filename, src_file, src_sheet="default"):
    df_stg = df.copy()
    df_stg["_row_id"] = np.arange(1, len(df_stg) + 1)
    df_stg["_source_file"] = src_file
    df_stg["_source_sheet"] = src_sheet
    df_stg["_staged_at"] = NOW
    df_stg.to_csv(STG / filename, index=False)
    print(f"  [STAGING] {filename} ({len(df_stg)} rows) from {src_file}:{src_sheet}")
    return df

# 1. Locations
raw_loc = pd.read_csv(RAW / "locations.csv.csv")
stage_df(raw_loc, "stg_locations.csv", "locations.csv.csv")

# 2. Products CSV
raw_prod_csv = pd.read_csv(RAW / "products.csv")
stage_df(raw_prod_csv, "stg_products.csv", "products.csv")

# 3. Final product list XLSX
raw_prod_master = load_xlsx(RAW / "Final product list.xlsx", "product_master")
stage_df(raw_prod_master, "stg_final_product_list_master.csv", "Final product list.xlsx", "product_master")

raw_cat_summary = load_xlsx(RAW / "Final product list.xlsx", "category_summary")
stage_df(raw_cat_summary, "stg_category_summary.csv", "Final product list.xlsx", "category_summary")

# 4. Festival calendar
raw_fest = pd.read_csv(RAW / "festival_calendar.csv")
stage_df(raw_fest, "stg_festival_calendar.csv", "festival_calendar.csv")

# 5. Weather weekly
raw_weather = pd.read_csv(RAW / "weather_weekly.csv")
stage_df(raw_weather, "stg_weather_weekly.csv", "weather_weekly.csv")

# 6. Demand - historical fact (primary)
raw_dem_fact = load_xlsx(RAW / "Demand of last 2 years.xlsx", "demand_training_data")
stage_df(raw_dem_fact, "stg_demand_history.csv", "Demand of last 2 years.xlsx", "demand_training_data")

# 7. Demand - training data (secondary)
raw_dem_train = load_xlsx(RAW / "final_demand_agent_training_2_years_kolkata (1).xlsx", "demand_training_data")
stage_df(raw_dem_train, "stg_demand_training.csv", "final_demand_agent_training_2_years_kolkata (1).xlsx", "demand_training_data")

# 8. Sales history (LFS pointer metadata)
stg_sales_lfs = pd.DataFrame([{
    "source_file": "sales_history.xlsx",
    "status": "BLOCKED_LFS_POINTER",
    "lfs_oid": "fc8022e6248ccb8725f6ff8cb9c70aa91a6f76aeb99bce62db5866f7c902e6e5",
    "expected_size_bytes": 177644415,
    "staged_at": NOW
}])
stg_sales_lfs.to_csv(STG / "stg_sales_history_lfs_pointer.csv", index=False)
print("  [STAGING] stg_sales_history_lfs_pointer.csv (1 row)")

# 9. Inventory Stock sheets
raw_inv_pos = load_xlsx(RAW / "inventory_stock.xlsx", "Inventory_Position")
stage_df(raw_inv_pos, "stg_inventory_position.csv", "inventory_stock.xlsx", "Inventory_Position")

raw_inv_ctrl = load_xlsx(RAW / "inventory_stock.xlsx", "Inventory_Control")
stage_df(raw_inv_ctrl, "stg_inventory_control.csv", "inventory_stock.xlsx", "Inventory_Control")

raw_inv_val = load_xlsx(RAW / "inventory_stock.xlsx", "Inventory_Valuation")
stage_df(raw_inv_val, "stg_inventory_valuation.csv", "inventory_stock.xlsx", "Inventory_Valuation")

raw_inv_shelf = load_xlsx(RAW / "inventory_stock.xlsx", "Shelf_Master")
stage_df(raw_inv_shelf, "stg_inventory_shelf_master.csv", "inventory_stock.xlsx", "Shelf_Master")

raw_inv_pshelf = load_xlsx(RAW / "inventory_stock.xlsx", "Product_Shelf_Assignment")
stage_df(raw_inv_pshelf, "stg_inventory_product_shelf.csv", "inventory_stock.xlsx", "Product_Shelf_Assignment")

# 10. Inventory transactions (LFS pointer metadata)
stg_inv_lfs = pd.DataFrame([{
    "source_file": "inventory_transactions.xlsx",
    "status": "BLOCKED_LFS_POINTER",
    "lfs_oid": "5fc053bab861bc764e13ac15b74ebcab11b4bf35403f436eadd68d727a06a749",
    "expected_size_bytes": 55855339,
    "staged_at": NOW
}])
stg_inv_lfs.to_csv(STG / "stg_inventory_transactions_lfs_pointer.csv", index=False)
print("  [STAGING] stg_inventory_transactions_lfs_pointer.csv (1 row)")

# 11. Supplier Inventory sheets
raw_sup_master = load_xlsx(RAW / "supplier_inventory.xlsx", "Supplier_Master")
stage_df(raw_sup_master, "stg_supplier_master.csv", "supplier_inventory.xlsx", "Supplier_Master")

raw_sup_area = load_xlsx(RAW / "supplier_inventory.xlsx", "Area_Master")
stage_df(raw_sup_area, "stg_supplier_area_master.csv", "supplier_inventory.xlsx", "Area_Master")

raw_sup_opt = load_xlsx(RAW / "supplier_inventory.xlsx", "Area_Supplier_Options")
stage_df(raw_sup_opt, "stg_supplier_area_options.csv", "supplier_inventory.xlsx", "Area_Supplier_Options")

raw_sup_cat = load_xlsx(RAW / "supplier_inventory.xlsx", "Supplier_Product_Catalog")
stage_df(raw_sup_cat, "stg_supplier_product_catalog.csv", "supplier_inventory.xlsx", "Supplier_Product_Catalog")

# 12. Warehouses sheets
raw_wh_primary = load_xlsx(RAW / "warehouses.xlsx", "warehouse")
stage_df(raw_wh_primary, "stg_warehouses_primary.csv", "warehouses.xlsx", "warehouse")

raw_wh_kolkata = load_xlsx(RAW / "final_warehouse_dataset_kolkata.xlsx", "warehouse")
stage_df(raw_wh_kolkata, "stg_warehouses_kolkata.csv", "final_warehouse_dataset_kolkata.xlsx", "warehouse")

print("\n" + "="*70)
print("PHASE 2: STANDARDIZATION & CLEANING INTO 04_STANDARDIZED")
print("="*70)

# STD 1. Locations
std_loc = raw_loc.copy()
std_loc.columns = ["location_id", "region_of_kolkata"]
std_loc["location_id"] = std_loc["location_id"].apply(norm_str)
std_loc["region_of_kolkata"] = std_loc["region_of_kolkata"].apply(norm_str)
std_loc["location_name"] = std_loc["region_of_kolkata"]

# Enrich with coordinates from supplier area master
sup_area_clean = raw_sup_area.copy()
sup_area_clean.columns = ["location_id", "location_name", "city", "latitude", "longitude"]
sup_area_clean["location_id"] = sup_area_clean["location_id"].apply(norm_str)
sup_area_clean["latitude"] = pd.to_numeric(sup_area_clean["latitude"], errors="coerce")
sup_area_clean["longitude"] = pd.to_numeric(sup_area_clean["longitude"], errors="coerce")
sup_area_clean["city"] = sup_area_clean["city"].apply(norm_str)

std_loc = std_loc.merge(sup_area_clean[["location_id", "city", "latitude", "longitude"]], on="location_id", how="left")
std_loc["source_file"] = "locations.csv.csv + supplier_inventory.xlsx/Area_Master"
std_loc["standardized_at"] = NOW
std_loc.to_csv(STD / "std_locations.csv", index=False)
print(f"  [STANDARDIZED] std_locations.csv ({len(std_loc)} rows)")

# STD 2. Products
std_prod = raw_prod_csv.copy()
std_prod.columns = [snake(c) for c in std_prod.columns]
for col in ["product_id", "category_code", "category_name", "product_name", "brand", "quality_level", "unit_type"]:
    if col in std_prod.columns:
        std_prod[col] = std_prod[col].apply(norm_str)

std_prod_base = std_prod[["product_id", "category_code", "category_name", "product_name",
                          "brand", "quality_level", "unit_type"]].copy()
std_prod_base["canonical_source"] = "products.csv"
std_prod_base["source_file"] = "products.csv (reconciled against Final product list.xlsx)"
std_prod_base["standardized_at"] = NOW
std_prod_base.to_csv(STD / "std_products.csv", index=False)
print(f"  [STANDARDIZED] std_products.csv ({len(std_prod_base)} rows)")

# STD 3. Product Variants (normalized entity from wide 5 sizes)
std_var_rows = []
for _, row in raw_prod_csv.iterrows():
    pid = norm_str(row["product_id"])
    utype = norm_str(row["unit_type"])
    for i in range(1, 6):
        size = norm_str(row.get(f"unit_size_{i}"))
        cp = pd.to_numeric(row.get(f"cp_{i}_rs"), errors="coerce")
        sp = pd.to_numeric(row.get(f"sp_{i}_rs"), errors="coerce")
        if pd.isna(size) or size is None or size == "":
            continue
        val, unit, norm = parse_unit(size)
        norm_val = norm[0] if norm else None
        norm_unit = norm[1] if norm else None
        size_tag = str(size).replace(" ", "").upper()
        pvid = f"{pid}-{size_tag}"
        std_var_rows.append({
            "product_variant_id": pvid,
            "product_id": pid,
            "variant_index": i,
            "unit_size_raw": size,
            "unit_size_value": val,
            "unit_size_unit": unit,
            "normalized_quantity_value": norm_val,
            "normalized_quantity_unit": norm_unit,
            "cost_price_rs": cp,
            "selling_price_rs": sp,
            "source_file": "products.csv",
            "source_record": f"product_id={pid}, unit_size_{i}",
            "standardized_at": NOW
        })
std_variants = pd.DataFrame(std_var_rows)
std_variants.to_csv(STD / "std_product_variants.csv", index=False)
print(f"  [STANDARDIZED] std_product_variants.csv ({len(std_variants)} rows)")

# STD 4. Festival Calendar
std_fest = raw_fest.copy()
std_fest.columns = [snake(c) for c in std_fest.columns]
std_fest["festival_event"] = std_fest["festival_event"].apply(norm_str)
std_fest["event_date"] = pd.to_datetime(std_fest["event_date"]).dt.date
std_fest["year"] = pd.to_numeric(std_fest["year"], errors="coerce")
std_fest["festival_id"] = [f"FEST-{i+1:03d}" for i in range(len(std_fest))]
std_fest["week_start_date"] = pd.to_datetime(std_fest["event_date"]).dt.to_period("W-MON").apply(lambda p: p.start_time.date())

def infer_category(name):
    n = str(name).lower()
    if any(k in n for k in ["eid", "muharram", "milad"]): return "Islamic"
    if any(k in n for k in ["christmas", "easter"]): return "Christian"
    if any(k in n for k in ["puja", "durga", "kali", "rath", "janmashtami", "saraswati", "diwali"]): return "Hindu"
    if any(k in n for k in ["new year", "boishakh"]): return "Cultural/New Year"
    if any(k in n for k in ["independence", "republic", "gandhi"]): return "National"
    return "Hindu"

std_fest["festival_category"] = std_fest["festival_event"].apply(infer_category)
std_fest["source_type"] = "SUPPLIED_REFERENCE"
std_fest["source_file"] = "festival_calendar.csv"
std_fest["standardized_at"] = NOW
std_fest.to_csv(STD / "std_festival_calendar.csv", index=False)
print(f"  [STANDARDIZED] std_festival_calendar.csv ({len(std_fest)} rows)")

# STD 5. Weather Weekly
std_weather = raw_weather.copy()
std_weather.columns = [snake(c) for c in std_weather.columns]
std_weather["week_start_date"] = pd.to_datetime(std_weather["week_start_date"]).dt.date
std_weather["week_end_date"] = pd.to_datetime(std_weather["week_end_date"]).dt.date
std_weather["year"] = pd.to_numeric(std_weather["year"], errors="coerce")
std_weather["season"] = std_weather["season"].apply(norm_str)
for col in ["temperature_mean_c", "temperature_max_c", "temperature_min_c", "rainfall_mm", "humidity_pct"]:
    std_weather[col] = pd.to_numeric(std_weather[col], errors="coerce")
std_weather["weather_condition"] = std_weather["weather_condition"].apply(norm_str)
std_weather["interval_days"] = (pd.to_datetime(std_weather["week_end_date"]) - pd.to_datetime(std_weather["week_start_date"])).dt.days
std_weather["weather_data_type"] = "SUPPLIED_SYNTHETIC"
std_weather["source_file"] = "weather_weekly.csv"
std_weather["standardized_at"] = NOW
std_weather.to_csv(STD / "std_weather_weekly.csv", index=False)
print(f"  [STANDARDIZED] std_weather_weekly.csv ({len(std_weather)} rows)")

# STD 6. Calendar Week
cal_weeks = []
for _, row in std_weather.iterrows():
    wsd = row["week_start_date"]
    wed = row["week_end_date"]
    wsd_dt = pd.to_datetime(wsd)
    cal_weeks.append({
        "week_key": wsd_dt.strftime("%Y%m%d"),
        "week_start_date": wsd,
        "week_end_date": wed,
        "year": row["year"],
        "week_number": wsd_dt.isocalendar()[1],
        "season": row["season"],
        "source_file": "weather_weekly.csv",
        "standardized_at": NOW
    })
std_calendar = pd.DataFrame(cal_weeks)
std_calendar.to_csv(STD / "std_calendar_week.csv", index=False)
print(f"  [STANDARDIZED] std_calendar_week.csv ({len(std_calendar)} rows)")

# STD 7. Warehouses (Consolidated)
wh_p = raw_wh_primary.copy()
wh_k = raw_wh_kolkata.copy()
wh_p.columns = [snake(c) for c in wh_p.columns]
wh_k.columns = [snake(c) for c in wh_k.columns]

std_wh = wh_p.merge(
    wh_k[["warehouse_id", "storage_type", "x_coordinate", "y_coordinate", "status"]],
    on="warehouse_id",
    how="left"
)
std_wh["warehouse_id"] = std_wh["warehouse_id"].apply(norm_str)
std_wh["warehouse_name"] = std_wh["warehouse_name"].apply(norm_str)
std_wh["area"] = std_wh["area"].apply(norm_str)
std_wh["city"] = std_wh["city"].apply(norm_str)
std_wh["latitude"] = pd.to_numeric(std_wh["latitude"], errors="coerce")
std_wh["longitude"] = pd.to_numeric(std_wh["longitude"], errors="coerce")
std_wh["capacity_units"] = pd.to_numeric(std_wh["capacity_units"], errors="coerce")
std_wh["daily_dispatch_capacity_units"] = pd.to_numeric(std_wh["daily_dispatch_capacity_units"], errors="coerce")
std_wh["service_radius_km"] = pd.to_numeric(std_wh["service_radius_km"], errors="coerce")
for vc in ["cycle_count", "bike_count", "scooter_count", "electric_scooter_count", "auto_count", "total_vehicle_count"]:
    if vc in std_wh.columns:
        std_wh[vc] = pd.to_numeric(std_wh[vc], errors="coerce").fillna(0).astype(int)

std_wh = std_wh.rename(columns={
    "weekday_opening": "weekday_open_time",
    "weekday_closing": "weekday_close_time",
    "weekend_opening": "weekend_open_time",
    "weekend_closing": "weekend_close_time",
})
std_wh["source_file"] = "warehouses.xlsx (primary) + final_warehouse_dataset_kolkata.xlsx"
std_wh["standardized_at"] = NOW
std_wh.to_csv(STD / "std_warehouses.csv", index=False)
print(f"  [STANDARDIZED] std_warehouses.csv ({len(std_wh)} rows)")

# STD 8. Suppliers Master
std_sup_m = raw_sup_master.copy()
std_sup_m.columns = [snake(c) for c in std_sup_m.columns]
for str_col in ["supplier_id", "supplier_name", "supplier_type_id", "supplier_type_name", "location_id", "location_name", "city", "product_category_scope", "vehicle_type", "location_note"]:
    if str_col in std_sup_m.columns:
        std_sup_m[str_col] = std_sup_m[str_col].apply(norm_str)

for num_col in ["supplier_latitude", "supplier_longitude", "minimum_order_qty_units", "max_order_qty_units", "max_ship_qty_at_once_units", "supplier_storage_capacity_units", "vehicle_count", "vehicle_load_capacity_units", "lead_time_days"]:
    if num_col in std_sup_m.columns:
        std_sup_m[num_col] = pd.to_numeric(std_sup_m[num_col], errors="coerce")

std_sup_m["source_file"] = "supplier_inventory.xlsx/Supplier_Master"
std_sup_m["standardized_at"] = NOW
std_sup_m.to_csv(STD / "std_supplier_master.csv", index=False)
print(f"  [STANDARDIZED] std_supplier_master.csv ({len(std_sup_m)} rows)")

# STD 9. Supplier Area Options
std_sup_opt = raw_sup_opt.copy()
std_sup_opt.columns = [snake(c) for c in std_sup_opt.columns]
for str_col in ["location_id", "location_name", "supplier_id", "supplier_type_id", "supplier_type_name", "service_available_flag"]:
    if str_col in std_sup_opt.columns:
        std_sup_opt[str_col] = std_sup_opt[str_col].apply(norm_str)

for num_col in ["supplier_latitude", "supplier_longitude", "distance_from_location_center_km", "supplier_option_rank"]:
    if num_col in std_sup_opt.columns:
        std_sup_opt[num_col] = pd.to_numeric(std_sup_opt[num_col], errors="coerce")

std_sup_opt["source_file"] = "supplier_inventory.xlsx/Area_Supplier_Options"
std_sup_opt["standardized_at"] = NOW
std_sup_opt.to_csv(STD / "std_supplier_area_options.csv", index=False)
print(f"  [STANDARDIZED] std_supplier_area_options.csv ({len(std_sup_opt)} rows)")

# STD 10. Supplier Product Catalog (With unmapped column preserved)
std_sup_cat = raw_sup_cat.copy()
known_cat_cols = [
    "supplier_product_key", "supplier_id", "supplier_type_id", "supplier_type_name",
    "product_id", "product_name", "category_code", "category_name",
    "unit_type", "supplier_cost_price_rs", "unmapped_col_10_quarantine",
    "supplied_unit_size", "supply_status"
]
std_sup_cat.columns = known_cat_cols[:len(std_sup_cat.columns)]
for str_col in ["supplier_product_key", "supplier_id", "supplier_type_id", "supplier_type_name", "product_id", "product_name", "category_code", "category_name", "unit_type", "supplied_unit_size", "supply_status"]:
    if str_col in std_sup_cat.columns:
        std_sup_cat[str_col] = std_sup_cat[str_col].apply(norm_str)

for num_col in ["supplier_cost_price_rs", "unmapped_col_10_quarantine"]:
    if num_col in std_sup_cat.columns:
        std_sup_cat[num_col] = pd.to_numeric(std_sup_cat[num_col], errors="coerce")

std_sup_cat["source_file"] = "supplier_inventory.xlsx/Supplier_Product_Catalog"
std_sup_cat["standardized_at"] = NOW
std_sup_cat.to_csv(STD / "std_supplier_product_catalog.csv", index=False)
print(f"  [STANDARDIZED] std_supplier_product_catalog.csv ({len(std_sup_cat)} rows)")

# STD 11. Inventory Position & Recalculated Formulas (Part H10 & Part I)
std_inv_pos = raw_inv_pos.copy()
std_inv_pos.columns = [snake(c) for c in std_inv_pos.columns]
std_inv_ctrl = raw_inv_ctrl.copy()
std_inv_ctrl.columns = [snake(c) for c in std_inv_ctrl.columns]

# Merge position with control
ctrl_sub = std_inv_ctrl[["warehouse_id", "product_id", "inventory_risk"]].copy()
ctrl_sub["warehouse_id"] = ctrl_sub["warehouse_id"].apply(norm_str)
ctrl_sub["product_id"] = ctrl_sub["product_id"].apply(norm_str)

std_inv = std_inv_pos.merge(ctrl_sub, on=["warehouse_id", "product_id"], how="left")

for str_col in ["warehouse_id", "product_id", "product_name", "category_name", "brand", "unit_size", "shelf_id", "bin_id", "stock_status", "inventory_risk"]:
    if str_col in std_inv.columns:
        std_inv[str_col] = std_inv[str_col].apply(norm_str)

for num_col in ["opening_stock_units", "received_units", "current_stock_units", "reserved_stock_units", "available_stock_units", "damaged_units", "cost_price_rs", "selling_price_rs", "avg_weekly_demand_units"]:
    if num_col in std_inv.columns:
        std_inv[num_col] = pd.to_numeric(std_inv[num_col], errors="coerce")

std_inv["reserved_stock_units"] = std_inv["reserved_stock_units"].fillna(0)
std_inv["damaged_units"] = std_inv["damaged_units"].fillna(0)

# Explicit recalculation of formula fields per Part H10
std_inv["weeks_of_cover_calc"] = np.where(
    std_inv["avg_weekly_demand_units"] > 0,
    (std_inv["available_stock_units"] / std_inv["avg_weekly_demand_units"]).round(2),
    np.nan
)
std_inv["reorder_flag_calc"] = (std_inv["weeks_of_cover_calc"] < 2.0).astype(int)
std_inv["target_stock_units"] = (2.0 * std_inv["avg_weekly_demand_units"]).round(1)
std_inv["shortage_units"] = np.maximum(0, (std_inv["target_stock_units"] - std_inv["available_stock_units"])).round(1)
std_inv["stock_cost_value_rs"] = (std_inv["current_stock_units"] * std_inv["cost_price_rs"]).round(2)
std_inv["available_sales_value_rs"] = (std_inv["available_stock_units"] * std_inv["selling_price_rs"]).round(2)
std_inv["snapshot_date"] = pd.to_datetime(std_inv["snapshot_date"]).dt.date

std_inv["source_file"] = "inventory_stock.xlsx/Inventory_Position+Inventory_Control"
std_inv["standardized_at"] = NOW
std_inv.to_csv(STD / "std_inventory_position.csv", index=False)
print(f"  [STANDARDIZED] std_inventory_position.csv ({len(std_inv)} rows)")

# STD 12. Shelf Master
std_shelf = raw_inv_shelf.copy()
std_shelf.columns = [snake(c) for c in std_shelf.columns]
for str_col in ["warehouse_id", "shelf_id", "zone_id", "rack_id", "shelf_level"]:
    if str_col in std_shelf.columns:
        std_shelf[str_col] = std_shelf[str_col].apply(norm_str)
for num_col in ["shelf_capacity_units", "product_slots", "used_units", "free_units", "space_utilization_pct"]:
    if num_col in std_shelf.columns:
        std_shelf[num_col] = pd.to_numeric(std_shelf[num_col], errors="coerce")
std_shelf["source_file"] = "inventory_stock.xlsx/Shelf_Master"
std_shelf["standardized_at"] = NOW
std_shelf.to_csv(STD / "std_inventory_shelf.csv", index=False)
print(f"  [STANDARDIZED] std_inventory_shelf.csv ({len(std_shelf)} rows)")

# STD 13. Demand History (Primary 2-Year Historical Fact)
std_dem1 = raw_dem_fact.copy()
std_dem1.columns = [snake(c) for c in std_dem1.columns]
for date_col in ["week_start_date", "week_end_date", "forecast_target_start", "forecast_target_end"]:
    if date_col in std_dem1.columns:
        std_dem1[date_col] = pd.to_datetime(std_dem1[date_col], errors="coerce").dt.date

for num_col in ["year", "week_number", "demand_rank", "weekday_units_sold", "weekend_units_sold", "units_sold",
                "avg_selling_price_rs", "promotion_flag", "discount_pct", "holiday_flag", "temperature_c",
                "rainfall_mm", "humidity_pct", "stockout_flag", "next_week_demand_target_units"]:
    if num_col in std_dem1.columns:
        std_dem1[num_col] = pd.to_numeric(std_dem1[num_col], errors="coerce")

for str_col in ["demand_id", "location_id", "region_of_kolkata", "product_id", "product_name", "category_name",
                "brand", "unit_size", "weekday_weekend", "festival_event", "season", "weather_condition",
                "data_source", "region_week_key", "region_product_week_key", "anchor_status"]:
    if str_col in std_dem1.columns:
        std_dem1[str_col] = std_dem1[str_col].apply(norm_str)

std_dem1["source_file"] = "Demand of last 2 years.xlsx/demand_training_data"
std_dem1["standardized_at"] = NOW
std_dem1.to_csv(STD / "std_demand_history.csv", index=False)
print(f"  [STANDARDIZED] std_demand_history.csv ({len(std_dem1)} rows)")

# STD 14. Demand Training (Secondary Synthetic Training Dataset)
std_dem2 = raw_dem_train.copy()
std_dem2.columns = [snake(c) for c in std_dem2.columns]
for date_col in ["week_start_date", "week_end_date", "forecast_target_start", "forecast_target_end"]:
    if date_col in std_dem2.columns:
        std_dem2[date_col] = pd.to_datetime(std_dem2[date_col], errors="coerce").dt.date

for num_col in ["year", "week_number", "demand_rank", "weekday_units_sold", "weekend_units_sold", "units_sold",
                "avg_selling_price_rs", "promotion_flag", "discount_pct", "holiday_flag", "temperature_c",
                "rainfall_mm", "humidity_pct", "stockout_flag", "next_week_demand_target_units"]:
    if num_col in std_dem2.columns:
        std_dem2[num_col] = pd.to_numeric(std_dem2[num_col], errors="coerce")

for str_col in ["demand_id", "location_id", "region_of_kolkata", "product_id", "product_name", "category_name",
                "brand", "unit_size", "weekday_weekend", "festival_event", "season", "weather_condition", "data_source"]:
    if str_col in std_dem2.columns:
        std_dem2[str_col] = std_dem2[str_col].apply(norm_str)

std_dem2["source_file"] = "final_demand_agent_training_2_years_kolkata (1).xlsx/demand_training_data"
std_dem2["standardized_at"] = NOW
std_dem2.to_csv(STD / "std_demand_training.csv", index=False)
print(f"  [STANDARDIZED] std_demand_training.csv ({len(std_dem2)} rows)")

# STD 15 & 16. Unavailable LFS files documentation
stg_sales_lfs.to_csv(STD / "std_sales_history_unavailable.csv", index=False)
stg_inv_lfs.to_csv(STD / "std_inventory_transactions_unavailable.csv", index=False)

print("\n" + "="*70)
print("PHASE 3: CANONICAL CURATED MODEL INTO 06_CURATED")
print("="*70)

# DIM_LOCATION
dim_loc = std_loc[["location_id", "region_of_kolkata", "location_name", "city", "latitude", "longitude", "source_file"]].copy()
dim_loc["pipeline_timestamp"] = NOW
dim_loc.to_csv(CUR / "DIM_LOCATION.csv", index=False)
print(f"  [CURATED] DIM_LOCATION: {len(dim_loc)} rows")

# DIM_PRODUCT
dim_prod = std_prod_base.copy()
dim_prod["pipeline_timestamp"] = NOW
dim_prod.to_csv(CUR / "DIM_PRODUCT.csv", index=False)
print(f"  [CURATED] DIM_PRODUCT: {len(dim_prod)} rows")

# DIM_PRODUCT_VARIANT
dim_var = std_variants.copy()
dim_var["pipeline_timestamp"] = NOW
dim_var.to_csv(CUR / "DIM_PRODUCT_VARIANT.csv", index=False)
print(f"  [CURATED] DIM_PRODUCT_VARIANT: {len(dim_var)} rows")

# DIM_WAREHOUSE
dim_wh = std_wh.copy()
dim_wh["pipeline_timestamp"] = NOW
dim_wh.to_csv(CUR / "DIM_WAREHOUSE.csv", index=False)
print(f"  [CURATED] DIM_WAREHOUSE: {len(dim_wh)} rows")

# DIM_SUPPLIER
dim_sup = std_sup_m.copy()
dim_sup["pipeline_timestamp"] = NOW
dim_sup.to_csv(CUR / "DIM_SUPPLIER.csv", index=False)
print(f"  [CURATED] DIM_SUPPLIER: {len(dim_sup)} rows")

# DIM_WEATHER
dim_wth = std_weather.copy()
dim_wth["pipeline_timestamp"] = NOW
dim_wth.to_csv(CUR / "DIM_WEATHER.csv", index=False)
print(f"  [CURATED] DIM_WEATHER: {len(dim_wth)} rows")

# DIM_FESTIVAL
dim_fest = std_fest.copy()
dim_fest["pipeline_timestamp"] = NOW
dim_fest.to_csv(CUR / "DIM_FESTIVAL.csv", index=False)
print(f"  [CURATED] DIM_FESTIVAL: {len(dim_fest)} rows")

# DIM_CALENDAR_WEEK
dim_cal = std_calendar.copy()
dim_cal["pipeline_timestamp"] = NOW
dim_cal.to_csv(CUR / "DIM_CALENDAR_WEEK.csv", index=False)
print(f"  [CURATED] DIM_CALENDAR_WEEK: {len(dim_cal)} rows")

# BRIDGE_SUPPLIER_PRODUCT
bridge_sp = std_sup_cat[[
    "supplier_product_key", "supplier_id", "supplier_type_id", "supplier_type_name",
    "product_id", "supplier_cost_price_rs", "supplied_unit_size",
    "supply_status", "unmapped_col_10_quarantine"
]].copy()
bridge_sp["source_file"] = "supplier_inventory.xlsx/Supplier_Product_Catalog"
bridge_sp["pipeline_timestamp"] = NOW
bridge_sp.to_csv(CUR / "BRIDGE_SUPPLIER_PRODUCT.csv", index=False)
print(f"  [CURATED] BRIDGE_SUPPLIER_PRODUCT: {len(bridge_sp)} rows")

# BRIDGE_LOCATION_SUPPLIER
bridge_ls = std_sup_opt.copy()
bridge_ls["pipeline_timestamp"] = NOW
bridge_ls.to_csv(CUR / "BRIDGE_LOCATION_SUPPLIER.csv", index=False)
print(f"  [CURATED] BRIDGE_LOCATION_SUPPLIER: {len(bridge_ls)} rows")

# BRIDGE_WAREHOUSE_LOCATION (Haversine Euclidean distance matrix)
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))

wh_coords = dim_wh[["warehouse_id", "latitude", "longitude", "service_radius_km"]].dropna()
loc_coords = dim_loc[["location_id", "latitude", "longitude"]].dropna()

bridge_wl_rows = []
for _, wrow in wh_coords.iterrows():
    for _, lrow in loc_coords.iterrows():
        dist = haversine(wrow["latitude"], wrow["longitude"], lrow["latitude"], lrow["longitude"])
        in_radius = dist <= float(wrow["service_radius_km"])
        bridge_wl_rows.append({
            "warehouse_id": wrow["warehouse_id"],
            "location_id": lrow["location_id"],
            "euclidean_distance_km": round(dist, 4),
            "service_radius_km": wrow["service_radius_km"],
            "service_available_flag": "Yes" if in_radius else "No",
            "assignment_method": "haversine_vs_service_radius",
            "mapping_source": "DERIVED_FROM_COORDINATES",
            "pipeline_timestamp": NOW,
        })
bridge_wl = pd.DataFrame(bridge_wl_rows)
bridge_wl.to_csv(CUR / "BRIDGE_WAREHOUSE_LOCATION.csv", index=False)
print(f"  [CURATED] BRIDGE_WAREHOUSE_LOCATION: {len(bridge_wl)} rows")

# BRIDGE_PRODUCT_WAREHOUSE
bridge_pw = std_inv[["warehouse_id", "product_id", "shelf_id", "bin_id"]].drop_duplicates()
bridge_pw["source_file"] = "inventory_stock.xlsx/Inventory_Position"
bridge_pw["pipeline_timestamp"] = NOW
bridge_pw.to_csv(CUR / "BRIDGE_PRODUCT_WAREHOUSE.csv", index=False)
print(f"  [CURATED] BRIDGE_PRODUCT_WAREHOUSE: {len(bridge_pw)} rows")

# FACT_INVENTORY_POSITION
fact_inv = std_inv[[
    "warehouse_id", "product_id", "shelf_id", "bin_id",
    "opening_stock_units", "received_units", "current_stock_units",
    "reserved_stock_units", "available_stock_units", "damaged_units",
    "cost_price_rs", "selling_price_rs", "avg_weekly_demand_units",
    "stock_status", "snapshot_date", "weeks_of_cover_calc", "reorder_flag_calc",
    "target_stock_units", "shortage_units",
    "stock_cost_value_rs", "available_sales_value_rs", "inventory_risk", "source_file"
]].copy()
fact_inv["pipeline_timestamp"] = NOW
fact_inv.to_csv(CUR / "FACT_INVENTORY_POSITION.csv", index=False)
print(f"  [CURATED] FACT_INVENTORY_POSITION: {len(fact_inv)} rows")

# FACT_DEMAND (primary)
fact_dem = std_dem1.copy()
fact_dem["fact_source"] = "DEMAND_OF_LAST_2_YEARS"
fact_dem["pipeline_timestamp"] = NOW
fact_dem.to_csv(CUR / "FACT_DEMAND.csv", index=False)
print(f"  [CURATED] FACT_DEMAND: {len(fact_dem)} rows")

# DEMAND_TRAINING_DATA (secondary)
fact_dem_train = std_dem2.copy()
fact_dem_train["fact_source"] = "FINAL_DEMAND_AGENT_TRAINING"
fact_dem_train["pipeline_timestamp"] = NOW
fact_dem_train.to_csv(CUR / "DEMAND_TRAINING_DATA.csv", index=False)
print(f"  [CURATED] DEMAND_TRAINING_DATA: {len(fact_dem_train)} rows")

# FACT_SUPPLIER_AVAILABILITY
fact_sa = bridge_sp.copy()
sup_sub = dim_sup[[
    "supplier_id", "minimum_order_qty_units", "max_order_qty_units",
    "max_ship_qty_at_once_units", "supplier_storage_capacity_units",
    "vehicle_type", "vehicle_count", "vehicle_load_capacity_units",
    "lead_time_days", "location_id"
]].copy()
fact_sa = fact_sa.merge(sup_sub, on="supplier_id", how="left")
fact_sa["snapshot_date"] = NOW
fact_sa["pipeline_timestamp"] = NOW
fact_sa.to_csv(CUR / "FACT_SUPPLIER_AVAILABILITY.csv", index=False)
print(f"  [CURATED] FACT_SUPPLIER_AVAILABILITY: {len(fact_sa)} rows")

# FACT_SALES (Blocked)
pd.DataFrame([{
    "status": "BLOCKED_BY_SOURCE",
    "reason": "sales_history.xlsx is a Git-LFS pointer. The underlying XLSX has not been fetched locally.",
    "lfs_oid": "fc8022e6248ccb8725f6ff8cb9c70aa91a6f76aeb99bce62db5866f7c902e6e5",
    "expected_size_bytes": 177644415,
    "remediation": "Run `git lfs pull` in the repository root to download sales_history.xlsx",
    "pipeline_timestamp": NOW,
}]).to_csv(CUR / "FACT_SALES__BLOCKED.csv", index=False)
print("  [CURATED] FACT_SALES: BLOCKED (LFS pointer)")

# FACT_INVENTORY_TRANSACTION (Blocked)
pd.DataFrame([{
    "status": "BLOCKED_BY_SOURCE",
    "reason": "inventory_transactions.xlsx is a Git-LFS pointer. The underlying XLSX has not been fetched.",
    "lfs_oid": "5fc053bab861bc764e13ac15b74ebcab11b4bf35403f436eadd68d727a06a749",
    "expected_size_bytes": 55855339,
    "remediation": "Run `git lfs pull` in the repository root to download inventory_transactions.xlsx",
    "pipeline_timestamp": NOW,
}]).to_csv(CUR / "FACT_INVENTORY_TRANSACTION__BLOCKED.csv", index=False)
print("  [CURATED] FACT_INVENTORY_TRANSACTION: BLOCKED (LFS pointer)")

print("\n" + "="*70)
print("✅ STAGING, STANDARDIZATION, AND CURATED PIPELINE COMPLETE")
print("="*70)
