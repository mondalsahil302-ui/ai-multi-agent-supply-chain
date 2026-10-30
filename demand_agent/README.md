# Demand Intelligence Agent

Autonomous demand forecasting and product ranking agent for the **Multi-Agent Supply Chain Optimization Framework**.

---

## 1. Overview & Capabilities

The **Demand Intelligence Agent** operates as an independent microservice responsible for:
1. **Next-Week Demand Forecasting**: Predicts forward sales volume in units per product across 40 Kolkata regional markets.
2. **Regional Top-10 Product Ranking**: Ranks demand within each region for downstream allocation and replenishment.
3. **SHAP Demand Driver Explanations**: Surfaces the top positive and negative features influencing each prediction.
4. **Governed Uncertainty Handling**: Enforces explicit omission of uncalibrated prediction intervals when calibrated conformal models are unavailable.
5. **Downstream Integration Contracts**: Emits standardized JSON schemas consumable by:
   - `Inventory_Intelligence_Agent`: Safety stock, reorder points, buffer sizing.
   - `Decision_Coordinator`: Cross-region stock rebalancing, supplier dispatch prioritization.

---

## 2. Directory Structure

```text
demand_agent/
├── __init__.py
├── config.py             # Feature blacklists, hyperparams, dataset constants
├── data_prep.py          # Chronological scaffolding, target alignment, gap detection
├── features.py           # Lag, rolling, region aggregate, calendar & price features
├── baselines.py          # Naive last-week & moving average benchmark models
├── train.py              # LightGBM & CatBoost training with time-based walk-forward
├── evaluate.py           # MAE, RMSE, R2, WAPE, Bias, Precision@K, NDCG@K, charts
├── pipeline.py           # End-to-end training orchestrator
├── schemas.py            # Pydantic v2 schemas for API requests & responses
├── service.py            # Singleton inference & SHAP explanation service
├── api.py                # Standalone FastAPI service
├── outputs/
│   ├── models/           # catboost_model.cbm, lightgbm_model.pkl, model_metadata.json
│   ├── metrics/          # evaluation_metrics.json, evaluation_metrics.csv
│   └── charts/           # Residuals, scatter, feature importance, walk-forward MAE
└── tests/
    ├── test_leakage.py   # 20 tests verifying exclusion of all future/leakage columns
    ├── test_temporal.py  # 19 tests verifying chronological splits, lag alignment, target shift
    └── test_api.py       # 14 tests verifying FastAPI endpoints, ranking, SHAP & error handling
```

---

## 3. Training & Evaluation Benchmark Results

Evaluated via strict chronological walk-forward testing on unseen future test weeks (Weeks 120–137, 2,059 test observations across 40 regions):

| Model | Samples | MAE | RMSE | $R^2$ | WAPE | Forecast Bias | Precision@5 | NDCG@5 | Demand Capture@5 |
|---|---|---|---|---|---|---|---|---|---|
| **Last-Week Naive** | 2,059 | 27.65 | 35.55 | -0.0131 | 0.2286 | +0.32 | 1.0000 | 0.9676 | 1.0000 |
| **4-Week Moving Average** | 1,547 | 24.47 | 31.19 | 0.2455 | 0.1977 | -1.59 | 1.0000 | 0.9721 | 1.0000 |
| **LightGBM Regressor** | 2,059 | 21.76 | 27.27 | 0.4039 | 0.1799 | +0.62 | 1.0000 | 0.9669 | 1.0000 |
| **CatBoost Regressor (Best)** | **2,059** | **20.50** | **26.01** | **0.4576** | **0.1695** | **+0.78** | **1.0000** | **0.9682** | **1.0000** |
| **Ensemble (Average)** | 2,059 | 20.91 | 26.33 | 0.4441 | 0.1729 | +0.70 | 1.0000 | 0.9672 | 1.0000 |

* **Best Validated Model**: **CatBoost Regressor** achieves the lowest MAE (20.50 units) and WAPE (16.95%), outperforming the Naive benchmark by **25.9%** and the 4-week Moving Average by **16.2%**.
* **Ranking Metrics Notice**: The provided dataset (`demand_agent_training.csv`) contains the top-5 anchor products per region-week (53 unique SKUs total). Ranking metrics were therefore evaluated at $K=5$ (the actual assortment depth) rather than $K=10$, as calculating top-10 metrics on groups with $\le 5$ items is mathematically invalid.

---

## 4. Leakage Prevention & Governance Guarantees

1. **Forward-Shifted Ground Truth**: Targets are constructed via strict `groupby(['location_id', 'product_id'])['units_sold'].shift(-1)` aligned to $+7$ days. The synthetic target column `next_week_demand_target_units` was proven during audit to only match actual sales 1.32% of the time, and was permanently blacklisted.
2. **Zero Forward Leakage**: All 19 leakage/metadata columns (`demand_rank`, `selling_unit_sheet`, `selling_unit_source_row`, `region_week_key`, etc.) are rigorously excluded from features.
3. **No Automatic Zero Imputation**: Missing intermediate weeks for an entity produce NaN lags rather than synthetic zero-sales, preventing artificial volatility dampening.
4. **Governed Uncertainty**: As required, forecast uncertainty intervals are omitted (`null`) because no calibrated conformal quantile model is present.

---

## 5. API Endpoints

### Run the FastAPI Service

```bash
python -m uvicorn demand_agent.api:app --host 0.0.0.0 --port 8000 --reload
```

Interactive OpenAPI Swagger UI is available at `http://localhost:8000/docs`.

### Key Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | System readiness, active model, date coverage |
| `GET` | `/api/v1/metrics` | Offline walk-forward evaluation metrics |
| `GET` | `/api/v1/regions` | List of all 40 supported Kolkata regions |
| `POST` | `/api/v1/forecast` | Forecast demand and rank products (JSON body) |
| `GET` | `/api/v1/forecast` | Forecast demand and rank products (Query params) |

### Sample Request: `POST /api/v1/forecast`

```json
{
  "target_week_start": "2026-08-24",
  "region": "Lake Gardens",
  "top_k": 10,
  "include_drivers": true,
  "model_name": "catboost"
}
```

### Sample Response

```json
{
  "agent_id": "Demand_Intelligence_Agent_v1",
  "target_week_start": "2026-08-24",
  "target_week_end": "2026-08-30",
  "forecast_cutoff_date": "2026-08-17",
  "model_name": "CatBoost Regressor (Best Validated)",
  "status": "success",
  "total_regions_processed": 1,
  "regions": [
    {
      "location_id": "KOL-LOC-001",
      "region_name": "Lake Gardens",
      "target_week_start": "2026-08-24",
      "target_week_end": "2026-08-30",
      "forecast_cutoff_date": "2026-08-17",
      "total_predicted_units": 382.45,
      "products_evaluated": 3,
      "returned_count": 3,
      "top_products": [
        {
          "product_id": "INS-009",
          "product_name": "Quaker Oats",
          "category_name": "Instant & Packaged Foods",
          "brand": "Quaker",
          "unit_size": "1 kg",
          "predicted_demand_units": 139.12,
          "demand_rank": 1,
          "uncertainty": null,
          "demand_drivers": [
            {
              "feature_name": "lag_1w",
              "shap_value": 7.42,
              "impact_direction": "positive",
              "description": "Sales volume in the prior week (positive impact: +7.4 units)"
            },
            {
              "feature_name": "roll_mean_4w",
              "shap_value": 4.18,
              "impact_direction": "positive",
              "description": "4-week moving average demand baseline (positive impact: +4.2 units)"
            }
          ]
        }
      ],
      "assortment_coverage_note": "Returned 3 products (maximum available in regional top-5 anchor dataset: 3). Requested top_k=10."
    }
  ],
  "governance_metadata": {
    "leakage_prevention": "Strict cutoff filter enforced; only observations <= cutoff_date utilized.",
    "calibrated_uncertainty_model_exists": false,
    "uncertainty_policy": "Uncertainty intervals omitted because no calibrated conformal/quantile model is trained.",
    "assortment_depth": "Top-5 regional anchor items per region-week (53 unique SKUs total).",
    "downstream_interfaces": [
      "Inventory_Intelligence_Agent",
      "Decision_Coordinator"
    ]
  }
}
```

---

## 6. Running the Unit Tests

```bash
python -m pytest demand_agent/tests/ -v
```

**Test Suite Coverage (53/53 Passed)**:
- `test_leakage.py`: 20 unit tests verifying zero future-data leakage and complete feature blacklist enforcement.
- `test_temporal.py`: 19 unit tests verifying forward-shifted target alignment, date continuity, and lag computation.
- `test_api.py`: 14 integration tests verifying input validation, status codes, top-product ranking, SHAP attributions, and uncertainty compliance.

