"""Comprehensive tests for product image resolver and Demand AI chat engine."""
import unittest
from demand_agent.products.images import get_product_image_url, PRODUCT_IMAGES, CATEGORY_IMAGES, DEFAULT_IMAGE
from demand_agent.agent.chat import DemandAIChatEngine


class TestImagesAndChat(unittest.TestCase):
    def test_direct_sku_mapping(self):
        url = get_product_image_url("ICE-001")
        self.assertIn("images.unsplash.com", url)
        self.assertEqual(url, PRODUCT_IMAGES["ICE-001"])

    def test_name_keyword_resolution(self):
        url = get_product_image_url("CUSTOM-999", product_name="Lay's Classic Salted Chips")
        self.assertIn("images.unsplash.com", url)
        self.assertEqual(url, CATEGORY_IMAGES["SNK"])

    def test_category_fallback(self):
        url = get_product_image_url("ICE-999", category_code="ICE")
        self.assertEqual(url, CATEGORY_IMAGES["ICE"])

    def test_unknown_sku_fallback(self):
        url = get_product_image_url("XYZ-999")
        self.assertEqual(url, DEFAULT_IMAGE)

    def test_normal_conversation_greeting(self):
        engine = DemandAIChatEngine()
        resp = engine._rule_based_analyst_response(
            "Hello! How are you doing today?",
            {
                "region_id": "KOL-LOC-001",
                "product_id": "ICE-001",
                "product_name": "Amul Vanilla Ice Cream",
                "target_week": "2026-11-15 to 2026-11-21",
                "forecast": {"point_forecast": 72.0, "p10": 64.0, "p50": 72.0, "p90": 85.0},
                "last_week_actual": 68.0,
                "avg_4w_actual": 70.0,
                "historical_count": 150,
                "stockouts_recorded": 2,
                "top_drivers": [],
            }
        )
        self.assertIn("Hello!", resp)
        self.assertIn("Amul Vanilla Ice Cream", resp)

    def test_complex_scenario_temperature(self):
        engine = DemandAIChatEngine()
        resp = engine._rule_based_analyst_response(
            "What happens if temperature increases by 4 degrees?",
            {
                "region_id": "KOL-LOC-001",
                "product_id": "ICE-001",
                "product_name": "Amul Vanilla Ice Cream",
                "target_week": "2026-11-15 to 2026-11-21",
                "forecast": {"point_forecast": 72.0, "p10": 64.0, "p50": 72.0, "p90": 85.0},
                "last_week_actual": 68.0,
                "avg_4w_actual": 70.0,
                "historical_count": 150,
                "stockouts_recorded": 2,
                "top_drivers": [],
            }
        )
        self.assertIn("Weather Scenario", resp)
        self.assertIn("Temperature Shift", resp)

    def test_complex_scenario_festival(self):
        engine = DemandAIChatEngine()
        resp = engine._rule_based_analyst_response(
            "What if we have Durga Puja rush?",
            {
                "region_id": "KOL-LOC-001",
                "product_id": "CHO-001",
                "product_name": "Cadbury Dairy Milk",
                "target_week": "2026-11-15 to 2026-11-21",
                "forecast": {"point_forecast": 120.0, "p10": 105.0, "p50": 120.0, "p90": 145.0},
                "last_week_actual": 110.0,
                "avg_4w_actual": 112.0,
                "historical_count": 150,
                "stockouts_recorded": 1,
                "top_drivers": [],
            }
        )
        self.assertIn("Festival Surge", resp)
        self.assertIn("Durga Puja", resp)

    def test_quantile_corridor_explanation(self):
        engine = DemandAIChatEngine()
        resp = engine._rule_based_analyst_response(
            "Explain the P10, P50, and P90 quantile corridor",
            {
                "region_id": "KOL-LOC-001",
                "product_id": "ICE-001",
                "product_name": "Amul Vanilla Ice Cream",
                "target_week": "2026-11-15 to 2026-11-21",
                "forecast": {"point_forecast": 72.0, "p10": 64.0, "p50": 72.0, "p90": 85.0},
                "last_week_actual": 68.0,
                "avg_4w_actual": 70.0,
                "historical_count": 150,
                "stockouts_recorded": 2,
                "top_drivers": [],
            }
        )
        self.assertIn("Quantile Corridor", resp)
        self.assertIn("P10", resp)
        self.assertIn("P90", resp)


if __name__ == "__main__":
    unittest.main()
