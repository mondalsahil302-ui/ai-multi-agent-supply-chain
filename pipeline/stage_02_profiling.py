"""
Stage 02: Data Profiling — schema, column, missing-value, duplicate, temporal, geographic,
categorical, and data quality issue profiles.
"""

import pandas as pd
import numpy as np
import openpyxl
import warnings
from pathlib import Path
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

BASE = Path(r"D:\ai-multi-agent-supply-chain")
RAW = BASE / "Datasets" / "raw"
PROFILE = BASE / "data" / "02_profile"
QUARANTINE = BASE / "data" / "data_quarantine"

schema_rows = []
column_rows = []
missing_rows = []
dup_rows = []
temporal_rows = []
geo_rows = []
cat_rows = []
quality_rows = []

QID = [0]

def qid():
    QID[0] += 1
    return f"QI-{QID[0]:04d}"


def profile_df(df, source_id, source_file, sheet_name, domain, source_type):
    """Profile a DataFrame and append rows to global lists."""
    n_rows, n_cols = df.shape

    # ── Schema row ──────────────────────────────────────────────────────────
    col_names = df.columns.tolist()
    blank_headers = [c for c in col_names if str(c).strip() == "" or str(c).lower().startswith("unnamed")]
    dup_headers = [c for c in col_names if col_names.count(c) > 1]

    schema_rows.append(
        {
            "source_id": source_id,
            "source_file": source_file,
            "sheet_name": sheet_name,
            "domain": domain,
            "source_type": source_type,
            "row_count": n_rows,
            "col_count": n_cols,
            "column_names": "|".join(str(c) for c in col_names),
            "blank_headers": "|".join(blank_headers) if blank_headers else None,
            "duplicate_headers": "|".join(dup_headers) if dup_headers else None,
            "profiled_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    if blank_headers:
        quality_rows.append(
            {
                "check_id": qid(),
                "source_id": source_id,
                "dataset": f"{source_file}/{sheet_name}",
                "check_name": "BLANK_HEADERS",
                "expected": "All columns have names",
                "actual": f"Blank/unnamed: {blank_headers}",
                "status": "WARNING",
                "severity": "MEDIUM",
                "failed_record_count": len(blank_headers),
                "remediation": "Rename or quarantine unnamed columns",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    # ── Column profiles ──────────────────────────────────────────────────────
    date_cols = []
    geo_fields = []

    for col in df.columns:
        s = df[col]
        dtype = str(s.dtype)
        null_count = int(s.isna().sum())
        null_pct = round(null_count / n_rows * 100, 2) if n_rows else 0
        unique_count = int(s.nunique(dropna=True))

        # detect date columns
        is_date = False
        min_date = max_date = None
        if "date" in str(col).lower() or "time" in str(col).lower() or dtype in ("datetime64[ns]",):
            is_date = True
            try:
                dts = pd.to_datetime(s, errors="coerce")
                min_date = str(dts.min()) if not dts.isna().all() else None
                max_date = str(dts.max()) if not dts.isna().all() else None
                date_cols.append(col)
            except Exception:
                pass

        # detect numeric ranges
        num_min = num_max = num_mean = None
        if dtype in ("int64", "float64", "int32", "float32"):
            try:
                num_min = float(s.min())
                num_max = float(s.max())
                num_mean = float(s.mean())
            except Exception:
                pass

        # detect suspicious: negative where not expected
        suspicious = None
        if dtype in ("int64", "float64") and num_min is not None and num_min < 0:
            neg_count = int((s < 0).sum())
            if neg_count > 0:
                suspicious = f"Negative values: {neg_count}"
                quality_rows.append(
                    {
                        "check_id": qid(),
                        "source_id": source_id,
                        "dataset": f"{source_file}/{sheet_name}",
                        "check_name": f"NEGATIVE_VALUES_{col}",
                        "expected": "Non-negative",
                        "actual": f"{neg_count} negative values",
                        "status": "WARNING",
                        "severity": "MEDIUM",
                        "failed_record_count": neg_count,
                        "remediation": "Investigate if these represent adjustments/returns",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

        # geographic detection
        if any(k in str(col).lower() for k in ("lat", "lon", "lng", "longitude", "latitude", "x_coord", "y_coord")):
            geo_fields.append(col)

        column_rows.append(
            {
                "source_id": source_id,
                "source_file": source_file,
                "sheet_name": sheet_name,
                "column_name": col,
                "dtype": dtype,
                "null_count": null_count,
                "null_pct": null_pct,
                "unique_count": unique_count,
                "min_value": num_min,
                "max_value": num_max,
                "mean_value": num_mean,
                "is_date": is_date,
                "min_date": min_date,
                "max_date": max_date,
                "suspicious": suspicious,
            }
        )

        # missing value profile
        if null_count > 0:
            missing_rows.append(
                {
                    "source_id": source_id,
                    "source_file": source_file,
                    "sheet_name": sheet_name,
                    "column_name": col,
                    "null_count": null_count,
                    "null_pct": null_pct,
                    "severity": "HIGH" if null_pct > 20 else ("MEDIUM" if null_pct > 5 else "LOW"),
                }
            )

        # categorical value profile (low cardinality non-numeric)
        if dtype == "object" and unique_count <= 50:
            try:
                vc = s.value_counts(dropna=True).head(10)
                cat_rows.append(
                    {
                        "source_id": source_id,
                        "source_file": source_file,
                        "sheet_name": sheet_name,
                        "column_name": col,
                        "unique_count": unique_count,
                        "top_values": "|".join(f"{k}:{v}" for k, v in vc.items()),
                    }
                )
            except Exception:
                pass

    # ── Duplicate rows ───────────────────────────────────────────────────────
    dup_count = int(df.duplicated().sum())
    dup_rows.append(
        {
            "source_id": source_id,
            "source_file": source_file,
            "sheet_name": sheet_name,
            "duplicate_row_count": dup_count,
            "total_rows": n_rows,
            "dup_pct": round(dup_count / n_rows * 100, 2) if n_rows else 0,
        }
    )

    if dup_count > 0:
        quality_rows.append(
            {
                "check_id": qid(),
                "source_id": source_id,
                "dataset": f"{source_file}/{sheet_name}",
                "check_name": "DUPLICATE_ROWS",
                "expected": "No duplicates",
                "actual": f"{dup_count} duplicate rows",
                "status": "WARNING",
                "severity": "MEDIUM",
                "failed_record_count": dup_count,
                "remediation": "Investigate business keys before dropping",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    # ── Temporal coverage ────────────────────────────────────────────────────
    if date_cols:
        for dc in date_cols:
            try:
                dts = pd.to_datetime(df[dc], errors="coerce")
                temporal_rows.append(
                    {
                        "source_id": source_id,
                        "source_file": source_file,
                        "sheet_name": sheet_name,
                        "date_column": dc,
                        "min_date": str(dts.min()),
                        "max_date": str(dts.max()),
                        "distinct_dates": int(dts.nunique()),
                        "null_count": int(dts.isna().sum()),
                    }
                )
            except Exception:
                pass

    # ── Geographic coverage ──────────────────────────────────────────────────
    if geo_fields:
        lat_col = next((c for c in geo_fields if "lat" in str(c).lower()), None)
        lon_col = next((c for c in geo_fields if "lon" in str(c).lower() or "lng" in str(c).lower()), None)
        if lat_col and lon_col:
            try:
                lats = pd.to_numeric(df[lat_col], errors="coerce")
                lons = pd.to_numeric(df[lon_col], errors="coerce")
                geo_rows.append(
                    {
                        "source_id": source_id,
                        "source_file": source_file,
                        "sheet_name": sheet_name,
                        "lat_col": lat_col,
                        "lon_col": lon_col,
                        "lat_min": float(lats.min()),
                        "lat_max": float(lats.max()),
                        "lon_min": float(lons.min()),
                        "lon_max": float(lons.max()),
                        "null_coords": int(lats.isna().sum() + lons.isna().sum()),
                    }
                )
                # Validate Kolkata bounds: lat 22.3–22.7, lon 88.2–88.5
                bad_lat = ((lats < 22.0) | (lats > 23.0)).sum()
                bad_lon = ((lons < 88.0) | (lons > 89.0)).sum()
                if bad_lat > 0 or bad_lon > 0:
                    quality_rows.append(
                        {
                            "check_id": qid(),
                            "source_id": source_id,
                            "dataset": f"{source_file}/{sheet_name}",
                            "check_name": "COORDINATE_OUT_OF_KOLKATA_BOUNDS",
                            "expected": "lat 22-23, lon 88-89",
                            "actual": f"bad_lat={bad_lat}, bad_lon={bad_lon}",
                            "status": "WARNING",
                            "severity": "HIGH",
                            "failed_record_count": int(bad_lat + bad_lon),
                            "remediation": "Review coordinates manually",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
            except Exception:
                pass


# ── Load and profile each dataset ────────────────────────────────────────────

def load_xlsx_sheet(path, sheet):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return pd.DataFrame()
    headers = [str(h) if h is not None else f"_unnamed_{i}" for i, h in enumerate(rows[0])]
    return pd.DataFrame(rows[1:], columns=headers)


# SRC-001 locations
df = pd.read_csv(RAW / "master" / "locations.csv.csv")
profile_df(df, "SRC-001", "locations.csv.csv", "N/A", "Location", "MASTER")

# SRC-002 products.csv
df = pd.read_csv(RAW / "master" / "products.csv")
profile_df(df, "SRC-002", "products.csv", "N/A", "Product", "MASTER")

# SRC-003 Final product list.xlsx
for sh in ["product_master", "category_summary"]:
    df = load_xlsx_sheet(RAW / "master" / "Final product list.xlsx", sh)
    profile_df(df, "SRC-003", "Final product list.xlsx", sh, "Product", "MASTER")

# SRC-004 festival_calendar
df = pd.read_csv(RAW / "external" / "festival_calendar.csv")
profile_df(df, "SRC-004", "festival_calendar.csv", "N/A", "Festival/Calendar", "REFERENCE")

# SRC-005 weather_weekly
df = pd.read_csv(RAW / "external" / "weather_weekly.csv")
profile_df(df, "SRC-005", "weather_weekly.csv", "N/A", "Weather", "EXTERNAL_CONTEXT")

# SRC-006 Demand of last 2 years
df = load_xlsx_sheet(RAW / "demand" / "Demand of last 2 years.xlsx", "demand_training_data")
profile_df(df, "SRC-006", "Demand of last 2 years.xlsx", "demand_training_data", "Demand", "HISTORICAL_FACT|TRAINING_DATA")

# SRC-007 final_demand_agent_training
df = load_xlsx_sheet(RAW / "demand" / "final_demand_agent_training_2_years_kolkata (1).xlsx", "demand_training_data")
profile_df(df, "SRC-007", "final_demand_agent_training_2_years_kolkata.xlsx", "demand_training_data", "Demand", "TRAINING_DATA")

# SRC-008 sales_history - LFS pointer
quality_rows.append(
    {
        "check_id": qid(),
        "source_id": "SRC-008",
        "dataset": "sales_history.xlsx",
        "check_name": "SALES_HISTORY_SOURCE_UNAVAILABLE",
        "expected": "XLSX file with sales transaction data",
        "actual": "Git-LFS pointer file. OID: fc8022e6248ccb8725f6ff8cb9c70aa91a6f76aeb99bce62db5866f7c902e6e5. Expected size: 177,644,415 bytes",
        "status": "BLOCKED_BY_SOURCE",
        "severity": "CRITICAL",
        "failed_record_count": -1,
        "remediation": "Run `git lfs pull` to fetch the real file. Until then, FACT_SALES output is unavailable.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
)

# SRC-009 inventory_stock - all main sheets
for sh in ["Inventory_Position", "Shelf_Master", "Product_Shelf_Assignment"]:
    df = load_xlsx_sheet(RAW / "inventory" / "inventory_stock.xlsx", sh)
    profile_df(df, "SRC-009", "inventory_stock.xlsx", sh, "Inventory", "SNAPSHOT")

# SRC-010 inventory_transactions - LFS pointer
quality_rows.append(
    {
        "check_id": qid(),
        "source_id": "SRC-010",
        "dataset": "inventory_transactions.xlsx",
        "check_name": "INVENTORY_TRANSACTIONS_SOURCE_UNAVAILABLE",
        "expected": "XLSX file with inventory transaction records",
        "actual": "Git-LFS pointer file. OID: 5fc053bab861bc764e13ac15b74ebcab11b4bf35403f436eadd68d727a06a749. Expected size: 55,855,339 bytes",
        "status": "BLOCKED_BY_SOURCE",
        "severity": "CRITICAL",
        "failed_record_count": -1,
        "remediation": "Run `git lfs pull` to fetch the real file. Until then, FACT_INVENTORY_TRANSACTION output is unavailable.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
)

# SRC-011 supplier_inventory - key sheets
for sh in ["Supplier_Master", "Area_Master", "Area_Supplier_Options", "Supplier_Product_Catalog"]:
    df = load_xlsx_sheet(RAW / "supplier" / "supplier_inventory.xlsx", sh)
    profile_df(df, "SRC-011", "supplier_inventory.xlsx", sh, "Supplier", "MASTER|BRIDGE")

# SRC-012 warehouses.xlsx
df = load_xlsx_sheet(RAW / "warehouse" / "warehouses.xlsx", "warehouse")
profile_df(df, "SRC-012", "warehouses.xlsx", "warehouse", "Warehouse", "MASTER")

# SRC-013 final_warehouse_dataset_kolkata.xlsx
df = load_xlsx_sheet(RAW / "warehouse" / "final_warehouse_dataset_kolkata.xlsx", "warehouse")
profile_df(df, "SRC-013", "final_warehouse_dataset_kolkata.xlsx", "warehouse", "Warehouse", "MASTER|SUPPORTING")

# Supplier catalog unmapped column quality issue
quality_rows.append(
    {
        "check_id": qid(),
        "source_id": "SRC-011",
        "dataset": "supplier_inventory.xlsx/Supplier_Product_Catalog",
        "check_name": "SUPPLIER_CATALOG_UNMAPPED_COLUMN",
        "expected": "12 labeled columns",
        "actual": "13 columns found. Column 13 (index 12) header is None. Values appear to be supply_status ('Available'). Analysis: Header row has 12 labels but 13 data columns. Column alignment appears shifted: col9=supplier_cost_price_rs, col10=numeric (unit quantity ratio, ~35.71), col11=supplied_unit_size, col12=supply_status. Col10 is UNLABELED and semantically unresolved — values appear to be a percentage or unit conversion ratio.",
        "status": "WARNING",
        "severity": "HIGH",
        "failed_record_count": 8000,
        "remediation": "Column preserved as 'unmapped_col_10_quarantine'. Values range ~9-200, possibly MOQ fraction or unit_quantity_ratio. Requires domain expert review.",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
)

# ── Write profile outputs ─────────────────────────────────────────────────────
pd.DataFrame(schema_rows).to_csv(PROFILE / "schema_profile.csv", index=False)
pd.DataFrame(column_rows).to_csv(PROFILE / "column_profile.csv", index=False)
pd.DataFrame(missing_rows).to_csv(PROFILE / "missing_value_profile.csv", index=False)
pd.DataFrame(dup_rows).to_csv(PROFILE / "duplicate_profile.csv", index=False)
pd.DataFrame(temporal_rows).to_csv(PROFILE / "temporal_coverage.csv", index=False)
pd.DataFrame(geo_rows).to_csv(PROFILE / "geographic_coverage.csv", index=False)
pd.DataFrame(cat_rows).to_csv(PROFILE / "categorical_value_profile.csv", index=False)
pd.DataFrame(quality_rows).to_csv(PROFILE / "data_quality_issue_log.csv", index=False)

print("✅ Stage 02 profiling complete.")
print(f"  schema_profile: {len(schema_rows)} datasets")
print(f"  column_profile: {len(column_rows)} columns")
print(f"  missing_value: {len(missing_rows)} issues")
print(f"  duplicate: {len(dup_rows)} datasets")
print(f"  temporal: {len(temporal_rows)} date columns")
print(f"  geographic: {len(geo_rows)} geo datasets")
print(f"  categorical: {len(cat_rows)} categorical columns")
print(f"  quality_issues: {len(quality_rows)} issues")

