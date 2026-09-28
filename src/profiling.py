"""Dataset Profiling Module.

Profiles the raw demand dataset and master entity files to detect:
- Missing values and completeness
- Column distributions and summary statistics
- Primary key and composite key uniqueness
- Referential integrity with Product and Location Masters
- Anomaly detection (negative sales, invalid discounts, out-of-bounds weather)
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List
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


class DemandDataProfiler:
    """Automated profiler for raw demand and master datasets."""

    def __init__(self, raw_demand_path: Path = None,
                 location_master_path: Path = None,
                 product_master_path: Path = None):
        self.raw_demand_path = Path(raw_demand_path or config.RAW_DEMAND_FILE)
        self.location_master_path = Path(location_master_path or config.LOCATION_MASTER_FILE)
        self.product_master_path = Path(product_master_path or config.PRODUCT_MASTER_FILE)

        self.df_demand: pd.DataFrame = None
        self.df_locations: pd.DataFrame = None
        self.df_products: pd.DataFrame = None
        self.profile_results: Dict[str, Any] = {}

    def load_datasets(self) -> None:
        """Loads raw demand dataset and master entity tables."""
        print(f"[*] Loading raw demand data from: {self.raw_demand_path}")
        if self.raw_demand_path.suffix.lower() in [".xlsx", ".xls"]:
            self.df_demand = pd.read_excel(
                self.raw_demand_path,
                sheet_name=config.RAW_DEMAND_SHEET_NAME,
                engine="openpyxl"
            )
        else:
            self.df_demand = pd.read_csv(self.raw_demand_path)

        print(f"    Loaded demand dataset: {self.df_demand.shape[0]:,} rows, {self.df_demand.shape[1]} columns")

        if self.location_master_path.exists():
            print(f"[*] Loading location master from: {self.location_master_path}")
            self.df_locations = pd.read_csv(self.location_master_path)
        else:
            print(f"[!] Warning: Location master not found at {self.location_master_path}")

        if self.product_master_path.exists():
            print(f"[*] Loading product master from: {self.product_master_path}")
            if self.product_master_path.suffix.lower() in [".xlsx", ".xls"]:
                self.df_products = pd.read_excel(self.product_master_path, engine="openpyxl")
            else:
                self.df_products = pd.read_csv(self.product_master_path)
        else:
            print(f"[!] Warning: Product master not found at {self.product_master_path}")

    def profile_overview(self) -> Dict[str, Any]:
        """Calculates high-level dataset dimensions, memory, and missing cell ratios."""
        total_cells = self.df_demand.size
        total_nulls = int(self.df_demand.isnull().sum().sum())
        null_percentage = (total_nulls / total_cells) * 100 if total_cells > 0 else 0.0

        overview = {
            "total_rows": int(len(self.df_demand)),
            "total_columns": int(len(self.df_demand.columns)),
            "total_cells": int(total_cells),
            "total_missing_cells": total_nulls,
            "overall_missing_pct": round(null_percentage, 3),
            "memory_usage_mb": round(self.df_demand.memory_usage(deep=True).sum() / (1024 * 1024), 2),
        }
        return overview

    def profile_columns(self) -> List[Dict[str, Any]]:
        """Profiles individual columns: null counts, uniqueness, and value distributions."""
        col_profiles = []
        for col in self.df_demand.columns:
            s = self.df_demand[col]
            null_count = int(s.isnull().sum())
            null_pct = round((null_count / len(s)) * 100, 2)
            n_unique = int(s.nunique(dropna=True))

            info: Dict[str, Any] = {
                "column_name": col,
                "dtype": str(s.dtype),
                "null_count": null_count,
                "null_pct": null_pct,
                "unique_values": n_unique,
            }

            if pd.api.types.is_numeric_dtype(s):
                valid_num = s.dropna()
                info.update({
                    "min": float(valid_num.min()) if not valid_num.empty else None,
                    "max": float(valid_num.max()) if not valid_num.empty else None,
                    "mean": round(float(valid_num.mean()), 2) if not valid_num.empty else None,
                    "median": round(float(valid_num.median()), 2) if not valid_num.empty else None,
                    "std": round(float(valid_num.std()), 2) if not valid_num.empty else None,
                })
            else:
                top_values = s.value_counts(dropna=True).head(3).to_dict()
                info["top_3_values"] = {str(k): int(v) for k, v in top_values.items()}

            col_profiles.append(info)
        return col_profiles

    def check_integrity_and_keys(self) -> Dict[str, Any]:
        """Evaluates primary key uniqueness and composite key validity."""
        results = {}
        if "demand_id" in self.df_demand.columns:
            is_unique = self.df_demand["demand_id"].is_unique
            dup_count = int(self.df_demand["demand_id"].duplicated().sum())
            results["demand_id_is_unique"] = bool(is_unique)
            results["demand_id_duplicates"] = dup_count

        composite_cols = ["location_id", "product_id", "week_start_date"]
        if all(c in self.df_demand.columns for c in composite_cols):
            comp_dups = int(self.df_demand.duplicated(subset=composite_cols).sum())
            results["composite_key_unique"] = comp_dups == 0
            results["composite_key_duplicates"] = comp_dups

        if self.df_locations is not None and "location_id" in self.df_locations.columns:
            master_locs = set(self.df_locations["location_id"].dropna().unique())
            demand_locs = set(self.df_demand["location_id"].dropna().unique())
            orphan_locs = list(demand_locs - master_locs)
            results["location_referential_integrity"] = {
                "demand_locations_count": len(demand_locs),
                "master_locations_count": len(master_locs),
                "unmatched_location_ids": orphan_locs,
                "all_matched": len(orphan_locs) == 0,
            }

        if self.df_products is not None and "product_id" in self.df_products.columns:
            master_prods = set(self.df_products["product_id"].dropna().unique())
            demand_prods = set(self.df_demand["product_id"].dropna().unique())
            orphan_prods = list(demand_prods - master_prods)
            results["product_referential_integrity"] = {
                "demand_products_count": len(demand_prods),
                "master_products_count": len(master_prods),
                "unmatched_product_ids": orphan_prods,
                "all_matched": len(orphan_prods) == 0,
            }

        return results

    def check_anomalies(self) -> Dict[str, Any]:
        """Detects business logic anomalies (negative values, extreme discounts, outliers)."""
        anomalies = {}

        if "units_sold" in self.df_demand.columns:
            neg_units = int((self.df_demand["units_sold"] < 0).sum())
            anomalies["negative_units_sold"] = neg_units

        if "avg_selling_price_rs" in self.df_demand.columns:
            neg_price = int((self.df_demand["avg_selling_price_rs"] < 0).sum())
            anomalies["negative_selling_price"] = neg_price

        if "discount_pct" in self.df_demand.columns:
            invalid_discounts = int(((self.df_demand["discount_pct"] < 0) | (self.df_demand["discount_pct"] > 100)).sum())
            anomalies["invalid_discount_pct"] = invalid_discounts

        if "temperature_c" in self.df_demand.columns:
            temp_outliers = int(((self.df_demand["temperature_c"] < 5) | (self.df_demand["temperature_c"] > 50)).sum())
            anomalies["extreme_temperature_readings"] = temp_outliers

        return anomalies

    def run_profiling(self) -> Dict[str, Any]:
        """Runs complete profiling suite and saves report."""
        if self.df_demand is None:
            self.load_datasets()

        print("[*] Profiling overview and memory metrics...")
        overview = self.profile_overview()

        print("[*] Profiling column-level distributions...")
        col_profiles = self.profile_columns()

        print("[*] Checking key uniqueness and referential integrity...")
        integrity = self.check_integrity_and_keys()

        print("[*] Detecting data anomalies and business rule violations...")
        anomalies = self.check_anomalies()

        self.profile_results = {
            "overview": overview,
            "columns": col_profiles,
            "integrity_and_keys": integrity,
            "anomalies": anomalies,
        }

        # Save JSON Report
        json_path = config.REPORTS_DIR / "demand_data_profile.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.profile_results, f, indent=2, default=str)
        print(f"[OK] Saved JSON profile report to: {json_path}")

        # Save Markdown Report
        md_path = config.REPORTS_DIR / "demand_data_profile.md"
        self._generate_markdown_report(md_path)
        print(f"[OK] Saved Markdown profile report to: {md_path}")

        return self.profile_results

    def _generate_markdown_report(self, output_path: Path) -> None:
        """Formats profile results into a clean markdown document."""
        ov = self.profile_results["overview"]
        integ = self.profile_results["integrity_and_keys"]
        anom = self.profile_results["anomalies"]

        lines = [
            "# Raw Demand Dataset Profiling Report",
            f"\n**Source File**: `{self.raw_demand_path}`  ",
            f"**Total Records**: {ov['total_rows']:,}  ",
            f"**Total Features**: {ov['total_columns']}  ",
            f"**Overall Missing Cells**: {ov['total_missing_cells']} ({ov['overall_missing_pct']}%)  ",
            f"**Memory Usage**: {ov['memory_usage_mb']} MB\n",
            "## 1. Key Uniqueness & Referential Integrity",
            f"- **`demand_id` is unique**: `{integ.get('demand_id_is_unique')}` (Duplicates: {integ.get('demand_id_duplicates', 0)})",
            f"- **Composite Key `(location_id, product_id, week_start_date)` unique**: `{integ.get('composite_key_unique')}`",
        ]

        if "location_referential_integrity" in integ:
            loc = integ["location_referential_integrity"]
            loc_status = "Passed (100% match)" if loc.get("all_matched") else f"FAILED ({len(loc.get('unmatched_location_ids', []))} unmatched)"
            lines.append(f"- **Location Referential Integrity**: {loc_status}")

        if "product_referential_integrity" in integ:
            prod = integ["product_referential_integrity"]
            prod_status = "Passed (100% match)" if prod.get("all_matched") else f"FAILED ({len(prod.get('unmatched_product_ids', []))} unmatched)"
            lines.append(f"- **Product Referential Integrity**: {prod_status}")

        lines.extend([
            "\n## 2. Business Logic Anomalies",
            f"- Negative Units Sold: `{anom.get('negative_units_sold', 0)}`",
            f"- Negative Selling Price: `{anom.get('negative_selling_price', 0)}`",
            f"- Invalid Discount % (<0 or >100): `{anom.get('invalid_discount_pct', 0)}`",
            f"- Extreme Temperature Readings (<5 deg C or >50 deg C): `{anom.get('extreme_temperature_readings', 0)}`",
            "\n## 3. Column Summary Breakdown",
            "| Column Name | Data Type | Null Count | Null % | Unique Values | Sample / Stats |",
            "| :--- | :--- | :--- | :--- | :--- | :--- |",
        ])

        for c in self.profile_results["columns"]:
            if "min" in c:
                stats = f"min={c['min']}, max={c['max']}, mean={c['mean']}"
            else:
                top = list(c.get("top_3_values", {}).keys())
                stats = f"Top: {', '.join(str(k) for k in top[:2])}"
            lines.append(f"| `{c['column_name']}` | `{c['dtype']}` | {c['null_count']} | {c['null_pct']}% | {c['unique_values']} | {stats} |")

        output_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    profiler = DemandDataProfiler()
    profiler.run_profiling()
