"""Warehouse master repository and entity resolver.

Supports:
  - Querying warehouse metadata
  - Listing all registered warehouses
  - Resolving warehouse_id (e.g. 'WH-001') <-> region_id ('KOL-LOC-001')
"""
from typing import Dict, List, Optional, Tuple
from pymongo.database import Database

COL_WAREHOUSE_MASTER = "warehouse_master"


def list_warehouses(db: Database) -> List[Dict]:
    """Returns all warehouses ordered by warehouse_id."""
    return list(db[COL_WAREHOUSE_MASTER].find({}, {"_id": 0}).sort("warehouse_id", 1))


def get_warehouse(db: Database, warehouse_id: str) -> Optional[Dict]:
    """Fetches single warehouse by warehouse_id."""
    return db[COL_WAREHOUSE_MASTER].find_one({"warehouse_id": warehouse_id}, {"_id": 0})


def get_warehouse_by_location(db: Database, location_id: str) -> Optional[Dict]:
    """Fetches single warehouse by location_id (region_id)."""
    return db[COL_WAREHOUSE_MASTER].find_one({"location_id": location_id}, {"_id": 0})


def resolve_warehouse_and_region(db: Database, entity_id: str) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
    """Resolves whether entity_id is a warehouse_id or region_id.

    Returns:
        (warehouse_id, region_id, warehouse_doc)
    """
    if entity_id.startswith("WH-"):
        wh = get_warehouse(db, entity_id)
        if wh:
            return wh["warehouse_id"], wh["location_id"], wh
        return entity_id, None, None
    elif entity_id.startswith("KOL-LOC-"):
        wh = get_warehouse_by_location(db, entity_id)
        if wh:
            return wh["warehouse_id"], wh["location_id"], wh
        return None, entity_id, None
    else:
        # Try both
        wh = get_warehouse(db, entity_id) or get_warehouse_by_location(db, entity_id)
        if wh:
            return wh["warehouse_id"], wh["location_id"], wh
        return None, None, None
