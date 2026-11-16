"""Weekly Batch Forecast Engine (Layer 5 & Layer 6).

Implements:
  1. Mandatory Data Readiness Gate check before execution.
  2. Next week ID generation / target week resolution.
  3. Minimum 52-week historical lookback retrieval and feature construction.
  4. Multi-tier recovery ladder:
     - Rung 1: Champion Ridge model (from approved model_registry).
     - Rung 2: Standby Global LightGBM model (scale-free pooled model).
     - Rung 3: Rolling moving median / seasonal naive baseline.
     - Rung 4: Controlled failure ("No Safe Forecast Available").
  5. Task isolation: individual task exception or missing data fails only that product,
     allowing remaining tasks to complete normally.
  6. Idempotent persistence to forecast_results and run_metadata.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from pymongo.database import Database

from demand_agent.config import Settings
from demand_agent.features import build_target_features
from demand_agent.forecast.data_fetcher import (
    fetch_festival_context,
    fetch_history,
    fetch_weather_context,
)
from demand_agent.forecast.merger import build_task_frame
from demand_agent.forecast.task_generator import generate_tasks
from demand_agent.forecast.week_resolver import resolve_target_week
from demand_agent.readiness.gate import ReadinessReport, check_data_readiness
from demand_agent.training.lgbm_trainer import category_of
from demand_agent.warehouse import resolve_warehouse_and_region

log = logging.getLogger(__name__)


class ReadinessGateBlockedError(Exception):
    """Raised when Data Readiness Gate refuses forecasting."""
    def __init__(self, report: ReadinessReport):
        super().__init__(f"Data Readiness Gate BLOCKED: {report.human_readable}")
        self.report = report


@dataclass
class ForecastTaskOutput:
    task_id: str
    region_id: str
    warehouse_id: str
    product_id: str
    product_name: str
    category: str
    target_week_id: str
    target_week_start: str
    target_week_end: str
    status: str                         # "SUCCESS" or "FAILED"
    method: str                         # "champion", "fallback_model", "baseline", "none"
    point_forecast: Optional[float]
    p10: Optional[float]
    p50: Optional[float]
    p90: Optional[float]
    model_name: str
    model_version: str
    fallback_reason: Optional[str] = None
    failure_reason: Optional[str] = None
    feature_row: Optional[Dict[str, float]] = None

    def to_record(self, run_id: str, timestamp_utc: datetime) -> Dict[str, Any]:
        return {
            "run_id": run_id,
            "forecast_run_id": run_id,
            "region_id": self.region_id,
            "warehouse_id": self.warehouse_id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "category": self.category,
            "target_week": self.target_week_id,
            "target_week_id": self.target_week_id,
            "target_week_start_date": self.target_week_start,
            "target_week_end_date": self.target_week_end,
            "horizon": 1,
            "forecast_created_at": timestamp_utc,
            "forecast_generation_timestamp": timestamp_utc,
            "status": self.status,
            "method": self.method,
            "point_forecast": round(self.point_forecast, 2) if self.point_forecast is not None else None,
            "p10": round(self.p10, 2) if self.p10 is not None else None,
            "p50": round(self.p50, 2) if self.p50 is not None else None,
            "p90": round(self.p90, 2) if self.p90 is not None else None,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "fallback_reason": self.fallback_reason,
            "failure_reason": self.failure_reason,
        }


@dataclass
class BatchForecastResult:
    run_id: str
    warehouse_id: str
    region_id: str
    target_week_id: str
    target_week_start: str
    target_week_end: str
    status: str
    total_tasks: int
    succeeded_tasks: int
    failed_tasks: int
    counts_by_method: Dict[str, int]
    duration_seconds: float
    tasks: List[ForecastTaskOutput]
    failed_task_summary: List[Dict[str, Any]]
    readiness_report: Optional[Dict[str, Any]] = None


class WeeklyBatchForecastEngine:
    """Production coordinator engine for weekly batch demand forecasts."""

    def __init__(self, db: Database, settings: Settings, model_dir: Optional[str] = None):
        self.db = db
        self.settings = settings
        self.model_dir = model_dir or os.path.join(os.getcwd(), "artifacts", "models")
        self._ridge_cache: Dict[str, Any] = {}
        self._lgb_artifact: Optional[Dict[str, Any]] = None
        self._lgb_booster: Optional[lgb.Booster] = None

    def _get_lgb_standby(self) -> Tuple[Optional[lgb.Booster], Optional[Dict[str, Any]]]:
        if self._lgb_booster is not None and self._lgb_artifact is not None:
            return self._lgb_booster, self._lgb_artifact

        lgb_path = os.path.join(self.model_dir, "lightgbm", "global_standby.joblib")
        if not os.path.exists(lgb_path):
            log.warning("LightGBM standby artifact not found at %s", lgb_path)
            return None, None

        art = joblib.load(lgb_path)
        booster = lgb.Booster(model_str=art["model_str"])
        self._lgb_artifact = art
        self._lgb_booster = booster
        return self._lgb_booster, self._lgb_artifact

    def _get_ridge_model(self, product_id: str) -> Optional[Dict[str, Any]]:
        if product_id in self._ridge_cache:
            return self._ridge_cache[product_id]

        path = os.path.join(self.model_dir, "ridge", f"{product_id}.joblib")
        if not os.path.exists(path):
            return None

        art = joblib.load(path)
        self._ridge_cache[product_id] = art
        return art

    def execute_task(
        self,
        task: Dict[str, Any],
        warehouse_id: str,
        frame: pd.DataFrame,
        reg_doc: Optional[Dict[str, Any]],
        force_rung: Optional[str] = None
    ) -> ForecastTaskOutput:
        """Executes a single product forecast through the multi-tier recovery ladder.

        Task isolation guarantees that an error in one product never bubbles up
        to abort other products in the batch.
        """
        pid = task["product_id"]
        last_row = frame.iloc[-2]  # last history row before target
        prod_name = str(last_row.get("product_name", pid))
        cat_name = str(last_row.get("category", "General"))
        r_id = task["region_id"]
        tw_id = task["week_id"]
        tw_start = task["week_start_date"]
        tw_end = task.get("week_end_date", "")

        hist = frame.iloc[:-1]  # history only

        # ------------------------------------------------------------------
        # Rung 1: Champion Ridge Model (Approved in Model Registry)
        # ------------------------------------------------------------------
        if force_rung not in ("fallback_model", "baseline", "controlled_failure"):
            is_approved = (reg_doc is not None and reg_doc.get("status") == "APPROVED")
            if is_approved:
                try:
                    ridge_art = self._get_ridge_model(pid)
                    if ridge_art is not None:
                        base_price = float(ridge_art.get("base_list_price", last_row.get("list_price_rs", 100.0)))
                        feats = build_target_features(frame, base_list_price=base_price)
                        pipe = ridge_art["model"]
                        pred_log = float(pipe.predict(feats)[0])

                        p10 = max(0.0, float(np.expm1(pred_log + ridge_art["q10_log_residual"])))
                        p50 = max(0.0, float(np.expm1(pred_log + ridge_art["q50_log_residual"])))
                        expected = max(0.0, float(np.exp(pred_log) * ridge_art["smearing_factor"] - 1.0))
                        p90 = max(0.0, float(np.expm1(pred_log + ridge_art["q90_log_residual"])))

                        if all(np.isfinite([p10, p50, expected, p90])) and expected >= 0.0:
                            return ForecastTaskOutput(
                                task_id=task["task_id"],
                                region_id=r_id,
                                warehouse_id=warehouse_id,
                                product_id=pid,
                                product_name=prod_name,
                                category=cat_name,
                                target_week_id=tw_id,
                                target_week_start=tw_start,
                                target_week_end=tw_end,
                                status="SUCCESS",
                                method="champion",
                                point_forecast=expected,
                                p10=p10,
                                p50=p50,
                                p90=p90,
                                model_name="ridge",
                                model_version=str(reg_doc.get("version", "v1")),
                                feature_row=feats.iloc[0].to_dict(),
                            )
                except Exception as e:
                    log.warning("Product %s Rung 1 (Ridge) execution error: %s. Falling to Rung 2.", pid, e)

        # ------------------------------------------------------------------
        # Rung 2: Standby Model (Global Pooled LightGBM)
        # ------------------------------------------------------------------
        if force_rung not in ("baseline", "controlled_failure"):
            try:
                booster, lgb_art = self._get_lgb_standby()
                if booster is not None and lgb_art is not None:
                    cat_map = lgb_art["category_map"]
                    cat_code = cat_map.get(category_of(pid), 0)
                    base_price = float(lgb_art["base_list_prices"].get(pid, last_row.get("list_price_rs", 100.0)))
                    feats = build_target_features(frame, base_list_price=base_price)
                    feats_lgb = feats.copy()
                    feats_lgb["category_code"] = cat_code

                    rel = float(booster.predict(feats_lgb[lgb_art["feature_columns"]])[0])
                    level = float(feats["demand_level_log1p"].iloc[0])
                    pred_log_lgb = level + rel

                    p10 = max(0.0, float(np.expm1(pred_log_lgb + lgb_art["q10_log_residual"])))
                    p50 = max(0.0, float(np.expm1(pred_log_lgb + lgb_art["q50_log_residual"])))
                    expected = max(0.0, float(np.exp(pred_log_lgb) * lgb_art["smearing_factor"] - 1.0))
                    p90 = max(0.0, float(np.expm1(pred_log_lgb + lgb_art["q90_log_residual"])))

                    reason = "ridge_not_approved" if (not reg_doc or reg_doc.get("status") != "APPROVED") else "ridge_inference_fallback"
                    if force_rung == "fallback_model":
                        reason = "forced_by_operator"

                    if all(np.isfinite([p10, p50, expected, p90])) and expected >= 0.0:
                        return ForecastTaskOutput(
                            task_id=task["task_id"],
                            region_id=r_id,
                            warehouse_id=warehouse_id,
                            product_id=pid,
                            product_name=prod_name,
                            category=cat_name,
                            target_week_id=tw_id,
                            target_week_start=tw_start,
                            target_week_end=tw_end,
                            status="SUCCESS",
                            method="fallback_model",
                            point_forecast=expected,
                            p10=p10,
                            p50=p50,
                            p90=p90,
                            model_name="lightgbm_global_standby",
                            model_version=str(lgb_art.get("version", "v1")),
                            fallback_reason=reason,
                            feature_row=feats.iloc[0].to_dict(),
                        )
            except Exception as e:
                log.warning("Product %s Rung 2 (LightGBM) error: %s. Falling to Rung 3.", pid, e)

        # ------------------------------------------------------------------
        # Rung 3: Rolling Moving Median / Seasonal Naive Baseline
        # ------------------------------------------------------------------
        if force_rung != "controlled_failure":
            try:
                valid_hist = hist.loc[hist["stockout_flag"].eq(0) & hist["units_sold"].notna(), "units_sold"].astype(float)
                recent = valid_hist.tail(4)
                if len(recent) > 0:
                    base_val = float(recent.median())
                elif len(valid_hist) > 0:
                    base_val = float(valid_hist.median())
                else:
                    base_val = 0.0

                p10 = max(0.0, round(base_val * 0.85, 2))
                p50 = max(0.0, round(base_val, 2))
                expected = max(0.0, round(base_val, 2))
                p90 = max(0.0, round(base_val * 1.15, 2))

                reason = "standby_model_unavailable_or_failed" if force_rung != "baseline" else "forced_by_operator"

                return ForecastTaskOutput(
                    task_id=task["task_id"],
                    region_id=r_id,
                    warehouse_id=warehouse_id,
                    product_id=pid,
                    product_name=prod_name,
                    category=cat_name,
                    target_week_id=tw_id,
                    target_week_start=tw_start,
                    target_week_end=tw_end,
                    status="SUCCESS",
                    method="baseline",
                    point_forecast=expected,
                    p10=p10,
                    p50=p50,
                    p90=p90,
                    model_name="moving_median_baseline",
                    model_version="v1",
                    fallback_reason=reason,
                )
            except Exception as e:
                log.warning("Product %s Rung 3 (Baseline) error: %s. Falling to Rung 4.", pid, e)

        # ------------------------------------------------------------------
        # Rung 4: Controlled Failure ("No Safe Forecast Available")
        # ------------------------------------------------------------------
        return ForecastTaskOutput(
            task_id=task["task_id"],
            region_id=r_id,
            warehouse_id=warehouse_id,
            product_id=pid,
            product_name=prod_name,
            category=cat_name,
            target_week_id=tw_id,
            target_week_start=tw_start,
            target_week_end=tw_end,
            status="FAILED",
            method="none",
            point_forecast=None,
            p10=None,
            p50=None,
            p90=None,
            model_name="none",
            model_version="none",
            failure_reason="No Safe Forecast Available (all rungs exhausted or forced failure)",
        )

    def run_batch_forecast(
        self,
        warehouse_id: Optional[str] = None,
        region_id: Optional[str] = None,
        product_id: Optional[str] = None,
        target_week_id: Optional[str] = None,
        run_id: Optional[str] = None,
        check_readiness_first: bool = True,
        force_rung: Optional[str] = None,
    ) -> BatchForecastResult:
        """Executes the full weekly batch forecast pipeline."""
        start_time = time.time()
        start_utc_dt = datetime.now(timezone.utc)
        start_utc = start_utc_dt.isoformat()
        run_id = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # 1. Resolve Demand Region & Warehouse
        ident = region_id or warehouse_id or self.settings.region_id
        w_id, r_id, wh_doc = resolve_warehouse_and_region(self.db, ident)
        if not r_id:
            r_id = ident
        resolved_wh_id = w_id or "WH-001"

        # 2. Resolve Target Week & Last Completed Week
        col_cal = self.db[self.settings.collections["calendar_weeks"]]
        if target_week_id:
            tw_doc = col_cal.find_one({"week_id": target_week_id})
            if not tw_doc:
                raise ValueError(f"Target week '{target_week_id}' not found in calendar_weeks")
            last_done = col_cal.find_one({"week_status": "COMPLETED"}, sort=[("week_start_date", -1)])
        else:
            tw_doc, last_done = resolve_target_week(self.db, self.settings)

        tw_id = tw_doc["week_id"]
        tw_start = tw_doc["week_start_date"]
        tw_end = tw_doc["week_end_date"]

        # 3. Mandatory Data Readiness Gate Check
        readiness_dict = None
        if check_readiness_first:
            gate_report = check_data_readiness(
                self.db, self.settings, warehouse_id=resolved_wh_id, region_id=r_id, target_week=tw_doc, persist_report=True
            )
            readiness_dict = gate_report.to_dict()
            if not gate_report.ready:
                # Log failed run in run_metadata and raise
                duration = round(time.time() - start_time, 3)
                self.db["run_metadata"].insert_one({
                    "run_id": run_id,
                    "type": "forecast_execution",
                    "warehouse_id": resolved_wh_id,
                    "region_id": r_id,
                    "target_week": tw_id,
                    "status": "FAILED",
                    "reason": "data_readiness_gate_blocked",
                    "issues": readiness_dict["issues"],
                    "started_at": start_utc,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "duration_seconds": duration,
                })
                raise ReadinessGateBlockedError(gate_report)

        # 4. Generate Eligible Tasks
        all_tasks, skipped = generate_tasks(self.db, self.settings, tw_doc, last_done)
        if product_id:
            tasks = [t for t in all_tasks if t["product_id"] == product_id]
            if not tasks:
                # Generate task on the fly for single product if mapped
                tasks = [{
                    "task_id": f"{r_id}|{product_id}|{tw_start}",
                    "region_id": r_id,
                    "product_id": product_id,
                    "week_id": tw_id,
                    "week_start_date": tw_start,
                    "lookback_start": all_tasks[0]["lookback_start"] if all_tasks else "",
                    "lookback_end": all_tasks[0]["lookback_end"] if all_tasks else "",
                }]
        else:
            tasks = all_tasks

        if not tasks:
            raise RuntimeError(f"No eligible tasks found for warehouse {warehouse_id} and target week {tw_id}")

        # 5. Fetch External and Historical Context
        pids = [t["product_id"] for t in tasks]
        lb_start = tasks[0]["lookback_start"]
        lb_end = tasks[0]["lookback_end"]
        histories = fetch_history(self.db, self.settings, pids, lb_start, lb_end)
        festival_ctx = fetch_festival_context(self.db, self.settings, tw_doc)
        weather_ctx = fetch_weather_context(self.db, self.settings, tw_doc)

        # 6. Preload Model Registry for Region
        col_reg = self.db["model_registry"]
        reg_docs = {d["product_id"]: d for d in col_reg.find({"region_id": r_id})}

        # 7. Execute Tasks with Isolation
        task_outputs: List[ForecastTaskOutput] = []
        failed_summaries: List[Dict[str, Any]] = []
        counts_by_method = {"champion": 0, "fallback_model": 0, "baseline": 0, "none": 0}

        for t in tasks:
            pid = t["product_id"]
            try:
                hist_df = histories.get(pid)
                if hist_df is None or hist_df.empty:
                    raise ValueError(f"No history found for product {pid} in lookback window {lb_start} -> {lb_end}")

                frame = build_task_frame(t, hist_df, festival_ctx, weather_ctx)
                out = self.execute_task(t, resolved_wh_id, frame, reg_docs.get(pid), force_rung=force_rung)
                task_outputs.append(out)

                counts_by_method[out.method] = counts_by_method.get(out.method, 0) + 1
                if out.status == "FAILED":
                    failed_summaries.append({"product_id": pid, "reason": out.failure_reason})
            except Exception as task_err:
                log.error("Task %s failed completely: %s", t["task_id"], task_err)
                failed_out = ForecastTaskOutput(
                    task_id=t["task_id"],
                    region_id=r_id,
                    warehouse_id=resolved_wh_id,
                    product_id=pid,
                    product_name=pid,
                    category="Unknown",
                    target_week_id=tw_id,
                    target_week_start=tw_start,
                    target_week_end=tw_end,
                    status="FAILED",
                    method="none",
                    point_forecast=None,
                    p10=None,
                    p50=None,
                    p90=None,
                    model_name="none",
                    model_version="none",
                    failure_reason=f"Task execution exception: {task_err}",
                )
                task_outputs.append(failed_out)
                counts_by_method["none"] += 1
                failed_summaries.append({"product_id": pid, "reason": str(task_err)})

        duration = round(time.time() - start_time, 3)
        completed_dt = datetime.now(timezone.utc)
        succeeded_count = sum(1 for o in task_outputs if o.status == "SUCCESS")
        failed_count = sum(1 for o in task_outputs if o.status == "FAILED")

        overall_status = "SUCCESS" if failed_count == 0 else ("PARTIAL_SUCCESS" if succeeded_count > 0 else "FAILED")

        # 8. Idempotent Batch Persistence into forecast_results
        col_res = self.db[self.settings.collections["forecast_results"]]
        records = [o.to_record(run_id, completed_dt) for o in task_outputs]
        if records:
            # Upsert each record
            for r in records:
                col_res.update_one(
                    {
                        "run_id": run_id,
                        "region_id": r["region_id"],
                        "product_id": r["product_id"],
                        "target_week": r["target_week"],
                    },
                    {"$set": r},
                    upsert=True,
                )

        # 9. Record Batch Metadata in run_metadata
        col_meta = self.db[self.settings.collections["run_metadata"]]
        meta_doc = {
            "run_id": run_id,
            "forecast_run_id": run_id,
            "type": "forecast_execution",
            "warehouse_id": resolved_wh_id,
            "region_id": r_id,
            "target_week": tw_id,
            "target_week_start": tw_start,
            "target_week_end": tw_end,
            "status": overall_status,
            "total_tasks": len(task_outputs),
            "succeeded_tasks": succeeded_count,
            "failed_tasks": failed_count,
            "counts_by_method": counts_by_method,
            "duration_seconds": duration,
            "started_at": start_utc,
            "completed_at": completed_dt.isoformat(),
            "failed_task_summary": failed_summaries[:20],
        }
        col_meta.insert_one(meta_doc)

        return BatchForecastResult(
            run_id=run_id,
            warehouse_id=resolved_wh_id,
            region_id=r_id,
            target_week_id=tw_id,
            target_week_start=tw_start,
            target_week_end=tw_end,
            status=overall_status,
            total_tasks=len(task_outputs),
            succeeded_tasks=succeeded_count,
            failed_tasks=failed_count,
            counts_by_method=counts_by_method,
            duration_seconds=duration,
            tasks=task_outputs,
            failed_task_summary=failed_summaries,
            readiness_report=readiness_dict,
        )
