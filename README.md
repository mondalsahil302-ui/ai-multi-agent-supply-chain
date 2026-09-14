# AI Multi-Agent Supply Chain

An AI-powered decision platform for planning and optimizing an end-to-end supply chain. The project combines demand forecasting, inventory intelligence, supplier selection, warehouse planning, and route optimization into one coordinated workflow.

## End-to-End Project Blueprint

The diagram below shows how raw business data becomes an explainable supply-chain decision.

```mermaid
flowchart TB
	subgraph INPUTS[1. Business data sources]
		SALES[Historical sales and demand]
		INV[Inventory transactions]
		PROD[Product master]
		LOC[Location and warehouse master]
		SUP[Supplier data and constraints]
		WEATHER[Weather history]
		EVENTS[Festival and seasonal calendar]
	end

	subgraph DATA[2. Data preparation and shared context]
		INGEST[Ingestion layer]
		VALIDATE[Data quality checks<br/>IDs, dates, units, missing values]
		FEATURE[Feature engineering<br/>trends, seasonality, weather, events]
		STORE[(Shared supply-chain<br/>data and feature layer)]
	end

	subgraph AGENTS[3. Specialist AI agents]
		DEMAND[Demand agent<br/>Forecast demand and confidence]
		INVENTORY[Inventory agent<br/>Safety stock and reorder points]
		SUPPLIER[Supplier agent<br/>Cost, quality, and lead-time trade-offs]
		WAREHOUSE[Warehouse agent<br/>Capacity and allocation]
		ROUTING[Routing agent<br/>Delivery sequence and transport cost]
	end

	subgraph DECISION[4. Coordination and decision layer]
		ORCHESTRATOR[Agent orchestrator<br/>Coordinates dependencies and priorities]
		OPTIMIZER[Constraint and optimization engine<br/>Service level, cost, capacity, distance]
		EXPLAIN[Explanation and KPI layer<br/>Risks, assumptions, and recommended actions]
	end

	subgraph OUTPUTS[5. Business outcomes]
		PLAN[Demand and replenishment plan]
		SOURCING[Supplier and purchase recommendation]
		WAREHOUSE_PLAN[Warehouse allocation plan]
		DELIVERY[Optimized delivery routes]
		DASHBOARD[Planner dashboard or API]
	end

	SALES --> INGEST
	INV --> INGEST
	PROD --> INGEST
	LOC --> INGEST
	SUP --> INGEST
	WEATHER --> INGEST
	EVENTS --> INGEST
	INGEST --> VALIDATE --> FEATURE --> STORE

	STORE --> DEMAND
	STORE --> INVENTORY
	STORE --> SUPPLIER
	STORE --> WAREHOUSE
	STORE --> ROUTING

	DEMAND --> ORCHESTRATOR
	INVENTORY --> ORCHESTRATOR
	SUPPLIER --> ORCHESTRATOR
	WAREHOUSE --> ORCHESTRATOR
	ROUTING --> ORCHESTRATOR
	ORCHESTRATOR --> OPTIMIZER --> EXPLAIN

	EXPLAIN --> PLAN
	EXPLAIN --> SOURCING
	EXPLAIN --> WAREHOUSE_PLAN
	EXPLAIN --> DELIVERY
	PLAN --> DASHBOARD
	SOURCING --> DASHBOARD
	WAREHOUSE_PLAN --> DASHBOARD
	DELIVERY --> DASHBOARD
	DASHBOARD -. Planner feedback .-> INGEST
```

## How the Agents Work Together

```mermaid
sequenceDiagram
	actor Planner
	participant Orchestrator
	participant Demand as Demand agent
	participant Inventory as Inventory agent
	participant Supplier as Supplier agent
	participant Warehouse as Warehouse agent
	participant Route as Routing agent

	Planner->>Orchestrator: Request a supply-chain plan
	Orchestrator->>Demand: Forecast future demand
	Demand-->>Orchestrator: Forecast and confidence
	Orchestrator->>Inventory: Evaluate stock and replenishment
	Inventory-->>Orchestrator: Reorder quantities and risk
	Orchestrator->>Supplier: Evaluate sourcing options
	Supplier-->>Orchestrator: Supplier recommendation
	Orchestrator->>Warehouse: Allocate inventory and capacity
	Warehouse-->>Orchestrator: Warehouse plan
	Orchestrator->>Route: Optimize deliveries
	Route-->>Orchestrator: Routes, distance, and cost
	Orchestrator->>Orchestrator: Apply constraints and rank options
	Orchestrator-->>Planner: Explainable recommendation and KPIs
```

## Core Decision Loop

```mermaid
flowchart LR
	A[Observe<br/>Sales, stock, capacity, context] --> B[Predict<br/>Demand and risk]
	B --> C[Decide<br/>Buy, move, store, deliver]
	C --> D[Optimize<br/>Cost, service level, constraints]
	D --> E[Act<br/>Execute the plan]
	E --> F[Measure<br/>Actuals and KPIs]
	F --> A
```

## Main Capabilities

| Capability | Main question answered | Typical output |
| --- | --- | --- |
| Demand intelligence | What will customers need, and how certain is the forecast? | Forecast, confidence, and demand drivers |
| Inventory intelligence | What should be reordered, where, and when? | Safety stock, reorder point, and priority |
| Supplier selection | Which source best balances cost, quality, and lead time? | Ranked supplier and purchase recommendation |
| Warehouse management | Where should stock be stored or allocated? | Capacity-aware allocation plan |
| Route optimization | How should deliveries be sequenced? | Feasible route, distance, and transport estimate |
| Decision coordination | How do separate recommendations become one plan? | Explainable, constraint-aware action plan |

## Data Flow

```mermaid
flowchart LR
	A[CSV and Excel files] --> B[Canonical schemas]
	B --> C[Validated product, location, and time keys]
	C --> D[Joined analytical features]
	D --> E[Agent inputs]
	E --> F[Forecasts and recommendations]
	F --> G[Optimization and constraints]
	G --> H[Planner dashboard or API]
	H --> I[Feedback and actual results]
	I --> A
```

## Recommended Project Structure

```text
ai-multi-agent-supply-chain/
├── Datasets/              # CSV and Excel source data
├── src/
│   ├── ingestion/          # Load and normalize source files
│   ├── features/           # Build shared analytical features
│   ├── agents/             # Demand, inventory, supplier, warehouse, route agents
│   ├── optimization/       # Constraints and objective functions
│   └── orchestration/      # Coordinate agents and decisions
├── tests/                  # Data, model, and workflow tests
├── notebooks/              # Exploration and evaluation
└── README.md
```

## Getting Started

Clone the repository and install Git LFS when working with large Excel datasets:

```bash
git clone https://github.com/mondalsahil302-ui/ai-multi-agent-supply-chain.git
cd ai-multi-agent-supply-chain
git lfs install
git lfs pull
```

The current `main` branch is the project documentation and architecture baseline. The data-backed implementation is being developed on the project feature branch.

## Data Quality Rules

Before training or running an agent:

- Validate product and location IDs against their master tables.
- Standardize dates, quantities, currencies, and units of measure.
- Check duplicate transactions and missing historical periods.
- Join weather by week and events by date or an explicitly defined look-ahead window.
- Record forecast accuracy, service level, stockout rate, inventory value, and route cost.
- Preserve the assumptions used by every recommendation so planners can audit decisions.

## Implementation Roadmap

1. Define canonical schemas for demand, inventory, suppliers, warehouses, and routes.
2. Add reproducible ingestion, validation, and feature-engineering pipelines.
3. Implement each specialist agent with measurable evaluation criteria.
4. Add the orchestrator and constraint-based optimization layer.
5. Expose recommendations through a planner dashboard or API.
6. Add monitoring for drift, forecast accuracy, service level, and operating cost.

## License and Data Use

Add the project license and dataset provenance before public distribution. Confirm that every third-party, synthetic, or organization-provided dataset is authorized for the intended use.
