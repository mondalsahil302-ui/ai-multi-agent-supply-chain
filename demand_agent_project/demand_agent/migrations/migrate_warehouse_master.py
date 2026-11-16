"""Reversible migration: create and populate warehouse_master collection.

Usage:
  python -m demand_agent.migrations.migrate_warehouse_master --dry-run
  python -m demand_agent.migrations.migrate_warehouse_master
  python -m demand_agent.migrations.migrate_warehouse_master --rollback
"""
import argparse
import logging
from pymongo import ASCENDING

from demand_agent.config import get_settings
from demand_agent.db import get_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)

WAREHOUSES = [
    {"warehouse_id": "WH-001", "warehouse_name": "South City Mall Warehouse", "area": "Jadavpur", "city": "Kolkata", "capacity_units": 20000, "daily_dispatch_capacity_units": 7000, "location_id": "KOL-LOC-001", "is_operational": True},
    {"warehouse_id": "WH-002", "warehouse_name": "Quest Mall Warehouse", "area": "Park Circus", "city": "Kolkata", "capacity_units": 16000, "daily_dispatch_capacity_units": 5600, "location_id": "KOL-LOC-002", "is_operational": False},
    {"warehouse_id": "WH-003", "warehouse_name": "Acropolis Mall Warehouse", "area": "Kasba", "city": "Kolkata", "capacity_units": 18000, "daily_dispatch_capacity_units": 6300, "location_id": "KOL-LOC-003", "is_operational": False},
    {"warehouse_id": "WH-004", "warehouse_name": "Mani Square Warehouse", "area": "Kankurgachi", "city": "Kolkata", "capacity_units": 18000, "daily_dispatch_capacity_units": 6300, "location_id": "KOL-LOC-004", "is_operational": False},
    {"warehouse_id": "WH-005", "warehouse_name": "City Centre I Warehouse", "area": "Salt Lake", "city": "Kolkata", "capacity_units": 20000, "daily_dispatch_capacity_units": 7000, "location_id": "KOL-LOC-005", "is_operational": False},
    {"warehouse_id": "WH-006", "warehouse_name": "City Centre II Warehouse", "area": "New Town", "city": "Kolkata", "capacity_units": 24000, "daily_dispatch_capacity_units": 8400, "location_id": "KOL-LOC-006", "is_operational": False},
    {"warehouse_id": "WH-007", "warehouse_name": "Axis Mall Warehouse", "area": "New Town", "city": "Kolkata", "capacity_units": 18000, "daily_dispatch_capacity_units": 6300, "location_id": "KOL-LOC-007", "is_operational": False},
    {"warehouse_id": "WH-008", "warehouse_name": "Lake Mall Warehouse", "area": "Rashbehari", "city": "Kolkata", "capacity_units": 12000, "daily_dispatch_capacity_units": 4200, "location_id": "KOL-LOC-008", "is_operational": False},
    {"warehouse_id": "WH-009", "warehouse_name": "Forum Courtyard Warehouse", "area": "Elgin", "city": "Kolkata", "capacity_units": 15000, "daily_dispatch_capacity_units": 5250, "location_id": "KOL-LOC-009", "is_operational": False},
    {"warehouse_id": "WH-010", "warehouse_name": "Diamond Plaza Warehouse", "area": "Dum Dum", "city": "Kolkata", "capacity_units": 16000, "daily_dispatch_capacity_units": 5600, "location_id": "KOL-LOC-010", "is_operational": False},
    {"warehouse_id": "WH-011", "warehouse_name": "Gariahat Mall Warehouse", "area": "Gariahat", "city": "Kolkata", "capacity_units": 13000, "daily_dispatch_capacity_units": 4550, "location_id": "KOL-LOC-011", "is_operational": False},
    {"warehouse_id": "WH-012", "warehouse_name": "Merlin Homeland Warehouse", "area": "Bhowanipore", "city": "Kolkata", "capacity_units": 12000, "daily_dispatch_capacity_units": 4200, "location_id": "KOL-LOC-012", "is_operational": False},
    {"warehouse_id": "WH-013", "warehouse_name": "Metro Plaza Warehouse", "area": "Park Street", "city": "Kolkata", "capacity_units": 10000, "daily_dispatch_capacity_units": 3500, "location_id": "KOL-LOC-013", "is_operational": False},
    {"warehouse_id": "WH-014", "warehouse_name": "E-Mall Warehouse", "area": "Chittaranjan Avenue", "city": "Kolkata", "capacity_units": 11000, "daily_dispatch_capacity_units": 3850, "location_id": "KOL-LOC-014", "is_operational": False},
    {"warehouse_id": "WH-015", "warehouse_name": "The Enclave Mall Warehouse", "area": "Alipore", "city": "Kolkata", "capacity_units": 12000, "daily_dispatch_capacity_units": 4200, "location_id": "KOL-LOC-015", "is_operational": False},
]


def run_migration(dry_run: bool = False, rollback: bool = False):
    s = get_settings()
    db = get_db(s)
    col_name = "warehouse_master"
    col = db[col_name]

    if rollback:
        if dry_run:
            log.info(f"DRY RUN: Would drop collection '{col_name}' and remove warehouse index links.")
            return {"status": "DRY_RUN_ROLLBACK", "target": col_name}
        col.drop()
        log.info(f"ROLLBACK SUCCESS: Dropped collection '{col_name}'.")
        return {"status": "ROLLED_BACK", "target": col_name}

    if dry_run:
        log.info(f"DRY RUN: Would upsert {len(WAREHOUSES)} warehouses into '{col_name}' and create indexes.")
        for wh in WAREHOUSES[:3]:
            log.info(f"  Sample doc: {wh['warehouse_id']} -> {wh['warehouse_name']} ({wh['location_id']})")
        log.info(f"  Indexes to create: unique('warehouse_id'), unique('location_id')")
        return {"status": "DRY_RUN_MIGRATE", "records_to_upsert": len(WAREHOUSES)}

    # Apply migration
    upserted, modified = 0, 0
    for wh in WAREHOUSES:
        res = col.replace_one(
            {"_id": wh["warehouse_id"]},
            {"_id": wh["warehouse_id"], **wh},
            upsert=True
        )
        if res.upserted_id:
            upserted += 1
        elif res.modified_count > 0:
            modified += 1

    col.create_index([("warehouse_id", ASCENDING)], unique=True, name="uq_warehouse_id")
    col.create_index([("location_id", ASCENDING)], unique=True, name="uq_warehouse_location_id")

    log.info(f"MIGRATION SUCCESS: '{col_name}' updated. Upserted: {upserted}, Modified: {modified}, Total docs: {col.count_documents({})}")
    return {"status": "APPLIED", "upserted": upserted, "modified": modified, "total": col.count_documents({})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Warehouse master migration.")
    parser.add_argument("--dry-run", action="store_true", help="Preview migration without writing.")
    parser.add_argument("--rollback", action="store_true", help="Revert migration by dropping warehouse_master.")
    args = parser.parse_args()

    run_migration(dry_run=args.dry_run, rollback=args.rollback)
