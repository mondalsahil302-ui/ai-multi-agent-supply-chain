# Dataset Layer Documentation

## 1. Overview & Pipeline Role

The **Dataset Layer** (`Datasets/raw_dataset/`) forms the immutable foundation of the *Intelligent Multi-Agent Supply Chain Optimization Framework*. It houses all source telemetry, deterministic reference dimensions, synthetic support structures, and initial catalog audits for the Kolkata supply chain ecosystem.

```
RAW DATA INGESTION (Frozen Source)
       ↓
    STAGING
       ↓
STANDARDIZATION
       ↓
 ENTITY MAPPING
       ↓
DATA INTEGRATION
       ↓
FEATURE ENGINEERING
       ↓
FEATURE VALIDATION
```

---

## 2. Directory Hierarchy

```
Datasets/raw_dataset/
├── 01_RAW_SOURCE/
│   ├── sales_history_source.xlsx               # Master weekly sales telemetry (139 sheets, 1.112M rows)
│   ├── inventory_snapshot.csv                  # Point-in-time stock positions (3,000 rows)
│   ├── product_master.csv                      # Product catalog dimension (200 products)
│   ├── location_master.csv                     # Delivery location nodes (40 Kolkata areas)
│   ├── warehouse_master.csv                    # Fulfillment centers (15 warehouses, WH-KOL-001..015)
│   ├── supplier_master.csv                     # Inbound vendors (200 suppliers)
│   ├── calendar_week.csv                       # Weekly calendar master (139 weeks)
│   ├── weather_events.csv                      # Weekly weather & festival events (139 weeks)
│   └── warehouse_picker_mapping.csv            # Pick & pack workforce (750 pickers, 50/wh)
├── 02_DERIVED_REFERENCE/
│   ├── location_distance_matrix.csv            # Pairwise Haversine distance matrix (40 x 40)
│   ├── warehouse_location_distance_matrix.csv  # Warehouse-to-location Haversine matrix (15 x 40)
│   └── supplier_location_distance_matrix.csv   # Supplier-to-location Haversine matrix (200 x 40)
├── 03_SYNTHETIC_SUPPORT/
│   └── inventory_transactions_reconstructed.csv# Reconstructed transactions (417K rows, SYNTHETIC)
└── 04_CATALOG_QA/
    └── README.md                               # Source catalog audit & validation notes
```

---

## 3. Dataset Grain, Volume & Key Registry

| Dataset Name | Subdirectory | Primary Key / Grain | Record Count | Temporal Span | Synthetic Status |
|---|---|---|---|---|---|
| `sales_history_source.xlsx` | `01_RAW_SOURCE` | `region_id + product_id + week_id` | 1,112,000 | 139 weeks (2024–2026) | NO (Observed) |
| `inventory_snapshot.csv` | `01_RAW_SOURCE` | `warehouse_id + product_id` | 3,000 | Snapshot | NO (Observed) |
| `product_master.csv` | `01_RAW_SOURCE` | `product_id` | 200 | Static Dimension | NO (Authoritative) |
| `location_master.csv` | `01_RAW_SOURCE` | `location_id` | 40 | Static Dimension | NO (Authoritative) |
| `warehouse_master.csv` | `01_RAW_SOURCE` | `warehouse_id` | 15 | Static Dimension | NO (Authoritative) |
| `supplier_master.csv` | `01_RAW_SOURCE` | `supplier_id` | 200 | Static Dimension | NO (Authoritative) |
| `warehouse_picker_mapping.csv` | `01_RAW_SOURCE` | `warehouse_id + picker_id` | 750 | Static Dimension | NO (Authoritative) |
| `calendar_week.csv` | `01_RAW_SOURCE` | `week_id` | 139 | 139 weeks | NO (Deterministic) |
| `weather_events.csv` | `01_RAW_SOURCE` | `week_id` | 139 | 139 weeks | NO (Historical) |
| `inventory_transactions_reconstructed.csv` | `03_SYNTHETIC_SUPPORT` | `warehouse_id + product_id + week_id` | 417,000 | 139 weeks | **RECONSTRUCTED_SYNTHETIC** |

---

## 4. Authoritative Identifier Standard

All datasets adhere strictly to canonical primary keys established in project governance:
- **Product ID**: `BAB-001` through `STA-020` (200 SKUs across 10 retail categories)
- **Location ID**: `KOL-LOC-001` through `KOL-LOC-040` (40 delivery zones in Kolkata)
- **Warehouse ID**: `WH-KOL-001` through `WH-KOL-015` (**Mandatory format**, never compressed to `WH-001`)
- **Supplier ID**: `SUP-001` through `SUP-200`
- **Week ID**: `W001` through `W139` (matching `week_start_date` 2024-01-01 through 2026-08-25)

---

## 5. Provenance & Boundary Rules

1. **Synthetic Data Governance**:
   - `inventory_transactions_reconstructed.csv` represents mathematically reconstructed warehouse movements.
   - It is explicitly tagged `RECONSTRUCTED_SYNTHETIC` and must never be relabeled as real/observed operational telemetry.
2. **Deferred Entities**:
   - **Vehicle Master** and **Customer Order Data** remain **DEFERRED** — no synthetic records are fabricated.
3. **Distance Clarification**:
   - All spatial distances in `02_DERIVED_REFERENCE` are computed via the spherical **Haversine formula**. They represent straight-line geographic distances and are **NOT road network distances or travel times**.
4. **Source Immutability**:
   - The contents of `Datasets/raw_dataset/` are read-only and frozen.
