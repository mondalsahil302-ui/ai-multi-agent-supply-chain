
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class WeatherDailyRecord(BaseModel):
    """Validated daily weather record for one configured region."""

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    # Region identity and geographic coordinates
    location_id: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    # Date and type of weather data
    weather_date: date
    data_kind: Literal["historical", "forecast"]

    # Daily weather measurements
    temperature_mean_c: float | None = Field(
        default=None, ge=-100, le=70
    )
    temperature_min_c: float | None = Field(
        default=None, ge=-100, le=70
    )
    temperature_max_c: float | None = Field(
        default=None, ge=-100, le=70
    )
    rainfall_mm: float | None = Field(default=None, ge=0)
    humidity_mean_pct: float | None = Field(
        default=None, ge=0, le=100
    )
    weather_code: int | None = Field(default=None, ge=0, le=99)

    # Forecast coverage information
    coverage_hours: int | None = Field(default=None, ge=0, le=24)

    # Provenance and audit information
    source: Literal["open_meteo"] = "open_meteo"
    retrieved_at_utc: datetime

    @field_validator("location_id")
    @classmethod
    def validate_location_id(cls, value: str) -> str:
        if not value:
            raise ValueError("location_id cannot be blank")
        return value

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

    @model_validator(mode="after")
    def validate_weather_consistency(self):
        minimum = self.temperature_min_c
        maximum = self.temperature_max_c
        mean = self.temperature_mean_c

        if (
            minimum is not None
            and maximum is not None
            and minimum > maximum
        ):
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
            raise ValueError(
                "At least one weather measurement must be present"
            )

        return self
