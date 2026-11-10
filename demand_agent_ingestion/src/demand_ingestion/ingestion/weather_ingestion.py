import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TypedDict
from zoneinfo import ZoneInfo

from demand_ingestion.config import Settings, get_settings
from demand_ingestion.data_sources.region_master import (
    RegionMasterEntry,
    load_region_master,
)
from demand_ingestion.database.collections import (
    WEATHER_FORECASTS,
    WEATHER_HISTORY,
    WEATHER_INGESTION_COLLECTIONS,
)
from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.database.upsert_manager import UpsertResult, upsert_records
from demand_ingestion.ingestion.quarantine import persist_quarantine
from demand_ingestion.monitoring.ingestion_logger import (
    IngestionRun,
    IngestionRunStatus,
    IngestionRunTracker,
)
from demand_ingestion.normalization.common import (
    LocationMetadata,
    LocationRegistry,
    QuarantineErrorCategory,
)
from demand_ingestion.normalization.quarantine import create_quarantine_record
from demand_ingestion.normalization.weather import (
    NormalizedWeatherRecord,
    normalize_weather_batch,
)
from demand_ingestion.open_meteo_client import (
    OpenMeteoClient,
    OpenMeteoError,
)
from demand_ingestion.weather_models import WeatherDailyRecord

logger = logging.getLogger(__name__)


class WeatherPersistCounts(TypedDict):
    validated: int
    quarantined: int
    inserted: int
    updated: int
    unchanged: int
    failed: int
    errors: list[str]


class WeatherIngestionResult(TypedDict):
    run: IngestionRun
    failed_regions: list[str]
    error_summary: list[str]


def ingest_weather(
    mongo: MongoDatabase,
    *,
    settings: Settings | None = None,
    regions: list[RegionMasterEntry] | None = None,
    region_master_path: str | Path | None = None,
    client: OpenMeteoClient | None = None,
    historical_start_date: date | None = None,
    forecast_days: int | None = None,
) -> WeatherIngestionResult:
    """Fetch, validate, quarantine, and persist weather for every region."""

    config = settings or get_settings()
    requested_forecast_days = (
        config.default_forecast_days if forecast_days is None else forecast_days
    )
    if (
        isinstance(requested_forecast_days, bool)
        or not isinstance(requested_forecast_days, int)
        or not 1 <= requested_forecast_days <= 16
    ):
        raise ValueError("forecast_days must be between 1 and 16.")
    mongo.ping()
    mongo.ensure_schema(collection_names=WEATHER_INGESTION_COLLECTIONS)
    tracker = IngestionRunTracker(
        mongo,
        source_name="open_meteo",
        command_name="weather_ingestion",
    )
    tracker.start()
    owned_client = client is None
    weather_client = client or OpenMeteoClient(settings=config)

    records_received = records_validated = records_quarantined = 0
    inserted = updated = unchanged = failed_records = 0
    failed_regions: set[str] = set()
    errors: list[str] = []
    successful_contexts: list[str] = []
    source_metadata: list[dict[str, object]] = []
    try:
        configured_regions = (
            regions
            if regions is not None
            else load_region_master(region_master_path, settings=config)
        )
        if len(configured_regions) != 40:
            raise ValueError(
                f"Expected 40 configured regions, found {len(configured_regions)}."
            )
        registry = LocationRegistry(
            [
                LocationMetadata(
                    location_id=region.region_id,
                    expected_latitude=region.latitude,
                    expected_longitude=region.longitude,
                    name=region.region_name,
                )
                for region in configured_regions
            ]
        )
        local_today = datetime.now(ZoneInfo(config.default_timezone)).date()
        history_end = local_today - timedelta(days=1)
        configured_backfill = config.weather_backfill_start_date
        initial_history_start = (
            date.fromisoformat(configured_backfill)
            if configured_backfill
            else None
        )
        forecast_snapshot = tracker.run.ingestion_run_id
        for region in configured_regions:
            region_failed = False
            history_start = _history_start(
                mongo,
                region.region_id,
                history_end,
                historical_start_date,
                initial_history_start,
                config.weather_history_lookback_days,
            )
            if history_start <= history_end:
                try:
                    result = weather_client.fetch_historical_daily_result(
                        location_id=region.region_id,
                        latitude=region.latitude,
                        longitude=region.longitude,
                        start_date=history_start,
                        end_date=history_end,
                        timezone=config.default_timezone,
                    )
                    observations = result.records
                    source_metadata.append(
                        result.metadata.model_dump(mode="json")
                    )
                    records_received += len(observations)
                    observations, date_quarantine = _filter_historical_dates(
                        observations,
                        local_today,
                        ingestion_run_id=tracker.run.ingestion_run_id,
                    )
                    records_quarantined += persist_quarantine(
                        mongo,
                        date_quarantine,
                        ingestion_run_id=tracker.run.ingestion_run_id,
                    )
                    counts = _normalize_and_persist(
                        mongo,
                        observations,
                        registry=registry,
                        ingestion_run_id=tracker.run.ingestion_run_id,
                        forecast_snapshot_id=None,
                        collection_name=WEATHER_HISTORY,
                        batch_size=config.ingestion_batch_size,
                    )
                    records_validated += counts["validated"]
                    records_quarantined += counts["quarantined"]
                    inserted += counts["inserted"]
                    updated += counts["updated"]
                    unchanged += counts["unchanged"]
                    failed_records += counts["failed"]
                    errors.extend(counts["errors"])
                    region_failed |= counts["failed"] > 0
                    successful_contexts.append(
                        f"history:{region.region_id}:{history_start}:{history_end}"
                    )
                except OpenMeteoError as exc:
                    region_failed = True
                    errors.append(
                        f"{region.region_id} historical request failed: {exc}"
                    )
                    if exc.source_metadata is not None:
                        source_metadata.append(
                            exc.source_metadata.model_dump(mode="json")
                        )

            try:
                result = weather_client.fetch_forecast_daily_result(
                    location_id=region.region_id,
                    latitude=region.latitude,
                    longitude=region.longitude,
                    forecast_days=requested_forecast_days,
                    timezone=config.default_timezone,
                )
                forecasts = result.records
                source_metadata.append(
                    result.metadata.model_dump(mode="json")
                )
                records_received += len(forecasts)
                counts = _normalize_and_persist(
                    mongo,
                    forecasts,
                    registry=registry,
                    ingestion_run_id=tracker.run.ingestion_run_id,
                    forecast_snapshot_id=forecast_snapshot,
                    collection_name=WEATHER_FORECASTS,
                    batch_size=config.ingestion_batch_size,
                )
                records_validated += counts["validated"]
                records_quarantined += counts["quarantined"]
                inserted += counts["inserted"]
                updated += counts["updated"]
                unchanged += counts["unchanged"]
                failed_records += counts["failed"]
                errors.extend(counts["errors"])
                region_failed |= counts["failed"] > 0
                successful_contexts.append(
                    f"forecast:{region.region_id}:{forecast_snapshot}"
                )
            except OpenMeteoError as exc:
                region_failed = True
                errors.append(f"{region.region_id} forecast request failed: {exc}")
                if exc.source_metadata is not None:
                    source_metadata.append(
                        exc.source_metadata.model_dump(mode="json")
                    )

            if region_failed:
                failed_regions.add(region.region_id)

        status = _status(
            successful_records=inserted + updated + unchanged,
            failed_regions=failed_regions,
            errors=errors,
            records_quarantined=records_quarantined,
            failed_records=failed_records,
        )
        completed = tracker.finish(
            status=status,
            records_received=records_received,
            records_validated=records_validated,
            records_inserted=inserted,
            records_updated=updated,
            records_unchanged=unchanged,
            records_quarantined=records_quarantined,
            records_failed=failed_records,
            failed_regions=sorted(failed_regions),
            error_summary=errors,
            successful_contexts=successful_contexts,
            source_metadata=source_metadata,
        )
        return {
            "run": completed,
            "failed_regions": sorted(failed_regions),
            "error_summary": errors,
        }
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        tracker.finish(
            status=IngestionRunStatus.FAILED,
            records_received=records_received,
            records_validated=records_validated,
            records_inserted=inserted,
            records_updated=updated,
            records_unchanged=unchanged,
            records_quarantined=records_quarantined,
            records_failed=failed_records,
            failed_regions=sorted(failed_regions),
            error_summary=errors,
            successful_contexts=successful_contexts,
            source_metadata=source_metadata,
        )
        raise
    finally:
        if owned_client:
            weather_client.close()


def _history_start(
    mongo: MongoDatabase,
    region_id: str,
    history_end: date,
    requested_start: date | None,
    initial_start: date | None,
    lookback_days: int,
) -> date:
    last = mongo.database[WEATHER_HISTORY].find_one(
        {"location_id": region_id},
        {"weather_date": 1},
        sort=[("weather_date", -1)],
    )
    if last is not None:
        if requested_start is not None:
            return requested_start
        try:
            return date.fromisoformat(last["weather_date"]) + timedelta(days=1)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Stored historical weather date is invalid for region {region_id}."
            ) from exc
    if requested_start is not None:
        return requested_start
    return initial_start or history_end - timedelta(days=lookback_days - 1)


def _filter_historical_dates(
    records: list[WeatherDailyRecord],
    local_today: date,
    *,
    ingestion_run_id: str,
) -> tuple[list[WeatherDailyRecord], list]:
    accepted: list[WeatherDailyRecord] = []
    quarantined = []
    for record in records:
        if record.weather_date >= local_today:
            quarantined.append(
                create_quarantine_record(
                    source_system="open_meteo",
                    record_type="weather",
                    raw_payload=record.model_dump(mode="json"),
                    error_category=QuarantineErrorCategory.DATE_OUT_OF_RANGE,
                    error_message=(
                        "Historical weather contains a current or future date."
                    ),
                    ingestion_run_id=ingestion_run_id,
                )
            )
        else:
            accepted.append(record)
    return accepted, quarantined


def _normalize_and_persist(
    mongo: MongoDatabase,
    records: list[WeatherDailyRecord],
    *,
    registry: LocationRegistry,
    ingestion_run_id: str,
    forecast_snapshot_id: str | None,
    collection_name: str,
    batch_size: int,
) -> WeatherPersistCounts:
    normalized, quarantined, report = normalize_weather_batch(
        records,
        location_registry=registry,
        strict_location_check=True,
        forecast_snapshot_id=forecast_snapshot_id,
        ingestion_run_id=ingestion_run_id,
    )
    persisted_quarantined = persist_quarantine(
        mongo,
        quarantined,
        ingestion_run_id=ingestion_run_id,
    )
    result = _persist_weather(
        mongo,
        collection_name,
        normalized,
        batch_size=batch_size,
    )
    return {
        "validated": report.accepted_records,
        "quarantined": persisted_quarantined,
        "inserted": result.inserted,
        "updated": result.updated,
        "unchanged": result.unchanged,
        "failed": result.failed,
        "errors": result.error_details,
    }


def _persist_weather(
    mongo: MongoDatabase,
    collection_name: str,
    records: list[NormalizedWeatherRecord],
    *,
    batch_size: int,
) -> UpsertResult:
    if collection_name == WEATHER_HISTORY:
        key_fields = ("location_id", "weather_date")
    else:
        key_fields = (
            "location_id",
            "weather_date",
            "forecast_snapshot_id",
        )
    return upsert_records(
        mongo,
        collection_name=collection_name,
        records=records,
        key_fields=key_fields,
        batch_size=batch_size,
    ).result


def _status(
    *,
    successful_records: int,
    failed_regions: set[str],
    errors: list[str],
    records_quarantined: int,
    failed_records: int,
) -> IngestionRunStatus:
    if not errors and not failed_regions and not records_quarantined and not failed_records:
        return IngestionRunStatus.SUCCESS
    if successful_records or records_quarantined:
        return IngestionRunStatus.PARTIAL_SUCCESS
    return IngestionRunStatus.FAILED
