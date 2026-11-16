"""Calendarific API adapter with timeout and bounded retries."""
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Dict, List
import requests

log = logging.getLogger(__name__)


class CalendarificAdapter:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://calendarific.com/api/v2",
        timeout_seconds: int = 15,
        max_retries: int = 3,
        retry_backoff: float = 2.0
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    def fetch_holidays(
        self,
        country: str = "IN",
        location: str = "IN-WB",
        year: int = None
    ) -> List[Dict[str, Any]]:
        """Fetches gazetted holidays and observances for country/location."""
        if not year:
            year = date.today().year

        url = f"{self.base_url}/holidays"
        params = {
            "api_key": self.api_key,
            "country": country,
            "year": year,
            "location": location,
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                log.info(f"Calendarific request attempt {attempt}/{self.max_retries} (year={year}, location={location})")
                r = requests.get(url, params=params, timeout=self.timeout)
                if r.status_code != 200:
                    raise RuntimeError(f"Calendarific returned HTTP {r.status_code}: {r.text[:200]}")
                data = r.json()
                response_data = data.get("response", {})
                holidays = response_data.get("holidays", [])

                records = []
                now_utc = datetime.now(timezone.utc).isoformat()
                for h in holidays:
                    h_date = h.get("date", {}).get("iso", "")
                    if len(h_date) > 10:
                        h_date = h_date[:10]
                    records.append({
                        "festival_date": h_date,
                        "festival_name": h.get("name", ""),
                        "event_type": h.get("type", ["National holiday"])[0] if isinstance(h.get("type"), list) else str(h.get("type")),
                        "description": h.get("description", ""),
                        "source_name": "Calendarific API",
                        "ingestion_timestamp_utc": now_utc
                    })
                return records
            except Exception as e:
                last_error = e
                log.warning(f"Calendarific fetch failed on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff * attempt)

        raise RuntimeError(f"Calendarific API failed after {self.max_retries} attempts: {last_error}")
