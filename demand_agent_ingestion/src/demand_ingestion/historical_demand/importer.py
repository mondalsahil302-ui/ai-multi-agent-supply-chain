import csv
import hashlib
import json
import logging
import sqlite3
import tempfile
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import TypedDict

from pydantic import ValidationError

from demand_ingestion.config import Settings, get_settings
from demand_ingestion.database.collections import (
    HISTORICAL_DEMAND,
    HISTORICAL_DEMAND_COLLECTIONS,
)
from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.database.upsert_manager import upsert_records
from demand_ingestion.historical_demand.validation import HistoricalDemandRecord
from demand_ingestion.ingestion.quarantine import persist_quarantine
from demand_ingestion.monitoring.ingestion_logger import (
    IngestionRun,
    IngestionRunStatus,
    IngestionRunTracker,
)
from demand_ingestion.normalization.common import QuarantineErrorCategory
from demand_ingestion.normalization.quarantine import (
    QuarantineRecord,
    create_quarantine_record,
)

logger = logging.getLogger(__name__)


class HistoricalImportResult(TypedDict):
    run: IngestionRun
    invalid_rows: int
    duplicate_rows: int
    continuity_gaps: int


def import_historical_demand(
    mongo: MongoDatabase,
    *,
    settings: Settings | None = None,
    dataset_path: str | Path | None = None,
    region_ids: Iterable[str] | None = None,
    product_ids: Iterable[str] | None = None,
    batch_size: int | None = None,
) -> HistoricalImportResult:
    """Manually import existing weekly demand data, safely resumable by upsert."""

    config = settings or get_settings()
    path = Path(
        config.historical_demand_dataset_path
        if dataset_path is None
        else dataset_path
    )
    size = (
        config.ingestion_batch_size
        if batch_size is None
        else batch_size
    )
    if size < 1:
        raise ValueError("batch_size must be positive.")
    mongo.ping()
    mongo.ensure_schema(collection_names=HISTORICAL_DEMAND_COLLECTIONS)
    tracker = IngestionRunTracker(
        mongo,
        source_name="historical_demand",
        command_name="historical_demand_import",
    )
    tracker.start()

    valid_batch: list[HistoricalDemandRecord] = []
    quarantine_batch: list[QuarantineRecord] = []
    series_ranges: dict[tuple[str, str], tuple[date, date, int]] = {}
    records_received = records_validated = records_quarantined = 0
    inserted = updated = unchanged = failed_records = 0
    invalid_rows = duplicate_rows = 0
    errors: list[str] = []
    seen_store: sqlite3.Connection | None = None
    seen_store_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            prefix="demand-import-",
            suffix=".sqlite3",
            delete=False,
        ) as temporary_store:
            seen_store_path = Path(temporary_store.name)
        seen_store = sqlite3.connect(seen_store_path)
        seen_store.execute(
            """
            CREATE TABLE seen_keys (
                region_id TEXT NOT NULL,
                product_id TEXT NOT NULL,
                week_start TEXT NOT NULL,
                PRIMARY KEY (region_id, product_id, week_start)
            ) WITHOUT ROWID
            """
        )
        allowed_regions = (
            set(region_ids)
            if region_ids is not None
            else set()
        )
        allowed_products = (
            set(product_ids)
            if product_ids is not None
            else _configured_product_ids(config)
        )
        if not path.is_file():
            raise FileNotFoundError(f"Historical demand dataset not found: {path}")

        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames:
                raise ValueError("Historical demand dataset has no header.")
            required_columns = {
                "region_id",
                "product_id",
                "week_start_date",
                "week_end_date",
                "units_sold",
            }
            if not required_columns.issubset(reader.fieldnames):
                raise ValueError(
                    "Historical demand dataset is missing one or more required columns."
                )

            for line_number, row in enumerate(reader, start=2):
                records_received += 1
                try:
                    demand = HistoricalDemandRecord(
                        region_id=row.get("region_id"),
                        product_id=row.get("product_id"),
                        week_start=row.get("week_start_date"),
                        week_end=row.get("week_end_date"),
                        demand_quantity=row.get("units_sold"),
                        source_reference=f"{path.resolve()}:{line_number}",
                        source_record_hash=_source_record_hash(row),
                        source_fields=dict(row),
                    )
                    if allowed_regions and demand.region_id not in allowed_regions:
                        raise ValueError(
                            f"Unknown region_id {demand.region_id!r}."
                        )
                    if allowed_products and demand.product_id not in allowed_products:
                        raise ValueError(
                            f"Unknown product_id {demand.product_id!r}."
                        )
                    if (demand.week_end - demand.week_start).days != 6:
                        raise ValueError(
                            "week_start_date and week_end_date must span seven days."
                        )
                except (ValidationError, ValueError, TypeError) as exc:
                    invalid_rows += 1
                    quarantine_batch.append(
                        _quarantine_row(
                            row,
                            path=path,
                            line_number=line_number,
                            run_id=tracker.run.ingestion_run_id,
                            message=_validation_message(exc),
                            category=QuarantineErrorCategory.VALIDATION_ERROR,
                        )
                    )
                else:
                    key = (
                        demand.region_id,
                        demand.product_id,
                        demand.week_start,
                    )
                    inserted_key = seen_store.execute(
                        """
                        INSERT OR IGNORE INTO seen_keys
                        (region_id, product_id, week_start)
                        VALUES (?, ?, ?)
                        """,
                        (key[0], key[1], key[2].isoformat()),
                    ).rowcount
                    if not inserted_key:
                        duplicate_rows += 1
                        quarantine_batch.append(
                            _quarantine_row(
                                row,
                                path=path,
                                line_number=line_number,
                                run_id=tracker.run.ingestion_run_id,
                                message="Duplicate region-product-week record in source dataset.",
                                category=QuarantineErrorCategory.CONFLICTING_DUPLICATE,
                            )
                        )
                    else:
                        _update_series_range(
                            series_ranges,
                            (demand.region_id, demand.product_id),
                            demand.week_start,
                        )
                        valid_batch.append(demand)
                        records_validated += 1

                if len(valid_batch) + len(quarantine_batch) >= size:
                    seen_store.commit()
                    persisted = _flush_batch(
                        mongo,
                        valid_batch,
                        quarantine_batch,
                        run_id=tracker.run.ingestion_run_id,
                    )
                    inserted += persisted["inserted"]
                    updated += persisted["updated"]
                    unchanged += persisted["unchanged"]
                    failed_records += persisted["failed"]
                    errors.extend(persisted["errors"])
                    records_quarantined += persisted["quarantined"]
                    valid_batch.clear()
                    quarantine_batch.clear()

            if valid_batch or quarantine_batch:
                seen_store.commit()
                persisted = _flush_batch(
                    mongo,
                    valid_batch,
                    quarantine_batch,
                    run_id=tracker.run.ingestion_run_id,
                )
                inserted += persisted["inserted"]
                updated += persisted["updated"]
                unchanged += persisted["unchanged"]
                failed_records += persisted["failed"]
                errors.extend(persisted["errors"])
                records_quarantined += persisted["quarantined"]

        gaps = _continuity_gaps(series_ranges)
        if gaps:
            errors.append(
                f"Weekly continuity gaps detected in {gaps} region-product series."
            )
        if invalid_rows or duplicate_rows:
            errors.append(
                f"Rejected {invalid_rows} invalid and {duplicate_rows} duplicate source row(s)."
            )
        status = (
            IngestionRunStatus.PARTIAL_SUCCESS
            if errors
            else IngestionRunStatus.SUCCESS
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
            error_summary=errors,
        )
        return {
            "run": completed,
            "invalid_rows": invalid_rows,
            "duplicate_rows": duplicate_rows,
            "continuity_gaps": gaps,
        }
    except Exception as exc:
        errors.append(f"Historical import failed: {type(exc).__name__}.")
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
        )
        raise
    finally:
        if seen_store is not None:
            seen_store.close()
        if seen_store_path is not None:
            seen_store_path.unlink(missing_ok=True)


def _configured_product_ids(config: Settings) -> set[str]:
    path = config.product_master_dataset_path
    if path is None:
        return set()
    product_path = Path(path)
    if not product_path.is_file():
        raise FileNotFoundError(f"Product master dataset not found: {product_path}")
    with product_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "product_id" not in reader.fieldnames:
            raise ValueError("Product master requires a product_id column.")
        return {
            value.strip()
            for row in reader
            if (value := row.get("product_id"))
        }


def _quarantine_row(
    row: dict[str, str | None],
    *,
    path: Path,
    line_number: int,
    run_id: str,
    message: str,
    category: QuarantineErrorCategory,
) -> QuarantineRecord:
    record = dict(row)
    record["_source_reference"] = f"{path.resolve()}:{line_number}"
    return create_quarantine_record(
        source_system="historical_demand",
        record_type="weekly_demand",
        raw_payload=record,
        error_category=category,
        error_message=message,
        ingestion_run_id=run_id,
    )


def _validation_message(error: Exception) -> str:
    if isinstance(error, ValidationError):
        issues = [
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        ]
        return "Invalid demand row: " + "; ".join(issues)
    return str(error)


def _source_record_hash(row: dict[str, str | None]) -> str:
    serialized = json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _flush_batch(
    mongo: MongoDatabase,
    valid_records: list[HistoricalDemandRecord],
    quarantined: list[QuarantineRecord],
    *,
    run_id: str,
) -> dict[str, int]:
    quarantine_count = persist_quarantine(
        mongo,
        quarantined,
        ingestion_run_id=run_id,
    )
    report = upsert_records(
        mongo,
        collection_name=HISTORICAL_DEMAND,
        records=[
            {
                "source_fields": record.source_fields,
                "region_id": record.region_id,
                "product_id": record.product_id,
                "week_start": record.week_start.isoformat(),
                "week_end": record.week_end.isoformat(),
                "demand_quantity": record.demand_quantity,
                "source_reference": record.source_reference,
                "source_record_hash": record.source_record_hash,
                "source_name": "historical_demand",
                "ingestion_run_id": run_id,
            }
            for record in valid_records
        ],
        key_fields=("region_id", "product_id", "week_start"),
        insert_only=True,
    ).result
    return {
        "inserted": report.inserted,
        "updated": report.updated,
        "unchanged": report.unchanged,
        "failed": report.failed,
        "errors": report.error_details,
        "quarantined": quarantine_count,
    }


def _update_series_range(
    ranges: dict[tuple[str, str], tuple[date, date, int]],
    key: tuple[str, str],
    week_start: date,
) -> None:
    state = ranges.get(key)
    if state is None:
        ranges[key] = (week_start, week_start, 1)
        return
    earliest, latest, count = state
    ranges[key] = (
        min(earliest, week_start),
        max(latest, week_start),
        count + 1,
    )


def _continuity_gaps(ranges: dict[tuple[str, str], tuple[date, date, int]]) -> int:
    gaps = 0
    for earliest, latest, count in ranges.values():
        if count > 1 and (latest - earliest).days != 7 * (count - 1):
            gaps += 1
    return gaps
