from datetime import date

import httpx
import pytest

from demand_ingestion.config import Settings
from demand_ingestion.open_meteo_client import (
    OpenMeteoClient,
    OpenMeteoHTTPError,
    OpenMeteoResponseError,
)


def make_settings(**overrides):
    values = {
        "_env_file": None,
        "app_env": "test",
        "open_meteo_archive_url": "https://weather.test/v1/archive",
        "http_max_retries": 0,
        "http_backoff_max_seconds": 0.01,
    }
    values.update(overrides)
    return Settings(**values)


def valid_payload():
    """Return a simulated Open-Meteo response with complete metadata."""
    return {
        "timezone": "Asia/Kolkata",
        "daily_units": {
            "weather_code": "wmo code",
            "temperature_2m_mean": "°C",
            "temperature_2m_min": "°C",
            "temperature_2m_max": "°C",
            "precipitation_sum": "mm",
            "relative_humidity_2m_mean": "%",
        },
        "daily": {
            "time": ["2026-10-27", "2026-10-28"],
            "weather_code": [61, 3],
            "temperature_2m_mean": [25.2, 26.0],
            "temperature_2m_min": [22.0, 23.0],
            "temperature_2m_max": [29.0, 30.0],
            "precipitation_sum": [4.5, 0.0],
            "relative_humidity_2m_mean": [78.0, 70.0],
        },
    }


def fetch_with_handler(
    handler,
    *,
    settings=None,
    start_date=date(2026, 10, 27),
    end_date=date(2026, 10, 28),
):
    """Run a request through a mocked HTTP transport."""
    config = settings or make_settings()

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as http_client:
        client = OpenMeteoClient(
            settings=config,
            http_client=http_client,
        )

        return client.fetch_historical_daily(
            location_id="LG_KOLKATA_001",
            latitude=22.5726,
            longitude=88.3639,
            start_date=start_date,
            end_date=end_date,
        )


def test_successful_response_produces_weather_records():
    def handler(request):
        assert request.url.host == "weather.test"
        assert request.url.path == "/v1/archive"

        assert request.url.params["start_date"] == "2026-10-27"
        assert request.url.params["end_date"] == "2026-10-28"
        assert request.url.params["timezone"] == "Asia/Kolkata"

        assert request.url.params["temperature_unit"] == "celsius"
        assert request.url.params["precipitation_unit"] == "mm"
        assert request.url.params["timeformat"] == "iso8601"

        assert (
            request.url.params["daily"]
            == ",".join(OpenMeteoClient.DAILY_VARIABLES)
        )

        return httpx.Response(200, json=valid_payload())

    records = fetch_with_handler(handler)

    assert len(records) == 2
    assert records[0].weather_date == date(2026, 10, 27)
    assert records[0].temperature_mean_c == 25.2
    assert records[0].rainfall_mm == 4.5
    assert records[0].humidity_mean_pct == 78.0
    assert records[0].location_id == "LG_KOLKATA_001"
    assert records[0].data_kind == "historical"
    assert records[1].weather_date == date(2026, 10, 28)


def test_missing_daily_object_is_rejected():
    def handler(request):
        return httpx.Response(200, json={})

    with pytest.raises(
        OpenMeteoResponseError,
        match="daily data object",
    ):
        fetch_with_handler(handler)


def test_mismatched_array_lengths_are_rejected():
    payload = valid_payload()
    payload["daily"]["temperature_2m_mean"] = [25.2]

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        OpenMeteoResponseError,
        match="Array length mismatch",
    ):
        fetch_with_handler(handler)


def test_invalid_json_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )

    with pytest.raises(
        OpenMeteoResponseError,
        match="invalid JSON",
    ):
        fetch_with_handler(handler)


def test_provider_error_envelope_is_rejected():
    def handler(request):
        return httpx.Response(
            200,
            json={
                "error": True,
                "reason": "Invalid request parameters",
            },
        )

    with pytest.raises(
        OpenMeteoResponseError,
        match="Invalid request parameters",
    ):
        fetch_with_handler(handler)


def test_permanent_http_error_is_reported():
    def handler(request):
        return httpx.Response(400, json={"error": "Bad request"})

    with pytest.raises(
        OpenMeteoHTTPError,
        match="400",
    ):
        fetch_with_handler(handler)


def test_invalid_humidity_is_rejected():
    payload = valid_payload()
    payload["daily"]["relative_humidity_2m_mean"][0] = 120.0

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        OpenMeteoResponseError,
        match="Invalid weather measurements",
    ):
        fetch_with_handler(handler)


def test_temporary_http_error_is_retried():
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


def test_reversed_date_range_is_rejected():
    def handler(request):
        pytest.fail("No HTTP request should be made")

    with pytest.raises(
        ValueError,
        match="start_date cannot be after end_date",
    ):
        fetch_with_handler(
            handler,
            start_date=date(2026, 10, 28),
            end_date=date(2026, 10, 27),
        )
def test_incorrect_timezone_is_rejected():
    payload = valid_payload()
    payload["timezone"] = "UTC"

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        OpenMeteoResponseError,
        match="timezone does not match",
    ):
        fetch_with_handler(handler)


def test_incorrect_temperature_unit_is_rejected():
    payload = valid_payload()
    payload["daily_units"]["temperature_2m_mean"] = "°F"

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        OpenMeteoResponseError,
        match="Unexpected unit",
    ):
        fetch_with_handler(handler)


def test_missing_requested_date_is_rejected():
    payload = valid_payload()
    payload["daily"]["time"] = ["2026-10-27"]

    def handler(request):
        return httpx.Response(200, json=payload)

    with pytest.raises(
        OpenMeteoResponseError,
        match="Returned dates do not exactly match",
    ):
        fetch_with_handler(handler)