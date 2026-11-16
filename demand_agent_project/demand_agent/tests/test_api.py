"""Integration and API unit tests for FastAPI Service and Coordinator Agent (Section 5)."""
import os
import unittest
from fastapi.testclient import TestClient

from demand_agent.api.app import app, API_KEY_ENV


class TestFastAPIEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.auth_headers = {"X-API-Key": API_KEY_ENV}

    def test_01_health_check_unauthenticated(self):
        """Health check endpoint must be publicly accessible and report healthy."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "connected")

    def test_02_auth_protection_on_secured_endpoints(self):
        """Accessing secured endpoints without API key must return 401 Unauthorized."""
        res = self.client.get("/readiness/check")
        self.assertEqual(res.status_code, 401)

        res_post = self.client.post("/forecast/run", json={"warehouse_id": "WH-001"})
        self.assertEqual(res_post.status_code, 401)

    def test_03_readiness_check_endpoint(self):
        """Readiness check returns 200 for ready warehouse WH-001 and 409 for unpopulated WH-002."""
        # Operational WH-001
        res = self.client.get("/readiness/check?warehouse_id=WH-001&target_week=W151", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ready"])

        # Unpopulated WH-002
        res_fail = self.client.get("/readiness/check?warehouse_id=WH-002&target_week=W151", headers=self.auth_headers)
        self.assertEqual(res_fail.status_code, 409)
        self.assertFalse(res_fail.json()["detail"]["ready"])

    def test_04_run_forecast_and_status(self):
        """Triggers single product forecast, verifies 200 response and status retrieval."""
        res = self.client.post(
            "/forecast/run",
            json={"warehouse_id": "WH-001", "product_id": "ICE-001", "target_week": "W151"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "SUCCESS")
        run_id = data["run_id"]
        self.assertIsNotNone(run_id)

        # Retrieve status
        res_status = self.client.get(f"/forecast/status/{run_id}", headers=self.auth_headers)
        self.assertEqual(res_status.status_code, 200)
        status_data = res_status.json()
        self.assertTrue(status_data["found"])
        self.assertEqual(status_data["metadata"]["run_id"], run_id)

    def test_05_run_forecast_unpopulated_warehouse_returns_409(self):
        """Attempting to forecast an unpopulated warehouse must return HTTP 409 with gate details."""
        res = self.client.post(
            "/forecast/run",
            json={"warehouse_id": "WH-002", "target_week": "W151"},
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["detail"]["status"], "REFUSED_NOT_READY")

    def test_06_query_forecast_results(self):
        """Queries historical forecast results via filter parameters."""
        res = self.client.get(
            "/forecast/results?warehouse_id=WH-001&target_week=W151&limit=5",
            headers=self.auth_headers,
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(data["count"], 1)

    def test_07_explanation_endpoint(self):
        """Verifies mathematical SHAP explanation endpoint for product."""
        res = self.client.get("/explain/ICE-001?warehouse_id=WH-001&target_week=W151", headers=self.auth_headers)
        self.assertEqual(res.status_code, 200)
        exp = res.json()
        self.assertIn(exp["status"], ("llm", "template"))
        self.assertIsNotNone(exp["explanation_text"])
        self.assertGreater(len(exp["top_drivers"]), 0)


if __name__ == "__main__":
    unittest.main()
