import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from demand_ingestion.database.collections import INGESTION_RUNS
from demand_ingestion.database.mongodb import MongoDatabase
from demand_ingestion.database.upsert_manager import upsert_records

logger = logging.getLogger(__name__)


class IngestionRunStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    FAILED = "FAILED"


class IngestionRun(BaseModel):
    """Auditable status and reconciliation counters for one execution."""

    model_config = ConfigDict(extra="forbid")

    ingestion_run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex}")
    source_name: str
    command_name: str
    start_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end_timestamp: datetime | None = None
    status: IngestionRunStatus = IngestionRunStatus.RUNNING
    records_received: int = 0
    records_validated: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    records_failed: int = 0
    records_quarantined: int = 0
    failed_regions: list[str] = Field(default_factory=list)
    error_summary: list[str] = Field(default_factory=list)
    successful_contexts: list[str] = Field(default_factory=list)
    source_metadata: list[dict[str, Any]] = Field(default_factory=list)


class IngestionRunTracker:
    """Persist run lifecycle updates independently of pipeline records."""

    def __init__(
        self,
        mongo: MongoDatabase,
        *,
        source_name: str,
        command_name: str,
    ) -> None:
        self.mongo = mongo
        self.run = IngestionRun(
            source_name=source_name,
            command_name=command_name,
        )

    def start(self) -> None:
        result = upsert_records(
            self.mongo,
            collection_name=INGESTION_RUNS,
            records=[self.run],
            key_fields=("ingestion_run_id",),
        ).result
        if result.failed:
            raise RuntimeError("Unable to persist the ingestion run start record.")

    def finish(
        self,
        *,
        status: IngestionRunStatus,
        records_received: int = 0,
        records_validated: int = 0,
        records_inserted: int = 0,
        records_updated: int = 0,
        records_unchanged: int = 0,
        records_failed: int = 0,
        records_quarantined: int = 0,
        failed_regions: list[str] | None = None,
        error_summary: list[str] | None = None,
        successful_contexts: list[str] | None = None,
        source_metadata: list[dict[str, Any]] | None = None,
    ) -> IngestionRun:
        self.run = self.run.model_copy(
            update={
                "end_timestamp": datetime.now(UTC),
                "status": status,
                "records_received": records_received,
                "records_validated": records_validated,
                "records_inserted": records_inserted,
                "records_updated": records_updated,
                "records_unchanged": records_unchanged,
                "records_failed": records_failed,
                "records_quarantined": records_quarantined,
                "failed_regions": failed_regions or [],
                "error_summary": error_summary or [],
                "successful_contexts": successful_contexts or [],
                "source_metadata": source_metadata or [],
            }
        )
        result = upsert_records(
            self.mongo,
            collection_name=INGESTION_RUNS,
            records=[self.run],
            key_fields=("ingestion_run_id",),
        ).result
        if result.failed:
            logger.error(
                "Unable to persist completion for ingestion run %s.",
                self.run.ingestion_run_id,
            )
            raise RuntimeError("Unable to persist ingestion run completion.")
        return self.run
