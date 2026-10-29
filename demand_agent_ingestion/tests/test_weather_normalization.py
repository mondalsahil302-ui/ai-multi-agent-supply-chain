"""Tests for weather normalization, duplicate reconciliation, and forecast snapshot integrity."""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from demand_ingestion.normalization.common import (
    LocationMetadata,
    LocationRegistry,
    QuarantineErrorCategory,
)
from demand_ingestion.normalization.weather import (
    NormalizedWeatherRecord,
    compute_weather_business_key,
    compute_weather_record_id,
    normalize_weather_batch,
    normalize_weather_record,
)
from demand_ingestion.weather_models import WeatherDailyRecord


@pytest.fixture
def sample_weather_record():
    return WeatherDailyRecord(
        location_id="KOL-LOC-001",
        latitude=22.5014,
        longitude=88.3617,
        weather_date=date(2026, 10, 29),
        data_kind="historical",
        temperature_mean_c=28.5,
        temperature_min_c=22.0,
        temperature_max_c=34.0,
        rainfall_mm=12.4,
        humidity_mean_pct=75.0,
        weather_code=61,
        coverage_hours=24,
        source="open_meteo",
        retrieved_at_utc=datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def sample_location_registry():
    return LocationRegistry(
        [
            LocationMetadata(
                location_id="KOL-LOC-001",
                expected_latitude=22.5014,
                expected_longitude=88.3617,
                name="South City",
            ),
            LocationMetadata(
                location_id="KOL-LOC-002",
                expected_latitude=22.5390,
                expected_longitude=88.3657,
                name="Quest Mall",
            ),
        ]
    )


def test_valid_historical_weather_normalization(sample_weather_record):
    norm, quar = normalize_weather_record(sample_weather_record)

    assert quar is None
    assert norm is not None
    assert isinstance(norm, NormalizedWeatherRecord)
    assert norm.location_id == "KOL-LOC-001"
    assert norm.weather_date == date(2026, 10, 29)
    assert norm.data_kind == "historical"
    assert norm.temperature_mean_c == 28.5
    assert norm.rainfall_mm == 12.4
    assert norm.humidity_mean_pct == 75.0
    assert norm.schema_version == "v1"
    assert len(norm.record_id) == 64


def test_deterministic_record_identity_and_business_key():
    key1 = compute_weather_business_key(
        "KOL-LOC-001", date(2026, 10, 29), "historical"
    )
    key2 = compute_weather_business_key(
        "KOL-LOC-001", date(2026, 10, 29), "historical"
    )
    assert key1 == key2
    assert key1 == "open_meteo:KOL-LOC-001:2026-10-29:historical"

    id1 = compute_weather_record_id(
        "KOL-LOC-001", date(2026, 10, 29), "historical"
    )
    id2 = compute_weather_record_id(
        "KOL-LOC-001", date(2026, 10, 29), "historical"
    )
    assert id1 == id2


def test_forecast_snapshot_integrity_distinguishes_snapshots():
    # Two forecasts for the same target date issued at different snapshot times
    target_date = date(2026, 11, 2)
    key_snap1 = compute_weather_business_key(
        "KOL-LOC-001", target_date, "forecast", forecast_snapshot_id="20261028T000000Z"
    )
    key_snap2 = compute_weather_business_key(
        "KOL-LOC-001", target_date, "forecast", forecast_snapshot_id="20261029T000000Z"
    )
    assert key_snap1 != key_snap2
    assert "20261028T000000Z" in key_snap1
    assert "20261029T000000Z" in key_snap2

    rec1 = NormalizedWeatherRecord(
        record_id=compute_weather_record_id(
            "KOL-LOC-001", target_date, "forecast", "20261028T000000Z"
        ),
        location_id="KOL-LOC-001",
        latitude=22.5014,
        longitude=88.3617,
        weather_date=target_date,
        data_kind="forecast",
        forecast_snapshot_id="20261028T000000Z",
        temperature_mean_c=27.0,
        retrieved_at_utc=datetime(2026, 10, 28, 0, 0, tzinfo=UTC),
    )
    rec2 = NormalizedWeatherRecord(
        record_id=compute_weather_record_id(
            "KOL-LOC-001", target_date, "forecast", "20261029T000000Z"
        ),
        location_id="KOL-LOC-001",
        latitude=22.5014,
        longitude=88.3617,
        weather_date=target_date,
        data_kind="forecast",
        forecast_snapshot_id="20261029T000000Z",
        temperature_mean_c=29.0,
        retrieved_at_utc=datetime(2026, 10, 29, 0, 0, tzinfo=UTC),
    )
    assert rec1.record_id != rec2.record_id


def test_temperature_consistency_validation():
    # Minimum above maximum
    raw = {
        "location_id": "KOL-LOC-001",
        "latitude": 22.5,
        "longitude": 88.3,
        "weather_date": "2026-10-29",
        "data_kind": "historical",
        "temperature_min_c": 35.0,
        "temperature_max_c": 20.0,
        "retrieved_at_utc": "2026-10-29T12:00:00Z",
    }
    norm, quar = normalize_weather_record(raw)
    assert norm is None
    assert quar is not None
    assert quar.error_category == QuarantineErrorCategory.VALIDATION_ERROR
    assert "Minimum temperature cannot exceed maximum" in quar.error_message


def test_nan_and_infinite_measurements_rejected():
    with pytest.raises(ValidationError):
        NormalizedWeatherRecord(
            record_id="abc",
            location_id="KOL-LOC-001",
            latitude=22.5014,
            longitude=88.3617,
            weather_date=date(2026, 10, 29),
            data_kind="historical",
            temperature_mean_c=float("nan"),
            retrieved_at_utc=datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
        )

    with pytest.raises(ValidationError):
        NormalizedWeatherRecord(
            record_id="abc",
            location_id="KOL-LOC-001",
            latitude=22.5014,
            longitude=88.3617,
            weather_date=date(2026, 10, 29),
            data_kind="historical",
            temperature_mean_c=float("inf"),
            retrieved_at_utc=datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
        )


def test_location_registry_strict_and_tolerance_checks(
    sample_weather_record, sample_location_registry
):
    # Registered and within tolerance -> Success
    norm, quar = normalize_weather_record(
        sample_weather_record,
        location_registry=sample_location_registry,
        strict_location_check=True,
    )
    assert quar is None
    assert norm is not None

    # Registered but coordinates deviate beyond tolerance -> Quarantined
    deviated = sample_weather_record.model_copy(update={"latitude": 22.6500})
    norm, quar = normalize_weather_record(
        deviated,
        location_registry=sample_location_registry,
        coordinate_tolerance_deg=0.05,
    )
    assert norm is None
    assert quar is not None
    assert quar.error_category == QuarantineErrorCategory.LOCATION_COORDINATE_MISMATCH
    assert "deviate from authoritative registered coordinates" in quar.error_message

    # Unregistered location in strict mode -> Quarantined
    unregistered = sample_weather_record.model_copy(
        update={"location_id": "UNREGISTERED-LOC"}
    )
    norm, quar = normalize_weather_record(
        unregistered,
        location_registry=sample_location_registry,
        strict_location_check=True,
    )
    assert norm is None
    assert quar is not None
    assert quar.error_category == QuarantineErrorCategory.UNKNOWN_LOCATION


def test_batch_normalization_identical_duplicates_collapsed(sample_weather_record):
    rec1 = sample_weather_record
    rec2 = sample_weather_record.model_copy()
    rec3 = sample_weather_record.model_copy()

    accepted, quar, report = normalize_weather_batch([rec1, rec2, rec3])

    assert len(accepted) == 1
    assert len(quar) == 0
    assert report.input_records == 3
    assert report.accepted_records == 1
    assert report.identical_duplicates == 2
    assert report.conflicting_duplicates == 0
    assert report.validation_failures == 0
    assert report.rejected_records == 0


def test_batch_normalization_conflicting_duplicates_quarantined(
    sample_weather_record,
):
    rec1 = sample_weather_record
    # Same business key (KOL-LOC-001, 2026-10-29, historical) but differing valid temperature
    rec2 = sample_weather_record.model_copy(update={"temperature_mean_c": 29.5})

    accepted, quar, report = normalize_weather_batch([rec1, rec2])

    # Both conflicting records must be rejected and quarantined
    assert len(accepted) == 0
    assert len(quar) == 2
    assert report.input_records == 2
    assert report.accepted_records == 0
    assert report.conflicting_duplicates == 2
    assert report.identical_duplicates == 0
    assert report.rejected_records == 2
    assert all(
        q.error_category == QuarantineErrorCategory.CONFLICTING_DUPLICATE
        for q in quar
    )


def test_batch_normalization_deterministic_sorting():
    w_dates = [date(2026, 10, 31), date(2026, 10, 29), date(2026, 10, 30)]
    records = [
        WeatherDailyRecord(
            location_id="KOL-LOC-001",
            latitude=22.5,
            longitude=88.3,
            weather_date=d,
            data_kind="historical",
            temperature_mean_c=25.0,
            retrieved_at_utc=datetime(2026, 10, 29, 12, 0, tzinfo=UTC),
        )
        for d in w_dates
    ]

    accepted, _, _ = normalize_weather_batch(records)
    assert len(accepted) == 3
    assert accepted[0].weather_date == date(2026, 10, 29)
    assert accepted[1].weather_date == date(2026, 10, 30)
    assert accepted[2].weather_date == date(2026, 10, 31)
