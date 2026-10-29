"""Canonical festival normalization, regional applicability governance, and deduplication."""

import json
import re
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

from demand_ingestion.festival_models import FestivalRecord
from demand_ingestion.normalization.common import (
    BatchNormalizationReport,
    QuarantineErrorCategory,
)
from demand_ingestion.normalization.quarantine import (
    QuarantineRecord,
    create_quarantine_record,
)


class NormalizedFestivalRecord(BaseModel):
    """
    Canonical normalized festival and calendar event record.

    Retains complete provider provenance, deterministic event keys,
    and verified regional applicability without fabricating demand impact.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    schema_version: Literal["v1"] = "v1"
    record_id: str = Field(min_length=1, max_length=128)

    country_code: str = Field(min_length=2, max_length=2)
    event_name: str = Field(min_length=1, max_length=255)
    event_date: date
    target_year: int | None = Field(default=None, ge=1, le=9999)

    description: str | None = Field(default=None, max_length=5000)
    event_types: list[str] = Field(default_factory=list, max_length=20)
    primary_type: str | None = Field(default=None, max_length=100)

    locations: str | None = Field(default=None, max_length=1000)
    states: str | None = Field(default=None, max_length=1000)
    regional_applicability: Literal["national", "regional", "unknown"] = (
        "unknown"
    )

    canonical_url: str | None = Field(default=None, max_length=2000)
    source: Literal["calendarific"] = "calendarific"
    retrieved_at_utc: datetime

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("country_code must be a string")
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", normalized):
            raise ValueError("country_code must be a two-letter country code")
        return normalized

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("event_name cannot be blank")
        return normalized

    @field_validator("event_types")
    @classmethod
    def normalize_event_types(cls, values: list[str]) -> list[str]:
        normalized = {
            item.strip() for item in values if isinstance(item, str) and item.strip()
        }
        return sorted(normalized, key=str.casefold)

    @field_validator("primary_type", "description", "canonical_url", "locations", "states")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("retrieved_at_utc")
    @classmethod
    def validate_retrieval_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at_utc must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def resolve_applicability(self) -> "NormalizedFestivalRecord":
        # Resolve regional applicability strictly from provider fields
        loc = (self.locations or "").strip().lower()
        st = (self.states or "").strip().lower()

        is_nat_type = bool(
            self.primary_type and "national" in self.primary_type.lower()
        )
        if loc == "all" or (not loc and not st and is_nat_type):
            self.regional_applicability = "national"
        elif loc or st:
            self.regional_applicability = "regional"
        else:
            self.regional_applicability = "unknown"

        return self


def compute_festival_content_hash(
    record: FestivalRecord | NormalizedFestivalRecord | dict[str, Any],
) -> str:
    """
    Compute deterministic content hash to differentiate identical duplicate
    events from conflicting duplicates.
    """
    if isinstance(record, (FestivalRecord, NormalizedFestivalRecord)):
        data = record.model_dump(mode="json")
    else:
        data = record

    types = sorted([str(t).strip().casefold() for t in data.get("event_types", [])])
    components = [
        str(data.get("country_code", "")).strip().upper(),
        str(data.get("event_name", "")).strip().casefold(),
        str(data.get("event_date", "")),
        str(data.get("description") or "").strip().casefold(),
        types,
        str(data.get("primary_type") or "").strip().casefold(),
        str(data.get("locations") or "").strip().casefold(),
        str(data.get("states") or "").strip().casefold(),
        str(data.get("canonical_url") or "").strip().casefold(),
    ]
    serialized = json.dumps(components, sort_keys=False, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def normalize_festival_record(
    record: FestivalRecord | dict[str, Any],
    *,
    requested_year: int | None = None,
    ingestion_run_id: str | None = None,
) -> tuple[NormalizedFestivalRecord | None, QuarantineRecord | None]:
    """
    Validate and normalize one festival record.

    Returns (normalized_record, None) on success.
    Returns (None, quarantine_record) on validation failure.
    """
    raw_payload = (
        record.model_dump(mode="json")
        if isinstance(record, FestivalRecord)
        else record
    )

    try:
        if isinstance(record, FestivalRecord):
            base_data = record.model_dump()
            event_key = record.event_key
        else:
            validated = FestivalRecord.model_validate(record)
            base_data = validated.model_dump()
            event_key = validated.event_key

        event_d = base_data["event_date"]
        # Validate requested year boundary if context is provided
        if requested_year is not None and event_d.year != requested_year:
            quarantine = create_quarantine_record(
                source_system="calendarific",
                record_type="festival",
                raw_payload=raw_payload,
                error_category=QuarantineErrorCategory.DATE_OUT_OF_RANGE,
                error_message=(
                    f"Event date '{event_d}' does not match requested year {requested_year}."
                ),
                ingestion_run_id=ingestion_run_id,
            )
            return (None, quarantine)

        normalized = NormalizedFestivalRecord(
            record_id=event_key,
            country_code=base_data["country_code"],
            event_name=base_data["event_name"],
            event_date=event_d,
            target_year=requested_year or event_d.year,
            description=base_data.get("description"),
            event_types=base_data.get("event_types", []),
            primary_type=base_data.get("primary_type"),
            locations=base_data.get("locations"),
            states=base_data.get("states"),
            canonical_url=base_data.get("canonical_url"),
            source="calendarific",
            retrieved_at_utc=base_data["retrieved_at_utc"],
        )
        return (normalized, None)

    except Exception as exc:
        quarantine = create_quarantine_record(
            source_system="calendarific",
            record_type="festival",
            raw_payload=raw_payload,
            error_category=QuarantineErrorCategory.VALIDATION_ERROR,
            error_message=f"Festival normalization validation error: {exc}",
            ingestion_run_id=ingestion_run_id,
        )
        return (None, quarantine)


def normalize_festival_batch(
    records: list[FestivalRecord | dict[str, Any]],
    *,
    requested_year: int | None = None,
    ingestion_run_id: str | None = None,
) -> tuple[
    list[NormalizedFestivalRecord],
    list[QuarantineRecord],
    BatchNormalizationReport,
]:
    """
    Normalize a batch of festival records with duplicate detection,
    conflicting duplicate quarantine, and operational reconciliation reporting.
    """
    batch_id = f"batch_festival_{uuid4().hex[:12]}"
    now_utc = datetime.now(UTC)
    total_inputs = len(records)

    quarantined: list[QuarantineRecord] = []
    candidates_by_key: dict[
        str, list[tuple[NormalizedFestivalRecord, str, dict[str, Any]]]
    ] = defaultdict(list)

    validation_failures = 0

    # Phase 1: Validate individual records
    for raw in records:
        norm_rec, quar_rec = normalize_festival_record(
            raw,
            requested_year=requested_year,
            ingestion_run_id=ingestion_run_id,
        )
        if quar_rec is not None:
            quarantined.append(quar_rec)
            validation_failures += 1
        elif norm_rec is not None:
            b_key = norm_rec.record_id
            c_hash = compute_festival_content_hash(norm_rec)
            raw_dict = (
                raw.model_dump(mode="json")
                if isinstance(raw, FestivalRecord)
                else raw
            )
            candidates_by_key[b_key].append((norm_rec, c_hash, raw_dict))

    # Phase 2: Deduplication and conflicting duplicate quarantine
    accepted_records: list[NormalizedFestivalRecord] = []
    identical_duplicates = 0
    conflicting_duplicates = 0

    for b_key, items in candidates_by_key.items():
        if len(items) == 1:
            accepted_records.append(items[0][0])
            continue

        distinct_hashes = {item[1] for item in items}
        if len(distinct_hashes) == 1:
            # All items agree on canonical content
            accepted_records.append(items[0][0])
            identical_duplicates += len(items) - 1
        else:
            # Conflicting duplicate events with same key but differing content
            conflicting_duplicates += len(items)
            for _norm_rec, _, raw_d in items:
                quarantined.append(
                    create_quarantine_record(
                        source_system="calendarific",
                        record_type="festival",
                        raw_payload=raw_d,
                        error_category=QuarantineErrorCategory.CONFLICTING_DUPLICATE,
                        error_message=(
                            f"Conflicting festival records detected for event key '{b_key}'. "
                            f"{len(items)} events share this key with differing content."
                        ),
                        ingestion_run_id=ingestion_run_id,
                    )
                )

    # Phase 3: Deterministic sorting
    accepted_records.sort(
        key=lambda r: (
            r.country_code,
            r.event_date,
            r.event_name.casefold(),
            r.record_id,
        )
    )

    report = BatchNormalizationReport(
        batch_id=batch_id,
        source_system="calendarific",
        record_type="festival",
        processed_at_utc=now_utc,
        input_records=total_inputs,
        accepted_records=len(accepted_records),
        rejected_records=len(quarantined),
        identical_duplicates=identical_duplicates,
        conflicting_duplicates=conflicting_duplicates,
        validation_failures=validation_failures,
    )

    return accepted_records, quarantined, report
