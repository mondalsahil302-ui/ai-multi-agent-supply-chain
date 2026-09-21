# Known Limitations

## Critical Blockers
1. **SALES_HISTORY_SOURCE_UNAVAILABLE**: `sales_history.xlsx` is a Git-LFS pointer (expected 177MB).
   - Impact: FACT_SALES cannot be built. Demand Agent cannot validate against actual sales.
   - Fix: `git lfs pull` in repo root.

2. **INVENTORY_TRANSACTIONS_SOURCE_UNAVAILABLE**: `inventory_transactions.xlsx` is a Git-LFS pointer (expected 56MB).
   - Impact: FACT_INVENTORY_TRANSACTION cannot be built. Transaction-level inventory tracking unavailable.
   - Fix: `git lfs pull` in repo root.

## Data Quality Issues
3. **SUPPLIER_CATALOG_UNMAPPED_COLUMN**: Column at index 10 in `Supplier_Product_Catalog` has no header.
   - Values are numeric (range ~9–200), possibly unit conversion ratio.
   - Preserved as `unmapped_col_10_quarantine`. Requires domain expert review.

4. **Synthetic Training Data**: Both demand datasets are explicitly labeled `SYNTHETIC_TRAINING`.
   - Do not treat demand data as observed real-world sales.
   - Weather context is marked `SUPPLIED_SYNTHETIC`.

5. **No Road Distance Available**: `BRIDGE_WAREHOUSE_LOCATION` uses Haversine (euclidean) distance.
   - Field is named `euclidean_distance_km`, NOT road_distance_km.
   - Route Optimization Agent must not use this as road distance.

6. **Product Variant Join in Demand**: FACT_DEMAND contains `unit_size` (string, e.g., "500 g") but does not directly join to DIM_PRODUCT_VARIANT by product_variant_id.
   - A join on `product_id + unit_size_raw` is required for variant-level aggregation.

7. **Inventory Formula Fields**: `stock_value_rs`, `available_sales_value_rs`, `gross_margin_potential_rs`, `weeks_of_cover`, `target_stock_units`, `shortage_units` appear as None in source (formula cache not populated).
   - These fields were recalculated explicitly in the pipeline where data permitted.
   - `weeks_of_cover_calc` and `reorder_flag_calc` are derived; source cached values not used.

8. **inventory_transactions Referenced But Unavailable**: The `inventory_stock.xlsx` workbook references `Inventory_Agent_Transactions_417000.xlsx` as a transaction companion. This file was not present in the repository.
