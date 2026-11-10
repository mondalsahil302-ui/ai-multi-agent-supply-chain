import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import TypedDict

from demand_ingestion.calendarific_client import (
    CalendarificClient,
    CalendarificError,
)
from demand_ingestion.config import Settings, get_settings
from demand_ingestion.database.collections import (
    FESTIVAL_CALENDAR,
    FESTIVAL_INGESTION_COLLECTIONS,
    INGESTION_RUNS,
)
from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.database.upsert_manager import upsert_records
from demand_ingestion.ingestion.quarantine import persist_quarantine
from demand_ingestion.monitoring.ingestion_logger import (
    IngestionRun,
    IngestionRunStatus,
    IngestionRunTracker,
)
from demand_ingestion.normalization.festivals import normalize_festival_batch

logger = logging.getLogger(__name__)


class FestivalIngestionResult(TypedDict):
    run: IngestionRun
    error_summary: list[str]
    successful_contexts: list[str]


def ingest_festivals(
    mongo: MongoDatabase,
    *,
    settings: Settings | None = None,
    client: CalendarificClient | None = None,
    years: Iterable[int] | None = None,
    locations: tuple[str | None, ...] | None = None,
    force_refresh: bool = False,
) -> FestivalIngestionResult:
    """Fetch, normalize, quarantine, and persist national and regional holidays."""

    config = settings or get_settings()
    mongo.ping()
    mongo.ensure_schema(collection_names=FESTIVAL_INGESTION_COLLECTIONS)
    tracker = IngestionRunTracker(
        mongo,
        source_name="calendarific",
        command_name="festival_ingestion",
    )
    tracker.start()
    owned_client = client is None
    calendarific = client or CalendarificClient(settings=config)

    records_received = records_validated = records_quarantined = 0
    inserted = updated = unchanged = failed_records = 0
    successful_contexts: list[str] = []
    errors: list[str] = []
    source_metadata: list[dict[str, object]] = []

    current = datetime.now(UTC).date()
    if years is None:
        final_month = current.month + config.festival_context_months - 1
        end_year = current.year + (final_month - 1) // 12
        requested_years = list(range(current.year, end_year + 1))
    else:
        requested_years = sorted(set(years))
    requested_locations = (
        (None, config.default_region_code)
        if locations is None
        else locations
    )

    try:
        for year in requested_years:
            for location in requested_locations:
                context_key = f"holidays:{config.default_country}:{location or 'national'}:{year}"
                if not force_refresh and _is_cached(
                    mongo,
                    context_key,
                    config.festival_cache_ttl_hours,
                ):
                    successful_contexts.append(context_key)
                    continue
                try:
                    result = calendarific.fetch_holidays_result(
                        country_code=config.default_country,
                        year=year,
                        location=location,
                    )
                    records = result.records
                    source_metadata.append(
                        result.metadata.model_dump(mode="json")
                    )
                except CalendarificError as exc:
                    errors.append(
                        f"{context_key}: {type(exc).__name__}: {exc}"
                    )
                    if exc.source_metadata is not None:
                        source_metadata.append(
                            exc.source_metadata.model_dump(mode="json")
                        )
                    continue

                records_received += len(records)
                normalized, quarantined, report = normalize_festival_batch(
                    records,
                    requested_year=year,
                    ingestion_run_id=tracker.run.ingestion_run_id,
                )
                records_quarantined += persist_quarantine(
                    mongo,
                    quarantined,
                    ingestion_run_id=tracker.run.ingestion_run_id,
                )
                documents = []
                for record in normalized:
                    document = record.model_dump(mode="json")
                    document["region_code"] = location
                    document["normalized_event_name"] = record.event_name.casefold()
                    document["source_region_code"] = location
                    documents.append(document)
                persisted = upsert_records(
                    mongo,
                    collection_name=FESTIVAL_CALENDAR,
                    records=documents,
                    key_fields=(
                        "country_code",
                        "region_code",
                        "event_date",
                        "normalized_event_name",
                    ),
                    batch_size=config.ingestion_batch_size,
                ).result
                records_validated += report.accepted_records
                inserted += persisted.inserted
                updated += persisted.updated
                unchanged += persisted.unchanged
                if persisted.failed:
                    failed_records += persisted.failed
                    errors.extend(persisted.error_details)
                    continue
                successful_contexts.append(context_key)

        successful_calls = len(successful_contexts)
        expected_calls = len(requested_years) * len(requested_locations)
        if (errors or records_quarantined) and successful_calls:
            status = IngestionRunStatus.PARTIAL_SUCCESS
        elif errors or (expected_calls and successful_calls == 0):
            status = IngestionRunStatus.FAILED
        else:
            status = IngestionRunStatus.SUCCESS
        completed = tracker.finish(
            status=status,
            records_received=records_received,
            records_validated=records_validated,
            records_inserted=inserted,
            records_updated=updated,
            records_unchanged=unchanged,
            records_quarantined=records_quarantined,
            records_failed=failed_records,
            error_summary=errors,
            successful_contexts=successful_contexts,
            source_metadata=source_metadata,
        )
        return {
            "run": completed,
            "error_summary": errors,
            "successful_contexts": successful_contexts,
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
            error_summary=errors,
            successful_contexts=successful_contexts,
            source_metadata=source_metadata,
        )
        raise
    finally:
        if owned_client:
            calendarific.close()


def _is_cached(
    mongo: MongoDatabase,
    context_key: str,
    cache_ttl_hours: int,
) -> bool:
    cutoff = (
        datetime.now(UTC) - timedelta(hours=cache_ttl_hours)
    ).isoformat()
    return (
        mongo.database[INGESTION_RUNS].find_one(
            {
                "source_name": "calendarific",
                "status": {"$in": ["SUCCESS", "PARTIAL_SUCCESS"]},
                "successful_contexts": context_key,
                "start_timestamp": {"$gte": cutoff},
            },
            {"_id": 1},
        )
        is not None
    )
