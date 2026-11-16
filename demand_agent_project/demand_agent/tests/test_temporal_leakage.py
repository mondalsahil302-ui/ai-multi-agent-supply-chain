"""Test temporal data leakage guard.

Verifies:
  1. Valid historical demand features pass temporal integrity checks with zero violations.
  2. Artificially injected future leakage (e.g. future target y_{t+1} injected as a feature)
     is caught and raises TemporalLeakageError.
"""
import unittest
import numpy as np
import pandas as pd

from demand_agent.features import FEATURE_COLUMNS
from demand_agent.training.leakage_guard import (
    TemporalLeakageError,
    assert_temporal_integrity,
    audit_temporal_leakage,
)


class TestTemporalLeakageGuard(unittest.TestCase):
    def setUp(self):
        # Create a synthetic series with 50 weeks
        dates = pd.date_range("2025-01-05", periods=50, freq="7D")
        np.random.seed(42)
        units = np.random.poisson(lam=45, size=50).astype(float)

        self.df = pd.DataFrame({
            "week_start_date": dates,
            "units": units,
            "lag_1": np.roll(units, 1),
            "lag_2": np.roll(units, 2),
            "temp_c": np.random.uniform(20, 35, size=50)
        })
        self.df.loc[0, "lag_1"] = 0
        self.df.loc[0:1, "lag_2"] = 0

    def test_01_clean_features_pass_leakage_check(self):
        """Legitimate lag and contemporaneous features must pass temporal integrity."""
        feature_cols = ["lag_1", "lag_2", "temp_c"]
        is_clean, violations = audit_temporal_leakage(self.df, feature_cols, target_col="units")
        self.assertTrue(is_clean, f"Clean features unexpectedly flagged for leakage: {violations}")
        self.assertEqual(len(violations), 0)

        # Should not raise
        assert_temporal_integrity(self.df, feature_cols, target_col="units")

    def test_02_injected_future_target_caught(self):
        """Injected future target y_{t+1} must be detected and raise TemporalLeakageError."""
        leaky_df = self.df.copy()
        # Inject future target at t+1 as a feature 'lookahead_demand'
        leaky_df["lookahead_demand"] = np.roll(leaky_df["units"], -1)
        feature_cols = ["lag_1", "temp_c", "lookahead_demand"]

        is_clean, violations = audit_temporal_leakage(leaky_df, feature_cols, target_col="units")
        self.assertFalse(is_clean, "Injected future target leakage was NOT caught!")
        self.assertTrue(any("identical to target at time t+1" in v or "CRITICAL LEAKAGE" in v for v in violations))

        # assert_temporal_integrity must raise TemporalLeakageError
        with self.assertRaises(TemporalLeakageError) as ctx:
            assert_temporal_integrity(leaky_df, feature_cols, target_col="units")
        self.assertIn("CRITICAL LEAKAGE", str(ctx.exception))

    def test_03_target_in_features_caught(self):
        """Including target column itself in features must raise TemporalLeakageError."""
        feature_cols = ["lag_1", "units"]
        with self.assertRaises(TemporalLeakageError):
            assert_temporal_integrity(self.df, feature_cols, target_col="units")


if __name__ == "__main__":
    unittest.main()
