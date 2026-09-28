# Data Integration Layer Documentation

## 1. Overview & Pipeline Role

The **Data Integration Layer** (`04_data_integration.ipynb`) joins standardized datasets using the validated relationships established in Entity Mapping. It creates unified, domain-level integrated datasets (`Datasets/integrated/*.csv`), domain-specific agent consumption views, and the central cross-domain dataset `supply_chain_core.csv`.

```
 ENTITY MAPPING
       ↓
DATA INTEGRATION   ← Layer 4
       ↓
FEATURE ENGINEERING
```

---

## 2. Integration Boundary & Strict Rules

1. **Controlled Joins Only**: Joins are strictly many-to-one or one-to-one to guarantee zero Cartesian products and zero unexpected row multiplication.
2. **Grain Preservation**:
   - Demand Grain: strictly `location × product × week` ($40 \times 200 \times 139 = 1,112,000$ rows).
   - Inventory Grain: strictly `warehouse × product` ($15 \times 200 = 3,000$ rows).
   - Transaction Grain: strictly `warehouse × product × week` ($15 \times 200 \times 139 = 417,000$ rows).
3. **No ML Transformations**: Integration does NOT perform lag computation, rolling averages, scaling, target generation, or forecasting.
4. **Deferred Entities Preserved**: Vehicle Master and Customer Order Data remain deferred; no records are fabricated.

---

## 3. Integrated Dataset Catalog (`Datasets/integrated/`)

| Integrated Dataset | Domain | Primary Key / Grain | Row Count | Source Inputs |
|---|---|---|---|---|
| `demand_integrated.csv` | Demand | `region_product_week_key` | 1,112,000 | `std_sales_demand`, `std_calendar_week`, `std_weather_events` |
| `inventory_integrated.csv` | Inventory | `warehouse_id + product_id` | 3,000 | `std_inventory_position`, `std_product_master`, `std_warehouse_master` |
| `inventory_transactions_integrated.csv` | Inventory Movement | `warehouse_product_week_key` | 417,000 | `std_inventory_transactions`, `std_warehouse_master` (SYNTHETIC) |
| `product_integrated.csv` | Product | `product_id` | 200 | `std_product_master` |
| `location_integrated.csv` | Location | `location_id` | 40 | `std_location_master` |
| `warehouse_integrated.csv` | Warehouse | `warehouse_id` | 15 | `std_warehouse_master` |
| `supplier_integrated.csv` | Supplier | `supplier_id` | 200 | `std_supplier_master` |
| `supplier_product_integrated.csv`| Supplier-Product | `supplier_id + product_id` | 8,000 | `std_supplier_product_catalog`, `std_product_master` |
| `supplier_area_integrated.csv` | Supplier-Area | `supplier_id + location_id` | 200 | `std_supplier_master`, `std_location_master` |
| `warehouse_picker_integrated.csv`| Warehouse Workforce | `warehouse_id + picker_id` | 750 | `std_warehouse_picker_mapping` |
| `warehouse_location_integrated.csv`| Logistics Proximity | `warehouse_id + location_id` | 75 | `em_warehouse_location_map` (Top-5 Nearest) |
| `calendar_integrated.csv` | Calendar | `week_id` | 139 | `std_calendar_week` |
| `weather_event_integrated.csv` | Environmental | `week_id` | 139 | `std_weather_events` |
| `supply_chain_core.csv` | Cross-Domain Core | `region_product_week_key` | 1,112,000 | Integrated demand joined with product & location dimensions |

---

## 4. Agent Consumption Views

To support downstream multi-agent operations, domain-tailored integrated views are published:
- `agent_demand_integrated.csv`: Clean demand history, promotions, discounts, holiday, and weather events.
- `agent_inventory_integrated.csv`: Warehouse stock levels, target units, safety stock, and space utilization.
- `agent_warehouse_integrated.csv`: Warehouse operational parameters, dispatch capacities, and assigned pickers.
- `agent_supplier_integrated.csv`: Vendor lead times, minimum order quantities (MOQ), and shipping capacities.

---

## 5. Governance & Reports

The data integration layer writes validation reports to `Datasets/reports/`:
- `integration_final_report.csv`: Master integration sign-off report.
- `integration_input_catalog.csv`: Inventory of all standardized inputs consumed.
- `integration_reconciliation_report.csv`: Source-to-integrated row count reconciliation.
- `integration_validation_report.csv`: Foreign key and cardinality check results.
- `integration_summary.csv`: Summary of all generated integrated outputs.
