from datetime import UTC, date, datetime

from pydantic import ValidationError

from demand_ingestion.weather_models import WeatherDailyRecord

# Example valid weather record
weather_data = {
    "location_id": "LG_KOLKATA_001",
    "latitude": 22.5726,
    "longitude": 88.3639,
    "weather_date": date(2026, 10, 29),
    "data_kind": "historical",
    "temperature_mean_c": 28.0,
    "temperature_min_c": 25.0,
    "temperature_max_c": 32.0,
    "rainfall_mm": 4.5,
    "humidity_mean_pct": 75.0,
    "weather_code": 61,
    "retrieved_at_utc": datetime(
        2026, 10, 29, 10, 0, tzinfo=UTC
    ),
}

print("=" * 55)
print("VALID WEATHER RECORD")
print("=" * 55)

record = WeatherDailyRecord(**weather_data)
print(record.model_dump_json(indent=2))

print("\n" + "=" * 55)
print("INVALID WEATHER RECORD")
print("=" * 55)

invalid_data = {
    **weather_data,
    "humidity_mean_pct": 120.0,
}

try:
    WeatherDailyRecord(**invalid_data)
except ValidationError as error:
    print("Record rejected successfully.")

    for issue in error.errors(include_url=False):
        field = ".".join(str(part) for part in issue["loc"])
        print(f"Field: {field}")
        print(f"Reason: {issue['msg']}")