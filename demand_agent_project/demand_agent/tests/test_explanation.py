"""Unit tests for Layer 7: Non-Blocking Explanation Layer."""
import os
import unittest
import joblib
import pandas as pd
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.explanation.explainer import (
    compute_linear_shap,
    extract_top_drivers,
    explain_forecast,
    generate_template_explanation,
)
from demand_agent.forecast.engine import WeeklyBatchForecastEngine


class TestExplanationLayer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.db = get_db(cls.settings)
        cls.engine = WeeklyBatchForecastEngine(cls.db, cls.settings)

    def test_01_exact_linear_shap_additivity(self):
        """Verifies exact linear SHAP formula: sum(phi_i) + intercept == predicted_log."""
        # Run single forecast to get feature row
        res = self.engine.run_batch_forecast(
            warehouse_id="WH-001",
            product_id="ICE-001",
            target_week_id="W151",
            check_readiness_first=False,
        )
        task = res.tasks[0]
        self.assertEqual(task.method, "champion")
        feat_df = pd.DataFrame([task.feature_row])

        ridge_art = joblib.load("artifacts/models/ridge/ICE-001.joblib")
        pipe = ridge_art["model"]

        shap_dict, intercept, pred_shap = compute_linear_shap(pipe, feat_df)
        pred_pipe = float(pipe.predict(feat_df)[0])

        self.assertAlmostEqual(pred_shap, pred_pipe, places=6)
        self.assertEqual(len(shap_dict), 34)

    def test_02_top_drivers_extraction(self):
        """Top drivers must be ranked by absolute SHAP magnitude descending."""
        res = self.engine.run_batch_forecast(
            warehouse_id="WH-001",
            product_id="ICE-001",
            target_week_id="W151",
            check_readiness_first=False,
        )
        feat_df = pd.DataFrame([res.tasks[0].feature_row])
        pipe = joblib.load("artifacts/models/ridge/ICE-001.joblib")["model"]
        shap_dict, _, _ = compute_linear_shap(pipe, feat_df)

        drivers = extract_top_drivers(shap_dict, feat_df, top_n=5)
        self.assertEqual(len(drivers), 5)
        magnitudes = [d["impact_magnitude"] for d in drivers]
        self.assertEqual(magnitudes, sorted(magnitudes, reverse=True))
        for d in drivers:
            self.assertIn(d["impact"], ("positive", "negative"))
            self.assertIn("description", d)

    def test_03_non_blocking_template_fallback_on_llm_failure(self):
        """If LLM call fails or times out, system falls back to template and never halts."""
        # Unset GEMINI_API_KEY to force fallback
        old_key = os.environ.pop("GEMINI_API_KEY", None)
        try:
            drivers = [
                {"feature": "festival_proximity", "description": "Festival Proximity", "shap_value": 0.35, "feature_value": 1.0, "impact": "positive", "impact_magnitude": 0.35},
                {"feature": "trend_scaled", "description": "Long-term secular sales trend", "shap_value": -0.12, "feature_value": 1.5, "impact": "negative", "impact_magnitude": 0.12},
            ]
            exp = explain_forecast(
                product_id="ICE-001",
                product_name="Amul Vanilla Ice Cream",
                target_week="W151",
                point_forecast=72.5,
                method="champion",
                top_drivers=drivers,
                timeout_sec=0.5,
            )
            self.assertEqual(exp["status"], "template")
            self.assertIn("Festival Proximity", exp["explanation_text"])
            self.assertIn("72.5 units", exp["explanation_text"])
        finally:
            if old_key:
                os.environ["GEMINI_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
