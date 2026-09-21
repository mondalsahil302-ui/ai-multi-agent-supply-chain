# Known Limitations

## Resolved Blockers (Updated)
1. ✅ **SALES_HISTORY RESOLVED**: Replaced Git-LFS blocked pointer with `SELL_of_past_2_years_COMBINED.csv` (448,000 rows). `FACT_SALES.csv` is now fully unblocked and available to Demand Agent and validation.
2. ✅ **INVENTORY_TRANSACTIONS RESOLVED**: Replaced Git-LFS blocked pointer with `Inventory_Transactions_417000_Reconstructed.csv` (417,000 rows). `FACT_INVENTORY_TRANSACTION.csv` is now fully unblocked and available to Inventory Agent and Risk Agent.
3. ✅ **WAREHOUSE_PICKERS INTEGRATED**: Added `Warehouse_Picker_IDs_Only.csv` (750 pickers across 15 warehouses), creating `DIM_PICKER` and `BRIDGE_WAREHOUSE_PICKER`, and enriching `WAREHOUSE_FEATURES.assigned_picker_count`.

## Remaining Data Quality Issues
1. **SUPPLIER_CATALOG_UNMAPPED_COLUMN**: Column at index 10 in `Supplier_Product_Catalog` has no header.
   - Values are numeric (range ~9–200), possibly unit conversion ratio.
   - Preserved as `unmapped_col_10_quarantine`. Requires domain expert review.

2. **Synthetic Training Data**: Demand training dataset (`final_demand_agent_training_2_years_kolkata.xlsx`) is explicitly labeled `SYNTHETIC_TRAINING`.
   - Now that `FACT_SALES` is unblocked (448,000 rows), models have access to true historical sales transactions.
   - Weather context is marked `SUPPLIED_SYNTHETIC`.

3. **No Road Distance Available**: `BRIDGE_WAREHOUSE_LOCATION` uses Haversine (euclidean) distance.
   - Field is named `euclidean_distance_km`, NOT road_distance_km.
   - Route Optimization Agent must not use this as road distance.

4. **Product Variant Join in Demand**: `FACT_DEMAND` contains `unit_size` (string, e.g., "500 g") but does not directly join to `DIM_PRODUCT_VARIANT` by `product_variant_id`.
   - A join on `product_id + unit_size_raw` is required for variant-level aggregation.

5. **Inventory Formula Fields in Raw Source**: Raw formula fields in `inventory_stock.xlsx` were not populated in the Excel cache (None).
   - Fully resolved in pipeline: `weeks_of_cover_calc`, `reorder_flag_calc`, `target_stock_units`, `shortage_units`, `stock_cost_value_rs`, and `available_sales_value_rs` are all explicitly calculated in `04_standardized` and `06_curated`.
