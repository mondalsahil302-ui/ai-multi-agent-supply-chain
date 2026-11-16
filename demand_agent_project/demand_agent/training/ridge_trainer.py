"""Offline Ridge training for ONE product-region series (main model).

Protocol ported from the reference notebook:
  - expanding-window, one-week-ahead rolling origins
  - alpha tuned on validation only, then locked for test
  - stockout weeks are never training targets and never scored
  - P10/P50/P90 + smearing factor calibrated from out-of-sample residuals
  - final model refit on all eligible weeks
"""
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from demand_agent.features import (
    FEATURE_COLUMNS, MIN_FEATURE_HISTORY, REQUIRED_INPUT_COLUMNS,
    build_feature_matrix, check_weekly_continuity)

log = logging.getLogger(__name__)

ALPHA_GRID = [0.1, 0.3, 1.0, 3.0, 10.0, 30.0, 100.0, 300.0]
MIN_TRAINING_ROWS = 30
NUMERIC = ["units_sold", "selling_price_rs", "list_price_rs", "discount_pct", "promo_flag",
           "stockout_flag", "festival_proximity", "temperature_c", "rainfall_mm", "humidity_pct"]


# ---------------- metrics ----------------
def wape(actual, predicted) -> float:
    a, p = np.asarray(actual, float), np.asarray(predicted, float)
    d = np.sum(np.abs(a))
    return float(np.sum(np.abs(a - p)) / d * 100.0) if d > 0 else np.nan


def bias_pct(actual, predicted) -> float:
    a, p = np.asarray(actual, float), np.asarray(predicted, float)
    d = np.sum(a)
    return float(np.sum(p - a) / d * 100.0) if d > 0 else np.nan


def score_metrics(actual, predicted) -> dict:
    a, p = np.asarray(actual, float), np.asarray(predicted, float)
    w = wape(a, p)
    return {"n": int(len(a)), "WAPE_pct": w, "Accuracy_pct": 100.0 - w,
            "MAE_units": float(mean_absolute_error(a, p)),
            "RMSE_units": float(np.sqrt(mean_squared_error(a, p))),
            "Bias_pct": bias_pct(a, p)}


# ---------------- data ----------------
def load_product_series(db, collection: str, region_id: str, product_id: str,
                        exclude_synthetic: bool = True, exclude_partial: bool = True) -> pd.DataFrame:
    q = {"region_id": region_id, "product_id": product_id, "split": {"$in": ["train", "validation", "test"]}}
    if exclude_partial:
        q["is_partial_week"] = False
    if exclude_synthetic:
        q["is_synthetic_record"] = False
    proj = {"_id": 0, "split": 1, **{c: 1 for c in REQUIRED_INPUT_COLUMNS}}
    df = pd.DataFrame(list(db[collection].find(q, proj)))
    if df.empty:
        raise ValueError(f"no training rows for {product_id}")
    df["week_start_date"] = pd.to_datetime(df["week_start_date"])
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("week_start_date").reset_index(drop=True)


class SeriesContext:
    """Holds the series, feature matrix and split boundaries for one product."""

    def __init__(self, series: pd.DataFrame):
        series = series.sort_values("week_start_date").reset_index(drop=True)
        check_weekly_continuity(series)
        order = series["split"].tolist()
        n_tr, n_va = order.count("train"), order.count("validation")
        if order != ["train"] * n_tr + ["validation"] * n_va + ["test"] * (len(order) - n_tr - n_va):
            raise ValueError("split labels are not ordered train -> validation -> test")
        self.series = series
        self.base_list_price = float(series["list_price_rs"].iloc[0])
        self.X = build_feature_matrix(series, self.base_list_price)
        self.y_log = np.log1p(series["units_sold"].astype(float).to_numpy())
        self.stockout = series["stockout_flag"].astype(int).to_numpy()
        self.train_end = n_tr
        self.validation_end = n_tr + n_va
        if len(self.X.iloc[MIN_FEATURE_HISTORY:].dropna()) != len(self.X) - MIN_FEATURE_HISTORY:
            raise ValueError("missing feature values after warm-up")

    def row_ready(self, i, cols=FEATURE_COLUMNS) -> bool:
        return bool(np.isfinite(self.X.loc[i, cols].to_numpy(dtype=float)).all())

    def eligible(self, i, cols=FEATURE_COLUMNS) -> bool:
        return (i >= MIN_FEATURE_HISTORY and self.stockout[i] == 0
                and np.isfinite(self.y_log[i]) and self.row_ready(i, cols))


def make_pipeline(alpha: float) -> Pipeline:
    return Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=float(alpha)))])


def fit_and_predict_origin(ctx: SeriesContext, origin: int, alpha: float, cols=FEATURE_COLUMNS):
    train_idx = [j for j in range(origin) if ctx.eligible(j, cols)]
    if len(train_idx) < MIN_TRAINING_ROWS or not ctx.row_ready(origin, cols):
        return np.nan, len(train_idx)
    model = make_pipeline(alpha)
    model.fit(ctx.X.loc[train_idx, cols], ctx.y_log[train_idx])
    return float(model.predict(ctx.X.loc[[origin], cols])[0]), len(train_idx)


# ---------------- training protocol ----------------
def tune_alpha(ctx: SeriesContext):
    results, by_alpha = [], {}
    for alpha in ALPHA_GRID:
        rows = []
        for i in range(ctx.train_end, ctx.validation_end):
            pred_log, n_train = fit_and_predict_origin(ctx, i, alpha)
            rows.append({"index": i, "actual_units": float(ctx.series.units_sold.iloc[i]),
                         "stockout_flag": int(ctx.stockout[i]), "pred_log": pred_log})
        frame = pd.DataFrame(rows)
        scored = frame[frame.stockout_flag.eq(0) & frame.pred_log.notna()]
        pred_units = np.maximum(0.0, np.expm1(scored.pred_log.to_numpy()))
        results.append({"alpha": alpha, "validation_WAPE_pct": wape(scored.actual_units, pred_units),
                        "scored_weeks": len(scored)})
        by_alpha[alpha] = frame
    table = pd.DataFrame(results).sort_values("validation_WAPE_pct").reset_index(drop=True)
    if table.empty or not np.isfinite(table.validation_WAPE_pct.iloc[0]):
        raise RuntimeError("unable to tune alpha: no eligible validation forecasts")
    best = float(table.alpha.iloc[0])
    return best, table, by_alpha[best]


def calibrate(ctx: SeriesContext, alpha: float, val_frame: pd.DataFrame):
    train_res = []
    for i in range(MIN_FEATURE_HISTORY + MIN_TRAINING_ROWS, ctx.train_end):
        if ctx.stockout[i] != 0 or not ctx.row_ready(i):
            continue
        pred_log, _ = fit_and_predict_origin(ctx, i, alpha)
        if np.isfinite(pred_log):
            train_res.append(float(ctx.y_log[i] - pred_log))
    v = val_frame[val_frame.stockout_flag.eq(0) & val_frame.pred_log.notna()]
    val_res = list(np.log1p(v.actual_units.to_numpy(dtype=float)) - v.pred_log.to_numpy(dtype=float))
    res = np.asarray(train_res + val_res, dtype=float)
    if len(res) < 20:
        raise RuntimeError(f"only {len(res)} out-of-sample residuals; need at least 20")
    q10, q50, q90 = np.quantile(res, [0.10, 0.50, 0.90])
    return {"q10": float(q10), "q50": float(q50), "q90": float(q90),
            "smearing": float(np.mean(np.exp(res))), "n_residuals": int(len(res))}


def evaluate_test(ctx: SeriesContext, alpha: float, cal: dict) -> pd.DataFrame:
    rows = []
    s = ctx.series
    for i in range(ctx.validation_end, len(s)):
        pred_log, n_train = fit_and_predict_origin(ctx, i, alpha)
        if not np.isfinite(pred_log):
            continue
        hist = s.iloc[:i]
        recent = hist.loc[hist.stockout_flag.eq(0), "units_sold"].tail(4)
        seasonal_pos = i - 52
        seasonal = (float(s.units_sold.iloc[seasonal_pos])
                    if seasonal_pos >= 0 and int(ctx.stockout[seasonal_pos]) == 0 else np.nan)
        rows.append({
            "week_start_date": s.week_start_date.iloc[i],
            "actual_units": float(s.units_sold.iloc[i]),
            "stockout_flag": int(ctx.stockout[i]),
            "p10": max(0.0, float(np.expm1(pred_log + cal["q10"]))),
            "p50": max(0.0, float(np.expm1(pred_log + cal["q50"]))),
            "expected": max(0.0, float(np.exp(pred_log) * cal["smearing"] - 1.0)),
            "p90": max(0.0, float(np.expm1(pred_log + cal["q90"]))),
            "moving_median": float(recent.median()) if len(recent) else np.nan,
            "seasonal_naive": seasonal,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("no test predictions were generated")
    return out


def final_fit(ctx: SeriesContext, alpha: float):
    idx = [i for i in range(len(ctx.series)) if ctx.eligible(i)]
    model = make_pipeline(alpha)
    model.fit(ctx.X.loc[idx, FEATURE_COLUMNS], ctx.y_log[idx])
    return model, len(idx)


def train_product(series: pd.DataFrame, product_id: str, region_id: str):
    """Returns (artifact dict, report dict)."""
    ctx = SeriesContext(series)
    alpha, alpha_table, val_frame = tune_alpha(ctx)
    cal = calibrate(ctx, alpha, val_frame)
    test = evaluate_test(ctx, alpha, cal)
    scored = test[test.stockout_flag.eq(0)]

    ridge_metrics = score_metrics(scored.actual_units, scored.expected)
    median_metrics = score_metrics(scored.actual_units, scored.moving_median)
    seas = scored.seasonal_naive.fillna(scored.moving_median)
    seasonal_metrics = score_metrics(scored.actual_units, seas)
    coverage = float(((scored.actual_units >= scored.p10) & (scored.actual_units <= scored.p90)).mean() * 100.0)

    model, n_fit = final_fit(ctx, alpha)
    artifact = {
        "model_type": "ridge",
        "model": model,
        "product_id": product_id,
        "region_id": region_id,
        "series_id": f"{region_id}_{product_id}",
        "feature_columns": list(FEATURE_COLUMNS),
        "best_alpha": alpha,
        "base_list_price": ctx.base_list_price,
        "q10_log_residual": cal["q10"], "q50_log_residual": cal["q50"], "q90_log_residual": cal["q90"],
        "smearing_factor": cal["smearing"],
        "training_cutoff": str(ctx.series.week_start_date.max().date()),
        "training_rows": n_fit,
        "weather_training_mode": "historical_observed_weather",
        "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        "metrics": {"test_ridge": ridge_metrics, "test_moving_median": median_metrics,
                    "test_seasonal_naive": seasonal_metrics, "test_p10_p90_coverage_pct": coverage,
                    "validation_WAPE_pct": float(alpha_table.validation_WAPE_pct.iloc[0])},
    }
    report = {"alpha_table": alpha_table, "calibration": cal, "test": test,
              "ridge": ridge_metrics, "median": median_metrics, "seasonal": seasonal_metrics,
              "coverage": coverage, "n_fit": n_fit, "weeks": len(ctx.series),
              "train_end": ctx.train_end, "validation_end": ctx.validation_end}
    return artifact, report