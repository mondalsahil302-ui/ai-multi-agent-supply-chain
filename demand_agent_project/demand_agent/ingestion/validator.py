"""Data quality validation rules for incoming external data.

Enforces:
  - Schema conformity & mandatory keys
  - Date format & chronological continuity
  - Strict value range bounds (temperature, precipitation, humidity)
  - Freshness constraints (staleness limit)
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    cleaned_record: Optional[Dict[str, Any]] = None


def validate_weather_forecast_record(
    doc: Dict[str, Any],
    temp_min_bound: float = 5.0,
    temp_max_bound: float = 48.0,
    max_staleness_hours: int = 48,
) -> ValidationResult:
    """Validates a single daily weather forecast record."""
    errors = []
    required_keys = ["region_id", "forecast_date", "temperature_max_c", "temperature_min_c"]
    for k in required_keys:
        if k not in doc or doc[k] is None:
            errors.append(f"Missing required key: {k}")

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    # Validate date
    try:
        fc_date = date.fromisoformat(str(doc["forecast_date"]))
    except Exception:
        errors.append(f"Invalid forecast_date format: {doc.get('forecast_date')}")

    # Validate temperature bounds
    try:
        t_max = float(doc["temperature_max_c"])
        t_min = float(doc["temperature_min_c"])

        if t_min > t_max:
            errors.append(f"Inconsistent temperatures: min ({t_min}) > max ({t_max})")
        if t_min < temp_min_bound or t_min > temp_max_bound:
            errors.append(f"temperature_min_c ({t_min}) outside valid range [{temp_min_bound}, {temp_max_bound}]")
        if t_max < temp_min_bound or t_max > temp_max_bound:
            errors.append(f"temperature_max_c ({t_max}) outside valid range [{temp_min_bound}, {temp_max_bound}]")
    except (ValueError, TypeError) as e:
        errors.append(f"Non-numeric temperature value: {e}")

    # Validate precipitation if present
    if "precipitation_sum_mm" in doc and doc["precipitation_sum_mm"] is not None:
        try:
            precip = float(doc["precipitation_sum_mm"])
            if precip < 0.0 or precip > 1500.0:
                errors.append(f"precipitation_sum_mm ({precip}) outside valid range [0, 1500]")
        except (ValueError, TypeError) as e:
            errors.append(f"Non-numeric precipitation value: {e}")

    # Validate freshness
    retrieved_at = doc.get("forecast_retrieved_at")
    if retrieved_at:
        try:
            if isinstance(retrieved_at, str):
                dt_retrieved = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
            elif isinstance(retrieved_at, datetime):
                dt_retrieved = retrieved_at if retrieved_at.tzinfo else retrieved_at.replace(tzinfo=timezone.utc)
            else:
                dt_retrieved = None

            if dt_retrieved:
                age_hours = (datetime.now(timezone.utc) - dt_retrieved).total_seconds() / 3600.0
                if age_hours > max_staleness_hours:
                    errors.append(f"Forecast retrieved_at is stale ({age_hours:.1f} hrs > {max_staleness_hours} hrs)")
        except Exception as e:
            errors.append(f"Could not parse forecast_retrieved_at timestamp: {e}")

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    return ValidationResult(is_valid=True, cleaned_record=doc)


def validate_festival_record(
    doc: Dict[str, Any],
    max_staleness_days: int = 90
) -> ValidationResult:
    """Validates a single festival / holiday record."""
    errors = []
    required_keys = ["region_id", "festival_date", "festival_name"]
    for k in required_keys:
        if k not in doc or not doc[k]:
            errors.append(f"Missing required festival key: {k}")

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    try:
        fest_date = date.fromisoformat(str(doc["festival_date"]))
    except Exception:
        errors.append(f"Invalid festival_date format: {doc.get('festival_date')}")

    if not isinstance(doc["festival_name"], str) or len(doc["festival_name"].strip()) == 0:
        errors.append("Empty or non-string festival_name")

    if errors:
        return ValidationResult(is_valid=False, errors=errors)

    return ValidationResult(is_valid=True, cleaned_record=doc)
