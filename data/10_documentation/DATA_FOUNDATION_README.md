# Data Foundation — AI Multi-Agent Supply Chain (Kolkata)

## Overview
This folder contains the complete data foundation pipeline outputs for the Kolkata Multi-Agent Supply Chain system. All layers were built by the automated ETL pipeline and are traceable from raw source to agent-ready output.

## Pipeline Layers
| Layer | Folder | Contents |
|---|---|---|
| 01 | `01_raw/` | Immutable copies of source files |
| 02 | `02_profile/` | Data profiling CSVs |
| 03 | `03_staging/` | Intermediate staging (scripts use direct read) |
| 04 | `04_standardized/` | Reserved for manual overrides |
| 05 | `05_entity_mapping/` | entity_mapping.csv + entity_mapping.json |
| 06 | `06_curated/` | All canonical DIM/FACT/BRIDGE tables |
| 07 | `07_features/` | Agent-specific feature tables |
| 08 | `08_validation/` | Validation summary + details |
| 09 | `09_agent_ready/` | Final copy for agent consumption |
| 10 | `10_documentation/` | All documentation |
| — | `data_quarantine/` | Quarantined unresolved records |

## Key Entities
- **DIM_PRODUCT**: 200 products, 20 categories, 10 per category
- **DIM_PRODUCT_VARIANT**: 1,000 variants (5 sizes per product)
- **DIM_LOCATION**: 40 Kolkata regions
- **DIM_WAREHOUSE**: 15 warehouses
- **DIM_SUPPLIER**: 200 suppliers
- **DIM_CALENDAR_WEEK**: 105 weeks
- **DIM_FESTIVAL**: 36 festival events
- **DIM_WEATHER**: 105 weekly weather records

## BLOCKED Sources (Git-LFS)
- `sales_history.xlsx` → FACT_SALES BLOCKED
- `inventory_transactions.xlsx` → FACT_INVENTORY_TRANSACTION BLOCKED

Run `git lfs pull` to restore these files.

## Source Data Classification
All synthetic/supplied data is clearly marked. No observed real-world data was altered.
