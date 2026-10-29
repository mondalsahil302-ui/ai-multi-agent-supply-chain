from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from demand_ingestion.weather_models import WeatherDailyRecord


def make_valid_record(**overrides):
    data = {
        "location_id": "LG_KOLKATA_001",
        "latitude": 22.5726,
        "longitude": 88.3639,
        "weather_date": date(2026, 10, 29),
        "data_kind": "historical",
        "temperature_mean_c": 28.0,
        "temperature_min_c": 25.0,
        "temperature_max_c": 32.0,
        "rainfall_mm": 4.5,
        "humidity_mean_pct": 75.0,
        "weather_code": 61,
        "retrieved_at_utc": datetime.now(UTC),
    }

    data.update(overrides)
    return WeatherDailyRecord(**data)


def test_valid_weather_record():
    record = make_valid_record()

    assert record.location_id == "LG_KOLKATA_001"
    assert record.temperature_mean_c == 28.0
    assert record.humidity_mean_pct == 75.0
    assert record.source == "open_meteo"


def test_humidity_above_100_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(humidity_mean_pct=120.0)


def test_negative_rainfall_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(rainfall_mm=-1.0)


def test_minimum_temperature_above_maximum_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(
            temperature_min_c=35.0,
            temperature_max_c=30.0,
        )


def test_mean_temperature_above_maximum_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(temperature_mean_c=36.0)


def test_timezone_naive_timestamp_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(
            retrieved_at_utc=datetime(2026, 10, 29, 10, 0, 0)
        )


def test_unexpected_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(unexpected_field="invalid")