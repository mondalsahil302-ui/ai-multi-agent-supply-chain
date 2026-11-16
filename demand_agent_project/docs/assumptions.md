# Demand Agent: System Assumptions & Design Invariants

This document records all architectural, data, domain, and operational assumptions made in the design and implementation of the single-agent Demand Forecasting subsystem.

---

## 1. Domain & Spatial-Temporal Scoping
1. **Target Geography & Warehouses:**
   - The operational modeling region is Kolkata, India (`Asia/Kolkata` timezone).
   - Primary operational warehouse: `WH-001` (South City Mall Warehouse, Jadavpur / Lake Gardens), mapped 1:1 to spatial region identifier `KOL-LOC-001`.
   - Regions `KOL-LOC-002` through `KOL-LOC-040` represent out-of-scope regions for Phase 1. Any request for unpopulated warehouses will trigger a deterministic "Data Not Ready" response from the Data Readiness Gate.
2. **Temporal Cadence:**
   - Granularity is strictly **weekly** (Monday to Sunday, or Sunday-anchored business week per calendar definition).
   - All models predict 1-step-ahead weekly demand ($t+1$) for a target week $[W_{\text{start}}, W_{\text{end}}]$.
   - Forecast horizon is 1 week for tactical replenishment.

---

## 2. Data & Ingestion Assumptions
1. **Source of Truth:**
   - MongoDB (`demand_agent` database) is the authenticated, persistent single source of truth.
   - Historical demand is loaded once and treated as immutable historical actuals.
   - Real-time weather and festival ingestion is scheduled via Airflow DAGs.
2. **Weather Invariants:**
   - Historical weather features are derived from observed meteorological records (`weather_history`).
   - Inference weather features are derived exclusively from genuine numerical weather forecasts (`weather_forecasts`) issued prior to the target forecast week.
   - If weather forecasts are unavailable or fail freshness bounds, fallback procedures or a no-weather model feature mask are applied.
3. **Festival & Calendar Invariants:**
   - Regional festival calendar is derived from official Calendarific / gazetted holiday feeds for West Bengal (`IN-WB`).
   - Festival features use lead/lag proximity indicators ($\le 7$ days, lead-up window, festival week flag).
4. **Stockout Censoring:**
   - When `stockout_flag == 1`, recorded sales understate true unconstrained customer demand.
   - Stockout weeks are excluded from model training to prevent learning artificial zero/low-demand bias.
   - During feature generation for inference, stockout weeks are flagged and handled safely.

---

## 3. Modeling & Gating Assumptions
1. **Model Architecture Hierarchy:**
   - **Primary / Champion Model:** Ridge Regression trained per product SKU over a 34-feature contract with expanding-window cross-validation for hyperparameter $\alpha \in [0.01, 1000.0]$.
   - Target is log-transformed $\ln(1 + \text{units})$ with Duan's smearing factor $\mathbb{E}[\exp(e)]$ and calibrated empirical residual quantiles ($P_{10}, P_{50}, P_{90}$).
   - **Standby Model:** Global Pooled LightGBM regressor on scale-free target $\ln(1 + \text{units}) - \text{demand\_level\_log1p}$, encoding category codes, trained with early stopping.
   - **Baseline Models:** 52-week seasonal naive and 8-week trailing moving median.
2. **Model Quality Gate (Rule C):**
   - Approval requires:
     1. $\text{WAPE} \le 35.0\%$
     2. $|\text{Bias}| \le 10.0\%$
     3. $\text{WAPE}_{\text{candidate}} - \min(\text{WAPE}_{\text{median}}, \text{WAPE}_{\text{seasonal}}) \le 1.0\text{ pt}$
   - Rejection preserves the existing approved champion. Rejection never halts the pipeline; it routes products through the Recovery Fallback Ladder.

---

## 4. Execution & Failure Isolation Assumptions
1. **Task Isolation:**
   - Batch forecast execution shards by `(product_id, region_id, target_week)`.
   - Each task executes independently. A data corruption, feature generation failure, or model exception on Product $A$ is quarantined and recorded as a task error without interrupting or invalidating forecasts for Products $B \dots Z$.
2. **Recovery Ladder Execution:**
   - Every product forecast attempts Champion Ridge $\rightarrow$ Standby LightGBM $\rightarrow$ Baseline $\rightarrow$ Explicit Failure (`"No Safe Forecast Available"`).
   - Predictions are never made up, interpolated from unvalidated proxies, or returned as unhandled exceptions.
3. **Non-Blocking Explainability:**
   - Explainability (SHAP feature attribution + LLM synthesis) is asynchronous and decoupled from forecast persistence.
   - If the LLM provider (Gemini API) experiences latency, rate limiting, or network timeouts, the system falls back to a deterministic rule-based template.
   - A failure in text generation will **never** withhold numerical forecast delivery.

---

## 5. Security & Infrastructure Assumptions
1. **Credentials & Secrets:**
   - No credentials, API keys, or connection strings are hardcoded in application source code.
   - All components authenticate via environment variables (`.env`).
   - All API endpoints (except `/health`) require API Key (`X-API-Key`) or JWT Bearer authentication.
2. **Database Privileges:**
   - Forecasting operations utilize least-privilege authenticated database access.
   - Ingestion writes are isolated to safe, idempotent upsert operations.
