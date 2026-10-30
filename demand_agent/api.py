"""
api.py – Standalone FastAPI Demand Intelligence Agent.

Exposes RESTful endpoints for demand prediction, top-10 regional product rankings,
SHAP feature drivers, and model evaluation metrics.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from demand_agent.config import RANK_K_AVAILABLE
from demand_agent.schemas import (
    ForecastRequest,
    ForecastResponse,
    EvaluationMetricsResponse,
    HealthResponse,
)
from demand_agent.service import demand_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload models, metadata, and feature scaffold at application startup."""
    logger.info("Starting up Demand Intelligence Agent API...")
    try:
        demand_service.initialize()
        logger.info("Demand Intelligence Agent successfully initialized.")
    except Exception as e:
        logger.error("Failed to initialize Demand Intelligence Agent: %s", e)
        raise e
    yield
    logger.info("Shutting down Demand Intelligence Agent API...")


app = FastAPI(
    title="Demand Intelligence Agent API",
    description=(
        "Standalone AI Agent for Kolkata regional FMCG demand forecasting and product ranking. "
        "Provides next-week product unit demand predictions, top-10 regional product rankings, "
        "SHAP-based demand drivers, and offline walk-forward evaluation metrics."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for cross-agent coordinator communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Agent Health and Status Check",
)
def get_health() -> HealthResponse:
    """Return agent health, loaded model type, and data coverage status."""
    return HealthResponse(
        status="healthy" if demand_service.is_initialized else "initializing",
        agent_name="Demand Intelligence Agent",
        version="1.0.0",
        active_model="CatBoost Regressor (Best Validated)",
        models_available=["catboost", "lightgbm"],
        dataset_date_range={
            "min_date": demand_service.min_date.date().isoformat() if demand_service.min_date else "N/A",
            "max_date": demand_service.max_date.date().isoformat() if demand_service.max_date else "N/A",
        },
        total_regions=len(demand_service.location_id_to_name),
        total_products=len(demand_service.df_feat["product_id"].unique()) if demand_service.df_feat is not None else 0,
        calibrated_uncertainty_available=False,
    )


@app.get(
    "/api/v1/metrics",
    response_model=EvaluationMetricsResponse,
    tags=["Evaluation"],
    summary="Get Model Evaluation Metrics",
)
def get_metrics() -> EvaluationMetricsResponse:
    """
    Retrieve offline chronological walk-forward evaluation metrics.
    Includes MAE, RMSE, R2, WAPE, Forecast Bias, Precision@5, NDCG@5, and Demand Capture@5.
    Also documents the ranking scope limitation.
    """
    try:
        return demand_service.get_evaluation_metrics()
    except Exception as e:
        logger.error("Error retrieving metrics: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load evaluation metrics: {str(e)}"
        )


@app.get(
    "/api/v1/regions",
    tags=["Metadata"],
    summary="List Supported Kolkata Regions",
)
def list_regions():
    """List all 40 supported Kolkata regions with location codes and names."""
    try:
        return {
            "total_regions": len(demand_service.location_id_to_name),
            "regions": demand_service.get_supported_regions(),
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@app.post(
    "/api/v1/forecast",
    response_model=ForecastResponse,
    tags=["Forecasting"],
    summary="Generate Demand Forecast and Regional Rankings (POST)",
)
def create_forecast(request: ForecastRequest) -> ForecastResponse:
    """
    Forecast next-week demand in units and rank products for each region.

    - **target_week_start**: Target week start date (ISO YYYY-MM-DD, e.g. '2026-08-24').
    - **region**: Optional filter by region name ('Lake Gardens') or location ID ('KOL-LOC-001').
    - **top_k**: Number of highest-demand products to return per region (default 10).
    - **include_drivers**: Include SHAP feature attributions explaining the forecast.
    - **model_name**: Model selector ('catboost' default, or 'lightgbm').

    Returns standardized JSON payload consumable by Inventory Intelligence Agent and Decision Coordinator.
    """
    try:
        return demand_service.predict_demand(
            target_week_start=request.target_week_start,
            region=request.region,
            top_k=request.top_k,
            include_drivers=request.include_drivers,
            model_name=request.model_name,
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error("Forecast execution error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Demand forecasting failed: {str(e)}"
        )


@app.get(
    "/api/v1/forecast",
    response_model=ForecastResponse,
    tags=["Forecasting"],
    summary="Generate Demand Forecast and Regional Rankings (GET)",
)
def get_forecast(
    target_week_start: str = Query(
        ...,
        description="Target week start date (YYYY-MM-DD, e.g. 2026-08-24)",
        examples=["2026-08-24"],
    ),
    region: Optional[str] = Query(
        None,
        description="Optional region name (e.g. 'Lake Gardens') or location_id (e.g. 'KOL-LOC-001')",
    ),
    top_k: int = Query(
        10,
        ge=1,
        le=50,
        description="Top-K products to return per region",
    ),
    include_drivers: bool = Query(
        True,
        description="Include SHAP demand drivers",
    ),
    model_name: str = Query(
        "catboost",
        description="Model selector ('catboost' or 'lightgbm')",
    ),
) -> ForecastResponse:
    """Convenience GET endpoint mirroring the POST forecast route."""
    req = ForecastRequest(
        target_week_start=target_week_start,
        region=region,
        top_k=top_k,
        include_drivers=include_drivers,
        model_name=model_name,
    )
    return create_forecast(req)

