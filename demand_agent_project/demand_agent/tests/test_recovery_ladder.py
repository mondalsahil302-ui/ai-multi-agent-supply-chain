"""Unit tests for Layer 6: Multi-Tier Recovery and Fallback Ladder."""
import unittest
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.forecast.engine import WeeklyBatchForecastEngine


class TestRecoveryLadder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.db = get_db(cls.settings)
        cls.engine = WeeklyBatchForecastEngine(cls.db, cls.settings)

    def test_01_rung_1_champion_ridge_selected_when_approved(self):
        """Approved product (ICE-001) must select Rung 1: champion Ridge model."""
        res = self.engine.run_batch_forecast(
            warehouse_id="WH-001",
            product_id="ICE-001",
            target_week_id="W151",
            check_readiness_first=False,
        )
        task = res.tasks[0]
        self.assertEqual(task.status, "SUCCESS")
        self.assertEqual(task.method, "champion")
        self.assertEqual(task.model_name, "ridge")
        self.assertIsNotNone(task.point_forecast)

    def test_02_rung_2_standby_lightgbm_selected_when_not_approved(self):
        """Not-approved product (BAB-001) must automatically fall to Rung 2: LightGBM standby model."""
        # Confirm BAB-001 is NOT_APPROVED in model_registry
        doc = self.db["model_registry"].find_one({"product_id": "BAB-001"})
        self.assertEqual(doc["status"], "NOT_APPROVED")

        res = self.engine.run_batch_forecast(
            warehouse_id="WH-001",
            product_id="BAB-001",
            target_week_id="W151",
            check_readiness_first=False,
        )
        task = res.tasks[0]
        self.assertEqual(task.status, "SUCCESS")
        self.assertEqual(task.method, "fallback_model")
        self.assertEqual(task.model_name, "lightgbm_global_standby")
        self.assertIn("not_approved", task.fallback_reason)

    def test_03_rung_3_baseline_fallback_on_standby_failure(self):
        """When standby model is bypassed or forced to baseline, selects Rung 3: moving median baseline."""
        res = self.engine.run_batch_forecast(
            warehouse_id="WH-001",
            product_id="ICE-001",
            target_week_id="W151",
            check_readiness_first=False,
            force_rung="baseline",
        )
        task = res.tasks[0]
        self.assertEqual(task.status, "SUCCESS")
        self.assertEqual(task.method, "baseline")
        self.assertEqual(task.model_name, "moving_median_baseline")
        self.assertIsNotNone(task.point_forecast)

    def test_04_rung_4_controlled_failure_when_all_exhausted(self):
        """When all rungs fail or are forced down, yields Rung 4: controlled failure."""
        res = self.engine.run_batch_forecast(
            warehouse_id="WH-001",
            product_id="ICE-001",
            target_week_id="W151",
            check_readiness_first=False,
            force_rung="controlled_failure",
        )
        task = res.tasks[0]
        self.assertEqual(task.status, "FAILED")
        self.assertEqual(task.method, "none")
        self.assertIsNone(task.point_forecast)
        self.assertIn("No Safe Forecast Available", task.failure_reason)


if __name__ == "__main__":
    unittest.main()
