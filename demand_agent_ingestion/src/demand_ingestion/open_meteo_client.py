from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from demand_ingestion.config import Settings, get_settings
from demand_ingestion.weather_models import WeatherDailyRecord


class OpenMeteoError(RuntimeError):
    """Base exception for Open-Meteo ingestion errors."""


class OpenMeteoResponseError(OpenMeteoError):
    """Raised when the provider returns an invalid response."""


class OpenMeteoHTTPError(OpenMeteoError):
    """Raised when an HTTP request fails permanently or exhausts retries."""


class OpenMeteoClient:
    """Fetch and validate historical daily weather from Open-Meteo."""

    DAILY_VARIABLES = (
        "weather_code",
        "temperature_2m_mean",
        "temperature_2m_min",
        "temperature_2m_max",
        "precipitation_sum",
        "relative_humidity_2m_mean",
    )

    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._owns_http_client = http_client is None

        if http_client is not None:
            self.http = http_client
        else:
            self.http = httpx.Client(
                timeout=self.settings.http_timeout_seconds,
                follow_redirects=False,
            )

    def close(self) -> None:
        """Close the HTTP client only when this instance owns it."""
        if self._owns_http_client:
            self.http.close()

    def __enter__(self) -> "OpenMeteoClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def fetch_historical_daily(
        self,
        *,
        location_id: str,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        timezone: str = "Asia/Kolkata",
    ) -> list[WeatherDailyRecord]:
        """Fetch daily historical weather for one configured location."""

        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")

        if not location_id.strip():
            raise ValueError("location_id cannot be blank")

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "daily": ",".join(self.DAILY_VARIABLES),
            "timezone": timezone,
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
            "timeformat": "iso8601",
        }

        payload = self._request_json(
            self.settings.open_meteo_archive_url,
            params,
        )

        return self._parse_daily_response(
            payload=payload,
            location_id=location_id,
            latitude=latitude,
            longitude=longitude,
            expected_timezone=timezone,
            expected_start_date=start_date,
            expected_end_date=end_date,
        )

    def _request_json(
        self,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Make a bounded-retry request and validate the JSON envelope."""

        retryable = retry_if_exception(
            lambda exc: (
                isinstance(exc, httpx.RequestError)
                or (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code
                    in self.RETRYABLE_STATUS_CODES
                )
            )
        )

        retryer = Retrying(
            stop=stop_after_attempt(
                self.settings.http_max_retries + 1
            ),
            wait=wait_exponential(
                multiplier=1,
                max=self.settings.http_backoff_max_seconds,
            ),
            retry=retryable,
            reraise=True,
        )

        try:
            return retryer(self._perform_request, url, params)

        except httpx.HTTPStatusError as exc:
            raise OpenMeteoHTTPError(
                f"Open-Meteo returned HTTP "
                f"{exc.response.status_code} after retry handling."
            ) from exc

        except httpx.RequestError as exc:
            raise OpenMeteoHTTPError(
                "Open-Meteo request failed after retry handling."
            ) from exc

    def _perform_request(
        self,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Perform one HTTP attempt."""

        response = self.http.get(url, params=params)

        if response.status_code in self.RETRYABLE_STATUS_CODES:
            response.raise_for_status()

        if response.is_error:
            raise OpenMeteoHTTPError(
                f"Open-Meteo returned permanent HTTP "
                f"error {response.status_code}."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenMeteoResponseError(
                "Open-Meteo returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise OpenMeteoResponseError(
                "Open-Meteo response must be a JSON object."
            )

        if payload.get("error") is True:
            raise OpenMeteoResponseError(
                "Open-Meteo reported an API error: "
                f"{payload.get('reason', 'reason not provided')}"
            )

        return payload

    def _parse_daily_response(
        self,
        *,
        payload: dict[str, Any],
        location_id: str,
        latitude: float,
        longitude: float,
        expected_timezone: str,
        expected_start_date: date,
        expected_end_date: date,
    ) -> list[WeatherDailyRecord]:
        """Validate metadata and measurements, then normalize records."""

        # Validate the top-level daily data object.
        daily = payload.get("daily")

        if not isinstance(daily, dict):
            raise OpenMeteoResponseError(
                "Response is missing the daily data object."
            )

        # Validate daily dates.
        dates = daily.get("time")

        if not isinstance(dates, list):
            raise OpenMeteoResponseError(
                "Daily response is missing the time array."
            )

        if not dates:
            raise OpenMeteoResponseError(
                "Daily response contains no weather dates."
            )

        parsed_dates: list[date] = []

        for date_value in dates:
            if not isinstance(date_value, str):
                raise OpenMeteoResponseError(
                    "Daily response contains a non-string date."
                )

            try:
                parsed_dates.append(date.fromisoformat(date_value))
            except ValueError as exc:
                raise OpenMeteoResponseError(
                    "Daily response contains an invalid date."
                ) from exc

        # Verify that the provider returned every requested date,
        # in chronological order, without missing or extra dates.
        expected_dates: list[date] = []
        current_date = expected_start_date

        while current_date <= expected_end_date:
            expected_dates.append(current_date)
            current_date += timedelta(days=1)

        if parsed_dates != expected_dates:
            raise OpenMeteoResponseError(
                "Returned dates do not exactly match "
                "the requested date range."
            )

        # Validate the timezone returned by the provider.
        returned_timezone = payload.get("timezone")

        if returned_timezone != expected_timezone:
            raise OpenMeteoResponseError(
                "Response timezone does not match "
                "the requested timezone."
            )

        # Validate units before interpreting numeric measurements.
        daily_units = payload.get("daily_units")

        if not isinstance(daily_units, dict):
            raise OpenMeteoResponseError(
                "Response is missing daily_units metadata."
            )

        expected_units = {
            "weather_code": "wmo code",
            "temperature_2m_mean": "°c",
            "temperature_2m_min": "°c",
            "temperature_2m_max": "°c",
            "precipitation_sum": "mm",
            "relative_humidity_2m_mean": "%",
        }

        for variable, expected_unit in expected_units.items():
            actual_unit = daily_units.get(variable)

            if (
                not isinstance(actual_unit, str)
                or actual_unit.strip().casefold() != expected_unit
            ):
                raise OpenMeteoResponseError(
                    f"Unexpected unit for {variable}: "
                    f"{actual_unit!r}."
                )

        # Validate that every requested variable has a matching array.
        for variable in self.DAILY_VARIABLES:
            values = daily.get(variable)

            if not isinstance(values, list):
                raise OpenMeteoResponseError(
                    f"Daily response is missing {variable}."
                )

            if len(values) != len(parsed_dates):
                raise OpenMeteoResponseError(
                    f"Array length mismatch for {variable}."
                )

        # Normalize the provider response into application records.
        retrieved_at = datetime.now(UTC)
        records: list[WeatherDailyRecord] = []

        for index, weather_date in enumerate(parsed_dates):
            try:
                record = WeatherDailyRecord(
                    location_id=location_id,
                    latitude=latitude,
                    longitude=longitude,
                    weather_date=weather_date,
                    data_kind="historical",
                    temperature_mean_c=daily[
                        "temperature_2m_mean"
                    ][index],
                    temperature_min_c=daily[
                        "temperature_2m_min"
                    ][index],
                    temperature_max_c=daily[
                        "temperature_2m_max"
                    ][index],
                    rainfall_mm=daily[
                        "precipitation_sum"
                    ][index],
                    humidity_mean_pct=daily[
                        "relative_humidity_2m_mean"
                    ][index],
                    weather_code=daily["weather_code"][index],
                    retrieved_at_utc=retrieved_at,
                )

            except (TypeError, ValueError) as exc:
                raise OpenMeteoResponseError(
                    f"Invalid weather measurements for "
                    f"{weather_date}."
                ) from exc

            records.append(record)

        return records