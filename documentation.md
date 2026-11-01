# Demand Forecasting & Supply Chain Intelligence System

## 1. Project Overview
This project builds an automated end-to-end Machine Learning pipeline to forecast next-week SKU-level product demand (`next_week_demand_target_units`) across 40 regional retail locations in Kolkata. By predicting weekly demand accurately, store managers can optimize inventory levels, mitigate stockouts, and highlight high-performing products.

---

## 2. Dataset & Key Features
- **Data Source:** `demand_agent_training.csv`
- **Target Variable:** `next_week_demand_target_units` (Continuous integer representing upcoming week unit demand)
- **Primary Input Features:**
  - **Temporal & Calendar:** `year`, `week_number`, `season`
  - **Store & Product Identifiers:** `location_id`, `product_id`, `category_name`, `brand`
  - **Sales & Operations:** `weekday_units_sold`, `weekend_units_sold`, `units_sold`, `demand_rank`, `stockout_flag`
  - **Pricing & Discounts:** `avg_selling_price_rs`, `discount_pct`, `promotion_flag`
  - **Weather & Environment:** `temperature_c`, `rainfall_mm`, `humidity_pct`, `weather_condition`, `holiday_flag`, `festival_event`

---

## 3. Data Preprocessing & Pipeline Steps
To ensure model stability, handle missing values, and prevent data leakage:
1. **Missing Value Imputation:** Missing values in `festival_event` are explicitly filled with `'None'` to capture non-festival baseline periods.
2. **Chronological Time-Series Sorting:** Records are sorted by `week_start_date`, `location_id`, and `product_id` to preserve time ordering.
3. **Categorical Encoding:** String attributes (`location_id`, `product_id`, `category_name`, `brand`, `season`, `weather_condition`, `festival_event`) are converted to `category` dtypes for native XGBoost handling.
4. **Chronological Train/Test Split:** An 80/20 train-test split is executed strictly on unique historical dates (first 80% dates for training, final 20% for testing).

---

## 4. Modeling & Performance Evaluation
- **Algorithm:** `XGBoost Regressor` (`xgb.XGBRegressor`)
- **Model Evaluation:**
  - **Regression Metrics:** Evaluated using Root Mean Squared Error (**RMSE**), Mean Absolute Error (**MAE**), and **$R^2$ Score** to measure continuous demand precision.
  - **Classification Metrics:** Evaluated by thresholding predictions at the training median demand into binary classes (`High Demand` vs. `Low Demand`), measuring **Accuracy**, **Recall**, and **F1-Score**.

---

## 5. Final Operational Output
The pipeline generates location-wise demand summaries for the next forecast period, outputting:
1. **`location_id` & `region_of_kolkata`:** Specific store location identifiers and names.
2. **`total_predicted_demand_units`:** Total forecasted unit volume per store.
3. **`avg_product_demand_units`:** Average expected demand per product SKU.
4. **`top_product_name` & `top_product_demand_units`:** Identifies the single highest-demand product for each store location and its projected sales volume.