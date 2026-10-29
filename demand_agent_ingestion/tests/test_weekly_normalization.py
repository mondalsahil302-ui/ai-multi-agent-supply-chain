"""Tests for weekly weather aggregations and weekly festival projections."""

from datetime import UTC, date, datetime

import pytest

from demand_ingestion.festival_models import FestivalRecord
from demand_ingestion.normalization.common import (
    CalendarRegistry,
    CalendarWeekRecord,
)
from demand_ingestion.normalization.festivals import normalize_festival_record
from demand_ingestion.normalization.weather import (
    NormalizedWeatherRecord,
    compute_weather_record_id,
)
from demand_ingestion.normalization.weekly import (
    aggregate_weekly_weather,
    project_festivals_to_weeks,
)


@pytest.fixture
def sample_calendar_registry():
    # 2024-01-07 (Sunday) to 2024-01-13 (Saturday) -> W002
    return CalendarRegistry(
        [
            CalendarWeekRecord(
                week_id="W002",
                week_start_date=date(2024, 1, 7),
                week_end_date=date(2024, 1, 13),
                year=2024,
                week_number=2,
            )
        ]
    )


def _create_daily_weather(
    w_date: date,
    temp_mean: float,
    temp_min: float,
    temp_max: float,
    rain: float,
    humidity: float,
    code: int,
    data_kind: str = "historical",
    snapshot_id: str | None = None,
    location_id: str = "KOL-LOC-001",
) -> NormalizedWeatherRecord:
    rec_id = compute_weather_record_id(location_id, w_date, data_kind, snapshot_id)
    return NormalizedWeatherRecord(
        record_id=rec_id,
        location_id=location_id,
        latitude=22.5014,
        longitude=88.3617,
        weather_date=w_date,
        data_kind=data_kind,
        forecast_snapshot_id=snapshot_id,
        temperature_mean_c=temp_mean,
        temperature_min_c=temp_min,
        temperature_max_c=temp_max,
        rainfall_mm=rain,
        humidity_mean_pct=humidity,
        weather_code=code,
        coverage_hours=24,
        source="open_meteo",
        retrieved_at_utc=datetime(2024, 1, 14, 0, 0, tzinfo=UTC),
    )


def test_weekly_weather_aggregation_math_and_coverage(sample_calendar_registry):
    # Full week 2024-01-07 to 2024-01-13 (Sunday to Saturday)
    days = [
        # date, mean, min, max, rain, hum, code
        (date(2024, 1, 7), 20.0, 15.0, 25.0, 0.0, 60.0, 0),
        (date(2024, 1, 8), 22.0, 16.0, 26.0, 5.0, 65.0, 61),
        (date(2024, 1, 9), 21.0, 14.0, 24.0, 2.5, 70.0, 61),
        (date(2024, 1, 10), 19.0, 13.0, 23.0, 0.0, 55.0, 1),
        (date(2024, 1, 11), 23.0, 17.0, 28.0, 10.0, 80.0, 61),
        (date(2024, 1, 12), 24.0, 18.0, 29.0, 1.0, 75.0, 2),
        (date(2024, 1, 13), 25.0, 19.0, 30.0, 0.0, 65.0, 0),
    ]
    records = [
        _create_daily_weather(d, mean_t, min_t, max_t, rain, hum, code)
        for d, mean_t, min_t, max_t, rain, hum, code in days
    ]

    summaries = aggregate_weekly_weather(
        records, calendar_registry=sample_calendar_registry
    )

    assert len(summaries) == 1
    s = summaries[0]
    assert s.location_id == "KOL-LOC-001"
    assert s.period_start_date == date(2024, 1, 7)
    assert s.period_end_date == date(2024, 1, 13)
    assert s.week_id == "W002"
    assert s.data_kind == "historical"

    # Math validations:
    # Means: [20, 22, 21, 19, 23, 24, 25] -> sum = 154 / 7 = 22.0
    assert s.temperature_mean_c == 22.0
    # Min of mins: [15, 16, 14, 13, 17, 18, 19] -> 13.0
    assert s.temperature_min_c == 13.0
    # Max of maxs: [25, 26, 24, 23, 28, 29, 30] -> 30.0
    assert s.temperature_max_c == 30.0
    # Total rain: 0 + 5.0 + 2.5 + 0 + 10.0 + 1.0 + 0 = 18.5
    assert s.rainfall_total_mm == 18.5
    # Humidity mean: [60, 65, 70, 55, 80, 75, 65] -> 470 / 7 = 67.14
    assert s.humidity_mean_pct == 67.14
    # Weather code frequency distribution (never averaged)
    assert s.weather_code_counts == {0: 2, 61: 3, 1: 1, 2: 1}

    # Coverage validations:
    assert s.expected_days == 7
    assert s.observed_days == 7
    assert s.missing_days == 0
    assert s.is_complete_week is True
    assert s.missing_dates == []
    assert len(s.daily_record_ids) == 7


def test_weekly_weather_missing_days_detected():
    # Only 4 days observed in the week of 2024-01-07
    days = [
        (date(2024, 1, 7), 20.0, 15.0, 25.0, 0.0, 60.0, 0),
        (date(2024, 1, 8), 22.0, 16.0, 26.0, 5.0, 65.0, 61),
        (date(2024, 1, 11), 23.0, 17.0, 28.0, 10.0, 80.0, 61),
        (date(2024, 1, 13), 25.0, 19.0, 30.0, 0.0, 65.0, 0),
    ]
    records = [
        _create_daily_weather(d, mean_t, min_t, max_t, rain, hum, code)
        for d, mean_t, min_t, max_t, rain, hum, code in days
    ]

    summaries = aggregate_weekly_weather(records, calendar_registry=None)

    assert len(summaries) == 1
    s = summaries[0]
    assert s.week_id is None
    assert s.expected_days == 7
    assert s.observed_days == 4
    assert s.missing_days == 3
    assert s.is_complete_week is False
    assert s.missing_dates == [
        date(2024, 1, 9),
        date(2024, 1, 10),
        date(2024, 1, 12),
    ]


def test_separation_of_historical_and_forecast_snapshots():
    w_date = date(2024, 1, 8)
    # Historical record
    rec_hist = _create_daily_weather(
        w_date, 20.0, 15.0, 25.0, 0.0, 60.0, 0, data_kind="historical"
    )
    # Forecast snapshot 1
    rec_fc1 = _create_daily_weather(
        w_date,
        21.0,
        16.0,
        26.0,
        1.0,
        65.0,
        1,
        data_kind="forecast",
        snapshot_id="20240101T000000Z",
    )
    # Forecast snapshot 2
    rec_fc2 = _create_daily_weather(
        w_date,
        22.0,
        17.0,
        27.0,
        2.0,
        70.0,
        2,
        data_kind="forecast",
        snapshot_id="20240105T000000Z",
    )

    summaries = aggregate_weekly_weather([rec_hist, rec_fc1, rec_fc2])

    # Must produce 3 distinct weekly summaries
    assert len(summaries) == 3

    hist_sum = [s for s in summaries if s.data_kind == "historical"][0]
    fc1_sum = [
        s for s in summaries if s.forecast_snapshot_id == "20240101T000000Z"
    ][0]
    fc2_sum = [
        s for s in summaries if s.forecast_snapshot_id == "20240105T000000Z"
    ][0]

    assert hist_sum.temperature_mean_c == 20.0
    assert fc1_sum.temperature_mean_c == 21.0
    assert fc2_sum.temperature_mean_c == 22.0


def test_project_festivals_to_weeks(sample_calendar_registry):
    # Create two festival records falling in week W002 (2024-01-07 to 2024-01-13)
    raw1 = FestivalRecord(
        country_code="IN",
        event_name="Event One",
        event_date=date(2024, 1, 8),
        primary_type="Gazetted Holiday",
        locations="All",
        retrieved_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    )
    raw2 = FestivalRecord(
        country_code="IN",
        event_name="Event Two",
        event_date=date(2024, 1, 12),
        primary_type="Regional Festival",
        states="West Bengal",
        retrieved_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    )
    # Third event in next week
    raw3 = FestivalRecord(
        country_code="IN",
        event_name="Event Next Week",
        event_date=date(2024, 1, 15),
        retrieved_at_utc=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
    )

    norm1, _ = normalize_festival_record(raw1)
    norm2, _ = normalize_festival_record(raw2)
    norm3, _ = normalize_festival_record(raw3)

    projections = project_festivals_to_weeks(
        [norm1, norm2, norm3], calendar_registry=sample_calendar_registry
    )

    assert len(projections) == 2

    w002_proj = projections[0]
    assert w002_proj.period_start_date == date(2024, 1, 7)
    assert w002_proj.period_end_date == date(2024, 1, 13)
    assert w002_proj.week_id == "W002"
    assert w002_proj.total_events == 2
    assert len(w002_proj.events) == 2
    assert w002_proj.events[0].event_name == "Event One"
    assert w002_proj.events[0].regional_applicability == "national"
    assert w002_proj.events[1].event_name == "Event Two"
    assert w002_proj.events[1].regional_applicability == "regional"

    next_proj = projections[1]
    assert next_proj.period_start_date == date(2024, 1, 14)
    assert next_proj.period_end_date == date(2024, 1, 20)
    assert next_proj.week_id is None  # Not in sample registry
    assert next_proj.total_events == 1

