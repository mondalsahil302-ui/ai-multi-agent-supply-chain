
import re
from datetime import UTC, date, datetime
from typing import Any

import httpx
from tenacity import (
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from demand_ingestion.config import Settings, get_settings
from demand_ingestion.festival_models import FestivalRecord


class CalendarificError(RuntimeError):
    """Base exception for Calendarific ingestion errors."""


class CalendarificResponseError(CalendarificError):
    """Raised when Calendarific returns an invalid response."""


class CalendarificAPIError(CalendarificError):
    """Raised for provider errors that should not be retried."""


class CalendarificHTTPError(CalendarificError):
    """Raised when an HTTP request fails permanently or exhausts retries."""


class CalendarificClient:
    """Fetch, validate, and normalize Calendarific holiday data."""

    RETRYABLE_STATUS_CODES = {408, 500, 502, 503, 504}

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

    def __enter__(self) -> "CalendarificClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def fetch_holidays(
        self,
        *,
        country_code: str,
        year: int,
        location: str | None = None,
    ) -> list[FestivalRecord]:
        """
        Fetch holidays for one country and year.

        `location` is an optional Calendarific region code, such as
        an ISO 3166-2 code supported by the provider.
        """

        normalized_country = country_code.strip().upper()

        if not re.fullmatch(r"[A-Z]{2}", normalized_country):
            raise ValueError(
                "country_code must be a two-letter country code."
            )

        if isinstance(year, bool) or not isinstance(year, int):
            raise ValueError("year must be an integer.")

        if not 1 <= year <= 9999:
            raise ValueError("year must be between 1 and 9999.")

        api_key = self.settings.calendarific_api_key

        if api_key is None or not api_key.get_secret_value().strip():
            raise CalendarificAPIError(
                "Calendarific API key is not configured."
            )

        params: dict[str, Any] = {
            "api_key": api_key.get_secret_value(),
            "country": normalized_country,
            "year": year,
        }

        if location is not None:
            normalized_location = location.strip().lower()

            if not normalized_location:
                raise ValueError("location cannot be blank.")

            params["location"] = normalized_location

        payload = self._request_json(
            self.settings.calendarific_base_url,
            params,
        )

        return self._parse_response(
            payload=payload,
            country_code=normalized_country,
            year=year,
        )

    def _request_json(
        self,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Make a bounded-retry request without exposing credentials."""

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
            # Do not propagate the HTTPX exception, which may contain
            # the request URL and the API key query parameter.
            raise CalendarificHTTPError(
                f"Calendarific returned HTTP "
                f"{exc.response.status_code} after retry handling."
            ) from None

        except httpx.RequestError:
            raise CalendarificHTTPError(
                "Calendarific request failed after retry handling."
            ) from None

    def _perform_request(
        self,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Perform one request and classify provider errors."""

        response = self.http.get(url, params=params)

        # Retry only selected transient server/network conditions.
        # Authentication and quota errors must not be retried blindly.
        if response.status_code in self.RETRYABLE_STATUS_CODES:
            response.raise_for_status()

        if response.is_error:
            self._raise_provider_error(response)

        try:
            payload = response.json()
        except ValueError:
            raise CalendarificResponseError(
                "Calendarific returned invalid JSON."
            ) from None

        if not isinstance(payload, dict):
            raise CalendarificResponseError(
                "Calendarific response must be a JSON object."
            )

        # Calendarific may also describe errors in its JSON envelope.
        meta = payload.get("meta")

        if isinstance(meta, dict) and meta.get("code") != 200:
            error_type = str(
                meta.get("error_type", "provider_error")
            )
            detail = str(
                meta.get("error_detail", "No error detail provided.")
            )

            raise CalendarificAPIError(
                f"Calendarific API error ({error_type}): {detail}"
            )

        return payload

    @staticmethod
    def _raise_provider_error(response: httpx.Response) -> None:
        """Raise a sanitized error without including the request URL."""

        status = response.status_code

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        meta = (
            payload.get("meta", {})
            if isinstance(payload, dict)
            else {}
        )

        error_type = (
            meta.get("error_type")
            if isinstance(meta, dict)
            else None
        )

        detail = (
            meta.get("error_detail")
            if isinstance(meta, dict)
            else None
        )

        # HTTP 401, 403, and 429 are not retried:
        # invalid credentials, expired access, and exhausted quota
        # require configuration or account-level action.
        if status in {401, 403, 429}:
            message = {
                401: "Authentication or required parameters were rejected.",
                403: "Calendarific access is forbidden or the subscription expired.",
                429: "Calendarific request quota was exceeded.",
            }[status]

            if error_type:
                message += f" Error type: {error_type}."

            if detail:
                message += f" Provider detail: {detail}"

            raise CalendarificAPIError(message)

        raise CalendarificAPIError(
            f"Calendarific rejected the request with HTTP {status}."
        )

    def _parse_response(
        self,
        *,
        payload: dict[str, Any],
        country_code: str,
        year: int,
    ) -> list[FestivalRecord]:
        """Validate the response envelope and normalize each holiday."""

        meta = payload.get("meta")

        if not isinstance(meta, dict):
            raise CalendarificResponseError(
                "Response is missing the meta object."
            )

        if meta.get("code") != 200:
            raise CalendarificAPIError(
                "Calendarific response metadata does not indicate success."
            )

        response_data = payload.get("response")

        if not isinstance(response_data, dict):
            raise CalendarificResponseError(
                "Response is missing the response object."
            )

        holidays = response_data.get("holidays")

        if not isinstance(holidays, list):
            raise CalendarificResponseError(
                "Response is missing the holidays array."
            )

        retrieved_at = datetime.now(UTC)
        records: list[FestivalRecord] = []

        for index, holiday in enumerate(holidays):
            if not isinstance(holiday, dict):
                raise CalendarificResponseError(
                    f"Holiday at index {index} is not an object."
                )

            name = holiday.get("name")
            if not isinstance(name, str) or not name.strip():
                raise CalendarificResponseError(
                    f"Holiday at index {index} has an invalid name."
                )

            country = holiday.get("country")
            if not isinstance(country, dict):
                raise CalendarificResponseError(
                    f"Holiday at index {index} is missing country metadata."
                )

            returned_country = country.get("id")
            if (
                isinstance(returned_country, str)
                and returned_country.strip()
                and returned_country.strip().upper() != country_code
            ):
                raise CalendarificResponseError(
                    f"Holiday at index {index} has a country-code mismatch."
                )

            date_info = holiday.get("date")
            if not isinstance(date_info, dict):
                raise CalendarificResponseError(
                    f"Holiday at index {index} is missing date metadata."
                )

            iso_date = date_info.get("iso")
            if not isinstance(iso_date, str):
                raise CalendarificResponseError(
                    f"Holiday at index {index} is missing its ISO date."
                )

            try:
                event_date = date.fromisoformat(iso_date)
            except ValueError:
                raise CalendarificResponseError(
                    f"Holiday at index {index} contains an invalid date."
                ) from None

            if event_date.year != year:
                raise CalendarificResponseError(
                    f"Holiday at index {index} falls outside requested year {year}."
                )

            event_types = holiday.get("type", [])
            if (
                not isinstance(event_types, list)
                or any(not isinstance(item, str) for item in event_types)
            ):
                raise CalendarificResponseError(
                    f"Holiday at index {index} has invalid type metadata."
                )

            primary_type = holiday.get("primary_type")
            description = holiday.get("description")
            canonical_url = holiday.get("canonical_url")
            locations = holiday.get("locations")
            states = holiday.get("states")

            # Validate optional fields before constructing the model.
            optional_text = {
                "primary_type": primary_type,
                "description": description,
                "canonical_url": canonical_url,
                "locations": locations,
                "states": states,
            }

            for field_name, field_value in optional_text.items():
                if field_value is not None and not isinstance(
                    field_value, str
                ):
                    raise CalendarificResponseError(
                        f"Holiday at index {index} has invalid "
                        f"{field_name} metadata."
                    )

            try:
                record = FestivalRecord(
                    country_code=country_code,
                    event_name=name,
                    event_date=event_date,
                    description=description,
                    event_types=event_types,
                    primary_type=primary_type,
                    canonical_url=canonical_url,
                    locations=locations,
                    states=states,
                    retrieved_at_utc=retrieved_at,
                )
            except (TypeError, ValueError):
                raise CalendarificResponseError(
                    f"Holiday at index {index} failed record validation."
                ) from None

            records.append(record)

        return records
