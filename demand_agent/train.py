"""
train.py – LightGBM and CatBoost model training with time-based validation.

Design:
  - Single-split training: fit on train, tune on val, evaluate on test.
  - Walk-forward evaluation: roll through test weeks one at a time,
    re-scoring (not re-fitting) to simulate real deployment.
  - Categorical features passed natively to both frameworks.
  - All hyperparameters are documented and reproducible via SEED.
"""

from __future__ import annotations

import json
import logging
import pickle
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool

from demand_agent.config import (
    ENTITY_COLS, TIME_COL, TARGET_COL,
    CAT_COLS, MODELS_DIR, METRICS_DIR,
    TRAIN_END_IDX, VAL_END_IDX,
)
from demand_agent.features import get_feature_columns, verify_no_leakage

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)

SEED = 42


# ─── Categorical handling helpers ─────────────────────────────────────────────

def _safe_cat_cols(feature_cols: List[str]) -> List[str]:
    """Return intersection of CAT_COLS and feature_cols (some may be absent)."""
    return [c for c in CAT_COLS if c in feature_cols]


def validate_feature_dtypes(X: pd.DataFrame, context: str = "Training") -> None:
    """Validate that all columns in X have dtypes acceptable to LightGBM/CatBoost."""
    bad_cols = {}
    for c in X.columns:
        dt = X[c].dtype
        is_ok = (
            pd.api.types.is_numeric_dtype(dt)
            or isinstance(dt, pd.CategoricalDtype)
            or pd.api.types.is_bool_dtype(dt)
        )
        if not is_ok:
            bad_cols[c] = str(dt)
    if bad_cols:
        raise TypeError(
            f"[{context}] Incompatible feature dtypes detected! Model requires numeric, bool, or categorical dtypes. "
            f"Found invalid columns: {bad_cols}"
        )


def _lgb_prepare(
    df: pd.DataFrame,
    feature_cols: List[str],
    cat_cols: List[str],
) -> Tuple[pd.DataFrame, Optional[pd.Series]]:
    """
    Prepare X, y for LightGBM.
    Categoricals and all string/object columns are cast to 'category' dtype (LightGBM native).
    """
    X = df[feature_cols].copy()
    y = df[TARGET_COL].copy() if TARGET_COL in df.columns else None
    for c in feature_cols:
        dt = X[c].dtype
        if (
            c in cat_cols
            or dt == "object"
            or isinstance(dt, pd.StringDtype)
            or str(dt) in ("str", "string", "object")
        ):
            X[c] = X[c].astype("category")
    return X, y


# ─── LightGBM Training ────────────────────────────────────────────────────────

LGB_PARAMS = {
    "objective": "regression_l1",   # MAE loss (robust to outliers)
    "metric": ["mae", "rmse"],
    "n_estimators": 1000,
    "learning_rate": 0.05,
    "num_leaves": 63,
    "max_depth": -1,
    "min_child_samples": 20,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": SEED,
    "n_jobs": -1,
    "verbose": -1,
}


def train_lightgbm(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    feature_cols: List[str],
) -> lgb.LGBMRegressor:
    """
    Fit LightGBM with early stopping on the validation set.
    Returns the fitted model.
    """
    cat_cols = _safe_cat_cols(feature_cols)
    verify_no_leakage(feature_cols)

    X_train, y_train = _lgb_prepare(df_train, feature_cols, cat_cols)
    X_val,   y_val   = _lgb_prepare(df_val,   feature_cols, cat_cols)

    # Validate feature dtypes before fitting
    validate_feature_dtypes(X_train, context="LightGBM X_train")
    validate_feature_dtypes(X_val,   context="LightGBM X_val")

    logger.info(
        "Training LightGBM on %d samples (%d features, %d cat cols)...",
        len(X_train), len(feature_cols), len(cat_cols),
    )

    model = lgb.LGBMRegressor(**LGB_PARAMS)
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        eval_names=["val"],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50, verbose=False),
            lgb.log_evaluation(period=-1),
        ],
        categorical_feature=cat_cols if cat_cols else "auto",
    )

    best_iter = model.best_iteration_
    logger.info("LightGBM best iteration: %d", best_iter)
    return model


# ─── CatBoost Training ────────────────────────────────────────────────────────

CB_PARAMS = {
    "loss_function": "MAE",
    "eval_metric": "RMSE",
    "iterations": 500,
    "learning_rate": 0.08,
    "depth": 6,
    "l2_leaf_reg": 3.0,
    "random_strength": 1.0,
    "bagging_temperature": 1.0,
    "border_count": 128,
    "random_seed": SEED,
    "thread_count": -1,
    "verbose": 0,
    "allow_writing_files": False,
    "early_stopping_rounds": 40,
}


def train_catboost(
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
    feature_cols: List[str],
) -> CatBoostRegressor:
    """
    Fit CatBoost with early stopping on the validation set.
    Categorical columns are passed natively without label encoding.
    Returns the fitted model.
    """
    cat_cols = _safe_cat_cols(feature_cols)
    verify_no_leakage(feature_cols)

    X_train = df_train[feature_cols].copy()
    y_train = df_train[TARGET_COL].copy()
    X_val   = df_val[feature_cols].copy()
    y_val   = df_val[TARGET_COL].copy()

    # Fill NaN in categoricals with a sentinel string (CatBoost requires non-NaN cats)
    for c in cat_cols:
        if c in X_train.columns:
            X_train[c] = X_train[c].astype(str).fillna("__missing__")
            X_val[c]   = X_val[c].astype(str).fillna("__missing__")

    cat_feature_indices = [X_train.columns.tolist().index(c) for c in cat_cols if c in X_train.columns]

    logger.info(
        "Training CatBoost on %d samples (%d features, %d cat cols)...",
        len(X_train), len(feature_cols), len(cat_cols),
    )

    train_pool = Pool(X_train, y_train, cat_features=cat_feature_indices)
    val_pool   = Pool(X_val,   y_val,   cat_features=cat_feature_indices)

    model = CatBoostRegressor(**CB_PARAMS)
    model.fit(train_pool, eval_set=val_pool, use_best_model=True)

    best_iter = model.best_iteration_
    logger.info("CatBoost best iteration: %d", best_iter)
    return model


# ─── Prediction helpers ───────────────────────────────────────────────────────

def predict_lgb(
    model: lgb.LGBMRegressor,
    df: pd.DataFrame,
    feature_cols: List[str],
) -> np.ndarray:
    cat_cols = _safe_cat_cols(feature_cols)
    X, _ = _lgb_prepare(df, feature_cols, cat_cols)
    validate_feature_dtypes(X, context="LightGBM inference")
    preds = model.predict(X)
    return np.maximum(preds, 0)   # demand cannot be negative


def predict_cb(
    model: CatBoostRegressor,
    df: pd.DataFrame,
    feature_cols: List[str],
) -> np.ndarray:
    cat_cols = _safe_cat_cols(feature_cols)
    X = df[feature_cols].copy()
    for c in cat_cols:
        if c in X.columns:
            X[c] = X[c].astype(str).fillna("__missing__")
    preds = model.predict(X)
    return np.maximum(preds, 0)


# ─── Walk-forward evaluation ──────────────────────────────────────────────────

def walk_forward_evaluate(
    df: pd.DataFrame,
    model_lgb: lgb.LGBMRegressor,
    model_cb: CatBoostRegressor,
    feature_cols: List[str],
) -> pd.DataFrame:
    """
    Simulate week-by-week forecasting over the test set.
    For each test week t:
      - Score both models on all rows where week_idx == t
      - Predictions are based on features computed from data up to week t-1
        (guaranteed by lag/rolling features computed once at build_features time)

    Returns a DataFrame with per-row predictions for all test weeks.
    """
    test_df = df[df["split"] == "test"].copy()
    test_weeks = sorted(test_df["week_idx"].unique())

    logger.info("Walk-forward evaluation over %d test weeks (%d rows)...", len(test_weeks), len(test_df))

    test_df["pred_lgb"] = predict_lgb(model_lgb, test_df, feature_cols)
    test_df["pred_cb"]  = predict_cb(model_cb,   test_df, feature_cols)
    test_df["pred_ensemble"] = 0.5 * test_df["pred_lgb"] + 0.5 * test_df["pred_cb"]

    logger.info("Walk-forward evaluation complete.")
    return test_df


# ─── Model persistence ────────────────────────────────────────────────────────

def save_models(
    model_lgb: lgb.LGBMRegressor,
    model_cb: CatBoostRegressor,
    feature_cols: List[str],
    meta: dict,
    output_dir: Path = MODELS_DIR,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # LightGBM – pickle + booster text
    lgb_path = output_dir / "lightgbm_model.pkl"
    with open(lgb_path, "wb") as f:
        pickle.dump(model_lgb, f)
    model_lgb.booster_.save_model(str(output_dir / "lightgbm_booster.txt"))
    logger.info("LightGBM saved to %s", lgb_path)

    # CatBoost – native format
    cb_path = output_dir / "catboost_model.cbm"
    model_cb.save_model(str(cb_path))
    logger.info("CatBoost saved to %s", cb_path)

    # Feature list + metadata
    artifact = {
        "feature_cols": feature_cols,
        "n_features": len(feature_cols),
        "lgb_best_iteration": int(model_lgb.best_iteration_),
        "cb_best_iteration": int(model_cb.best_iteration_),
        "lgb_params": LGB_PARAMS,
        "cb_params": CB_PARAMS,
        **meta,
    }
    meta_path = output_dir / "model_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(artifact, f, indent=2, default=str)
    logger.info("Model metadata saved to %s", meta_path)


def load_models(
    output_dir: Path = MODELS_DIR,
) -> Tuple[lgb.LGBMRegressor, CatBoostRegressor, List[str]]:
    lgb_path = output_dir / "lightgbm_model.pkl"
    cb_path  = output_dir / "catboost_model.cbm"
    meta_path = output_dir / "model_metadata.json"

    with open(lgb_path, "rb") as f:
        model_lgb = pickle.load(f)

    model_cb = CatBoostRegressor()
    model_cb.load_model(str(cb_path))

    with open(meta_path) as f:
        meta = json.load(f)

    return model_lgb, model_cb, meta["feature_cols"]

