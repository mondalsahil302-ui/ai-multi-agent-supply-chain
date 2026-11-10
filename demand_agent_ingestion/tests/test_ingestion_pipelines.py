import tempfile
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from demand_ingestion.config import Settings
from demand_ingestion.data_sources.region_master import RegionMasterEntry
from demand_ingestion.database.upsert_manager import upsert_records
from demand_ingestion.festival_models import FestivalRecord
from demand_ingestion.historical_demand.importer import import_historical_demand
from demand_ingestion.ingestion.festival_ingestion import ingest_festivals
from demand_ingestion.ingestion.weather_ingestion import ingest_weather
from demand_ingestion.monitoring.ingestion_logger import IngestionRunStatus
from demand_ingestion.open_meteo_client import OpenMeteoError
from demand_ingestion.source_metadata import SourceMetadata, SourceResult
from demand_ingestion.weather_models import WeatherDailyRecord


def settings(**overrides):
    values = {
        "_env_file": None,
        "app_env": "test",
        "http_max_retries": 0,
        "weather_history_lookback_days": 1,
        "default_forecast_days": 2,
        "ingestion_batch_size": 5,
    }
    values.update(overrides)
    return Settings(**values)


class FakeWeatherClient:
    def __init__(self, fail_region=None):
        self.fail_region = fail_region
        self.history_calls = []
        self.forecast_calls = []

    def fetch_historical_daily_result(self, **kwargs):
        self.history_calls.append(kwargs["location_id"])
        if kwargs["location_id"] == self.fail_region:
            raise OpenMeteoError("temporary archive failure", response_status=503)
        day = kwargs["start_date"]
        record = make_weather(kwargs["location_id"], kwargs, day, "historical")
        return SourceResult(
            records=[record],
            metadata=weather_metadata(kwargs["location_id"], day, day),
        )

    def fetch_forecast_daily_result(self, **kwargs):
        self.forecast_calls.append(kwargs["location_id"])
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        records = [
            make_weather(
                kwargs["location_id"],
                kwargs,
                today + timedelta(days=index),
                "forecast",
            )
            for index in range(kwargs["forecast_days"])
        ]
        return SourceResult(
            records=records,
            metadata=weather_metadata(
                kwargs["location_id"],
                today,
                today + timedelta(days=kwargs["forecast_days"] - 1),
            ),
        )


class FakeFestivalClient:
    def __init__(self):
        self.calls = []

    def fetch_holidays_result(self, *, country_code, year, location):
        self.calls.append((country_code, year, location))
        record = FestivalRecord(
            country_code=country_code,
            event_name="Durga Puja",
            event_date=date(year, 10, 20),
            event_types=["Religious"],
            locations="West Bengal" if location else "All",
            states="West Bengal" if location else "All",
            provider_data={"name": "Durga Puja"},
            retrieved_at_utc=datetime.now(UTC),
        )
        return SourceResult(
            records=[record],
            metadata=SourceMetadata(
                source_name="calendarific",
                retrieved_at_utc=datetime.now(UTC),
                requested_year=year,
                region_id=location,
                request_status="success",
                response_status=200,
                data_available=True,
            ),
        )


def weather_metadata(region_id, start, end):
    return SourceMetadata(
        source_name="open_meteo",
        retrieved_at_utc=datetime.now(UTC),
        requested_start_date=start,
        requested_end_date=end,
        region_id=region_id,
        request_status="success",
        response_status=200,
        data_available=True,
    )


def make_weather(region_id, kwargs, day, kind):
    return WeatherDailyRecord(
        location_id=region_id,
        latitude=kwargs["latitude"],
        longitude=kwargs["longitude"],
        weather_date=day,
        data_kind=kind,
        temperature_mean_c=25,
        temperature_min_c=22,
        temperature_max_c=28,
        precipitation_mm=2,
        rainfall_mm=1,
        humidity_mean_pct=75,
        weather_code=3,
        wind_speed_mean_kmh=10,
        retrieved_at_utc=datetime.now(UTC),
    )


def make_regions():
    return [
        RegionMasterEntry(
            region_id=f"KOL-LOC-{index:03d}",
            region_name=f"Region {index}",
            latitude=22.0 + index / 1000,
            longitude=88.0 + index / 1000,
        )
        for index in range(1, 41)
    ]


def test_weather_pipeline_persists_all_regions_incrementally(fake_mongo):
    client = FakeWeatherClient()
    preserved_collections = (
        "historical_demand",
        "region_master",
        "product_master",
        "forecast_results",
    )
    for collection_name in preserved_collections:
        fake_mongo.database[collection_name].documents[
            f"preserved-{collection_name}"
        ] = {
            "_id": f"preserved-{collection_name}",
            "sentinel": "keep",
        }

    result = ingest_weather(
        fake_mongo,
        settings=settings(),
        regions=make_regions(),
        client=client,
    )

    assert result["run"].status == IngestionRunStatus.SUCCESS
    assert result["run"].records_inserted == 120
    assert len(client.history_calls) == 40
    assert len(fake_mongo.database["weather_history"].documents) == 40
    assert len(fake_mongo.database["weather_forecasts"].documents) == 80
    for collection_name in preserved_collections:
        assert fake_mongo.database[collection_name].find_one(
            {"_id": f"preserved-{collection_name}"}
        ) == {
            "_id": f"preserved-{collection_name}",
            "sentinel": "keep",
        }
    assert fake_mongo.database["historical_demand"].indexes == []

    second = ingest_weather(
        fake_mongo,
        settings=settings(),
        regions=make_regions(),
        client=client,
    )

    assert second["run"].status == IngestionRunStatus.SUCCESS
    assert len(client.history_calls) == 40
    assert len(client.forecast_calls) == 80
    assert second["run"].records_inserted == 80
    assert second["run"].records_unchanged == 0


def test_weather_pipeline_isolates_region_api_failures(fake_mongo):
    client = FakeWeatherClient(fail_region="KOL-LOC-001")

    result = ingest_weather(
        fake_mongo,
        settings=settings(),
        regions=make_regions(),
        client=client,
    )

    assert result["run"].status == IngestionRunStatus.PARTIAL_SUCCESS
    assert result["run"].failed_regions == ["KOL-LOC-001"]
    assert len(fake_mongo.database["weather_forecasts"].documents) == 80
    assert len(client.history_calls) == 40


def test_weather_pipeline_rejects_invalid_forecast_horizon(fake_mongo):
    with pytest.raises(ValueError, match="forecast_days"):
        ingest_weather(
            fake_mongo,
            settings=settings(),
            regions=make_regions(),
            client=FakeWeatherClient(),
            forecast_days=0,
        )

    assert fake_mongo.database.list_collection_names() == []


def test_festival_ingestion_caches_successful_national_and_regional_calls(fake_mongo):
    client = FakeFestivalClient()
    config = settings(festival_cache_ttl_hours=24)

    first = ingest_festivals(
        fake_mongo,
        settings=config,
        client=client,
        years=[2026],
        locations=(None, "IN-WB"),
    )
    second = ingest_festivals(
        fake_mongo,
        settings=config,
        client=client,
        years=[2026],
        locations=(None, "IN-WB"),
    )

    assert first["run"].status == IngestionRunStatus.SUCCESS
    assert len(client.calls) == 2
    assert second["run"].status == IngestionRunStatus.SUCCESS
    assert len(client.calls) == 2
    assert len(fake_mongo.database["festival_calendar"].documents) == 2
    assert "historical_demand" not in fake_mongo.database.list_collection_names()


def test_historical_import_quarantines_bad_and_duplicate_rows(
    tmp_path,
    fake_mongo,
    monkeypatch,
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    dataset = tmp_path / "demand.csv"
    dataset.write_text(
        "region_product_week_key,region_id,region_of_kolkata,product_id,"
        "product_name,week_start_date,week_end_date,units_sold,brand\n"
        "key1,R1,Area,P1,Product,2024-01-01,2024-01-07,4,Brand\n"
        "key2,R1,Area,P1,Product,2024-01-01,2024-01-07,4,Brand\n"
        "key3,UNKNOWN,Area,P2,Product,2024-01-08,2024-01-14,2,Brand\n"
        "key4,R1,Area,P3,Product,2024-01-08,2024-01-14,-1,Brand\n",
        encoding="utf-8",
    )

    result = import_historical_demand(
        fake_mongo,
        settings=settings(),
        dataset_path=dataset,
        region_ids={"R1"},
        batch_size=2,
    )

    assert result["run"].status == IngestionRunStatus.PARTIAL_SUCCESS
    assert result["run"].records_received == 4
    assert result["run"].records_validated == 1
    assert result["run"].records_inserted == 1
    assert result["invalid_rows"] == 2
    assert result["duplicate_rows"] == 1
    assert result["run"].records_quarantined == 3
    assert len(fake_mongo.database["historical_demand"].documents) == 1
    assert len(fake_mongo.database["ingestion_quarantine"].documents) == 3
    persisted_record = next(
        iter(fake_mongo.database["historical_demand"].documents.values())
    )
    assert len(persisted_record["source_record_hash"]) == 64
    assert "source_record" not in persisted_record
    assert persisted_record["source_fields"]["region_product_week_key"] == "key1"
    assert persisted_record["source_fields"]["week_start_date"] == "2024-01-01"
    assert persisted_record["source_fields"]["brand"] == "Brand"
    assert fake_mongo.database["historical_demand"].find_one(
        {
            "region_id": "R1",
            "product_id": "P1",
            "week_start": "2024-01-01",
        }
    ) is not None
    assert "weather_history" not in fake_mongo.database.list_collection_names()
    assert "weather_forecasts" not in fake_mongo.database.list_collection_names()
    assert "festival_calendar" not in fake_mongo.database.list_collection_names()
    assert not list(tmp_path.glob("demand-import-*.sqlite3"))

    resumed = import_historical_demand(
        fake_mongo,
        settings=settings(),
        dataset_path=dataset,
        region_ids={"R1"},
        batch_size=2,
    )

    assert resumed["run"].records_inserted == 0
    assert resumed["run"].records_unchanged == 1
    assert len(fake_mongo.database["historical_demand"].documents) == 1


def test_historical_import_does_not_overwrite_existing_business_key(
    tmp_path,
    fake_mongo,
):
    dataset = tmp_path / "demand.csv"
    dataset.write_text(
        "region_product_week_key,region_id,region_of_kolkata,product_id,"
        "product_name,week_start_date,week_end_date,units_sold\n"
        "key,R1,Area,P1,Product,2024-01-01,2024-01-07,4\n",
        encoding="utf-8",
    )
    existing = {
        "region_id": "R1",
        "product_id": "P1",
        "week_start": "2024-01-01",
        "week_end": "2024-01-07",
        "demand_quantity": 99,
        "preserved_existing_field": "leave unchanged",
    }
    upsert_records(
        fake_mongo,
        collection_name="historical_demand",
        records=[existing],
        key_fields=("region_id", "product_id", "week_start"),
    )

    result = import_historical_demand(
        fake_mongo,
        settings=settings(),
        dataset_path=dataset,
    )

    saved = fake_mongo.database["historical_demand"].find_one(
        {
            "region_id": "R1",
            "product_id": "P1",
            "week_start": "2024-01-01",
        }
    )
    assert result["run"].records_inserted == 0
    assert result["run"].records_updated == 0
    assert result["run"].records_unchanged == 1
    assert saved["demand_quantity"] == 99
    assert saved["preserved_existing_field"] == "leave unchanged"


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("", "no header"),
        ("region_id,product_id\n", "missing one or more required columns"),
    ],
)
def test_historical_import_rejects_empty_or_incomplete_dataset(
    tmp_path,
    fake_mongo,
    monkeypatch,
    contents,
    message,
):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    dataset = tmp_path / "invalid.csv"
    dataset.write_text(contents, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        import_historical_demand(
            fake_mongo,
            settings=settings(),
            dataset_path=dataset,
            region_ids={"R1"},
        )

    saved_run = next(
        iter(fake_mongo.database["ingestion_runs"].documents.values())
    )
    assert saved_run["status"] == IngestionRunStatus.FAILED
    assert not list(tmp_path.glob("demand-import-*.sqlite3"))
