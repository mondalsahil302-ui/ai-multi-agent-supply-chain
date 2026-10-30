"""
test_api.py – Comprehensive unit and integration tests for FastAPI Demand Intelligence Agent.
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from demand_agent.api import app
from demand_agent.service import demand_service


@pytest.fixture(scope="session")
def client():
    """Create a TestClient with pre-initialized service."""
    demand_service.initialize()
    with TestClient(app) as test_client:
        yield test_client


# ─── System & Metadata Endpoints ──────────────────────────────────────────────

def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["agent_name"] == "Demand Intelligence Agent"
    assert data["total_regions"] == 40
    assert "CatBoost" in data["active_model"]
    assert data["calibrated_uncertainty_available"] is False


def test_regions_endpoint(client):
    response = client.get("/api/v1/regions")
    assert response.status_code == 200
    data = response.json()
    assert data["total_regions"] == 40
    regions = data["regions"]
    assert len(regions) == 40
    assert any(r["region_name"] == "Lake Gardens" for r in regions)
    assert any(r["location_id"] == "KOL-LOC-001" for r in regions)


def test_metrics_endpoint(client):
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert len(data["metrics"]) >= 4  # Naive, MA4, LGB, CB
    assert data["ranking_k_used"] == 5
    assert data["ranking_k_requested"] == 10
    assert "limitation_notice" in data
    assert "5 products" in data["limitation_notice"]


# ─── Forecasting Endpoints ────────────────────────────────────────────────────

def test_forecast_all_regions_post(client):
    """Test forecasting for all 40 regions."""
    payload = {
        "target_week_start": "2026-08-24",
        "top_k": 10,
        "include_drivers": True,
        "model_name": "catboost",
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "success"
    assert data["target_week_start"] == "2026-08-24"
    assert data["total_regions_processed"] == 40
    assert len(data["regions"]) == 40

    # Inspect first region
    first_region = data["regions"][0]
    assert "location_id" in first_region
    assert "region_name" in first_region
    assert "top_products" in first_region
    assert first_region["returned_count"] > 0
    assert first_region["returned_count"] <= 10


def test_forecast_single_region_by_name(client):
    """Test forecasting filtered to a specific region name."""
    payload = {
        "target_week_start": "2026-08-24",
        "region": "Lake Gardens",
        "top_k": 5,
        "include_drivers": True,
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["total_regions_processed"] == 1
    region_data = data["regions"][0]
    assert region_data["region_name"] == "Lake Gardens"
    assert region_data["location_id"] == "KOL-LOC-001"
    assert 1 <= len(region_data["top_products"]) <= 5
    assert region_data["returned_count"] == len(region_data["top_products"])


def test_forecast_single_region_by_location_id(client):
    """Test forecasting filtered by location ID."""
    payload = {
        "target_week_start": "2026-08-24",
        "region": "KOL-LOC-002",
        "top_k": 5,
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["total_regions_processed"] == 1
    region_data = data["regions"][0]
    assert region_data["location_id"] == "KOL-LOC-002"


def test_product_ranking_order(client):
    """Verify products are strictly sorted descending by predicted units."""
    payload = {
        "target_week_start": "2026-08-24",
        "region": "Lake Gardens",
        "top_k": 10,
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()

    products = data["regions"][0]["top_products"]
    pred_units = [p["predicted_demand_units"] for p in products]
    ranks = [p["demand_rank"] for p in products]

    # Verify monotonic ordering
    assert pred_units == sorted(pred_units, reverse=True), "Demand units not sorted descending"
    assert ranks == list(range(1, len(products) + 1)), "Ranks must be 1, 2, 3..."


def test_uncertainty_is_omitted_uncalibrated(client):
    """
    Requirement 8: Return forecast uncertainty only if a calibrated uncertainty model exists.
    Must be null/omitted.
    """
    payload = {
        "target_week_start": "2026-08-24",
        "region": "Lake Gardens",
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()

    products = data["regions"][0]["top_products"]
    for p in products:
        assert p["uncertainty"] is None, "Uncertainty must be null since no calibrated model exists"

    gov = data["governance_metadata"]
    assert gov["calibrated_uncertainty_model_exists"] is False
    assert "omitted" in gov["uncertainty_policy"].lower()


def test_shap_demand_drivers_included(client):
    """
    Requirement 9: Return demand drivers using SHAP where supported.
    """
    payload = {
        "target_week_start": "2026-08-24",
        "region": "Lake Gardens",
        "include_drivers": True,
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()

    products = data["regions"][0]["top_products"]
    for p in products:
        assert p["demand_drivers"] is not None
        assert len(p["demand_drivers"]) > 0
        driver = p["demand_drivers"][0]
        assert "feature_name" in driver
        assert "shap_value" in driver
        assert driver["impact_direction"] in ("positive", "negative")
        assert "description" in driver


def test_lightgbm_model_option(client):
    """Test forecasting with LightGBM model option."""
    payload = {
        "target_week_start": "2026-08-24",
        "region": "Lake Gardens",
        "model_name": "lightgbm",
        "include_drivers": False,
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "LightGBM" in data["model_name"]
    assert len(data["regions"]) == 1


def test_forecast_get_endpoint(client):
    """Test convenience GET endpoint."""
    response = client.get(
        "/api/v1/forecast?target_week_start=2026-08-24&region=Lake%20Gardens&top_k=5"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_regions_processed"] == 1
    assert data["regions"][0]["region_name"] == "Lake Gardens"


# ─── Error Handling & Validation Tests ────────────────────────────────────────

def test_invalid_region_returns_400(client):
    payload = {
        "target_week_start": "2026-08-24",
        "region": "NonExistentRegionXYZ",
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 400
    assert "Unknown region" in response.json()["detail"]


def test_invalid_date_format_returns_422(client):
    payload = {
        "target_week_start": "24-08-2026",  # invalid format
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 422


def test_date_too_early_returns_400(client):
    payload = {
        "target_week_start": "2023-01-01",  # earlier than dataset start
    }
    response = client.post("/api/v1/forecast", json=payload)
    assert response.status_code == 400
    assert "No historical data available" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
