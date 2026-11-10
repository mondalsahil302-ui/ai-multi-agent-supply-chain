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
            "rain_sum": "mm",
            "relative_humidity_2m_mean": "%",
            "wind_speed_10m_mean": "km/h",
        },
        "daily": {
            "time": ["2026-10-27", "2026-10-28"],
            "weather_code": [61, 3],
            "temperature_2m_mean": [25.2, 26.0],
            "temperature_2m_min": [22.0, 23.0],
            "temperature_2m_max": [29.0, 30.0],
            "precipitation_sum": [4.5, 0.0],
            "rain_sum": [4.0, 0.0],
            "relative_humidity_2m_mean": [78.0, 70.0],
            "wind_speed_10m_mean": [12.0, 15.0],
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
    assert records[0].precipitation_mm == 4.5
    assert records[0].rainfall_mm == 4.0
    assert records[0].humidity_mean_pct == 78.0
    assert records[0].wind_speed_mean_kmh == 12.0
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


def test_missing_weather_variables_are_returned_as_none():
    payload = valid_payload()
    payload["daily"].pop("relative_humidity_2m_mean")
    payload["daily"].pop("wind_speed_10m_mean")
    payload["daily_units"].pop("relative_humidity_2m_mean")
    payload["daily_units"].pop("wind_speed_10m_mean")

    def handler(request):
        return httpx.Response(200, json=payload)

    records = fetch_with_handler(handler)

    assert records[0].humidity_mean_pct is None
    assert records[0].wind_speed_mean_kmh is None
    assert records[0].rainfall_mm == 4.0


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [(91.0, 0.0), (0.0, 181.0), (float("nan"), 0.0)],
)
def test_invalid_coordinates_are_rejected_before_request(latitude, longitude):
    def handler(request):
        pytest.fail("Invalid coordinates must not trigger a request")

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OpenMeteoClient(
            settings=make_settings(),
            http_client=http_client,
        )
        with pytest.raises(ValueError, match="latitude|longitude"):
            client.fetch_historical_daily(
                location_id="LG_KOLKATA_001",
                latitude=latitude,
                longitude=longitude,
                start_date=date(2026, 10, 27),
                end_date=date(2026, 10, 27),
            )


def test_request_timeout_is_reported():
    def handler(request):
        raise httpx.ReadTimeout("request timed out", request=request)

    settings = make_settings(http_max_retries=0)
    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OpenMeteoClient(settings=settings, http_client=http_client)
        with pytest.raises(OpenMeteoHTTPError, match="request failed"):
            client.fetch_historical_daily(
                location_id="LG_KOLKATA_001",
                latitude=22.5,
                longitude=88.3,
                start_date=date(2026, 10, 27),
                end_date=date(2026, 10, 27),
            )


def test_successful_forecast_includes_requested_horizon_and_metadata():
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    payload = valid_payload()
    payload["daily"]["time"] = [
        (today + timedelta(days=offset)).isoformat()
        for offset in range(2)
    ]

    def handler(request):
        assert request.url.path == "/v1/forecast"
        assert request.url.params["forecast_days"] == "2"
        assert request.url.params["timezone"] == "Asia/Kolkata"
        assert request.url.params["wind_speed_unit"] == "kmh"
        return httpx.Response(201, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http_client:
        client = OpenMeteoClient(
            settings=make_settings(
                open_meteo_base_url="https://weather.test/v1/forecast"
            ),
            http_client=http_client,
        )
        result = client.fetch_forecast_daily_result(
            location_id="KOL-LOC-001",
            latitude=22.5,
            longitude=88.3,
            forecast_days=2,
        )

    assert len(result.records) == 2
    assert result.records[0].data_kind == "forecast"
    assert result.metadata.source_name == "open_meteo"
    assert result.metadata.request_status == "success"
    assert result.metadata.response_status == 201
    assert result.metadata.region_id == "KOL-LOC-001"


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