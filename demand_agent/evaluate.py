"""
evaluate.py – Comprehensive evaluation metrics and visualisation.

Metrics computed:
  Regression:  MAE, RMSE, R2, WAPE (Weighted Absolute Percentage Error),
               Forecast Bias (mean signed error)
  Ranking:     Precision@K, NDCG@K, Demand Capture@K
               (grouped by region × target week)

Ranking limitation notice:
  The dataset contains at most 5 products per region-week (top-5 anchor export).
  Precision@10, NDCG@10, and Demand Capture@10 cannot be validly computed on
  fewer than 10 items. This module:
    - Raises a LimitationError if K > available products per group.
    - Computes @K for K = min(RANK_K_REQUESTED, RANK_K_AVAILABLE) = 5.
    - Reports the limitation explicitly in all outputs.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import r2_score

from demand_agent.config import (
    TARGET_COL, TIME_COL,
    CHARTS_DIR, METRICS_DIR,
    RANK_K_AVAILABLE, RANK_K_REQUESTED,
)

logger = logging.getLogger(__name__)
warnings.filterwarnings("ignore")
sns.set_theme(style="whitegrid", palette="muted")

EFFECTIVE_K = min(RANK_K_REQUESTED, RANK_K_AVAILABLE)   # 10 when 200 products available


class LimitationError(Exception):
    """Raised when a metric cannot be validly computed given dataset constraints."""
    pass


# ─── Regression metrics ───────────────────────────────────────────────────────

def regression_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    model_name: str = "model",
) -> dict:
    """
    Compute MAE, RMSE, R2, WAPE, and ForecastBias.
    All values rounded to 4 decimal places.
    """
    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    yt = y_true[mask].astype(float)
    yp = y_pred[mask].astype(float)
    n  = len(yt)

    if n == 0:
        raise ValueError(f"No valid samples for {model_name}.")

    mae  = float(np.mean(np.abs(yt - yp)))
    rmse = float(np.sqrt(np.mean((yt - yp) ** 2)))
    r2   = float(r2_score(yt, yp))
    wape = float(np.sum(np.abs(yt - yp)) / np.sum(np.abs(yt))) if np.sum(np.abs(yt)) > 0 else float("nan")
    bias = float(np.mean(yp - yt))

    metrics = {
        "model": model_name,
        "n_samples": n,
        "MAE": round(mae, 4),
        "RMSE": round(rmse, 4),
        "R2": round(r2, 4),
        "WAPE": round(wape, 4),
        "ForecastBias": round(bias, 4),
    }
    logger.info(
        "[%s] MAE=%.2f RMSE=%.2f R2=%.4f WAPE=%.4f Bias=%.2f",
        model_name, mae, rmse, r2, wape, bias,
    )
    return metrics


# ─── Ranking metrics ──────────────────────────────────────────────────────────

def _dcg_at_k(relevances: np.ndarray, k: int) -> float:
    """Discounted Cumulative Gain at K."""
    top_k = relevances[:k]
    gains = top_k / np.log2(np.arange(2, len(top_k) + 2))
    return float(gains.sum())


def _ndcg_at_k(y_true_ranked: np.ndarray, y_pred_ranked: np.ndarray, k: int) -> float:
    """
    NDCG@K for a single group.
    y_true_ranked: actual demand values sorted by predicted demand (descending).
    y_pred_ranked: unused here (relevances come from y_true order).
    """
    ideal = np.sort(y_true_ranked)[::-1]
    dcg   = _dcg_at_k(y_true_ranked, k)
    idcg  = _dcg_at_k(ideal, k)
    if idcg == 0:
        return float("nan")
    return dcg / idcg


def ranking_metrics_per_group(
    df: pd.DataFrame,
    pred_col: str,
    k: int = EFFECTIVE_K,
    group_cols: Optional[List[str]] = None,
) -> Dict[str, float]:
    """
    Compute Precision@K, NDCG@K, and Demand Capture@K grouped by
    (location_id, week_start_date).

    Precision@K : fraction of top-K predicted products that are in actual top-K.
    NDCG@K      : normalised DCG where relevance = actual demand units.
    Demand Capture@K : sum(actual demand of top-K predicted) / sum(all actual demand in group).

    Parameters
    ----------
    df        : DataFrame with predictions and actual targets.
    pred_col  : column name of model predictions.
    k         : number of top items to consider.
    group_cols: grouping columns (default: ['location_id', TIME_COL]).

    Returns aggregated metrics dict.
    """
    if group_cols is None:
        group_cols = ["location_id", TIME_COL]

    # Check feasibility
    max_group_size = df.groupby(group_cols)[TARGET_COL].count().max()
    if k > max_group_size:
        raise LimitationError(
            f"Cannot compute @{k} metrics: maximum group size is {max_group_size}. "
            f"Dataset contains only {RANK_K_AVAILABLE} products per region-week. "
            f"Computing @{max_group_size} instead. "
            f"To compute @{RANK_K_REQUESTED}, ingest the full 200-product dataset."
        )

    precision_list = []
    ndcg_list      = []
    capture_list   = []

    for _, grp in df.groupby(group_cols):
        n = len(grp)
        if n == 0:
            continue
        effective_k = min(k, n)

        # Sort by predicted demand descending → top-K predicted
        pred_order = grp[pred_col].values.argsort()[::-1][:effective_k]
        true_vals  = grp[TARGET_COL].values

        # Actual top-K indices (by true demand)
        true_order = true_vals.argsort()[::-1][:effective_k]
        true_top_k_set = set(true_order)

        # Precision@K: how many of pred top-K are in actual top-K
        pred_top_k_set = set(pred_order)
        precision = len(pred_top_k_set & true_top_k_set) / effective_k
        precision_list.append(precision)

        # NDCG@K: relevance = actual demand of predicted-ranked items
        true_in_pred_order = true_vals[pred_order]
        ndcg = _ndcg_at_k(true_in_pred_order, None, effective_k)
        if not np.isnan(ndcg):
            ndcg_list.append(ndcg)

        # Demand Capture@K: fraction of total demand captured by top-K predicted
        total_demand = true_vals.sum()
        captured_demand = true_vals[pred_order].sum()
        capture = captured_demand / total_demand if total_demand > 0 else float("nan")
        if not np.isnan(capture):
            capture_list.append(capture)

    eff_k_str = f"@{k}" if k == EFFECTIVE_K else f"@{k}(capped)"
    return {
        f"Precision{eff_k_str}": round(float(np.mean(precision_list)), 4) if precision_list else float("nan"),
        f"NDCG{eff_k_str}": round(float(np.mean(ndcg_list)), 4) if ndcg_list else float("nan"),
        f"DemandCapture{eff_k_str}": round(float(np.mean(capture_list)), 4) if capture_list else float("nan"),
        "n_groups": len(precision_list),
        "k_used": k,
    }


def compute_all_metrics(
    df_results: pd.DataFrame,
    model_configs: List[Tuple[str, str]],   # [(model_name, pred_col), ...]
) -> Tuple[List[dict], str]:
    """
    Compute full metric suite for each model.
    Returns (metrics_list, limitation_notice).
    """
    all_metrics = []
    limitation_notice = ""

    for model_name, pred_col in model_configs:
        if pred_col not in df_results.columns:
            logger.warning("Prediction column %s not found, skipping.", pred_col)
            continue

        mask = df_results[TARGET_COL].notna() & df_results[pred_col].notna()
        df_valid = df_results[mask].copy()

        # Regression
        reg = regression_metrics(
            df_valid[TARGET_COL].values,
            df_valid[pred_col].values,
            model_name=model_name,
        )

        # Ranking at Top-10
        rank_k = ranking_metrics_per_group(
            df_valid, pred_col, k=EFFECTIVE_K
        )
        combined = {**reg, **rank_k}
        all_metrics.append(combined)

    return all_metrics, limitation_notice


# ─── Walk-forward metric aggregation ──────────────────────────────────────────

def walk_forward_metrics(
    df_wf: pd.DataFrame,
    pred_col: str,
    model_name: str,
) -> pd.DataFrame:
    """
    Compute per-week MAE, RMSE, WAPE for walk-forward results.
    Useful for plotting forecast accuracy over time.
    """
    records = []
    for wk, grp in df_wf.groupby("week_idx"):
        mask = grp[TARGET_COL].notna() & grp[pred_col].notna()
        grp_valid = grp[mask]
        if len(grp_valid) == 0:
            continue
        yt = grp_valid[TARGET_COL].values.astype(float)
        yp = grp_valid[pred_col].values.astype(float)
        records.append({
            "week_idx": wk,
            TIME_COL: grp_valid[TIME_COL].iloc[0],
            "MAE": float(np.mean(np.abs(yt - yp))),
            "RMSE": float(np.sqrt(np.mean((yt - yp) ** 2))),
            "WAPE": float(np.sum(np.abs(yt - yp)) / np.sum(np.abs(yt))),
            "model": model_name,
        })
    return pd.DataFrame(records)


# ─── Charts ───────────────────────────────────────────────────────────────────

def plot_actual_vs_predicted(
    df: pd.DataFrame,
    pred_col: str,
    model_name: str,
    out_dir: Path = CHARTS_DIR,
) -> Path:
    """Scatter plot of actual vs predicted demand."""
    mask = df[TARGET_COL].notna() & df[pred_col].notna()
    yt = df.loc[mask, TARGET_COL].values
    yp = df.loc[mask, pred_col].values

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(yt, yp, alpha=0.3, s=15, color="steelblue", edgecolors="none")
    lo, hi = min(yt.min(), yp.min()), max(yt.max(), yp.max())
    ax.plot([lo, hi], [lo, hi], "r--", linewidth=1.5, label="Perfect forecast")
    ax.set_xlabel("Actual next-week demand (units)")
    ax.set_ylabel("Predicted next-week demand (units)")
    ax.set_title(f"{model_name} — Actual vs Predicted (test set)")
    ax.legend()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{model_name.lower().replace(' ', '_')}_actual_vs_pred.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved: %s", path)
    return path


def plot_residuals(
    df: pd.DataFrame,
    pred_col: str,
    model_name: str,
    out_dir: Path = CHARTS_DIR,
) -> Path:
    """Residual distribution plot."""
    mask = df[TARGET_COL].notna() & df[pred_col].notna()
    residuals = (df.loc[mask, pred_col] - df.loc[mask, TARGET_COL]).values

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # Histogram
    axes[0].hist(residuals, bins=50, color="steelblue", edgecolor="white", alpha=0.8)
    axes[0].axvline(0, color="red", linestyle="--")
    axes[0].set_title(f"{model_name} — Residual Distribution")
    axes[0].set_xlabel("Residual (Predicted − Actual)")
    axes[0].set_ylabel("Count")

    # Residuals vs actual
    yt = df.loc[mask, TARGET_COL].values
    axes[1].scatter(yt, residuals, alpha=0.3, s=12, color="steelblue", edgecolors="none")
    axes[1].axhline(0, color="red", linestyle="--")
    axes[1].set_title(f"{model_name} — Residuals vs Actual Demand")
    axes[1].set_xlabel("Actual Demand")
    axes[1].set_ylabel("Residual")

    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{model_name.lower().replace(' ', '_')}_residuals.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved: %s", path)
    return path


def plot_walk_forward_mae(
    wf_records: List[pd.DataFrame],
    out_dir: Path = CHARTS_DIR,
) -> Path:
    """Line plot of walk-forward MAE over test weeks, one line per model."""
    fig, ax = plt.subplots(figsize=(12, 4))
    colors = ["steelblue", "darkorange", "seagreen", "crimson", "purple"]
    for i, wf_df in enumerate(wf_records):
        if wf_df.empty:
            continue
        model_name = wf_df["model"].iloc[0]
        ax.plot(
            wf_df[TIME_COL], wf_df["MAE"],
            marker="o", markersize=3, linewidth=1.5,
            color=colors[i % len(colors)], label=model_name,
        )
    ax.set_title("Walk-forward MAE by test week")
    ax.set_xlabel("Forecast week")
    ax.set_ylabel("MAE (units)")
    ax.legend()
    fig.autofmt_xdate()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "walk_forward_mae.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved: %s", path)
    return path


def plot_feature_importance(
    model_lgb,
    feature_cols: List[str],
    top_n: int = 30,
    out_dir: Path = CHARTS_DIR,
) -> Path:
    """Horizontal bar chart of LightGBM feature importances."""
    imp = pd.Series(
        model_lgb.feature_importances_, index=feature_cols
    ).sort_values(ascending=False).head(top_n)

    fig, ax = plt.subplots(figsize=(8, max(4, top_n * 0.3)))
    imp[::-1].plot(kind="barh", ax=ax, color="steelblue", edgecolor="white")
    ax.set_title(f"LightGBM top-{top_n} feature importances (gain)")
    ax.set_xlabel("Importance score")
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "lgb_feature_importance.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved: %s", path)
    return path


def plot_metrics_comparison(
    metrics_list: List[dict],
    out_dir: Path = CHARTS_DIR,
) -> Path:
    """Bar chart comparing MAE/RMSE/WAPE across models."""
    df_m = pd.DataFrame(metrics_list).set_index("model")
    metrics_to_plot = ["MAE", "RMSE", "WAPE"]
    df_m = df_m[[c for c in metrics_to_plot if c in df_m.columns]]

    fig, axes = plt.subplots(1, len(df_m.columns), figsize=(5 * len(df_m.columns), 5))
    if len(df_m.columns) == 1:
        axes = [axes]

    colors = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2"]
    for ax, col in zip(axes, df_m.columns):
        bars = ax.bar(
            df_m.index, df_m[col],
            color=colors[:len(df_m)], edgecolor="white",
        )
        ax.set_title(col)
        ax.set_ylabel("Value")
        ax.tick_params(axis="x", rotation=30)
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2, h + 0.002,
                    f"{h:.2f}", ha="center", va="bottom", fontsize=9)

    fig.suptitle("Model comparison — error metrics (test set)", fontsize=13)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "metrics_comparison.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved: %s", path)
    return path


def plot_top10_demand_by_region(
    df_results: pd.DataFrame,
    pred_col: str,
    model_name: str,
    target_week: Optional[pd.Timestamp] = None,
    out_dir: Path = CHARTS_DIR,
) -> Path:
    """
    Bar chart of predicted top-K demand products for each of 40 Kolkata regions
    for a specific target week (latest test week by default).

    Note: Limited to EFFECTIVE_K (5) products per region due to dataset scope.
    """
    if target_week is None:
        # Use the last test week with valid predictions
        valid = df_results[df_results[pred_col].notna()]
        target_week = valid[TIME_COL].max()

    week_df = df_results[df_results[TIME_COL] == target_week].copy()
    if week_df.empty:
        logger.warning("No data for target week %s", target_week)
        return None

    # Top-K by predicted demand per region
    top_k_df = (
        week_df.sort_values(pred_col, ascending=False)
        .groupby("location_id")
        .head(EFFECTIVE_K)
        .reset_index(drop=True)
    )

    n_regions = top_k_df["location_id"].nunique()
    n_cols = 4
    n_rows = (n_regions + n_cols - 1) // n_cols

    fig = plt.figure(figsize=(5 * n_cols, 3.5 * n_rows))
    fig.suptitle(
        f"{model_name} — Predicted Top-{EFFECTIVE_K} demand products per region\n"
        f"Target week: {target_week.date() if hasattr(target_week, 'date') else target_week}",
        fontsize=13, y=1.01,
    )

    for i, (loc_id, grp) in enumerate(top_k_df.groupby("location_id")):
        ax = fig.add_subplot(n_rows, n_cols, i + 1)
        region_name = grp["region_of_kolkata"].iloc[0]
        grp_sorted = grp.sort_values(pred_col, ascending=True)
        labels = [f"{r['product_id']}\n{r['product_name'][:18]}" for _, r in grp_sorted.iterrows()]
        ax.barh(labels, grp_sorted[pred_col], color="steelblue", edgecolor="white")
        ax.set_title(region_name, fontsize=9, pad=3)
        ax.set_xlabel("Pred units", fontsize=7)
        ax.tick_params(axis="y", labelsize=6)

    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"top{EFFECTIVE_K}_demand_by_region_{model_name.lower().replace(' ','_')}.png"
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    logger.info("Chart saved: %s", path)
    return path


# ─── Metrics persistence ──────────────────────────────────────────────────────

def save_metrics(
    metrics_list: List[dict],
    limitation_notice: str,
    out_dir: Path = METRICS_DIR,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "metrics": metrics_list,
        "limitation_notice": limitation_notice,
        "ranking_k_requested": RANK_K_REQUESTED,
        "ranking_k_available": RANK_K_AVAILABLE,
        "ranking_k_used": EFFECTIVE_K,
    }
    path = out_dir / "evaluation_metrics.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    # Also save as CSV for easy inspection
    df_m = pd.DataFrame(metrics_list)
    df_m.to_csv(out_dir / "evaluation_metrics.csv", index=False)
    logger.info("Metrics saved to %s", path)
    return path

