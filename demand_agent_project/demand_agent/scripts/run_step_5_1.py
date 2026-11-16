import logging
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.forecast.week_resolver import resolve_target_week
from demand_agent.forecast.task_generator import generate_tasks

if __name__ == "__main__":
    s = get_settings()
    logging.basicConfig(level=s.log_level, format="%(levelname)s | %(message)s")
    db = get_db(s)

    target, last_done = resolve_target_week(db, s)
    tasks, skipped = generate_tasks(db, s, target, last_done)

    print("Target week        :", target["week_id"], target["week_start_date"], "->", target["week_end_date"], target["week_status"])
    print("Last completed week:", last_done["week_id"], last_done["week_start_date"])
    print("Eligible tasks     :", len(tasks))
    print("Ineligible tasks   :", len(skipped), skipped[:3])
    print("Lookback window    :", tasks[0]["lookback_start"], "->", tasks[0]["lookback_end"])
    print("Synthetic weeks in lookback (distinct values):", sorted({t["lookback_synthetic_weeks"] for t in tasks}))
    print("Example task       :", tasks[0])