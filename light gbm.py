
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import lightgbm as lgb
from sklearn.preprocessing import OrdinalEncoder
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

# ---------------------------------------------------------
# 1. LOAD & PREPROCESS DATASET
# ---------------------------------------------------------
df = pd.read_csv('demand_agent_training.csv')

# Ensure date parsing
df['week_start_date'] = pd.to_datetime(df['week_start_date'])

# Fill missing categorical values
df['festival_event'] = df['festival_event'].fillna('None')

# Select feature columns and target
feature_cols = [
    'year', 'week_number', 'demand_rank',
    'location_id', 'product_id', 'category_name', 'brand',
    'weekday_units_sold', 'weekend_units_sold', 'units_sold',
    'avg_selling_price_rs', 'promotion_flag', 'discount_pct',
    'holiday_flag', 'festival_event', 'season',
    'temperature_c', 'rainfall_mm', 'humidity_pct', 'weather_condition',
    'stockout_flag'
]

target_col = 'next_week_demand_target_units'
cat_cols = ['location_id', 'product_id', 'category_name', 'brand', 'festival_event', 'season', 'weather_condition']

# Encode categorical variables for tree-based modeling
data = df[feature_cols + [target_col, 'week_start_date']].copy()
encoder = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
data[cat_cols] = encoder.fit_transform(data[cat_cols])

# ---------------------------------------------------------
# 2. TIME-SERIES CHRONOLOGICAL SPLIT (80% Train, 20% Test)
# ---------------------------------------------------------
dates = sorted(data['week_start_date'].unique())
split_idx = int(len(dates) * 0.8)
split_date = dates[split_idx]

train_df = data[data['week_start_date'] < split_date]
test_df = data[data['week_start_date'] >= split_date]

X_train, y_train = train_df[feature_cols], train_df[target_col]
X_test, y_test = test_df[feature_cols], test_df[target_col]

print(f"Train samples: {len(X_train)} | Test samples: {len(X_test)}")

# ---------------------------------------------------------
# 3. TRAIN LIGHTGBM REGRESSOR
# ---------------------------------------------------------
lgb_model = lgb.LGBMRegressor(
    n_estimators=400,
    learning_rate=0.03,
    num_leaves=31,
    min_child_samples=20,
    reg_alpha=0.1,         # L1 Regularization
    reg_lambda=1.0,        # L2 Regularization
    random_state=42,
    n_jobs=-1
)

lgb_model.fit(X_train, y_train)

# ---------------------------------------------------------
# 4. PREDICTIONS & EVALUATION
# ---------------------------------------------------------
y_pred_train = lgb_model.predict(X_train)
y_pred_test = lgb_model.predict(X_test)

# Calculate performance metrics
train_rmse = np.sqrt(mean_squared_error(y_train, y_pred_train))
test_rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
test_mae = mean_absolute_error(y_test, y_pred_test)
test_r2 = r2_score(y_test, y_pred_test)
test_wmape = (np.sum(np.abs(y_test - y_pred_test)) / np.sum(y_test)) * 100

print("\n=== LightGBM Model Evaluation ===")
print(f"Train RMSE : {train_rmse:.2f}")
print(f"Test RMSE  : {test_rmse:.2f}")
print(f"Test MAE   : {test_mae:.2f}")
print(f"Test WMAPE : {test_wmape:.2f}%")
print(f"Test R2    : {test_r2:.4f}")

# ---------------------------------------------------------
# 5. VISUALIZATION
# ---------------------------------------------------------
test_results = test_df.copy()
test_results['predicted_demand'] = y_pred_test

weekly_agg = test_results.groupby('week_start_date')[['next_week_demand_target_units', 'predicted_demand']].sum().reset_index()

