"""
schemas.py – Pydantic models for Demand Intelligence Agent API.

Designed for seamless integration with downstream agents:
  - Inventory Intelligence Agent (consumes predicted units and uncertainty flags)
  - Decision Coordinator (consumes ranked top products, demand drivers, and region totals)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class DemandDriver(BaseModel):
    """A feature driver identified via SHAP with positive or negative demand impact."""
    feature_name: str = Field(..., description="Name of the predictive feature")
    shap_value: float = Field(..., description="SHAP attribution impact on predicted units")
    impact_direction: str = Field(..., description="'positive' (increases demand) or 'negative' (decreases demand)")
    description: str = Field(..., description="Human-readable explanation of the driver")


class UncertaintyEstimate(BaseModel):
    """
    Uncertainty estimate block.
    Per governance requirement: returned ONLY if a calibrated uncertainty model exists.
    """
    calibrated: bool = Field(False, description="Whether the uncertainty bounds are calibrated")
    confidence_level: Optional[float] = Field(None, description="Nominal confidence interval coverage")
    lower_bound: Optional[float] = Field(None, description="Lower prediction bound")
    upper_bound: Optional[float] = Field(None, description="Upper prediction bound")
    status_note: str = Field(
        ...,
        description="Explanation of calibration status (e.g. uncalibrated point forecast)"
    )


class ProductForecastItem(BaseModel):
    """Forecast and ranking for a single product within a region."""
    product_id: str = Field(..., description="Product SKU identifier (e.g. TEA-001)")
    product_name: str = Field(..., description="Standard product name")
    category_name: str = Field(..., description="Product category")
    brand: str = Field(..., description="Manufacturer brand")
    unit_size: str = Field(..., description="Retail package unit size")
    predicted_demand_units: float = Field(..., description="Predicted next-week demand in units")
    demand_rank: int = Field(..., ge=1, description="Rank within region (1 = highest predicted demand)")
    uncertainty: Optional[UncertaintyEstimate] = Field(
        None,
        description="Uncertainty estimates (null if no calibrated uncertainty model exists)"
    )
    demand_drivers: Optional[List[DemandDriver]] = Field(
        None,
        description="Top predictive drivers explaining this forecast (via SHAP)"
    )


class RegionForecast(BaseModel):
    """Grouped demand forecast and rankings for a single Kolkata region."""
    location_id: str = Field(..., description="Location code (e.g. KOL-LOC-001)")
    region_name: str = Field(..., description="Kolkata neighborhood / region name")
    target_week_start: str = Field(..., description="ISO date of target week start (Monday)")
    target_week_end: str = Field(..., description="ISO date of target week end (Sunday)")
    forecast_cutoff_date: str = Field(..., description="Latest observation date available prior to forecast")
    total_predicted_units: float = Field(..., description="Sum of predicted demand across returned top products")
    products_evaluated: int = Field(..., description="Total products evaluated for this region-week")
    returned_count: int = Field(..., description="Number of ranked products returned in top list")
    top_products: List[ProductForecastItem] = Field(..., description="Ranked list of top products")
    assortment_coverage_note: str = Field(
        ...,
        description="Notice regarding available assortment depth (e.g. top-5 anchor dataset)"
    )


class ForecastRequest(BaseModel):
    """Request payload for demand forecasting and top-10 ranking."""
    target_week_start: str = Field(
        ...,
        description="Target forecast week start date in ISO format YYYY-MM-DD (e.g. '2026-08-24')",
        examples=["2026-08-24"]
    )
    region: Optional[str] = Field(
        None,
        description="Optional region filter: region name (e.g. 'Lake Gardens') or location_id (e.g. 'KOL-LOC-001'). If omitted, all 40 regions are processed."
    )
    top_k: int = Field(
        10,
        ge=1,
        le=50,
        description="Number of top highest-demand products to return per region (default: 10)"
    )
    include_drivers: bool = Field(
        True,
        description="Whether to compute and include SHAP demand drivers for top products"
    )
    model_name: Optional[str] = Field(
        "catboost",
        description="Forecasting model to use: 'catboost' (default, best validated) or 'lightgbm'"
    )

    @field_validator("target_week_start")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        import datetime
        try:
            datetime.date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Invalid date format '{v}'. Expected ISO format 'YYYY-MM-DD'.")
        return v


class ForecastResponse(BaseModel):
    """Standardized response schema for Inventory Agent and Decision Coordinator."""
    agent_id: str = Field("Demand_Intelligence_Agent_v1", description="Source agent identity")
    target_week_start: str = Field(..., description="Target forecast week start date")
    target_week_end: str = Field(..., description="Target forecast week end date")
    forecast_cutoff_date: str = Field(..., description="Historical data cutoff date")
    model_name: str = Field(..., description="Forecasting model used (e.g. CatBoost)")
    status: str = Field("success", description="Execution status")
    total_regions_processed: int = Field(..., description="Number of regions in forecast output")
    regions: List[RegionForecast] = Field(..., description="Region-by-region forecast results")
    governance_metadata: Dict[str, Any] = Field(
        ...,
        description="Data provenance, uncertainty calibration status, and ranking scope notice"
    )


class HealthResponse(BaseModel):
    """Healthcheck and agent status."""
    status: str
    agent_name: str
    version: str
    active_model: str
    models_available: List[str]
    dataset_date_range: Dict[str, str]
    total_regions: int
    total_products: int
    calibrated_uncertainty_available: bool


class EvaluationMetricsResponse(BaseModel):
    """Model evaluation metrics from chronological walk-forward testing."""
    metrics: List[Dict[str, Any]]
    ranking_k_requested: int
    ranking_k_available: int
    ranking_k_used: int
    limitation_notice: str

