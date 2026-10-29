
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime configuration for Demand Agent ingestion."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"

    mongo_uri: SecretStr = SecretStr("mongodb://localhost:27017")
    mongo_database: str = "demand_agent"

    open_meteo_archive_url: str = (
        "https://archive-api.open-meteo.com/v1/archive"
    )
    open_meteo_forecast_url: str = (
        "https://api.open-meteo.com/v1/forecast"
    )

    calendarific_base_url: str = (
        "https://calendarific.com/api/v2/holidays"
    )
    calendarific_api_key: SecretStr | None = None

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
    def validate_production_security(self):
        """Reject unsafe default settings in production."""

        if self.app_env != "production":
            return self

        mongo_uri = self.mongo_uri.get_secret_value()
        normalized_uri = mongo_uri.lower()

        if any(
            host in normalized_uri
            for host in ("localhost", "127.0.0.1", "0.0.0.0")
        ):
            raise ValueError(
                "Production MongoDB must not use a localhost address."
            )

        tls_configured = (
            normalized_uri.startswith("mongodb+srv://")
            or "tls=true" in normalized_uri
            or "ssl=true" in normalized_uri
        )

        if not tls_configured:
            raise ValueError(
                "Production MongoDB must use a TLS-enabled connection."
            )

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
