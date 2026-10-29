"""Canonical weather normalization, duplicate reconciliation, and forecast snapshot integrity."""

import json
from collections import defaultdict
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Any, Literal
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from demand_ingestion.normalization.common import (
    BatchNormalizationReport,
    LocationRegistry,
    QuarantineErrorCategory,
)
from demand_ingestion.normalization.quarantine import (
    QuarantineRecord,
    create_quarantine_record,
)
from demand_ingestion.weather_models import WeatherDailyRecord


class NormalizedWeatherRecord(BaseModel):
    """
    Canonical normalized daily weather record with immutable provenance,
    deterministic identity, and forecast snapshot separation.
    """

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    schema_version: Literal["v1"] = "v1"
    record_id: str = Field(min_length=1, max_length=128)

    # Business grain
    location_id: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    weather_date: date
    data_kind: Literal["historical", "forecast"]

    # Forecast snapshot integrity fields
    forecast_snapshot_id: str | None = Field(default=None, max_length=100)
    forecast_issued_at_utc: datetime | None = Field(default=None)

    # Core measurements in canonical units (°C, mm, %)
    temperature_mean_c: float | None = Field(default=None, ge=-100.0, le=70.0)
    temperature_min_c: float | None = Field(default=None, ge=-100.0, le=70.0)
    temperature_max_c: float | None = Field(default=None, ge=-100.0, le=70.0)
    rainfall_mm: float | None = Field(default=None, ge=0.0)
    humidity_mean_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    weather_code: int | None = Field(default=None, ge=0, le=99)
    coverage_hours: int | None = Field(default=None, ge=0, le=24)

    # Provenance
    source: Literal["open_meteo"] = "open_meteo"
    retrieved_at_utc: datetime

    @field_validator("retrieved_at_utc")
    @classmethod
    def validate_retrieval_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at_utc must include a timezone")
        return value.astimezone(UTC)

    @field_validator("forecast_issued_at_utc")
    @classmethod
    def validate_forecast_timestamp(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("forecast_issued_at_utc must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_weather_consistency(self) -> "NormalizedWeatherRecord":
        minimum = self.temperature_min_c
        maximum = self.temperature_max_c
        mean = self.temperature_mean_c

        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(
                "Minimum temperature cannot exceed maximum temperature"
            )

        if mean is not None and minimum is not None and mean < minimum:
            raise ValueError(
                "Mean temperature cannot be below minimum temperature"
            )

        if mean is not None and maximum is not None and mean > maximum:
            raise ValueError(
                "Mean temperature cannot exceed maximum temperature"
            )

        measurements = (
            mean,
            minimum,
            maximum,
            self.rainfall_mm,
            self.humidity_mean_pct,
            self.weather_code,
        )

        if all(value is None for value in measurements):
            raise ValueError("At least one weather measurement must be present")

        # Forecast snapshot validation
        if self.data_kind == "forecast" and not self.forecast_snapshot_id:
            if self.forecast_issued_at_utc is not None:
                self.forecast_snapshot_id = self.forecast_issued_at_utc.strftime(
                    "%Y%m%dT%H%M%SZ"
                )
            else:
                self.forecast_snapshot_id = self.retrieved_at_utc.strftime(
                    "%Y%m%dT%H%M%SZ"
                )

        return self


def compute_weather_business_key(
    location_id: str,
    weather_date: date,
    data_kind: str,
    forecast_snapshot_id: str | None = None,
) -> str:
    """
    Produce the deterministic business grain key for weather records.

    Historical grain: location + date + historical
    Forecast grain: location + date + forecast + forecast_snapshot_id
    """
    loc = location_id.strip()
    d_str = weather_date.isoformat()
    if data_kind == "forecast":
        snapshot = (forecast_snapshot_id or "unspecified_snapshot").strip()
        return f"open_meteo:{loc}:{d_str}:forecast:{snapshot}"
    return f"open_meteo:{loc}:{d_str}:historical"


def compute_weather_record_id(
    location_id: str,
    weather_date: date,
    data_kind: str,
    forecast_snapshot_id: str | None = None,
) -> str:
    """Generate SHA-256 fingerprint from business key."""
    key = compute_weather_business_key(
        location_id, weather_date, data_kind, forecast_snapshot_id
    )
    return sha256(key.encode("utf-8")).hexdigest()


def compute_weather_content_hash(
    record: WeatherDailyRecord | NormalizedWeatherRecord | dict[str, Any],
    forecast_snapshot_id: str | None = None,
) -> str:
    """
    Compute deterministic content hash across all canonical measurements
    and coordinates to distinguish identical duplicates from conflicting duplicates.
    """
    if isinstance(record, (WeatherDailyRecord, NormalizedWeatherRecord)):
        data = record.model_dump(mode="json")
    else:
        data = record

    snapshot = (
        data.get("forecast_snapshot_id")
        or forecast_snapshot_id
        or ""
    )
    payload_components = [
        str(data.get("location_id", "")).strip(),
        data.get("latitude"),
        data.get("longitude"),
        str(data.get("weather_date", "")),
        str(data.get("data_kind", "")),
        snapshot,
        data.get("temperature_mean_c"),
        data.get("temperature_min_c"),
        data.get("temperature_max_c"),
        data.get("rainfall_mm"),
        data.get("humidity_mean_pct"),
        data.get("weather_code"),
        data.get("coverage_hours"),
    ]
    serialized = json.dumps(payload_components, sort_keys=False, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def normalize_weather_record(
    record: WeatherDailyRecord | dict[str, Any],
    *,
    location_registry: LocationRegistry | None = None,
    strict_location_check: bool = False,
    coordinate_tolerance_deg: float = 0.05,
    forecast_snapshot_id: str | None = None,
    forecast_issued_at_utc: datetime | None = None,
    ingestion_run_id: str | None = None,
) -> tuple[NormalizedWeatherRecord | None, QuarantineRecord | None]:
    """
    Validate and normalize one daily weather record.

    Returns (normalized_record, None) on success.
    Returns (None, quarantine_record) on validation failure.
    """
    raw_payload = (
        record.model_dump(mode="json")
        if isinstance(record, WeatherDailyRecord)
        else record
    )

    try:
        # Step 1: Base schema instantiation & numeric bounds validation
        if isinstance(record, WeatherDailyRecord):
            base_data = record.model_dump()
        else:
            base_data = WeatherDailyRecord.model_validate(record).model_dump()

        loc_id = base_data["location_id"]
        lat = base_data["latitude"]
        lon = base_data["longitude"]
        w_date = base_data["weather_date"]
        kind = base_data["data_kind"]

        # Step 2: Location registry check
        if location_registry is not None:
            is_valid_loc, loc_error = location_registry.validate_location(
                location_id=loc_id,
                latitude=lat,
                longitude=lon,
                tolerance_deg=coordinate_tolerance_deg,
                strict=strict_location_check,
            )
            if not is_valid_loc:
                category = (
                    QuarantineErrorCategory.UNKNOWN_LOCATION
                    if "not registered" in (loc_error or "")
                    else QuarantineErrorCategory.LOCATION_COORDINATE_MISMATCH
                )
                quarantine = create_quarantine_record(
                    source_system="open_meteo",
                    record_type="weather",
                    raw_payload=raw_payload,
                    error_category=category,
                    error_message=loc_error or "Location validation failed",
                    ingestion_run_id=ingestion_run_id,
                )
                return (None, quarantine)

        # Step 3: Compute deterministic record ID and forecast snapshot
        snapshot_id = (
            forecast_snapshot_id
            or (
                forecast_issued_at_utc.strftime("%Y%m%dT%H%M%SZ")
                if forecast_issued_at_utc
                else None
            )
        )
        rec_id = compute_weather_record_id(loc_id, w_date, kind, snapshot_id)

        normalized = NormalizedWeatherRecord(
            record_id=rec_id,
            location_id=loc_id,
            latitude=lat,
            longitude=lon,
            weather_date=w_date,
            data_kind=kind,
            forecast_snapshot_id=snapshot_id,
            forecast_issued_at_utc=forecast_issued_at_utc,
            temperature_mean_c=base_data.get("temperature_mean_c"),
            temperature_min_c=base_data.get("temperature_min_c"),
            temperature_max_c=base_data.get("temperature_max_c"),
            rainfall_mm=base_data.get("rainfall_mm"),
            humidity_mean_pct=base_data.get("humidity_mean_pct"),
            weather_code=base_data.get("weather_code"),
            coverage_hours=base_data.get("coverage_hours"),
            source="open_meteo",
            retrieved_at_utc=base_data["retrieved_at_utc"],
        )
        return (normalized, None)

    except Exception as exc:
        quarantine = create_quarantine_record(
            source_system="open_meteo",
            record_type="weather",
            raw_payload=raw_payload,
            error_category=QuarantineErrorCategory.VALIDATION_ERROR,
            error_message=f"Weather normalization validation error: {exc}",
            ingestion_run_id=ingestion_run_id,
        )
        return (None, quarantine)


def normalize_weather_batch(
    records: list[WeatherDailyRecord | dict[str, Any]],
    *,
    location_registry: LocationRegistry | None = None,
    strict_location_check: bool = False,
    coordinate_tolerance_deg: float = 0.05,
    forecast_snapshot_id: str | None = None,
    forecast_issued_at_utc: datetime | None = None,
    ingestion_run_id: str | None = None,
) -> tuple[
    list[NormalizedWeatherRecord],
    list[QuarantineRecord],
    BatchNormalizationReport,
]:
    """
    Normalize a batch of weather records with duplicate detection,
    conflicting duplicate quarantine, and operational reconciliation reporting.
    """
    batch_id = f"batch_weather_{uuid4().hex[:12]}"
    now_utc = datetime.now(UTC)
    total_inputs = len(records)

    quarantined: list[QuarantineRecord] = []
    candidates_by_key: dict[
        str, list[tuple[NormalizedWeatherRecord, str, dict[str, Any]]]
    ] = defaultdict(list)

    validation_failures = 0

    # Phase 1: Validate individual records
    for raw in records:
        norm_rec, quar_rec = normalize_weather_record(
            raw,
            location_registry=location_registry,
            strict_location_check=strict_location_check,
            coordinate_tolerance_deg=coordinate_tolerance_deg,
            forecast_snapshot_id=forecast_snapshot_id,
            forecast_issued_at_utc=forecast_issued_at_utc,
            ingestion_run_id=ingestion_run_id,
        )
        if quar_rec is not None:
            quarantined.append(quar_rec)
            validation_failures += 1
        elif norm_rec is not None:
            b_key = compute_weather_business_key(
                norm_rec.location_id,
                norm_rec.weather_date,
                norm_rec.data_kind,
                norm_rec.forecast_snapshot_id,
            )
            c_hash = compute_weather_content_hash(norm_rec)
            raw_dict = (
                raw.model_dump(mode="json")
                if isinstance(raw, WeatherDailyRecord)
                else raw
            )
            candidates_by_key[b_key].append((norm_rec, c_hash, raw_dict))

    # Phase 2: Duplicate detection and conflicting duplicate quarantine
    accepted_records: list[NormalizedWeatherRecord] = []
    identical_duplicates = 0
    conflicting_duplicates = 0

    for b_key, items in candidates_by_key.items():
        if len(items) == 1:
            accepted_records.append(items[0][0])
            continue

        # Check content hashes for collision
        distinct_content_hashes = {item[1] for item in items}

        if len(distinct_content_hashes) == 1:
            # All items are identical duplicates
            # Accept one canonical instance
            accepted_records.append(items[0][0])
            identical_duplicates += len(items) - 1
        else:
            # Conflicting duplicates: same business key but differing measurement values
            # Quarantine ALL conflicting records with this business key
            conflicting_duplicates += len(items)
            for _norm_rec, _, raw_d in items:
                quarantined.append(
                    create_quarantine_record(
                        source_system="open_meteo",
                        record_type="weather",
                        raw_payload=raw_d,
                        error_category=QuarantineErrorCategory.CONFLICTING_DUPLICATE,
                        error_message=(
                            f"Conflicting duplicate records detected for business key '{b_key}'. "
                            f"{len(items)} records present with differing measurements."
                        ),
                        ingestion_run_id=ingestion_run_id,
                    )
                )

    # Phase 3: Deterministic sorting
    accepted_records.sort(
        key=lambda r: (
            r.location_id,
            r.weather_date,
            r.data_kind,
            r.forecast_snapshot_id or "",
        )
    )

    report = BatchNormalizationReport(
        batch_id=batch_id,
        source_system="open_meteo",
        record_type="weather",
        processed_at_utc=now_utc,
        input_records=total_inputs,
        accepted_records=len(accepted_records),
        rejected_records=len(quarantined),
        identical_duplicates=identical_duplicates,
        conflicting_duplicates=conflicting_duplicates,
        validation_failures=validation_failures,
    )

    return accepted_records, quarantined, report
