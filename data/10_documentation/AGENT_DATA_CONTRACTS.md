# Agent Data Contracts

## Demand Agent
**Inputs**:
- `DEMAND_FEATURES.csv` — features for prediction (lag, rolling mean, promotion, weather, festival)
- `DEMAND_TARGETS.csv` — prediction target (next_week_demand_target_units)
- `FACT_SALES.csv` — 448,000 regional weekly sales transaction records (replaces blocked sales history)
- `DIM_LOCATION.csv`, `DIM_PRODUCT.csv`, `DIM_WEATHER.csv`, `DIM_FESTIVAL.csv`

**Output**:
- Predicted next-period demand (units) per location+product
- Demand forecasts benchmarked against true historical sales

**Leakage Guard**: `next_week_demand_target_units` is in DEMAND_TARGETS only — not in DEMAND_FEATURES.

**Agent Readiness**: READY

---
## Inventory Agent
**Inputs**:
- `INVENTORY_FEATURES.csv` — current stock positions, utilization, reorder flags
- `FACT_INVENTORY_TRANSACTION.csv` — 417,000 inventory movement transactions (replaces blocked transactions)
- `DIM_PRODUCT.csv`, `DIM_WAREHOUSE.csv`

**Output**:
- Shortage detection, reorder recommendations, inventory velocity, replenishment alerts

**Agent Readiness**: READY

---
## Supply Agent
**Inputs**:
- `SUPPLY_FEATURES.csv` — supplier catalog, MOQ, lead times, vehicle info
- `BRIDGE_SUPPLIER_PRODUCT.csv`, `BRIDGE_LOCATION_SUPPLIER.csv`

**Output**:
- Candidate suppliers, procurement quantities, costs, lead times

**Note**: Column `unmapped_col_10_quarantine` in BRIDGE_SUPPLIER_PRODUCT requires domain review.

**Agent Readiness**: READY_WITH_WARNINGS (unmapped column unresolved)

---
## Warehouse Agent
**Inputs**:
- `WAREHOUSE_FEATURES.csv` — capacity, dispatch, vehicles, operating hours, `assigned_picker_count` (50 pickers/warehouse)
- `BRIDGE_WAREHOUSE_LOCATION.csv`, `FACT_INVENTORY_POSITION.csv`
- `DIM_PICKER.csv`, `BRIDGE_WAREHOUSE_PICKER.csv` — warehouse-to-picker assignment relationship

**Output**:
- Fulfillment warehouse selection, dispatch feasibility, assigned picker identification

**Picker Queries Supported**:
- Which warehouse? -> `warehouse_id`
- How many pickers assigned? -> `assigned_picker_count` (50 per active facility)
- Which picker IDs belong to it? -> `BRIDGE_WAREHOUSE_PICKER.picker_id` (e.g., WH-001 -> WH-001-PKR-001 ... WH-001-PKR-050)

**Agent Readiness**: READY

---
## Risk Agent
**Inputs**:
- `RISK_FEATURES_INVENTORY.csv` — shortage/reorder risk
- `RISK_FEATURES_DEMAND.csv` — stockout + weather + festival risk signals
- `RISK_FEATURES_SUPPLY.csv` — supplier lead time risk
- `FACT_INVENTORY_TRANSACTION.csv` — movement velocity risk

**Output**:
- Structured risk indicators per entity

**Agent Readiness**: READY

---
## Route Optimization Agent
**Inputs**:
- `ROUTING_FEATURES.csv` — warehouse-location and supplier-location euclidean distances
- `DIM_WAREHOUSE.csv`, `DIM_LOCATION.csv`, `DIM_SUPPLIER.csv`

**Output**:
- Feasible route inputs

**Critical Note**: `euclidean_distance_km` is Haversine only — NOT road distance.

**Agent Readiness**: READY_WITH_WARNINGS (no road network data available)

---
## Coordinator Agent
**Inputs**: Outputs from all 6 agents above.

**Agent Readiness**: READY
