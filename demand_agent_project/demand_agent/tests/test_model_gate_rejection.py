"""Test model quality gate rejection and champion preservation.

Verifies:
  1. A worse candidate model is rejected by Gate Rule C.
  2. An existing approved champion is preserved in the model registry and never
     replaced by a failing candidate.
"""
import unittest
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.training.gate import GateThresholds, evaluate_gate
from demand_agent.training.registry import register


class TestModelGateRejection(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.db = get_db(self.settings)
        self.thresholds = GateThresholds(
            max_wape_pct=35.0,
            max_abs_bias_pct=10.0,
            max_worse_than_baseline_pts=1.0,
            rule="C"
        )
        self.test_col = "test_model_registry_gate"

    def tearDown(self):
        self.db[self.test_col].drop()

    def test_01_worse_model_gate_verdict_fail(self):
        """A model that exceeds WAPE or is worse than baseline must FAIL the gate."""
        # Scenario A: WAPE exceeds 35%
        metrics_high_wape = {
            "test_ridge": {"WAPE_pct": 38.5, "Bias_pct": 3.0},
            "test_moving_median": {"WAPE_pct": 20.0},
            "test_seasonal_naive": {"WAPE_pct": 22.0}
        }
        res_a = evaluate_gate(metrics_high_wape, self.thresholds)
        self.assertEqual(res_a["verdict"], "FAIL")
        self.assertTrue(any("WAPE" in r for r in res_a["reasons"]))

        # Scenario B: Bias exceeds 10%
        metrics_high_bias = {
            "test_ridge": {"WAPE_pct": 15.0, "Bias_pct": 14.5},
            "test_moving_median": {"WAPE_pct": 20.0},
            "test_seasonal_naive": {"WAPE_pct": 22.0}
        }
        res_b = evaluate_gate(metrics_high_bias, self.thresholds)
        self.assertEqual(res_b["verdict"], "FAIL")
        self.assertTrue(any("bias" in r for r in res_b["reasons"]))

        # Scenario C: Worse than best baseline by > 1.0 pt
        metrics_worse_gap = {
            "test_ridge": {"WAPE_pct": 12.0, "Bias_pct": 2.0},
            "test_moving_median": {"WAPE_pct": 8.0},  # gap = 12.0 - 8.0 = 4.0 pts > 1.0 limit
            "test_seasonal_naive": {"WAPE_pct": 10.0}
        }
        res_c = evaluate_gate(metrics_worse_gap, self.thresholds)
        self.assertEqual(res_c["verdict"], "FAIL")
        self.assertTrue(any("worse than best baseline" in r for r in res_c["reasons"]))

    def test_02_worse_candidate_rejected_champion_preserved(self):
        """When an approved champion exists, a failing candidate must NOT replace it."""
        series_id = "TEST_SERIES_001"

        # 1. Register good champion
        good_candidate = [{
            "_id": series_id,
            "product_id": "TEST-001",
            "region_id": "KOL-LOC-001",
            "model_type": "ridge",
            "status": "APPROVED",
            "version": "v1_champion",
            "artifact_file": "ridge/test.joblib",
            "artifact_sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "registered_at_utc": "2026-11-01T00:00:00Z",
            "gate": {"verdict": "PASS", "ridge_wape_pct": 5.0}
        }]
        c1 = register(self.db, self.test_col, good_candidate)
        self.assertEqual(c1["approved_new"], 1)

        # Verify champion is saved
        doc1 = self.db[self.test_col].find_one({"_id": series_id})
        self.assertEqual(doc1["status"], "APPROVED")
        self.assertEqual(doc1["version"], "v1_champion")

        # 2. Try to register a worse failing candidate
        bad_candidate = [{
            "_id": series_id,
            "product_id": "TEST-001",
            "region_id": "KOL-LOC-001",
            "model_type": "ridge",
            "status": "NOT_APPROVED",  # Failed gate
            "version": "v2_bad_candidate",
            "artifact_file": "ridge/test_v2.joblib",
            "artifact_sha256": "9999991234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            "registered_at_utc": "2026-11-16T00:00:00Z",
            "gate": {"verdict": "FAIL", "reasons": ["WAPE 40.0% > 35%"]}
        }]
        c2 = register(self.db, self.test_col, bad_candidate)
        self.assertEqual(c2["kept_previous_champion"], 1, "Failed candidate should trigger kept_previous_champion!")

        # 3. CRITICAL ASSERTION: The champion was NOT replaced!
        doc2 = self.db[self.test_col].find_one({"_id": series_id})
        self.assertEqual(doc2["status"], "APPROVED", "Champion status was erroneously changed!")
        self.assertEqual(doc2["version"], "v1_champion", "Champion was erroneously overwritten by bad candidate!")
        self.assertIn("rejected_candidate", doc2, "Champion record should record the rejected candidate details!")
        self.assertEqual(doc2["rejected_candidate"]["version"], "v2_bad_candidate")


if __name__ == "__main__":
    unittest.main()
