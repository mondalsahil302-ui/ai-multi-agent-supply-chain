"""
baselines.py – Last-week and moving-average demand baselines.

These serve as reference benchmarks against which LightGBM and CatBoost
results are compared. Both baselines are strictly causal (no future data used).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from demand_agent.config import ENTITY_COLS, TIME_COL, TARGET_COL

logger = logging.getLogger(__name__)


def predict_last_week(df: pd.DataFrame) -> pd.Series:
    """
    Baseline 1 – Naive last-week: predict next-week demand = current-week units_sold.
    This is equivalent to lag_1w for the target.

    Returns a Series aligned to df.index.
    """
    return df["units_sold"].copy().rename("pred_last_week")


def predict_moving_average(
    df: pd.DataFrame,
    window: int = 4,
) -> pd.Series:
    """
    Baseline 2 – Moving-average: predict next-week demand = mean of last `window` weeks.
    Uses shift(1) inside the rolling to avoid same-week contamination.

    Returns a Series aligned to df.index.
    """
    df_sorted = df.sort_values(ENTITY_COLS + [TIME_COL])
    preds = (
        df_sorted.groupby(ENTITY_COLS)["units_sold"]
        .transform(
            lambda x: x.shift(1).rolling(window, min_periods=1).mean()
        )
        .round()
    )
    # Fallback: if rolling returns NaN, use last known value
    fallback = df_sorted.groupby(ENTITY_COLS)["units_sold"].transform(
        lambda x: x.shift(1)
    )
    preds = preds.fillna(fallback)
    preds = preds.reindex(df.index)
    return preds.rename(f"pred_ma{window}w")


def evaluate_baseline(
    name: str,
    y_true: pd.Series,
    y_pred: pd.Series,
) -> dict:
    """Quick scalar metrics for a baseline (see evaluate.py for full metrics)."""
    mask = y_true.notna() & y_pred.notna()
    yt = y_true[mask].values.astype(float)
    yp = y_pred[mask].values.astype(float)
    mae  = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    ss_res = np.sum((yt - yp) ** 2)
    ss_tot = np.sum((yt - yt.mean()) ** 2)
    r2   = float(1 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    wape = float(np.sum(np.abs(yt - yp)) / np.sum(np.abs(yt))) if np.sum(np.abs(yt)) > 0 else float("nan")
    bias = float(np.mean(yp - yt))
    logger.info(
        "%s baseline — MAE=%.2f RMSE=%.2f R2=%.4f WAPE=%.4f Bias=%.2f",
        name, mae, rmse, r2, wape, bias,
    )
    return {
        "model": name,
        "n_samples": int(mask.sum()),
        "MAE": mae,
        "RMSE": rmse,
        "R2": r2,
        "WAPE": wape,
        "ForecastBias": bias,
    }

