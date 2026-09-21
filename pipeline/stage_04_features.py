"""
Stage 04: Feature Engineering — agent-specific feature tables.
"""
import pandas as pd
import numpy as np
import math
import warnings
from pathlib import Path
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

BASE = Path(r"D:\ai-multi-agent-supply-chain")
CUR  = BASE / "data" / "06_curated"
FEAT = BASE / "data" / "07_features"
NOW  = datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# N1. DEMAND AGENT FEATURES
# ═══════════════════════════════════════════════════════════════════════════════
print("Building DEMAND_FEATURES...")
demand = pd.read_csv(CUR / "FACT_DEMAND.csv", low_memory=False)
weather = pd.read_csv(CUR / "DIM_WEATHER.csv")
fests   = pd.read_csv(CUR / "DIM_FESTIVAL.csv")

demand["week_start_date"] = pd.to_datetime(demand["week_start_date"], errors="coerce")
demand["units_sold"]      = pd.to_numeric(demand["units_sold"], errors="coerce")
demand["promotion_flag"]  = pd.to_numeric(demand["promotion_flag"], errors="coerce")
demand["discount_pct"]    = pd.to_numeric(demand["discount_pct"], errors="coerce")
demand["holiday_flag"]    = pd.to_numeric(demand["holiday_flag"], errors="coerce")
demand["stockout_flag"]   = pd.to_numeric(demand["stockout_flag"], errors="coerce")
demand["temperature_c"]   = pd.to_numeric(demand["temperature_c"], errors="coerce")
demand["rainfall_mm"]     = pd.to_numeric(demand["rainfall_mm"], errors="coerce")
demand["humidity_pct"]    = pd.to_numeric(demand["humidity_pct"], errors="coerce")
demand["weekday_units_sold"] = pd.to_numeric(demand["weekday_units_sold"], errors="coerce")
demand["weekend_units_sold"] = pd.to_numeric(demand["weekend_units_sold"], errors="coerce")
demand["next_week_demand_target_units"] = pd.to_numeric(demand["next_week_demand_target_units"], errors="coerce")

# Sort by entity + time for lag computation
demand = demand.sort_values(["location_id", "product_id", "week_start_date"]).reset_index(drop=True)

def make_lag(df, group_cols, val_col, lag, new_col):
    df[new_col] = df.groupby(group_cols)[val_col].shift(lag)
    return df

group = ["location_id", "product_id"]
for lag in [1, 2, 4, 8, 12]:
    demand = make_lag(demand, group, "units_sold", lag, f"lag_{lag}w_units_sold")

# Rolling means (on lag-1 to avoid leakage)
demand["rolling_mean_4w"]  = demand.groupby(group)["lag_1w_units_sold"].transform(lambda x: x.rolling(4, min_periods=1).mean())
demand["rolling_mean_8w"]  = demand.groupby(group)["lag_1w_units_sold"].transform(lambda x: x.rolling(8, min_periods=1).mean())
demand["rolling_mean_12w"] = demand.groupby(group)["lag_1w_units_sold"].transform(lambda x: x.rolling(12, min_periods=1).mean())

# Trend: slope of last 4 weeks lag
def safe_trend(arr):
    # arr is a numpy array when raw=True
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return np.nan
    x = np.arange(len(arr))
    return np.polyfit(x, arr, 1)[0]

demand["demand_trend_4w"] = demand.groupby(group)["lag_1w_units_sold"].transform(
    lambda x: x.rolling(4, min_periods=2).apply(safe_trend, raw=True)
)

# Weekday/weekend ratios
demand["weekday_ratio"] = demand["weekday_units_sold"] / demand["units_sold"].replace(0, np.nan)
demand["weekend_ratio"] = demand["weekend_units_sold"] / demand["units_sold"].replace(0, np.nan)

# Festival context from demand row (already merged in source)
# Compute days_to_next_festival and days_since_last_festival
fests["event_date"] = pd.to_datetime(fests["event_date"])
fest_dates = sorted(fests["event_date"].dt.date.tolist())

def days_to_festival(row_date):
    if pd.isna(row_date):
        return np.nan
    d = row_date.date() if hasattr(row_date, "date") else row_date
    future = [f for f in fest_dates if f >= d]
    return (min(future) - d).days if future else np.nan

def days_since_festival(row_date):
    if pd.isna(row_date):
        return np.nan
    d = row_date.date() if hasattr(row_date, "date") else row_date
    past = [f for f in fest_dates if f <= d]
    return (d - max(past)).days if past else np.nan

demand["days_to_next_festival"]  = demand["week_start_date"].apply(days_to_festival)
demand["days_since_last_festival"] = demand["week_start_date"].apply(days_since_festival)
demand["festival_flag"] = (demand["festival_event"].notna() & (demand["festival_event"] != "None")).astype(int)

# CRITICAL: Target field explicitly marked — NOT to be used as input feature
# Keep as target only
demand_features = demand.drop(columns=[
    "next_week_demand_target_units",   # TARGET — excluded from feature set
    "forecast_target_start",
    "forecast_target_end",
], errors="ignore")

demand_features["feature_set"] = "DEMAND_AGENT"
demand_features["leakage_safe"] = True
demand_features["target_column"] = "next_week_demand_target_units (excluded from features)"
demand_features["pipeline_timestamp"] = NOW

demand_features.to_csv(FEAT / "DEMAND_FEATURES.csv", index=False)
print(f"  DEMAND_FEATURES: {len(demand_features)} rows, {len(demand_features.columns)} cols")


# Also save target file separately (for model training)
demand_target = demand[["demand_id", "location_id", "product_id", "week_start_date",
                          "next_week_demand_target_units", "forecast_target_start"]].copy()
demand_target.to_csv(FEAT / "DEMAND_TARGETS.csv", index=False)
print(f"  DEMAND_TARGETS: {len(demand_target)} rows (leakage-isolated target)")


# ═══════════════════════════════════════════════════════════════════════════════
# N2. INVENTORY AGENT FEATURES
# ═══════════════════════════════════════════════════════════════════════════════
print("Building INVENTORY_FEATURES...")
inv = pd.read_csv(CUR / "FACT_INVENTORY_POSITION.csv", low_memory=False)
wh  = pd.read_csv(CUR / "DIM_WAREHOUSE.csv")

for c in ["current_stock_units","available_stock_units","reserved_stock_units",
          "damaged_units","avg_weekly_demand_units","cost_price_rs","selling_price_rs"]:
    if c in inv.columns:
        inv[c] = pd.to_numeric(inv[c], errors="coerce")

# Merge warehouse capacity
wh_cap = wh[["warehouse_id", "capacity_units"]].copy()
wh_cap["capacity_units"] = pd.to_numeric(wh_cap["capacity_units"], errors="coerce")

# Aggregate inventory per warehouse
inv_agg = inv.groupby("warehouse_id")["current_stock_units"].sum().reset_index()
inv_agg.rename(columns={"current_stock_units": "total_warehouse_stock"}, inplace=True)
inv_agg = inv_agg.merge(wh_cap, on="warehouse_id", how="left")
inv_agg["capacity_utilization_pct"] = (inv_agg["total_warehouse_stock"] / inv_agg["capacity_units"] * 100).round(2)

inv_feat = inv.merge(inv_agg[["warehouse_id","total_warehouse_stock","capacity_units","capacity_utilization_pct"]], on="warehouse_id", how="left")
inv_feat["feature_set"] = "INVENTORY_AGENT"
inv_feat["pipeline_timestamp"] = NOW

inv_feat.to_csv(FEAT / "INVENTORY_FEATURES.csv", index=False)
print(f"  INVENTORY_FEATURES: {len(inv_feat)} rows, {len(inv_feat.columns)} cols")


# ═══════════════════════════════════════════════════════════════════════════════
# N3. SUPPLY AGENT FEATURES
# ═══════════════════════════════════════════════════════════════════════════════
print("Building SUPPLY_FEATURES...")
sup_avail = pd.read_csv(CUR / "FACT_SUPPLIER_AVAILABILITY.csv", low_memory=False)
sup_avail["feature_set"] = "SUPPLY_AGENT"
sup_avail["pipeline_timestamp"] = NOW

# Select relevant supply features
supply_feat_cols = [
    "supplier_id", "product_id", "supplier_type_id", "supplier_type_name",
    "supplier_cost_price_rs", "supplied_unit_size", "supply_status",
    "minimum_order_qty_units", "max_order_qty_units", "max_ship_qty_at_once_units",
    "supplier_storage_capacity_units", "vehicle_type", "vehicle_count",
    "vehicle_load_capacity_units", "lead_time_days", "location_id",
    "unmapped_col_10_quarantine", "feature_set", "pipeline_timestamp"
]
sup_feat = sup_avail[[c for c in supply_feat_cols if c in sup_avail.columns]].copy()
sup_feat.to_csv(FEAT / "SUPPLY_FEATURES.csv", index=False)
print(f"  SUPPLY_FEATURES: {len(sup_feat)} rows, {len(sup_feat.columns)} cols")


# ═══════════════════════════════════════════════════════════════════════════════
# N4. WAREHOUSE AGENT FEATURES
# ═══════════════════════════════════════════════════════════════════════════════
print("Building WAREHOUSE_FEATURES...")
wh_full = pd.read_csv(CUR / "DIM_WAREHOUSE.csv")
wh_inv  = inv_agg.copy()  # warehouse-level inventory summary

wh_feat = wh_full.merge(wh_inv[["warehouse_id","total_warehouse_stock","capacity_utilization_pct"]], on="warehouse_id", how="left")
for c in ["capacity_units","daily_dispatch_capacity_units","service_radius_km",
          "total_vehicle_count","cycle_count","bike_count","scooter_count",
          "electric_scooter_count","auto_count"]:
    if c in wh_feat.columns:
        wh_feat[c] = pd.to_numeric(wh_feat[c], errors="coerce")

wh_feat["free_capacity_units"] = wh_feat["capacity_units"] - wh_feat["total_warehouse_stock"]
wh_feat["feature_set"] = "WAREHOUSE_AGENT"
wh_feat["pipeline_timestamp"] = NOW

wh_feat.to_csv(FEAT / "WAREHOUSE_FEATURES.csv", index=False)
print(f"  WAREHOUSE_FEATURES: {len(wh_feat)} rows, {len(wh_feat.columns)} cols")


# ═══════════════════════════════════════════════════════════════════════════════
# N5. ROUTING FEATURES
# ═══════════════════════════════════════════════════════════════════════════════
print("Building ROUTING_FEATURES...")
# Use BRIDGE_WAREHOUSE_LOCATION which has euclidean_distance_km
bridge_wl = pd.read_csv(CUR / "BRIDGE_WAREHOUSE_LOCATION.csv")
bridge_ls  = pd.read_csv(CUR / "BRIDGE_LOCATION_SUPPLIER.csv")

# Warehouse → Location routing
rt_wl = bridge_wl[["warehouse_id","location_id","euclidean_distance_km","service_available_flag"]].copy()
rt_wl["origin_type"] = "WAREHOUSE"
rt_wl["destination_type"] = "LOCATION"
rt_wl.rename(columns={"warehouse_id":"origin_id","location_id":"destination_id"}, inplace=True)

# Supplier → Location routing
rt_sl = bridge_ls[["supplier_id","location_id","distance_from_location_center_km","service_available_flag"]].copy()
rt_sl.rename(columns={
    "supplier_id":"origin_id",
    "location_id":"destination_id",
    "distance_from_location_center_km":"euclidean_distance_km"
}, inplace=True)
rt_sl["origin_type"] = "SUPPLIER"
rt_sl["destination_type"] = "LOCATION"

routing_feat = pd.concat([rt_wl, rt_sl], ignore_index=True)
routing_feat["distance_type"] = "euclidean_km"
routing_feat["note"] = "Euclidean (Haversine) distance only. Road distance not available — do not use as road_distance_km."
routing_feat["feature_set"] = "ROUTE_OPTIMIZATION_AGENT"
routing_feat["pipeline_timestamp"] = NOW

routing_feat.to_csv(FEAT / "ROUTING_FEATURES.csv", index=False)
print(f"  ROUTING_FEATURES: {len(routing_feat)} rows")


# ═══════════════════════════════════════════════════════════════════════════════
# N6. RISK AGENT FEATURES
# ═══════════════════════════════════════════════════════════════════════════════
print("Building RISK_FEATURES...")
risk_rows = []

# From inventory: shortage/reorder risk per warehouse-product
inv_risk = inv_feat[["warehouse_id","product_id","available_stock_units","avg_weekly_demand_units",
                       "weeks_of_cover_calc","reorder_flag_calc","stock_status","inventory_risk",
                       "shortage_units","capacity_utilization_pct"]].copy()
inv_risk["risk_source"] = "INVENTORY"

# From demand: stockout signal
demand_risk = demand[["location_id","product_id","week_start_date","stockout_flag",
                        "rainfall_mm","humidity_pct","temperature_c","festival_flag",
                        "holiday_flag","weather_condition"]].copy()
demand_risk["risk_source"] = "DEMAND_OBSERVATION"

# From supplier: lead time risk
sup_risk = sup_feat[["supplier_id","product_id","lead_time_days","supply_status",
                       "supplier_storage_capacity_units"]].copy()
sup_risk["high_lead_time"] = (pd.to_numeric(sup_risk["lead_time_days"], errors="coerce") > 3).astype(int)
sup_risk["risk_source"] = "SUPPLIER"

# Save each separately (don't merge — different grains)
inv_risk["pipeline_timestamp"] = NOW
demand_risk["pipeline_timestamp"] = NOW
sup_risk["pipeline_timestamp"] = NOW

inv_risk.to_csv(FEAT / "RISK_FEATURES_INVENTORY.csv", index=False)
demand_risk.to_csv(FEAT / "RISK_FEATURES_DEMAND.csv", index=False)
sup_risk.to_csv(FEAT / "RISK_FEATURES_SUPPLY.csv", index=False)

# Combine into unified RISK_FEATURES with shared columns
risk_unified = pd.DataFrame([{
    "risk_feature_type": "INVENTORY_SHORTAGE",
    "record_count": len(inv_risk),
    "key_grain": "warehouse_id + product_id",
    "output_file": "RISK_FEATURES_INVENTORY.csv",
    "pipeline_timestamp": NOW,
},{
    "risk_feature_type": "DEMAND_STOCKOUT",
    "record_count": len(demand_risk),
    "key_grain": "location_id + product_id + week_start_date",
    "output_file": "RISK_FEATURES_DEMAND.csv",
    "pipeline_timestamp": NOW,
},{
    "risk_feature_type": "SUPPLIER_LEAD_TIME",
    "record_count": len(sup_risk),
    "key_grain": "supplier_id + product_id",
    "output_file": "RISK_FEATURES_SUPPLY.csv",
    "pipeline_timestamp": NOW,
}])
risk_unified.to_csv(FEAT / "RISK_FEATURES.csv", index=False)
print(f"  RISK_FEATURES: 3 sub-tables (inv={len(inv_risk)}, demand={len(demand_risk)}, supply={len(sup_risk)})")

print("\n✅ Stage 04 feature engineering complete.")

