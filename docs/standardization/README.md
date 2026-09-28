# Data Standardization Layer Documentation

## 1. Overview & Pipeline Role

The **Data Standardization Layer** (`02_data_standardization.ipynb`) transforms staged tables into rigorously typed, canonical representations (`Datasets/standardized/std_*.csv`). It resolves casing discrepancies, trims whitespace, standardizes units of measure, parses ISO dates, and enforces semantic integrity without silent type coercion.

```
    STAGING
       ↓
STANDARDIZATION   ← Layer 2
       ↓
 ENTITY MAPPING
```

---

## 2. Standardization Rules & Operations

### A. Data Type Enforcement
- **Numeric Fields**: Quantities (`units_sold`, `current_stock_units`), capacities, and lead times cast to strict integer/float types.
- **Financial Fields**: Prices (`cost_price_rs`, `selling_price_rs`) standardized to 2-decimal floats representing Indian Rupees (INR).
- **Temporal Fields**: `week_start_date`, `week_end_date`, and `snapshot_date` parsed to ISO 8601 `YYYY-MM-DD`.
- **Coordinates**: Latitudes ($[-90, 90]$) and Longitudes ($[-180, 180]$) validated as 6-decimal floats.

### B. Categorical Canonicalization
- **String Cleaning**: Strip leading/trailing whitespace, collapse internal double spaces, and normalize to uppercase or title-case based on semantic standards.
- **Product Categories**: Standardized to 10 canonical retail categories (`Baby Care`, `Bakery & Dairy`, `Beverages`, `Personal Care`, `Snacks`, etc.).
- **Warehouse IDs**: Strictly validated to adhere to `WH-KOL-001` through `WH-KOL-015`. Any non-conforming representation is rejected.
- **Seasons & Weather**: Canonical season names (`Winter`, `Summer`, `Pre-Monsoon`, `Monsoon`, `Post-Monsoon`) and weather conditions (`Clear`, `Rainy`, `Humid`, `Cloudy`).

### C. Units of Measurement
- Volume/Capacity: Standardized to storage units (crates/boxes) or liters/kilograms.
- Distance: Standardized strictly to kilometers (`km`), explicitly noting spherical Haversine computation.

---

## 3. Standardized Output Catalog (`Datasets/standardized/`)

| Standardized File | Source Staging File | Grain | Row Count | Primary Key |
|---|---|---|---|---|
| `std_sales_demand.csv` | `stg_sales_demand.csv` | location × product × week | 1,112,000 | `region_id + product_id + week_id` |
| `std_inventory_position.csv` | `stg_inventory_position.csv` | warehouse × product | 3,000 | `warehouse_id + product_id` |
| `std_product_master.csv` | `stg_product_master.csv` | product | 200 | `product_id` |
| `std_location_master.csv` | `stg_location_master.csv` | location | 40 | `location_id` |
| `std_warehouse_master.csv` | `stg_warehouse_master.csv` | warehouse | 15 | `warehouse_id` |
| `std_supplier_master.csv` | `stg_supplier_master.csv` | supplier | 200 | `supplier_id` |
| `std_calendar_week.csv` | `stg_calendar_week.csv` | week | 139 | `week_id` |
| `std_weather_events.csv` | `stg_weather_events.csv` | week | 139 | `week_id` |
| `std_warehouse_picker_mapping.csv`| `stg_warehouse_picker_mapping.csv` | warehouse × picker | 750 | `warehouse_id + picker_id` |
| `std_inventory_transactions.csv` | `stg_inventory_transactions.csv` | warehouse × product × week | 417,000 | `warehouse_id + product_id + week_id` |
| `std_supplier_product_catalog.csv`| `stg_supplier_master.csv` (derived) | supplier × product | 8,000 | `supplier_id + product_id` |
| `std_storage_assignment.csv` | `stg_inventory_position.csv` (derived) | warehouse × product | 3,000 | `warehouse_id + product_id` |

---

## 4. Governance & Audit Reports

The standardization layer produces profiling and validation reports in `Datasets/reports/`:
- `standardization_final_report.csv`: Overall rule execution log and certification status.
- `standardization_column_profile.csv`: Column-by-column null, cardinality, and type audit.
- `standardization_dataset_profile.csv`: High-level row and column metrics.
- `standardization_validation_report.csv`: Pass/fail audit against schema constraints.
