# Data Dictionary
## Kolkata Multi-Agent Supply Chain System
**Generated**: 2026-09-21 14:38 UTC  
**Total tables**: 18  
**Total fields**: 256

> **Key conventions**
> - All final tables use `lowercase_snake_case` column names.
> - `pipeline_timestamp` is always UTC ISO-8601.
> - `PK` = Primary Key, `FK→<table>` = Foreign Key reference.
> - `TARGET` = model prediction target — **must not be used as a feature**.
> - `QUARANTINE` = field with unresolved semantics — do not use in production without domain review.
> - `SUPPLIED_SYNTHETIC` = data generated for simulation, not real-world observations.
> - Euclidean distances are **Haversine great-circle km** — never road distance.

---

## Table of Contents

- **Dimension Tables**
  - [DIM_PRODUCT](#dim-product)
  - [DIM_PRODUCT_VARIANT](#dim-product-variant)
  - [DIM_LOCATION](#dim-location)
  - [DIM_WAREHOUSE](#dim-warehouse)
  - [DIM_SUPPLIER](#dim-supplier)
  - [DIM_CALENDAR_WEEK](#dim-calendar-week)
  - [DIM_FESTIVAL](#dim-festival)
  - [DIM_WEATHER](#dim-weather)
- **Fact Tables**
  - [FACT_DEMAND](#fact-demand)
  - [FACT_INVENTORY_POSITION](#fact-inventory-position)
  - [FACT_SUPPLIER_AVAILABILITY](#fact-supplier-availability)
- **Bridge / Mapping Tables**
  - [BRIDGE_SUPPLIER_PRODUCT](#bridge-supplier-product)
  - [BRIDGE_LOCATION_SUPPLIER](#bridge-location-supplier)
  - [BRIDGE_WAREHOUSE_LOCATION](#bridge-warehouse-location)
  - [BRIDGE_PRODUCT_WAREHOUSE](#bridge-product-warehouse)
- **Feature Sets**
  - [DEMAND_FEATURES](#demand-features)
  - [DEMAND_TARGETS](#demand-targets)
  - [ROUTING_FEATURES](#routing-features)
- **Blocked Outputs (LFS)**
- [Blocked Outputs](#blocked-outputs)

---

## Dimension Tables

### DIM_PRODUCT

**Source layer**: `06_curated/DIM_PRODUCT.csv`  
**Row count**: 200  
**Primary key**: `product_id`  
**Foreign keys**: `category_code`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `product_id` | STRING | ❌ | PK | Unique product identifier. Format: <CATEGORY_CODE>-<NNN>. e.g. ICE-001, BEV-005. | `ICE-001` |
| `category_code` | STRING | ❌ | FK→category | Short category code. 2–4 uppercase letters. e.g. ICE, BEV, DAI. | `ICE` |
| `category_name` | STRING | ❌ | — | Full human-readable category name. | `Ice Cream & Frozen Desserts` |
| `product_name` | STRING | ❌ | — | Full commercial product name including brand prefix. | `Amul Vanilla Ice Cream` |
| `brand` | STRING | ❌ | — | Brand name of the product. Used for grouping and supplier matching. | `Amul` |
| `quality_level` | STRING | ❌ | — | Product tier: Standard or Premium. | `Standard` |
| `unit_type` | STRING | ❌ | — | Physical unit dimension: ml (volume) or g (mass). Never mix across dimensions. | `ml` |
| `canonical_source` | STRING | ❌ | — | Source file chosen as canonical: products.csv (reconciled against Final product list.xlsx). | `products.csv` |
| `source_file` | STRING | ❌ | — | Provenance: source file(s) this record was built from. | `products.csv (reconciled against Final product list.xlsx)` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC timestamp when this record was written by the pipeline. | `2026-09-21T13:24:00Z` |

---

### DIM_PRODUCT_VARIANT

**Source layer**: `06_curated/DIM_PRODUCT_VARIANT.csv`  
**Row count**: 1,000  
**Primary key**: `product_variant_id`  
**Foreign keys**: `product_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `product_variant_id` | STRING | ❌ | PK | Deterministic variant key. Format: <product_id>-<SIZE><UNIT>. e.g. ICE-001-80ML. | `ICE-001-80ML` |
| `product_id` | STRING | ❌ | FK→DIM_PRODUCT | Parent product identifier. Joins to DIM_PRODUCT.product_id. | `ICE-001` |
| `variant_index` | INTEGER | ❌ | — | Ordinal position of this variant within the product (1–5). 1 = smallest size. | `1` |
| `unit_size_raw` | STRING | ❌ | — | Original size string exactly as supplied in source. e.g. '80 ml', '500 g', '1 L'. | `80 ml` |
| `unit_size_value` | FLOAT | ✅ | — | Numeric part of the unit size. e.g. 80 for '80 ml'. | `80` |
| `unit_size_unit` | STRING | ✅ | — | Unit string extracted from size. ml, l, g, kg, piece, dozen. | `ml` |
| `normalized_quantity_value` | FLOAT | ✅ | — | Canonical quantity in base unit. ml→ml, l→ml×1000, kg→g×1000. | `80` |
| `normalized_quantity_unit` | STRING | ✅ | — | Base unit after normalization: ml or g. Never cross-converts volume↔mass. | `ml` |
| `cost_price_rs` | FLOAT | ✅ | — | Cost price (INR) for this specific variant size. | `36` |
| `selling_price_rs` | FLOAT | ✅ | — | Selling price (INR) for this specific variant size. | `41` |
| `source_file` | STRING | ❌ | — | Provenance. | `products.csv` |
| `source_record` | STRING | ❌ | — | Row-level provenance including product_id and column name. | `product_id=ICE-001, unit_size_1` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### DIM_LOCATION

**Source layer**: `06_curated/DIM_LOCATION.csv`  
**Row count**: 40  
**Primary key**: `location_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `location_id` | STRING | ❌ | PK | Canonical Kolkata region identifier. Format: KOL-LOC-<NNN>. | `KOL-LOC-001` |
| `region_of_kolkata` | STRING | ❌ | — | Human-readable neighbourhood/area name within Kolkata. | `Lake Gardens` |
| `city` | STRING | ✅ | — | City name. All records = 'Kolkata'. | `Kolkata` |
| `latitude` | FLOAT | ✅ | — | WGS-84 latitude of the approximate area centroid. Range: 22.3–22.7. | `22.5065` |
| `longitude` | FLOAT | ✅ | — | WGS-84 longitude of the approximate area centroid. Range: 88.2–88.5. | `88.3554` |
| `location_name` | STRING | ❌ | — | Alias for region_of_kolkata. Same value. | `Lake Gardens` |
| `source_file` | STRING | ❌ | — | Provenance: primary + enrichment source. | `locations.csv.csv + supplier_inventory.xlsx/Area_Master` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### DIM_WAREHOUSE

**Source layer**: `06_curated/DIM_WAREHOUSE.csv`  
**Row count**: 15  
**Primary key**: `warehouse_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `warehouse_id` | STRING | ❌ | PK | Unique warehouse identifier. Format: WH-KOL-<NNN>. | `WH-KOL-001` |
| `warehouse_name` | STRING | ❌ | — | Full descriptive warehouse name. | `South City Mall Warehouse` |
| `area` | STRING | ❌ | — | Kolkata neighbourhood where the warehouse is located. | `Jadavpur` |
| `city` | STRING | ❌ | — | City. All records = 'Kolkata'. | `Kolkata` |
| `latitude` | FLOAT | ❌ | — | WGS-84 latitude of warehouse. Range: 22.3–22.7. | `22.5014` |
| `longitude` | FLOAT | ❌ | — | WGS-84 longitude of warehouse. Range: 88.2–88.5. | `88.36175` |
| `capacity_units` | INTEGER | ❌ | — | Maximum total stock units the warehouse can hold. | `20000` |
| `weekday_open_time` | STRING | ❌ | — | Opening time on weekdays. Format: HH:MM (24h). | `08:00` |
| `weekday_close_time` | STRING | ❌ | — | Closing time on weekdays. Format: HH:MM (24h). | `22:00` |
| `weekend_open_time` | STRING | ❌ | — | Opening time on weekends. Format: HH:MM (24h). | `09:00` |
| `weekend_close_time` | STRING | ❌ | — | Closing time on weekends. Format: HH:MM (24h). | `22:00` |
| `daily_dispatch_capacity_units` | INTEGER | ❌ | — | Maximum units that can be dispatched from this warehouse per day. | `7000` |
| `service_radius_km` | FLOAT | ❌ | — | Geographic radius (km) within which this warehouse can serve locations. Used to derive BRIDGE_WAREHOUSE_LOCATION. | `18` |
| `cycle_count` | INTEGER | ✅ | — | Number of cycle vehicles available for local delivery. | `8` |
| `bike_count` | INTEGER | ✅ | — | Number of motorbikes available for delivery. | `14` |
| `scooter_count` | INTEGER | ✅ | — | Number of scooters available for delivery. | `10` |
| `electric_scooter_count` | INTEGER | ✅ | — | Number of electric scooters available. | `6` |
| `auto_count` | INTEGER | ✅ | — | Number of auto-rickshaws available for delivery. | `4` |
| `total_vehicle_count` | INTEGER | ❌ | — | Sum of all vehicle types at this warehouse. | `42` |
| `storage_type` | STRING | ✅ | — | Storage category: Mixed, Cold, Dry, etc. From final_warehouse_dataset_kolkata.xlsx. | `Mixed` |
| `x_coordinate` | FLOAT | ✅ | — | X coordinate (same as longitude in source). Retained for completeness. | `88.36175` |
| `y_coordinate` | FLOAT | ✅ | — | Y coordinate (same as latitude in source). Retained for completeness. | `22.5014` |
| `status` | STRING | ✅ | — | Operational status: Active or Inactive. From final_warehouse_dataset_kolkata.xlsx. | `Active` |
| `source_file` | STRING | ❌ | — | Merged from two warehouse sources. | `warehouses.xlsx + final_warehouse_dataset_kolkata.xlsx` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### DIM_SUPPLIER

**Source layer**: `06_curated/DIM_SUPPLIER.csv`  
**Row count**: 200  
**Primary key**: `supplier_id`  
**Foreign keys**: `location_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `supplier_id` | STRING | ❌ | PK | Unique supplier identifier. Format: SUP-KOL-<LOC_NUM>-<SUPPLIER_NUM>. | `SUP-KOL-001-01` |
| `supplier_name` | STRING | ❌ | — | Full legal/trade name of the supplier. | `Lake Gardens Fresh Produce & Chilled Market` |
| `supplier_type_id` | STRING | ❌ | — | Supplier type code. e.g. SUP-T01. | `SUP-T01` |
| `supplier_type_name` | STRING | ❌ | — | Human-readable supplier type. e.g. 'Fresh Produce & Chilled'. | `Fresh Produce & Chilled` |
| `location_id` | STRING | ❌ | FK→DIM_LOCATION | Location (area) where this supplier is based. | `KOL-LOC-001` |
| `location_name` | STRING | ❌ | — | Area name corresponding to location_id. | `Lake Gardens` |
| `city` | STRING | ❌ | — | City. All records = 'Kolkata'. | `Kolkata` |
| `supplier_latitude` | FLOAT | ❌ | — | WGS-84 latitude of the supplier's approximate location. | `22.5051` |
| `supplier_longitude` | FLOAT | ❌ | — | WGS-84 longitude of the supplier's approximate location. | `88.3542` |
| `product_category_scope` | STRING | ❌ | — | Semicolon-separated list of product categories this supplier stocks. | `Fresh Fruits; Dairy & Milk Products; Ice Cream` |
| `minimum_order_qty_units` | INTEGER | ❌ | — | Minimum Order Quantity (MOQ) in units. Must be <= max_order_qty_units. | `90` |
| `max_order_qty_units` | INTEGER | ❌ | — | Maximum single order quantity in units. | `1900` |
| `max_ship_qty_at_once_units` | INTEGER | ❌ | — | Maximum units that can be shipped in a single shipment. | `750` |
| `supplier_storage_capacity_units` | INTEGER | ❌ | — | Total storage capacity of the supplier's facility in units. | `2300` |
| `vehicle_type` | STRING | ❌ | — | Primary vehicle type used for delivery. e.g. 'Refrigerated Mini Truck'. | `Refrigerated Mini Truck` |
| `vehicle_count` | INTEGER | ❌ | — | Number of vehicles of the primary type available. | `4` |
| `vehicle_load_capacity_units` | INTEGER | ❌ | — | Load capacity per vehicle in units. | `34` |
| `lead_time_days` | INTEGER | ❌ | — | Standard lead time from order to delivery in days. Must be >= 0. | `1` |
| `location_note` | STRING | ✅ | — | Free-text provenance note about the coordinate data quality. | `Approximate planning coordinate near area center` |
| `source_file` | STRING | ❌ | — | Provenance. | `supplier_inventory.xlsx/Supplier_Master` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### DIM_CALENDAR_WEEK

**Source layer**: `06_curated/DIM_CALENDAR_WEEK.csv`  
**Row count**: 105  
**Primary key**: `week_key`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `week_key` | STRING | ❌ | PK | Deterministic week identifier. Format: YYYYMMDD of week_start_date. e.g. 20240101. | `20240101` |
| `week_start_date` | DATE | ❌ | — | Monday (or first day) of the week. ISO 8601 date. | `2024-01-01` |
| `week_end_date` | DATE | ❌ | — | Last day of the week (7 days after week_start_date minus 1). Should be week_start + 6 days. | `2024-01-07` |
| `year` | INTEGER | ❌ | — | Calendar year of week_start_date. | `2024` |
| `week_number` | INTEGER | ❌ | — | ISO week number within the year (1–53). | `1` |
| `season` | STRING | ❌ | — | Season label: Winter, Summer, Monsoon, Post-Monsoon, Spring. Derived from Kolkata climate. | `Winter` |
| `source_file` | STRING | ❌ | — | Derived from weather_weekly.csv date coverage. | `weather_weekly.csv` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### DIM_FESTIVAL

**Source layer**: `06_curated/DIM_FESTIVAL.csv`  
**Row count**: 36  
**Primary key**: `festival_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `festival_id` | STRING | ❌ | PK | Synthetic festival record identifier. Format: FEST-<NNN>. | `FEST-001` |
| `festival_event` | STRING | ❌ | — | Name of the festival or public holiday event. | `Saraswati Puja` |
| `event_date` | DATE | ❌ | — | Actual date of the festival event. Sourced directly from festival_calendar.csv; not inferred. | `2024-02-14` |
| `year` | INTEGER | ❌ | — | Calendar year of the event. | `2024` |
| `week_start_date` | DATE | ❌ | — | Monday of the ISO week containing event_date. Derived via period(W-MON). | `2024-02-12` |
| `festival_category` | STRING | ❌ | — | Inferred religious/cultural category: Hindu, Islamic, Christian, National, Cultural/New Year. | `Hindu` |
| `source_type` | STRING | ❌ | — | Data provenance type. SUPPLIED_REFERENCE = provided reference data; not inferred or synthetic. | `SUPPLIED_REFERENCE` |
| `source_file` | STRING | ❌ | — | Provenance. | `festival_calendar.csv` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### DIM_WEATHER

**Source layer**: `06_curated/DIM_WEATHER.csv`  
**Row count**: 105  
**Primary key**: `week_start_date`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `week_start_date` | DATE | ❌ | PK | First day of the weather observation week. | `2024-01-01` |
| `week_end_date` | DATE | ❌ | — | Last day of the weather observation week. Should be week_start + 6 days. | `2024-01-07` |
| `year` | INTEGER | ❌ | — | Calendar year. | `2024` |
| `season` | STRING | ❌ | — | Season label for Kolkata. Values: Winter, Summer, Monsoon, Post-Monsoon. | `Winter` |
| `temperature_mean_c` | FLOAT | ❌ | — | Mean weekly temperature in degrees Celsius. | `18.6` |
| `temperature_max_c` | FLOAT | ❌ | — | Maximum temperature recorded during the week (°C). | `22.3` |
| `temperature_min_c` | FLOAT | ❌ | — | Minimum temperature recorded during the week (°C). | `16.1` |
| `rainfall_mm` | FLOAT | ❌ | — | Total rainfall for the week in millimetres. Domain: >= 0. | `12.9` |
| `humidity_pct` | FLOAT | ❌ | — | Average relative humidity for the week as a percentage. Domain: 0–100. | `56.8` |
| `weather_condition` | STRING | ❌ | — | Categorical weather label. Values: Clear/Partly Cloudy, Rain, Heavy Rain, Fog, Humid. | `Clear/Partly Cloudy` |
| `weather_data_type` | STRING | ❌ | — | Data provenance marker. SUPPLIED_SYNTHETIC = generated for simulation; not real Kolkata observations. | `SUPPLIED_SYNTHETIC` |
| `interval_days` | INTEGER | ✅ | — | Computed interval: week_end_date - week_start_date in days. Should = 6. WARNING: 1 record has non-6 interval. | `6` |
| `source_file` | STRING | ❌ | — | Provenance. | `weather_weekly.csv` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

## Fact Tables

### FACT_DEMAND

**Source layer**: `06_curated/FACT_DEMAND.csv`  
**Row count**: 27,800  
**Primary key**: `demand_id`  
**Foreign keys**: `week_start_date`, `location_id`, `product_id`, `festival_event`  
**⚠️ TARGET fields** (excluded from features): `next_week_demand_target_units`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `demand_id` | STRING | ❌ | PK | Unique demand record identifier. Format: DEM-<7-digit sequence>. | `DEM-0000001` |
| `week_start_date` | DATE | ❌ | FK→DIM_CALENDAR_WEEK | First day of the demand observation week. | `2024-01-01` |
| `week_end_date` | DATE | ❌ | — | Last day of the demand observation week. | `2024-01-07` |
| `year` | INTEGER | ❌ | — | Calendar year of this demand record. | `2024` |
| `week_number` | INTEGER | ❌ | — | ISO week number within the year. | `1` |
| `location_id` | STRING | ❌ | FK→DIM_LOCATION | Kolkata region identifier. Joins to DIM_LOCATION.location_id. | `KOL-LOC-001` |
| `region_of_kolkata` | STRING | ❌ | — | Region name (denormalized from DIM_LOCATION for convenience). | `Lake Gardens` |
| `demand_rank` | INTEGER | ❌ | — | Rank of this product by units_sold within the region-week (1 = top-selling). | `1` |
| `product_id` | STRING | ❌ | FK→DIM_PRODUCT | Product identifier. Joins to DIM_PRODUCT.product_id. | `DAI-005` |
| `product_name` | STRING | ❌ | — | Product name (denormalized). | `Mother Dairy Curd` |
| `category_name` | STRING | ❌ | — | Product category name (denormalized). | `Dairy & Milk Products` |
| `brand` | STRING | ❌ | — | Brand name (denormalized). | `Mother Dairy` |
| `unit_size` | STRING | ❌ | — | Unit size string as used in demand context. Joins to DIM_PRODUCT_VARIANT.unit_size_raw via product_id. | `500 g` |
| `weekday_weekend` | STRING | ❌ | — | Observation split. Values: Weekday or Weekend. Current source only contains Weekday rows. | `Weekday` |
| `weekday_units_sold` | INTEGER | ❌ | — | Units sold on weekdays during this week. | `111` |
| `weekend_units_sold` | INTEGER | ❌ | — | Units sold on weekends during this week. | `35` |
| `units_sold` | INTEGER | ❌ | — | Total units sold = weekday_units_sold + weekend_units_sold. Validated for consistency. | `146` |
| `avg_selling_price_rs` | FLOAT | ❌ | — | Average actual selling price per unit in INR during this week. | `52.79` |
| `promotion_flag` | INTEGER | ❌ | — | 1 if a promotion was active this week for this product-location, else 0. | `0` |
| `discount_pct` | FLOAT | ❌ | — | Discount percentage applied (0–100). 0 if no discount. | `0` |
| `holiday_flag` | INTEGER | ❌ | — | 1 if a public holiday falls within this week, else 0. | `0` |
| `festival_event` | STRING | ✅ | FK→DIM_FESTIVAL | Name of the festival if one falls within this week. NULL if no festival. | `None` |
| `season` | STRING | ❌ | — | Season label for this week. Matches DIM_WEATHER.season. | `Winter` |
| `temperature_c` | FLOAT | ❌ | — | Weekly mean temperature in °C. Sourced from weather context. | `18.6` |
| `rainfall_mm` | FLOAT | ❌ | — | Weekly total rainfall in mm. | `12.9` |
| `humidity_pct` | FLOAT | ❌ | — | Weekly average humidity %. | `56.8` |
| `weather_condition` | STRING | ❌ | — | Categorical weather label for this week. | `Clear/Partly Cloudy` |
| `stockout_flag` | INTEGER | ❌ | — | 1 if a stockout occurred for this product-location-week, else 0. | `0` |
| `forecast_target_start` | DATE | ❌ | — | Start of the forecast target window (= next week_start_date). | `2024-01-08` |
| `forecast_target_end` | DATE | ❌ | — | End of the forecast target window (= next week_end_date). | `2024-01-14` |
| `next_week_demand_target_units` | FLOAT | ❌ | TARGET | Prediction target: units expected to be sold in the NEXT week. MUST NOT be used as a feature. Isolated to DEMAND_TARGETS.csv. | `152` |
| `data_source` | STRING | ❌ | — | Pipe-separated provenance flags. e.g. SYNTHETIC_TRAINING \| SUPPLIED_WEATHER \| SUPPLIED_FESTIVAL. | `SYNTHETIC_TRAINING \| SUPPLIED_WEATHER` |
| `region_week_key` | STRING | ❌ | — | Composite key: <location_id>_<YYYYMMDD>. Primary join key for region-week aggregation. | `KOL-LOC-001_20240101` |
| `region_product_week_key` | STRING | ❌ | — | Composite key: <location_id>_<YYYYMMDD>_<product_id>. Natural key for this fact table. | `KOL-LOC-001_20240101_DAI-005` |
| `anchor_status` | STRING | ❌ | — | Data quality marker from source. e.g. observed_top5_anchor. | `observed_top5_anchor` |
| `fact_source` | STRING | ❌ | — | Pipeline tag identifying source dataset. | `DEMAND_OF_LAST_2_YEARS` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### FACT_INVENTORY_POSITION

**Source layer**: `06_curated/FACT_INVENTORY_POSITION.csv`  
**Row count**: 3,000  
**Foreign keys**: `warehouse_id`, `product_id`, `shelf_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `warehouse_id` | STRING | ❌ | FK→DIM_WAREHOUSE | Warehouse containing this inventory. | `WH-KOL-001` |
| `product_id` | STRING | ❌ | FK→DIM_PRODUCT | Product stocked at this location. | `ICE-001` |
| `shelf_id` | STRING | ❌ | FK→Shelf_Master | Physical shelf identifier within the warehouse zone. | `WH-KOL-001-Z01-R01-S01` |
| `bin_id` | STRING | ❌ | — | Bin/slot identifier within the shelf. Most granular physical location. | `WH-KOL-001-Z01-R01-S01-B01` |
| `opening_stock_units` | INTEGER | ✅ | — | Stock units at the start of the snapshot period. | `94` |
| `received_units` | INTEGER | ✅ | — | Units received (inbound) during the snapshot period. | `46` |
| `current_stock_units` | INTEGER | ✅ | — | Total physical units currently on hand. = opening + received - outbound. | `84` |
| `reserved_stock_units` | INTEGER | ✅ | — | Units reserved for pending orders. Must be <= current_stock_units. | `7` |
| `available_stock_units` | INTEGER | ✅ | — | Units available for new orders. Domain: >= 0. Formula: current - reserved - damaged. | `77` |
| `damaged_units` | INTEGER | ✅ | — | Units classified as damaged/unsellable. Domain: >= 0. | `0` |
| `cost_price_rs` | FLOAT | ✅ | — | Average cost price per unit in INR for this product-warehouse combination. | `101.6` |
| `selling_price_rs` | FLOAT | ✅ | — | Selling price per unit in INR. | `116.8` |
| `avg_weekly_demand_units` | FLOAT | ✅ | — | Historical average weekly demand for this product at this warehouse. | `67.3` |
| `stock_status` | STRING | ✅ | — | Qualitative status from source: Healthy, Low, Critical, Overstocked. | `Healthy` |
| `snapshot_date` | DATE | ❌ | — | Date when this inventory position was recorded. All records: 2026-08-31. | `2026-08-31` |
| `weeks_of_cover_calc` | FLOAT | ✅ | — | PIPELINE-CALCULATED: available_stock / avg_weekly_demand. Formula cache in source was empty (None). Replaces source weeks_of_cover. | `1.14` |
| `reorder_flag_calc` | INTEGER | ✅ | — | PIPELINE-CALCULATED: 1 if weeks_of_cover_calc < 2.0, else 0. | `1` |
| `stock_cost_value_rs` | FLOAT | ✅ | — | PIPELINE-CALCULATED: current_stock_units × cost_price_rs. | `8534.4` |
| `available_sales_value_rs` | FLOAT | ✅ | — | PIPELINE-CALCULATED: available_stock_units × selling_price_rs. | `8993.6` |
| `inventory_risk` | STRING | ✅ | — | Risk classification from source Inventory_Control sheet. Values: NORMAL, LOW_STOCK, CRITICAL. | `NORMAL` |
| `source_file` | STRING | ❌ | — | Merged from Inventory_Position + Inventory_Control sheets. | `inventory_stock.xlsx/Inventory_Position+Inventory_Control` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### FACT_SUPPLIER_AVAILABILITY

**Source layer**: `06_curated/FACT_SUPPLIER_AVAILABILITY.csv`  
**Row count**: 8,000  
**Primary key**: `supplier_product_key`  
**Foreign keys**: `supplier_id`, `product_id`, `location_id`  
**🔶 QUARANTINE fields** (domain review required): `unmapped_col_10_quarantine`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `supplier_product_key` | STRING | ❌ | PK | Composite key: <supplier_id>_<product_id>. | `SUP-KOL-001-01_ICE-001` |
| `supplier_id` | STRING | ❌ | FK→DIM_SUPPLIER | Supplier identifier. | `SUP-KOL-001-01` |
| `product_id` | STRING | ❌ | FK→DIM_PRODUCT | Product identifier. | `ICE-001` |
| `supplier_type_id` | STRING | ❌ | — | Supplier type code. | `SUP-T01` |
| `supplier_type_name` | STRING | ❌ | — | Supplier type description. | `Fresh Produce & Chilled` |
| `supplier_cost_price_rs` | FLOAT | ❌ | — | Supplier's cost price for this product in INR. | `36` |
| `supplied_unit_size` | STRING | ❌ | — | Unit size in which the supplier provides this product. Joins to DIM_PRODUCT_VARIANT.unit_size_raw. | `80 ml` |
| `supply_status` | STRING | ❌ | — | Availability status. Values: Available, Unavailable, Limited. | `Available` |
| `unmapped_col_10_quarantine` | FLOAT | ✅ | QUARANTINE | QUARANTINED FIELD: Column at index 10 in Supplier_Product_Catalog had no header. Values are numeric (~9–200). Semantic meaning unresolved. Do NOT use in models without domain review. | `35.71` |
| `minimum_order_qty_units` | INTEGER | ✅ | — | Minimum Order Quantity from DIM_SUPPLIER. Inherited via supplier_id join. | `90` |
| `max_order_qty_units` | INTEGER | ✅ | — | Maximum order quantity from DIM_SUPPLIER. | `1900` |
| `max_ship_qty_at_once_units` | INTEGER | ✅ | — | Maximum shipment quantity per trip. | `750` |
| `supplier_storage_capacity_units` | INTEGER | ✅ | — | Supplier's total storage capacity. | `2300` |
| `vehicle_type` | STRING | ✅ | — | Primary delivery vehicle type. | `Refrigerated Mini Truck` |
| `vehicle_count` | INTEGER | ✅ | — | Number of vehicles available. | `4` |
| `vehicle_load_capacity_units` | INTEGER | ✅ | — | Capacity per vehicle in units. | `34` |
| `lead_time_days` | INTEGER | ✅ | — | Lead time from supplier in days. | `1` |
| `location_id` | STRING | ✅ | FK→DIM_LOCATION | Supplier's operating area. | `KOL-LOC-001` |
| `snapshot_date` | TIMESTAMP | ❌ | — | UTC timestamp of snapshot creation. | `2026-09-21T13:24:00Z` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

## Bridge / Mapping Tables

### BRIDGE_SUPPLIER_PRODUCT

**Source layer**: `06_curated/BRIDGE_SUPPLIER_PRODUCT.csv`  
**Row count**: 8,000  
**Primary key**: `supplier_product_key`  
**Foreign keys**: `supplier_id`, `product_id`  
**🔶 QUARANTINE fields** (domain review required): `unmapped_col_10_quarantine`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `supplier_product_key` | STRING | ❌ | PK | Deterministic key: <supplier_id>_<product_id>. | `SUP-KOL-001-01_ICE-001` |
| `supplier_id` | STRING | ❌ | FK→DIM_SUPPLIER | Supplier. | `SUP-KOL-001-01` |
| `product_id` | STRING | ❌ | FK→DIM_PRODUCT | Product supplied by this supplier. | `ICE-001` |
| `supplier_type_id` | STRING | ❌ | — | Supplier type code. | `SUP-T01` |
| `supplier_type_name` | STRING | ❌ | — | Supplier type description. | `Fresh Produce & Chilled` |
| `supplier_cost_price_rs` | FLOAT | ❌ | — | Cost price for this product from this supplier in INR. | `36` |
| `supplied_unit_size` | STRING | ❌ | — | Unit size supplied. Matches DIM_PRODUCT_VARIANT.unit_size_raw. | `80 ml` |
| `supply_status` | STRING | ❌ | — | Availability: Available, Unavailable, Limited. | `Available` |
| `unmapped_col_10_quarantine` | FLOAT | ✅ | QUARANTINE | Unresolved numeric column from Supplier_Product_Catalog index 10. Preserved for domain review. Do not use in production until resolved. | `35.71` |
| `source_file` | STRING | ❌ | — | Provenance. | `supplier_inventory.xlsx/Supplier_Product_Catalog` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### BRIDGE_LOCATION_SUPPLIER

**Source layer**: `06_curated/BRIDGE_LOCATION_SUPPLIER.csv`  
**Row count**: 200  
**Foreign keys**: `location_id`, `supplier_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `location_id` | STRING | ❌ | FK→DIM_LOCATION | Service area (location) identifier. | `KOL-LOC-001` |
| `location_name` | STRING | ❌ | — | Area name. | `Lake Gardens` |
| `supplier_id` | STRING | ❌ | FK→DIM_SUPPLIER | Supplier serving this location. | `SUP-KOL-001-01` |
| `supplier_type_id` | STRING | ❌ | — | Supplier type code. | `SUP-T01` |
| `supplier_type_name` | STRING | ❌ | — | Supplier type name. | `Fresh Produce & Chilled` |
| `supplier_latitude` | FLOAT | ❌ | — | Supplier's latitude. | `22.5051` |
| `supplier_longitude` | FLOAT | ❌ | — | Supplier's longitude. | `88.3542` |
| `distance_from_location_center_km` | FLOAT | ❌ | — | Straight-line distance from supplier to location centre in km. From source data; method not explicitly stated. | `0.198` |
| `supplier_option_rank` | INTEGER | ❌ | — | Rank of this supplier for this location (1 = closest/preferred). | `1` |
| `service_available_flag` | STRING | ❌ | — | Whether the supplier services this location: Yes / No. | `Yes` |
| `source_file` | STRING | ❌ | — | Provenance. | `supplier_inventory.xlsx/Area_Supplier_Options` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### BRIDGE_WAREHOUSE_LOCATION

**Source layer**: `06_curated/BRIDGE_WAREHOUSE_LOCATION.csv`  
**Row count**: 600  
**Foreign keys**: `warehouse_id`, `location_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `warehouse_id` | STRING | ❌ | FK→DIM_WAREHOUSE | Warehouse identifier. | `WH-KOL-001` |
| `location_id` | STRING | ❌ | FK→DIM_LOCATION | Location (delivery area) identifier. | `KOL-LOC-001` |
| `euclidean_distance_km` | FLOAT | ❌ | — | Haversine great-circle distance between warehouse centroid and location centroid in km. NOT road distance. | `0.8644` |
| `service_radius_km` | FLOAT | ❌ | — | Service radius of the warehouse (from DIM_WAREHOUSE). Used to compute service_available_flag. | `18` |
| `service_available_flag` | STRING | ❌ | — | 'Yes' if euclidean_distance_km <= service_radius_km; else 'No'. | `Yes` |
| `assignment_method` | STRING | ❌ | — | How the mapping was derived. Value: haversine_vs_service_radius. | `haversine_vs_service_radius` |
| `mapping_source` | STRING | ❌ | — | Origin of the mapping. DERIVED_FROM_COORDINATES = computed, not sourced. | `DERIVED_FROM_COORDINATES` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

### BRIDGE_PRODUCT_WAREHOUSE

**Source layer**: `06_curated/BRIDGE_PRODUCT_WAREHOUSE.csv`  
**Row count**: 3,000  
**Foreign keys**: `warehouse_id`, `product_id`, `shelf_id`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `warehouse_id` | STRING | ❌ | FK→DIM_WAREHOUSE | Warehouse holding this product. | `WH-KOL-001` |
| `product_id` | STRING | ❌ | FK→DIM_PRODUCT | Product stocked in this warehouse. | `ICE-001` |
| `shelf_id` | STRING | ❌ | FK→Shelf_Master | Physical shelf where product is stored. | `WH-KOL-001-Z01-R01-S01` |
| `bin_id` | STRING | ❌ | — | Bin within the shelf. | `WH-KOL-001-Z01-R01-S01-B01` |
| `source_file` | STRING | ❌ | — | Provenance. | `inventory_stock.xlsx/Inventory_Position` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

## Feature Sets

### DEMAND_FEATURES

**Source layer**: `07_features/DEMAND_FEATURES.csv`  
**Row count**: 27,800  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `lag_1w_units_sold` | FLOAT | ✅ | FEATURE | Units sold 1 week prior (lag-1). Computed per location+product. NULL for first week. | `143` |
| `lag_2w_units_sold` | FLOAT | ✅ | FEATURE | Units sold 2 weeks prior (lag-2). | `138` |
| `lag_4w_units_sold` | FLOAT | ✅ | FEATURE | Units sold 4 weeks prior (lag-4). | `130` |
| `lag_8w_units_sold` | FLOAT | ✅ | FEATURE | Units sold 8 weeks prior (lag-8). | `125` |
| `lag_12w_units_sold` | FLOAT | ✅ | FEATURE | Units sold 12 weeks prior (lag-12). | `120` |
| `rolling_mean_4w` | FLOAT | ✅ | FEATURE | 4-week rolling mean of lag_1w_units_sold. Leakage-safe (uses lagged values only). | `135.0` |
| `rolling_mean_8w` | FLOAT | ✅ | FEATURE | 8-week rolling mean of lag_1w_units_sold. | `130.0` |
| `rolling_mean_12w` | FLOAT | ✅ | FEATURE | 12-week rolling mean of lag_1w_units_sold. | `128.0` |
| `demand_trend_4w` | FLOAT | ✅ | FEATURE | OLS slope of lag_1w over the last 4 weeks. Positive = growing demand. | `1.5` |
| `weekday_ratio` | FLOAT | ✅ | FEATURE | weekday_units_sold / units_sold. Proportion of sales on weekdays. | `0.76` |
| `weekend_ratio` | FLOAT | ✅ | FEATURE | weekend_units_sold / units_sold. Proportion of sales on weekends. | `0.24` |
| `days_to_next_festival` | FLOAT | ✅ | FEATURE | Days from week_start_date to the next festival event. NULL if no future festival in data. | `14` |
| `days_since_last_festival` | FLOAT | ✅ | FEATURE | Days since the most recent past festival event. | `7` |
| `festival_flag` | INTEGER | ❌ | FEATURE | 1 if a festival event falls within this demand week, else 0. Derived from festival_event column. | `0` |
| `leakage_safe` | BOOLEAN | ❌ | — | Pipeline metadata: True confirms next_week_demand_target_units has been removed from this table. | `True` |
| `target_column` | STRING | ❌ | — | Documents which column was removed as the prediction target. | `next_week_demand_target_units (excluded from features)` |

---

### DEMAND_TARGETS

**Source layer**: `07_features/DEMAND_TARGETS.csv`  
**Row count**: 27,800  
**Primary key**: `demand_id`  
**Foreign keys**: `location_id`, `product_id`  
**⚠️ TARGET fields** (excluded from features): `next_week_demand_target_units`  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `demand_id` | STRING | ❌ | PK | Links to FACT_DEMAND and DEMAND_FEATURES. | `DEM-0000001` |
| `location_id` | STRING | ❌ | FK→DIM_LOCATION | Location of the demand record. | `KOL-LOC-001` |
| `product_id` | STRING | ❌ | FK→DIM_PRODUCT | Product of the demand record. | `DAI-005` |
| `week_start_date` | DATE | ❌ | — | Week the observation relates to (not the target week). | `2024-01-01` |
| `next_week_demand_target_units` | FLOAT | ❌ | TARGET | PREDICTION TARGET: Expected demand for the FOLLOWING week. Must NEVER be used as a feature. | `152` |
| `forecast_target_start` | DATE | ❌ | — | Start of the target forecast window (next week_start_date). | `2024-01-08` |

---

### ROUTING_FEATURES

**Source layer**: `07_features/ROUTING_FEATURES.csv`  
**Row count**: 800  

| Field | Type | Nullable | Key | Description | Example |
|---|---|:---:|---|---|---|
| `origin_id` | STRING | ❌ | — | ID of the origin entity (warehouse_id or supplier_id). | `WH-KOL-001` |
| `destination_id` | STRING | ❌ | — | ID of the destination entity (location_id). | `KOL-LOC-001` |
| `euclidean_distance_km` | FLOAT | ❌ | — | Haversine great-circle distance in km. IMPORTANT: this is NOT road distance. | `0.8644` |
| `service_available_flag` | STRING | ❌ | — | Whether service is available on this route: Yes / No. | `Yes` |
| `origin_type` | STRING | ❌ | — | Entity type of origin: WAREHOUSE or SUPPLIER. | `WAREHOUSE` |
| `destination_type` | STRING | ❌ | — | Entity type of destination: LOCATION. | `LOCATION` |
| `distance_type` | STRING | ❌ | — | Distance calculation method. Always 'euclidean_km' (Haversine). Never call this road distance. | `euclidean_km` |
| `note` | STRING | ❌ | — | Important usage warning about distance type. | `Euclidean (Haversine) distance only. Road distance not available.` |
| `feature_set` | STRING | ❌ | — | Agent this feature set is designed for. | `ROUTE_OPTIMIZATION_AGENT` |
| `pipeline_timestamp` | TIMESTAMP | ❌ | — | UTC pipeline write timestamp. | `2026-09-21T13:24:00Z` |

---

## Blocked Outputs

These tables **cannot be built** until the Git-LFS source files are fetched.

| Table | Blocked By | LFS OID | Expected Size | Fix |
|---|---|---|---|---|
| `FACT_SALES` | `sales_history.xlsx` (LFS pointer) | `fc8022e6...` | 177 MB | `git lfs pull` |
| `FACT_INVENTORY_TRANSACTION` | `inventory_transactions.xlsx` (LFS pointer) | `5fc053ba...` | 56 MB | `git lfs pull` |

After running `git lfs pull`, re-execute `pipeline/run_pipeline.py` to build these tables.

---

## Quarantine Register

| QRN-ID | Field | Table | Issue | Action |
|---|---|---|---|---|
| QRN-001 | `unmapped_col_10_quarantine` | BRIDGE_SUPPLIER_PRODUCT, FACT_SUPPLIER_AVAILABILITY | Column index 10 in Supplier_Product_Catalog has no header. Values numeric ~9–200. Possible unit ratio. | Domain expert review required before production use. |
| QRN-002 | ALL | FACT_SALES | sales_history.xlsx is a Git-LFS pointer. | Run `git lfs pull`. |
| QRN-003 | ALL | FACT_INVENTORY_TRANSACTION | inventory_transactions.xlsx is a Git-LFS pointer. | Run `git lfs pull`. |
