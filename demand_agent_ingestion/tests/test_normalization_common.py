"""Tests for common normalization utilities, registries, sanitization, and batch reporting."""

from datetime import UTC, date, datetime

import pytest

from demand_ingestion.normalization.common import (
    BatchNormalizationReport,
    CalendarRegistry,
    CalendarWeekRecord,
    LocationMetadata,
    LocationRegistry,
    QuarantineErrorCategory,
    compute_payload_fingerprint,
    sanitize_payload,
)


def test_sanitize_payload_redacts_credentials():
    payload = {
        "api_key": "secret_calendarific_key_123",
        "nested": {
            "token": "bearer_jwt_token_xyz",
            "password": "db_password_456",
            "mongo_uri": "mongodb://user:pass@localhost:27017",
            "normal_field": "Kolkata",
        },
        "url": "https://api.example.com/data?api_key=secret999&format=json",
        "header": "Bearer eyJhbGciOi...",
    }

    sanitized = sanitize_payload(payload)

    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["token"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert sanitized["nested"]["mongo_uri"] == "[REDACTED]"
    assert sanitized["nested"]["normal_field"] == "Kolkata"
    assert "secret999" not in sanitized["url"]
    assert "[REDACTED]" in sanitized["url"]
    assert "eyJhbGci" not in sanitized["header"]
    assert "[REDACTED]" in sanitized["header"]


def test_compute_payload_fingerprint_is_deterministic():
    p1 = {"location_id": "KOL-LOC-001", "date": "2026-10-29", "temp": 28.5}
    p2 = {"temp": 28.5, "date": "2026-10-29", "location_id": "KOL-LOC-001"}

    fp1 = compute_payload_fingerprint(p1)
    fp2 = compute_payload_fingerprint(p2)

    assert fp1 == fp2
    assert len(fp1) == 64


def test_location_registry_coordinate_validation():
    loc = LocationMetadata(
        location_id="KOL-LOC-001",
        expected_latitude=22.5014,
        expected_longitude=88.3617,
        name="South City",
    )
    registry = LocationRegistry([loc])

    # Within tolerance (0.05 deg ~ 5.5 km)
    is_valid, err = registry.validate_location(
        "KOL-LOC-001", 22.5020, 88.3620, tolerance_deg=0.05
    )
    assert is_valid is True
    assert err is None

    # Outside tolerance
    is_valid, err = registry.validate_location(
        "KOL-LOC-001", 22.6000, 88.3617, tolerance_deg=0.05
    )
    assert is_valid is False
    assert "deviate from authoritative registered coordinates" in err

    # Unknown location in strict mode
    is_valid, err = registry.validate_location(
        "UNKNOWN-LOC", 22.5014, 88.3617, strict=True
    )
    assert is_valid is False
    assert "not registered" in err

    # Unknown location in permissive mode
    is_valid, err = registry.validate_location(
        "UNKNOWN-LOC", 22.5014, 88.3617, strict=False
    )
    assert is_valid is True
    assert err is None


def test_calendar_registry_week_lookup_and_bounds():
    # Sunday 2026-11-01 to Saturday 2026-11-07
    w1 = CalendarWeekRecord(
        week_id="W140",
        week_start_date=date(2026, 11, 1),
        week_end_date=date(2026, 11, 7),
        year=2026,
        week_number=45,
    )
    registry = CalendarRegistry([w1])

    # Lookup within week
    found = registry.lookup_week_id(date(2026, 11, 4))
    assert found is not None
    assert found.week_id == "W140"

    # Lookup outside registered weeks
    assert registry.lookup_week_id(date(2026, 11, 10)) is None

    # Sunday-through-Saturday period bounds calculation
    # 2026-11-04 is a Wednesday -> Week starts on Sunday 2026-11-01, ends on Saturday 2026-11-07
    start_d, end_d = CalendarRegistry.compute_project_week_bounds(
        date(2026, 11, 4)
    )
    assert start_d == date(2026, 11, 1)  # Sunday
    assert end_d == date(2026, 11, 7)    # Saturday
    assert (end_d - start_d).days == 6

    # Sunday itself is the start date
    start_sun, end_sat = CalendarRegistry.compute_project_week_bounds(
        date(2026, 11, 1)
    )
    assert start_sun == date(2026, 11, 1)
    assert end_sat == date(2026, 11, 7)

    # Saturday is the end date
    start_sat, end_sat2 = CalendarRegistry.compute_project_week_bounds(
        date(2026, 11, 7)
    )
    assert start_sat == date(2026, 11, 1)
    assert end_sat2 == date(2026, 11, 7)


def test_batch_normalization_report_reconciliation():
    # Valid reconciliation
    rep = BatchNormalizationReport(
        batch_id="b1",
        source_system="open_meteo",
        record_type="weather",
        processed_at_utc=datetime.now(UTC),
        input_records=10,
        accepted_records=6,
        rejected_records=3,
        identical_duplicates=1,
        conflicting_duplicates=2,
        validation_failures=1,
    )
    assert rep.input_records == 10
    assert rep.accepted_records == 6
    assert rep.rejected_records == 3

    # Mismatched total input sum raises ValueError
    with pytest.raises(ValueError, match="Batch count reconciliation mismatch"):
        BatchNormalizationReport(
            batch_id="b2",
            source_system="open_meteo",
            record_type="weather",
            processed_at_utc=datetime.now(UTC),
            input_records=10,
            accepted_records=5,  # 5 + 1 + 2 + 1 = 9 != 10
            rejected_records=3,
            identical_duplicates=1,
            conflicting_duplicates=2,
            validation_failures=1,
        )

    # Mismatched rejected count raises ValueError
    with pytest.raises(ValueError, match="Rejected count mismatch"):
        BatchNormalizationReport(
            batch_id="b3",
            source_system="open_meteo",
            record_type="weather",
            processed_at_utc=datetime.now(UTC),
            input_records=10,
            accepted_records=6,
            rejected_records=4,  # Expected 2 + 1 = 3
            identical_duplicates=1,
            conflicting_duplicates=2,
            validation_failures=1,
        )


def test_quarantine_error_categories():
    assert QuarantineErrorCategory.VALIDATION_ERROR == "VALIDATION_ERROR"
    assert QuarantineErrorCategory.CONFLICTING_DUPLICATE == "CONFLICTING_DUPLICATE"
    assert QuarantineErrorCategory.LOCATION_COORDINATE_MISMATCH == "LOCATION_COORDINATE_MISMATCH"
