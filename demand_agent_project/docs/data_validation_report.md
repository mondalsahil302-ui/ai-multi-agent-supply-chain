# Data Audit & Validation Report (Phase 2)
Generated at: 2026-11-16
Region Scope: `KOL-LOC-001` (Lake Gardens)

---

## 1. Executive Data Quality Assessment
- **Status:** **VALIDATED & PRODUCTION READY**
- **Completeness:** 100% of required series (200 / 200) present with zero missing weeks.
- **Integrity:** Zero duplicate records, zero negative units, zero null units.
- **Coverage:** Exact 150 completed weekly steps (2024-01-01 to 2026-11-08).

---

## 2. Logical Collection Audits

### 2.1 Historical Demand (`historical_demand`)
| Metric | Value | Expected / Rule | Status |
|---|---|---|:---:|
| Total Documents | 30,000 | 30,000 | PASS |
| Products in Region | 200 | 200 | PASS |
| Date Span | 2024-01-01 to 2026-11-08 | 150 weeks | PASS |
| Weeks per Product (min/max) | 150 / 150 | Exactly 150 | PASS |
| Duplicate (Product x Week) | 0 | 0 | PASS |
| Negative / NaN Units Sold | 0 / 0 | 0 | PASS |
| Products with Date Gaps | 0 | 0 | PASS |
| Stockout Weeks | 0 | Flagged (censored) | PASS |
| Partial Weeks | 200 | Flagged | PASS |
| Splits Distribution | {'synthetic_extension': 2200, 'synthetic_partial_as_of_2026-11-11': 200, 'test': 2400, 'train': 21000, 'validation': 4200} | Train / Val / Test | PASS |

### 2.2 Weather Data (`weather_history` & `weather_forecasts`)
| Dataset | Document Count | Date Range | Freshness / Quality |
|---|---|---|---|
| Weather History | 150 weeks | 2024-01-01 to 2026-11-08 | Full continuity over demand history |
| Weather Forecasts | 7 daily snapshots | 2026-11-11 to 2026-11-17 | Active rolling forecast window |

### 2.3 Festival Calendar (`festival_calendar`)
- **Total Registered Events:** 24 events
- **Coverage Horizon:** 2026-08-26 to 2026-11-24
- **Event Types Recorded:** festival, national_holiday, observance, regional_holiday

### 2.4 Entity Masters (`product_master` & `region_master`)
- **Total Products:** 200 (200 MAPPED, 0 unmapped)
- **Categories:** 20 distinct retail categories (Baby Care & Family Care, Biscuits & Cookies, Bread & Bakery, Chips & Namkeen, Chocolates & Confectionery...)
- **Total Regions in Master:** 40
- **Active Operational Region:** `KOL-LOC-001` (Lake Gardens)

---

## 3. Database Indexes Audit & Optimization Plan

| Collection | Current Index Count | Unique Index Present? | Recommended Optimization |
|---|:---:|:---:|---|
| `historical_demand` | 2 | YES | `_id_: {'_id': 1}; uq_historical_demand: {'region_id': 1, 'product_id': 1, 'week_start_date': 1}` |
| `weather_history` | 2 | YES | `_id_: {'_id': 1}; uq_region_weather_week: {'region_id': 1, 'week_start_date': 1}` |
| `weather_forecasts` | 2 | YES | `_id_: {'_id': 1}; uq_region_forecast_run_day: {'region_id': 1, 'forecast_date': 1, 'forecast_retrieved_at': 1}` |
| `festival_calendar` | 2 | YES | `_id_: {'_id': 1}; uq_region_festival_date_name: {'region_id': 1, 'festival_date': 1, 'festival_name': 1}` |
| `product_master` | 3 | YES | `_id_: {'_id': 1}; uq_product_id: {'product_id': 1}` |
| `region_master` | 2 | YES | `_id_: {'_id': 1}; uq_region_id: {'region_id': 1}` |
| `forecast_results` | 6 | YES | `_id_: {'_id': 1}; ix_region_product_week_forecast: {'region_id': 1, 'product_id': 1, 'target_week': 1, 'forecast_generation_timestamp': -1}` |
| `run_metadata` | 3 | YES | `_id_: {'_id': 1}; idx_run_metadata_run_id_unique: {'run_id': 1}` |
| `model_registry` | 2 | NO | `_id_: {'_id': 1}; status_1: {'status': 1}` |

---

## 4. Warehouse Entity Resolution
In accordance with Layer 3 requirements, warehouse identification is formalized:
- **`WH-001`** (South City Mall Warehouse, Jadavpur/Lake Gardens) maps 1:1 to spatial `region_id`: **`KOL-LOC-001`**.
- Warehouses `WH-002` through `WH-015` are defined in the master registry as out-of-scope for the Lake Gardens pilot, correctly producing **"NOT READY"** status when evaluated by the Data Readiness Gate.
