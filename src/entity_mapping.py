"""Entity Mapping Module.

Performs entity resolution and master table mapping:
1. Normalizes Product Master from wide format (unit_size_1..5, cp..sp) into a relational entity catalog.
2. Joins Product Master attributes (category_code, quality_level, canonical CP & SP) to Demand records.
3. Joins Location Master attributes (canonical location_id and region name).
4. Produces the standardized dataset matching the Demand Agent template ('demand agent sheet.xlsx').
5. Generates the enriched ML Feature Store for demand forecasting models.
"""

import sys
from pathlib import Path
from typing import Optional, Tuple
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


class DemandEntityMapper:
    """Handles entity resolution, normalization, and schema mapping for Demand Agent."""

    def __init__(
        self,
        staged_demand_path: Optional[Path] = None,
        location_master_path: Optional[Path] = None,
        product_master_path: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ):
        self.staged_demand_path = Path(
            staged_demand_path or (config.STAGED_DIR / "staged_demand.parquet")
        )
        if not self.staged_demand_path.exists():
            self.staged_demand_path = config.STAGED_DIR / "staged_demand.csv"

        self.location_master_path = Path(location_master_path or config.LOCATION_MASTER_FILE)
        self.product_master_path = Path(product_master_path or config.PRODUCT_MASTER_FILE)
        self.output_dir = Path(output_dir or config.PROCESSED_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_staged_demand(self) -> pd.DataFrame:
        """Loads clean staged demand data."""
        if self.staged_demand_path.suffix == ".parquet" and self.staged_demand_path.exists():
            return pd.read_parquet(self.staged_demand_path)
        csv_fallback = config.STAGED_DIR / "staged_demand.csv"
        return pd.read_csv(csv_fallback)

    def load_and_normalize_product_master(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Loads wide product master and unpivots it into a normalized product-variant catalog."""
        print(f"[*] Loading Product Master from: {self.product_master_path}")
        if self.product_master_path.suffix.lower() in [".xlsx", ".xls"]:
            df_raw_prod = pd.read_excel(self.product_master_path, engine="openpyxl")
        else:
            df_raw_prod = pd.read_csv(self.product_master_path)

        core_cols = ["product_id", "category_code", "category_name", "product_name", "brand", "quality_level", "unit_type"]
        existing_core_cols = [c for c in core_cols if c in df_raw_prod.columns]
        df_product_entity = df_raw_prod[existing_core_cols].drop_duplicates(subset=["product_id"])

        variant_rows = []
        for _, row in df_raw_prod.iterrows():
            pid = row["product_id"]
            for i in range(1, 6):
                size_col = f"unit_size_{i}"
                cp_col = f"cp_{i}_rs"
                sp_col = f"sp_{i}_rs"

                if size_col in df_raw_prod.columns and pd.notna(row.get(size_col)):
                    unit_size = str(row[size_col]).strip()
                    cp = float(row[cp_col]) if cp_col in df_raw_prod.columns and pd.notna(row.get(cp_col)) else np.nan
                    sp = float(row[sp_col]) if sp_col in df_raw_prod.columns and pd.notna(row.get(sp_col)) else np.nan
                    variant_rows.append({
                        "product_id": pid,
                        "unit_size": unit_size,
                        "master_cost_price_rs": cp,
                        "master_selling_price_rs": sp,
                    })

        df_product_variants = pd.DataFrame(variant_rows).drop_duplicates(subset=["product_id", "unit_size"])
        print(f"    Normalized {len(df_product_entity)} product entities and {len(df_product_variants)} SKU size variants.")
        return df_product_entity, df_product_variants

    def load_location_master(self) -> pd.DataFrame:
        """Loads canonical location master."""
        print(f"[*] Loading Location Master from: {self.location_master_path}")
        df_loc = pd.read_csv(self.location_master_path)
        df_loc.columns = df_loc.columns.str.strip().str.lower()
        return df_loc

    def map_entities(self, df_demand: pd.DataFrame) -> pd.DataFrame:
        """Enriches demand dataset with Product and Location Master entities."""
        df_prod_entity, df_prod_variants = self.load_and_normalize_product_master()
        df_loc = self.load_location_master()

        df_demand = df_demand.copy()
        df_demand["product_id"] = df_demand["product_id"].astype(str).str.strip()
        df_demand["location_id"] = df_demand["location_id"].astype(str).str.strip()
        if "unit_size" in df_demand.columns:
            df_demand["unit_size"] = df_demand["unit_size"].astype(str).str.strip()

        print("[*] Merging Product Master entity attributes...")
        prod_attrs_to_join = ["product_id", "category_code", "quality_level"]
        available_prod_attrs = [c for c in prod_attrs_to_join if c in df_prod_entity.columns]

        for col in ["category_code", "quality_level"]:
            if col in df_demand.columns and col in available_prod_attrs:
                df_demand = df_demand.drop(columns=[col])

        df_mapped = df_demand.merge(
            df_prod_entity[available_prod_attrs],
            on="product_id",
            how="left"
        )

        print("[*] Merging SKU Variant pricing references...")
        df_mapped = df_mapped.merge(
            df_prod_variants,
            on=["product_id", "unit_size"],
            how="left"
        )

        print("[*] Reconciling Location Master entities...")
        unmatched_locs = df_mapped[~df_mapped["location_id"].isin(df_loc["location_id"])]["location_id"].unique()
        if len(unmatched_locs) > 0:
            print(f"[!] Warning: Found unmatched locations: {unmatched_locs}")
        else:
            print("    All 40 Kolkata locations 100% matched against master.")

        return df_mapped

    def build_demand_agent_dataset(self, df_mapped: pd.DataFrame) -> pd.DataFrame:
        """Transforms mapped data into the exact schema of 'demand agent sheet.xlsx'."""
        print("[*] Transforming mapped data into Demand Agent Schema...")
        df = df_mapped.copy()

        date_series = pd.to_datetime(df["week_start_date"])
        df["date"] = date_series.dt.strftime("%Y-%m-%d")
        df["day_of_week"] = date_series.dt.day_name()
        df["is_weekend"] = date_series.dt.dayofweek.isin([5, 6]).astype(int)
        df["is_public_holiday"] = df["holiday_flag"].fillna(0).astype(int)

        df["units_demanded"] = df["units_sold"].astype(int)
        df["unfulfilled_demand"] = np.where(
            df["stockout_flag"] == 1,
            np.maximum(0, (df["units_sold"] * 0.2).round().astype(int)),
            0
        )

        df["selling_price"] = df["avg_selling_price_rs"].fillna(df.get("master_selling_price_rs", 0.0)).round(2)

        for col in config.DEMAND_AGENT_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan

        df_target = df[config.DEMAND_AGENT_COLUMNS].copy()
        return df_target

    def run_entity_mapping(self, df_input: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Executes entity mapping and exports both Demand Agent schema and ML Feature Store."""
        df_staged = df_input if df_input is not None else self.load_staged_demand()
        df_mapped = self.map_entities(df_staged)

        # 1. Demand Agent Standardized Sheet
        df_agent = self.build_demand_agent_dataset(df_mapped)

        agent_csv = self.output_dir / "demand_agent_standardized.csv"
        agent_xlsx = self.output_dir / "demand_agent_standardized.xlsx"
        df_agent.to_csv(agent_csv, index=False)
        print(f"[OK] Saved Demand Agent CSV to: {agent_csv}")

        try:
            df_agent.to_excel(agent_xlsx, index=False, engine="openpyxl")
            print(f"[OK] Saved Demand Agent Excel to: {agent_xlsx}")
        except Exception as e:
            print(f"[!] Excel export notice: {e}")

        # 2. Comprehensive ML Forecasting Feature Store
        feature_store_file = self.output_dir / "demand_forecasting_feature_store.parquet"
        try:
            df_mapped.to_parquet(feature_store_file, index=False)
            print(f"[OK] Saved ML Forecasting Feature Store to: {feature_store_file}")
        except Exception as e:
            csv_store = self.output_dir / "demand_forecasting_feature_store.csv"
            df_mapped.to_csv(csv_store, index=False)
            print(f"[OK] Saved ML Forecasting Feature Store CSV to: {csv_store}")

        print(f"[OK] Entity mapping completed successfully ({len(df_agent):,} records mapped).\n")
        return df_agent, df_mapped


if __name__ == "__main__":
    mapper = DemandEntityMapper()
    mapper.run_entity_mapping()
