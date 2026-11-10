import pytest

from demand_ingestion.config import Settings


def test_source_configuration_defaults(monkeypatch):
    for name in (
        "OPEN_METEO_BASE_URL",
        "OPEN_METEO_FORECAST_URL",
        "DEFAULT_TIMEZONE",
        "DEFAULT_COUNTRY",
        "DEFAULT_REGION_CODE",
        "DEFAULT_FORECAST_DAYS",
        "HISTORICAL_DEMAND_DATASET_PATH",
        "REGION_MASTER_DATASET_PATH",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.open_meteo_base_url == (
        "https://api.open-meteo.com/v1/forecast"
    )
    assert settings.default_timezone == "Asia/Kolkata"
    assert settings.default_country == "IN"
    assert settings.default_region_code == "IN-WB"
    assert settings.default_forecast_days == 7
    assert settings.historical_demand_dataset_path == "agent_demand_integrated.txt"
    assert settings.region_master_dataset_path == "region_master.csv"


def test_open_meteo_base_url_supports_legacy_environment_name(monkeypatch):
    monkeypatch.delenv("OPEN_METEO_BASE_URL", raising=False)
    monkeypatch.setenv(
        "OPEN_METEO_FORECAST_URL",
        "https://legacy.example/v1/forecast",
    )

    settings = Settings(_env_file=None)

    assert settings.open_meteo_base_url == (
        "https://legacy.example/v1/forecast"
    )


def test_mongodb_credentials_must_be_configured_as_a_pair():
    with pytest.raises(ValueError, match="configured together"):
        Settings(_env_file=None, mongo_username="demand-agent")

    with pytest.raises(ValueError, match="configured together"):
        Settings(
            _env_file=None,
            mongo_password="not-a-real-password",
        )
