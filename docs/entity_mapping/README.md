# Entity Mapping Layer Documentation

## 1. Overview & Pipeline Role

The **Entity Mapping Layer** (`03_entity_mapping.ipynb`) establishes the relational integrity and dimensional backbone of the supply chain framework. It validates foreign-key constraints between disparate business entities, produces verified entity relationship mappings (`Datasets/entity_mapping/em_*.csv`), and generates relational ER diagrams.

```
STANDARDIZATION
       ↓
 ENTITY MAPPING   ← Layer 3
       ↓
DATA INTEGRATION
```

---

## 2. Relational Architecture & Dimensional Backbone

The entity mapping layer connects five primary master entities across the supply chain network:

```
[ Product Master ] ──< (1:N) >── [ Sales Demand Telemetry ] ──< (N:1) >── [ Location Master ]
        │                                                                         │
        ├──< (1:N) >── [ Inventory Snapshot / Txn ]                                │
        │                          │                                              │
        │                          └──< (N:1) >── [ Warehouse Master ] ──< (N:M) ─┘
        │                                                 │
        └──< (N:M) >── [ Supplier Master ]                └──< (1:N) >── [ Picker Mapping ]
```

---

## 3. Entity Mapping Dataset Catalog (`Datasets/entity_mapping/`)

| Mapping Dataset | Relationship | Source Datasets | Output Grain | Record Count |
|---|---|---|---|---|
| `em_product_dim.csv` | Product Dimension | `std_product_master` | `product_id` | 200 |
| `em_location_dim.csv` | Location Dimension | `std_location_master` | `location_id` | 40 |
| `em_warehouse_dim.csv` | Warehouse Dimension | `std_warehouse_master` | `warehouse_id` | 15 |
| `em_supplier_dim.csv` | Supplier Dimension | `std_supplier_master` | `supplier_id` | 200 |
| `em_calendar_dim.csv` | Calendar Dimension | `std_calendar_week` | `week_id` | 139 |
| `em_warehouse_location_map.csv` | Proximity Matrix | `std_warehouse_master`, `std_location_master` | `warehouse_id + location_id` | 75 (Top-5 Nearest) |
| `em_supplier_product_map.csv` | Vendor Sourcing | `std_supplier_master`, `std_product_master` | `supplier_id + product_id` | 8,000 |
| `em_supplier_area_map.csv` | Service Coverage | `std_supplier_master`, `std_location_master` | `supplier_id + location_id` | 200 |
| `em_warehouse_picker_map.csv` | Workforce Allocation | `std_warehouse_picker_mapping` | `warehouse_id + picker_id` | 750 |
| `em_inventory_dim.csv` | Stock Positioning | `std_inventory_position` | `warehouse_id + product_id` | 3,000 |
| `em_sales_demand_dim.csv` | Demand Grain Map | `std_sales_demand` | `region_id + product_id + week_id` | 1,112,000 |
| `em_inventory_transactions_dim.csv`| Warehouse Throughput | `std_inventory_transactions` | `warehouse_id + product_id + week_id` | 417,000 |

---

## 4. Foreign Key Audits & Referential Integrity

1. **Product FK Integrity**: Every `product_id` appearing in demand (1.112M rows), inventory snapshots (3,000 rows), and supplier catalogs (8,000 rows) is verified to exist in `product_master.csv`. Orphan keys: **0**.
2. **Location FK Integrity**: Every `region_id` in sales demand maps cleanly to a valid `location_id` in `location_master.csv`. Orphan keys: **0**.
3. **Warehouse FK Integrity**: All warehouse foreign keys in picker mappings, inventory positions, and proximity matrices strictly match `WH-KOL-001` through `WH-KOL-015`. Orphan keys: **0**.
4. **Calendar FK Integrity**: Every `week_id` in sales demand, transaction logs, and weather events matches `calendar_week.csv`. Orphan keys: **0**.

---

## 5. ER Diagrams & Visual Documentation

Relational ER diagrams are maintained under [`docs/entity_mapping_diagrams/`](file:///d:/ai-multi-agent-supply-chain/docs/entity_mapping_diagrams/):
- `full_er_diagram.jpg`: Comprehensive global schema across all 13 mapped dimensions.
- `block03_product_er.jpg` through `block15_txn_er.jpg`: Entity-specific relationship diagrams.
- `block16_fk_audit_er.jpg`: Foreign key referential graph.

---

## 6. Governance & Reports

The entity mapping layer outputs governance artifacts to `Datasets/reports/`:
- `entity_mapping_final_report.csv`: Master validation summary.
- `entity_mapping_dimension_catalog.csv`: Field, type, and key catalog per dimension.
- `entity_mapping_fk_audit.csv`: Referential integrity check results.
- `em_cross_entity_fk_report.csv`: Cross-table foreign key audit log.
