"""MongoDB persistence for validated demand-agent ingestion records."""

from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.database.upsert_manager import (
    UpsertReport,
    UpsertResult,
)

__all__ = ["MongoDatabase", "UpsertReport", "UpsertResult"]
