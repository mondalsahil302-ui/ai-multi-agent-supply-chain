"""Quarantine queue and error logging for invalid ingestion records.

Invariants:
  - Invalid external data is NEVER written to canonical state collections.
  - Quarantined documents retain raw payload, validation failure reasons, source, and ingestion timestamp.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pymongo.database import Database

COL_QUARANTINE = "quarantine_data"
COL_INGESTION_ERRORS = "ingestion_errors"


def quarantine_record(
    db: Database,
    source: str,
    raw_payload: Dict[str, Any],
    reasons: List[str],
    region_id: Optional[str] = None
) -> str:
    """Isolates an invalid payload into quarantine_data and registers an ingestion error."""
    now = datetime.now(timezone.utc)
    quarantine_doc = {
        "source": source,
        "region_id": region_id or raw_payload.get("region_id"),
        "raw_payload": raw_payload,
        "reasons": reasons,
        "quarantined_at_utc": now,
        "status": "QUARANTINED"
    }
    res = db[COL_QUARANTINE].insert_one(quarantine_doc)
    doc_id = str(res.inserted_id)

    # Log ingestion error
    error_doc = {
        "quarantine_id": doc_id,
        "source": source,
        "region_id": region_id or raw_payload.get("region_id"),
        "error_count": len(reasons),
        "reasons": reasons,
        "occurred_at_utc": now
    }
    db[COL_INGESTION_ERRORS].insert_one(error_doc)
    return doc_id


def get_quarantine_count(db: Database, source: Optional[str] = None) -> int:
    """Returns count of quarantined documents."""
    query = {"source": source} if source else {}
    return db[COL_QUARANTINE].count_documents(query)


def get_latest_quarantined_records(db: Database, limit: int = 10) -> List[Dict]:
    """Retrieves recent quarantined records for observability/dashboard."""
    return list(db[COL_QUARANTINE].find({}, {"_id": 0}).sort("quarantined_at_utc", -1).limit(limit))
