"""Open-Meteo API adapter with retry backoff and timeout safeguards."""
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
import requests

log = logging.getLogger(__name__)


class OpenMeteoAdapter:
    def __init__(
        self,
        forecast_url: str = "https://api.open-meteo.com/v1/forecast",
        timeout_seconds: int = 15,
        max_retries: int = 3,
        retry_backoff: float = 2.0
    ):
        self.forecast_url = forecast_url
        self.timeout = timeout_seconds
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

    def fetch_forecast(
        self,
        latitude: float,
        longitude: float,
        timezone_str: str = "Asia/Kolkata",
        forecast_days: int = 7
    ) -> List[Dict[str, Any]]:
        """Fetches daily forecast from Open-Meteo with bounded retries."""
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_str,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "forecast_days": forecast_days,
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                log.info(f"Open-Meteo request attempt {attempt}/{self.max_retries} (lat={latitude}, lon={longitude})")
                r = requests.get(self.forecast_url, params=params, timeout=self.timeout)
                r.raise_for_status()
                data = r.json()

                daily = data.get("daily", {})
                times = daily.get("time", [])
                t_max = daily.get("temperature_2m_max", [])
                t_min = daily.get("temperature_2m_min", [])
                precip = daily.get("precipitation_sum", [0.0] * len(times))

                records = []
                now_utc = datetime.now(timezone.utc).isoformat()
                for i in range(len(times)):
                    records.append({
                        "forecast_date": times[i],
                        "temperature_max_c": float(t_max[i]) if t_max[i] is not None else None,
                        "temperature_min_c": float(t_min[i]) if t_min[i] is not None else None,
                        "precipitation_sum_mm": float(precip[i]) if precip[i] is not None else 0.0,
                        "forecast_retrieved_at": now_utc,
                        "source_type": "open_meteo_api"
                    })
                return records
            except Exception as e:
                last_error = e
                log.warning(f"Open-Meteo fetch failed on attempt {attempt}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff * attempt)

        raise RuntimeError(f"Open-Meteo API failed after {self.max_retries} attempts: {last_error}")
