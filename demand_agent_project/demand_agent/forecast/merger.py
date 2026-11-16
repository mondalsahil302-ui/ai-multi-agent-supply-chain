import logging
import pandas as pd

log = logging.getLogger(__name__)


def build_task_frame(task: dict, history: pd.DataFrame | None,
                     festival_ctx: dict, weather_ctx: dict) -> pd.DataFrame:
    """History rows + one target-week row (units_sold = NaN) carrying the future context."""
    if history is None or history.empty:
        raise ValueError("no history rows in lookback window")

    hist = history.copy()
    hist["is_target"] = False

    last = hist.iloc[-1]
    target = {
        "product_id": task["product_id"],
        "product_name": last.get("product_name"),
        "category": last.get("category"),
        "week_id": task["week_id"],
        "week_start_date": task["week_start_date"],
        "units_sold": float("nan"),
        "is_synthetic_record": False,
        "is_partial_week": False,
        "is_target": True,
        "festival_name": festival_ctx["festival_name"],
        "festival_proximity": festival_ctx["festival_proximity"],
        "festival_count": festival_ctx["festival_count"],
        "fc_days_covered": weather_ctx["days_covered"],
        "fc_temp_mean_c": weather_ctx["temp_mean_c"],
        "fc_temp_max_mean_c": weather_ctx["temp_max_mean_c"],
        "fc_temp_min_mean_c": weather_ctx["temp_min_mean_c"],
        "fc_precip_prob_mean_pct": weather_ctx["precip_prob_mean_pct"],
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