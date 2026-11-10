"""Validation contract for supplied historical-demand rows."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class HistoricalDemandRecord(BaseModel):
    """Validated logical demand row with its unchanged source representation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    region_id: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=100)
    week_start: date
    week_end: date
    demand_quantity: int = Field(ge=0)
    source_reference: str = Field(min_length=1)
    source_record_hash: str = Field(min_length=64, max_length=64)
    source_fields: dict[str, str | None]
