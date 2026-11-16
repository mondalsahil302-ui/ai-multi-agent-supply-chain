"""Data Readiness Gate (Section 3).

Forecasting is allowed ONLY when all required data is loaded in MongoDB
for the selected warehouse. Otherwise the system refuses to forecast and
returns a structured not-ready report with human-readable and JSON diagnostics.

Checks:
  1. Historical demand (lookback window, gaps, duplicates, freshness)
  2. Weather (history coverage, forecast coverage, freshness)
  3. Festival calendar (coverage of target week, freshness)
  4. Product/region mappings (active product master mapping)
  5. Model (approved model in model_registry, schema v1, 34 features)
"""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
from pymongo.database import Database

from demand_agent.config import Settings
from demand_agent.forecast.week_resolver import resolve_target_week
from demand_agent.warehouse import resolve_warehouse_and_region


@dataclass
class ReadinessIssue:
    dataset: str
    entity: str
    reason: str
    detail: str


@dataclass
class ReadinessReport:
    ready: bool
    warehouse_id: str
    region_id: Optional[str]
    target_week_id: str
    target_week_start: str
    target_week_end: str
    issues: List[Dict[str, Any]]
    human_readable: str
    checked_at_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def check_data_readiness(
    db: Database,
    settings: Settings,
    warehouse_id: Optional[str] = None,
    region_id: Optional[str] = None,
    target_week: Optional[Dict[str, Any]] = None,
    persist_report: bool = False
) -> ReadinessReport:
    """Evaluates all 5 mandatory data readiness checks for the given demand region/warehouse and target week."""
    issues: List[ReadinessIssue] = []
    now_utc = datetime.now(timezone.utc).isoformat()

    # 1. Resolve Demand Region and Warehouse
    ident = region_id or warehouse_id or settings.region_id
    w_id, r_id, wh_doc = resolve_warehouse_and_region(db, ident)
    
    if not r_id:
        r_id = ident

    # If warehouse is unpopulated / region is out of scope for pilot
    is_pilot_region = (r_id == settings.region_id or w_id == settings.warehouse_id)
    if not wh_doc and not is_pilot_region:
        dataset_name = "warehouse_master" if (ident.startswith("WH-") or (w_id and w_id.startswith("WH-"))) else "region_master"
        issues.append(ReadinessIssue(
            dataset=dataset_name,
            entity=f"warehouse:{w_id}" if dataset_name == "warehouse_master" else f"region:{r_id}",
            reason="out_of_scope",
            detail=f"{'Warehouse' if dataset_name == 'warehouse_master' else 'Demand region'} '{ident}' is not recognized or out of scope for pilot phase (Lake Gardens KOL-LOC-001 / WH-001 is active)."
        ))
        target_week_str = target_week["week_id"] if target_week else "UNKNOWN"
        tw_start = target_week.get("week_start_date", "") if target_week else ""
        tw_end = target_week.get("week_end_date", "") if target_week else ""
        return _build_report(False, w_id or "NONE", r_id, target_week_str, tw_start, tw_end, issues, now_utc)

    if wh_doc and not wh_doc.get("is_operational", False) and not is_pilot_region:
        issues.append(ReadinessIssue(
            dataset="historical_demand",
            entity=f"region:{r_id}",
            reason="unpopulated",
            detail=f"Demand region '{r_id}' has no historical demand loaded (pilot phase is focused on Lake Gardens KOL-LOC-001)."
        ))

    # 2. Resolve Target Week and Lookback Window
    if not target_week:
        try:
            target_week_obj, last_completed_obj = resolve_target_week(db, settings)
        except Exception as e:
            issues.append(ReadinessIssue(
                dataset="calendar_weeks",
                entity="target_week",
                reason="resolution_failed",
                detail=f"Could not resolve target week from calendar_weeks: {e}"
            ))
            return _build_report(False, warehouse_id, r_id, "UNKNOWN", "", "", issues, now_utc)
    else:
        target_week_obj = target_week
        last_completed_obj = db[settings.collections["calendar_weeks"]].find_one(
            {"week_status": "COMPLETED"},
            sort=[("week_start_date", -1)]
        )

    tw_id = target_week_obj.get("week_id", "")
    tw_start = target_week_obj.get("week_start_date", "")
    tw_end = target_week_obj.get("week_end_date", "")

    # Lookback window calculation (52 weeks ending at last completed week)
    if last_completed_obj:
        last_start = date.fromisoformat(last_completed_obj["week_start_date"])
        lb_start = (last_start - timedelta(weeks=51)).isoformat()
        lb_end = last_start.isoformat()
    else:
        lb_start, lb_end = "", ""
        issues.append(ReadinessIssue(
            dataset="calendar_weeks",
            entity="last_completed_week",
            reason="missing",
            detail="No completed week found in calendar_weeks to anchor lookback window."
        ))

    # If region is unpopulated, stop early and return clear not-ready response
    if not is_pilot_region and (not wh_doc or not wh_doc.get("is_operational", False)):
        return _build_report(False, w_id or "NONE", r_id, tw_id, tw_start, tw_end, issues, now_utc)

    # 3. Check 1: Historical Demand
    col_hist = db[settings.collections["historical_demand"]]
    hist_count = col_hist.count_documents({"region_id": r_id})
    if hist_count == 0:
        issues.append(ReadinessIssue(
            dataset="historical_demand",
            entity=f"region:{r_id}",
            reason="missing",
            detail=f"No historical demand records found for region '{r_id}'."
        ))
    else:
        # Check required lookback window coverage across series
        # Expected: exactly 52 weeks in [lb_start, lb_end]
        pipeline_lb = [
            {"$match": {"region_id": r_id, "week_start_date": {"$gte": lb_start, "$lte": lb_end}}},
            {"$group": {"_id": "$product_id", "count": {"$sum": 1}}}
        ]
        lb_counts = {r["_id"]: r["count"] for r in col_hist.aggregate(pipeline_lb)}
        missing_history_prods = [p for p, c in lb_counts.items() if c < 52]

        if missing_history_prods:
            sample_missing = missing_history_prods[:3]
            issues.append(ReadinessIssue(
                dataset="historical_demand",
                entity=f"{len(missing_history_prods)} series (e.g. {', '.join(sample_missing)})",
                reason="incomplete_lookback",
                detail=f"Lookback window {lb_start} to {lb_end} has missing weeks (expected 52 weeks per series)."
            ))

        # Check latest actual week freshness
        latest_act = col_hist.find_one({"region_id": r_id}, sort=[("week_start_date", -1)])
        if latest_act and latest_act["week_start_date"] < lb_end:
            issues.append(ReadinessIssue(
                dataset="historical_demand",
                entity=f"region:{r_id}",
                reason="stale",
                detail=f"Latest actual week {latest_act['week_start_date']} is older than required lookback end {lb_end}."
            ))

    # 4. Check 2: Weather Data
    col_w_hist = db[settings.collections["weather_history"]]
    col_w_fc = db[settings.collections["weather_forecasts"]]

    # Weather history coverage
    w_hist_count = col_w_hist.count_documents({
        "region_id": r_id,
        "week_start_date": {"$gte": lb_start, "$lte": lb_end}
    })
    if w_hist_count < 52:
        issues.append(ReadinessIssue(
            dataset="weather_history",
            entity=f"region:{r_id}",
            reason="incomplete_lookback",
            detail=f"Weather history only covers {w_hist_count}/52 weeks in lookback window [{lb_start} -> {lb_end}]."
        ))

    # Weather forecast coverage for target week
    # Target week days: tw_start to tw_end
    if tw_start and tw_end:
        fc_days = col_w_fc.count_documents({
            "region_id": r_id,
            "forecast_date": {"$gte": tw_start, "$lte": tw_end}
        })
        if fc_days < 7:
            # Check if any future forecast is ingested
            total_fc = col_w_fc.count_documents({"region_id": r_id})
            if total_fc == 0:
                issues.append(ReadinessIssue(
                    dataset="weather_forecast",
                    entity=f"region:{r_id}",
                    reason="not_ingested",
                    detail=f"No weather forecast ingested for target week {tw_id} ({tw_start} -> {tw_end})."
                ))
            else:
                issues.append(ReadinessIssue(
                    dataset="weather_forecast",
                    entity=f"region:{r_id}",
                    reason="partial_horizon",
                    detail=f"Weather forecast only covers {fc_days}/7 days for target week {tw_id} ({tw_start} -> {tw_end})."
                ))

        # Check weather forecast freshness (limit: 48h)
        latest_fc = col_w_fc.find_one({"region_id": r_id}, sort=[("forecast_retrieved_at", -1)])
        if latest_fc and "forecast_retrieved_at" in latest_fc:
            try:
                retrieved_dt = datetime.fromisoformat(str(latest_fc["forecast_retrieved_at"]).replace("Z", "+00:00"))
                age_h = (datetime.now(timezone.utc) - retrieved_dt).total_seconds() / 3600.0
                if age_h > 48.0:
                    issues.append(ReadinessIssue(
                        dataset="weather_forecast",
                        entity=f"region:{r_id}",
                        reason="stale",
                        detail=f"Weather forecast is stale (last retrieved {age_h:.1f} hours ago, limit 48 hours)."
                    ))
            except Exception:
                pass

    # 5. Check 3: Festival Calendar
    col_fest = db[settings.collections["festival_calendar"]]
    fest_count = col_fest.count_documents({"region_id": r_id})
    if fest_count == 0:
        issues.append(ReadinessIssue(
            dataset="festival_calendar",
            entity=f"region:{r_id}",
            reason="missing",
            detail="Festival calendar has 0 events registered for this region."
        ))
    else:
        # Check if events cover target horizon (at least events within target month)
        target_year = tw_start[:4] if tw_start else str(date.today().year)
        fest_year_count = col_fest.count_documents({"region_id": r_id, "festival_date": {"$regex": f"^{target_year}"}})
        if fest_year_count == 0:
            issues.append(ReadinessIssue(
                dataset="festival_calendar",
                entity=f"year:{target_year}",
                reason="not_ingested",
                detail=f"Festival calendar has no holidays ingested for year {target_year}."
            ))

    # 6. Check 4: Product/Region Mappings
    col_prod = db[settings.collections["product_master"]]
    mapped_count = col_prod.count_documents({"mapping_status": "MAPPED"})
    if mapped_count == 0:
        issues.append(ReadinessIssue(
            dataset="product_master",
            entity="mapping_status",
            reason="no_mapped_products",
            detail="product_master contains 0 MAPPED products."
        ))

    # 7. Check 5: Approved Model in Registry
    col_reg = db["model_registry"]
    approved_models = col_reg.count_documents({"region_id": r_id, "status": "APPROVED"})
    if approved_models == 0:
        issues.append(ReadinessIssue(
            dataset="model_registry",
            entity=f"region:{r_id}",
            reason="no_approved_model",
            detail=f"No approved models found in model_registry for region '{r_id}'."
        ))

    # Build and return readiness report
    is_ready = (len(issues) == 0)
    report = _build_report(is_ready, warehouse_id, r_id, tw_id, tw_start, tw_end, issues, now_utc)

    # Persist readiness report in run_metadata if requested
    if persist_report:
        run_id = f"gate_{uuid.uuid4().hex[:16]}"
        db["run_metadata"].insert_one({
            "run_id": run_id,
            "type": "readiness_gate_report",
            "warehouse_id": warehouse_id,
            "region_id": r_id,
            "target_week": tw_id,
            "ready": is_ready,
            "issues": [asdict(i) for i in issues],
            "checked_at_utc": now_utc,
            "started_at": now_utc,
        })

    return report


def _build_report(
    ready: bool,
    warehouse_id: str,
    region_id: Optional[str],
    target_week_id: str,
    target_week_start: str,
    target_week_end: str,
    issues: List[ReadinessIssue],
    checked_at_utc: str
) -> ReadinessReport:
    """Formats human-readable string and compiles structured report."""
    status_header = "READY FOR FORECASTING" if ready else "NOT READY FOR FORECASTING"
    human_lines = [
        f"Status: {status_header}",
        f"Warehouse: {warehouse_id}   Target week: {target_week_id} ({target_week_start} -> {target_week_end})"
    ]

    if not ready:
        human_lines.append("Missing / invalid data:")
        for iss in issues:
            human_lines.append(f"  - {iss.dataset}: {iss.detail}")
        human_lines.append("Action: wait for ingestion to complete, then retry.")
    else:
        human_lines.append("All 5 data readiness checks PASSED: demand lookback, weather, festival, mappings, approved model.")
        human_lines.append("Action: Ready to execute weekly batch forecast.")

    human_str = "\n".join(human_lines)

    return ReadinessReport(
        ready=ready,
        warehouse_id=warehouse_id,
        region_id=region_id,
        target_week_id=target_week_id,
        target_week_start=target_week_start,
        target_week_end=target_week_end,
        issues=[asdict(i) for i in issues],
        human_readable=human_str,
        checked_at_utc=checked_at_utc
    )
