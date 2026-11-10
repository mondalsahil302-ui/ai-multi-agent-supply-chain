from collections.abc import Iterable

from pymongo import ASCENDING
from pymongo.database import Database

from demand_ingestion.database.collections import (
    FESTIVAL_CALENDAR,
    FESTIVAL_INGESTION_COLLECTIONS,
    HISTORICAL_DEMAND,
    HISTORICAL_DEMAND_COLLECTIONS,
    INGESTION_QUARANTINE,
    INGESTION_RUNS,
    REQUIRED_COLLECTIONS,
    WEATHER_FORECASTS,
    WEATHER_HISTORY,
    WEATHER_INGESTION_COLLECTIONS,
)


def ensure_indexes(
    database: Database,
    collection_names: Iterable[str],
) -> None:
    """Create indexes only for the selected ingestion path's collections."""

    selected = set(collection_names)
    unknown = selected.difference(REQUIRED_COLLECTIONS)
    if unknown:
        raise ValueError(f"Unknown ingestion collections: {sorted(unknown)}")

    if HISTORICAL_DEMAND in selected:
        database[HISTORICAL_DEMAND].create_index(
            [
                ("region_id", ASCENDING),
                ("product_id", ASCENDING),
                ("week_start", ASCENDING),
            ],
            unique=True,
            name="uq_historical_region_product_week",
        )
    if WEATHER_HISTORY in selected:
        database[WEATHER_HISTORY].create_index(
            [("location_id", ASCENDING), ("weather_date", ASCENDING)],
            unique=True,
            name="uq_weather_history_region_date",
        )
    if WEATHER_FORECASTS in selected:
        database[WEATHER_FORECASTS].create_index(
            [
                ("location_id", ASCENDING),
                ("weather_date", ASCENDING),
                ("forecast_snapshot_id", ASCENDING),
            ],
            unique=True,
            name="uq_weather_forecast_snapshot",
        )
    if FESTIVAL_CALENDAR in selected:
        database[FESTIVAL_CALENDAR].create_index(
            [
                ("country_code", ASCENDING),
                ("region_code", ASCENDING),
                ("event_date", ASCENDING),
                ("normalized_event_name", ASCENDING),
            ],
            unique=True,
            name="uq_festival_country_region_date_name",
        )
    if INGESTION_RUNS in selected:
        database[INGESTION_RUNS].create_index(
            [("ingestion_run_id", ASCENDING)],
            unique=True,
            name="uq_ingestion_run_id",
        )
        database[INGESTION_RUNS].create_index(
            [("source_name", ASCENDING), ("start_timestamp", ASCENDING)],
            name="ix_ingestion_runs_source_started",
        )
    if INGESTION_QUARANTINE in selected:
        database[INGESTION_QUARANTINE].create_index(
            [("quarantine_id", ASCENDING)],
            unique=True,
            name="uq_quarantine_id",
        )
        database[INGESTION_QUARANTINE].create_index(
            [("processing_status", ASCENDING), ("ingestion_timestamp", ASCENDING)],
            name="ix_quarantine_reprocessing",
        )
        database[INGESTION_QUARANTINE].create_index(
            [("ingestion_run_id", ASCENDING)],
            name="ix_quarantine_run",
        )


def ensure_weather_indexes(database: Database) -> None:
    ensure_indexes(database, WEATHER_INGESTION_COLLECTIONS)


def ensure_festival_indexes(database: Database) -> None:
    ensure_indexes(database, FESTIVAL_INGESTION_COLLECTIONS)


def ensure_historical_demand_indexes(database: Database) -> None:
    ensure_indexes(database, HISTORICAL_DEMAND_COLLECTIONS)
