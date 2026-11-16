"""Global LightGBM standby model (ONE model for all products).

Used only when a product's Ridge model is not approved or fails at forecast time.
  - same 34 shared features as Ridge + one categorical `category_code`
  - target = log1p(units) - demand_level_log1p  (scale-free, so low and high volume
    products can share one model); prediction = expm1(level + relative prediction)
  - one-step-ahead features use only past actual demand (same protocol as Ridge)
  - early stopping on the validation split; P10/P90 from validation residuals
"""
import logging
from datetime import datetime, timezone

import lightgbm as lgb
import numpy as np
import pandas as pd

from demand_agent.features import FEATURE_COLUMNS, MIN_FEATURE_HISTORY, build_feature_matrix, check_weekly_continuity

log = logging.getLogger(__name__)

LGBM_FEATURES = FEATURE_COLUMNS + ["category_code"]
PARAMS = {
    "objective": "regression", "learning_rate": 0.03, "num_leaves": 15, "min_child_samples": 40,
    "subsample": 0.8, "subsample_freq": 1, "colsample_bytree": 0.8, "reg_lambda": 5.0,
    "max_depth": -1, "verbosity": -1, "force_row_wise": True, "deterministic": True,
}
MAX_ROUNDS = 3000
EARLY_STOPPING = 100


def category_of(product_id: str) -> str:
    return product_id.split("-")[0]


def build_pooled_dataset(series_by_product: dict[str, pd.DataFrame]):
    """Feature rows for every product, with split labels. Returns (frame, category_map, base_prices)."""
    categories = sorted({category_of(p) for p in series_by_product})
    category_map = {c: i for i, c in enumerate(categories)}
    parts, base_prices = [], {}
    for pid, series in series_by_product.items():
        series = series.sort_values("week_start_date").reset_index(drop=True)
        check_weekly_continuity(series)
        base = float(series["list_price_rs"].iloc[0])
        base_prices[pid] = base
        X = build_feature_matrix(series, base)
        X["category_code"] = category_map[category_of(pid)]
        X["product_id"] = pid
        X["week_start_date"] = series["week_start_date"]
        X["split"] = series["split"]
        X["stockout"] = series["stockout_flag"].astype(int).to_numpy()
        X["units"] = series["units_sold"].astype(float).to_numpy()
        X["pos"] = np.arange(len(series))
        parts.append(X)
    df = pd.concat(parts, ignore_index=True)
    ready = df["pos"].ge(MIN_FEATURE_HISTORY) & np.isfinite(df[LGBM_FEATURES].to_numpy(dtype=float)).all(axis=1)
    df = df[ready].copy()
    df["y_rel"] = np.log1p(df["units"]) - df["demand_level_log1p"]
    return df.reset_index(drop=True), category_map, base_prices


def fit_global(df: pd.DataFrame, seed: int = 42):
    fit_rows = df[df.split.eq("train") & df.stockout.eq(0)]
    val_rows = df[df.split.eq("validation") & df.stockout.eq(0)]
    params = {**PARAMS, "seed": seed}
    dtrain = lgb.Dataset(fit_rows[LGBM_FEATURES], fit_rows["y_rel"], categorical_feature=["category_code"])
    dval = lgb.Dataset(val_rows[LGBM_FEATURES], val_rows["y_rel"], reference=dtrain)
    booster = lgb.train(params, dtrain, num_boost_round=MAX_ROUNDS, valid_sets=[dval],
                        callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)])
    return booster, params, len(fit_rows), len(val_rows)


def predict_units(booster, rows: pd.DataFrame, cal: dict, num_iteration=None) -> pd.DataFrame:
    rel = booster.predict(rows[LGBM_FEATURES], num_iteration=num_iteration)
    level = rows["demand_level_log1p"].to_numpy()
    pred_log = level + rel
    return pd.DataFrame({
        "p10": np.maximum(0.0, np.expm1(pred_log + cal["q10"])),
        "p50": np.maximum(0.0, np.expm1(pred_log + cal["q50"])),
        "expected": np.maximum(0.0, np.exp(pred_log) * cal["smearing"] - 1.0),
        "p90": np.maximum(0.0, np.expm1(pred_log + cal["q90"])),
    }, index=rows.index)


def calibrate_from_validation(booster, df: pd.DataFrame) -> dict:
    val = df[df.split.eq("validation") & df.stockout.eq(0)]
    rel = booster.predict(val[LGBM_FEATURES], num_iteration=booster.best_iteration)
    res = val["y_rel"].to_numpy() - rel
    q10, q50, q90 = np.quantile(res, [0.10, 0.50, 0.90])
    return {"q10": float(q10), "q50": float(q50), "q90": float(q90),
            "smearing": float(np.mean(np.exp(res))), "n_residuals": int(len(res))}


def final_refit(df: pd.DataFrame, params: dict, rounds: int):
    rows = df[df.stockout.eq(0)]
    dall = lgb.Dataset(rows[LGBM_FEATURES], rows["y_rel"], categorical_feature=["category_code"])
    return lgb.train(params, dall, num_boost_round=rounds), len(rows)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()
