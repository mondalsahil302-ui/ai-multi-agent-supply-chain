from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from demand_ingestion.festival_models import FestivalRecord


def make_valid_record(**overrides):
    data = {
        "country_code": "IN",
        "event_name": "Durga Puja",
        "event_date": date(2026, 10, 19),
        "description": "Festival celebrated in West Bengal",
        "event_types": ["Religious", "Festival"],
        "primary_type": "Festival",
        "locations": "West Bengal",
        "states": "West Bengal",
        "canonical_url": None,
        "retrieved_at_utc": datetime(
            2026, 10, 29, 10, 0, tzinfo=UTC
        ),
    }
    data.update(overrides)
    return FestivalRecord(**data)


def test_valid_festival_record():
    record = make_valid_record()

    assert record.country_code == "IN"
    assert record.event_name == "Durga Puja"
    assert record.event_date == date(2026, 10, 19)
    assert record.source == "calendarific"
    assert len(record.event_key) == 64


def test_country_code_is_normalized():
    record = make_valid_record(country_code=" in ")

    assert record.country_code == "IN"


def test_invalid_country_code_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(country_code="IND")


def test_blank_event_name_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(event_name="   ")


def test_invalid_event_date_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(event_date="not-a-date")


def test_naive_retrieval_timestamp_is_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(
            retrieved_at_utc=datetime(2026, 10, 29, 10, 0)
        )


def test_retrieval_timestamp_is_normalized_to_utc():
    record = make_valid_record()

    assert record.retrieved_at_utc.tzinfo == UTC


def test_event_key_is_deterministic():
    first = make_valid_record()
    second = make_valid_record()

    assert first.event_key == second.event_key


def test_different_events_get_different_keys():
    first = make_valid_record(event_name="Durga Puja")
    second = make_valid_record(event_name="Kali Puja")

    assert first.event_key != second.event_key


def test_event_types_are_normalized_and_deduplicated():
    record = make_valid_record(
        event_types=["Festival", " Religious ", "Festival", ""]
    )

    assert record.event_types == ["Festival", "Religious"]


def test_unexpected_fields_are_rejected():
    with pytest.raises(ValidationError):
        make_valid_record(unexpected_field="invalid")
def test_same_canonical_url_different_years_get_different_keys():
    first = make_valid_record(
        event_name="New Year's Day",
        event_date=date(2026, 1, 1),
        canonical_url="https://calendarific.com/holiday/in/new-year",
    )

    second = make_valid_record(
        event_name="New Year's Day",
        event_date=date(2027, 1, 1),
        canonical_url="https://calendarific.com/holiday/in/new-year",
    )

    assert first.canonical_url == second.canonical_url
    assert first.event_key != second.event_key