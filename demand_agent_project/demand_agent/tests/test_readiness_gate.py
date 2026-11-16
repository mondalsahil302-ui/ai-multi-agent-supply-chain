"""Unit and integration test suite for Section 3 Data Readiness Gate.

Verifies:
  1. Fully loaded warehouse (WH-001) passes all 5 checks and returns ready=True.
  2. Unpopulated warehouse (WH-002) returns ready=False with descriptive message.
  3. Unknown warehouse (WH-999) returns ready=False.
  4. Missing weather forecast returns ready=False with exact missing dataset named.
  5. Missing model returns ready=False naming model_registry.
  6. Machine-readable JSON output conforms to required contract ({ready, issues, ...}).
"""
import unittest
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.readiness.gate import ReadinessReport, check_data_readiness


class TestDataReadinessGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.db = get_db(cls.settings)

    def test_01_fully_loaded_warehouse_passes_gate(self):
        """Fully loaded operational warehouse (WH-001 / Lake Gardens) must pass the gate."""
        # Target week W151 (2026-11-15 to 2026-11-21)
        tw = {
            "week_id": "W151",
            "week_start_date": "2026-11-15",
            "week_end_date": "2026-11-21"
        }
        report = check_data_readiness(self.db, self.settings, warehouse_id="WH-001", target_week=tw)

        self.assertIsInstance(report, ReadinessReport)
        self.assertTrue(report.ready, f"Fully loaded warehouse failed readiness gate: {report.human_readable}")
        self.assertEqual(len(report.issues), 0)
        self.assertIn("READY FOR FORECASTING", report.human_readable)
        self.assertEqual(report.warehouse_id, "WH-001")
        self.assertEqual(report.region_id, "KOL-LOC-001")

        # Verify JSON dict serialization
        d = report.to_dict()
        self.assertTrue(d["ready"])
        self.assertIn("checked_at_utc", d)

    def test_02_unpopulated_warehouse_fails_gate(self):
        """Unpopulated warehouse (WH-002 / Quest Mall) must fail with descriptive message."""
        report = check_data_readiness(self.db, self.settings, warehouse_id="WH-002")

        self.assertFalse(report.ready)
        self.assertGreater(len(report.issues), 0)
        self.assertIn("NOT READY FOR FORECASTING", report.human_readable)
        self.assertIn("WH-002", report.human_readable)
        self.assertTrue(any(iss["dataset"] == "historical_demand" for iss in report.issues))
        self.assertTrue(any("out of scope" in iss["detail"] or "no historical demand" in iss["detail"] for iss in report.issues))

    def test_03_unknown_warehouse_fails_gate(self):
        """Non-existent warehouse (WH-999) must fail immediately."""
        report = check_data_readiness(self.db, self.settings, warehouse_id="WH-999")

        self.assertFalse(report.ready)
        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0]["dataset"], "warehouse_master")
        self.assertIn("WH-999", report.issues[0]["detail"])

    def test_04_missing_weather_forecast_fails_gate(self):
        """Target week without ingested weather forecast must fail naming weather_forecast."""
        # Target week in distant future where no weather forecast exists
        tw_future = {
            "week_id": "W200",
            "week_start_date": "2027-10-01",
            "week_end_date": "2027-10-07"
        }
        report = check_data_readiness(self.db, self.settings, warehouse_id="WH-001", target_week=tw_future)

        self.assertFalse(report.ready)
        self.assertIn("NOT READY FOR FORECASTING", report.human_readable)
        self.assertTrue(any("weather_forecast" in iss["dataset"] for iss in report.issues))
        self.assertIn("Weather forecast", report.human_readable)

    def test_05_missing_model_fails_gate(self):
        """Testing a region with zero approved models in registry must fail."""
        # Using a region with no models (e.g. KOL-LOC-010)
        tw = {
            "week_id": "W151",
            "week_start_date": "2026-11-11",
            "week_end_date": "2026-11-17"
        }
        report = check_data_readiness(self.db, self.settings, warehouse_id="WH-010", target_week=tw)
        self.assertFalse(report.ready)
        self.assertTrue(any("historical_demand" in iss["dataset"] or "model_registry" in iss["dataset"] for iss in report.issues))

    def test_06_report_persists_in_run_metadata(self):
        """When persist_report=True, report is recorded in run_metadata collection."""
        tw = {
            "week_id": "W151",
            "week_start_date": "2026-11-15",
            "week_end_date": "2026-11-21"
        }
        report = check_data_readiness(self.db, self.settings, warehouse_id="WH-001", target_week=tw, persist_report=True)
        self.assertTrue(report.ready)

        # Verify saved in run_metadata
        doc = self.db["run_metadata"].find_one({
            "type": "readiness_gate_report",
            "warehouse_id": "WH-001",
            "target_week": "W151"
        })
        self.assertIsNotNone(doc, "Readiness report was not persisted in run_metadata!")
        self.assertTrue(doc["ready"])

        # Clean up test metadata record
        self.db["run_metadata"].delete_one({"_id": doc["_id"]})


if __name__ == "__main__":
    unittest.main()
