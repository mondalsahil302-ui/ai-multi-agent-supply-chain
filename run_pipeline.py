"""Demand Dataset ETL & Standardization Pipeline Orchestrator.

Executes:
1. Profiling (Data quality, null ratios, anomaly detection, referential integrity)
2. Staging & Standardization (Column hygiene, date casting, flag normalization, imputation)
3. Entity Mapping (Master entity joins, SKU variant unpivoting, target agent schema generation)

Usage:
    python run_pipeline.py --all
    python run_pipeline.py --profile
    python run_pipeline.py --stage
    python run_pipeline.py --map
"""

import argparse
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from src.profiling import DemandDataProfiler
from src.staging import DemandDataStager
from src.entity_mapping import DemandEntityMapper
from src import config


def main():
    parser = argparse.ArgumentParser(description="Demand Data ETL Pipeline Orchestrator")
    parser.add_argument("--profile", action="store_true", help="Run dataset profiling and generate reports")
    parser.add_argument("--stage", action="store_true", help="Run staging and data standardization")
    parser.add_argument("--map", action="store_true", help="Run entity mapping and generate agent dataset")
    parser.add_argument("--all", action="store_true", help="Execute complete end-to-end pipeline")

    args = parser.parse_args()

    if not (args.profile or args.stage or args.map or args.all):
        args.all = True

    start_time = time.time()
    print("=" * 70)
    print("      AI MULTI-AGENT SUPPLY CHAIN - DEMAND DATA PIPELINE")
    print("=" * 70)
    print(f"Raw Input File:     {config.RAW_DEMAND_FILE}")
    print(f"Location Master:    {config.LOCATION_MASTER_FILE}")
    print(f"Product Master:     {config.PRODUCT_MASTER_FILE}")
    print(f"Output Directory:   {config.PROCESSED_DIR}")
    print("=" * 70)

    raw_df = None

    if args.all or args.profile:
        print("\n>>> STEP 1: PROFILING RAW DEMAND DATASET <<<")
        profiler = DemandDataProfiler()
        profiler.run_profiling()
        raw_df = profiler.df_demand

    df_staged = None
    if args.all or args.stage:
        print("\n>>> STEP 2: STAGING & STANDARDIZATION <<<")
        stager = DemandDataStager()
        df_staged = stager.run_staging(df_input=raw_df)

    if args.all or args.map:
        print("\n>>> STEP 3: ENTITY RESOLUTION & MAPPING <<<")
        mapper = DemandEntityMapper()
        mapper.run_entity_mapping(df_input=df_staged)

    elapsed = round(time.time() - start_time, 2)
    print("=" * 70)
    print(f"[OK] Pipeline execution finished successfully in {elapsed} seconds.")
    print("=" * 70)


if __name__ == "__main__":
    main()
