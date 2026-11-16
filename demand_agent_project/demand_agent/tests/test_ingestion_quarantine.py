"""Test suite for ingestion validation, quarantine isolation, and idempotency.

Verifies:
  1. Idempotency: re-running ingestion twice results in zero duplicate documents.
  2. Quarantine isolation: invalid API payloads are diverted to quarantine_data and
     ingestion_errors, while main collections remain untouched.
  3. Live smoke tests for OpenMeteoAdapter and CalendarificAdapter.
"""
import unittest
from datetime import date, datetime, timezone
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.ingestion.adapters.open_meteo import OpenMeteoAdapter
from demand_agent.ingestion.adapters.calendarific import CalendarificAdapter
from demand_agent.ingestion.pipeline import (
    ingest_weather_forecasts,
    ingest_festival_calendar,
)
from demand_agent.ingestion.quarantine import COL_QUARANTINE, COL_INGESTION_ERRORS


class TestIngestionQuarantineAndIdempotency(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.settings = get_settings()
        cls.db = get_db(cls.settings)
        cls.region_id = cls.settings.region_id

    def test_01_weather_idempotency_zero_duplicates(self):
        """Re-running weather ingestion twice produces zero duplicates."""
        test_records = [
            {
                "forecast_date": "2026-12-01",
                "temperature_max_c": 28.5,
                "temperature_min_c": 18.0,
                "precipitation_sum_mm": 0.0,
                "forecast_retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "forecast_date": "2026-12-02",
                "temperature_max_c": 29.0,
                "temperature_min_c": 18.5,
                "precipitation_sum_mm": 2.0,
                "forecast_retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        # First ingestion run
        res1 = ingest_weather_forecasts(self.db, self.settings, mock_records=test_records)
        self.assertEqual(res1["status"], "SUCCESS")
        self.assertEqual(res1["valid"], 2)
        self.assertEqual(res1["quarantined"], 0)

        # Count documents for test date
        count1 = self.db[self.settings.collections["weather_forecasts"]].count_documents({
            "region_id": self.region_id,
            "forecast_date": {"$in": ["2026-12-01", "2026-12-02"]}
        })
        self.assertEqual(count1, 2)

        # Second ingestion run with same data (simulating DAG re-run)
        res2 = ingest_weather_forecasts(self.db, self.settings, mock_records=test_records)
        self.assertEqual(res2["status"], "SUCCESS")

        # Document count must strictly remain 2 (zero duplicates)
        count2 = self.db[self.settings.collections["weather_forecasts"]].count_documents({
            "region_id": self.region_id,
            "forecast_date": {"$in": ["2026-12-01", "2026-12-02"]}
        })
        self.assertEqual(count2, 2, "Re-running ingestion created duplicate records in weather_forecasts!")

        # Cleanup test records
        self.db[self.settings.collections["weather_forecasts"]].delete_many({
            "region_id": self.region_id,
            "forecast_date": {"$in": ["2026-12-01", "2026-12-02"]}
        })

    def test_02_quarantine_invalid_weather_payload(self):
        """Invalid weather payload must be quarantined and main collection left untouched."""
        col_weather = self.db[self.settings.collections["weather_forecasts"]]
        col_quarantine = self.db[COL_QUARANTINE]
        col_errors = self.db[COL_INGESTION_ERRORS]

        quarantine_before = col_quarantine.count_documents({"source": "open_meteo_weather"})
        errors_before = col_errors.count_documents({"source": "open_meteo_weather"})
        main_before = col_weather.count_documents({"forecast_date": "2026-12-99"})

        invalid_records = [
            {
                # Corrupted record: min temp > max temp
                "forecast_date": "2026-12-98",
                "temperature_max_c": 15.0,
                "temperature_min_c": 35.0,  # Invalid: min > max
                "precipitation_sum_mm": 0.0,
                "forecast_retrieved_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                # Corrupted record: temperature out of reasonable physical bounds
                "forecast_date": "2026-12-99",
                "temperature_max_c": 99.0,  # Invalid: > 48.0
                "temperature_min_c": 10.0,
                "precipitation_sum_mm": -5.0,  # Invalid: negative
                "forecast_retrieved_at": datetime.now(timezone.utc).isoformat(),
            }
        ]

        res = ingest_weather_forecasts(self.db, self.settings, mock_records=invalid_records)
        self.assertEqual(res["valid"], 0)
        self.assertEqual(res["quarantined"], 2)

        # Assert quarantine queue has 2 new records
        quarantine_after = col_quarantine.count_documents({"source": "open_meteo_weather"})
        self.assertEqual(quarantine_after - quarantine_before, 2)

        # Assert ingestion errors logged
        errors_after = col_errors.count_documents({"source": "open_meteo_weather"})
        self.assertEqual(errors_after - errors_before, 2)

        # CRITICAL ASSERTION: Main collection was NEVER touched by the invalid records
        main_after = col_weather.count_documents({"forecast_date": {"$in": ["2026-12-98", "2026-12-99"]}})
        self.assertEqual(main_after, 0, "Security failure: Invalid data leaked into main weather_forecasts collection!")

        # Cleanup quarantine test items
        col_quarantine.delete_many({"raw_payload.forecast_date": {"$in": ["2026-12-98", "2026-12-99"]}})
        col_errors.delete_many({"reasons": {"$elemMatch": {"$regex": "temperature"}}})

    def test_03_quarantine_invalid_festival_payload(self):
        """Invalid festival payload must be quarantined and main collection left untouched."""
        col_fest = self.db[self.settings.collections["festival_calendar"]]
        col_quarantine = self.db[COL_QUARANTINE]

        invalid_festival = [
            {
                # Missing festival_name and invalid date format
                "festival_date": "NOT_A_DATE",
                "festival_name": "",
            }
        ]

        res = ingest_festival_calendar(self.db, self.settings, mock_records=invalid_festival)
        self.assertEqual(res["valid"], 0)
        self.assertEqual(res["quarantined"], 1)

        # Verify not in festival_calendar
        doc = col_fest.find_one({"festival_date": "NOT_A_DATE"})
        self.assertIsNone(doc, "Invalid festival record leaked into festival_calendar collection!")

        # Cleanup
        col_quarantine.delete_many({"raw_payload.festival_date": "NOT_A_DATE"})

    def test_04_live_open_meteo_adapter(self):
        """Smoke test live Open-Meteo API adapter."""
        adapter = OpenMeteoAdapter(timeout_seconds=15)
        records = adapter.fetch_forecast(
            latitude=float(self.settings.collections.get("REGION_LATITUDE", 22.50574)),
            longitude=float(self.settings.collections.get("REGION_LONGITUDE", 88.35672)),
            forecast_days=7
        )
        self.assertEqual(len(records), 7)
        for r in records:
            self.assertIn("forecast_date", r)
            self.assertIsNotNone(r["temperature_max_c"])
            self.assertIsNotNone(r["temperature_min_c"])
            self.assertGreaterEqual(r["temperature_max_c"], r["temperature_min_c"])

    def test_05_live_calendarific_adapter(self):
        """Smoke test live Calendarific API adapter."""
        import os
        api_key = os.environ.get("CALENDARIFIC_API_KEY", "")
        if not api_key or api_key == "CHANGE_ME":
            self.skipTest("CALENDARIFIC_API_KEY not configured")

        adapter = CalendarificAdapter(api_key=api_key, timeout_seconds=15)
        holidays = adapter.fetch_holidays(country="IN", location="IN-WB", year=2026)
        self.assertGreater(len(holidays), 0)
        for h in holidays[:5]:
            self.assertIn("festival_date", h)
            self.assertIn("festival_name", h)


if __name__ == "__main__":
    unittest.main()
