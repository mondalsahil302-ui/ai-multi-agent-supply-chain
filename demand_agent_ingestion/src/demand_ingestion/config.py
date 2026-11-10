
from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration for Demand Agent ingestion."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application environment
    app_env: Literal["local", "test", "staging", "production"] = "local"

    # MongoDB configuration
    mongo_uri: SecretStr = SecretStr("mongodb://127.0.0.1:27017")
    mongo_database: str = "demand_agent"

    mongo_username: str | None = None
    mongo_password: SecretStr | None = None
    mongo_auth_source: str = "demand_agent"

    mongo_server_selection_timeout_ms: int = Field(
        default=5000,
        ge=1000,
        le=120000,
    )

    mongo_connect_timeout_ms: int = Field(
        default=5000,
        ge=1000,
        le=120000,
    )

    mongo_socket_timeout_ms: int = Field(
        default=20000,
        ge=1000,
        le=120000,
    )

    # Open-Meteo configuration
    open_meteo_base_url: str = Field(
        default="https://api.open-meteo.com/v1/forecast",
        validation_alias=AliasChoices(
            "OPEN_METEO_BASE_URL",
            "OPEN_METEO_FORECAST_URL",
        ),
    )

    open_meteo_archive_url: str = (
        "https://archive-api.open-meteo.com/v1/archive"
    )

    # Calendarific configuration
    calendarific_base_url: str = (
        "https://calendarific.com/api/v2/holidays"
    )

    calendarific_api_key: SecretStr | None = None

    # External API source context
    default_timezone: str = "Asia/Kolkata"
    default_country: str = "IN"
    default_region_code: str = "IN-WB"
    default_forecast_days: int = Field(default=7, ge=1, le=16)
    region_master_dataset_path: str = "region_master.csv"
    ingestion_batch_size: int = Field(default=500, ge=1, le=10000)
    weather_history_lookback_days: int = Field(default=2, ge=1, le=365)
    weather_backfill_start_date: str | None = None
    festival_context_months: int = Field(default=12, ge=1, le=60)
    festival_cache_ttl_hours: int = Field(default=720, ge=1, le=8760)
    weather_ingestion_schedule: str = "0 1 * * *"
    festival_ingestion_schedule: str = "0 2 1 * *"

    # Independent manual historical-demand loader
    historical_demand_dataset_path: str = "agent_demand_integrated.txt"
    product_master_dataset_path: str | None = None

    # HTTP configuration
    http_timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        le=120,
    )

    http_max_retries: int = Field(
        default=3,
        ge=0,
        le=8,
    )

    http_backoff_max_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
    )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Validate credential pairing and reject unsafe production settings."""

        username_set = bool(self.mongo_username and self.mongo_username.strip())
        password_set = bool(
            self.mongo_password
            and self.mongo_password.get_secret_value().strip()
        )
        if username_set != password_set:
            raise ValueError(
                "MongoDB username and password must be configured together."
            )

        if self.app_env != "production":
            return self

        # Validate MongoDB URI structure.
        mongo_uri = self.mongo_uri.get_secret_value()

        try:
            parsed_uri = urlsplit(mongo_uri)
        except ValueError as exc:
            raise ValueError(
                "Invalid production MongoDB URI."
            ) from exc

        if (
            parsed_uri.scheme not in {"mongodb", "mongodb+srv"}
            or not parsed_uri.netloc
        ):
            raise ValueError(
                "Production MongoDB URI must use mongodb:// or mongodb+srv://."
            )

        # Check all MongoDB hosts for local addresses.
        authority = parsed_uri.netloc.rsplit("@", 1)[-1]
        hosts = []

        for host_entry in authority.split(","):
            if host_entry.startswith("["):
                hostname = host_entry[1:].split("]", 1)[0]
            elif host_entry.count(":") == 1:
                hostname = host_entry.rsplit(":", 1)[0]
            else:
                hostname = host_entry

            hosts.append(hostname.strip().lower())

        local_hosts = {
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "::1",
        }

        if not hosts or any(host in local_hosts for host in hosts):
            raise ValueError(
                "Production MongoDB must not use a localhost address."
            )

        # Validate TLS configuration.
        options = parse_qs(parsed_uri.query)
        tls_values = options.get("tls") or options.get("ssl") or []

        if parsed_uri.scheme == "mongodb+srv":
            # SRV connections use TLS by default unless explicitly disabled.
            tls_configured = (
                not tls_values
                or tls_values[-1].lower() not in {"false", "0", "no"}
            )
        else:
            tls_configured = (
                bool(tls_values)
                and tls_values[-1].lower() in {"true", "1", "yes"}
            )

        if not tls_configured:
            raise ValueError(
                "Production MongoDB must use TLS."
            )

        # Require dedicated application credentials.
        if not self.mongo_username or not self.mongo_username.strip():
            raise ValueError(
                "Production MongoDB username is required."
            )

        if (
            self.mongo_password is None
            or not self.mongo_password.get_secret_value().strip()
        ):
            raise ValueError(
                "Production MongoDB password is required."
            )

        if not self.mongo_auth_source.strip():
            raise ValueError(
                "MongoDB authentication source is required."
            )

        # Require Calendarific credentials in production.
        if (
            self.calendarific_api_key is None
            or not self.calendarific_api_key.get_secret_value().strip()
        ):
            raise ValueError(
                "Calendarific API key is required in production."
            )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings instance per process."""

    return Settings()
