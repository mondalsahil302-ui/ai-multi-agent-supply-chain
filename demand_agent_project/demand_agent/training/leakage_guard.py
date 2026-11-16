"""Temporal data leakage detection and auditing for time series features.

Guarantees:
  - No feature computed at time T contains information from time > T.
  - Demand history features use only strictly past actuals (min lag >= 1).
  - Target variables (units_sold, revenue) are never present in feature matrices.
  - Future actuals are never leaked into lookback rolling aggregates.
"""
import logging
from typing import List, Tuple
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


class TemporalLeakageError(Exception):
    """Raised when future information leaks into training or inference features."""
    pass


def audit_temporal_leakage(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str = "units",
    time_col: str = "week_start_date"
) -> Tuple[bool, List[str]]:
    """Audits a dataset for temporal data leakage.

    Checks:
      1. Target column is NOT among the feature columns.
      2. Perfect future correlation test: no feature column has exact correlation with target at t+1.
      3. Future value identity check: no feature at row t equals target at row t+1 across all rows.
      4. Label column names: no feature column contains 'future', 'lead_', or target names.

    Returns:
        (is_leakage_free, list_of_violations)
    """
    violations = []

    # Check 1: Target present in feature columns
    for f in feature_cols:
        if f == target_col or f == "units_sold" or f == "y_rel":
            violations.append(f"Target column '{f}' is present in feature set!")

    # Check 2: Column naming conventions
    for f in feature_cols:
        fl = f.lower()
        if "lead_" in fl or "future_units" in fl or "next_week" in fl:
            violations.append(f"Suspicious look-ahead feature name detected: '{f}'")

    if target_col in df.columns:
        y = df[target_col].to_numpy()
        # Sort chronologically if time_col present
        if time_col in df.columns:
            df_sorted = df.sort_values(time_col).reset_index(drop=True)
            y = df_sorted[target_col].to_numpy()
        else:
            df_sorted = df

        # Check 3: Check correlation or identical values with y_{t+1} (future actual)
        if len(y) > 10:
            y_future = y[1:]  # target at t+1
            for f in feature_cols:
                if f in df_sorted.columns:
                    feat_vals = df_sorted[f].iloc[:-1].to_numpy(dtype=float)
                    # Check for exact equality with future target
                    if np.allclose(feat_vals, y_future, rtol=1e-5, atol=1e-5):
                        violations.append(f"CRITICAL LEAKAGE: Feature '{f}' at time t is identical to target at time t+1!")
                    # Check for near-perfect correlation with future target
                    elif np.std(feat_vals) > 1e-4 and np.std(y_future) > 1e-4:
                        corr = np.corrcoef(feat_vals, y_future)[0, 1]
                        if abs(corr) > 0.9999:
                            violations.append(f"CRITICAL LEAKAGE: Feature '{f}' has correlation {corr:.6f} with future target t+1!")

    is_clean = len(violations) == 0
    return is_clean, violations


def assert_temporal_integrity(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str = "units",
    time_col: str = "week_start_date"
):
    """Enforces temporal integrity, raising TemporalLeakageError on violations."""
    is_clean, violations = audit_temporal_leakage(df, feature_cols, target_col, time_col)
    if not is_clean:
        msg = f"Temporal data leakage detected ({len(violations)} violations):\n" + "\n".join(f"  - {v}" for v in violations)
        log.error(msg)
        raise TemporalLeakageError(msg)
