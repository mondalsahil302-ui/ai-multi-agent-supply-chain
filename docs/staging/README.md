# Staging Pipeline Layer Documentation

## 1. Overview & Pipeline Role

The **Staging Pipeline** (`01_data_staging_pipeline.ipynb`) is the first operational stage of the supply chain data foundation. It ingests raw files from `Datasets/raw_dataset/`, standardizes column naming to snake_case, enforces UTF-8 encoding, appends cryptographic lineage hashes, and writes immutable staging tables (`Datasets/staging/stg_*.csv`).

```
RAW DATA INGESTION
       ↓
    STAGING   ← Layer 1
       ↓
STANDARDIZATION
```

---

## 2. Ingestion Principles & Guarantees

1. **Zero Row Loss**: Every valid record from raw source workbooks and CSVs is preserved without dropping rows.
2. **Cryptographic Integrity**: Every row receives a SHA-256 `record_hash` derived from all raw fields.
3. **Audit Trail**: Every record is tagged with an ISO 8601 `ingestion_timestamp` and `source_row_number`.
4. **Header Normalization**: Raw headers containing spaces, punctuation, or mixed casing are converted to uniform lowercase `snake_case`.
5. **Excel Sheet Assembly**: For `sales_history_source.xlsx`, all 139 individual weekly sheets (8,000 rows each) are systematically unrolled and concatenated into a unified 1,112,000-row staging table.

---

## 3. Staging Dataset Catalog (`Datasets/staging/`)

| Staging File | Source File | Grain | Row Count | Primary Key |
|---|---|---|---|---|
| `stg_sales_demand.csv` | `sales_history_source.xlsx` (139 sheets) | location × product × week | 1,112,000 | `region_id + product_id + week_id` |
| `stg_inventory_position.csv` | `inventory_snapshot.csv` | warehouse × product | 3,000 | `warehouse_id + product_id` |
| `stg_product_master.csv` | `product_master.csv` | product | 200 | `product_id` |
| `stg_location_master.csv` | `location_master.csv` | location | 40 | `location_id` |
| `stg_warehouse_master.csv` | `warehouse_master.csv` | warehouse | 15 | `warehouse_id` |
| `stg_supplier_master.csv` | `supplier_master.csv` | supplier | 200 | `supplier_id` |
| `stg_calendar_week.csv` | `calendar_week.csv` | week | 139 | `week_id` |
| `stg_weather_events.csv` | `weather_events.csv` | week | 139 | `week_id` |
| `stg_warehouse_picker_mapping.csv`| `warehouse_picker_mapping.csv` | warehouse × picker | 750 | `warehouse_id + picker_id` |
| `stg_inventory_transactions.csv` | `inventory_transactions_reconstructed.csv` | warehouse × product × week | 417,000 | `warehouse_id + product_id + week_id` |
| `stg_location_distance_matrix.csv`| `location_distance_matrix.csv` | location × location | 1,600 | `origin_id + destination_id` |
| `stg_warehouse_location_distance.csv`| `warehouse_location_distance_matrix.csv`| warehouse × location | 600 | `warehouse_id + location_id` |
| `stg_supplier_location_distance.csv`| `supplier_location_distance_matrix.csv` | supplier × location | 8,000 | `supplier_id + location_id` |

---

## 4. Lineage Fields Added

Each staging record is enriched with four immutable lineage columns:
- `source_file`: Original filename from which the record was extracted.
- `source_row_number`: Zero-based or one-based index in the raw file.
- `ingestion_timestamp`: UTC timestamp of staging execution.
- `record_hash`: SHA-256 fingerprint computed across all raw cell values.

---

## 5. Governance & Reports

The staging pipeline generates execution and reconciliation reports in `Datasets/reports/`:
- `staging_final_report.csv`: Complete row count reconciliation and execution log.
- `pipeline_dataset_status.csv`: Status registry tracking dataset availability across pipeline layers.
