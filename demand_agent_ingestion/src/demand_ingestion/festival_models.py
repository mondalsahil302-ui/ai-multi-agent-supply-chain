import json
import re
from datetime import UTC, date, datetime
from hashlib import sha256
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)


class FestivalRecord(BaseModel):
    """Validated, normalized festival or holiday record."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    # Event identity and date
    country_code: str = Field(min_length=2, max_length=2)
    event_name: str = Field(min_length=1, max_length=255)
    event_date: date
    # Event details returned by Calendarific
    description: str | None = Field(default=None, max_length=5000)
    event_types: list[str] = Field(default_factory=list, max_length=20)
    primary_type: str | None = Field(default=None, max_length=100)

    # Regional applicability reported by the provider
    locations: str | None = Field(default=None, max_length=1000)
    states: str | None = Field(default=None, max_length=1000)

    # Provider metadata
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
            raise ValueError(
                "country_code must be a two-letter country code"
            )

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
            value.strip()
            for value in values
            if value.strip()
        }
        return sorted(normalized, key=str.casefold)

    @field_validator("primary_type", "description", "canonical_url")
    @classmethod
    def normalize_optional_text(
        cls, value: str | None
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("locations", "states")
    @classmethod
    def normalize_regional_text(
        cls, value: str | None
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        return normalized or None

    @field_validator("retrieved_at_utc")
    @classmethod
    def validate_retrieval_timestamp(
        cls, value: datetime
    ) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "retrieved_at_utc must include a timezone"
            )

        return value.astimezone(UTC)

    @computed_field
    @property
    def event_key(self) -> str:
        """Return a stable key for one event occurrence."""

        common_identity = [
            self.source,
            self.country_code,
            self.event_date.isoformat(),
            (self.locations or "").casefold(),
            (self.states or "").casefold(),
        ]

        if self.canonical_url:
            identity = common_identity + [
                self.canonical_url.casefold()
            ]
        else:
            identity = common_identity + [
                self.event_name.casefold(),
                (self.primary_type or "").casefold(),
                sorted(
                    item.casefold()
                    for item in self.event_types
                ),
            ]

        serialized_identity = json.dumps(
            identity,
            ensure_ascii=False,
            separators=(",", ":"),
        )

        return sha256(
            serialized_identity.encode("utf-8")
        ).hexdigest()
