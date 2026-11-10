import pytest
from pymongo.errors import BulkWriteError

from demand_ingestion.database.collections import REQUIRED_COLLECTIONS
from demand_ingestion.database.upsert_manager import upsert_records
from demand_ingestion.ingestion.quarantine import (
    persist_quarantine,
    update_quarantine_status,
)
from demand_ingestion.monitoring.ingestion_logger import (
    IngestionRunStatus,
    IngestionRunTracker,
)
from demand_ingestion.normalization.common import QuarantineErrorCategory
from demand_ingestion.normalization.quarantine import create_quarantine_record


def test_schema_creates_all_required_collections_and_unique_indexes(fake_mongo):
    fake_mongo.ensure_schema(collection_names=REQUIRED_COLLECTIONS)

    assert set(fake_mongo.database.list_collection_names()) == set(REQUIRED_COLLECTIONS)
    history_indexes = fake_mongo.database["weather_history"].indexes
    assert any(index["unique"] for _, index in history_indexes)


def test_upsert_is_idempotent_and_tracks_updates(fake_mongo):
    first = {
        "region_id": "KOL-LOC-001",
        "product_id": "P-001",
        "week_start": "2024-01-01",
        "demand_quantity": 10,
    }

    inserted = upsert_records(
        fake_mongo,
        collection_name="historical_demand",
        records=[first],
        key_fields=("region_id", "product_id", "week_start"),
    ).result
    unchanged = upsert_records(
        fake_mongo,
        collection_name="historical_demand",
        records=[first],
        key_fields=("region_id", "product_id", "week_start"),
    ).result
    changed = upsert_records(
        fake_mongo,
        collection_name="historical_demand",
        records=[{**first, "demand_quantity": 12}],
        key_fields=("region_id", "product_id", "week_start"),
    ).result

    assert (inserted.inserted, inserted.updated, inserted.unchanged) == (1, 0, 0)
    assert (unchanged.inserted, unchanged.updated, unchanged.unchanged) == (0, 0, 1)
    assert (changed.inserted, changed.updated, changed.unchanged) == (0, 1, 0)
    assert len(fake_mongo.database["historical_demand"].documents) == 1


def test_upsert_does_not_update_valid_data_for_run_provenance_only(fake_mongo):
    source = {
        "region_id": "R1",
        "product_id": "P1",
        "week_start": "2024-01-01",
        "demand_quantity": 5,
        "ingestion_run_id": "run-first",
    }
    upsert_records(
        fake_mongo,
        collection_name="historical_demand",
        records=[source],
        key_fields=("region_id", "product_id", "week_start"),
    )
    result = upsert_records(
        fake_mongo,
        collection_name="historical_demand",
        records=[{**source, "ingestion_run_id": "run-resume"}],
        key_fields=("region_id", "product_id", "week_start"),
    ).result

    assert result.unchanged == 1


def test_upsert_reports_partial_bulk_write_failures(fake_mongo):
    collection = fake_mongo.database["historical_demand"]

    def fail_bulk_write(operations, ordered=False):
        raise BulkWriteError(
            {
                "writeErrors": [{"index": 0, "code": 11000}],
                "nUpserted": 0,
                "nModified": 0,
                "nMatched": 0,
            }
        )

    collection.bulk_write = fail_bulk_write
    result = upsert_records(
        fake_mongo,
        collection_name="historical_demand",
        records=[
            {
                "region_id": "R1",
                "product_id": "P1",
                "week_start": "2024-01-01",
                "demand_quantity": 5,
            }
        ],
        key_fields=("region_id", "product_id", "week_start"),
    ).result

    assert result.failed == 1
    assert result.error_details == [
        "record 0: MongoDB write failed (code 11000)"
    ]


def test_quarantine_persists_original_and_rejection_reason(fake_mongo):
    record = create_quarantine_record(
        source_system="historical_demand",
        record_type="weekly_demand",
        raw_payload={"region_id": "BAD", "units_sold": "-1"},
        error_category=QuarantineErrorCategory.VALIDATION_ERROR,
        error_message="Demand cannot be negative.",
        ingestion_run_id="run-test",
    )

    count = persist_quarantine(
        fake_mongo,
        [record],
        ingestion_run_id="run-test",
    )
    saved = next(
        iter(fake_mongo.database["ingestion_quarantine"].documents.values())
    )

    assert count == 1
    assert saved["original_record"]["units_sold"] == "-1"
    assert saved["validation_errors"] == ["Demand cannot be negative."]
    assert saved["processing_status"] == "PENDING"
    assert saved["ingestion_run_id"] == "run-test"
    update_quarantine_status(
        fake_mongo,
        quarantine_id=saved["quarantine_id"],
        expected_status="PENDING",
        new_status="REPROCESSING",
    )
    saved = next(
        iter(fake_mongo.database["ingestion_quarantine"].documents.values())
    )
    assert saved["processing_status"] == "REPROCESSING"
    with pytest.raises(ValueError, match="Invalid quarantine status transition"):
        update_quarantine_status(
            fake_mongo,
            quarantine_id=saved["quarantine_id"],
            expected_status="PENDING",
            new_status="REPROCESSED",
        )


def test_run_tracker_persists_auditable_lifecycle(fake_mongo):
    tracker = IngestionRunTracker(
        fake_mongo,
        source_name="weather",
        command_name="unit-test",
    )
    tracker.start()
    completed = tracker.finish(
        status=IngestionRunStatus.PARTIAL_SUCCESS,
        records_received=3,
        records_validated=2,
        records_inserted=2,
        records_quarantined=1,
        failed_regions=["KOL-LOC-004"],
        error_summary=["one region failed"],
    )

    saved = next(iter(fake_mongo.database["ingestion_runs"].documents.values()))
    assert completed.status == IngestionRunStatus.PARTIAL_SUCCESS
    assert saved["records_received"] == 3
    assert saved["records_quarantined"] == 1
    assert saved["failed_regions"] == ["KOL-LOC-004"]
    assert saved["end_timestamp"] is not None
