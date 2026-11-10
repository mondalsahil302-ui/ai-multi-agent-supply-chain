
from copy import deepcopy
from datetime import date

import httpx
import pytest

from demand_ingestion.calendarific_client import (
    CalendarificAPIError,
    CalendarificClient,
    CalendarificHTTPError,
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
    assert records[0].provider_data["country"]["name"] == "India"
    assert records[1].description is None
    assert records[1].event_types == ["Observance"]


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


def test_empty_holiday_response_is_valid_and_metadata_marks_unavailable():
    payload = valid_payload()
    payload["response"]["holidays"] = []

    def handler(request):
        return httpx.Response(201, json=payload)

    settings = make_settings()
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        result = CalendarificClient(
            settings=settings,
            http_client=http_client,
        ).fetch_holidays_result(year=2026)

    assert result.records == []
    assert result.metadata.request_status == "success"
    assert result.metadata.response_status == 201
    assert result.metadata.data_available is False
    assert result.metadata.requested_year == 2026


def test_duplicate_festival_records_are_returned_once():
    payload = valid_payload()
    payload["response"]["holidays"].append(
        deepcopy(payload["response"]["holidays"][0])
    )

    def handler(request):
        return httpx.Response(200, json=payload)

    records = fetch_with_handler(handler)

    assert len(records) == 2
    assert len({record.event_key for record in records}) == 2


def test_default_region_uses_configured_region_and_captures_metadata():
    def handler(request):
        assert request.url.params["country"] == "IN"
        assert request.url.params["location"] == "in-wb"
        return httpx.Response(200, json=valid_payload())

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        result = CalendarificClient(
            settings=make_settings(),
            http_client=http_client,
        ).fetch_default_region_holidays_result(year=2026)

    assert result.metadata.region_id == "IN-WB"
    assert result.metadata.data_available is True


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


def test_api_key_is_redacted_from_provider_errors_and_metadata():
    secret = "sensitive-test-token"

    def handler(request):
        return httpx.Response(
            401,
            json={
                "meta": {
                    "error_type": "invalid_key",
                    "error_detail": f"Rejected {secret}",
                }
            },
        )

    settings = make_settings(calendarific_api_key=secret)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = CalendarificClient(settings=settings, http_client=http_client)
        with pytest.raises(CalendarificAPIError) as error:
            client.fetch_holidays_result(year=2026)

    assert secret not in str(error.value)
    assert error.value.response_status == 401
    assert error.value.source_metadata.response_status == 401
    assert secret not in error.value.source_metadata.error_details


def test_network_timeout_is_reported_without_api_key():
    def handler(request):
        raise httpx.ReadTimeout("request timed out", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = CalendarificClient(
            settings=make_settings(http_max_retries=0),
            http_client=http_client,
        )
        with pytest.raises(CalendarificHTTPError, match="request failed") as error:
            client.fetch_holidays(year=2026)

    assert "test-api-key" not in str(error.value)


def test_quota_failure_retries_a_bounded_number_of_times():
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

    assert attempts == 4


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
