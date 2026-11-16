"""Merges historical demand with future festival and weather context for inference."""
import logging
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

SEASON_MAP = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring", 4: "Spring",
    5: "Summer", 6: "Summer",
    7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
    10: "Autumn", 11: "Autumn",
}


def get_season_for_date(dt_str_or_ts) -> str:
    ts = pd.to_datetime(dt_str_or_ts)
    return SEASON_MAP.get(ts.month, "Autumn")


def build_task_frame(task: dict, history: pd.DataFrame | None,
                     festival_ctx: dict, weather_ctx: dict) -> pd.DataFrame:
    """History rows + one target-week row (units_sold = NaN) carrying the future context."""
    if history is None or history.empty:
        raise ValueError("no history rows in lookback window")

    hist = history.copy()
    hist["week_start_date"] = pd.to_datetime(hist["week_start_date"])
    hist["is_target"] = False

    last = hist.iloc[-1]
    target_dt = pd.to_datetime(task["week_start_date"])

    temp_c = weather_ctx.get("temp_mean_c")
    if temp_c is None or not np.isfinite(temp_c):
        temp_c = float(last.get("temperature_c", 25.0))

    humid_pct = float(last.get("humidity_pct", 70.0)) if pd.notna(last.get("humidity_pct")) else 70.0
    list_price = float(last.get("list_price_rs", 100.0))
    selling_price = float(last.get("selling_price_rs", 100.0))

    target = {
        "product_id": task["product_id"],
        "product_name": last.get("product_name"),
        "category": last.get("category"),
        "week_id": task["week_id"],
        "week_start_date": target_dt,
        "units_sold": float("nan"),
        "stockout_flag": 0,
        "promo_flag": 0.0,
        "discount_pct": 0.0,
        "selling_price_rs": selling_price,
        "list_price_rs": list_price,
        "festival_name": festival_ctx.get("festival_name"),
        "festival_proximity": festival_ctx.get("festival_proximity") or 0.0,
        "festival_count": festival_ctx.get("festival_count", 0),
        "season": get_season_for_date(target_dt),
        "temperature_c": temp_c,
        "rainfall_mm": 0.0,
        "humidity_pct": humid_pct,
        "is_synthetic_record": False,
        "is_partial_week": False,
        "is_target": True,
        "fc_days_covered": weather_ctx.get("days_covered", 7),
        "fc_temp_mean_c": weather_ctx.get("temp_mean_c"),
        "fc_temp_max_mean_c": weather_ctx.get("temp_max_mean_c"),
        "fc_temp_min_mean_c": weather_ctx.get("temp_min_mean_c"),
        "fc_precip_prob_mean_pct": weather_ctx.get("precip_prob_mean_pct"),
    }
    return pd.concat([hist, pd.DataFrame([target])], ignore_index=True)


def build_all_task_frames(tasks: list[dict], histories: dict[str, pd.DataFrame],
                          festival_ctx: dict, weather_ctx: dict):
    """Per-task isolation: one task failing never stops the others."""
    frames: dict[str, pd.DataFrame] = {}
    failed: list[dict] = []
    for t in tasks:
        try:
            frames[t["task_id"]] = build_task_frame(t, histories.get(t["product_id"]),
                                                    festival_ctx, weather_ctx)
        except Exception as e:                     # noqa: BLE001 - isolate per task
            log.warning("task %s failed in merge: %s", t["task_id"], e)
            failed.append({"task_id": t["task_id"], "stage": "merge",
                           "error": f"{type(e).__name__}: {e}"})
    return frames, failed
