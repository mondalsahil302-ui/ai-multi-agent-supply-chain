# Feature Engineering Layer Documentation

## 1. Overview & Pipeline Role

The **Feature Engineering Layer** (`05_feature_engineering.ipynb`) consumes integrated datasets from `Datasets/integrated/` and constructs informative, structured variables for downstream Machine Learning models and autonomous operational agents. All engineered outputs are written to `Datasets/feature_engineered/`.

```
DATA INTEGRATION
       ↓
FEATURE ENGINEERING   ← Layer 5
       ↓
FEATURE VALIDATION
```

---

## 2. Mathematical Formulations & Feature Groups

A total of **55 engineered features** are configured across 9 functional groups:

### A. Demand Time-Series Features (`demand_features.csv`)
- **Historical Lags**:
  $$\text{lag\_1\_demand}_{l,p,t} = D_{l,p,t-1}, \quad \dots \quad \text{lag\_4\_demand}_{l,p,t} = D_{l,p,t-4}$$
- **Rolling Windows** (Evaluated strictly on the $\text{lag\_1}$ series to eliminate current-week lookahead leakage):
  $$\text{rolling\_mean\_4}_{l,p,t} = \frac{1}{\min(4, n)} \sum_{k=1}^{\min(4, n)} D_{l,p,t-k}$$
  $$\text{rolling\_std\_4}_{l,p,t} = \sqrt{\frac{1}{n-1} \sum_{k=1}^n (D_{l,p,t-k} - \bar{D})^2}$$
  $$\text{rolling\_sum\_4}_{l,p,t}, \quad \text{recent\_min\_demand}_{l,p,t}, \quad \text{recent\_max\_demand}_{l,p,t}$$

### B. Demand Trend & Momentum
- **Absolute Change**:
  $$\Delta D_{l,p,t} = D_{l,p,t} - D_{l,p,t-1}$$
- **Percentage Growth Rate**:
  $$G_{l,p,t} = \frac{D_{l,p,t} - D_{l,p,t-1}}{D_{l,p,t-1}} \quad (\text{Zero Denominator Policy: } D_{l,p,t-1} = 0 \implies \text{NaN})$$

### C. Seasonality & Cyclical Encodings
- Continuous sine/cosine representation avoiding year-boundary boundary jumps:
  $$\text{sin\_week} = \sin\left(\frac{2\pi \cdot w}{52}\right), \quad \text{cos\_week} = \cos\left(\frac{2\pi \cdot w}{52}\right)$$
- Categorical attributes: `month` (1–12), `quarter` (1–4), `season` (Winter, Monsoon, etc.).

### D. Weather & Event Context
- `temperature_mean_c`, `temperature_max_c`, `temperature_min_c`, `rainfall_mm`, `humidity_pct`.
- `rainfall_flag` ($R > 0$) and `high_rainfall_flag` ($R > 50\text{mm}$, project-defined Kolkata monsoon threshold).
- `temp_deviation_c` ($T_t - \bar{T}_{\text{annual}}$).
- `festival_flag` and `festival_count` (known published religious calendar dates).

### E. Inventory Health Features (`inventory_features.csv`)
- **Stock Gap**:
  $$\text{stock\_gap}_{w,p} = \text{available\_stock}_{w,p} - \text{target\_stock}_{w,p}$$
- **Stock Coverage Runway**:
  $$\text{stock\_coverage}_{w,p} = \frac{\text{available\_stock}_{w,p}}{\text{avg\_weekly\_demand}_{w,p}} \quad (\text{Denom } = 0 \implies \text{NaN})$$
- **Stockout Indicator**: Binary flag indicating depleted stock ($\text{available\_stock} \leq 0$).

### F. Inventory Movement Features (`inventory_transaction_features.csv`)
- Weekly throughput (`weekly_sold_units`) and 4-week rolling throughput (`rolling_sold_4w`) computed on reconstructed transactions.
- **Strict Provenance**: 100% of rows preserve `record_status = RECONSTRUCTED_SYNTHETIC`.

### G. Supplier & Logistics Features
- Supplier lead time, storage capacity, vehicle load capacity, minimum order quantity (MOQ).
- Warehouse picker workforce count (`wh_picker_count`) and capacity load ratio (`wh_inventory_load`).
- Geographic proximity (`wh_location_haversine_km`) explicitly labeled as `HAVERSINE_GEOGRAPHIC_NOT_ROAD`.

---

## 3. Feature Output Catalog (`Datasets/feature_engineered/`)

| Output Dataset | Grain | Row Count | Primary Key | Key Features |
|---|---|---|---|---|
| `demand_features.csv` | location × product × week | 1,112,000 | `region_product_week_key` | Lags 1–4, rolling 4w/8w mean/std/sum, trend, cyclical $\sin/\cos$, weather |
| `inventory_features.csv` | warehouse × product | 3,000 | `warehouse_id + product_id` | `stock_gap`, `stock_coverage`, `stockout_indicator`, `space_utilization_pct` |
| `inventory_transaction_features.csv` | warehouse × product × week | 417,000 | `warehouse_product_week_key` | `weekly_sold_units`, `rolling_sold_4w` (**RECONSTRUCTED_SYNTHETIC**) |
| `supplier_features.csv` | supplier | 200 | `supplier_id` | `lead_time_days`, `min_order_qty_units`, `supplier_storage_capacity` |
| `supplier_product_features.csv` | supplier × product | 8,000 | `supplier_id + product_supplied_id` | `supplier_cost_price_rs`, `supply_status` |
| `supplier_area_features.csv` | supplier × location | 200 | `supplier_id + location_id` | `distance_from_location_center_km`, `service_available_flag` |
| `warehouse_features.csv` | warehouse | 15 | `warehouse_id` | `capacity_units`, `wh_picker_count`, `wh_inventory_load` |
| `routing_features.csv` | warehouse × location | 75 | `warehouse_id + location_id` | `wh_location_haversine_km` (`HAVERSINE_GEOGRAPHIC_NOT_ROAD`), rank |
| `supplier_routing_features.csv` | supplier × location | 200 | `supplier_id + location_id` | `supplier_location_haversine_km` (`HAVERSINE_GEOGRAPHIC_NOT_ROAD`) |

---

## 4. Governance & Anti-Leakage Enforcements

1. **Zero Lookahead Leakage**: All rolling features operate strictly on historical $\text{lag\_1}$ series; current-week demand $D_t$ is never included in the rolling window.
2. **Zero Target Generation**: No prediction target column (`next_week_demand`, `future_sales`) is generated in this stage.
3. **Zero-Denominator Policy**: Any division by zero evaluates to `NaN`, never `inf` or silent `0`.
4. **Synthetic Provenance**: Synthetic transaction features inherit `RECONSTRUCTED_SYNTHETIC`.
5. **No Optimization/Decisions**: Does not perform route optimization, vehicle dispatch, or supplier selection.
