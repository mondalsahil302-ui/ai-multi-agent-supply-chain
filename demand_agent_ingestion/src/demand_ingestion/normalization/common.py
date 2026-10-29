"""Common contracts, registries, sanitization, and batch reporting for normalization."""

import json
import re
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class QuarantineErrorCategory(StrEnum):
    """Stable, machine-readable quarantine error categories."""

    VALIDATION_ERROR = "VALIDATION_ERROR"
    CONFLICTING_DUPLICATE = "CONFLICTING_DUPLICATE"
    UNKNOWN_LOCATION = "UNKNOWN_LOCATION"
    LOCATION_COORDINATE_MISMATCH = "LOCATION_COORDINATE_MISMATCH"
    DATE_OUT_OF_RANGE = "DATE_OUT_OF_RANGE"
    MISSING_MEASUREMENT = "MISSING_MEASUREMENT"
    INVALID_MEASUREMENT = "INVALID_MEASUREMENT"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"


SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|password|token|secret|auth|bearer|credential|mongo_uri)"
)
REDACTED_MARKER = "[REDACTED]"


def sanitize_payload(payload: Any) -> Any:
    """Recursively scrub sensitive keys and credential patterns from payloads."""
    if isinstance(payload, dict):
        sanitized: dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(k, str) and SENSITIVE_KEY_PATTERN.search(k):
                sanitized[k] = REDACTED_MARKER
            else:
                sanitized[k] = sanitize_payload(v)
        return sanitized

    if isinstance(payload, list):
        return [sanitize_payload(item) for item in payload]

    if isinstance(payload, str):
        # Scrub inline key patterns like ?api_key=xyz or bearer xyz
        scrubbed = re.sub(
            r"(?i)(api[_-]?key|token|password|secret)=([^&\s]+)",
            r"\1=[REDACTED]",
            payload,
        )
        scrubbed = re.sub(
            r"(?i)(bearer\s+)([A-Za-z0-9_\-\.]+)",
            r"\1[REDACTED]",
            scrubbed,
        )
        return scrubbed

    return payload


def compute_payload_fingerprint(payload: Any) -> str:
    """Compute a deterministic SHA-256 fingerprint of sanitized payload."""
    clean = sanitize_payload(payload)
    serialized = json.dumps(clean, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


class BatchNormalizationReport(BaseModel):
    """Audited operational statistics and reconciliation report for a normalization batch."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
    )

    batch_id: str = Field(min_length=1, max_length=100)
    source_system: str = Field(min_length=1, max_length=100)
    record_type: str = Field(min_length=1, max_length=50)
    processed_at_utc: datetime

    input_records: int = Field(ge=0)
    accepted_records: int = Field(ge=0)
    rejected_records: int = Field(ge=0)
    identical_duplicates: int = Field(ge=0)
    conflicting_duplicates: int = Field(ge=0)
    validation_failures: int = Field(ge=0)

    @field_validator("processed_at_utc")
    @classmethod
    def validate_processed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("processed_at_utc must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def reconcile_counts(self) -> "BatchNormalizationReport":
        expected_total = (
            self.accepted_records
            + self.identical_duplicates
            + self.conflicting_duplicates
            + self.validation_failures
        )
        if self.input_records != expected_total:
            raise ValueError(
                f"Batch count reconciliation mismatch: input_records ({self.input_records}) "
                f"!= accepted ({self.accepted_records}) + identical_duplicates "
                f"({self.identical_duplicates}) + conflicting_duplicates "
                f"({self.conflicting_duplicates}) + validation_failures "
                f"({self.validation_failures}) [sum: {expected_total}]"
            )

        expected_rejected = self.conflicting_duplicates + self.validation_failures
        if self.rejected_records != expected_rejected:
            raise ValueError(
                f"Rejected count mismatch: rejected_records ({self.rejected_records}) "
                f"!= conflicting_duplicates ({self.conflicting_duplicates}) + "
                f"validation_failures ({self.validation_failures}) [sum: {expected_rejected}]"
            )

        return self


class LocationMetadata(BaseModel):
    """Authoritative location definition."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    location_id: str = Field(min_length=1, max_length=100)
    expected_latitude: float = Field(ge=-90.0, le=90.0)
    expected_longitude: float = Field(ge=-180.0, le=180.0)
    name: str | None = Field(default=None, max_length=200)
    city: str = Field(default="Kolkata", max_length=100)


class LocationRegistry:
    """Injected authoritative location mapping and geographic coordinate validator."""

    def __init__(self, locations: list[LocationMetadata] | None = None) -> None:
        self._locations: dict[str, LocationMetadata] = {}
        if locations:
            for loc in locations:
                self.register(loc)

    def register(self, location: LocationMetadata) -> None:
        """Register a canonical location."""
        self._locations[location.location_id] = location

    def get(self, location_id: str) -> LocationMetadata | None:
        """Retrieve registered metadata for a location."""
        return self._locations.get(location_id)

    def validate_location(
        self,
        location_id: str,
        latitude: float,
        longitude: float,
        tolerance_deg: float = 0.05,
        strict: bool = False,
    ) -> tuple[bool, str | None]:
        """
        Validate location presence and coordinate alignment within a tolerance.

        Returns (True, None) if valid.
        Returns (False, error_reason) if invalid.
        """
        registered = self._locations.get(location_id)
        if registered is None:
            if strict:
                return (
                    False,
                    f"Location '{location_id}' is not registered in authoritative registry.",
                )
            return (True, None)

        lat_diff = abs(latitude - registered.expected_latitude)
        lon_diff = abs(longitude - registered.expected_longitude)

        if lat_diff > tolerance_deg or lon_diff > tolerance_deg:
            return (
                False,
                f"Location '{location_id}' coordinates ({latitude:.5f}, {longitude:.5f}) "
                f"deviate from authoritative registered coordinates "
                f"({registered.expected_latitude:.5f}, {registered.expected_longitude:.5f}) "
                f"beyond tolerance {tolerance_deg:.4f} degrees (lat_diff={lat_diff:.5f}, "
                f"lon_diff={lon_diff:.5f}).",
            )

        return (True, None)


class CalendarWeekRecord(BaseModel):
    """Authoritative calendar week definition mapping a weekly period to a week_id."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    week_id: str = Field(min_length=1, max_length=50)
    week_start_date: date
    week_end_date: date
    year: int = Field(ge=1, le=9999)
    week_number: int = Field(ge=1, le=54)

    @model_validator(mode="after")
    def validate_dates(self) -> "CalendarWeekRecord":
        if self.week_start_date > self.week_end_date:
            raise ValueError("week_start_date cannot be after week_end_date")
        return self


class CalendarRegistry:
    """Injected authoritative calendar registry for week assignment."""

    def __init__(self, weeks: list[CalendarWeekRecord] | None = None) -> None:
        self._by_id: dict[str, CalendarWeekRecord] = {}
        self._by_start_date: dict[date, CalendarWeekRecord] = {}
        if weeks:
            for w in weeks:
                self.register(w)

    def register(self, week_record: CalendarWeekRecord) -> None:
        """Register a canonical calendar week."""
        self._by_id[week_record.week_id] = week_record
        self._by_start_date[week_record.week_start_date] = week_record

    def lookup_week_id(self, target_date: date) -> CalendarWeekRecord | None:
        """Lookup canonical calendar record covering target_date."""
        for rec in self._by_id.values():
            if rec.week_start_date <= target_date <= rec.week_end_date:
                return rec
        return None

    def get_by_id(self, week_id: str) -> CalendarWeekRecord | None:
        """Retrieve calendar record by its canonical week_id."""
        return self._by_id.get(week_id)

    @staticmethod
    def compute_project_week_bounds(target_date: date) -> tuple[date, date]:
        """
        Compute Sunday-through-Saturday period bounds for any given date.

        Sunday is the first day of the week, Saturday is the last day.
        In Python datetime, weekday() returns:
            Monday = 0, Tuesday = 1, ..., Saturday = 5, Sunday = 6.
        """
        days_since_sunday = (target_date.weekday() + 1) % 7
        start_date = target_date - timedelta(days=days_since_sunday)
        end_date = start_date + timedelta(days=6)
        return (start_date, end_date)
