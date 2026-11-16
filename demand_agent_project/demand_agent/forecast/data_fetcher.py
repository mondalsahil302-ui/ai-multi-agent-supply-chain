import logging
import pandas as pd
from pymongo.database import Database
from demand_agent.config import Settings

log = logging.getLogger(__name__)

EXPECTED_FORECAST_DAYS = 7

HISTORY_PROJECTION = {
    "_id": 0, "product_id": 1, "product_name": 1, "category": 1,
    "week_id": 1, "week_start_date": 1,
    "units_sold": 1, "stockout_flag": 1,
    "promo_flag": 1, "discount_pct": 1, "selling_price_rs": 1, "list_price_rs": 1,
    "festival_name": 1, "festival_proximity": 1, "season": 1,
    "temperature_c": 1, "rainfall_mm": 1, "humidity_pct": 1,
    "is_synthetic_record": 1, "is_partial_week": 1, "period_status": 1,
}


def fetch_history(db: Database, settings: Settings, product_ids: list[str],
                  lb_start: str, lb_end: str) -> dict[str, pd.DataFrame]:
    """One bulk query for all products. Completed (non-partial) weeks only."""
    cur = db[settings.collections["demand_features"]].find(
        {
            "region_id": settings.region_id,
            "product_id": {"$in": product_ids},
            "week_start_date": {"$gte": lb_start, "$lte": lb_end},
            "is_partial_week": False,
        },
        HISTORY_PROJECTION,
    )
    df = pd.DataFrame(list(cur))
    if df.empty:
        return {}
    df = df.sort_values(["product_id", "week_start_date"])
    return {pid: g.reset_index(drop=True) for pid, g in df.groupby("product_id")}


def fetch_festival_context(db: Database, settings: Settings, target_week: dict) -> dict:
    doc = db[settings.collections["festival_week_features"]].find_one(
        {"region_id": settings.region_id, "week_start_date": target_week["week_start_date"]},
        {"_id": 0, "festival_name": 1, "festival_names": 1, "festival_count": 1,
         "festival_proximity": 1, "data_provenance": 1},
    )
    if not doc:
        return {"found": False, "festival_name": None, "festival_names": [],
                "festival_count": None, "festival_proximity": None}
    return {"found": True, "festival_name": doc.get("festival_name"),
            "festival_names": doc.get("festival_names", []),
            "festival_count": doc.get("festival_count"),
            "festival_proximity": doc.get("festival_proximity"),
            "provenance": doc.get("data_provenance")}


def fetch_weather_context(db: Database, settings: Settings, target_week: dict) -> dict:
    """Latest forecast per day inside the target week, summarised to week level."""
    docs = list(db[settings.collections["weather_forecasts"]].find(
        {
            "region_id": settings.region_id,
            "forecast_date": {"$gte": target_week["week_start_date"],
                              "$lte": target_week["week_end_date"]},
        },
        {"_id": 0, "forecast_date": 1, "temperature_max_c": 1, "temperature_min_c": 1,
         "precipitation_probability_day_pct": 1, "precipitation_probability_night_pct": 1,
         "forecast_retrieved_at_utc": 1},
    ).sort("forecast_retrieved_at_utc", -1))

    latest: dict[str, dict] = {}
    for d in docs:                       # newest first, keep first seen per date
        latest.setdefault(d["forecast_date"], d)

    if not latest:
        return {"days_covered": 0, "expected_days": EXPECTED_FORECAST_DAYS, "covered_dates": [],
                "temp_max_mean_c": None, "temp_min_mean_c": None, "temp_mean_c": None,
                "precip_prob_mean_pct": None, "latest_retrieved_at": None}

    rows = pd.DataFrame(latest.values()).sort_values("forecast_date")
    tmax, tmin = rows["temperature_max_c"], rows["temperature_min_c"]
    prob = (rows["precipitation_probability_day_pct"] + rows["precipitation_probability_night_pct"]) / 2
    return {
        "days_covered": int(len(rows)),
        "expected_days": EXPECTED_FORECAST_DAYS,
        "covered_dates": rows["forecast_date"].tolist(),
        "temp_max_mean_c": round(float(tmax.mean()), 2),
        "temp_min_mean_c": round(float(tmin.mean()), 2),
        "temp_mean_c": round(float(((tmax + tmin) / 2).mean()), 2),
        "precip_prob_mean_pct": round(float(prob.mean()), 1),
        "latest_retrieved_at": str(rows["forecast_retrieved_at_utc"].max()),
    }