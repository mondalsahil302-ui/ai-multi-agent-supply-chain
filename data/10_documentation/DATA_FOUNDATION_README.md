# Data Foundation — AI Multi-Agent Supply Chain (Kolkata)

## Overview
This folder contains the complete data foundation pipeline outputs for the Kolkata Multi-Agent Supply Chain system. All layers were built by the automated ETL pipeline and are traceable from raw source to agent-ready output.

## Pipeline Layers
| Layer | Folder | Contents |
|---|---|---|
| 01 | `01_raw/` | Immutable copies of source files |
| 02 | `02_profile/` | Data profiling CSVs (schema, columns, nulls, duplicates, geographic, temporal) |
| 03 | `03_staging/` | 21 staged source table/sheet extractions with audit metadata (_source_file, _source_sheet, _staged_at, _row_id) |
| 04 | `04_standardized/` | 16 cleaned, typed, unit-normalized, formula-recalculated datasets (Part H transformations) |
| 05 | `05_entity_mapping/` | entity_mapping.csv + entity_mapping.json |
| 06 | `06_curated/` | All canonical DIM/FACT/BRIDGE tables (Part E dimensional model) |
| 07 | `07_features/` | Agent-specific feature tables (Part N feature engineering) |
| 08 | `08_validation/` | Validation summary + details (Part O & P multi-level validation) |
| 09 | `09_agent_ready/` | Final copy for agent consumption |
| 10 | `10_documentation/` | All documentation (dictionary, contracts, limitations, lineage, report) |
| — | `data_quarantine/` | Quarantined unresolved records |

## Staging Layer (`data/03_staging/`)
Contains 21 extracted raw tabular sheets preserved with exact raw data values and audit metadata:
- `stg_locations.csv`, `stg_products.csv`, `stg_final_product_list_master.csv`, `stg_category_summary.csv`
- `stg_festival_calendar.csv`, `stg_weather_weekly.csv`, `stg_demand_history.csv`, `stg_demand_training.csv`
- `stg_inventory_position.csv`, `stg_inventory_control.csv`, `stg_inventory_valuation.csv`, `stg_inventory_shelf_master.csv`, `stg_inventory_product_shelf.csv`
- `stg_supplier_master.csv`, `stg_supplier_area_master.csv`, `stg_supplier_area_options.csv`, `stg_supplier_product_catalog.csv`
- `stg_warehouses_primary.csv`, `stg_warehouses_kolkata.csv`
- `stg_sales_history_lfs_pointer.csv`, `stg_inventory_transactions_lfs_pointer.csv`

## Standardized Layer (`data/04_standardized/`)
Applies Part H transformations per source entity before dimensional modeling:
- `std_locations.csv`: Trimmed, validated IDs, enriched with lat/lon
- `std_products.csv`: Standardized lowercase snake_case, verified 200 products across 20 categories
- `std_product_variants.csv`: Normalized long entity with parsed physical units (`unit_size_value`, `unit_size_unit`, `normalized_quantity_value`, `normalized_quantity_unit`)
- `std_festival_calendar.csv`: ISO dates, derived Monday-based week keys, inferred festival categories
- `std_weather_weekly.csv`: Typed floats/dates, validated non-negative rainfall and 0-100% humidity
- `std_calendar_week.csv`: Deterministic week keys (`YYYYMMDD`), week number, year, season
- `std_warehouses.csv`: Merged facility specs, operating hours, dispatch capacities, and vehicle fleets
- `std_supplier_master.csv`: Cleaned MOQ, maximum order/ship limits, vehicle capacity, lead times
- `std_supplier_area_options.csv`: Standardized area-to-supplier options and service availability
- `std_supplier_product_catalog.csv`: Preserved unmapped column 10 in quarantine
- `std_inventory_position.csv`: Explicitly recalculated `weeks_of_cover_calc`, `reorder_flag_calc`, `target_stock_units`, `shortage_units`, `stock_cost_value_rs`, `available_sales_value_rs`
- `std_inventory_shelf.csv`: Standardized warehouse shelf capacities and utilization
- `std_demand_history.csv`: 27,800 rows with parsed dates, numerical conversions, and standard flags
- `std_demand_training.csv`: 20,800 rows secondary training dataset
- `std_sales_history_unavailable.csv` & `std_inventory_transactions_unavailable.csv`: LFS blockage documentation

## Curated Canonical Entities (`data/06_curated/`)
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
