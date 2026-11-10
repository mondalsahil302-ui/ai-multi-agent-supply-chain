import logging
import math
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from demand_ingestion.config import Settings, get_settings
from demand_ingestion.source_metadata import SourceMetadata, SourceResult
from demand_ingestion.weather_models import WeatherDailyRecord

logger = logging.getLogger(__name__)


class OpenMeteoError(RuntimeError):
    """Base exception for Open-Meteo ingestion errors."""

    def __init__(
        self,
        message: str,
        *,
        response_status: int | None = None,
    ) -> None:
        super().__init__(message)
        self.response_status = response_status
        self.source_metadata: SourceMetadata | None = None


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
        "rain_sum",
        "relative_humidity_2m_mean",
        "wind_speed_10m_mean",
    )

    RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
    MAX_FORECAST_DAYS = 16

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
        timezone: str | None = None,
    ) -> list[WeatherDailyRecord]:
        """Fetch daily historical weather for one configured location."""

        records, _ = self._fetch_historical_daily(
            location_id=location_id,
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
        )
        return records

    def _fetch_historical_daily(
        self,
        *,
        location_id: str,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        timezone: str | None,
    ) -> tuple[list[WeatherDailyRecord], int]:
        """Fetch historical records and the exact HTTP response status."""

        timezone = timezone or self.settings.default_timezone
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date")

        if not location_id.strip():
            raise ValueError("location_id cannot be blank")

        self._validate_coordinates(latitude, longitude)
        self._validate_timezone(timezone)

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

        response_status: int | None = None
        try:
            payload, response_status = self._request_json(
                self.settings.open_meteo_archive_url,
                params,
            )
            records = self._parse_daily_response(
                payload=payload,
                location_id=location_id,
                latitude=latitude,
                longitude=longitude,
                expected_timezone=timezone,
                expected_start_date=start_date,
                expected_end_date=end_date,
                data_kind="historical",
            )
            return records, response_status
        except OpenMeteoError as exc:
            if exc.response_status is None:
                exc.response_status = response_status
            logger.warning(
                "Open-Meteo historical request failed for region %s (HTTP %s): %s",
                location_id,
                exc.response_status,
                str(exc),
            )
            raise

    def fetch_forecast_daily(
        self,
        *,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_days: int | None = None,
        timezone: str | None = None,
    ) -> list[WeatherDailyRecord]:
        """Fetch daily forecasts for one configured location."""

        records, _ = self._fetch_forecast_daily(
            location_id=location_id,
            latitude=latitude,
            longitude=longitude,
            forecast_days=forecast_days,
            timezone=timezone,
            forecast_start_date=None,
        )
        return records

    def _fetch_forecast_daily(
        self,
        *,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_days: int | None,
        timezone: str | None,
        forecast_start_date: date | None,
    ) -> tuple[list[WeatherDailyRecord], int]:
        """Fetch forecast records and the exact HTTP response status."""

        if not location_id.strip():
            raise ValueError("location_id cannot be blank")

        self._validate_coordinates(latitude, longitude)
        timezone = timezone or self.settings.default_timezone
        self._validate_timezone(timezone)
        forecast_days = (
            self.settings.default_forecast_days
            if forecast_days is None
            else forecast_days
        )
        if (
            isinstance(forecast_days, bool)
            or not isinstance(forecast_days, int)
            or not 1 <= forecast_days <= self.MAX_FORECAST_DAYS
        ):
            raise ValueError("forecast_days must be between 1 and 16")

        start_date = forecast_start_date or datetime.now(
            ZoneInfo(timezone)
        ).date()
        end_date = start_date + timedelta(days=forecast_days - 1)
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "daily": ",".join(self.DAILY_VARIABLES),
            "timezone": timezone,
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
            "wind_speed_unit": "kmh",
            "timeformat": "iso8601",
            "forecast_days": forecast_days,
        }

        response_status: int | None = None
        try:
            payload, response_status = self._request_json(
                self.settings.open_meteo_base_url,
                params,
            )
            records = self._parse_daily_response(
                payload=payload,
                location_id=location_id,
                latitude=latitude,
                longitude=longitude,
                expected_timezone=timezone,
                expected_start_date=start_date,
                expected_end_date=end_date,
                data_kind="forecast",
            )
            return records, response_status
        except OpenMeteoError as exc:
            if exc.response_status is None:
                exc.response_status = response_status
            logger.warning(
                "Open-Meteo forecast request failed for region %s (HTTP %s): %s",
                location_id,
                exc.response_status,
                str(exc),
            )
            raise

    def fetch_historical_daily_result(
        self,
        *,
        location_id: str,
        latitude: float,
        longitude: float,
        start_date: date,
        end_date: date,
        timezone: str | None = None,
    ) -> SourceResult[WeatherDailyRecord]:
        """Fetch validated historical observations with separate metadata."""

        timezone = timezone or self.settings.default_timezone
        try:
            records, response_status = self._fetch_historical_daily(
                location_id=location_id,
                latitude=latitude,
                longitude=longitude,
                start_date=start_date,
                end_date=end_date,
                timezone=timezone,
            )
        except OpenMeteoError as exc:
            exc.source_metadata = self._failure_metadata(
                exc,
                location_id=location_id,
                start_date=start_date,
                end_date=end_date,
            )
            raise

        return SourceResult[WeatherDailyRecord](
            records=records,
            metadata=SourceMetadata(
                source_name="open_meteo",
                retrieved_at_utc=datetime.now(UTC),
                requested_start_date=start_date,
                requested_end_date=end_date,
                region_id=location_id,
                request_status="success",
                response_status=response_status,
                data_available=bool(records),
            ),
        )

    def fetch_forecast_daily_result(
        self,
        *,
        location_id: str,
        latitude: float,
        longitude: float,
        forecast_days: int | None = None,
        timezone: str | None = None,
    ) -> SourceResult[WeatherDailyRecord]:
        """Fetch validated forecasts with separate request metadata."""

        timezone = timezone or self.settings.default_timezone
        forecast_days = (
            self.settings.default_forecast_days
            if forecast_days is None
            else forecast_days
        )
        self._validate_timezone(timezone)
        if (
            isinstance(forecast_days, bool)
            or not isinstance(forecast_days, int)
            or not 1 <= forecast_days <= self.MAX_FORECAST_DAYS
        ):
            raise ValueError("forecast_days must be between 1 and 16")
        request_start = datetime.now(ZoneInfo(timezone)).date()
        request_end = request_start + timedelta(days=forecast_days - 1)
        try:
            records, response_status = self._fetch_forecast_daily(
                location_id=location_id,
                latitude=latitude,
                longitude=longitude,
                forecast_days=forecast_days,
                timezone=timezone,
                forecast_start_date=request_start,
            )
        except OpenMeteoError as exc:
            exc.source_metadata = self._failure_metadata(
                exc,
                location_id=location_id,
                start_date=request_start,
                end_date=request_end,
            )
            raise

        return SourceResult[WeatherDailyRecord](
            records=records,
            metadata=SourceMetadata(
                source_name="open_meteo",
                retrieved_at_utc=datetime.now(UTC),
                requested_start_date=request_start,
                requested_end_date=request_end,
                region_id=location_id,
                request_status="success",
                response_status=response_status,
                data_available=bool(records),
            ),
        )

    @staticmethod
    def _validate_coordinates(latitude: float, longitude: float) -> None:
        if (
            isinstance(latitude, bool)
            or not isinstance(latitude, (int, float))
            or not math.isfinite(latitude)
            or not -90 <= latitude <= 90
        ):
            raise ValueError("latitude must be a finite value between -90 and 90")
        if (
            isinstance(longitude, bool)
            or not isinstance(longitude, (int, float))
            or not math.isfinite(longitude)
            or not -180 <= longitude <= 180
        ):
            raise ValueError("longitude must be a finite value between -180 and 180")

    @staticmethod
    def _validate_timezone(timezone: str) -> None:
        try:
            ZoneInfo(timezone)
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError("timezone must be a valid IANA timezone") from exc

    @staticmethod
    def _failure_metadata(
        error: OpenMeteoError,
        *,
        location_id: str,
        start_date: date,
        end_date: date,
    ) -> SourceMetadata:
        return SourceMetadata(
            source_name="open_meteo",
            retrieved_at_utc=datetime.now(UTC),
            requested_start_date=start_date,
            requested_end_date=end_date,
            region_id=location_id,
            request_status="failure",
            response_status=error.response_status,
            data_available=False,
            error_details=str(error),
        )

    def _request_json(
        self,
        url: str,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
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
                f"{exc.response.status_code} after retry handling.",
                response_status=exc.response.status_code,
            ) from exc

        except httpx.RequestError as exc:
            raise OpenMeteoHTTPError(
                "Open-Meteo request failed after retry handling."
            ) from exc

    def _perform_request(
        self,
        url: str,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        """Perform one HTTP attempt."""

        response = self.http.get(url, params=params)

        if response.status_code in self.RETRYABLE_STATUS_CODES:
            response.raise_for_status()

        if response.is_error:
            raise OpenMeteoHTTPError(
                f"Open-Meteo returned permanent HTTP "
                f"error {response.status_code}.",
                response_status=response.status_code,
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
                f"{payload.get('reason', 'reason not provided')}",
                response_status=response.status_code,
            )

        return payload, response.status_code

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
        data_kind: str,
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
            "rain_sum": "mm",
            "relative_humidity_2m_mean": "%",
            "wind_speed_10m_mean": "km/h",
        }

        for variable, expected_unit in expected_units.items():
            if variable not in daily:
                continue
            actual_unit = daily_units.get(variable)

            if (
                not isinstance(actual_unit, str)
                or actual_unit.strip().casefold() != expected_unit
            ):
                raise OpenMeteoResponseError(
                    f"Unexpected unit for {variable}: "
                    f"{actual_unit!r}."
                )

        # Missing variables are represented as null rather than blocking
        # otherwise usable weather observations.
        variable_values: dict[str, list[Any]] = {}
        for variable in self.DAILY_VARIABLES:
            values = daily.get(variable)

            if values is None:
                variable_values[variable] = [None] * len(parsed_dates)
                continue

            if not isinstance(values, list):
                raise OpenMeteoResponseError(
                    f"Daily response variable {variable} must be an array."
                )

            if len(values) != len(parsed_dates):
                raise OpenMeteoResponseError(
                    f"Array length mismatch for {variable}."
                )
            variable_values[variable] = values

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
                    data_kind=data_kind,
                    temperature_mean_c=variable_values[
                        "temperature_2m_mean"
                    ][index],
                    temperature_min_c=variable_values[
                        "temperature_2m_min"
                    ][index],
                    temperature_max_c=variable_values[
                        "temperature_2m_max"
                    ][index],
                    precipitation_mm=variable_values[
                        "precipitation_sum"
                    ][index],
                    rainfall_mm=variable_values["rain_sum"][index],
                    humidity_mean_pct=variable_values[
                        "relative_humidity_2m_mean"
                    ][index],
                    weather_code=variable_values["weather_code"][index],
                    wind_speed_mean_kmh=variable_values[
                        "wind_speed_10m_mean"
                    ][index],
                    retrieved_at_utc=retrieved_at,
                )

            except (TypeError, ValueError) as exc:
                if isinstance(exc, OpenMeteoError):
                    raise
                raise OpenMeteoResponseError(
                    f"Invalid weather measurements for "
                    f"{weather_date}.",
                    response_status=200,
                ) from exc

            records.append(record)

        return records