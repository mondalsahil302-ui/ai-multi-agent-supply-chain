"""Quarantine record contract and sanitized quarantine record creation."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from demand_ingestion.normalization.common import (
    QuarantineErrorCategory,
    compute_payload_fingerprint,
    sanitize_payload,
)


class QuarantineRecord(BaseModel):
    """
    Structured quarantine record representing a rejected or conflicting source record.

    Payloads and messages are strictly sanitized to ensure no credentials or
    secrets are ever leaked.
    """

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
    )

    quarantine_id: str = Field(min_length=1, max_length=100)
    source_system: str = Field(min_length=1, max_length=100)
    record_type: str = Field(min_length=1, max_length=50)
    ingestion_run_id: str | None = Field(default=None, max_length=100)
    source_record_fingerprint: str = Field(min_length=1, max_length=64)
    error_category: QuarantineErrorCategory
    error_message: str = Field(min_length=1, max_length=2000)
    quarantined_at_utc: datetime
    raw_payload: dict[str, Any]

    @field_validator("quarantined_at_utc")
    @classmethod
    def validate_quarantined_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("quarantined_at_utc must be timezone-aware")
        return value.astimezone(UTC)


def create_quarantine_record(
    *,
    source_system: str,
    record_type: str,
    raw_payload: Any,
    error_category: QuarantineErrorCategory,
    error_message: str,
    ingestion_run_id: str | None = None,
    quarantine_id: str | None = None,
    quarantined_at_utc: datetime | None = None,
) -> QuarantineRecord:
    """Create a structured, credential-scrubbed quarantine record."""
    clean_payload = (
        sanitize_payload(raw_payload)
        if isinstance(raw_payload, dict)
        else {"raw": sanitize_payload(raw_payload)}
    )
    clean_message = sanitize_payload(error_message)
    fingerprint = compute_payload_fingerprint(clean_payload)
    qid = quarantine_id or f"quar_{uuid4().hex}"
    timestamp = quarantined_at_utc or datetime.now(UTC)

    return QuarantineRecord(
        quarantine_id=qid,
        source_system=source_system,
        record_type=record_type,
        ingestion_run_id=ingestion_run_id,
        source_record_fingerprint=fingerprint,
        error_category=error_category,
        error_message=str(clean_message),
        quarantined_at_utc=timestamp,
        raw_payload=clean_payload,
    )

