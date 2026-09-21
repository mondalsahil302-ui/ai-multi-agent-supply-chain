# FINAL DATA FOUNDATION REPORT
## Kolkata Multi-Agent Supply Chain System
**Generated**: 2026-09-21T13:26:30.071015+00:00

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
| Total Checks | 49 |
| PASS | 45 |
| WARNING | 2 |
| FAIL | 0 |
| BLOCKED_BY_SOURCE | 2 |

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
