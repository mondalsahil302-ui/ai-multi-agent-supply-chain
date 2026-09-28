"""Staging & Standardization Module.

Standardizes raw demand data:
- Cleans and formats column headers into snake_case
- Casts dates, quantities, prices, and weather metrics to standard data types
- Normalizes boolean flags (0/1) and text categories
- Imputes missing values with business-sensible defaults
- Exports clean staged data to Parquet and CSV
"""

import sys
from pathlib import Path
from typing import Optional
import pandas as pd
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from . import config
except ImportError:
    import config


class DemandDataStager:
    """Ingests and standardizes raw demand data into a production staging layer."""

    def __init__(self, raw_demand_path: Optional[Path] = None, output_dir: Optional[Path] = None):
        self.raw_demand_path = Path(raw_demand_path or config.RAW_DEMAND_FILE)
        self.output_dir = Path(output_dir or config.STAGED_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.df_staged: pd.DataFrame = None

    def ingest_raw_data(self) -> pd.DataFrame:
        """Loads raw demand dataset from Excel or CSV."""
        print(f"[*] Ingesting raw demand dataset: {self.raw_demand_path}")
        if self.raw_demand_path.suffix.lower() in [".xlsx", ".xls"]:
            df = pd.read_excel(
                self.raw_demand_path,
                sheet_name=config.RAW_DEMAND_SHEET_NAME,
                engine="openpyxl"
            )
        else:
            df = pd.read_csv(self.raw_demand_path)

        print(f"    Raw data ingested: {df.shape[0]:,} rows, {df.shape[1]} columns")
        return df

    def standardize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Transforms column names to standard lowercase snake_case."""
        df = df.copy()
        df.columns = (
            df.columns.astype(str)
            .str.strip()
            .str.lower()
            .str.replace(" ", "_", regex=False)
            .str.replace("-", "_", regex=False)
            .str.replace("/", "_", regex=False)
        )
        return df

    def filter_audit_metadata(self, df: pd.DataFrame, drop_audit: bool = True) -> pd.DataFrame:
        """Removes Excel formula trace / audit metadata columns if requested."""
        if drop_audit:
            cols_to_drop = [c for c in config.AUDIT_METADATA_COLUMNS if c in df.columns]
            if cols_to_drop:
                print(f"[*] Removing {len(cols_to_drop)} audit/reference columns from staging dataset.")
                df = df.drop(columns=cols_to_drop)
        return df

    def standardize_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parses and formats date columns into standard datetime objects."""
        df = df.copy()
        date_cols = ["week_start_date", "week_end_date", "forecast_target_start", "forecast_target_end"]
        for col in date_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
        return df

    def standardize_numeric_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Casts quantities, monetary values, and weather readings to clean numeric types."""
        df = df.copy()

        int_cols = [
            "units_sold",
            "weekday_units_sold",
            "weekend_units_sold",
            "next_week_demand_target_units",
            "year",
            "week_number",
            "demand_rank",
        ]
        for col in int_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        if {"units_sold", "weekday_units_sold", "weekend_units_sold"}.issubset(df.columns):
            expected_total = df["weekday_units_sold"] + df["weekend_units_sold"]
            discrepancy = (df["units_sold"] != expected_total).sum()
            if discrepancy > 0:
                print(f"[!] Reconciling {discrepancy} rows where units_sold != weekday + weekend sales.")
                df["units_sold"] = expected_total

        float_cols = [
            "avg_selling_price_rs",
            "discount_pct",
            "temperature_c",
            "rainfall_mm",
            "humidity_pct",
        ]
        for col in float_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(2)

        if "rainfall_mm" in df.columns:
            df["rainfall_mm"] = df["rainfall_mm"].fillna(0.0)
        if "humidity_pct" in df.columns:
            median_humidity = df["humidity_pct"].median()
            df["humidity_pct"] = df["humidity_pct"].fillna(median_humidity)

        return df

    def standardize_flags_and_categories(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizes binary flags and cleans categorical text columns."""
        df = df.copy()

        flag_cols = ["promotion_flag", "holiday_flag", "stockout_flag"]
        for col in flag_cols:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .replace({"True": 1, "False": 0, "TRUE": 1, "FALSE": 0, "Y": 1, "N": 0, True: 1, False: 0})
                    .fillna(0)
                    .astype(int)
                )

        text_cols = ["region_of_kolkata", "product_name", "category_name", "brand", "unit_size", "season", "weather_condition"]
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()

        if "festival_event" in df.columns:
            df["festival_event"] = df["festival_event"].fillna("None").astype(str).str.strip()
            df.loc[df["festival_event"].str.lower().isin(["nan", "none", "", "null"]), "festival_event"] = "None"

        return df

    def run_staging(self, drop_audit_metadata: bool = True, df_input: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Executes full staging and standardization pipeline."""
        df_raw = df_input if df_input is not None else self.ingest_raw_data()

        print("[*] Standardizing column names...")
        df_clean = self.standardize_column_names(df_raw)

        print("[*] Filtering metadata columns...")
        df_clean = self.filter_audit_metadata(df_clean, drop_audit=drop_audit_metadata)

        print("[*] Standardizing dates and calendar intervals...")
        df_clean = self.standardize_dates(df_clean)

        print("[*] Standardizing numeric metrics, quantities, and prices...")
        df_clean = self.standardize_numeric_metrics(df_clean)

        print("[*] Normalizing categorical text and binary flags...")
        df_clean = self.standardize_flags_and_categories(df_clean)

        self.df_staged = df_clean

        # Save staged outputs
        parquet_file = self.output_dir / "staged_demand.parquet"
        csv_file = self.output_dir / "staged_demand.csv"

        try:
            self.df_staged.to_parquet(parquet_file, index=False)
            print(f"[OK] Saved staged Parquet dataset to: {parquet_file}")
        except Exception as e:
            print(f"[!] Warning: Parquet export skipped ({e})")

        self.df_staged.to_csv(csv_file, index=False)
        print(f"[OK] Saved staged CSV dataset to: {csv_file}")

        print(f"[OK] Staging complete: {len(self.df_staged):,} clean standardized records.\n")
        return self.df_staged


if __name__ == "__main__":
    stager = DemandDataStager()
    stager.run_staging()
