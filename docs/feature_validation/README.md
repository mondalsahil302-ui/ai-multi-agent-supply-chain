# Feature Validation Layer Documentation

## 1. Overview & Pipeline Role

The **Feature Validation Layer** (`06_feature_validation.ipynb`) serves as the strict quality-control and anti-leakage audit gate. It verifies that engineered features from Layer 5 are mathematically accurate, structurally sound, type-correct, grain-preserving, free from forward-looking leakage, and fully traceable before any ML model training or agent consumption.

```
FEATURE ENGINEERING
       ↓
FEATURE VALIDATION   ← Layer 6
       ↓
TARGET GENERATION / AGENT-READY ML
```

---

## 2. Validation Framework (34 Systematic Blocks)

The validation notebook executes across 34 structured governance blocks:

| Block Range | Category | Key Audits & Gates |
|---|---|---|
| **Blocks 1–3** | Environment & Discovery | Input file discovery, schema registry, feature dictionary completeness |
| **Blocks 4–5** | Schema & Typing | Column name uniqueness, primary key presence, strict type audit (0 numbers as strings) |
| **Blocks 6–7** | Nulls & Numerics | Distinction between expected burn-in nulls vs unexpected missingness, 0 infinite values |
| **Blocks 8–9** | Keys & Grains | 0 duplicate business keys, strict dimensional grain preservation |
| **Blocks 10–13**| Temporal & Demand | Strict chronological monotonicity, exact math match on lags 1–4, rolling window audit, trend verification |
| **Blocks 14–18**| Domain Features | Inventory formulas, supplier capacity bounds, warehouse ID canonical format, weather ranges, Haversine distance verification |
| **Blocks 19–20**| Anti-Leakage & Safety | **CRITICAL**: Zero target column leakage, zero future windows, decision-time feasibility check |
| **Blocks 21–24**| Ranges & Distributions | Physical bound compliance, clean categorical strings, distribution profiling, redundancy/collinearity audit |
| **Blocks 25–27**| Lineage & Provenance | 100% dictionary lineage match, `RECONSTRUCTED_SYNTHETIC` preservation, cross-domain join audit |
| **Blocks 28–30**| ML Preparation | Temporal train/val/test split feasibility (~70/15/15), preprocessing leakage check, column role classification (IDENTIFIER, FEATURE, TARGET, METADATA) |
| **Blocks 31–34**| Governance & Outputs | Objective summary scoring, quarantine routing (0 records quarantined), publishing to `Datasets/feature_validation/`, 18 audit reports |

---

## 3. Validated Output Catalog (`Datasets/feature_validation/`)

Certified feature datasets published upon passing all 34 quality gates:
- `validated_demand_features.csv` (1,112,000 rows × 48 cols)
- `validated_inventory_features.csv` (3,000 rows × 26 cols)
- `validated_inventory_transaction_features.csv` (417,000 rows × 17 cols, `RECONSTRUCTED_SYNTHETIC`)
- `validated_supplier_features.csv` (200 rows × 17 cols)
- `validated_supplier_product_features.csv` (8,000 rows × 11 cols)
- `validated_supplier_area_features.csv` (200 rows × 11 cols)
- `validated_warehouse_features.csv` (15 rows × 22 cols)
- `validated_routing_features.csv` (75 rows × 11 cols)
- `validated_supplier_routing_features.csv` (200 rows × 7 cols)

---

## 4. Governance Audit Reports (`Datasets/reports/`)

The validation execution produces 18 audit reports documenting every test result:
1. `feature_validation_summary.csv`: Rule-based PASS/WARNING/FAIL status per dataset.
2. `feature_validation_detail.csv`: Detailed check-by-check metrics.
3. `feature_validation_final_report.csv`: Master executive sign-off manifest.
4. `feature_discovery_catalog.csv`: Inventory of discovered files and sizes.
5. `feature_schema_report.csv`: Column structure and key presence check.
6. `feature_type_validation.csv`: Data type evaluation across all columns.
7. `feature_type_report.csv`: Type classification summary.
8. `feature_null_report.csv`: Expected vs unexpected null distribution.
9. `feature_numeric_anomaly_report.csv`: Infinite values and overflow audit.
10. `feature_grain_report.csv`: Expected vs observed row counts and grain keys.
11. `feature_temporal_validation.csv`: Monotonicity check across entity series.
12. `feature_lag_validation.csv`: Exact mathematical match verification for lags.
13. `feature_rolling_validation.csv`: Rolling window computation audit.
14. `feature_leakage_report.csv`: Prohibited keyword and target leakage scan.
15. `feature_lineage_validation.csv`: Feature dictionary traceability check.
16. `feature_provenance_report.csv`: Synthetic data tag audit.
17. `feature_distribution_report.csv`: Statistical profiling for numerical features.
18. `feature_redundancy_report.csv`: Pairwise correlation and collinearity audit.
19. `feature_column_classification.csv`: Classification into IDENTIFIER / FEATURE / METADATA.
20. `feature_quarantine_report.csv`: Record-level quarantine log (0 failures).

---

## 5. Certification Status

- **Duplicate Keys**: 0
- **Infinite Values**: 0
- **Target Leakage**: 0 (ZERO_LEAKAGE verified)
- **Temporal Order**: Strictly monotonic non-decreasing
- **Final Governance Status**: **PASS**
- **Stop Condition Enforced**: `STOP_BEFORE_TARGET_GENERATION` (ML target generation and training deferred to subsequent ML phase).
