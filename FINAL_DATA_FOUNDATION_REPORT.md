# FINAL DATA FOUNDATION REPORT
## Kolkata Multi-Agent Supply Chain System
**Generated / Updated**: 2026-09-21 17:52 UTC

---

## 1. Source Summary

| Source ID | File | Domain | Status | Rows |
|---|---|---|---|---|
| SRC-001 | locations.csv.csv | Location | Available | 40 |
| SRC-002 | products.csv | Product | Available | 200 |
| SRC-003 | Final product list.xlsx | Product | Available | 200 |
| SRC-004 | festival_calendar.csv | Festival | Available | 36 |
| SRC-005 | weather_weekly.csv | Weather | Available | 105 |
| SRC-006 | Demand of last 2 years.xlsx | Demand | Available | 27,800 |
| SRC-007 | final_demand_agent_training.xlsx | Demand | Available | 20,800 |
| SRC-008 | SELL_of_past_2_years_COMBINED.csv | Sales | Available (Replaced LFS pointer) | 448,000 |
| SRC-009 | inventory_stock.xlsx | Inventory | Available | 3,000 |
| SRC-010 | Inventory_Transactions_417000_Reconstructed.csv | Inventory | Available (Replaced LFS pointer) | 417,000 |
| SRC-011 | supplier_inventory.xlsx | Supplier | Available | 8,000+ |
| SRC-012 | warehouses.xlsx | Warehouse | Available | 15 |
| SRC-013 | final_warehouse_dataset_kolkata.xlsx | Warehouse | Available | 15 |
| SRC-014 | Warehouse_Picker_IDs_Only.csv | Warehouse | Available (New Mapping) | 750 |

---

## 2. Dataset Counts

### 2.1 Staging Layer (data/03_staging/)
| Staged File | Records | Source |
|---|---|---|
| stg_locations.csv | 40 | locations.csv.csv |
| stg_products.csv | 200 | products.csv |
| stg_final_product_list_master.csv | 200 | Final product list.xlsx / product_master |
| stg_category_summary.csv | 20 | Final product list.xlsx / category_summary |
| stg_festival_calendar.csv | 36 | estival_calendar.csv |
| stg_weather_weekly.csv | 105 | weather_weekly.csv |
| stg_demand_history.csv | 27,800 | Demand of last 2 years.xlsx / demand_training_data |
| stg_demand_training.csv | 20,800 | inal_demand_agent_training_2_years_kolkata (1).xlsx |
| stg_sales_history.csv | 448,000 | SELL_of_past_2_years_COMBINED.csv |
| stg_inventory_position.csv | 3,000 | inventory_stock.xlsx / Inventory_Position |
| stg_inventory_control.csv | 3,000 | inventory_stock.xlsx / Inventory_Control |
| stg_inventory_valuation.csv | 3,000 | inventory_stock.xlsx / Inventory_Valuation |
| stg_inventory_shelf_master.csv | 600 | inventory_stock.xlsx / Shelf_Master |
| stg_inventory_product_shelf.csv | 3,000 | inventory_stock.xlsx / Product_Shelf_Assignment |
| stg_inventory_transactions.csv | 417,000 | Inventory_Transactions_417000_Reconstructed.csv |
| stg_supplier_master.csv | 200 | supplier_inventory.xlsx / Supplier_Master |
| stg_supplier_area_master.csv | 40 | supplier_inventory.xlsx / Area_Master |
| stg_supplier_area_options.csv | 200 | supplier_inventory.xlsx / Area_Supplier_Options |
| stg_supplier_product_catalog.csv | 8,000 | supplier_inventory.xlsx / Supplier_Product_Catalog |
| stg_warehouses_primary.csv | 15 | warehouses.xlsx / warehouse |
| stg_warehouses_kolkata.csv | 15 | inal_warehouse_dataset_kolkata.xlsx / warehouse |
| stg_warehouse_pickers.csv | 750 | Warehouse_Picker_IDs_Only.csv |

### 2.2 Standardized Layer (data/04_standardized/)
| Standardized File | Records | Cleaning & Transformation Highlights |
|---|---|---|
| std_locations.csv | 40 | Validated IDs, trimmed names, enriched with lat/lon |
| std_products.csv | 200 | Normalized snake_case, verified 20 categories x 10 items |
| std_product_variants.csv | 1,000 | Unpivoted 5 sizes to normalized variant entity with base units |
| std_festival_calendar.csv | 36 | ISO dates, derived Monday-week start, inferred categories |
| std_weather_weekly.csv | 105 | Parsed metrics, non-negative rainfall, 0-100% humidity |
| std_calendar_week.csv | 105 | Normalized YYYYMMDD week keys, week number, season |
| std_warehouses.csv | 15 | Consolidated facility specs, dispatch, and vehicle counts |
| std_warehouse_pickers.csv | 750 | Mapped WH-XXX to canonical WH-KOL-XXX format |
| std_supplier_master.csv | 200 | Standardized MOQ, lead times, max limits, vehicle fleet |
| std_supplier_area_options.csv | 200 | Standardized area-to-supplier options and rankings |
| std_supplier_product_catalog.csv | 8,000 | Preserved unmapped column 10 in quarantine |
| std_inventory_position.csv | 3,000 | Recalculated weeks_of_cover, 
eorder_flag, 	arget_stock, shortage |
| std_inventory_shelf.csv | 600 | Standardized shelf capacity and space utilization % |
| std_inventory_transactions.csv | 417,000 | Fully typed inventory transactions with direction & type |
| std_demand_history.csv | 27,800 | Fully typed demand history with promotions, holidays, weather |
| std_demand_training.csv | 20,800 | Standardized secondary training dataset |
| std_sales_history.csv | 448,000 | True historical sales transactions across 40 regions x 200 products |

### 2.3 Curated Canonical Layer (data/06_curated/)
| Entity | Records | Status |
|---|---|---|
| DIM_PRODUCT | 200 | Active |
| DIM_PRODUCT_VARIANT | 1,000 | Active |
| DIM_LOCATION | 40 | Active |
| DIM_WAREHOUSE | 15 | Active |
| DIM_PICKER | 750 | Active (New) |
| DIM_SUPPLIER | 200 | Active |
| DIM_CALENDAR_WEEK | 105 | Active |
| DIM_FESTIVAL | 36 | Active |
| DIM_WEATHER | 105 | Active |
| FACT_SALES | 448,000 | Active (Unblocked) |
| FACT_INVENTORY_TRANSACTION | 417,000 | Active (Unblocked) |
| FACT_DEMAND | 27,800 | Active |
| DEMAND_TRAINING_DATA | 20,800 | Active |
| FACT_INVENTORY_POSITION | 3,000 | Active |
| FACT_SUPPLIER_AVAILABILITY | 8,000 | Active |
| BRIDGE_WAREHOUSE_PICKER | 750 | Active (New) |
| BRIDGE_SUPPLIER_PRODUCT | 8,000 | Active |
| BRIDGE_LOCATION_SUPPLIER | 200 | Active |
| BRIDGE_WAREHOUSE_LOCATION | 600 | Active |
| BRIDGE_PRODUCT_WAREHOUSE | 3,000 | Active |

---

## 3. Validation Results

| Metric | Count |
|---|---|
| Total Checks | 62 |
| PASS | 60 |
| WARNING | 2 (1 weather interval, 1 unmapped supplier col) |
| FAIL | 0 |
| BLOCKED_BY_SOURCE | 0 (All previous blockers resolved!) |

---

## 4. Agent Readiness

| Agent | Status | Notes |
|---|---|---|
| Demand Agent | READY | Benchmarked against 448,000 actual sales records |
| Inventory Agent | READY | 417,000 transaction history unblocked; positions recalculated |
| Warehouse Agent | READY | Picker mapping integrated (50 pickers/warehouse) |
| Risk Agent | READY | Shortage, lead time, stockout, and velocity risk inputs available |
| Supply Agent | READY_WITH_WARNINGS | Unmapped catalog column preserved in quarantine |
| Route Optimization Agent | READY_WITH_WARNINGS | Euclidean Haversine distances available; no road network |
| Coordinator Agent | READY | All agent feeds operational |
