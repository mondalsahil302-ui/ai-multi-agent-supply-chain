# Data Validation Report

## Objective
Validate every raw dataset, remove inconsistencies, standardize identifiers, and build a clean processed layer without modifying the raw files.

## Dataset Metrics

| Collection | Total Records | Duplicate Records | Missing Values | Invalid References | Status |
| --- | ---: | ---: | ---: | ---: | --- |
| Products | 200 | 0 | 0 | 0 | PASS |
| Locations | 40 | 0 | 0 | 0 | PASS |
| Warehouses | 15 | 0 | 0 | 0 | PASS |
| Suppliers | 200 | 0 | 0 | 0 | PASS |
| Inventory | 3000 | 0 | 0 | 0 | PASS |
| Sales | 27800 | 0 | 0 | 0 | PASS |
| Weather | 105 | 0 | 0 | 0 | PASS |
| Festivals | 36 | 0 | 0 | 0 | PASS |

## ID Standardization

| Collection | ID Format |
| --- | --- |
| Products | PRO-001 |
| Locations | KOL-LOC-001 |
| Warehouses | WH-001 |
| Suppliers | SUP-001 |
| Inventory | INV-001 |
| Sales | SALE-000001 |
| Weather | WEA-001 |
| Festivals | FES-001 |
| Week | 2024-W01 |

## Reference Integrity

- Sales → Product exists: PASS
- Sales → Location exists: PASS
- Warehouse → Location exists: PASS
- Inventory → Warehouse exists: PASS
- Inventory → Product exists: PASS
- Supplier → Product exists: PASS

## Missing Value Handling

- Product name, brand, and selling price are rejected if missing.
- Rainfall values are filled from weekly weather by week_id when absent.
- Festival gaps are set to None.
- No critical business field is left null in the processed layer.

## Final Status

The processed collections are ready for MongoDB ingestion and downstream agent use.
