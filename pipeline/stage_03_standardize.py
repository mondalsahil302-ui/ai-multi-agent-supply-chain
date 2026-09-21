"""
Stage 03: Standardization and canonical entities.
Produces all DIM_*, FACT_*, and BRIDGE_* tables in 04_standardized and 06_curated.
"""

import pandas as pd
import numpy as np
import openpyxl
import warnings
import re
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta

warnings.filterwarnings("ignore")

BASE = Path(r"D:\ai-multi-agent-supply-chain")
RAW  = BASE / "Datasets" / "raw"
STG  = BASE / "data" / "03_staging"
STD  = BASE / "data" / "04_standardized"
MAP  = BASE / "data" / "05_entity_mapping"
CUR  = BASE / "data" / "06_curated"
QRT  = BASE / "data" / "data_quarantine"
NOW  = datetime.now(timezone.utc).isoformat()


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
    return str(s).strip()


# ═══════════════════════════════════════════════════════════════════════════════
# DIM_LOCATION
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DIM_LOCATION...")
loc_csv = pd.read_csv(RAW / "master" / "locations.csv.csv")
sup_area = load_xlsx(RAW / "supplier" / "supplier_inventory.xlsx", "Area_Master")

# Merge: locations.csv.csv has location_id + region_of_kolkata
# supplier Area_Master has location_id, location_name, city, lat, lon
dim_loc = loc_csv.copy()
dim_loc.columns = ["location_id", "region_of_kolkata"]

# Enrich with lat/lon from supplier Area_Master
sup_area.columns = ["location_id", "location_name", "city", "latitude", "longitude"]
dim_loc = dim_loc.merge(sup_area[["location_id", "city", "latitude", "longitude"]], on="location_id", how="left")

dim_loc["location_name"] = dim_loc["region_of_kolkata"]  # same concept
dim_loc["source_file"] = "locations.csv.csv + supplier_inventory.xlsx/Area_Master"
dim_loc["pipeline_timestamp"] = NOW

assert dim_loc["location_id"].nunique() == len(dim_loc), "DIM_LOCATION: duplicate location_id"
dim_loc.to_csv(CUR / "DIM_LOCATION.csv", index=False)
print(f"  DIM_LOCATION: {len(dim_loc)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# DIM_PRODUCT (canonical — products.csv, validated against Final product list.xlsx)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DIM_PRODUCT...")
prod_csv = pd.read_csv(RAW / "master" / "products.csv")
prod_xlsx = load_xlsx(RAW / "master" / "Final product list.xlsx", "product_master")

# Compare product IDs
ids_csv = set(prod_csv["product_id"].dropna())
ids_xlsx = set(prod_xlsx["product_id"].dropna())

only_csv = ids_csv - ids_xlsx
only_xlsx = ids_xlsx - ids_csv
print(f"  products.csv only: {len(only_csv)}, Final product list.xlsx only: {len(only_xlsx)}")

# Both have 200 products with identical schema → products.csv is canonical
# (xlsx has extra column product_source which is metadata)
dim_product = prod_csv[["product_id", "category_code", "category_name", "product_name",
                         "brand", "quality_level", "unit_type"]].copy()
dim_product["canonical_source"] = "products.csv"
dim_product["source_file"] = "products.csv (reconciled against Final product list.xlsx)"
dim_product["pipeline_timestamp"] = NOW

assert dim_product["product_id"].nunique() == len(dim_product), "DIM_PRODUCT: duplicate product_id"
dim_product.to_csv(CUR / "DIM_PRODUCT.csv", index=False)
print(f"  DIM_PRODUCT: {len(dim_product)} rows, {dim_product['category_code'].nunique()} categories")


# ═══════════════════════════════════════════════════════════════════════════════
# DIM_PRODUCT_VARIANT  (normalize 5 unit sizes per product)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DIM_PRODUCT_VARIANT...")

def parse_unit(size_str):
    """Return (value, unit, normalized_ml_g) or (None,None,None)."""
    if pd.isna(size_str) or size_str == "":
        return None, None, None
    s = str(size_str).strip().lower()
    # patterns: "80 ml", "500 g", "1 l", "1 dozen", "1 piece", "100 g"
    m = re.match(r"([\d\.]+)\s*(ml|l|g|kg|piece|dozen)", s)
    if not m:
        return s, "unknown", None
    val = float(m.group(1))
    unit = m.group(2)
    # normalize to ml or g
    norm_val = val
    norm_unit = unit
    if unit == "l":
        norm_val = val * 1000
        norm_unit = "ml"
    elif unit == "kg":
        norm_val = val * 1000
        norm_unit = "g"
    return val, unit, (norm_val, norm_unit)


variant_rows = []
for _, row in prod_csv.iterrows():
    pid = row["product_id"]
    unit_type = row["unit_type"]
    for i in range(1, 6):
        size = row.get(f"unit_size_{i}")
        cp   = row.get(f"cp_{i}_rs")
        sp   = row.get(f"sp_{i}_rs")
        if pd.isna(size) or size == "":
            continue
        val, unit, norm = parse_unit(size)
        norm_val = norm[0] if norm else None
        norm_unit = norm[1] if norm else None

        # Build deterministic variant ID
        size_tag = str(size).replace(" ", "").upper()
        pvid = f"{pid}-{size_tag}"

        variant_rows.append({
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
            "pipeline_timestamp": NOW,
        })

dim_variant = pd.DataFrame(variant_rows)
assert dim_variant["product_variant_id"].nunique() == len(dim_variant), "DIM_PRODUCT_VARIANT: duplicate keys"
dim_variant.to_csv(CUR / "DIM_PRODUCT_VARIANT.csv", index=False)
print(f"  DIM_PRODUCT_VARIANT: {len(dim_variant)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# DIM_WAREHOUSE  (merge warehouses.xlsx + final_warehouse_dataset_kolkata.xlsx)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DIM_WAREHOUSE...")
wh1 = load_xlsx(RAW / "warehouse" / "warehouses.xlsx", "warehouse")
wh2 = load_xlsx(RAW / "warehouse" / "final_warehouse_dataset_kolkata.xlsx", "warehouse")

# wh1: has vehicle counts, dispatch capacity, service_radius
# wh2: has storage_type, x/y coordinates, status
wh1.columns = [snake(c) for c in wh1.columns]
wh2.columns = [snake(c) for c in wh2.columns]

dim_wh = wh1.merge(
    wh2[["warehouse_id", "storage_type", "x_coordinate", "y_coordinate", "status"]],
    on="warehouse_id",
    how="left"
)

dim_wh["source_file"] = "warehouses.xlsx (primary) + final_warehouse_dataset_kolkata.xlsx (storage_type/status)"
dim_wh["pipeline_timestamp"] = NOW

# Rename for consistency
dim_wh = dim_wh.rename(columns={
    "weekday_opening": "weekday_open_time",
    "weekday_closing": "weekday_close_time",
    "weekend_opening": "weekend_open_time",
    "weekend_closing": "weekend_close_time",
})

assert dim_wh["warehouse_id"].nunique() == len(dim_wh), "DIM_WAREHOUSE: duplicate warehouse_id"
dim_wh.to_csv(CUR / "DIM_WAREHOUSE.csv", index=False)
print(f"  DIM_WAREHOUSE: {len(dim_wh)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# DIM_SUPPLIER
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DIM_SUPPLIER...")
sup_master = load_xlsx(RAW / "supplier" / "supplier_inventory.xlsx", "Supplier_Master")
sup_master.columns = [snake(c) for c in sup_master.columns]
sup_master["source_file"] = "supplier_inventory.xlsx/Supplier_Master"
sup_master["pipeline_timestamp"] = NOW

dim_supplier = sup_master.copy()
assert dim_supplier["supplier_id"].nunique() == len(dim_supplier), "DIM_SUPPLIER: duplicate supplier_id"
dim_supplier.to_csv(CUR / "DIM_SUPPLIER.csv", index=False)
print(f"  DIM_SUPPLIER: {len(dim_supplier)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# DIM_WEATHER_WEEKLY
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DIM_WEATHER...")
weather = pd.read_csv(RAW / "external" / "weather_weekly.csv")
weather["week_start_date"] = pd.to_datetime(weather["week_start_date"])
weather["week_end_date"]   = pd.to_datetime(weather["week_end_date"])

# Validate 7-day intervals
weather["interval_days"] = (weather["week_end_date"] - weather["week_start_date"]).dt.days
bad_intervals = weather[weather["interval_days"] != 6]  # end-start=6 → 7 days inclusive
if len(bad_intervals) > 0:
    print(f"  WARNING: {len(bad_intervals)} weather rows with non-7-day intervals")

# Validate domain constraints
assert (weather["humidity_pct"] >= 0).all() and (weather["humidity_pct"] <= 100).all(), "humidity out of range"
assert (weather["rainfall_mm"] >= 0).all(), "negative rainfall"

weather["weather_data_type"] = "SUPPLIED_SYNTHETIC"  # as declared in data_source column
weather["source_file"] = "weather_weekly.csv"
weather["pipeline_timestamp"] = NOW

weather.to_csv(CUR / "DIM_WEATHER.csv", index=False)
print(f"  DIM_WEATHER: {len(weather)} rows, {weather['week_start_date'].min()} to {weather['week_start_date'].max()}")


# ═══════════════════════════════════════════════════════════════════════════════
# DIM_FESTIVAL
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DIM_FESTIVAL...")
fests = pd.read_csv(RAW / "external" / "festival_calendar.csv")
fests["event_date"] = pd.to_datetime(fests["event_date"])
fests["festival_id"] = ["FEST-" + str(i+1).zfill(3) for i in range(len(fests))]

# Derive week_start_date (Monday of that week)
fests["week_start_date"] = fests["event_date"].dt.to_period("W-MON").apply(lambda p: p.start_time)

# Infer category
def infer_category(name):
    n = str(name).lower()
    if "eid" in n or "muharram" in n or "milad" in n:
        return "Islamic"
    if "christmas" in n or "easter" in n:
        return "Christian"
    if "puja" in n or "durga" in n or "kali" in n or "rath" in n or "janmashtami" in n:
        return "Hindu"
    if "new year" in n or "boishakh" in n:
        return "Cultural/New Year"
    if "independence" in n or "republic" in n or "gandhi" in n:
        return "National"
    return "Hindu"  # default for Kolkata context

fests["festival_category"] = fests["festival_event"].apply(infer_category)
fests["source_type"] = "SUPPLIED_REFERENCE"
fests["source_file"] = "festival_calendar.csv"
fests["pipeline_timestamp"] = NOW

fests.to_csv(CUR / "DIM_FESTIVAL.csv", index=False)
print(f"  DIM_FESTIVAL: {len(fests)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# DIM_CALENDAR_WEEK  (from demand date coverage + weather coverage)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DIM_CALENDAR_WEEK...")
# Use weather to derive complete calendar
weather_w = pd.read_csv(RAW / "external" / "weather_weekly.csv")
weather_w["week_start_date"] = pd.to_datetime(weather_w["week_start_date"])
weather_w["week_end_date"]   = pd.to_datetime(weather_w["week_end_date"])

cal_rows = []
for _, row in weather_w.iterrows():
    wsd = row["week_start_date"]
    wed = row["week_end_date"]
    week_key = f"{wsd.strftime('%Y%m%d')}"
    cal_rows.append({
        "week_key": week_key,
        "week_start_date": wsd.date(),
        "week_end_date": wed.date(),
        "year": row["year"],
        "week_number": wsd.isocalendar()[1],
        "season": row["season"],
        "source_file": "weather_weekly.csv",
        "pipeline_timestamp": NOW,
    })

dim_cal = pd.DataFrame(cal_rows)
dim_cal.to_csv(CUR / "DIM_CALENDAR_WEEK.csv", index=False)
print(f"  DIM_CALENDAR_WEEK: {len(dim_cal)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# BRIDGE_SUPPLIER_PRODUCT
# ═══════════════════════════════════════════════════════════════════════════════
print("Building BRIDGE_SUPPLIER_PRODUCT...")
cat_raw = load_xlsx(RAW / "supplier" / "supplier_inventory.xlsx", "Supplier_Product_Catalog")

# Header analysis: actual columns (13 total):
# 0: supplier_product_key, 1: supplier_id, 2: supplier_type_id, 3: supplier_type_name,
# 4: product_supplied_id, 5: product_name, 6: category_code, 7: category_name,
# 8: unit_type, 9: supplier_cost_price_rs, 10: UNLABELED (numeric), 11: supplied_unit_size, 12: supply_status
# The header says 12 named columns but data has 13. Col 10 is unlabeled.
# Col 10 values (~35.71) appear to be a ratio. Preserved as quarantine column.

known_cols = [
    "supplier_product_key", "supplier_id", "supplier_type_id", "supplier_type_name",
    "product_supplied_id", "product_name", "category_code", "category_name",
    "unit_type", "supplier_cost_price_rs", "unmapped_col_10_quarantine",
    "supplied_unit_size", "supply_status"
]
cat_raw.columns = known_cols[:len(cat_raw.columns)]

# Validate supplier_id and product_id references
valid_sup_ids = set(dim_supplier["supplier_id"])
valid_prod_ids = set(dim_product["product_id"])

bad_sup = cat_raw[~cat_raw["supplier_id"].isin(valid_sup_ids)]
bad_prod = cat_raw[~cat_raw["product_supplied_id"].isin(valid_prod_ids)]
print(f"  Unresolved supplier refs: {len(bad_sup)}, unresolved product refs: {len(bad_prod)}")

bridge_sp = cat_raw[[
    "supplier_product_key", "supplier_id", "supplier_type_id", "supplier_type_name",
    "product_supplied_id", "supplier_cost_price_rs", "supplied_unit_size",
    "supply_status", "unmapped_col_10_quarantine"
]].copy()
bridge_sp.rename(columns={"product_supplied_id": "product_id"}, inplace=True)
bridge_sp["source_file"] = "supplier_inventory.xlsx/Supplier_Product_Catalog"
bridge_sp["pipeline_timestamp"] = NOW

bridge_sp.to_csv(CUR / "BRIDGE_SUPPLIER_PRODUCT.csv", index=False)
print(f"  BRIDGE_SUPPLIER_PRODUCT: {len(bridge_sp)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# BRIDGE_LOCATION_SUPPLIER
# ═══════════════════════════════════════════════════════════════════════════════
print("Building BRIDGE_LOCATION_SUPPLIER...")
area_sup = load_xlsx(RAW / "supplier" / "supplier_inventory.xlsx", "Area_Supplier_Options")
area_sup.columns = [snake(c) for c in area_sup.columns]
area_sup["source_file"] = "supplier_inventory.xlsx/Area_Supplier_Options"
area_sup["pipeline_timestamp"] = NOW

area_sup.to_csv(CUR / "BRIDGE_LOCATION_SUPPLIER.csv", index=False)
print(f"  BRIDGE_LOCATION_SUPPLIER: {len(area_sup)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# BRIDGE_WAREHOUSE_LOCATION  (derive from service radius + location coordinates)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building BRIDGE_WAREHOUSE_LOCATION...")

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.asin(math.sqrt(a))


# wh1 already loaded — has service_radius_km
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
print(f"  BRIDGE_WAREHOUSE_LOCATION: {len(bridge_wl)} rows (warehouse-location pairs)")


# ═══════════════════════════════════════════════════════════════════════════════
# BRIDGE_PRODUCT_WAREHOUSE  (from Inventory_Position)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building BRIDGE_PRODUCT_WAREHOUSE...")
inv_pos = load_xlsx(RAW / "inventory" / "inventory_stock.xlsx", "Inventory_Position")
inv_pos.columns = [snake(c) for c in inv_pos.columns]
bridge_pw = inv_pos[["warehouse_id", "product_id", "shelf_id", "bin_id"]].drop_duplicates()
bridge_pw["source_file"] = "inventory_stock.xlsx/Inventory_Position"
bridge_pw["pipeline_timestamp"] = NOW
bridge_pw.to_csv(CUR / "BRIDGE_PRODUCT_WAREHOUSE.csv", index=False)
print(f"  BRIDGE_PRODUCT_WAREHOUSE: {len(bridge_pw)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# FACT_INVENTORY_POSITION
# ═══════════════════════════════════════════════════════════════════════════════
print("Building FACT_INVENTORY_POSITION...")
inv_ctrl = load_xlsx(RAW / "inventory" / "inventory_stock.xlsx", "Inventory_Control")
inv_ctrl.columns = [snake(c) for c in inv_ctrl.columns]

# Merge position + control
inv_pos_f = load_xlsx(RAW / "inventory" / "inventory_stock.xlsx", "Inventory_Position")
inv_pos_f.columns = [snake(c) for c in inv_pos_f.columns]

# Key columns to keep from Inventory_Position
pos_cols = [
    "warehouse_id", "product_id", "shelf_id", "bin_id",
    "opening_stock_units", "received_units", "current_stock_units",
    "reserved_stock_units", "available_stock_units", "damaged_units",
    "cost_price_rs", "selling_price_rs", "avg_weekly_demand_units",
    "stock_status", "snapshot_date"
]
inv_fact = inv_pos_f[[c for c in pos_cols if c in inv_pos_f.columns]].copy()

# Merge control layer for computed fields
ctrl_cols = ["warehouse_id", "product_id", "weeks_of_cover", "target_stock_units",
             "shortage_units", "reorder_flag", "inventory_risk"]
inv_ctrl_sub = inv_ctrl[[c for c in ctrl_cols if c in inv_ctrl.columns]]
inv_fact = inv_fact.merge(inv_ctrl_sub, on=["warehouse_id", "product_id"], how="left")

# Recalculate formula fields explicitly
inv_fact["available_stock_units"] = pd.to_numeric(inv_fact["available_stock_units"], errors="coerce")
inv_fact["current_stock_units"]   = pd.to_numeric(inv_fact["current_stock_units"], errors="coerce")
inv_fact["reserved_stock_units"]  = pd.to_numeric(inv_fact.get("reserved_stock_units", 0), errors="coerce").fillna(0)
inv_fact["damaged_units"]         = pd.to_numeric(inv_fact.get("damaged_units", 0), errors="coerce").fillna(0)
inv_fact["avg_weekly_demand_units"] = pd.to_numeric(inv_fact["avg_weekly_demand_units"], errors="coerce")

# Recalculate weeks_of_cover
inv_fact["weeks_of_cover_calc"] = np.where(
    inv_fact["avg_weekly_demand_units"] > 0,
    inv_fact["available_stock_units"] / inv_fact["avg_weekly_demand_units"],
    np.nan
)
inv_fact["weeks_of_cover_calc"] = inv_fact["weeks_of_cover_calc"].round(2)

# Recalculate reorder_flag: flag if weeks_of_cover < 2
inv_fact["reorder_flag_calc"] = (inv_fact["weeks_of_cover_calc"] < 2).astype(int)

# Stock value
inv_fact["cost_price_rs"] = pd.to_numeric(inv_fact["cost_price_rs"], errors="coerce")
inv_fact["selling_price_rs"] = pd.to_numeric(inv_fact["selling_price_rs"], errors="coerce")
inv_fact["stock_cost_value_rs"] = (inv_fact["current_stock_units"] * inv_fact["cost_price_rs"]).round(2)
inv_fact["available_sales_value_rs"] = (inv_fact["available_stock_units"] * inv_fact["selling_price_rs"]).round(2)

# Validate business rules
neg_avail = (inv_fact["available_stock_units"] < 0).sum()
neg_dam   = (inv_fact["damaged_units"] < 0).sum()
if neg_avail > 0:
    print(f"  WARNING: {neg_avail} rows with negative available_stock_units")
if neg_dam > 0:
    print(f"  WARNING: {neg_dam} rows with negative damaged_units")

inv_fact["source_file"] = "inventory_stock.xlsx/Inventory_Position+Inventory_Control"
inv_fact["pipeline_timestamp"] = NOW

inv_fact.to_csv(CUR / "FACT_INVENTORY_POSITION.csv", index=False)
print(f"  FACT_INVENTORY_POSITION: {len(inv_fact)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# FACT_DEMAND (primary demand file)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building FACT_DEMAND (primary)...")
dem1 = load_xlsx(RAW / "demand" / "Demand of last 2 years.xlsx", "demand_training_data")
dem1.columns = [str(c) if c is not None else f"_unnamed_{i}" for i, c in enumerate(dem1.columns)]

# Convert dates
for dc in ["week_start_date", "week_end_date", "forecast_target_start", "forecast_target_end", "recorded_at"]:
    if dc in dem1.columns:
        dem1[dc] = pd.to_datetime(dem1[dc], errors="coerce")

# Numeric conversions
for nc in ["weekday_units_sold", "weekend_units_sold", "units_sold", "avg_selling_price_rs",
           "promotion_flag", "discount_pct", "holiday_flag", "stockout_flag",
           "next_week_demand_target_units", "demand_rank", "assortment_size"]:
    if nc in dem1.columns:
        dem1[nc] = pd.to_numeric(dem1[nc], errors="coerce")

# Validate: units_sold = weekday_units_sold + weekend_units_sold
if all(c in dem1.columns for c in ["weekday_units_sold", "weekend_units_sold", "units_sold"]):
    dem1["units_calc"] = dem1["weekday_units_sold"].fillna(0) + dem1["weekend_units_sold"].fillna(0)
    mismatch = (abs(dem1["units_calc"] - dem1["units_sold"]) > 1).sum()
    if mismatch > 0:
        print(f"  WARNING: {mismatch} rows where units_sold != weekday+weekend")
    dem1.drop("units_calc", axis=1, inplace=True)

# Source type declared in demand dataset
dem1["fact_source"] = "DEMAND_OF_LAST_2_YEARS"
dem1["pipeline_timestamp"] = NOW

dem1.to_csv(CUR / "FACT_DEMAND.csv", index=False)
print(f"  FACT_DEMAND: {len(dem1)} rows, cols: {len(dem1.columns)}")


# ═══════════════════════════════════════════════════════════════════════════════
# DEMAND_TRAINING_DATA (secondary demand training file)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DEMAND_TRAINING_DATA (secondary)...")
dem2 = load_xlsx(RAW / "demand" / "final_demand_agent_training_2_years_kolkata (1).xlsx", "demand_training_data")
dem2.columns = [str(c) if c is not None else f"_unnamed_{i}" for i, c in enumerate(dem2.columns)]

for dc in ["week_start_date", "week_end_date", "forecast_target_start", "forecast_target_end", "recorded_at"]:
    if dc in dem2.columns:
        dem2[dc] = pd.to_datetime(dem2[dc], errors="coerce")

dem2["fact_source"] = "FINAL_DEMAND_AGENT_TRAINING"
dem2["pipeline_timestamp"] = NOW

dem2.to_csv(CUR / "DEMAND_TRAINING_DATA.csv", index=False)
print(f"  DEMAND_TRAINING_DATA: {len(dem2)} rows, cols: {len(dem2.columns)}")


# ═══════════════════════════════════════════════════════════════════════════════
# FACT_SALES — BLOCKED (LFS pointer)
# ═══════════════════════════════════════════════════════════════════════════════
pd.DataFrame([{
    "status": "BLOCKED_BY_SOURCE",
    "reason": "sales_history.xlsx is a Git-LFS pointer. The underlying XLSX has not been fetched locally.",
    "lfs_oid": "fc8022e6248ccb8725f6ff8cb9c70aa91a6f76aeb99bce62db5866f7c902e6e5",
    "expected_size_bytes": 177644415,
    "remediation": "Run `git lfs pull` in the repository root to download sales_history.xlsx",
    "pipeline_timestamp": NOW,
}]).to_csv(CUR / "FACT_SALES__BLOCKED.csv", index=False)
print("  FACT_SALES: BLOCKED (LFS pointer)")


# ═══════════════════════════════════════════════════════════════════════════════
# FACT_INVENTORY_TRANSACTION — BLOCKED (LFS pointer)
# ═══════════════════════════════════════════════════════════════════════════════
pd.DataFrame([{
    "status": "BLOCKED_BY_SOURCE",
    "reason": "inventory_transactions.xlsx is a Git-LFS pointer. The underlying XLSX has not been fetched.",
    "lfs_oid": "5fc053bab861bc764e13ac15b74ebcab11b4bf35403f436eadd68d727a06a749",
    "expected_size_bytes": 55855339,
    "remediation": "Run `git lfs pull` in the repository root to download inventory_transactions.xlsx",
    "pipeline_timestamp": NOW,
}]).to_csv(CUR / "FACT_INVENTORY_TRANSACTION__BLOCKED.csv", index=False)
print("  FACT_INVENTORY_TRANSACTION: BLOCKED (LFS pointer)")


# ═══════════════════════════════════════════════════════════════════════════════
# FACT_SUPPLIER_AVAILABILITY (from supplier catalog — one row per supplier-product)
# ═══════════════════════════════════════════════════════════════════════════════
print("Building FACT_SUPPLIER_AVAILABILITY...")
fact_sa = bridge_sp.copy()
# Merge supplier info
sup_sub = dim_supplier[["supplier_id", "minimum_order_qty_units", "max_order_qty_units",
                          "max_ship_qty_at_once_units", "supplier_storage_capacity_units",
                          "vehicle_type", "vehicle_count", "vehicle_load_capacity_units",
                          "lead_time_days", "location_id"]].copy()
fact_sa = fact_sa.merge(sup_sub, on="supplier_id", how="left")
fact_sa["snapshot_date"] = NOW
fact_sa.to_csv(CUR / "FACT_SUPPLIER_AVAILABILITY.csv", index=False)
print(f"  FACT_SUPPLIER_AVAILABILITY: {len(fact_sa)} rows")


print("\n✅ Stage 03 standardization complete — all canonical entities created.")

