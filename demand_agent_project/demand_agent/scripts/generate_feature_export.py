import os
import sys
import time
from pathlib import Path
import pandas as pd
import numpy as np
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from demand_agent.config import get_settings
from demand_agent.db import get_db
from demand_agent.features import (
    FEATURE_COLUMNS,
    REQUIRED_INPUT_COLUMNS,
    build_feature_matrix,
    check_weekly_continuity
)

FEATURE_DICTIONARY = [
    {
        "Group": "Calendar & Secular Trend",
        "Feature Name": "trend_scaled",
        "Formula / Transformation": "(week_start_date - 2024-01-01).days / (7 * 100)",
        "Type / Range": "Float [-0.5, 2.0]",
        "Leakage Prevention": "Calendar-only deterministic origin; identical across all series.",
        "Forecasting & Business Significance": "Captures long-term structural drift, population growth, and inflation trend without overfitting."
    },
    {
        "Group": "Calendar & Fourier Harmonics",
        "Feature Name": "annual_sin_1",
        "Formula / Transformation": "sin(2 * pi * 1 * (dayofyear - 1) / 365.2425)",
        "Type / Range": "Float [-1.0, 1.0]",
        "Leakage Prevention": "Strictly calendar-derived; independent of past/future demand.",
        "Forecasting & Business Significance": "Primary 52-week annual harmonic capturing broad seasonal cycles (summer peak vs winter trough)."
    },
    {
        "Group": "Calendar & Fourier Harmonics",
        "Feature Name": "annual_cos_1",
        "Formula / Transformation": "cos(2 * pi * 1 * (dayofyear - 1) / 365.2425)",
        "Type / Range": "Float [-1.0, 1.0]",
        "Leakage Prevention": "Strictly calendar-derived; independent of past/future demand.",
        "Forecasting & Business Significance": "Orthogonal cosine component enabling arbitrary seasonal phase shift adjustment."
    },
    {
        "Group": "Calendar & Fourier Harmonics",
        "Feature Name": "annual_sin_2",
        "Formula / Transformation": "sin(2 * pi * 2 * (dayofyear - 1) / 365.2425)",
        "Type / Range": "Float [-1.0, 1.0]",
        "Leakage Prevention": "Strictly calendar-derived; independent of past/future demand.",
        "Forecasting & Business Significance": "Semi-annual (26-week) harmonic capturing secondary intra-year seasonality."
    },
    {
        "Group": "Calendar & Fourier Harmonics",
        "Feature Name": "annual_cos_2",
        "Formula / Transformation": "cos(2 * pi * 2 * (dayofyear - 1) / 365.2425)",
        "Type / Range": "Float [-1.0, 1.0]",
        "Leakage Prevention": "Strictly calendar-derived; independent of past/future demand.",
        "Forecasting & Business Significance": "Orthogonal semi-annual phase regulator for bi-annual seasonal peaks."
    },
    {
        "Group": "Meteorological Seasonality",
        "Feature Name": "season_summer",
        "Formula / Transformation": "1.0 if season == 'Summer' else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Fixed calendar month mapping (March to May for Kolkata DC).",
        "Forecasting & Business Significance": "Captures intense heat spikes for beverages, ice creams, and perishable goods."
    },
    {
        "Group": "Meteorological Seasonality",
        "Feature Name": "season_monsoon",
        "Formula / Transformation": "1.0 if season == 'Monsoon' else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Fixed calendar month mapping (June to September for Kolkata DC).",
        "Forecasting & Business Significance": "Captures monsoon disruption, waterlogging delays, and comfort food demand shifts."
    },
    {
        "Group": "Meteorological Seasonality",
        "Feature Name": "season_autumn",
        "Formula / Transformation": "1.0 if season == 'Autumn' else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Fixed calendar month mapping (October to November for Kolkata DC).",
        "Forecasting & Business Significance": "Encodes autumn festive season transition; winter acts as reference zero base."
    },
    {
        "Group": "Commercial & Pricing Dynamics",
        "Feature Name": "log_list_price_index",
        "Formula / Transformation": "ln(list_price_rs / base_list_price)",
        "Type / Range": "Float [-0.5, 0.5]",
        "Leakage Prevention": "base_list_price is locked to the training baseline stored in the model artifact.",
        "Forecasting & Business Significance": "Measures permanent price shifts / inflation relative to baseline for price elasticity estimation."
    },
    {
        "Group": "Commercial & Pricing Dynamics",
        "Feature Name": "discount_fraction",
        "Formula / Transformation": "discount_pct / 100.0",
        "Type / Range": "Float [0.0, 1.0]",
        "Leakage Prevention": "Exogenously planned commercial offer for target week.",
        "Forecasting & Business Significance": "Quantifies promotional depth and volume discount elasticity."
    },
    {
        "Group": "Commercial & Pricing Dynamics",
        "Feature Name": "promo_flag",
        "Formula / Transformation": "1.0 if promo_flag == 1 else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Exogenously scheduled marketing campaign flag.",
        "Forecasting & Business Significance": "Captures marketing push / app banner feature lift independent of price discount."
    },
    {
        "Group": "Regional Bengali Festivals",
        "Feature Name": "festival_proximity",
        "Formula / Transformation": "min(1.0, max(0.0, 1.0 - abs(days_to_nearest_festival)/21.0))",
        "Type / Range": "Float [0.0, 1.0]",
        "Leakage Prevention": "Fixed regional holiday calendar dates verified by WB Govt.",
        "Forecasting & Business Significance": "Smooth exponential bell ramp peaking during festive buying weeks."
    },
    {
        "Group": "Regional Bengali Festivals",
        "Feature Name": "festival_durga_puja",
        "Formula / Transformation": "1.0 if festival_name == 'Durga Puja' else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Astronomical panjika date published months in advance.",
        "Forecasting & Business Significance": "Largest annual consumption surge in Kolkata (150%-300% demand surge across sweets, snacks, oils)."
    },
    {
        "Group": "Regional Bengali Festivals",
        "Feature Name": "festival_diwali_kali_puja",
        "Formula / Transformation": "1.0 if festival_name in ('Diwali', 'Kali Puja') else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Astronomical panjika date published months in advance.",
        "Forecasting & Business Significance": "Major lighting & gifting festival; huge confectionery and dry-fruit surge."
    },
    {
        "Group": "Regional Bengali Festivals",
        "Feature Name": "festival_holi",
        "Formula / Transformation": "1.0 if festival_name == 'Holi' else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Published national/state holiday date.",
        "Forecasting & Business Significance": "Spring festival driving packaged drinks, snacks, and dairy products."
    },
    {
        "Group": "Regional Bengali Festivals",
        "Feature Name": "festival_eid_al-fitr",
        "Formula / Transformation": "1.0 if festival_name == 'Eid al-Fitr' else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Published regional holiday date.",
        "Forecasting & Business Significance": "Major feast day driving high demand for vermicelli, edible oil, spices, and dairy."
    },
    {
        "Group": "Regional Bengali Festivals",
        "Feature Name": "festival_poila_boishakh",
        "Formula / Transformation": "1.0 if festival_name == 'Poila Boishakh' else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Bengali New Year (April 14/15 calendar date).",
        "Forecasting & Business Significance": "Cultural new year driving feast preparation, traditional sweets, and grocery restocking."
    },
    {
        "Group": "Regional Bengali Festivals",
        "Feature Name": "festival_christmas",
        "Formula / Transformation": "1.0 if festival_name == 'Christmas' else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Fixed calendar holiday (Dec 25).",
        "Forecasting & Business Significance": "Winter holiday surge; Park Street carnival bakery, cakes, and dairy demand."
    },
    {
        "Group": "Climate & Weather Telemetry",
        "Feature Name": "temperature_c",
        "Formula / Transformation": "Weekly average temperature in degrees Celsius",
        "Type / Range": "Float [12.0, 42.0]",
        "Leakage Prevention": "7-day IMD/Open-Meteo weather forecast available at decision cut-off.",
        "Forecasting & Business Significance": "Direct driver for temperature-sensitive SKUs (ice cream, soft drinks, curd)."
    },
    {
        "Group": "Climate & Weather Telemetry",
        "Feature Name": "rainfall_log1p",
        "Formula / Transformation": "ln(1 + max(rainfall_mm, 0.0))",
        "Type / Range": "Float [0.0, 6.0]",
        "Leakage Prevention": "7-day weather forecast available at decision cut-off.",
        "Forecasting & Business Significance": "Log-compressed precipitation metric preventing extreme tropical rain outlier leverage."
    },
    {
        "Group": "Climate & Weather Telemetry",
        "Feature Name": "humidity_pct",
        "Formula / Transformation": "Weekly average relative humidity %",
        "Type / Range": "Float [30.0, 100.0]",
        "Leakage Prevention": "7-day weather forecast available at decision cut-off.",
        "Forecasting & Business Significance": "Kolkata coastal humidity factor influencing spoilage rates and comfort food choices."
    },
    {
        "Group": "Climate & Weather Telemetry",
        "Feature Name": "heavy_rain_week_50mm",
        "Formula / Transformation": "1.0 if rainfall_mm >= 50.0 else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Forecast threshold indicator.",
        "Forecasting & Business Significance": "Flags severe monsoon inundation weeks causing footfall drop and home-delivery spikes."
    },
    {
        "Group": "Leakage-Proof Autoregressive Lags",
        "Feature Name": "lag_1_relative_log",
        "Formula / Transformation": "ln(1 + units_{t-1}) - ln(1 + level)",
        "Type / Range": "Float [-3.0, 3.0]",
        "Leakage Prevention": "Uses STRICTLY row_position - 1; stockout weeks censored & replaced with historical level.",
        "Forecasting & Business Significance": "Primary 1-week momentum deviation from baseline level."
    },
    {
        "Group": "Leakage-Proof Autoregressive Lags",
        "Feature Name": "lag_2_relative_log",
        "Formula / Transformation": "ln(1 + units_{t-2}) - ln(1 + level)",
        "Type / Range": "Float [-3.0, 3.0]",
        "Leakage Prevention": "Uses strictly row_position - 2; stockout weeks masked to baseline level.",
        "Forecasting & Business Significance": "2-week autoregressive momentum capturing short-term demand autocorrelation."
    },
    {
        "Group": "Leakage-Proof Autoregressive Lags",
        "Feature Name": "lag_4_relative_log",
        "Formula / Transformation": "ln(1 + units_{t-4}) - ln(1 + level)",
        "Type / Range": "Float [-3.0, 3.0]",
        "Leakage Prevention": "Uses strictly row_position - 4; stockout weeks masked to baseline level.",
        "Forecasting & Business Significance": "Monthly autoregressive cycle indicator (salary payout / monthly grocery cycle)."
    },
    {
        "Group": "Leakage-Proof Autoregressive Lags",
        "Feature Name": "lag_8_relative_log",
        "Formula / Transformation": "ln(1 + units_{t-8}) - ln(1 + level)",
        "Type / Range": "Float [-3.0, 3.0]",
        "Leakage Prevention": "Uses strictly row_position - 8; stockout weeks masked to baseline level.",
        "Forecasting & Business Significance": "Bi-monthly historical demand reference anchor."
    },
    {
        "Group": "Leakage-Proof Autoregressive Lags",
        "Feature Name": "lag_52_relative_log",
        "Formula / Transformation": "ln(1 + units_{t-52}) - ln(1 + level)",
        "Type / Range": "Float [-3.0, 3.0]",
        "Leakage Prevention": "Uses strictly row_position - 52; if <52 weeks exist, falls back to 0.0 with availability flag.",
        "Forecasting & Business Significance": "Year-over-year same-week seasonal demand benchmark."
    },
    {
        "Group": "Leakage-Proof Autoregressive Lags",
        "Feature Name": "lag_52_available",
        "Formula / Transformation": "1.0 if history >= 52 weeks and no stockout in t-52 else 0.0",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Deterministic indicator of whether 52-week lag is authentic.",
        "Forecasting & Business Significance": "Informs Ridge/LGBM model whether to trust lag_52_relative_log or down-weight it for young SKUs."
    },
    {
        "Group": "Leakage-Proof Rolling Baselines",
        "Feature Name": "rolling_4_relative_log",
        "Formula / Transformation": "ln(1 + median(valid_units_{t-4..t-1})) - ln(1 + level)",
        "Type / Range": "Float [-2.0, 2.0]",
        "Leakage Prevention": "Trailing 4-week window ending strictly at t-1; stockouts excluded from median.",
        "Forecasting & Business Significance": "Short-term baseline level stability relative to long-term trend."
    },
    {
        "Group": "Leakage-Proof Rolling Baselines",
        "Feature Name": "rolling_8_relative_log",
        "Formula / Transformation": "ln(1 + median(valid_units_{t-8..t-1})) - ln(1 + level)",
        "Type / Range": "Float [-2.0, 2.0]",
        "Leakage Prevention": "Trailing 8-week window ending strictly at t-1; stockouts excluded from median.",
        "Forecasting & Business Significance": "Medium-term baseline level stability over past 2 months."
    },
    {
        "Group": "Supply Chain & Friction Flags",
        "Feature Name": "stockout_rate_previous_4w",
        "Formula / Transformation": "mean(stockout_flag_{t-4..t-1})",
        "Type / Range": "Float [0.0, 1.0]",
        "Leakage Prevention": "Lookback strictly before row_position.",
        "Forecasting & Business Significance": "Quantifies recent supply fragility; high stockout rate suppresses observed sales."
    },
    {
        "Group": "Supply Chain & Friction Flags",
        "Feature Name": "stockout_rate_previous_8w",
        "Formula / Transformation": "mean(stockout_flag_{t-8..t-1})",
        "Type / Range": "Float [0.0, 1.0]",
        "Leakage Prevention": "Lookback strictly before row_position.",
        "Forecasting & Business Significance": "Medium-term supply reliability indicator."
    },
    {
        "Group": "Supply Chain & Friction Flags",
        "Feature Name": "promo_previous_week",
        "Formula / Transformation": "promo_flag_{t-1}",
        "Type / Range": "Binary {0.0, 1.0}",
        "Leakage Prevention": "Historical promotional flag from prior week only.",
        "Forecasting & Business Significance": "Measures post-promotion demand dip (pantry-loading payback effect)."
    },
    {
        "Group": "Autoregressive Baseline Scale",
        "Feature Name": "demand_level_log1p",
        "Formula / Transformation": "ln(1 + median(eligible_non_stockout_tail_8w))",
        "Type / Range": "Float [1.0, 10.0]",
        "Leakage Prevention": "Computed strictly from historical non-stockout weeks prior to row_position.",
        "Forecasting & Business Significance": "The absolute product volume scale anchor in log space; normalizes products of different sizes."
    }
]

def main():
    s = get_settings()
    db = get_db(s)
    
    print("=" * 70)
    print("DEMAND FEATURE EXTRACTION: ALL 200 PRODUCTS x ALL 152 WEEKS")
    print("=" * 70)
    
    t0 = time.time()
    print("1. Fetching all historical demand records from MongoDB...")
    cur = db[s.collections["demand_features"]].find(
        {"region_id": s.region_id},
        {"_id": 0, "product_id": 1, "product_name": 1, "category": 1, "week_id": 1, "split": 1, **{c: 1 for c in REQUIRED_INPUT_COLUMNS}}
    ).sort([("product_id", 1), ("week_start_date", 1)])
    
    raw_df_all = pd.DataFrame(list(cur))
    print(f"   Fetched {len(raw_df_all)} records in {time.time() - t0:.2f}s")
    
    raw_df_all["week_start_date"] = pd.to_datetime(raw_df_all["week_start_date"])
    for c in ["units_sold", "selling_price_rs", "list_price_rs", "discount_pct", "promo_flag", 
              "stockout_flag", "festival_proximity", "temperature_c", "rainfall_mm", "humidity_pct"]:
        raw_df_all[c] = pd.to_numeric(raw_df_all[c], errors="coerce")
        
    pids = sorted(raw_df_all["product_id"].unique())
    print(f"   Total unique products: {len(pids)}")
    
    all_engineered_rows = []
    product_summaries = []
    
    print("\n2. Processing all 200 products across all 152 weeks...")
    t_feat_start = time.time()
    
    for i, pid in enumerate(pids):
        sku_df = raw_df_all[raw_df_all["product_id"] == pid].sort_values("week_start_date").reset_index(drop=True)
        pname = sku_df["product_name"].iloc[0]
        cat = sku_df["category"].iloc[0]
        base_price = float(sku_df["list_price_rs"].iloc[0])
        last_row = sku_df.iloc[-1]
        
        # Append W151 (Target Week: 2026-11-15) and W152 (Horizon Week 2: 2026-11-22)
        w151_row = {c: np.nan for c in REQUIRED_INPUT_COLUMNS}
        w151_row.update(
            week_start_date=pd.Timestamp("2026-11-15"),
            product_id=pid, product_name=pname, category=cat,
            week_id="W151", split="forecast_target", units_sold=np.nan,
            selling_price_rs=float(last_row["selling_price_rs"]), list_price_rs=float(last_row["list_price_rs"]),
            discount_pct=0.0, promo_flag=0.0, stockout_flag=0, festival_name="Chhath Puja",
            festival_proximity=1.0, season="Winter", temperature_c=24.1, rainfall_mm=0.0, humidity_pct=65.0
        )
        w152_row = {c: np.nan for c in REQUIRED_INPUT_COLUMNS}
        w152_row.update(
            week_start_date=pd.Timestamp("2026-11-22"),
            product_id=pid, product_name=pname, category=cat,
            week_id="W152", split="forecast_horizon_2", units_sold=np.nan,
            selling_price_rs=float(last_row["selling_price_rs"]), list_price_rs=float(last_row["list_price_rs"]),
            discount_pct=0.0, promo_flag=0.0, stockout_flag=0, festival_name="Birthday of Guru Nanak",
            festival_proximity=1.0, season="Winter", temperature_c=23.5, rainfall_mm=0.0, humidity_pct=62.0
        )
        
        sku_152 = pd.concat([sku_df, pd.DataFrame([w151_row, w152_row])], ignore_index=True)
        
        # Build 34 features
        feat_df = build_feature_matrix(sku_152, base_list_price=base_price)
        
        # Metadata columns
        meta_cols = sku_152[["product_id", "product_name", "category", "week_id", "week_start_date", "split", "units_sold", "stockout_flag", "selling_price_rs", "list_price_rs", "promo_flag"]].copy()
        meta_cols["week_start_date"] = meta_cols["week_start_date"].dt.strftime("%Y-%m-%d")
        
        combined = pd.concat([meta_cols, feat_df[FEATURE_COLUMNS]], axis=1)
        all_engineered_rows.append(combined)
        
        # Summary row
        valid_units = sku_df.loc[sku_df["stockout_flag"] == 0, "units_sold"].dropna()
        product_summaries.append({
            "Product ID": pid,
            "Product Name": pname,
            "Category": cat,
            "Total Weeks": len(combined),
            "Historical Weeks": len(sku_df),
            "Base List Price (Rs)": base_price,
            "Latest List Price (Rs)": float(last_row["list_price_rs"]),
            "Mean Weekly Units": round(float(valid_units.mean()), 1) if len(valid_units) else 0.0,
            "Max Weekly Units": round(float(valid_units.max()), 1) if len(valid_units) else 0.0,
            "Total Stockouts": int(sku_df["stockout_flag"].sum())
        })
        
        if (i + 1) % 25 == 0 or (i + 1) == len(pids):
            print(f"   [{i + 1:3d}/{len(pids)}] Completed {pid:10s} | {len(all_engineered_rows) * 152:5d} rows processed so far")
            
    print(f"   Finished feature extraction in {time.time() - t_feat_start:.2f}s")
    
    print("\n3. Concatenating master dataset...")
    master_df = pd.concat(all_engineered_rows, ignore_index=True)
    summary_df = pd.DataFrame(product_summaries)
    dict_df = pd.DataFrame(FEATURE_DICTIONARY)
    
    print(f"   Master Feature Matrix Shape: {master_df.shape} (200 products x 152 weeks = {len(master_df)} rows, {len(master_df.columns)} columns)")
    
    out_dir = Path("demand_agent_project")
    excel_path_local = out_dir / "Demand_Features_Export.xlsx"
    csv_path_local = out_dir / "demand_features_sample.csv"
    
    excel_path_root = Path("Demand_Features_Export.xlsx")
    csv_path_root = Path("demand_features_sample.csv")
    
    print("\n4. Saving CSV exports...")
    master_df.to_csv(csv_path_local, index=False)
    master_df.to_csv(csv_path_root, index=False)
    print(f"   CSV written to {csv_path_local.name} ({master_df.shape[0]} rows)")
    
    print("\n5. Writing high-performance styled Excel workbook...")
    t_excel = time.time()
    with pd.ExcelWriter(excel_path_local, engine="openpyxl") as writer:
        master_df.to_excel(writer, sheet_name="Engineered_34_ML_Features", index=False)
        summary_df.to_excel(writer, sheet_name="Product_Summary_200", index=False)
        dict_df.to_excel(writer, sheet_name="Feature_Dictionary_34", index=False)
        
        wb = writer.book
        header_fill = PatternFill(start_color="789B4A", end_color="789B4A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        
        for ws in wb.worksheets:
            ws.views.sheetView[0].showGridLines = True
            for col_idx in range(1, ws.max_column + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center", vertical="center")
                
            # Efficient column width calculation
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col[:100])
                col_letter = get_column_letter(col[0].column)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 12), 40)
                
    import shutil
    try:
        shutil.copy(excel_path_local, excel_path_root)
        print(f"   Copied to root: {excel_path_root.resolve()}")
    except PermissionError:
        alt_root = Path("Demand_Features_Export_All_200_Products_152W.xlsx")
        shutil.copy(excel_path_local, alt_root)
        print(f"   Notice: '{excel_path_root.name}' is currently open in Excel. Copied to '{alt_root.name}' instead.")
    
    print("\n" + "=" * 70)
    print("SUCCESS: 30,400 Demand Feature records generated across all 200 products x 152 weeks!")
    print(f"  - Excel (Local): {excel_path_local.resolve()} ({excel_path_local.stat().st_size / (1024*1024):.2f} MB)")
    print(f"  - Excel (Root):  {excel_path_root.resolve()}")
    print(f"  - CSV (Local):   {csv_path_local.resolve()} ({csv_path_local.stat().st_size / (1024*1024):.2f} MB)")
    print(f"  - CSV (Root):    {csv_path_root.resolve()}")
    print("=" * 70)

if __name__ == "__main__":
    main()
