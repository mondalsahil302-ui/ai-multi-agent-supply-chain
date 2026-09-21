"""
Stage 01: Setup directory structure and create raw-layer registry.
Copies source files into data/01_raw and records metadata.
"""

import os, shutil, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"D:\ai-multi-agent-supply-chain")
DATA = BASE / "data"

# ── Create all pipeline directories ─────────────────────────────────────────
LAYERS = [
    "01_raw",
    "02_profile",
    "03_staging",
    "04_standardized",
    "05_entity_mapping",
    "06_curated",
    "07_features",
    "08_validation",
    "09_agent_ready",
    "10_documentation",
    "data_quarantine",
]
for layer in LAYERS:
    (DATA / layer).mkdir(parents=True, exist_ok=True)

print("✅ All pipeline directories created.")

# ── Source file registry ─────────────────────────────────────────────────────
RAW = BASE / "Datasets" / "raw"

SOURCES = [
    {
        "source_id": "SRC-001",
        "source_file": str(RAW / "master" / "locations.csv.csv"),
        "file_format": "CSV",
        "sheet_name": None,
        "source_type": "MASTER",
        "domain": "Location",
        "description": "40 Kolkata region location IDs and names",
    },
    {
        "source_id": "SRC-002",
        "source_file": str(RAW / "master" / "products.csv"),
        "file_format": "CSV",
        "sheet_name": None,
        "source_type": "MASTER",
        "domain": "Product",
        "description": "200-product master with 5 unit sizes and pricing per product",
    },
    {
        "source_id": "SRC-003",
        "source_file": str(RAW / "master" / "Final product list.xlsx"),
        "file_format": "XLSX",
        "sheet_name": "product_master|category_summary|README",
        "source_type": "MASTER",
        "domain": "Product",
        "description": "Excel version of product master; also contains category_summary and README",
    },
    {
        "source_id": "SRC-004",
        "source_file": str(RAW / "external" / "festival_calendar.csv"),
        "file_format": "CSV",
        "sheet_name": None,
        "source_type": "REFERENCE",
        "domain": "Festival/Calendar",
        "description": "36 festival/holiday events across 2024-2025",
    },
    {
        "source_id": "SRC-005",
        "source_file": str(RAW / "external" / "weather_weekly.csv"),
        "file_format": "CSV",
        "sheet_name": None,
        "source_type": "EXTERNAL_CONTEXT",
        "domain": "Weather",
        "description": "105 weekly weather observations (2024-2026) for Kolkata",
    },
    {
        "source_id": "SRC-006",
        "source_file": str(RAW / "demand" / "Demand of last 2 years.xlsx"),
        "file_format": "XLSX",
        "sheet_name": "demand_training_data|data_dictionary|README|data_sources|quality_checks|Reference_Key_Spec|Product_Universe|Region_Week_Index|Backend_QA|Linked_Architecture",
        "source_type": "HISTORICAL_FACT|TRAINING_DATA",
        "domain": "Demand",
        "description": "Primary demand dataset: 27,800 rows x 44 cols, 40 regions x 200 products x 139 weeks (synthetic-training data with weather+festival context)",
    },
    {
        "source_id": "SRC-007",
        "source_file": str(RAW / "demand" / "final_demand_agent_training_2_years_kolkata (1).xlsx"),
        "file_format": "XLSX",
        "sheet_name": "demand_training_data|data_dictionary|README",
        "source_type": "TRAINING_DATA",
        "domain": "Demand",
        "description": "Secondary demand training dataset: 20,800 rows x 34 cols, 40 regions x 5 products x 104 weeks (synthetic)",
    },
    {
        "source_id": "SRC-008",
        "source_file": str(RAW / "demand" / "sales_history.xlsx"),
        "file_format": "XLSX_LFS_POINTER",
        "sheet_name": None,
        "source_type": "HISTORICAL_FACT",
        "domain": "Sales",
        "description": "BLOCKED: Git-LFS pointer. Underlying sales history not available locally. OID: fc8022e6248ccb8725f6ff8cb9c70aa91a6f76aeb99bce62db5866f7c902e6e5. Expected size: 177,644,415 bytes.",
    },
    {
        "source_id": "SRC-009",
        "source_file": str(RAW / "inventory" / "inventory_stock.xlsx"),
        "file_format": "XLSX",
        "sheet_name": "README|Product_Master|Warehouse_Master|Shelf_Master|Product_Shelf_Assignment|Inventory_Position|Inventory_Valuation|Inventory_Control|Transaction_File_Reference|Data_Dictionary|QA",
        "source_type": "SNAPSHOT",
        "domain": "Inventory",
        "description": "Inventory snapshot: 3,000 product-warehouse positions across 15 warehouses x 200 products. Snapshot date: 2026-08-31.",
    },
    {
        "source_id": "SRC-010",
        "source_file": str(RAW / "inventory" / "inventory_transactions.xlsx"),
        "file_format": "XLSX_LFS_POINTER",
        "sheet_name": None,
        "source_type": "TRANSACTION",
        "domain": "Inventory",
        "description": "BLOCKED: Git-LFS pointer. Underlying transaction data not available locally. OID: 5fc053bab861bc764e13ac15b74ebcab11b4bf35403f436eadd68d727a06a749. Expected size: 55,855,339 bytes.",
    },
    {
        "source_id": "SRC-011",
        "source_file": str(RAW / "supplier" / "supplier_inventory.xlsx"),
        "file_format": "XLSX",
        "sheet_name": "README|Area_Master|Supplier_Master|Area_Supplier_Options|Supplier_Product_Catalog|Product_Master_Reference|Warehouse_Master_Reference|Data_Dictionary|QA",
        "source_type": "MASTER|BRIDGE",
        "domain": "Supplier",
        "description": "Supplier dataset: 200 suppliers, 8,000 catalog rows, 40-area location master, area-supplier options",
    },
    {
        "source_id": "SRC-012",
        "source_file": str(RAW / "warehouse" / "warehouses.xlsx"),
        "file_format": "XLSX",
        "sheet_name": "warehouse|README|Data_Dictionary|QA",
        "source_type": "MASTER",
        "domain": "Warehouse",
        "description": "Primary warehouse master: 15 warehouses with vehicle counts, operating hours, dispatch capacity",
    },
    {
        "source_id": "SRC-013",
        "source_file": str(RAW / "warehouse" / "final_warehouse_dataset_kolkata.xlsx"),
        "file_format": "XLSX",
        "sheet_name": "warehouse|README",
        "source_type": "MASTER|SUPPORTING",
        "domain": "Warehouse",
        "description": "Secondary warehouse dataset: 15 warehouses with storage_type, x/y coordinates, status",
    },
]

# Copy files to 01_raw and record metadata
import pandas as pd

rows = []
for s in SOURCES:
    src = Path(s["source_file"])
    dst = DATA / "01_raw" / src.name
    provenance = "Datasets/raw"

    if "XLSX_LFS_POINTER" in s["file_format"]:
        file_size = src.stat().st_size if src.exists() else 0
        file_status = "BLOCKED_LFS_POINTER"
        sha256 = "N/A (LFS pointer)"
    elif src.exists():
        file_size = src.stat().st_size
        with open(src, "rb") as fh:
            sha256 = hashlib.sha256(fh.read()).hexdigest()
        if not dst.exists():
            shutil.copy2(src, dst)
        file_status = "AVAILABLE"
    else:
        file_size = 0
        sha256 = "N/A"
        file_status = "NOT_FOUND"

    rows.append(
        {
            "source_id": s["source_id"],
            "source_file": src.name,
            "source_path": str(src),
            "raw_copy_path": str(dst),
            "file_format": s["file_format"],
            "file_size_bytes": file_size,
            "sheet_name": s["sheet_name"],
            "source_type": s["source_type"],
            "domain": s["domain"],
            "description": s["description"],
            "sha256": sha256,
            "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
            "source_status": file_status,
            "provenance": provenance,
        }
    )

df = pd.DataFrame(rows)
df.to_csv(DATA / "02_profile" / "source_registry.csv", index=False)
print("✅ source_registry.csv created with", len(df), "entries")
print(df[["source_id", "source_file", "source_status", "domain"]].to_string(index=False))

