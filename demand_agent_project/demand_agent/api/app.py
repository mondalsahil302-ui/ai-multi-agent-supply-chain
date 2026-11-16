"""FastAPI Service for Demand Forecasting Agent (Section 5).

Provides REST endpoints for:
  - Triggering weekly batch and single-product forecasts
  - Checking data readiness gate diagnostics
  - Retrieving forecast runs and queryable forecast results
  - Generating mathematical SHAP explanations
  - Monitoring database and service health
"""
from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from demand_agent.agent.coordinator import DemandCoordinatorAgent
from demand_agent.config import get_settings
from demand_agent.db import get_db

log = logging.getLogger(__name__)

# Authentication Configuration
API_KEY_ENV = os.environ.get("DEMAND_AGENT_API_KEY", "demand-agent-secret-key-2026")

app = FastAPI(
    title="Demand Forecasting Agent API",
    version="1.0.0",
    description="Production REST API for retail SKU x Region weekly demand forecasting in Kolkata.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Coordinator Instance
_settings = get_settings()
_db = get_db(_settings)
coordinator = DemandCoordinatorAgent(db=_db, settings=_settings)


# ------------------------------------------------------------------
# Security Dependency
# ------------------------------------------------------------------
def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Authenticates caller via X-API-Key header or Authorization: Bearer token."""
    token = x_api_key
    if not token and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]

    expected = os.environ.get("DEMAND_AGENT_API_KEY", API_KEY_ENV)
    if not token or token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


# ------------------------------------------------------------------
# Request / Response Schemas
# ------------------------------------------------------------------
class ForecastRunRequest(BaseModel):
    region_id: Optional[str] = Field(default=None, description="Demand Region ID (e.g. KOL-LOC-001)")
    warehouse_id: Optional[str] = Field(default=None, description="Optional Fulfillment Warehouse ID (e.g. WH-001)")
    product_id: Optional[str] = Field(default=None, description="Optional single SKU ID (e.g. ICE-001)")
    target_week: Optional[str] = Field(default=None, description="Optional target week ID (e.g. W151)")


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------
@app.get("/health", tags=["System"])
def health_check():
    """Unauthenticated health check."""
    try:
        _db.command("ping")
        db_status = "connected"
    except Exception as e:
        db_status = f"unhealthy: {e}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "database": db_status,
        "region_id": _settings.region_id,
    }


@app.get("/readiness/check", tags=["Readiness Gate"], dependencies=[Depends(verify_api_key)])
def check_readiness(
    region_id: Optional[str] = Query(None, description="Demand Region ID (e.g. KOL-LOC-001)"),
    warehouse_id: Optional[str] = Query(None, description="Warehouse ID"),
    target_week: Optional[str] = Query(None, description="Target week ID (e.g. W151)"),
):
    """Evaluates all 5 mandatory data readiness checks for the demand region."""
    report = coordinator.check_data_readiness(warehouse_id=warehouse_id, region_id=region_id, target_week=target_week)
    if not report.get("ready"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=report,
        )
    return report


@app.post("/forecast/run", tags=["Forecasting"], dependencies=[Depends(verify_api_key)])
def run_forecast_endpoint(req: ForecastRunRequest):
    """Triggers batch or single-product forecasting for the target region."""
    res = coordinator.run_forecast(
        warehouse_id=req.warehouse_id,
        region_id=req.region_id,
        target_week=req.target_week,
        product_id=req.product_id,
    )
    if res.get("status") == "REFUSED_NOT_READY":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=res,
        )
    if res.get("status") == "FAILED":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=res,
        )
    return res


@app.get("/forecast/status/{run_id}", tags=["Forecasting"], dependencies=[Depends(verify_api_key)])
def get_run_status_endpoint(run_id: str):
    """Retrieves status and metadata for a specific forecast run."""
    res = coordinator.get_run_status(run_id)
    if not res.get("found"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run '{run_id}' not found.")
    return res


@app.get("/forecast/results", tags=["Forecasting"], dependencies=[Depends(verify_api_key)])
def query_forecast_results(
    region_id: Optional[str] = Query(None, description="Demand Region ID"),
    warehouse_id: Optional[str] = Query(None, description="Warehouse ID"),
    product_id: Optional[str] = Query(None),
    target_week: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
):
    """Queries forecast records from persistent store."""
    query: Dict[str, Any] = {}
    if region_id:
        query["region_id"] = region_id
    if warehouse_id:
        query["warehouse_id"] = warehouse_id
    if product_id:
        query["product_id"] = product_id
    if target_week:
        query["target_week"] = target_week
    if status_filter:
        query["status"] = status_filter

    col = _db[_settings.collections["forecast_results"]]
    docs = list(
        col.find(query, {"_id": 0})
        .sort("forecast_generation_timestamp", -1)
        .limit(limit)
    )
    return {"count": len(docs), "results": docs}


@app.get("/explain/{product_id}", tags=["Explanations"], dependencies=[Depends(verify_api_key)])
def get_product_explanation(
    product_id: str,
    warehouse_id: str = Query("WH-001"),
    target_week: Optional[str] = Query(None),
):
    """Generates mathematical SHAP top drivers and plain-English explanation."""
    res = coordinator.get_explanation(
        product_id=product_id,
        target_week=target_week,
        warehouse_id=warehouse_id,
    )
    return res


@app.get("/data/summary", tags=["Diagnostics"], dependencies=[Depends(verify_api_key)])
def get_data_summary_endpoint(warehouse_id: str = Query("WH-001")):
    """Returns high-level operational and readiness summary for the dashboard."""
    return coordinator.get_data_summary(warehouse_id=warehouse_id)
