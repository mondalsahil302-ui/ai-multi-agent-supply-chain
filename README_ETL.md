# Demand Dataset ETL & Feature Engineering Pipeline

Automated pipeline for **profiling**, **staging & standardization**, and **entity mapping** of the supply chain demand dataset for the Multi-Agent Supply Chain System.

---

## 🏗 Pipeline Architecture

```
                                  [Raw Files]
            D:\Downloads\Demand of last 2 years.xlsx (27,800 records)
            D:\Downloads\Location_ID_Master_40_For_Sharing.csv
            D:\Downloads\Product_ID_Master_200_For_Sharing.csv
                                       │
                                       ▼
                      ┌─────────────────────────────────┐
                      │      1. Data Profiling          │
                      │  (src/profiling.py)             │
                      │  - Null ratios & stats          │
                      │  - Key & referential integrity  │
                      │  - Business anomaly detection   │
                      └────────────────┬────────────────┘
                                       │
                                       ▼
                      ┌─────────────────────────────────┐
                      │  2. Staging & Standardization   │
                      │  (src/staging.py)               │
                      │  - Lowercase snake_case headers │
                      │  - ISO dates & integer counts   │
                      │  - Impute defaults / nulls      │
                      │  - Filter metadata columns      │
                      └────────────────┬────────────────┘
                                       │
                                       ▼
                      ┌─────────────────────────────────┐
                      │      3. Entity Resolution       │
                      │  (src/entity_mapping.py)        │
                      │  - Unpivot Product Master sizes │
                      │  - Join category, brand, tier   │
                      │  - Map 40 Kolkata Locations     │
                      └────────────────┬────────────────┘
                                       │
                   ┌───────────────────┴───────────────────┐
                   ▼                                       ▼
    [Demand Agent Standard Schema]            [ML Forecasting Feature Store]
   `demand_agent_standardized.xlsx`         `demand_forecasting_feature_store.parquet`
  Matches `demand agent sheet.xlsx`           Enriched with weather, festivals,
  for multi-agent inventory loops            promotions, price elasticities
```

---

## 📁 Project Structure

```
ai-multi-agent-supply-chain/
├── run_pipeline.py              # Main orchestrator CLI
├── requirements.txt             # Pipeline dependencies
├── data/
│   ├── staged/                  # Cleaned staged datasets (.parquet / .csv)
│   ├── processed/               # Mapped agent schemas & feature stores
│   └── reports/                 # Profiling reports (.md / .json)
└── src/
    ├── config.py                # File paths & schema settings
    ├── profiling.py             # Quality & referential integrity profiler
    ├── staging.py               # Ingestion, cleaning & standardization
    └── entity_mapping.py        # Master entity resolution & unpivoting
```

---

## 🚀 Execution Guide

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Run Complete Pipeline
```bash
python run_pipeline.py --all
```

### 3. Run Individual Steps
- **Profiling Only**:
  ```bash
  python run_pipeline.py --profile
  ```
  *(Generates `data/reports/demand_data_profile.md` and `demand_data_profile.json`)*

- **Staging & Standardization Only**:
  ```bash
  python run_pipeline.py --stage
  ```
  *(Generates `data/staged/staged_demand.parquet` and `data/staged/staged_demand.csv`)*

- **Entity Mapping Only**:
  ```bash
  python run_pipeline.py --map
  ```
  *(Generates `data/processed/demand_agent_standardized.xlsx` and `demand_forecasting_feature_store.parquet`)*
