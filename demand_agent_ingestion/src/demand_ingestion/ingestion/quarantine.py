import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from demand_ingestion.database.collections import INGESTION_QUARANTINE
from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.database.upsert_manager import upsert_records
from demand_ingestion.normalization.common import sanitize_payload
from demand_ingestion.normalization.quarantine import QuarantineRecord

_CREDENTIAL_PATTERN = re.compile(
    r"(?i)(api[_-]?key|password|token|secret|credential)=([^&\s]+)"
)
QuarantineStatus = Literal["PENDING", "REPROCESSING", "REPROCESSED", "REJECTED"]
_ALLOWED_TRANSITIONS = {
    "PENDING": {"REPROCESSING", "REJECTED"},
    "REPROCESSING": {"PENDING", "REPROCESSED", "REJECTED"},
    "REPROCESSED": set(),
    "REJECTED": set(),
}


def persist_quarantine(
    mongo: MongoDatabase,
    records: list[QuarantineRecord | dict[str, Any]],
    *,
    ingestion_run_id: str,
) -> int:
    """Persist sanitized rejection records with controlled reprocess state."""

    documents: list[dict[str, Any]] = []
    for item in records:
        raw = (
            item.model_dump(mode="json")
            if isinstance(item, QuarantineRecord)
            else dict(item)
        )
        raw_payload = sanitize_payload(
            raw.get("raw_payload", raw.get("original_record", {}))
        )
        error = _CREDENTIAL_PATTERN.sub(r"\1=[REDACTED]", str(
            raw.get("error_message", raw.get("validation_errors", "Validation failed"))
        ))
        quarantine_id = raw.get("quarantine_id") or hashlib.sha256(
            json.dumps(
                [ingestion_run_id, raw_payload, error],
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        region_id = _region_id(raw_payload)
        documents.append(
            {
                "quarantine_id": quarantine_id,
                "source_name": raw.get("source_system", raw.get("source_name", "unknown")),
                "original_record": raw_payload,
                "validation_errors": [error],
                "region_id": region_id,
                "ingestion_timestamp": raw.get(
                    "quarantined_at_utc",
                    datetime.now(UTC).isoformat(),
                ),
                "ingestion_run_id": ingestion_run_id,
                "processing_status": "PENDING",
                "error_category": raw.get("error_category", "VALIDATION_ERROR"),
                "source_record_fingerprint": raw.get("source_record_fingerprint"),
            }
        )

    if not documents:
        return 0

    result = upsert_records(
        mongo,
        collection_name=INGESTION_QUARANTINE,
        records=documents,
        key_fields=("quarantine_id",),
    ).result
    if result.failed:
        raise RuntimeError(
            f"Failed to persist {result.failed} quarantine record(s)."
        )
    return len(documents)


def _region_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("region_id") or payload.get("location_id")
    return value if isinstance(value, str) else None


def update_quarantine_status(
    mongo: MongoDatabase,
    *,
    quarantine_id: str,
    expected_status: QuarantineStatus,
    new_status: QuarantineStatus,
) -> None:
    """Apply a guarded quarantine-state transition for controlled reprocessing."""

    if new_status not in _ALLOWED_TRANSITIONS[expected_status]:
        raise ValueError(
            f"Invalid quarantine status transition: "
            f"{expected_status} -> {new_status}."
        )
    result = mongo.run_with_retry(
        lambda: mongo.database[INGESTION_QUARANTINE].update_one(
            {
                "quarantine_id": quarantine_id,
                "processing_status": expected_status,
            },
            {
                "$set": {
                    "processing_status": new_status,
                    "status_updated_at": datetime.now(UTC).isoformat(),
                }
            },
        )
    )
    if result.matched_count != 1:
        raise ValueError(
            "Quarantine record was not found in the expected processing state."
        )
