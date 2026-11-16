"""Ingestion pipeline coordinating API adapters, validation, quarantine, and idempotent upsert."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo.database import Database

from demand_agent.config import Settings
from demand_agent.ingestion.adapters.calendarific import CalendarificAdapter
from demand_agent.ingestion.adapters.open_meteo import OpenMeteoAdapter
from demand_agent.ingestion.quarantine import quarantine_record
from demand_agent.ingestion.validator import (
    validate_festival_record,
    validate_weather_forecast_record,
)

log = logging.getLogger(__name__)


def ingest_weather_forecasts(
    db: Database,
    settings: Settings,
    adapter: Optional[OpenMeteoAdapter] = None,
    mock_records: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Fetches, validates, quarantines, and upserts weather forecasts."""
    region_id = settings.region_id
    col_name = settings.collections["weather_forecasts"]
    col = db[col_name]

    if mock_records is not None:
        raw_records = mock_records
    else:
        ad = adapter or OpenMeteoAdapter(
            timeout_seconds=int(settings.collections.get("API_TIMEOUT_SECONDS", 15)),
            max_retries=int(settings.collections.get("API_MAX_RETRIES", 3))
        )
        lat = float(settings.collections.get("REGION_LATITUDE", 22.50574))
        lon = float(settings.collections.get("REGION_LONGITUDE", 88.35672))
        raw_records = ad.fetch_forecast(latitude=lat, longitude=lon, forecast_days=7)

    valid_count = 0
    quarantined_count = 0
    upserted_count = 0

    for rec in raw_records:
        rec["region_id"] = region_id
        val_res = validate_weather_forecast_record(
            rec,
            temp_min_bound=float(settings.collections.get("WEATHER_TEMP_MIN_C", 5.0)),
            temp_max_bound=float(settings.collections.get("WEATHER_TEMP_MAX_C", 48.0)),
            max_staleness_hours=int(settings.collections.get("SOURCE_MAX_STALENESS_HOURS", 48)),
        )

        if not val_res.is_valid:
            quarantine_record(db, source="open_meteo_weather", raw_payload=rec, reasons=val_res.errors, region_id=region_id)
            quarantined_count += 1
            log.warning(f"Quarantined invalid weather record for date {rec.get('forecast_date')}: {val_res.errors}")
        else:
            valid_doc = val_res.cleaned_record
            fc_date = valid_doc["forecast_date"]
            valid_doc["region_name"] = settings.collections.get("region_name", "Lake Gardens")

            # Remove _id if present to avoid immutable _id modification errors
            valid_doc.pop("_id", None)

            # Safe idempotent upsert keyed by region_id + forecast_date
            res = col.update_one(
                {"region_id": region_id, "forecast_date": fc_date},
                {"$set": valid_doc, "$setOnInsert": {"_id": f"{region_id}|{fc_date}"}},
                upsert=True
            )
            if res.upserted_id or res.modified_count > 0:
                upserted_count += 1
            valid_count += 1

    return {
        "status": "SUCCESS",
        "total_received": len(raw_records),
        "valid": valid_count,
        "quarantined": quarantined_count,
        "upserted": upserted_count,
        "collection": col_name
    }


def ingest_festival_calendar(
    db: Database,
    settings: Settings,
    adapter: Optional[CalendarificAdapter] = None,
    mock_records: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Fetches, validates, quarantines, and upserts festival calendar events."""
    region_id = settings.region_id
    col_name = settings.collections["festival_calendar"]
    col = db[col_name]

    if mock_records is not None:
        raw_records = mock_records
    else:
        api_key = settings.collections.get("CALENDARIFIC_API_KEY", "")
        ad = adapter or CalendarificAdapter(
            api_key=api_key,
            timeout_seconds=int(settings.collections.get("API_TIMEOUT_SECONDS", 15)),
            max_retries=int(settings.collections.get("API_MAX_RETRIES", 3))
        )
        country = settings.collections.get("CALENDARIFIC_COUNTRY", "IN")
        state = settings.collections.get("CALENDARIFIC_STATE", "IN-WB")
        raw_records = ad.fetch_holidays(country=country, location=state)

    valid_count = 0
    quarantined_count = 0
    upserted_count = 0

    for rec in raw_records:
        rec["region_id"] = region_id
        val_res = validate_festival_record(rec)

        if not val_res.is_valid:
            quarantine_record(db, source="calendarific_festival", raw_payload=rec, reasons=val_res.errors, region_id=region_id)
            quarantined_count += 1
            log.warning(f"Quarantined invalid festival record {rec.get('festival_name')}: {val_res.errors}")
        else:
            valid_doc = val_res.cleaned_record
            f_date = valid_doc["festival_date"]
            f_name = valid_doc["festival_name"]
            slug = f_name.lower().replace(" ", "-").replace("'", "")
            valid_doc["region_name"] = settings.collections.get("region_name", "Lake Gardens")

            # Remove _id if present to avoid immutable _id modification errors
            valid_doc.pop("_id", None)

            # Safe idempotent upsert keyed by region_id + festival_date + festival_name
            res = col.update_one(
                {"region_id": region_id, "festival_date": f_date, "festival_name": f_name},
                {"$set": valid_doc, "$setOnInsert": {"_id": f"{region_id}|{f_date}|{slug}"}},
                upsert=True
            )
            if res.upserted_id or res.modified_count > 0:
                upserted_count += 1
            valid_count += 1

    return {
        "status": "SUCCESS",
        "total_received": len(raw_records),
        "valid": valid_count,
        "quarantined": quarantined_count,
        "upserted": upserted_count,
        "collection": col_name
    }
