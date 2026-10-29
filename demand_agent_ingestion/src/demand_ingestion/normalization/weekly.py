"""Weekly derived projections for normalized daily weather and festival events."""

from collections import Counter, defaultdict
from datetime import date, timedelta
from hashlib import sha256
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from demand_ingestion.normalization.common import (
    CalendarRegistry,
)
from demand_ingestion.normalization.festivals import (
    NormalizedFestivalRecord,
)
from demand_ingestion.normalization.weather import (
    NormalizedWeatherRecord,
)


class WeeklyWeatherSummary(BaseModel):
    """
    Derived weekly weather projection.

    Aggregates daily records over Sunday-through-Saturday project weeks,
    preserving missing-day coverage, distinct forecast snapshots, and
    strict separation between historical and forecast data.
    """

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    schema_version: Literal["v1"] = "v1"
    summary_id: str = Field(min_length=1, max_length=128)

    location_id: str = Field(min_length=1, max_length=100)
    period_start_date: date
    period_end_date: date
    week_id: str | None = Field(default=None, max_length=50)

    data_kind: Literal["historical", "forecast"]
    forecast_snapshot_id: str | None = Field(default=None, max_length=100)

    # Aggregated measurements
    temperature_mean_c: float | None = Field(default=None, ge=-100.0, le=70.0)
    temperature_min_c: float | None = Field(default=None, ge=-100.0, le=70.0)
    temperature_max_c: float | None = Field(default=None, ge=-100.0, le=70.0)
    rainfall_total_mm: float | None = Field(default=None, ge=0.0)
    humidity_mean_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    weather_code_counts: dict[int, int] = Field(default_factory=dict)

    # Coverage metrics
    expected_days: int = Field(default=7, ge=1, le=7)
    observed_days: int = Field(ge=0, le=7)
    missing_days: int = Field(ge=0, le=7)
    is_complete_week: bool
    missing_dates: list[date] = Field(default_factory=list)
    daily_record_ids: list[str] = Field(default_factory=list)


class WeeklyFestivalEventItem(BaseModel):
    """Event reference in a weekly festival projection."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    record_id: str = Field(min_length=1, max_length=128)
    event_name: str = Field(min_length=1, max_length=255)
    event_date: date
    primary_type: str | None = Field(default=None, max_length=100)
    event_types: list[str] = Field(default_factory=list, max_length=20)
    regional_applicability: str = Field(max_length=50)
    locations: str | None = Field(default=None, max_length=1000)
    states: str | None = Field(default=None, max_length=1000)


class WeeklyFestivalProjection(BaseModel):
    """Derived weekly festival and calendar event projection."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: Literal["v1"] = "v1"
    projection_id: str = Field(min_length=1, max_length=128)

    country_code: str = Field(min_length=2, max_length=2)
    period_start_date: date
    period_end_date: date
    week_id: str | None = Field(default=None, max_length=50)

    total_events: int = Field(ge=0)
    events: list[WeeklyFestivalEventItem] = Field(default_factory=list)


def aggregate_weekly_weather(
    records: list[NormalizedWeatherRecord],
    *,
    calendar_registry: CalendarRegistry | None = None,
) -> list[WeeklyWeatherSummary]:
    """
    Aggregate daily normalized weather records into Sunday-through-Saturday weekly summaries.

    Separates historical and forecast records and keeps distinct forecast snapshots isolated.
    """
    # Group records by grain:
    # (location_id, period_start_date, period_end_date, data_kind, snapshot_id)
    groups: dict[
        tuple[str, date, date, str, str | None], list[NormalizedWeatherRecord]
    ] = defaultdict(list)

    for rec in records:
        if calendar_registry is not None:
            cal = calendar_registry.lookup_week_id(rec.weather_date)
            if cal is not None:
                start_d = cal.week_start_date
                end_d = cal.week_end_date
            else:
                start_d, end_d = CalendarRegistry.compute_project_week_bounds(
                    rec.weather_date
                )
        else:
            start_d, end_d = CalendarRegistry.compute_project_week_bounds(
                rec.weather_date
            )

        group_key = (
            rec.location_id,
            start_d,
            end_d,
            rec.data_kind,
            rec.forecast_snapshot_id,
        )
        groups[group_key].append(rec)

    summaries: list[WeeklyWeatherSummary] = []

    for group_key, daily_list in groups.items():
        loc_id, start_d, end_d, kind, snapshot_id = group_key

        # Resolve week_id from calendar registry if available
        week_id: str | None = None
        if calendar_registry is not None:
            cal = calendar_registry.lookup_week_id(start_d)
            if cal is not None:
                week_id = cal.week_id

        # Coverage analysis
        observed_dates = {r.weather_date for r in daily_list}
        all_expected_dates = [
            start_d + timedelta(days=i) for i in range((end_d - start_d).days + 1)
        ]
        expected_days = len(all_expected_dates)
        missing_dates = sorted(set(all_expected_dates) - observed_dates)
        observed_days = len(observed_dates)
        missing_days = len(missing_dates)
        is_complete = missing_days == 0

        # Numerical aggregations (excluding None)
        mean_temps = [
            r.temperature_mean_c
            for r in daily_list
            if r.temperature_mean_c is not None
        ]
        min_temps = [
            r.temperature_min_c
            for r in daily_list
            if r.temperature_min_c is not None
        ]
        max_temps = [
            r.temperature_max_c
            for r in daily_list
            if r.temperature_max_c is not None
        ]
        rainfalls = [
            r.rainfall_mm for r in daily_list if r.rainfall_mm is not None
        ]
        humidities = [
            r.humidity_mean_pct
            for r in daily_list
            if r.humidity_mean_pct is not None
        ]
        codes = [r.weather_code for r in daily_list if r.weather_code is not None]

        temp_mean = (
            round(sum(mean_temps) / len(mean_temps), 2) if mean_temps else None
        )
        temp_min = min(min_temps) if min_temps else None
        temp_max = max(max_temps) if max_temps else None
        rain_sum = round(sum(rainfalls), 2) if rainfalls else None
        hum_mean = (
            round(sum(humidities) / len(humidities), 2) if humidities else None
        )
        code_counts = dict(Counter(codes))

        summary_key = (
            f"wsum:{loc_id}:{start_d.isoformat()}:{kind}:{snapshot_id or ''}"
        )
        summary_id = sha256(summary_key.encode("utf-8")).hexdigest()

        sorted_daily_ids = [
            r.record_id
            for r in sorted(daily_list, key=lambda x: x.weather_date)
        ]

        summary = WeeklyWeatherSummary(
            summary_id=summary_id,
            location_id=loc_id,
            period_start_date=start_d,
            period_end_date=end_d,
            week_id=week_id,
            data_kind=kind,
            forecast_snapshot_id=snapshot_id,
            temperature_mean_c=temp_mean,
            temperature_min_c=temp_min,
            temperature_max_c=temp_max,
            rainfall_total_mm=rain_sum,
            humidity_mean_pct=hum_mean,
            weather_code_counts=code_counts,
            expected_days=expected_days,
            observed_days=observed_days,
            missing_days=missing_days,
            is_complete_week=is_complete,
            missing_dates=missing_dates,
            daily_record_ids=sorted_daily_ids,
        )
        summaries.append(summary)

    # Sort deterministically
    summaries.sort(
        key=lambda s: (
            s.location_id,
            s.period_start_date,
            s.data_kind,
            s.forecast_snapshot_id or "",
        )
    )
    return summaries


def project_festivals_to_weeks(
    records: list[NormalizedFestivalRecord],
    *,
    calendar_registry: CalendarRegistry | None = None,
) -> list[WeeklyFestivalProjection]:
    """
    Project normalized festival events into weekly periods based on event date.
    """
    groups: dict[tuple[str, date, date], list[NormalizedFestivalRecord]] = (
        defaultdict(list)
    )

    for rec in records:
        if calendar_registry is not None:
            cal = calendar_registry.lookup_week_id(rec.event_date)
            if cal is not None:
                start_d = cal.week_start_date
                end_d = cal.week_end_date
            else:
                start_d, end_d = CalendarRegistry.compute_project_week_bounds(
                    rec.event_date
                )
        else:
            start_d, end_d = CalendarRegistry.compute_project_week_bounds(
                rec.event_date
            )

        group_key = (rec.country_code, start_d, end_d)
        groups[group_key].append(rec)

    projections: list[WeeklyFestivalProjection] = []

    for group_key, event_list in groups.items():
        country_code, start_d, end_d = group_key

        week_id: str | None = None
        if calendar_registry is not None:
            cal = calendar_registry.lookup_week_id(start_d)
            if cal is not None:
                week_id = cal.week_id

        # Sort events inside the week
        sorted_events = sorted(
            event_list, key=lambda e: (e.event_date, e.event_name.casefold())
        )

        event_items = [
            WeeklyFestivalEventItem(
                record_id=e.record_id,
                event_name=e.event_name,
                event_date=e.event_date,
                primary_type=e.primary_type,
                event_types=e.event_types,
                regional_applicability=e.regional_applicability,
                locations=e.locations,
                states=e.states,
            )
            for e in sorted_events
        ]

        proj_key = f"wfest:{country_code}:{start_d.isoformat()}"
        projection_id = sha256(proj_key.encode("utf-8")).hexdigest()

        projection = WeeklyFestivalProjection(
            projection_id=projection_id,
            country_code=country_code,
            period_start_date=start_d,
            period_end_date=end_d,
            week_id=week_id,
            total_events=len(event_items),
            events=event_items,
        )
        projections.append(projection)

    projections.sort(key=lambda p: (p.country_code, p.period_start_date))
    return projections
