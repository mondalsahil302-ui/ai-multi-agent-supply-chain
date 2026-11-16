import sys
import numpy as np
import pandas as pd
from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.features import (
    FEATURE_COLUMNS, MIN_FEATURE_HISTORY, REQUIRED_INPUT_COLUMNS,
    check_weekly_continuity, build_feature_matrix, build_target_features)

NUMERIC = ["units_sold", "selling_price_rs", "list_price_rs", "discount_pct", "promo_flag",
           "stockout_flag", "festival_proximity", "temperature_c", "rainfall_mm", "humidity_pct"]


def load_series(db, settings, product_id: str) -> pd.DataFrame:
    rows = list(db[settings.collections["demand_features"]].find(
        {"region_id": settings.region_id, "product_id": product_id, "is_partial_week": False},
        {"_id": 0, **{c: 1 for c in REQUIRED_INPUT_COLUMNS}}))
    df = pd.DataFrame(rows)
    df["week_start_date"] = pd.to_datetime(df["week_start_date"])
    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("week_start_date").reset_index(drop=True)[REQUIRED_INPUT_COLUMNS]


if __name__ == "__main__":
    product_id = sys.argv[1] if len(sys.argv) > 1 else "BAB-001"
    s = get_settings()
    db = get_db(s)
    data = load_series(db, s, product_id)
    print(f"{product_id}: {len(data)} completed weeks, {data.week_start_date.min().date()} -> {data.week_start_date.max().date()}")

    check_weekly_continuity(data)
    print("OK    weekly continuity")

    X = build_feature_matrix(data)
    ok_cols = list(X.columns) == FEATURE_COLUMNS
    n_nan = int(X.iloc[MIN_FEATURE_HISTORY:].isna().sum().sum())
    print(("OK    " if ok_cols else "FAIL  ") + f"feature matrix {X.shape}, columns match the 34-feature contract")
    print(("OK    " if n_nan == 0 else "FAIL  ") + f"NaN values after warm-up: {n_nan}")

    # Inference path: 52-week lookback + one target row (test values only, carried forward)
    base_price = float(data["list_price_rs"].iloc[0])           # what training would store in the artifact
    lookback = data.tail(52).copy()
    last = lookback.iloc[-1]
    target = {c: np.nan for c in REQUIRED_INPUT_COLUMNS}
    target.update(week_start_date=last.week_start_date + pd.Timedelta(weeks=1),
                  selling_price_rs=float(last.selling_price_rs), list_price_rs=float(last.list_price_rs),
                  discount_pct=0.0, promo_flag=0.0, stockout_flag=0, festival_name="no_festival",
                  festival_proximity=0.0, season="Winter", temperature_c=25.0, rainfall_mm=5.0, humidity_pct=70.0)
    frame = pd.concat([lookback, pd.DataFrame([target])], ignore_index=True)
    check_weekly_continuity(frame)
    f_right = build_target_features(frame, base_list_price=base_price)
    f_wrong = build_target_features(frame)                        # base taken from the short window (wrong)
    finite = bool(np.isfinite(f_right.to_numpy(dtype=float)).all())
    print(("OK    " if finite else "FAIL  ") + f"inference features: shape {f_right.shape}, all finite, lag_52_available={f_right['lag_52_available'].iloc[0]:.0f}")
    a, b = f_right["log_list_price_index"].iloc[0], f_wrong["log_list_price_index"].iloc[0]
    if abs(a - b) > 1e-9:
        print(f"INFO  log_list_price_index: stored training base = {a:.3f}, 52-week-window base = {b:.3f} (DIFFERENT)")
        print("      -> the model artifact must store the training base price, or inference features drift")
    else:
        print(f"INFO  log_list_price_index same either way for this product ({a:.3f}); try other products")