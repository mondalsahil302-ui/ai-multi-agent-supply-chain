import os
import sys
import time
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()
RESULTS = []


def mask(v: str) -> str:
    return f"{v[:4]}...{v[-3:]}" if v and len(v) > 8 else "(short)"


def record(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(("OK    " if ok else "FAIL  ") + f"{name}: {detail}")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---------- 1. .env sanity ----------
def check_env() -> None:
    required = ["MONGO_URI", "MONGO_DB", "REGION_ID", "REGION_LATITUDE", "REGION_LONGITUDE",
                "CALENDARIFIC_API_KEY", "LLM_API_KEY", "LLM_MODEL", "API_KEY"]
    bad = [k for k in required if env(k) in ("", "CHANGE_ME")]
    record(".env required keys", not bad, "all set" if not bad else f"missing/placeholder: {bad}")


# ---------- 2. MongoDB ----------
def check_mongo() -> None:
    try:
        from pymongo import MongoClient
        c = MongoClient(env("MONGO_URI"), serverSelectionTimeoutMS=int(env("MONGO_SERVER_TIMEOUT_MS", "5000")))
        c.admin.command("ping")
        db = c[env("MONGO_DB")]
        expected = {"region_master": 40, "product_master": 200, "calendar_weeks": 152,
                    "weather_history": 150, "weather_forecasts": 7, "festival_calendar": 24,
                    "festival_week_features": 152, "historical_demand": 30000,
                    "sales_history": 30000, "demand_features": 30000}
        wrong = {}
        for col, n in expected.items():
            got = db[col].count_documents({})
            if got != n:
                wrong[col] = f"{got} (expected {n})"
        record("MongoDB connect + collections", not wrong, "10/10 counts match" if not wrong else str(wrong))
        reg = db.region_master.find_one({"region_id": env("REGION_ID")}, {"latitude": 1, "longitude": 1})
        ok = bool(reg) and abs(float(reg["latitude"]) - float(env("REGION_LATITUDE"))) < 1e-4 \
            and abs(float(reg["longitude"]) - float(env("REGION_LONGITUDE"))) < 1e-4
        record("Region coords match .env", ok, "match" if ok else f"db={reg}")
    except Exception as e:
        record("MongoDB", False, f"{type(e).__name__}: {e}")


# ---------- 3. Open-Meteo ----------
def check_open_meteo() -> None:
    timeout = int(env("API_TIMEOUT_SECONDS", "15"))
    lat, lon = env("REGION_LATITUDE"), env("REGION_LONGITUDE")
    try:
        r = requests.get(env("OPEN_METEO_FORECAST_URL"), timeout=timeout, params={
            "latitude": lat, "longitude": lon, "timezone": env("TIMEZONE", "Asia/Kolkata"),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "forecast_days": 7})
        r.raise_for_status()
        d = r.json()["daily"]
        record("Open-Meteo forecast", len(d["time"]) == 7, f"{d['time'][0]} -> {d['time'][-1]}, tmax[0]={d['temperature_2m_max'][0]}")
    except Exception as e:
        record("Open-Meteo forecast", False, f"{type(e).__name__}: {e}")
    try:
        end = date.today() - timedelta(days=7)
        start = end - timedelta(days=6)
        r = requests.get(env("OPEN_METEO_ARCHIVE_URL"), timeout=timeout, params={
            "latitude": lat, "longitude": lon, "timezone": env("TIMEZONE", "Asia/Kolkata"),
            "start_date": start.isoformat(), "end_date": end.isoformat(),
            "daily": "temperature_2m_mean,precipitation_sum,relative_humidity_2m_mean"})
        r.raise_for_status()
        d = r.json()["daily"]
        record("Open-Meteo archive", len(d["time"]) == 7, f"{d['time'][0]} -> {d['time'][-1]}, humidity[0]={d['relative_humidity_2m_mean'][0]}")
    except Exception as e:
        record("Open-Meteo archive", False, f"{type(e).__name__}: {e}")


# ---------- 4. Calendarific ----------
def check_calendarific() -> None:
    try:
        r = requests.get(f"{env('CALENDARIFIC_BASE_URL')}/holidays", timeout=int(env("API_TIMEOUT_SECONDS", "15")),
                         params={"api_key": env("CALENDARIFIC_API_KEY"), "country": env("CALENDARIFIC_COUNTRY"),
                                 "year": date.today().year, "location": env("CALENDARIFIC_STATE")})
        body = r.json()
        if r.status_code != 200:
            record("Calendarific", False, f"HTTP {r.status_code}: {str(body)[:150]}")
            return
        hs = body["response"]["holidays"]
        record("Calendarific", len(hs) > 0, f"{len(hs)} holidays returned, e.g. {hs[0]['name']} ({hs[0]['date']['iso']})")
    except Exception as e:
        record("Calendarific", False, f"{type(e).__name__}: {e}")


# ---------- 5. Gemini ----------
def check_gemini() -> None:
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=env("LLM_API_KEY"),
                              http_options=types.HttpOptions(timeout=int(env("LLM_TIMEOUT_SECONDS", "20")) * 1000))
        t0 = time.time()
        r = client.models.generate_content(model=env("LLM_MODEL"), contents="Reply with exactly one word: pong")
        txt = (r.text or "").strip()
        record(f"Gemini ({env('LLM_MODEL')})", bool(txt), f"{time.time() - t0:.1f}s -> {txt[:40]!r} key={mask(env('LLM_API_KEY'))}")
    except Exception as e:
        record("Gemini", False, f"{type(e).__name__}: {str(e)[:200]}")


if __name__ == "__main__":
    check_env()
    check_mongo()
    check_open_meteo()
    check_calendarific()
    check_gemini()
    failed = [n for n, ok, _ in RESULTS if not ok]
    print("\n" + "=" * 50)
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("Failed:", ", ".join(failed))
        sys.exit(1)