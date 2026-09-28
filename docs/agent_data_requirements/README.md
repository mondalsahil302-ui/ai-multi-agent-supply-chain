# Multi-Agent Data Requirements Specification

## 1. System Architecture Overview

The **Intelligent Multi-Agent Supply Chain Optimization Framework** coordinates seven autonomous, role-specialized operational agents. Each agent consumes curated datasets produced by the data-foundation pipeline, respects strict temporal and provenance boundaries, executes domain-specific decision logic, and collaborates via structured message-passing under the governance of the Coordinator Agent.

```
                    ┌────────────────────────┐
                    │   COORDINATOR AGENT    │
                    └───────────┬────────────┘
                                │
        ┌───────────────┬───────┴───────┬───────────────┐
        │               │               │               │
        ▼               ▼               ▼               ▼
┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐
│ DEMAND AGENT ││INVENTORY AGT ││ SUPPLIER AGT ││WAREHOUSE AGT │
└───────┬──────┘└───────┬──────┘└───────┬──────┘└───────┬──────┘
        │               │               │               │
        └───────────────┼───────────────┘               │
                        ▼                               ▼
                 ┌──────────────┐               ┌──────────────┐
                 │  RISK AGENT  │               │ ROUTE OPT AGT│
                 └──────────────┘               └──────────────┘
```

---

## 2. Comprehensive Agent Profiles & Data Contracts

### 2.1 Demand Agent

- **Objective**: Generates localized weekly SKU-level demand forecasts, captures seasonal trends, and identifies promotional or event-driven consumption surges.
- **Required Grain**: `location × product × week` (`region_id + product_id + week_id`)
- **Primary Business Key**: `region_product_week_key`
- **Datasets Consumed**:
  - `validated_demand_features.csv`
  - `agent_demand_integrated.csv`
- **Features Ingested**:
  - Historical Lags: `lag_1_demand`, `lag_2_demand`, `lag_3_demand`, `lag_4_demand`
  - Rolling Windows: `rolling_mean_4`, `rolling_mean_8`, `rolling_std_4`, `rolling_std_8`, `rolling_sum_4`
  - Trend Metrics: `demand_change`, `demand_growth_rate`
  - Cyclical Encodings: `sin_week`, `cos_week`, `month`, `quarter`, `season`
  - Environmental / Events: `temperature_mean_c`, `rainfall_mm`, `festival_flag`, `festival_count`, `holiday_flag`, `promotion_flag`, `discount_pct`
- **Boundaries**: Strictly evaluates on data $\leq t$; prediction targets ($\hat{D}_{t+1}$) are generated inside the downstream ML stage.
- **Decision Outputs**:
  - $\hat{D}_{l,p,t+1}$: Point forecast of weekly demand.
  - $\sigma_{l,p,t+1}$: Demand forecast uncertainty / variance.
  - Promotional lift multiplier and festival surge warnings.
- **Downstream Consumers**: Inventory Agent, Risk Agent, Coordinator Agent.

---

### 2.2 Inventory Agent

- **Objective**: Monitors multi-echelon stock health, calculates reorder points, tracks stockout risks, and balances stock cover against holding costs.
- **Required Grain**: `warehouse × product` (point-in-time) and `warehouse × product × week` (historical movement)
- **Primary Business Keys**: `warehouse_id + product_id`, `warehouse_product_week_key`
- **Datasets Consumed**:
  - `validated_inventory_features.csv`
  - `validated_inventory_transaction_features.csv`
  - `agent_inventory_integrated.csv`
- **Features Ingested**:
  - Stock Position: `available_stock_units`, `current_stock_units`, `reserved_stock_units`, `target_stock_units`
  - Derived Ratios: `stock_gap`, `stock_coverage` (runway weeks), `stockout_indicator`, `space_utilization_pct`
  - Movement History: `weekly_sold_units`, `rolling_sold_4w`
- **Boundaries**: All transaction movement features inherit **`RECONSTRUCTED_SYNTHETIC`** provenance and must not be treated as empirical telemetry. Zero future demand is used in coverage ratios.
- **Decision Outputs**:
  - Recommended replenishment orders $Q_{w,p}$ per warehouse.
  - Stock reorder trigger flags (`reorder_required = True`).
  - Stockout risk alerts sent to Coordinator Agent.
- **Downstream Consumers**: Supplier Agent, Warehouse Agent, Risk Agent, Coordinator Agent.

---

### 2.3 Warehouse Agent

- **Objective**: Manages fulfillment center throughput, monitors storage space utilization, allocates picker workforce, and evaluates daily dispatch limits.
- **Required Grain**: `warehouse` (`warehouse_id`)
- **Primary Business Key**: `warehouse_id` (Canonical: `WH-KOL-001` through `WH-KOL-015`)
- **Datasets Consumed**:
  - `validated_warehouse_features.csv`
  - `agent_warehouse_integrated.csv`
- **Features Ingested**:
  - Storage & Operational: `capacity_units`, `daily_dispatch_capacity_units`, `service_radius_km`
  - Fleet Constraints: `total_vehicle_count`, `bike_count`, `scooter_count`, `auto_count`
  - Labor & Load: `wh_picker_count` (50 pickers/wh), `wh_inventory_load` (current stock / capacity)
- **Boundaries**: Does not perform vehicle assignment (Vehicle Master DEFERRED). Does not optimize picking paths.
- **Decision Outputs**:
  - Warehouse capacity utilization warnings ($\text{load} > 85\%$).
  - Dispatch throughput availability ($C_{\text{avail}} = C_{\text{daily}} - C_{\text{committed}}$).
  - Picker labor availability and staging clearance confirmation.
- **Downstream Consumers**: Route Optimization Agent, Coordinator Agent.

---

### 2.4 Supplier Agent

- **Objective**: Evaluates vendor lead times, minimum order quantities (MOQ), supplier production/storage capacity, and procurement unit costs to fulfill restocking orders.
- **Required Grain**: `supplier` (`supplier_id`) and `supplier × product` (`supplier_id + product_supplied_id`)
- **Primary Business Keys**: `supplier_id`, `supplier_product_key`
- **Datasets Consumed**:
  - `validated_supplier_features.csv`
  - `validated_supplier_product_features.csv`
  - `validated_supplier_area_features.csv`
  - `agent_supplier_integrated.csv`
- **Features Ingested**:
  - Vendor Constraints: `lead_time_days`, `minimum_order_qty_units`, `max_order_qty_units`, `supplier_storage_capacity_units`
  - Commercial Terms: `supplier_cost_price_rs`, `supply_status` (`Active` / `Inactive`)
  - Geographical Reach: `distance_from_location_center_km`, `service_available_flag`
- **Boundaries**: Does not calculate arbitrary vendor rankings or subjective scores in feature layers.
- **Decision Outputs**:
  - Optimal supplier selection for purchase orders $PO(s, p, Q)$.
  - Expected delivery ETA based on vendor `lead_time_days`.
  - Batching / MOQ compliance confirmations.
- **Downstream Consumers**: Inventory Agent, Risk Agent, Coordinator Agent.

---

### 2.5 Risk Agent

- **Objective**: Evaluates supply chain vulnerability, detects simultaneous weather and stockout risks, monitors supplier lead time fragility, and assesses buffer stock adequacy.
- **Required Grain**: Multi-echelon cross-domain grain (Region × Warehouse × Supplier)
- **Datasets Consumed**:
  - `validated_demand_features.csv`
  - `validated_inventory_features.csv`
  - `validated_supplier_features.csv`
  - `weather_event_integrated.csv`
- **Features Ingested**:
  - Environmental Disruptions: `high_rainfall_flag` ($>50\text{mm}$), `temp_deviation_c`, `weather_condition`
  - Buffer Fragility: `stockout_indicator`, `stock_coverage` $< 1.5 \text{ weeks}$, `shortage_units`
  - Supplier Exposure: `lead_time_days` $> 7 \text{ days}$, single-source supplier dependencies
- **Boundaries**: Generates objective probabilistic risk indicators; does not unilaterally cancel operations without Coordinator consent.
- **Decision Outputs**:
  - Node vulnerability score $R_{\text{node}} \in [0, 1]$.
  - Weather disruption warnings for specific delivery zones.
  - Recommended buffer stock escalations for high-risk SKUs.
- **Downstream Consumers**: Coordinator Agent, Inventory Agent, Route Optimization Agent.

---

### 2.6 Route Optimization Agent

- **Objective**: Solves last-mile logistics delivery problems using hybrid metaheuristic routing (Genetic Algorithm / Simulated Annealing), respecting vehicle capacities and delivery windows.
- **Required Grain**: `warehouse × location` (`warehouse_id + location_id`)
- **Primary Business Key**: `warehouse_id + location_id`
- **Datasets Consumed**:
  - `validated_routing_features.csv`
  - `validated_supplier_routing_features.csv`
  - `validated_warehouse_features.csv`
  - `em_location_dim.csv`
- **Features Ingested**:
  - Spatial Distance: `wh_location_haversine_km`, `supplier_location_haversine_km`
  - Metadata Label: **`HAVERSINE_GEOGRAPHIC_NOT_ROAD`** (Mandatory transparent flag)
  - Proximity Hierarchy: `mapping_rank` (Top-5 nearest warehouses per location)
  - Fleet Limits: `total_vehicle_count`, `bike_count`, `scooter_count`
- **Boundaries**: Straight-line distance must never be treated as road distance or travel time. Optimization logic executes inside the metaheuristic module, not in the data pipeline.
- **Decision Outputs**:
  - Optimized dispatch clusters and delivery stop sequences.
  - Estimated vehicle load allocation per trip.
  - Logistics fulfillment cost estimates.
- **Downstream Consumers**: Warehouse Agent, Coordinator Agent.

---

### 2.7 Coordinator Agent

- **Objective**: Orchestrates global multi-agent alignment, resolves inter-agent resource conflicts (e.g. inventory shortages vs warehouse capacity constraints), and enforces end-to-end optimization objectives.
- **Required Grain**: Global system state (Aggregated multi-domain metrics)
- **Datasets Consumed**:
  - `supply_chain_core.csv`
  - `feature_validation_summary.csv`
  - Output messages and proposals from all specialized agents
- **Features Ingested**:
  - System-wide demand velocity, aggregate stock coverage, warehouse capacity headroom, and regional risk indices.
- **Boundaries**: Operates as the central consensus engine. Does not bypass data validation standards.
- **Decision Outputs**:
  - Approval / rejection of replenishment purchase orders.
  - Inter-warehouse stock rebalancing directives.
  - Final execution plan for regional delivery dispatch.
- **Downstream Consumers**: Human operators, executive dashboards, execution sidecars.

---

## 3. Inter-Agent Communication & Protocol Matrix

| Sender Agent | Receiver Agent | Message Type | Payload Structure | Trigger Condition |
|---|---|---|---|---|
| **Demand Agent** | **Inventory Agent** | `DEMAND_FORECAST_UPDATE` | `product_id, location_id, week_id, forecast_units, uncertainty_std` | Weekly cycle / Event alert |
| **Inventory Agent** | **Supplier Agent** | `REPLENISHMENT_REQUEST` | `warehouse_id, product_id, order_qty, target_delivery_date` | Stock coverage $< \text{threshold}$ |
| **Supplier Agent** | **Inventory Agent** | `ORDER_CONFIRMATION` | `supplier_id, order_qty, lead_time_days, cost_rs, confirmed_eta` | Upon PO receipt |
| **Inventory Agent** | **Warehouse Agent** | `INBOUND_STAGING_NOTICE` | `warehouse_id, product_id, units, eta_timestamp` | Confirmed supplier shipment |
| **Warehouse Agent**| **Route Opt Agent**| `DISPATCH_AVAILABILITY` | `warehouse_id, dispatch_capacity, fleet_available` | Daily dispatch planning |
| **Risk Agent** | **Coordinator Agent**| `RISK_ALERT_ESCALATION` | `region_id, risk_factor, severity_score, recommended_action`| Severe weather / Stockout threat |
| **Route Opt Agent**| **Coordinator Agent**| `ROUTING_PLAN_PROPOSAL` | `route_id, warehouse_id, stop_list, total_distance_km, vehicle_type`| Route optimization complete |
| **Coordinator Agent**| **ALL AGENTS** | `GLOBAL_CONSENSUS_PLAN` | `plan_id, execution_schedule, resource_commitments` | Cycle reconciliation complete |
