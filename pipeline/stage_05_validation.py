"""
Stage 05: Validation — multi-level validation framework.
Produces validation_summary.csv and validation_details.csv.
"""
import pandas as pd
import numpy as np
import warnings
from pathlib import Path
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

BASE = Path(r"D:\ai-multi-agent-supply-chain")
CUR  = BASE / "data" / "06_curated"
FEAT = BASE / "data" / "07_features"
VAL  = BASE / "data" / "08_validation"
QRT  = BASE / "data" / "data_quarantine"
NOW  = datetime.now(timezone.utc).isoformat()

details = []
CID = [0]

def vid():
    CID[0] += 1
    return f"VAL-{CID[0]:04d}"


def check(check_id, dataset, check_name, expected, actual, status, severity, failed_count, remediation=""):
    details.append({
        "check_id": check_id,
        "dataset": dataset,
        "check_name": check_name,
        "expected": expected,
        "actual": actual,
        "status": status,
        "severity": severity,
        "failed_record_count": failed_count,
        "remediation": remediation,
        "timestamp": NOW,
    })


def load(fname):
    return pd.read_csv(CUR / fname, low_memory=False)


# ═══════════════════════════════════════════════════════════════════════════════
# File-level checks
# ═══════════════════════════════════════════════════════════════════════════════
print("Running file-level checks...")
required_files = [
    "DIM_LOCATION.csv", "DIM_PRODUCT.csv", "DIM_PRODUCT_VARIANT.csv",
    "DIM_WAREHOUSE.csv", "DIM_SUPPLIER.csv", "DIM_CALENDAR_WEEK.csv",
    "DIM_FESTIVAL.csv", "DIM_WEATHER.csv",
    "FACT_DEMAND.csv", "FACT_INVENTORY_POSITION.csv",
    "FACT_SUPPLIER_AVAILABILITY.csv",
    "BRIDGE_SUPPLIER_PRODUCT.csv", "BRIDGE_LOCATION_SUPPLIER.csv",
    "BRIDGE_WAREHOUSE_LOCATION.csv", "BRIDGE_PRODUCT_WAREHOUSE.csv",
]
for f in required_files:
    exists = (CUR / f).exists()
    check(vid(), f, "FILE_EXISTS",
          "File exists", "Exists" if exists else "Missing",
          "PASS" if exists else "FAIL", "CRITICAL" if not exists else "INFO", 0 if exists else 1)

# LFS-blocked files
for f in ["FACT_SALES__BLOCKED.csv", "FACT_INVENTORY_TRANSACTION__BLOCKED.csv"]:
    check(vid(), f, "FILE_BLOCKED_LFS",
          "Available XLSX file", "Git-LFS pointer (data not fetched)",
          "BLOCKED_BY_SOURCE", "CRITICAL", -1,
          "Run `git lfs pull` to fetch underlying data")

print(f"  File checks: {len(details)} checks recorded")


# ═══════════════════════════════════════════════════════════════════════════════
# Primary key uniqueness
# ═══════════════════════════════════════════════════════════════════════════════
print("Running PK uniqueness checks...")
pk_checks = {
    "DIM_LOCATION.csv":       "location_id",
    "DIM_PRODUCT.csv":        "product_id",
    "DIM_PRODUCT_VARIANT.csv":"product_variant_id",
    "DIM_WAREHOUSE.csv":      "warehouse_id",
    "DIM_SUPPLIER.csv":       "supplier_id",
    "DIM_CALENDAR_WEEK.csv":  "week_key",
    "DIM_FESTIVAL.csv":       "festival_id",
    "DIM_WEATHER.csv":        "week_start_date",
}
for fname, pk in pk_checks.items():
    df = load(fname)
    dups = df[pk].duplicated().sum()
    nulls = df[pk].isna().sum()
    check(vid(), fname, f"PK_UNIQUENESS_{pk}",
          "All values unique and non-null",
          f"Duplicates: {dups}, Nulls: {nulls}",
          "PASS" if dups == 0 and nulls == 0 else "FAIL",
          "HIGH" if dups > 0 else "INFO",
          int(dups + nulls))

# Composite key checks
dem = load("FACT_DEMAND.csv")
dem["week_start_date"] = pd.to_datetime(dem["week_start_date"], errors="coerce")
ck = dem[["location_id","product_id","week_start_date"]].drop_duplicates()
grain_dups = len(dem) - len(ck)
check(vid(), "FACT_DEMAND.csv", "COMPOSITE_KEY_location_product_week",
      "Unique grain: location_id + product_id + week_start_date",
      f"Duplicates at grain: {grain_dups}",
      "PASS" if grain_dups == 0 else "WARNING",
      "MEDIUM", grain_dups)

inv = load("FACT_INVENTORY_POSITION.csv")
ck_inv = inv[["warehouse_id","product_id","shelf_id","bin_id"]].drop_duplicates()
inv_dups = len(inv) - len(ck_inv)
check(vid(), "FACT_INVENTORY_POSITION.csv", "COMPOSITE_KEY_warehouse_product_shelf_bin",
      "Unique grain: warehouse_id + product_id + shelf_id + bin_id",
      f"Duplicates: {inv_dups}",
      "PASS" if inv_dups == 0 else "WARNING",
      "MEDIUM", inv_dups)


# ═══════════════════════════════════════════════════════════════════════════════
# Referential integrity
# ═══════════════════════════════════════════════════════════════════════════════
print("Running referential integrity checks...")
dim_loc  = load("DIM_LOCATION.csv")
dim_prod = load("DIM_PRODUCT.csv")
dim_wh   = load("DIM_WAREHOUSE.csv")
dim_sup  = load("DIM_SUPPLIER.csv")

valid_locs  = set(dim_loc["location_id"].dropna())
valid_prods = set(dim_prod["product_id"].dropna())
valid_whs   = set(dim_wh["warehouse_id"].dropna())
valid_sups  = set(dim_sup["supplier_id"].dropna())

# Demand → location
bad = dem["location_id"].isin(valid_locs).value_counts().get(False, 0)
check(vid(), "FACT_DEMAND.csv", "RI_DEMAND_LOCATION",
      "All location_id in DIM_LOCATION", f"Unresolved: {bad}",
      "PASS" if bad == 0 else "FAIL", "HIGH", bad,
      "Quarantine unresolved location records")

# Demand → product
bad = dem["product_id"].isin(valid_prods).value_counts().get(False, 0)
check(vid(), "FACT_DEMAND.csv", "RI_DEMAND_PRODUCT",
      "All product_id in DIM_PRODUCT", f"Unresolved: {bad}",
      "PASS" if bad == 0 else "FAIL", "HIGH", bad)

# Inventory → warehouse
bad = inv["warehouse_id"].isin(valid_whs).value_counts().get(False, 0)
check(vid(), "FACT_INVENTORY_POSITION.csv", "RI_INVENTORY_WAREHOUSE",
      "All warehouse_id in DIM_WAREHOUSE", f"Unresolved: {bad}",
      "PASS" if bad == 0 else "FAIL", "HIGH", bad)

# Inventory → product
bad = inv["product_id"].isin(valid_prods).value_counts().get(False, 0)
check(vid(), "FACT_INVENTORY_POSITION.csv", "RI_INVENTORY_PRODUCT",
      "All product_id in DIM_PRODUCT", f"Unresolved: {bad}",
      "PASS" if bad == 0 else "FAIL", "HIGH", bad)

# Supplier catalog → supplier
sup_cat = load("BRIDGE_SUPPLIER_PRODUCT.csv")
bad = (~sup_cat["supplier_id"].isin(valid_sups)).sum()
check(vid(), "BRIDGE_SUPPLIER_PRODUCT.csv", "RI_CATALOG_SUPPLIER",
      "All supplier_id in DIM_SUPPLIER", f"Unresolved: {bad}",
      "PASS" if bad == 0 else "FAIL", "HIGH", bad)

bad = (~sup_cat["product_id"].isin(valid_prods)).sum()
check(vid(), "BRIDGE_SUPPLIER_PRODUCT.csv", "RI_CATALOG_PRODUCT",
      "All product_id in DIM_PRODUCT", f"Unresolved: {bad}",
      "PASS" if bad == 0 else "FAIL", "HIGH", bad)


# ═══════════════════════════════════════════════════════════════════════════════
# Domain validation
# ═══════════════════════════════════════════════════════════════════════════════
print("Running domain checks...")

# Weather
weather = load("DIM_WEATHER.csv")
weather["humidity_pct"] = pd.to_numeric(weather["humidity_pct"], errors="coerce")
weather["rainfall_mm"]  = pd.to_numeric(weather["rainfall_mm"], errors="coerce")
bad_hum  = ((weather["humidity_pct"] < 0) | (weather["humidity_pct"] > 100)).sum()
bad_rain = (weather["rainfall_mm"] < 0).sum()
check(vid(), "DIM_WEATHER.csv", "DOMAIN_HUMIDITY_RANGE", "0 ≤ humidity_pct ≤ 100", f"Violations: {bad_hum}",
      "PASS" if bad_hum == 0 else "FAIL", "HIGH", bad_hum)
check(vid(), "DIM_WEATHER.csv", "DOMAIN_RAINFALL_NON_NEGATIVE", "rainfall_mm ≥ 0", f"Violations: {bad_rain}",
      "PASS" if bad_rain == 0 else "FAIL", "HIGH", bad_rain)

# Warehouse
dim_wh["capacity_units"] = pd.to_numeric(dim_wh["capacity_units"], errors="coerce")
bad_cap = (dim_wh["capacity_units"] < 0).sum()
check(vid(), "DIM_WAREHOUSE.csv", "DOMAIN_CAPACITY_NON_NEGATIVE", "capacity_units ≥ 0", f"Violations: {bad_cap}",
      "PASS" if bad_cap == 0 else "FAIL", "HIGH", bad_cap)

# Coordinates
dim_loc["latitude"]  = pd.to_numeric(dim_loc["latitude"], errors="coerce")
dim_loc["longitude"] = pd.to_numeric(dim_loc["longitude"], errors="coerce")
bad_lat = ((dim_loc["latitude"] < 22.0) | (dim_loc["latitude"] > 23.0)).sum()
bad_lon = ((dim_loc["longitude"] < 88.0) | (dim_loc["longitude"] > 89.0)).sum()
check(vid(), "DIM_LOCATION.csv", "DOMAIN_LATITUDE_KOLKATA", "lat in [22,23]", f"Out-of-range: {bad_lat}",
      "PASS" if bad_lat == 0 else "WARNING", "HIGH", bad_lat)
check(vid(), "DIM_LOCATION.csv", "DOMAIN_LONGITUDE_KOLKATA", "lon in [88,89]", f"Out-of-range: {bad_lon}",
      "PASS" if bad_lon == 0 else "WARNING", "HIGH", bad_lon)

# Inventory non-negative stocks
inv["available_stock_units"] = pd.to_numeric(inv["available_stock_units"], errors="coerce")
inv["damaged_units"]         = pd.to_numeric(inv["damaged_units"], errors="coerce")
bad_avail = (inv["available_stock_units"] < 0).sum()
bad_dam   = (inv["damaged_units"] < 0).sum()
check(vid(), "FACT_INVENTORY_POSITION.csv", "DOMAIN_AVAILABLE_STOCK_NON_NEGATIVE",
      "available_stock_units ≥ 0", f"Violations: {bad_avail}",
      "PASS" if bad_avail == 0 else "FAIL", "HIGH", bad_avail)
check(vid(), "FACT_INVENTORY_POSITION.csv", "DOMAIN_DAMAGED_UNITS_NON_NEGATIVE",
      "damaged_units ≥ 0", f"Violations: {bad_dam}",
      "PASS" if bad_dam == 0 else "FAIL", "HIGH", bad_dam)


# ═══════════════════════════════════════════════════════════════════════════════
# Temporal validation
# ═══════════════════════════════════════════════════════════════════════════════
print("Running temporal checks...")
weather["week_start_date"] = pd.to_datetime(weather["week_start_date"], errors="coerce")
weather["week_end_date"]   = pd.to_datetime(weather["week_end_date"], errors="coerce")
weather["interval"] = (weather["week_end_date"] - weather["week_start_date"]).dt.days
bad_interval = (weather["interval"] != 6).sum()
check(vid(), "DIM_WEATHER.csv", "TEMPORAL_WEEK_INTERVAL_7DAYS",
      "week_end - week_start = 6 days (7-day window)", f"Violations: {bad_interval}",
      "PASS" if bad_interval == 0 else "WARNING", "MEDIUM", bad_interval)

# Demand date consistency
dem["week_start_date"] = pd.to_datetime(dem["week_start_date"], errors="coerce")
dem["week_end_date"]   = pd.to_datetime(dem["week_end_date"], errors="coerce")
bad_order = (dem["week_start_date"] > dem["week_end_date"]).sum()
check(vid(), "FACT_DEMAND.csv", "TEMPORAL_WEEK_START_BEFORE_END",
      "week_start_date < week_end_date", f"Violations: {bad_order}",
      "PASS" if bad_order == 0 else "FAIL", "HIGH", bad_order)

# Target leakage check: ensure next_week_demand_target_units NOT in DEMAND_FEATURES
feat_file = FEAT / "DEMAND_FEATURES.csv"
if feat_file.exists():
    feat_cols = pd.read_csv(feat_file, nrows=1).columns.tolist()
    leakage = "next_week_demand_target_units" in feat_cols
    check(vid(), "DEMAND_FEATURES.csv", "LEAKAGE_TARGET_NOT_IN_FEATURES",
          "next_week_demand_target_units absent from DEMAND_FEATURES",
          "TARGET PRESENT (LEAKAGE!)" if leakage else "Target absent (safe)",
          "FAIL" if leakage else "PASS", "CRITICAL", 1 if leakage else 0,
          "Remove next_week_demand_target_units from features immediately")


# ═══════════════════════════════════════════════════════════════════════════════
# Supply business rules
# ═══════════════════════════════════════════════════════════════════════════════
print("Running supply business rule checks...")
sup_feat = pd.read_csv(FEAT / "SUPPLY_FEATURES.csv", low_memory=False)
for c in ["minimum_order_qty_units","max_order_qty_units","max_ship_qty_at_once_units",
          "supplier_storage_capacity_units","vehicle_load_capacity_units","lead_time_days"]:
    if c in sup_feat.columns:
        sup_feat[c] = pd.to_numeric(sup_feat[c], errors="coerce")

bad_moq = (sup_feat["minimum_order_qty_units"] < 0).sum()
check(vid(), "SUPPLY_FEATURES.csv", "DOMAIN_MOQ_NON_NEGATIVE", "MOQ ≥ 0", f"Violations: {bad_moq}",
      "PASS" if bad_moq == 0 else "FAIL", "HIGH", bad_moq)

bad_lead = (sup_feat["lead_time_days"] < 0).sum()
check(vid(), "SUPPLY_FEATURES.csv", "DOMAIN_LEAD_TIME_NON_NEGATIVE", "lead_time_days ≥ 0", f"Violations: {bad_lead}",
      "PASS" if bad_lead == 0 else "FAIL", "HIGH", bad_lead)

moq_over_max = (sup_feat["minimum_order_qty_units"] > sup_feat["max_order_qty_units"]).sum()
check(vid(), "SUPPLY_FEATURES.csv", "BUSINESS_RULE_MOQ_LEQT_MAX_ORDER",
      "MOQ ≤ max_order_qty", f"Violations: {moq_over_max}",
      "PASS" if moq_over_max == 0 else "WARNING", "MEDIUM", moq_over_max)


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-dataset consistency
# ═══════════════════════════════════════════════════════════════════════════════
print("Running cross-dataset consistency checks...")

# Products in demand vs DIM_PRODUCT
prods_demand = set(dem["product_id"].dropna())
prods_master = set(dim_prod["product_id"].dropna())
only_demand = prods_demand - prods_master
only_master = prods_master - prods_demand
check(vid(), "FACT_DEMAND vs DIM_PRODUCT", "CONSISTENCY_DEMAND_PRODUCT_MATCH",
      "All demand products in DIM_PRODUCT",
      f"In demand only: {len(only_demand)}, In master only: {len(only_master)}",
      "PASS" if len(only_demand) == 0 else "WARNING", "MEDIUM", len(only_demand))

# Locations in demand vs DIM_LOCATION
locs_demand  = set(dem["location_id"].dropna())
locs_master  = set(dim_loc["location_id"].dropna())
only_demand_loc = locs_demand - locs_master
only_master_loc = locs_master - locs_demand
check(vid(), "FACT_DEMAND vs DIM_LOCATION", "CONSISTENCY_DEMAND_LOCATION_MATCH",
      "All demand locations in DIM_LOCATION",
      f"In demand only: {len(only_demand_loc)}, In master only: {len(only_master_loc)}",
      "PASS" if len(only_demand_loc) == 0 else "WARNING", "MEDIUM", len(only_demand_loc))

# Warehouses in inventory vs DIM_WAREHOUSE
whs_inv    = set(inv["warehouse_id"].dropna())
whs_master = set(dim_wh["warehouse_id"].dropna())
only_inv_wh = whs_inv - whs_master
check(vid(), "FACT_INVENTORY vs DIM_WAREHOUSE", "CONSISTENCY_INVENTORY_WAREHOUSE_MATCH",
      "All inventory warehouses in DIM_WAREHOUSE",
      f"In inventory only: {len(only_inv_wh)}",
      "PASS" if len(only_inv_wh) == 0 else "FAIL", "HIGH", len(only_inv_wh))


# ═══════════════════════════════════════════════════════════════════════════════
# Quarantine collection
# ═══════════════════════════════════════════════════════════════════════════════
print("Generating quarantine records...")
quarantine_rows = []

# Unmapped column in supplier catalog
quarantine_rows.append({
    "quarantine_id": "QRN-001",
    "source_file": "supplier_inventory.xlsx/Supplier_Product_Catalog",
    "source_column": "column_index_10",
    "record_count": 8000,
    "reason": "SUPPLIER_CATALOG_UNMAPPED_COLUMN: Column at index 10 has no header. Values are numeric (~35-200). Possible unit conversion ratio or undocumented pricing metric. Cannot safely assign semantic meaning without domain expert input.",
    "severity": "HIGH",
    "suggested_action": "Domain expert to confirm whether this is MOQ fraction, unit_quantity_ratio, or another field. Preserved as unmapped_col_10_quarantine.",
    "pipeline_timestamp": NOW,
})

# Unresolved LFS data
quarantine_rows.append({
    "quarantine_id": "QRN-002",
    "source_file": "sales_history.xlsx",
    "source_column": "ALL",
    "record_count": -1,
    "reason": "SALES_HISTORY_SOURCE_UNAVAILABLE: Git-LFS pointer. Underlying 177MB XLSX not fetched. FACT_SALES cannot be built.",
    "severity": "CRITICAL",
    "suggested_action": "Run `git lfs pull` to fetch the file.",
    "pipeline_timestamp": NOW,
})

quarantine_rows.append({
    "quarantine_id": "QRN-003",
    "source_file": "inventory_transactions.xlsx",
    "source_column": "ALL",
    "record_count": -1,
    "reason": "INVENTORY_TRANSACTIONS_SOURCE_UNAVAILABLE: Git-LFS pointer. Underlying 56MB XLSX not fetched. FACT_INVENTORY_TRANSACTION cannot be built.",
    "severity": "CRITICAL",
    "suggested_action": "Run `git lfs pull` to fetch the file.",
    "pipeline_timestamp": NOW,
})

pd.DataFrame(quarantine_rows).to_csv(QRT / "quarantine_log.csv", index=False)
print(f"  Quarantine: {len(quarantine_rows)} issues logged")


# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
detail_df = pd.DataFrame(details)
detail_df.to_csv(VAL / "validation_details.csv", index=False)

summary_data = []
for ds in detail_df["dataset"].unique():
    sub = detail_df[detail_df["dataset"] == ds]
    cnt = sub["status"].value_counts().to_dict()
    summary_data.append({
        "dataset": ds,
        "total_checks": len(sub),
        "PASS": cnt.get("PASS", 0),
        "WARNING": cnt.get("WARNING", 0),
        "FAIL": cnt.get("FAIL", 0),
        "BLOCKED_BY_SOURCE": cnt.get("BLOCKED_BY_SOURCE", 0),
        "overall_status": "FAIL" if cnt.get("FAIL", 0) > 0 else (
            "BLOCKED_BY_SOURCE" if cnt.get("BLOCKED_BY_SOURCE", 0) > 0 else (
                "WARNING" if cnt.get("WARNING", 0) > 0 else "PASS"
            )
        ),
        "pipeline_timestamp": NOW,
    })

summary_df = pd.DataFrame(summary_data)
summary_df.to_csv(VAL / "validation_summary.csv", index=False)

total = len(detail_df)
passes = (detail_df["status"] == "PASS").sum()
warns  = (detail_df["status"] == "WARNING").sum()
fails  = (detail_df["status"] == "FAIL").sum()
blocked= (detail_df["status"] == "BLOCKED_BY_SOURCE").sum()
print(f"\n✅ Stage 05 validation complete.")
print(f"  Total checks: {total}")
print(f"  PASS: {passes}, WARNING: {warns}, FAIL: {fails}, BLOCKED: {blocked}")

