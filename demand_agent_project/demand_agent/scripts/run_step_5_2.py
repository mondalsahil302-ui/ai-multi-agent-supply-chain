import logging
import pandas as pd
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.forecast.week_resolver import resolve_target_week
from demand_agent.forecast.task_generator import generate_tasks
from demand_agent.forecast.data_fetcher import (
    fetch_history, fetch_festival_context, fetch_weather_context)
from demand_agent.forecast.merger import build_all_task_frames

if __name__ == "__main__":
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s | %(message)s")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    db = get_db(s)
    target, last_done = resolve_target_week(db, s)
    tasks, skipped = generate_tasks(db, s, target, last_done)

    histories = fetch_history(db, s, [t["product_id"] for t in tasks],
                              tasks[0]["lookback_start"], tasks[0]["lookback_end"])
    festival = fetch_festival_context(db, s, target)
    weather = fetch_weather_context(db, s, target)
    frames, failed = build_all_task_frames(tasks, histories, festival, weather)

    print("Target week     :", target["week_id"], target["week_start_date"], "->", target["week_end_date"])
    print("Festival context:", festival)
    print("Weather context :", weather)
    print("Tasks / frames  :", len(tasks), "/", len(frames), "| failed:", len(failed), failed[:3])

    if frames:
        rows = [len(f) for f in frames.values()]
        print("Rows per frame  : min", min(rows), "max", max(rows), "(history + 1 target row)")
        tid = tasks[0]["task_id"]
        f = frames[tid]
        print("\nExample frame   :", tid, f.shape)
        cols = ["week_id", "week_start_date", "units_sold", "stockout_flag", "promo_flag",
                "is_synthetic_record", "is_target", "festival_name", "fc_temp_mean_c"]
        print(f[[c for c in cols if c in f.columns]].tail(6).to_string(index=False))