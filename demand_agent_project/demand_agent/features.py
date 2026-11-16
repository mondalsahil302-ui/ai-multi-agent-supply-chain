"""Shared feature engineering for the Ridge (main) and LightGBM (standby) models.

Ported from the reference notebook (V5 single-product, 34 features).
The SAME code is used by offline training and by weekly inference, so the
two can never drift apart. Do not edit the feature logic without retraining.
"""
import numpy as np
import pandas as pd

FESTIVALS = ["Durga Puja", "Diwali/Kali Puja", "Holi", "Eid al-Fitr", "Poila Boishakh", "Christmas"]
SEASONS = ["Summer", "Monsoon", "Autumn"]            # Winter is the reference category
WEATHER_FEATURES = ["temperature_c", "rainfall_log1p", "humidity_pct", "heavy_rain_week_50mm"]
MIN_FEATURE_HISTORY = 12
TREND_ORIGIN = pd.Timestamp("2024-01-01")

REQUIRED_INPUT_COLUMNS = [
    "week_start_date", "units_sold", "selling_price_rs", "list_price_rs", "discount_pct",
    "promo_flag", "stockout_flag", "festival_name", "festival_proximity", "season",
    "temperature_c", "rainfall_mm", "humidity_pct",
]

FEATURE_COLUMNS = [
    "trend_scaled", "annual_sin_1", "annual_cos_1", "annual_sin_2", "annual_cos_2",
    "season_summer", "season_monsoon", "season_autumn",
    "log_list_price_index", "discount_fraction", "promo_flag",
    "festival_proximity", "festival_durga_puja", "festival_diwali_kali_puja", "festival_holi",
    "festival_eid_al-fitr", "festival_poila_boishakh", "festival_christmas",
    "temperature_c", "rainfall_log1p", "humidity_pct", "heavy_rain_week_50mm",
    "lag_1_relative_log", "lag_2_relative_log", "lag_4_relative_log", "lag_8_relative_log",
    "lag_52_relative_log", "lag_52_available",
    "rolling_4_relative_log", "rolling_8_relative_log",
    "stockout_rate_previous_4w", "stockout_rate_previous_8w",
    "promo_previous_week", "demand_level_log1p",
]


def check_weekly_continuity(data: pd.DataFrame) -> None:
    """Lags are position-based, so the weekly series must have no missing weeks.
    A 6-day step is allowed only between the first two rows (Monday bootstrap anchor
    followed by Sunday-start weeks)."""
    d = pd.to_datetime(data["week_start_date"]).reset_index(drop=True)
    if d.duplicated().any():
        raise ValueError("duplicate weekly dates")
    steps = d.diff().dropna().dt.days.reset_index(drop=True)
    bad = [i + 1 for i, s in enumerate(steps) if not (s == 7 or (i == 0 and s == 6))]
    if bad:
        raise ValueError(f"weekly continuity failed near rows {bad[:5]} (missing week or irregular gap)")


def make_one_row_features(data: pd.DataFrame, row_position: int, base_list_price: float | None = None) -> dict:
    """Features for the week at row_position, using only demand BEFORE that row.

    base_list_price: the list price the model was TRAINED against (stored in the model artifact).
    At inference the lookback window is short, so its first row is NOT the training base.
    """
    row = data.iloc[row_position]
    hist = data.iloc[:row_position]
    eligible_hist = hist.loc[
        hist["stockout_flag"].eq(0) & hist["units_sold"].notna(), "units_sold"].astype(float)

    recent = eligible_hist.tail(8)
    if len(recent) >= 4:
        level = float(recent.median())
    elif len(eligible_hist) >= 3:
        level = float(eligible_hist.median())
    else:
        level = np.nan
    if not np.isfinite(level):
        return {}
    level = max(level, 0.0)
    log_level = float(np.log1p(level))

    f = {}
    week_number = (row["week_start_date"] - TREND_ORIGIN).days / 7.0
    annual_phase = (row["week_start_date"].dayofyear - 1) / 365.2425
    f["trend_scaled"] = week_number / 100.0
    for k in (1, 2):
        f[f"annual_sin_{k}"] = np.sin(2 * np.pi * k * annual_phase)
        f[f"annual_cos_{k}"] = np.cos(2 * np.pi * k * annual_phase)

    season = str(row["season"]) if pd.notna(row["season"]) else "Unknown"
    for s in SEASONS:
        f[f"season_{s.lower()}"] = float(season == s)

    if base_list_price is None:
        base_list_price = float(data["list_price_rs"].iloc[0])
    list_price = max(float(row["list_price_rs"]), 1.0)
    f["log_list_price_index"] = np.log(list_price / base_list_price)
    f["discount_fraction"] = float(row["discount_pct"]) / 100.0
    f["promo_flag"] = float(row["promo_flag"])

    f["festival_proximity"] = float(row["festival_proximity"]) if pd.notna(row["festival_proximity"]) else 0.0
    festival_name = str(row["festival_name"]) if pd.notna(row["festival_name"]) else ""
    for name in FESTIVALS:
        key = "festival_" + name.lower().replace(" ", "_").replace("/", "_")
        f[key] = float(festival_name == name)

    temperature = float(row["temperature_c"]) if pd.notna(row["temperature_c"]) else np.nan
    rainfall = float(row["rainfall_mm"]) if pd.notna(row["rainfall_mm"]) else np.nan
    humidity = float(row["humidity_pct"]) if pd.notna(row["humidity_pct"]) else np.nan
    f["temperature_c"] = temperature
    f["rainfall_log1p"] = np.log1p(max(rainfall, 0.0)) if np.isfinite(rainfall) else np.nan
    f["humidity_pct"] = humidity
    f["heavy_rain_week_50mm"] = float(rainfall >= 50.0) if np.isfinite(rainfall) else np.nan

    for k in (1, 2, 4, 8, 52):                      # a stockout week is never used as ordinary demand
        prior_position = row_position - k
        if prior_position >= 0:
            prior = data.iloc[prior_position]
            if int(prior["stockout_flag"]) == 0 and pd.notna(prior["units_sold"]):
                value, available = max(float(prior["units_sold"]), 0.0), 1.0
            else:
                value, available = level, 0.0
        else:
            value, available = level, 0.0
        f[f"lag_{k}_relative_log"] = np.log1p(value) - log_level
        if k == 52:
            f["lag_52_available"] = available

    for window in (4, 8):
        previous_window = hist.tail(window)
        valid_values = previous_window.loc[
            previous_window["stockout_flag"].eq(0), "units_sold"].dropna().astype(float)
        rolling_level = float(valid_values.median()) if len(valid_values) >= 2 else level
        f[f"rolling_{window}_relative_log"] = np.log1p(max(rolling_level, 0.0)) - log_level

    f["stockout_rate_previous_4w"] = float(hist.tail(4)["stockout_flag"].mean()) if row_position else 0.0
    f["stockout_rate_previous_8w"] = float(hist.tail(8)["stockout_flag"].mean()) if row_position else 0.0
    f["promo_previous_week"] = float(data["promo_flag"].iloc[row_position - 1]) if row_position else 0.0
    f["demand_level_log1p"] = log_level
    return f


def build_feature_matrix(data: pd.DataFrame, base_list_price: float | None = None) -> pd.DataFrame:
    rows = [make_one_row_features(data, i, base_list_price) for i in range(len(data))]
    return pd.DataFrame(rows, index=data.index).replace([np.inf, -np.inf], np.nan)


def build_target_features(data_with_target_row: pd.DataFrame, base_list_price: float | None = None) -> pd.DataFrame:
    """Inference: the LAST row is the target week. Returns a 1-row frame in FEATURE_COLUMNS order."""
    feats = make_one_row_features(data_with_target_row, len(data_with_target_row) - 1, base_list_price)
    if not feats:
        raise ValueError("not enough eligible demand history to build features")
    return pd.DataFrame([feats]).replace([np.inf, -np.inf], np.nan)[FEATURE_COLUMNS]