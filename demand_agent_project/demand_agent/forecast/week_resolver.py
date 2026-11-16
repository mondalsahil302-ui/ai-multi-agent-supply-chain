import logging
from pymongo.database import Database
from demand_agent.config import Settings

log = logging.getLogger(__name__)


def resolve_target_week(db: Database, settings: Settings) -> tuple[dict, dict]:
    """Weeks are Sunday-start (Sun-Sat).
    Returns (target_week, last_completed_week).
    Target = first FUTURE week. IN_PROGRESS weeks are never used as actuals."""
    weeks = list(db[settings.collections["calendar_weeks"]].find(
        {"region_id": settings.region_id},
        {"_id": 0, "week_id": 1, "week_start_date": 1, "week_end_date": 1, "week_status": 1},
    ).sort("week_start_date", 1))

    if not weeks:
        raise RuntimeError(f"No calendar_weeks for region {settings.region_id}")

    future = [w for w in weeks if w["week_status"] == "FUTURE"]
    if not future:
        raise RuntimeError("No FUTURE week in calendar_weeks; extend the calendar.")

    completed = [w for w in weeks if w["week_status"] == "COMPLETED"]
    if not completed:
        raise RuntimeError("No COMPLETED weeks in calendar_weeks.")

    last_completed = max(completed, key=lambda w: w["week_start_date"])
    return future[0], last_completed