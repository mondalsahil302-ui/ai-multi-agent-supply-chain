# Supply Chain Dataset V2

This package is the frozen base dataset layer for the project.

## Important
- The previous incomplete sales CSV is intentionally NOT used. `sales_history_source.xlsx` is the original source workbook with 139 weekly sheets. The workbook metadata states 8,000 rows per week, giving 1,112,000 expected records.
- Warehouse IDs use the canonical `WH-KOL-###` convention.
- Warehouse-picker mapping contains 50 unique picker IDs per warehouse.

## Source vs derived vs synthetic
- `01_RAW_SOURCE`: source datasets preserved/exported from supplied files.
- `02_DERIVED_REFERENCE`: deterministic reference tables required to connect the source entities.
- `03_SYNTHETIC_SUPPORT`: explicitly synthetic/proxy tables where no authoritative source was supplied.

## Not fabricated
Road-network distances, real customer orders, real vehicle availability history, and the original 417,000-row inventory transaction object are not claimed as observed source data. Haversine matrices and synthetic proxies are clearly labelled for prototype use.

## Next layer
After this package is approved, build staging -> standardization -> curated -> features -> agent-ready tables -> synthetic VAE/TVAE scenario data -> LLM message/decision data.
