from datetime import date, timedelta
from pymongo.database import Database
from demand_agent.config import Settings


def generate_tasks(db: Database, settings: Settings, target_week: dict, last_completed: dict):
    """One task per MAPPED product. Lookback = 52 weeks ending at the last COMPLETED week."""
    c = settings.collections
    last_start = date.fromisoformat(last_completed["week_start_date"])
    lb_start = (last_start - timedelta(weeks=51)).isoformat()
    lb_end = last_start.isoformat()

    products = [p["product_id"] for p in db[c["product_master"]].find(
        {"mapping_status": "MAPPED"}, {"_id": 0, "product_id": 1})]

    hist_counts = {r["_id"]: r["n"] for r in db[c["historical_demand"]].aggregate([
        {"$match": {"region_id": settings.region_id, "is_partial_week": False}},
        {"$group": {"_id": "$product_id", "n": {"$sum": 1}}},
    ])}

    synth = {r["_id"]: r["n"] for r in db[c["demand_features"]].aggregate([
        {"$match": {"region_id": settings.region_id, "is_synthetic_record": True,
                    "week_start_date": {"$gte": lb_start, "$lte": lb_end}}},
        {"$group": {"_id": "$product_id", "n": {"$sum": 1}}},
    ])}

    eligible, ineligible = [], []
    for pid in products:
        n = hist_counts.get(pid, 0)
        if n < settings.min_history_weeks:
            ineligible.append({"product_id": pid,
                               "reason": f"only {n} completed weeks (< {settings.min_history_weeks})"})
            continue
        eligible.append({
            "task_id": f"{settings.region_id}|{pid}|{target_week['week_start_date']}",
            "region_id": settings.region_id,
            "product_id": pid,
            "week_id": target_week["week_id"],
            "week_start_date": target_week["week_start_date"],
            "lookback_start": lb_start,
            "lookback_end": lb_end,
            "lookback_synthetic_weeks": synth.get(pid, 0),
        })
    return eligible, ineligible