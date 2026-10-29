"""Demand Agent normalization layer: canonical records, quarantine, and weekly projections."""

from demand_ingestion.normalization.common import (
    BatchNormalizationReport,
    CalendarRegistry,
    CalendarWeekRecord,
    LocationMetadata,
    LocationRegistry,
    QuarantineErrorCategory,
    compute_payload_fingerprint,
    sanitize_payload,
)
from demand_ingestion.normalization.festivals import (
    NormalizedFestivalRecord,
    compute_festival_content_hash,
    normalize_festival_batch,
    normalize_festival_record,
)
from demand_ingestion.normalization.quarantine import (
    QuarantineRecord,
    create_quarantine_record,
)
from demand_ingestion.normalization.weather import (
    NormalizedWeatherRecord,
    compute_weather_business_key,
    compute_weather_content_hash,
    compute_weather_record_id,
    normalize_weather_batch,
    normalize_weather_record,
)
from demand_ingestion.normalization.weekly import (
    WeeklyFestivalEventItem,
    WeeklyFestivalProjection,
    WeeklyWeatherSummary,
    aggregate_weekly_weather,
    project_festivals_to_weeks,
)

__all__ = [
    "BatchNormalizationReport",
    "CalendarRegistry",
    "CalendarWeekRecord",
    "LocationMetadata",
    "LocationRegistry",
    "NormalizedFestivalRecord",
    "NormalizedWeatherRecord",
    "QuarantineErrorCategory",
    "QuarantineRecord",
    "WeeklyFestivalEventItem",
    "WeeklyFestivalProjection",
    "WeeklyWeatherSummary",
    "aggregate_weekly_weather",
    "compute_festival_content_hash",
    "compute_payload_fingerprint",
    "compute_weather_business_key",
    "compute_weather_content_hash",
    "compute_weather_record_id",
    "create_quarantine_record",
    "normalize_festival_batch",
    "normalize_festival_record",
    "normalize_weather_batch",
    "normalize_weather_record",
    "project_festivals_to_weeks",
    "sanitize_payload",
]

