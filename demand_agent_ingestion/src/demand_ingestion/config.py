
from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qs, urlsplit

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
    open_meteo_archive_url: str = (
        "https://archive-api.open-meteo.com/v1/archive"
    )

    open_meteo_forecast_url: str = (
        "https://api.open-meteo.com/v1/forecast"
    )

    # Calendarific configuration
    calendarific_base_url: str = (
        "https://calendarific.com/api/v2/holidays"
    )

    calendarific_api_key: SecretStr | None = None

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
        """Reject unsafe configuration in production."""

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
