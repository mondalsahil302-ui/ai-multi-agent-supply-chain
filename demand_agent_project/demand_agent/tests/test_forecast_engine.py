"""Unit and integration tests for WeeklyBatchForecastEngine (Layer 5)."""
import os
import unittest
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.forecast.engine import WeeklyBatchForecastEngine, ReadinessGateBlockedError


class TestForecastEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.db = get_db(cls.settings)
        cls.engine = WeeklyBatchForecastEngine(cls.db, cls.settings)

    def test_01_single_product_forecast(self):
        """Verifies single product forecast execution, bounds, and fields."""
        res = self.engine.run_batch_forecast(
            warehouse_id="WH-001",
            product_id="ICE-001",
            target_week_id="W151",
            check_readiness_first=True,
        )
        self.assertEqual(res.status, "SUCCESS")
        self.assertEqual(res.total_tasks, 1)
        self.assertEqual(res.succeeded_tasks, 1)
        self.assertEqual(res.failed_tasks, 0)

        task = res.tasks[0]
        self.assertEqual(task.product_id, "ICE-001")
        self.assertIsNotNone(task.point_forecast)
        self.assertGreater(task.point_forecast, 0)
        self.assertLessEqual(task.p10, task.p50)
        self.assertLessEqual(task.p50, task.p90)
        self.assertIn(task.method, ("champion", "fallback_model", "baseline"))

        # Verify saved in forecast_results
        doc = self.db["forecast_results"].find_one({
            "run_id": res.run_id,
            "product_id": "ICE-001",
            "target_week": "W151",
        })
        self.assertIsNotNone(doc)
        self.assertEqual(doc["status"], "SUCCESS")
        self.assertEqual(doc["point_forecast"], round(task.point_forecast, 2))

    def test_02_full_batch_forecast_200_products(self):
        """Verifies full batch execution across all 200 products with task isolation."""
        res = self.engine.run_batch_forecast(
            warehouse_id="WH-001",
            target_week_id="W151",
            check_readiness_first=True,
        )
        self.assertEqual(res.total_tasks, 200)
        self.assertEqual(res.succeeded_tasks, 200)
        self.assertEqual(res.failed_tasks, 0)
        self.assertEqual(res.status, "SUCCESS")

        # Verify method breakdown
        counts = res.counts_by_method
        self.assertGreater(counts["champion"], 100, f"Expected >100 champions, got {counts}")
        self.assertGreater(counts["fallback_model"], 50, f"Expected >50 fallbacks, got {counts}")

        # Verify run_metadata record
        meta = self.db["run_metadata"].find_one({"run_id": res.run_id})
        self.assertIsNotNone(meta)
        self.assertEqual(meta["total_tasks"], 200)
        self.assertEqual(meta["succeeded_tasks"], 200)
        self.assertEqual(meta["status"], "SUCCESS")

    def test_03_readiness_gate_refusal_blocks_forecast(self):
        """Verifies that an unpopulated warehouse is blocked by the gate with 0 forecast writes."""
        initial_count = self.db["forecast_results"].count_documents({"warehouse_id": "WH-002"})
        with self.assertRaises(ReadinessGateBlockedError):
            self.engine.run_batch_forecast(
                warehouse_id="WH-002",
                target_week_id="W151",
                check_readiness_first=True,
            )
        final_count = self.db["forecast_results"].count_documents({"warehouse_id": "WH-002"})
        self.assertEqual(initial_count, final_count, "Gate failure must not write any forecast results!")


if __name__ == "__main__":
    unittest.main()
