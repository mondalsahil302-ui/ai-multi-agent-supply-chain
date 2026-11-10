from datetime import UTC, date, datetime
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

RecordT = TypeVar("RecordT")


class SourceMetadata(BaseModel):
    """Provenance and request status, kept separate from source records."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(min_length=1, max_length=100)
    retrieved_at_utc: datetime
    requested_start_date: date | None = None
    requested_end_date: date | None = None
    requested_year: int | None = Field(default=None, ge=1, le=9999)
    region_id: str | None = Field(default=None, min_length=1, max_length=100)
    request_status: Literal["success", "failure"]
    response_status: int | None = Field(default=None, ge=100, le=599)
    data_available: bool
    error_details: str | None = None

    @model_validator(mode="after")
    def validate_request_metadata(self) -> "SourceMetadata":
        if (
            self.retrieved_at_utc.tzinfo is None
            or self.retrieved_at_utc.utcoffset() is None
        ):
            raise ValueError("retrieved_at_utc must include a timezone")
        self.retrieved_at_utc = self.retrieved_at_utc.astimezone(UTC)

        if (
            self.requested_start_date is not None
            and self.requested_end_date is not None
            and self.requested_start_date > self.requested_end_date
        ):
            raise ValueError("requested_start_date cannot be after requested_end_date")

        if self.request_status == "failure":
            if self.data_available:
                raise ValueError("Failed requests cannot report available data")
            if not self.error_details:
                raise ValueError("Failed requests must include error_details")
        elif self.error_details is not None:
            raise ValueError("Successful requests cannot include error_details")

        return self


class SourceResult[RecordT](BaseModel):
    """Structured records paired with source/request metadata."""

    model_config = ConfigDict(extra="forbid")

    records: list[RecordT]
    metadata: SourceMetadata
