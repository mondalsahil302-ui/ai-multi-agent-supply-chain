"""Tests for quarantine record creation and payload scrubbing."""

from datetime import UTC, datetime

import pytest

from demand_ingestion.normalization.common import QuarantineErrorCategory
from demand_ingestion.normalization.quarantine import (
    QuarantineRecord,
    create_quarantine_record,
)


def test_create_quarantine_record_sanitizes_payload():
    raw = {
        "api_key": "my_super_secret_calendarific_key",
        "nested": {"token": "secret_jwt", "temperature": 32.5},
        "location_id": "KOL-LOC-001",
    }
    msg = "Validation failed due to bad token: secret_jwt"

    quar = create_quarantine_record(
        source_system="open_meteo",
        record_type="weather",
        raw_payload=raw,
        error_category=QuarantineErrorCategory.VALIDATION_ERROR,
        error_message=msg,
        ingestion_run_id="run_123",
    )

    assert isinstance(quar, QuarantineRecord)
    assert quar.source_system == "open_meteo"
    assert quar.record_type == "weather"
    assert quar.ingestion_run_id == "run_123"
    assert quar.error_category == QuarantineErrorCategory.VALIDATION_ERROR
    assert len(quar.source_record_fingerprint) == 64

    # Verify sensitive data is scrubbed
    assert quar.raw_payload["api_key"] == "[REDACTED]"
    assert quar.raw_payload["nested"]["token"] == "[REDACTED]"
    assert quar.raw_payload["nested"]["temperature"] == 32.5
    assert quar.raw_payload["location_id"] == "KOL-LOC-001"


def test_quarantine_record_requires_timezone_aware_utc():
    # Naive datetime raises ValueError
    with pytest.raises(ValueError, match="timezone-aware"):
        QuarantineRecord(
            quarantine_id="q1",
            source_system="open_meteo",
            record_type="weather",
            source_record_fingerprint="abc",
            error_category=QuarantineErrorCategory.VALIDATION_ERROR,
            error_message="Error",
            quarantined_at_utc=datetime.now(),  # naive
            raw_payload={},
        )

    # Timezone-aware datetime normalized to UTC
    q = QuarantineRecord(
        quarantine_id="q2",
        source_system="open_meteo",
        record_type="weather",
        source_record_fingerprint="abc",
        error_category=QuarantineErrorCategory.VALIDATION_ERROR,
        error_message="Error",
        quarantined_at_utc=datetime.now(UTC),
        raw_payload={"foo": "bar"},
    )
    assert q.quarantined_at_utc.tzinfo == UTC

