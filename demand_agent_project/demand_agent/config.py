import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

COLLECTION_KEYS = {
    "region_master": "COL_REGION_MASTER",
    "product_master": "COL_PRODUCT_MASTER",
    "calendar_weeks": "COL_CALENDAR_WEEKS",
    "weather_history": "COL_WEATHER_HISTORY",
    "weather_forecasts": "COL_WEATHER_FORECASTS",
    "festival_calendar": "COL_FESTIVAL_CALENDAR",
    "festival_week_features": "COL_FESTIVAL_WEEK_FEATURES",
    "historical_demand": "COL_HISTORICAL_DEMAND",
    "sales_history": "COL_SALES_HISTORY",
    "demand_features": "COL_DEMAND_FEATURES",
    "forecast_results": "COL_FORECAST_RESULTS",
    "run_metadata": "COL_RUN_METADATA",
}


def _e(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    mongo_uri: str
    mongo_database: str
    mongo_username: str
    mongo_password: str
    mongo_auth_source: str
    mongo_server_selection_timeout_ms: int
    mongo_connect_timeout_ms: int
    mongo_socket_timeout_ms: int
    region_id: str
    min_history_weeks: int
    log_level: str
    collections: dict = field(default_factory=dict)


def get_settings() -> Settings:
    cols = {k: _e(v, k) for k, v in COLLECTION_KEYS.items()}
    return Settings(
        mongo_uri=_e("MONGO_URI", "mongodb://localhost:27017"),
        mongo_database=_e("MONGO_DATABASE", "demand_agent"),
        mongo_username=_e("MONGO_USERNAME"),
        mongo_password=_e("MONGO_PASSWORD"),
        mongo_auth_source=_e("MONGO_AUTH_SOURCE", "demand_agent"),
        mongo_server_selection_timeout_ms=int(_e("MONGO_SERVER_SELECTION_TIMEOUT_MS", "5000")),
        mongo_connect_timeout_ms=int(_e("MONGO_CONNECT_TIMEOUT_MS", "5000")),
        mongo_socket_timeout_ms=int(_e("MONGO_SOCKET_TIMEOUT_MS", "20000")),
        region_id=_e("REGION_ID", "KOL-LOC-001"),
        min_history_weeks=int(_e("MIN_HISTORY_WEEKS", "52")),
        log_level=_e("LOG_LEVEL", "INFO"),
        collections=cols,
    )