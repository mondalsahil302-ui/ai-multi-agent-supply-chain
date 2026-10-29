
from datetime import date

import httpx
import pytest

from demand_ingestion.calendarific_client import (
    CalendarificAPIError,
    CalendarificClient,
    CalendarificResponseError,
)
from demand_ingestion.config import Settings


def make_settings(**overrides):
    values = {
        "_env_file": None,
        "app_env": "test",
        "calendarific_base_url": (
            "https://calendarific.test/api/v2/holidays"
        ),
        "calendarific_api_key": "test-api-key",
        "http_max_retries": 0,
        "http_backoff_max_seconds": 0.01,
    }
    values.update(overrides)
    return Settings(**values)


def valid_payload():
    return {
        "meta": {
            "code": 200,
            "error_type": None,
            "error_detail": None,
        },
        "response": {
            "holidays": [
                {
                    "name": "New Year's Day",
                    "description": "First day of the calendar year",
                    "country": {
                        "id": "IN",
                        "name": "India",
                    },
                    "date": {
                        "iso": "2026-01-01",
                    },
                    "type": ["National holiday"],
                    "primary_type": "National holiday",
                    "locations": "All",
                    "states": "All",
                    "canonical_url": (
                        "https://calendarific.test/holiday/in/new-year"
                    ),
                },
                {
                    "name": "Kali Puja",
                    "country": {
                        "id": "IN",
                        "name": "India",
                    },
                    "date": {
                        "iso": "2026-10-29",
                    },
                    "type": ["Observance"],
                },
            ]
        },
    }


def fetch_with_handler(
    handler,
    *,
    settings=None,
    country_code="in",
    year=2026,
    location=None,
):
    """Run a Calendarific request against a mocked HTTP transport."""
    config = settings or make_settings()

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as http_client:
        client = CalendarificClient(
            settings=config,
            http_client=http_client,
        )

        return client.fetch_holidays(
            country_code=country_code,
            year=year,
            location=location,
        )


def test_successful_response_produces_festival_records():
    def handler(request):
        assert request.url.host == "calendarific.test"
        assert request.url.path == "/api/v2/holidays"
        assert request.url.params["api_key"] == "test-api-key"
        assert request.url.params["country"] == "IN"
        assert request.url.params["year"] == "2026"

        return httpx.Response(200, json=valid_payload())

    records = fetch_with_handler(handler)

    assert len(records) == 2
    assert records[0].event_name == "New Year's Day"
    assert records[0].country_code == "IN"
    assert records[0].event_date == date(2026, 1, 1)
    assert records[0].source == "calendarific"
    assert records[1].event_name == "Kali Puja"
    assert len(records[0].event_key) == 64


def test_country_code_is_normalized():
    def handler(request):
        assert request.url.params["country"] == "IN"
        return httpx.Response(200, json=valid_payload())

    records = fetch_with_handler(handler, country_code=" in ")

    assert all(record.country_code == "IN" for record in records)


def test_invalid_country_code_is_rejected_before_request():
    def handler(request):
        pytest.fail("Invalid country code must not trigger a request")

    with pytest.raises(ValueError, match="two-letter"):
        fetch_with_handler(handler, country_code="IND")


def test_invalid_year_is_rejected_before_request():
    def handler(request):
        pytest.fail("Invalid year must not trigger a request")

    with pytest.raises(ValueError, match="between 1 and 9999"):
        fetch_with_handler(handler, year=0)


def test_boolean_year_is_rejected():
    def handler(request):
        pytest.fail("Boolean year must not trigger a request")

    with pytest.raises(ValueError, match="year must be an integer"):
        fetch_with_handler(handler, year=True)


def test_missing_api_key_is_rejected_before_request():
    def handler(request):
        pytest.fail("Missing API key must not trigger a request")

    settings = make_settings(calendarific_api_key=None)

    with pytest.raises(
        CalendarificAPIError,
        match="API key is not configured",
    ):
        fetch_with_handler(handler, settings=settings)


def test_invalid_json_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            content=b"{invalid-json",
            headers={"Content-Type": "application/json"},
        )

    with pytest.raises(
        CalendarificResponseError,
        match="invalid JSON",
    ):
        fetch_with_handler(handler)


def test_missing_metadata_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={"response": {"holidays": []}},
        )

    with pytest.raises(
        CalendarificResponseError,
        match="meta object",
    ):
        fetch_with_handler(handler)


def test_missing_holidays_array_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "meta": {"code": 200},
                "response": {},
            },
        )

    with pytest.raises(
        CalendarificResponseError,
        match="holidays array",
    ):
        fetch_with_handler(handler)


def test_invalid_event_date_is_rejected():
    payload = valid_payload()
    payload["response"]["holidays"][0]["date"]["iso"] = (
        "2026-99-99"
    )

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        CalendarificResponseError,
        match="invalid date",
    ):
        fetch_with_handler(handler)


def test_wrong_country_in_event_is_rejected():
    payload = valid_payload()
    payload["response"]["holidays"][0]["country"]["id"] = "US"

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        CalendarificResponseError,
        match="country-code mismatch",
    ):
        fetch_with_handler(handler)


def test_event_outside_requested_year_is_rejected():
    payload = valid_payload()
    payload["response"]["holidays"][0]["date"]["iso"] = (
        "2027-01-01"
    )

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        CalendarificResponseError,
        match="outside requested year",
    ):
        fetch_with_handler(handler)


def test_authentication_failure_is_not_retried():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1

        return httpx.Response(
            401,
            json={
                "meta": {
                    "error_type": "invalid_key",
                    "error_detail": "Invalid test key",
                }
            },
        )

    settings = make_settings(http_max_retries=3)

    with pytest.raises(
        CalendarificAPIError,
        match="Authentication",
    ):
        fetch_with_handler(handler, settings=settings)

    assert attempts == 1


def test_quota_failure_is_not_retried():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, json={})

    settings = make_settings(http_max_retries=3)

    with pytest.raises(
        CalendarificAPIError,
        match="quota",
    ):
        fetch_with_handler(handler, settings=settings)

    assert attempts == 1


def test_temporary_server_error_is_retried():
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1

        if attempts == 1:
            return httpx.Response(503)

        return httpx.Response(200, json=valid_payload())

    settings = make_settings(
        http_max_retries=1,
        http_backoff_max_seconds=0.01,
    )

    records = fetch_with_handler(
        handler,
        settings=settings,
    )

    assert attempts == 2
    assert len(records) == 2


def test_provider_error_envelope_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "meta": {
                    "code": 400,
                    "error_type": "bad_request",
                    "error_detail": "Invalid parameters",
                }
            },
        )

    with pytest.raises(
        CalendarificAPIError,
        match="Invalid parameters",
    ):
        fetch_with_handler(handler)
