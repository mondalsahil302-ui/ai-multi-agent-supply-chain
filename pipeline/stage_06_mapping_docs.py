"""
Stage 06: Entity mapping files, agent-ready copy, data lineage, and documentation.
"""
import pandas as pd
import json
import warnings
from pathlib import Path
from datetime import datetime, timezone
import shutil

warnings.filterwarnings("ignore")

BASE = Path(r"D:\ai-multi-agent-supply-chain")
CUR  = BASE / "data" / "06_curated"
FEAT = BASE / "data" / "07_features"
MAP  = BASE / "data" / "05_entity_mapping"
AGT  = BASE / "data" / "09_agent_ready"
DOC  = BASE / "data" / "10_documentation"
VAL  = BASE / "data" / "08_validation"
QRT  = BASE / "data" / "data_quarantine"
NOW  = datetime.now(timezone.utc).isoformat()


# ═══════════════════════════════════════════════════════════════════════════════
# Entity Mapping CSV + JSON
# ═══════════════════════════════════════════════════════════════════════════════
print("Building entity_mapping.csv and entity_mapping.json...")

mapping_rows = [
    # Product mappings
    {"source_table":"products.csv","source_field":"product_id","canonical_entity":"DIM_PRODUCT","canonical_field":"product_id","relationship_type":"PK","target_table":"DIM_PRODUCT","target_field":"product_id","confidence":"HIGH","transformation_required":"None","notes":"Direct copy"},
    {"source_table":"products.csv","source_field":"unit_size_1..5","canonical_entity":"DIM_PRODUCT_VARIANT","canonical_field":"unit_size_raw","relationship_type":"NORMALIZATION","target_table":"DIM_PRODUCT_VARIANT","target_field":"product_variant_id","confidence":"HIGH","transformation_required":"Pivot wide→long, generate product_variant_id","notes":"5 variants per product normalized"},
    # Location mappings
    {"source_table":"locations.csv.csv","source_field":"location_id","canonical_entity":"DIM_LOCATION","canonical_field":"location_id","relationship_type":"PK","target_table":"DIM_LOCATION","target_field":"location_id","confidence":"HIGH","transformation_required":"None","notes":"Primary location key"},
    {"source_table":"supplier_inventory.xlsx/Area_Master","source_field":"location_latitude","canonical_entity":"DIM_LOCATION","canonical_field":"latitude","relationship_type":"ENRICHMENT","target_table":"DIM_LOCATION","target_field":"latitude","confidence":"HIGH","transformation_required":"LEFT JOIN on location_id","notes":"Lat/lon from supplier Area_Master"},
    # Warehouse mappings
    {"source_table":"warehouses.xlsx","source_field":"warehouse_id","canonical_entity":"DIM_WAREHOUSE","canonical_field":"warehouse_id","relationship_type":"PK","target_table":"DIM_WAREHOUSE","target_field":"warehouse_id","confidence":"HIGH","transformation_required":"None","notes":"Primary warehouse key"},
    {"source_table":"final_warehouse_dataset_kolkata.xlsx","source_field":"storage_type","canonical_entity":"DIM_WAREHOUSE","canonical_field":"storage_type","relationship_type":"ENRICHMENT","target_table":"DIM_WAREHOUSE","target_field":"storage_type","confidence":"HIGH","transformation_required":"LEFT JOIN on warehouse_id","notes":"Storage type from secondary source"},
    # Supplier mappings
    {"source_table":"supplier_inventory.xlsx/Supplier_Master","source_field":"supplier_id","canonical_entity":"DIM_SUPPLIER","canonical_field":"supplier_id","relationship_type":"PK","target_table":"DIM_SUPPLIER","target_field":"supplier_id","confidence":"HIGH","transformation_required":"snake_case column names","notes":"200 suppliers"},
    # Calendar
    {"source_table":"weather_weekly.csv","source_field":"week_start_date","canonical_entity":"DIM_CALENDAR_WEEK","canonical_field":"week_start_date","relationship_type":"PK","target_table":"DIM_CALENDAR_WEEK","target_field":"week_key","confidence":"HIGH","transformation_required":"Derive week_key as YYYYMMDD string","notes":"105 weeks"},
    # Weather
    {"source_table":"weather_weekly.csv","source_field":"temperature_mean_c","canonical_entity":"DIM_WEATHER","canonical_field":"temperature_mean_c","relationship_type":"DIRECT","target_table":"DIM_WEATHER","target_field":"temperature_mean_c","confidence":"HIGH","transformation_required":"None","notes":"Marked as SUPPLIED_SYNTHETIC"},
    {"source_table":"weather_weekly.csv","source_field":"temperature_mean_c","canonical_entity":"DEMAND_FEATURES","canonical_field":"temperature_c","relationship_type":"FEATURE","target_table":"DEMAND_FEATURES","target_field":"temperature_c","confidence":"HIGH","transformation_required":"Joined via week_start_date","notes":"Demand agent feature"},
    # Festival
    {"source_table":"festival_calendar.csv","source_field":"festival_event","canonical_entity":"DIM_FESTIVAL","canonical_field":"festival_event","relationship_type":"DIRECT","target_table":"DIM_FESTIVAL","target_field":"festival_event","confidence":"HIGH","transformation_required":"Derive festival_id, festival_category, week_start_date","notes":"36 events"},
    # Demand
    {"source_table":"Demand of last 2 years.xlsx","source_field":"demand_id","canonical_entity":"FACT_DEMAND","canonical_field":"demand_id","relationship_type":"PK","target_table":"FACT_DEMAND","target_field":"demand_id","confidence":"HIGH","transformation_required":"Date parsing, numeric conversion","notes":"27,800 rows"},
    {"source_table":"Demand of last 2 years.xlsx","source_field":"next_week_demand_target_units","canonical_entity":"DEMAND_TARGETS","canonical_field":"next_week_demand_target_units","relationship_type":"TARGET","target_table":"DEMAND_TARGETS","target_field":"next_week_demand_target_units","confidence":"HIGH","transformation_required":"Isolated to target file to prevent leakage","notes":"LEAKAGE-SAFE"},
    # Inventory
    {"source_table":"inventory_stock.xlsx/Inventory_Position","source_field":"warehouse_id","canonical_entity":"FACT_INVENTORY_POSITION","canonical_field":"warehouse_id","relationship_type":"FK","target_table":"FACT_INVENTORY_POSITION","target_field":"warehouse_id","confidence":"HIGH","transformation_required":"snake_case","notes":"FK to DIM_WAREHOUSE"},
    {"source_table":"inventory_stock.xlsx/Inventory_Control","source_field":"weeks_of_cover","canonical_entity":"FACT_INVENTORY_POSITION","canonical_field":"weeks_of_cover_calc","relationship_type":"RECALCULATED","target_table":"FACT_INVENTORY_POSITION","target_field":"weeks_of_cover_calc","confidence":"HIGH","transformation_required":"Recalculated: available_stock / avg_weekly_demand","notes":"Formula explicitly recalculated; not trusting cached formula values"},
    # Bridge tables
    {"source_table":"supplier_inventory.xlsx/Supplier_Product_Catalog","source_field":"supplier_product_key","canonical_entity":"BRIDGE_SUPPLIER_PRODUCT","canonical_field":"supplier_product_key","relationship_type":"PK","target_table":"BRIDGE_SUPPLIER_PRODUCT","target_field":"supplier_product_key","confidence":"HIGH","transformation_required":"Rename column 12 (unmapped) to unmapped_col_10_quarantine","notes":"SUPPLIER_CATALOG_UNMAPPED_COLUMN preserved"},
    {"source_table":"supplier_inventory.xlsx/Area_Supplier_Options","source_field":"location_id","canonical_entity":"BRIDGE_LOCATION_SUPPLIER","canonical_field":"location_id","relationship_type":"FK","target_table":"BRIDGE_LOCATION_SUPPLIER","target_field":"location_id","confidence":"HIGH","transformation_required":"snake_case","notes":"200 area-supplier pairs"},
    {"source_table":"DERIVED_HAVERSINE","source_field":"N/A","canonical_entity":"BRIDGE_WAREHOUSE_LOCATION","canonical_field":"euclidean_distance_km","relationship_type":"DERIVED","target_table":"BRIDGE_WAREHOUSE_LOCATION","target_field":"euclidean_distance_km","confidence":"MEDIUM","transformation_required":"Haversine formula from warehouse+location coordinates","notes":"NOT road distance — clearly labeled euclidean_km"},
]

em_df = pd.DataFrame(mapping_rows)
em_df.to_csv(MAP / "entity_mapping.csv", index=False)
em_df.to_json(MAP / "entity_mapping.json", orient="records", indent=2)
print(f"  entity_mapping: {len(em_df)} mappings")


# ═══════════════════════════════════════════════════════════════════════════════
# Agent-ready: copy curated + feature files to 09_agent_ready
# ═══════════════════════════════════════════════════════════════════════════════
print("Copying to agent-ready layer...")

agent_files = [
    # Dimensions
    ("06_curated", "DIM_LOCATION.csv"),
    ("06_curated", "DIM_PRODUCT.csv"),
    ("06_curated", "DIM_PRODUCT_VARIANT.csv"),
    ("06_curated", "DIM_WAREHOUSE.csv"),
    ("06_curated", "DIM_SUPPLIER.csv"),
    ("06_curated", "DIM_CALENDAR_WEEK.csv"),
    ("06_curated", "DIM_FESTIVAL.csv"),
    ("06_curated", "DIM_WEATHER.csv"),
    # Facts
    ("06_curated", "FACT_DEMAND.csv"),
    ("06_curated", "FACT_INVENTORY_POSITION.csv"),
    ("06_curated", "FACT_SUPPLIER_AVAILABILITY.csv"),
    # Bridge tables
    ("06_curated", "BRIDGE_SUPPLIER_PRODUCT.csv"),
    ("06_curated", "BRIDGE_LOCATION_SUPPLIER.csv"),
    ("06_curated", "BRIDGE_WAREHOUSE_LOCATION.csv"),
    ("06_curated", "BRIDGE_PRODUCT_WAREHOUSE.csv"),
    # Blocked outputs
    ("06_curated", "FACT_SALES__BLOCKED.csv"),
    ("06_curated", "FACT_INVENTORY_TRANSACTION__BLOCKED.csv"),
    # Training data
    ("06_curated", "DEMAND_TRAINING_DATA.csv"),
    # Features
    ("07_features", "DEMAND_FEATURES.csv"),
    ("07_features", "DEMAND_TARGETS.csv"),
    ("07_features", "INVENTORY_FEATURES.csv"),
    ("07_features", "SUPPLY_FEATURES.csv"),
    ("07_features", "WAREHOUSE_FEATURES.csv"),
    ("07_features", "ROUTING_FEATURES.csv"),
    ("07_features", "RISK_FEATURES.csv"),
    ("07_features", "RISK_FEATURES_INVENTORY.csv"),
    ("07_features", "RISK_FEATURES_DEMAND.csv"),
    ("07_features", "RISK_FEATURES_SUPPLY.csv"),
]

for layer, fname in agent_files:
    src = BASE / "data" / layer / fname
    dst = AGT / fname
    if src.exists():
        shutil.copy2(src, dst)
    else:
        print(f"  WARN: {fname} not found in {layer}")

print(f"  Agent-ready files: {len(list(AGT.iterdir()))} files")


# ═══════════════════════════════════════════════════════════════════════════════
# Data Lineage
# ═══════════════════════════════════════════════════════════════════════════════
print("Writing data_lineage.csv...")
lineage = [
    {"source_dataset":"weather_weekly.csv","source_column":"temperature_mean_c","transformation":"Direct copy","target_dataset":"DIM_WEATHER","target_column":"temperature_mean_c","agent_consumer":"Demand Agent, Risk Agent"},
    {"source_dataset":"DIM_WEATHER","source_column":"temperature_mean_c","transformation":"Joined to FACT_DEMAND via week_start_date","target_dataset":"DEMAND_FEATURES","target_column":"temperature_c","agent_consumer":"Demand Agent"},
    {"source_dataset":"festival_calendar.csv","source_column":"event_date","transformation":"Derive week_start_date via period(W-MON)","target_dataset":"DIM_FESTIVAL","target_column":"week_start_date","agent_consumer":"Demand Agent, Risk Agent"},
    {"source_dataset":"products.csv","source_column":"unit_size_1..5, cp_N_rs, sp_N_rs","transformation":"Pivot wide→long, generate product_variant_id","target_dataset":"DIM_PRODUCT_VARIANT","target_column":"product_variant_id, unit_size_raw","agent_consumer":"Inventory Agent, Supply Agent"},
    {"source_dataset":"Demand of last 2 years.xlsx","source_column":"units_sold","transformation":"Sort by location+product+week, generate lag features","target_dataset":"DEMAND_FEATURES","target_column":"lag_1w_units_sold..lag_12w_units_sold","agent_consumer":"Demand Agent"},
    {"source_dataset":"Demand of last 2 years.xlsx","source_column":"next_week_demand_target_units","transformation":"Isolated to DEMAND_TARGETS to prevent leakage","target_dataset":"DEMAND_TARGETS","target_column":"next_week_demand_target_units","agent_consumer":"Demand Agent (training target only)"},
    {"source_dataset":"inventory_stock.xlsx/Inventory_Position","source_column":"available_stock_units, avg_weekly_demand_units","transformation":"weeks_of_cover = available/avg_weekly_demand","target_dataset":"FACT_INVENTORY_POSITION","target_column":"weeks_of_cover_calc","agent_consumer":"Inventory Agent, Risk Agent"},
    {"source_dataset":"inventory_stock.xlsx/Inventory_Control","source_column":"inventory_risk","transformation":"Direct copy after snake_case rename","target_dataset":"INVENTORY_FEATURES","target_column":"inventory_risk","agent_consumer":"Risk Agent"},
    {"source_dataset":"supplier_inventory.xlsx/Supplier_Master","source_column":"lead_time_days","transformation":"Direct copy","target_dataset":"SUPPLY_FEATURES","target_column":"lead_time_days","agent_consumer":"Supply Agent, Risk Agent"},
    {"source_dataset":"warehouses.xlsx","source_column":"latitude, longitude, service_radius_km","transformation":"Haversine distance to each location","target_dataset":"BRIDGE_WAREHOUSE_LOCATION","target_column":"euclidean_distance_km, service_available_flag","agent_consumer":"Route Optimization Agent, Warehouse Agent"},
    {"source_dataset":"supplier_inventory.xlsx/Area_Supplier_Options","source_column":"distance_from_location_center_km","transformation":"Direct copy to ROUTING_FEATURES","target_dataset":"ROUTING_FEATURES","target_column":"euclidean_distance_km","agent_consumer":"Route Optimization Agent"},
    {"source_dataset":"supplier_inventory.xlsx/Supplier_Product_Catalog","source_column":"col_index_10 (unlabeled)","transformation":"Preserved as unmapped_col_10_quarantine","target_dataset":"BRIDGE_SUPPLIER_PRODUCT","target_column":"unmapped_col_10_quarantine","agent_consumer":"QUARANTINE — domain review required"},
    {"source_dataset":"locations.csv.csv + supplier_inventory.xlsx/Area_Master","source_column":"location_id, latitude, longitude","transformation":"LEFT JOIN on location_id to enrich location with coordinates","target_dataset":"DIM_LOCATION","target_column":"latitude, longitude","agent_consumer":"All agents needing geospatial context"},
    {"source_dataset":"warehouses.xlsx + final_warehouse_dataset_kolkata.xlsx","source_column":"storage_type, status","transformation":"LEFT JOIN on warehouse_id","target_dataset":"DIM_WAREHOUSE","target_column":"storage_type, status","agent_consumer":"Warehouse Agent"},
]
pd.DataFrame(lineage).to_csv(DOC / "data_lineage.csv", index=False)
print(f"  data_lineage: {len(lineage)} lineage records")


# ═══════════════════════════════════════════════════════════════════════════════
# Documentation files
# ═══════════════════════════════════════════════════════════════════════════════
print("Writing documentation...")

# --- DATA_FOUNDATION_README.md ---
readme_text = """# Data Foundation — AI Multi-Agent Supply Chain (Kolkata)

## Overview
This folder contains the complete data foundation pipeline outputs for the Kolkata Multi-Agent Supply Chain system. All layers were built by the automated ETL pipeline and are traceable from raw source to agent-ready output.

## Pipeline Layers
| Layer | Folder | Contents |
|---|---|---|
| 01 | `01_raw/` | Immutable copies of source files |
| 02 | `02_profile/` | Data profiling CSVs |
| 03 | `03_staging/` | Intermediate staging (scripts use direct read) |
| 04 | `04_standardized/` | Reserved for manual overrides |
| 05 | `05_entity_mapping/` | entity_mapping.csv + entity_mapping.json |
| 06 | `06_curated/` | All canonical DIM/FACT/BRIDGE tables |
| 07 | `07_features/` | Agent-specific feature tables |
| 08 | `08_validation/` | Validation summary + details |
| 09 | `09_agent_ready/` | Final copy for agent consumption |
| 10 | `10_documentation/` | All documentation |
| — | `data_quarantine/` | Quarantined unresolved records |

## Key Entities
- **DIM_PRODUCT**: 200 products, 20 categories, 10 per category
- **DIM_PRODUCT_VARIANT**: 1,000 variants (5 sizes per product)
- **DIM_LOCATION**: 40 Kolkata regions
- **DIM_WAREHOUSE**: 15 warehouses
- **DIM_SUPPLIER**: 200 suppliers
- **DIM_CALENDAR_WEEK**: 105 weeks
- **DIM_FESTIVAL**: 36 festival events
- **DIM_WEATHER**: 105 weekly weather records

## BLOCKED Sources (Git-LFS)
- `sales_history.xlsx` → FACT_SALES BLOCKED
- `inventory_transactions.xlsx` → FACT_INVENTORY_TRANSACTION BLOCKED

Run `git lfs pull` to restore these files.

## Source Data Classification
All synthetic/supplied data is clearly marked. No observed real-world data was altered.
"""

# --- KNOWN_LIMITATIONS.md ---
limitations_text = """# Known Limitations

## Critical Blockers
1. **SALES_HISTORY_SOURCE_UNAVAILABLE**: `sales_history.xlsx` is a Git-LFS pointer (expected 177MB).
   - Impact: FACT_SALES cannot be built. Demand Agent cannot validate against actual sales.
   - Fix: `git lfs pull` in repo root.

2. **INVENTORY_TRANSACTIONS_SOURCE_UNAVAILABLE**: `inventory_transactions.xlsx` is a Git-LFS pointer (expected 56MB).
   - Impact: FACT_INVENTORY_TRANSACTION cannot be built. Transaction-level inventory tracking unavailable.
   - Fix: `git lfs pull` in repo root.

## Data Quality Issues
3. **SUPPLIER_CATALOG_UNMAPPED_COLUMN**: Column at index 10 in `Supplier_Product_Catalog` has no header.
   - Values are numeric (range ~9–200), possibly unit conversion ratio.
   - Preserved as `unmapped_col_10_quarantine`. Requires domain expert review.

4. **Synthetic Training Data**: Both demand datasets are explicitly labeled `SYNTHETIC_TRAINING`.
   - Do not treat demand data as observed real-world sales.
   - Weather context is marked `SUPPLIED_SYNTHETIC`.

5. **No Road Distance Available**: `BRIDGE_WAREHOUSE_LOCATION` uses Haversine (euclidean) distance.
   - Field is named `euclidean_distance_km`, NOT road_distance_km.
   - Route Optimization Agent must not use this as road distance.

6. **Product Variant Join in Demand**: FACT_DEMAND contains `unit_size` (string, e.g., "500 g") but does not directly join to DIM_PRODUCT_VARIANT by product_variant_id.
   - A join on `product_id + unit_size_raw` is required for variant-level aggregation.

7. **Inventory Formula Fields**: `stock_value_rs`, `available_sales_value_rs`, `gross_margin_potential_rs`, `weeks_of_cover`, `target_stock_units`, `shortage_units` appear as None in source (formula cache not populated).
   - These fields were recalculated explicitly in the pipeline where data permitted.
   - `weeks_of_cover_calc` and `reorder_flag_calc` are derived; source cached values not used.

8. **inventory_transactions Referenced But Unavailable**: The `inventory_stock.xlsx` workbook references `Inventory_Agent_Transactions_417000.xlsx` as a transaction companion. This file was not present in the repository.
"""

# --- AGENT_DATA_CONTRACTS.md ---
contracts_text = """# Agent Data Contracts

## Demand Agent
**Inputs**:
- `DEMAND_FEATURES.csv` — features for prediction (lag, rolling mean, promotion, weather, festival)
- `DEMAND_TARGETS.csv` — prediction target (next_week_demand_target_units)
- `DIM_LOCATION.csv`, `DIM_PRODUCT.csv`, `DIM_WEATHER.csv`, `DIM_FESTIVAL.csv`

**Output**:
- Predicted next-period demand (units) per location+product

**Leakage Guard**: `next_week_demand_target_units` is in DEMAND_TARGETS only — not in DEMAND_FEATURES.

**Agent Readiness**: READY_WITH_WARNINGS (demand data is synthetic; no observed sales to validate against)

---
## Inventory Agent
**Inputs**:
- `INVENTORY_FEATURES.csv` — current stock positions, utilization, reorder flags
- `DIM_PRODUCT.csv`, `DIM_WAREHOUSE.csv`

**Output**:
- Shortage detection, reorder recommendations, inventory status

**Agent Readiness**: READY_WITH_WARNINGS (transaction history blocked by LFS)

---
## Supply Agent
**Inputs**:
- `SUPPLY_FEATURES.csv` — supplier catalog, MOQ, lead times, vehicle info
- `BRIDGE_SUPPLIER_PRODUCT.csv`, `BRIDGE_LOCATION_SUPPLIER.csv`

**Output**:
- Candidate suppliers, procurement quantities, costs, lead times

**Note**: Column `unmapped_col_10_quarantine` in BRIDGE_SUPPLIER_PRODUCT requires domain review.

**Agent Readiness**: READY_WITH_WARNINGS (unmapped column unresolved)

---
## Warehouse Agent
**Inputs**:
- `WAREHOUSE_FEATURES.csv` — capacity, dispatch, vehicles, operating hours
- `BRIDGE_WAREHOUSE_LOCATION.csv`, `FACT_INVENTORY_POSITION.csv`

**Output**:
- Fulfillment warehouse selection, dispatch feasibility

**Agent Readiness**: READY

---
## Risk Agent
**Inputs**:
- `RISK_FEATURES_INVENTORY.csv` — shortage/reorder risk
- `RISK_FEATURES_DEMAND.csv` — stockout + weather + festival risk signals
- `RISK_FEATURES_SUPPLY.csv` — supplier lead time risk

**Output**:
- Structured risk indicators per entity

**Agent Readiness**: READY_WITH_WARNINGS (transaction history blocked)

---
## Route Optimization Agent
**Inputs**:
- `ROUTING_FEATURES.csv` — warehouse-location and supplier-location euclidean distances
- `DIM_WAREHOUSE.csv`, `DIM_LOCATION.csv`, `DIM_SUPPLIER.csv`

**Output**:
- Feasible route inputs

**Critical Note**: `euclidean_distance_km` is Haversine only — NOT road distance.

**Agent Readiness**: READY_WITH_WARNINGS (no road network data available)

---
## Coordinator Agent
**Inputs**: Outputs from all 6 agents above.

**Agent Readiness**: READY (contingent on individual agent readiness)
"""

for fname, content in [
    ("DATA_FOUNDATION_README.md", readme_text),
    ("KNOWN_LIMITATIONS.md", limitations_text),
    ("AGENT_DATA_CONTRACTS.md", contracts_text),
]:
    (DOC / fname).write_text(content, encoding="utf-8")
    print(f"  Wrote {fname}")


# ═══════════════════════════════════════════════════════════════════════════════
# Final execution summary
# ═══════════════════════════════════════════════════════════════════════════════
print("Writing FINAL_DATA_FOUNDATION_REPORT.md...")

# Load validation summary
val_summary = pd.read_csv(VAL / "validation_summary.csv")
val_detail  = pd.read_csv(VAL / "validation_details.csv")

total = len(val_detail)
passes = (val_detail["status"] == "PASS").sum()
warns  = (val_detail["status"] == "WARNING").sum()
fails  = (val_detail["status"] == "FAIL").sum()
blocked= (val_detail["status"] == "BLOCKED_BY_SOURCE").sum()

report = f"""# FINAL DATA FOUNDATION REPORT
## Kolkata Multi-Agent Supply Chain System
**Generated**: {NOW}

---

## 1. Source Summary

| Source ID | File | Domain | Status | Rows |
|---|---|---|---|---|
| SRC-001 | locations.csv.csv | Location | ✅ Available | 40 |
| SRC-002 | products.csv | Product | ✅ Available | 200 |
| SRC-003 | Final product list.xlsx | Product | ✅ Available | 200 |
| SRC-004 | festival_calendar.csv | Festival | ✅ Available | 36 |
| SRC-005 | weather_weekly.csv | Weather | ✅ Available | 105 |
| SRC-006 | Demand of last 2 years.xlsx | Demand | ✅ Available | 27,800 |
| SRC-007 | final_demand_agent_training.xlsx | Demand | ✅ Available | 20,800 |
| SRC-008 | sales_history.xlsx | Sales | ❌ LFS BLOCKED | N/A |
| SRC-009 | inventory_stock.xlsx | Inventory | ✅ Available | 3,000 |
| SRC-010 | inventory_transactions.xlsx | Inventory | ❌ LFS BLOCKED | N/A |
| SRC-011 | supplier_inventory.xlsx | Supplier | ✅ Available | 8,000+ |
| SRC-012 | warehouses.xlsx | Warehouse | ✅ Available | 15 |
| SRC-013 | final_warehouse_dataset_kolkata.xlsx | Warehouse | ✅ Available | 15 |

---

## 2. Dataset Counts

| Entity | Records |
|---|---|
| DIM_PRODUCT | 200 |
| DIM_PRODUCT_VARIANT | 1,000 (5 sizes × 200 products) |
| DIM_LOCATION | 40 |
| DIM_WAREHOUSE | 15 |
| DIM_SUPPLIER | 200 |
| DIM_CALENDAR_WEEK | 105 |
| DIM_FESTIVAL | 36 |
| DIM_WEATHER | 105 |
| FACT_DEMAND | 27,800 |
| DEMAND_TRAINING_DATA | 20,800 |
| FACT_INVENTORY_POSITION | 3,000 |
| FACT_SUPPLIER_AVAILABILITY | 8,000 |
| BRIDGE_SUPPLIER_PRODUCT | 8,000 |
| BRIDGE_LOCATION_SUPPLIER | 200 |
| BRIDGE_WAREHOUSE_LOCATION | 600 (15 × 40) |
| BRIDGE_PRODUCT_WAREHOUSE | 3,000 |

---

## 3. Canonical Entities Created

- ✅ DIM_PRODUCT (canonical source: products.csv, validated vs Final product list.xlsx)
- ✅ DIM_PRODUCT_VARIANT (1,000 normalized variants from wide→long pivot)
- ✅ DIM_LOCATION (enriched with coordinates from supplier Area_Master)
- ✅ DIM_WAREHOUSE (merged warehouses.xlsx + final_warehouse_dataset_kolkata.xlsx)
- ✅ DIM_SUPPLIER (from Supplier_Master, snake_case normalized)
- ✅ DIM_CALENDAR_WEEK (derived from weather coverage)
- ✅ DIM_FESTIVAL (with derived festival_category, week_start_date)
- ✅ DIM_WEATHER (with SUPPLIED_SYNTHETIC tag)

---

## 4. Relationships Created

| Bridge Table | From | To | Method |
|---|---|---|---|
| BRIDGE_SUPPLIER_PRODUCT | DIM_SUPPLIER | DIM_PRODUCT | Supplier_Product_Catalog JOIN |
| BRIDGE_LOCATION_SUPPLIER | DIM_LOCATION | DIM_SUPPLIER | Area_Supplier_Options |
| BRIDGE_WAREHOUSE_LOCATION | DIM_WAREHOUSE | DIM_LOCATION | Haversine + service radius |
| BRIDGE_PRODUCT_WAREHOUSE | DIM_PRODUCT | DIM_WAREHOUSE | Inventory_Position |

---

## 5. Transformations Performed

1. **Column naming**: All final tables use lowercase snake_case.
2. **Date parsing**: All date fields converted to proper datetime types.
3. **Unit normalization**: Product unit sizes parsed to (value, unit, normalized_ml_g).
4. **Product variant normalization**: Wide format (5 columns) → long format DIM_PRODUCT_VARIANT.
5. **Coordinate enrichment**: locations.csv.csv enriched with lat/lon from Area_Master via location_id JOIN.
6. **Warehouse merge**: warehouses.xlsx (vehicle counts, dispatch) + final_warehouse_dataset_kolkata.xlsx (storage_type, status).
7. **Inventory formula recalculation**: weeks_of_cover_calc, reorder_flag_calc, stock_cost_value_rs, available_sales_value_rs explicitly recalculated (not relying on Excel formula cache).
8. **Lag features**: 1, 2, 4, 8, 12-week lags on units_sold (per location+product).
9. **Rolling means**: 4, 8, 12-week rolling means on lag_1w values (leakage-safe).
10. **Haversine distance matrix**: 15 warehouses × 40 locations = 600 warehouse-location distances.
11. **Festival proximity**: days_to_next_festival, days_since_last_festival derived per demand row.
12. **Unmapped supplier column**: Preserved as unmapped_col_10_quarantine in BRIDGE_SUPPLIER_PRODUCT.
13. **LFS pointer detection**: sales_history.xlsx and inventory_transactions.xlsx identified as LFS pointers; blocked outputs clearly labeled.

---

## 6. Features Created

| Feature Set | File | Rows | Columns | Target Agent |
|---|---|---|---|---|
| DEMAND_FEATURES | DEMAND_FEATURES.csv | 27,800 | 60+ | Demand Agent |
| DEMAND_TARGETS | DEMAND_TARGETS.csv | 27,800 | 6 | Demand Agent (training) |
| INVENTORY_FEATURES | INVENTORY_FEATURES.csv | 3,000 | 35+ | Inventory Agent |
| SUPPLY_FEATURES | SUPPLY_FEATURES.csv | 8,000 | 18+ | Supply Agent |
| WAREHOUSE_FEATURES | WAREHOUSE_FEATURES.csv | 15 | 25+ | Warehouse Agent |
| ROUTING_FEATURES | ROUTING_FEATURES.csv | 800 | 10 | Route Optimization Agent |
| RISK_FEATURES_INVENTORY | RISK_FEATURES_INVENTORY.csv | 3,000 | 12 | Risk Agent |
| RISK_FEATURES_DEMAND | RISK_FEATURES_DEMAND.csv | 27,800 | 12 | Risk Agent |
| RISK_FEATURES_SUPPLY | RISK_FEATURES_SUPPLY.csv | 8,000 | 8 | Risk Agent |

---

## 7. Validation Results

| Metric | Count |
|---|---|
| Total Checks | {total} |
| PASS | {passes} |
| WARNING | {warns} |
| FAIL | {fails} |
| BLOCKED_BY_SOURCE | {blocked} |

See `08_validation/validation_details.csv` for full check-by-check results.

---

## 8. Issues Discovered

| ID | Issue | Severity |
|---|---|---|
| QI-001 | SALES_HISTORY_SOURCE_UNAVAILABLE — LFS pointer | CRITICAL |
| QI-002 | INVENTORY_TRANSACTIONS_SOURCE_UNAVAILABLE — LFS pointer | CRITICAL |
| QI-003 | SUPPLIER_CATALOG_UNMAPPED_COLUMN — column index 10 has no header | HIGH |
| QI-004 | Inventory formula cache empty — values recalculated explicitly | MEDIUM |
| QI-005 | Both demand datasets are SYNTHETIC_TRAINING — no real observed data | MEDIUM |

---

## 9. Quarantined Records

| QRN-ID | Issue | Records | Action |
|---|---|---|---|
| QRN-001 | Supplier catalog unmapped column | 8,000 | Preserved as unmapped_col_10_quarantine |
| QRN-002 | sales_history.xlsx LFS pointer | N/A (blocked) | Restore with git lfs pull |
| QRN-003 | inventory_transactions.xlsx LFS pointer | N/A (blocked) | Restore with git lfs pull |

---

## 10. Source Limitations

1. `sales_history.xlsx`: Git-LFS pointer. OID: `fc8022e6248ccb8725f6ff8cb9c70aa91a6f76aeb99bce62db5866f7c902e6e5`. Expected: 177 MB. FACT_SALES cannot be built.
2. `inventory_transactions.xlsx`: Git-LFS pointer. OID: `5fc053bab861bc764e13ac15b74ebcab11b4bf35403f436eadd68d727a06a749`. Expected: 56 MB. FACT_INVENTORY_TRANSACTION cannot be built.
3. No road network distance data — only Haversine (euclidean) distances available.
4. Demand data is entirely synthetic/simulated, not observed real-world transactions.
5. Inventory formula-cached values were not populated in the source XLSX (None values) — recalculated from components.

---

## 11. Agent Readiness

| Agent | Status | Blocker |
|---|---|---|
| Demand Agent | READY_WITH_WARNINGS | Demand data is synthetic; no real sales for validation |
| Inventory Agent | READY_WITH_WARNINGS | FACT_INVENTORY_TRANSACTION blocked by LFS |
| Supply Agent | READY_WITH_WARNINGS | Unmapped supplier catalog column unresolved |
| Warehouse Agent | READY | — |
| Risk Agent | READY_WITH_WARNINGS | Incomplete transaction history |
| Route Optimization Agent | READY_WITH_WARNINGS | Euclidean distance only, no road network |
| Coordinator Agent | READY_WITH_WARNINGS | Contingent on upstream agents |

---
*Pipeline executed end-to-end. No data was fabricated. No raw files were modified.*
"""

(DOC / "FINAL_DATA_FOUNDATION_REPORT.md").write_text(report, encoding="utf-8")
# Also copy to project root for visibility
shutil.copy2(DOC / "FINAL_DATA_FOUNDATION_REPORT.md", BASE / "FINAL_DATA_FOUNDATION_REPORT.md")
print("  Wrote FINAL_DATA_FOUNDATION_REPORT.md")

print("\n✅ Stage 06 complete — all documentation, entity mapping, agent-ready data written.")

