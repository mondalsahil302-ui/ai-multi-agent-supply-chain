"""Single Demand Coordinator Agent (Section 5).

The Coordinator Agent is the single entry point and owner of the entire forecasting lifecycle:
  1. Data readiness verification (mandatory invariant before forecasting)
  2. Weekly batch or single-product forecast orchestration
  3. Multi-tier recovery execution
  4. Mathematical SHAP and LLM/template explanation generation
  5. Audit history retrieval and data diagnostics summary
"""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import os
from typing import Any, Dict, List, Optional
import pandas as pd
from pymongo.database import Database

from demand_agent.config import Settings, get_settings
from demand_agent.db import get_db
from demand_agent.explanation.explainer import (
    compute_linear_shap,
    explain_forecast,
    extract_top_drivers,
    generate_template_explanation,
)
from demand_agent.forecast.engine import (
    BatchForecastResult,
    ReadinessGateBlockedError,
    WeeklyBatchForecastEngine,
)
from demand_agent.forecast.week_resolver import resolve_target_week
from demand_agent.readiness.gate import ReadinessReport, check_data_readiness
from demand_agent.warehouse import resolve_warehouse_and_region

log = logging.getLogger(__name__)


class DemandCoordinatorAgent:
    """Production coordinator agent owning the complete demand forecasting lifecycle."""

    def __init__(self, db: Optional[Database] = None, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.db = db if db is not None else get_db(self.settings)
        self.engine = WeeklyBatchForecastEngine(self.db, self.settings)

    # ------------------------------------------------------------------
    # Tool 1: Check Data Readiness
    # ------------------------------------------------------------------
    def check_data_readiness(
        self, warehouse_id: Optional[str] = None, region_id: Optional[str] = None, target_week: Optional[str] = None
    ) -> Dict[str, Any]:
        """Evaluates all 5 mandatory checks for demand region and warehouse data readiness."""
        ident = region_id or warehouse_id or self.settings.region_id
        w_id, r_id, wh_doc = resolve_warehouse_and_region(self.db, ident)
        resolved_region = r_id or ident
        resolved_wh = w_id or "NONE"

        tw_doc = None
        if target_week:
            tw_doc = self.db[self.settings.collections["calendar_weeks"]].find_one({"week_id": target_week})
            if not tw_doc:
                return {
                    "ready": False,
                    "warehouse_id": resolved_wh,
                    "region_id": resolved_region,
                    "target_week_id": target_week,
                    "issues": [{
                        "dataset": "calendar_weeks",
                        "entity": target_week,
                        "reason": "week_not_found",
                        "detail": f"Target week '{target_week}' does not exist in calendar_weeks collection."
                    }],
                    "human_readable": f"Target week '{target_week}' was not found in calendar_weeks.",
                    "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                }

        report = check_data_readiness(
            self.db, self.settings, warehouse_id=resolved_wh, region_id=resolved_region, target_week=tw_doc, persist_report=True
        )
        return report.to_dict()

    # ------------------------------------------------------------------
    # Tool 2: Run Forecast (Invariant: Always Checks Readiness First)
    # ------------------------------------------------------------------
    def run_forecast(
        self,
        warehouse_id: Optional[str] = None,
        region_id: Optional[str] = None,
        target_week: Optional[str] = None,
        product_id: Optional[str] = None,
        force_rung: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Runs the forecasting workflow based on demand region.

        Invariant: NEVER runs without checking data readiness first.
        If data is not ready, halts immediately and returns an explicit refusal report.
        """
        ident = region_id or warehouse_id or self.settings.region_id
        w_id, r_id, _ = resolve_warehouse_and_region(self.db, ident)
        resolved_region = r_id or ident
        resolved_wh = w_id or "WH-001"

        try:
            result: BatchForecastResult = self.engine.run_batch_forecast(
                warehouse_id=resolved_wh,
                region_id=resolved_region,
                product_id=product_id,
                target_week_id=target_week,
                check_readiness_first=True,
                force_rung=force_rung,
            )
            return {
                "status": result.status,
                "run_id": result.run_id,
                "warehouse_id": result.warehouse_id,
                "region_id": result.region_id,
                "target_week": result.target_week_id,
                "target_week_start": result.target_week_start,
                "target_week_end": result.target_week_end,
                "total_tasks": result.total_tasks,
                "succeeded_tasks": result.succeeded_tasks,
                "failed_tasks": result.failed_tasks,
                "counts_by_method": result.counts_by_method,
                "duration_seconds": result.duration_seconds,
                "tasks": [asdict(t) for t in result.tasks],
                "failed_task_summary": result.failed_task_summary,
            }
        except ReadinessGateBlockedError as gate_err:
            log.warning("Forecast blocked by Readiness Gate: %s", gate_err)
            return {
                "status": "REFUSED_NOT_READY",
                "error": "DATA_READINESS_GATE_BLOCKED",
                "message": str(gate_err),
                "readiness_report": gate_err.report.to_dict(),
            }
        except Exception as e:
            log.error("Fatal forecast workflow exception: %s", e)
            return {
                "status": "FAILED",
                "error": type(e).__name__,
                "message": str(e),
            }

    # ------------------------------------------------------------------
    # Tool 3: Get Explanation
    # ------------------------------------------------------------------
    def get_explanation(
        self,
        product_id: str,
        target_week: Optional[str] = None,
        warehouse_id: str = "WH-001",
    ) -> Dict[str, Any]:
        """Computes mathematical SHAP feature drivers and returns explanation."""
        w_id, r_id, _ = resolve_warehouse_and_region(self.db, warehouse_id)
        col_res = self.db[self.settings.collections["forecast_results"]]

        query: Dict[str, Any] = {"region_id": r_id, "product_id": product_id}
        if target_week:
            query["target_week"] = target_week

        doc = col_res.find_one(query, sort=[("forecast_generation_timestamp", -1)])
        if not doc:
            # If not yet generated, attempt to generate on the fly
            tw_res = target_week or "W151"
            forecast_out = self.run_forecast(warehouse_id=warehouse_id, target_week=tw_res, product_id=product_id)
            if forecast_out.get("status") != "SUCCESS":
                return {
                    "status": "error",
                    "explanation_text": f"Could not generate forecast for {product_id}: {forecast_out.get('message')}",
                    "top_drivers": [],
                    "method": "none",
                }
            doc = col_res.find_one({"region_id": r_id, "product_id": product_id, "target_week": tw_res},
                                   sort=[("forecast_generation_timestamp", -1)])

        if not doc or doc.get("status") != "SUCCESS":
            return {
                "status": "error",
                "explanation_text": f"No successful forecast available for {product_id} in {target_week}.",
                "top_drivers": [],
                "method": "none",
            }

        method = doc.get("method", "champion")
        pid = doc["product_id"]
        pname = doc.get("product_name", pid)
        tw = doc.get("target_week", "Target Week")
        point_fc = float(doc.get("point_forecast", 0.0))

        top_drivers = []
        if method == "champion":
            try:
                ridge_art = self.engine._get_ridge_model(pid)
                if ridge_art:
                    # Run single task to get fresh feature row
                    task_res = self.engine.run_batch_forecast(
                        warehouse_id=warehouse_id, product_id=pid, target_week_id=tw, check_readiness_first=False
                    )
                    if task_res.tasks and task_res.tasks[0].feature_row:
                        feat_df = pd.DataFrame([task_res.tasks[0].feature_row])
                        shap_dict, _, _ = compute_linear_shap(ridge_art["model"], feat_df)
                        top_drivers = extract_top_drivers(shap_dict, feat_df, top_n=5)
            except Exception as e:
                log.warning("Linear SHAP computation error for %s: %s", pid, e)

        return explain_forecast(
            product_id=pid,
            product_name=pname,
            target_week=tw,
            point_forecast=point_fc,
            method=method,
            top_drivers=top_drivers,
        )

    # ------------------------------------------------------------------
    # Tool 4: Get Run Status
    # ------------------------------------------------------------------
    def get_run_status(self, run_id: str) -> Dict[str, Any]:
        """Retrieves execution summary and task counts for a forecast run."""
        col_meta = self.db[self.settings.collections["run_metadata"]]
        meta = col_meta.find_one({"run_id": run_id}, {"_id": 0})
        if not meta:
            return {"found": False, "run_id": run_id, "error": "Run not found"}

        col_res = self.db[self.settings.collections["forecast_results"]]
        sample_tasks = list(
            col_res.find({"run_id": run_id}, {"_id": 0, "feature_row": 0})
            .sort("product_id", 1)
            .limit(10)
        )
        return {
            "found": True,
            "metadata": meta,
            "sample_tasks": sample_tasks,
        }

    # ------------------------------------------------------------------
    # Tool 5: Get Data Summary
    # ------------------------------------------------------------------
    def get_data_summary(self, warehouse_id: str = "WH-001") -> Dict[str, Any]:
        """Returns comprehensive diagnostic and operational summary of the system."""
        w_id, r_id, wh_doc = resolve_warehouse_and_region(self.db, warehouse_id)
        c = self.settings.collections

        # Calendar weeks
        col_cal = self.db[c["calendar_weeks"]]
        last_done = col_cal.find_one({"week_status": "COMPLETED"}, sort=[("week_start_date", -1)], projection={"_id": 0})
        next_target, _ = resolve_target_week(self.db, self.settings)

        # Historical demand
        col_hist = self.db[c["historical_demand"]]
        hist_count = col_hist.count_documents({"region_id": r_id})
        hist_products = len(col_hist.distinct("product_id", {"region_id": r_id}))

        # Weather forecasts
        col_wf = self.db[c["weather_forecasts"]]
        wf_dates = sorted(col_wf.distinct("forecast_date", {"region_id": r_id}))
        wf_count = len(wf_dates)
        wf_range = f"{wf_dates[0]} -> {wf_dates[-1]}" if wf_dates else "None"

        # Model Registry
        col_reg = self.db["model_registry"]
        reg_total = col_reg.count_documents({"region_id": r_id})
        reg_approved = col_reg.count_documents({"region_id": r_id, "status": "APPROVED"})
        reg_standby = reg_total - reg_approved

        # Quarantine & Ingestion Errors
        q_count = self.db["quarantine_data"].count_documents({})
        err_count = self.db["ingestion_errors"].count_documents({})

        return {
            "warehouse": wh_doc,
            "region_id": r_id,
            "last_completed_week": last_done,
            "next_target_week": {"week_id": next_target["week_id"], "week_start_date": next_target["week_start_date"], "week_end_date": next_target["week_end_date"]},
            "historical_demand": {
                "records": hist_count,
                "products": hist_products,
            },
            "weather_forecasts": {
                "days_available": wf_count,
                "date_range": wf_range,
            },
            "model_registry": {
                "total_registered": reg_total,
                "approved_champions": reg_approved,
                "standby_fallback": reg_standby,
            },
            "quarantine_and_errors": {
                "quarantined_records": q_count,
                "ingestion_errors": err_count,
            },
        }
