# Intelligent Multi-Agent Supply Chain Optimization Framework
### *Using Machine Learning and Hybrid Metaheuristic Routing*

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Data Pipeline](https://img.shields.io/badge/pipeline-layer%206%20complete-brightgreen.svg)]()
[![Governance](https://img.shields.io/badge/governance-zero%20leakage%20verified-success.svg)]()
[![Git LFS](https://img.shields.io/badge/git--lfs-managed-orange.svg)](https://git-lfs.github.com/)

---

## 1. Executive Summary

This repository implements the data-foundation and operational architecture for an **Intelligent Multi-Agent Supply Chain Optimization Framework**. Focused on the metropolitan retail supply chain ecosystem of Kolkata, India, the framework integrates multi-echelon demand forecasting, inventory rebalancing, warehouse dispatch management, vendor sourcing, and last-mile logistics routing across seven specialized autonomous agents.

---

## 2. Completed Data-Foundation Pipeline

The pipeline processes raw source telemetry through six immutable, audited governance layers:

```
01. RAW DATA INGESTION    (Sales telemetry, master dimensions, distance matrices)
        ↓
02. STAGING               (snake_case normalization, SHA-256 record hashing, zero row loss)
        ↓
03. STANDARDIZATION       (Canonical typing, UOM normalization, WH-KOL-### validation)
        ↓
04. ENTITY MAPPING        (FK integrity verification, dimensional backbone, ER diagrams)
        ↓
05. DATA INTEGRATION      (19 integrated datasets, demand integration, agent views)
        ↓
06. FEATURE ENGINEERING   (55 features across 9 groups, demand lags, rolling, trend, weather)
        ↓
07. FEATURE VALIDATION    (34 blocks, zero leakage, zero infinite values, 18 audit reports)
        ↓
08. TARGET GENERATION     [Next Stage: Machine Learning Preparation]
        ↓
09. AGENT-READY ML        [Next Stage: Multi-Agent Deployment]
```

---

## 3. Project Directory Structure

```
ai-multi-agent-supply-chain/
├── Datasets/
│   ├── raw_dataset/                    # Immutable raw source workbooks & references
│   │   ├── 01_RAW_SOURCE/              # Sales workbook (1.112M rows), masters, snapshots
│   │   ├── 02_DERIVED_REFERENCE/       # Haversine distance matrices
│   │   ├── 03_SYNTHETIC_SUPPORT/       # Reconstructed transactions (417K rows, SYNTHETIC)
│   │   └── 04_CATALOG_QA/              # Source catalog audit
│   ├── staging/                        # Staged datasets with SHA-256 hashes (stg_*.csv)
│   ├── standardized/                   # Standardized, canonically typed datasets (std_*.csv)
│   ├── entity_mapping/                 # Verified entity dimensions & mappings (em_*.csv)
│   ├── integrated/                     # Domain & agent integrated datasets (*_integrated.csv)
│   ├── feature_engineered/             # 55 engineered features (*_features.csv)
│   ├── feature_validation/             # Certified validated feature datasets (validated_*.csv)
│   ├── quarantine/                     # Record-level quarantine logs (quarantine_manifest.csv)
│   └── reports/                        # Stage manifests & governance audit reports
│
├── notebooks/
│   ├── 01_data_staging_pipeline.ipynb  # Stage 1: Ingestion, hashing & staging
│   ├── 02_data_standardization.ipynb   # Stage 2: Canonical typing & value normalization
│   ├── 03_entity_mapping.ipynb         # Stage 3: Relational mapping & foreign key validation
│   ├── 04_data_integration.ipynb       # Stage 4: Controlled multi-domain dataset integration
│   ├── 05_feature_engineering.ipynb    # Stage 5: Time-series, inventory & routing features
│   └── 06_feature_validation.ipynb     # Stage 6: 34-block quality control & anti-leakage audit
│
├── docs/
│   ├── dataset/                        # Documentation of raw sources, schemas & volumes
│   ├── staging/                        # Documentation of staging pipeline & hashing
│   ├── standardization/                # Documentation of cleaning & canonical rules
│   ├── entity_mapping/                 # Documentation of dimensional backbone & ER schema
│   ├── entity_mapping_diagrams/        # 18 relational ER diagrams (.jpg)
│   ├── data_integration/               # Documentation of integration layers & agent views
│   ├── feature_engineering/            # Documentation of 55 features & LaTeX formulations
│   ├── feature_validation/             # Documentation of 34 validation blocks & reports
│   └── agent_data_requirements/        # Multi-agent data requirements specification (7 agents)
│
├── .gitattributes                      # Git LFS tracking configuration for large CSV files
├── .gitignore                          # Ignored patterns (.venv, cache, temporary files)
└── README.md                           # Master project guide
```

---

## 4. Canonical Entities & Authoritative Identifiers

| Entity | Canonical ID Format | Observed Count | Notes |
|---|---|---|---|
| **Product** | `BAB-001` .. `STA-020` | 200 SKUs | 10 retail categories |
| **Location** | `KOL-LOC-001` .. `KOL-LOC-040` | 40 Delivery Zones | Kolkata metropolitan area |
| **Warehouse** | `WH-KOL-001` .. `WH-KOL-015` | 15 Hubs | **Strict format**, never `WH-001` |
| **Supplier** | `SUP-001` .. `SUP-200` | 200 Vendors | Lead times & capacity constraints |
| **Picker** | 50 unique IDs per warehouse | 750 Workforce | 15 warehouses × 50 pickers |
| **Calendar Week** | `W001` .. `W139` | 139 Weeks | Continuous chronological span 2024–2026 |

---

## 5. Core Governance Standards Preserved

1. **Anti-Leakage Guarantee**: Rolling window features are evaluated strictly on historical `lag_1_demand` series ($t-4$ to $t-1$). Zero prediction target columns exist in feature layers.
2. **Zero-Denominator Policy**: Any division by zero in growth or coverage ratios evaluates to `NaN`, never `inf` or silent `0`.
3. **Synthetic Data Provenance**: All features derived from reconstructed inventory movements preserve `RECONSTRUCTED_SYNTHETIC` and are never mislabeled as empirical telemetry.
4. **Distance Transparency**: Straight-line geographic distances are explicitly tagged as `HAVERSINE_GEOGRAPHIC_NOT_ROAD`.
5. **Deferred Entities**: Vehicle Master and Customer Order Data remain deferred without artificial fabrication.
6. **No Premature Decisions**: No feature selection, supplier ranking, route optimization, or target generation is performed in the data pipeline.

---

## 6. Multi-Agent System Architecture

The framework coordinates seven specialized agents documented in [`docs/agent_data_requirements/`](docs/agent_data_requirements/):
- **Demand Agent**: SKU-level demand forecasting, promotional lift, and festival surges.
- **Inventory Agent**: Stock coverage runway, reorder point triggers, and stockout risk monitoring.
- **Warehouse Agent**: Fulfillment center throughput, space utilization, and picker allocation.
- **Supplier Agent**: Sourcing selection, MOQ compliance, and vendor lead-time management.
- **Risk Agent**: Environmental and supply vulnerability assessment.
- **Route Optimization Agent**: Hybrid metaheuristic logistics dispatching.
- **Coordinator Agent**: Global multi-agent consensus and end-to-end plan orchestration.

---

## 7. Quickstart Guide (VS Code)

### Environment Setup
```bash
# Clone repository
git clone https://github.com/mondalsahil302-ui/ai-multi-agent-supply-chain.git
cd ai-multi-agent-supply-chain

# Pull Git LFS data files
git lfs install
git lfs pull

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # Or pandas, numpy, nbformat, nbclient
```

### Running the Notebooks
All notebooks are organized sequentially in `notebooks/` and include directory-agnostic path resolution:
```bash
# Execute sequentially:
# notebooks/01_data_staging_pipeline.ipynb
# notebooks/02_data_standardization.ipynb
# notebooks/03_entity_mapping.ipynb
# notebooks/04_data_integration.ipynb
# notebooks/05_feature_engineering.ipynb
# notebooks/06_feature_validation.ipynb
```
All outputs and governance reports are written directly to `Datasets/feature_validation/` and `Datasets/reports/`.
