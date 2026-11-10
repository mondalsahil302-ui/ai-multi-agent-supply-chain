import hashlib
import json
import logging
from typing import Any

from pydantic import BaseModel
from pymongo import UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError

from demand_ingestion.database.mongodb import MongoDatabase

logger = logging.getLogger(__name__)


class UpsertResult(BaseModel):
    """Reconciled counts and per-input write errors."""

    received: int
    inserted: int
    updated: int
    unchanged: int
    failed: int
    error_details: list[str]


class UpsertReport(BaseModel):
    """Collection-specific summary for one idempotent write batch."""

    collection_name: str
    result: UpsertResult


def upsert_records(
    mongo: MongoDatabase,
    *,
    collection_name: str,
    records: list[BaseModel | dict[str, Any]],
    key_fields: tuple[str, ...],
    content_hash_fields: tuple[str, ...] | None = None,
    batch_size: int = 500,
    insert_only: bool = False,
) -> UpsertReport:
    """Idempotently upsert records or insert without changing existing keys."""

    if not key_fields:
        raise ValueError("key_fields cannot be empty")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    collection = mongo.database[collection_name]
    inserted = updated = unchanged = failed = 0
    error_details: list[str] = []
    for offset in range(0, len(records), batch_size):
        batch = records[offset : offset + batch_size]
        documents = [
            _serialize_record(record, key_fields, content_hash_fields)
            for record in batch
        ]
        existing = (
            {}
            if insert_only
            else {
                document["_id"]: document
                for document in collection.find(
                    {"_id": {"$in": [item["_id"] for item in documents]}},
                    {"_id": 1, "content_hash": 1},
                )
            }
        )

        operations: list[UpdateOne] = []
        for document in documents:
            previous = existing.get(document["_id"])
            if (
                not insert_only
                and previous is not None
                and previous.get("content_hash") == document["content_hash"]
            ):
                unchanged += 1
                continue
            query = (
                {field: document[field] for field in key_fields}
                if insert_only
                else {"_id": document["_id"]}
            )
            update = (
                {"$setOnInsert": document}
                if insert_only
                else {"$set": document}
            )
            operations.append(
                UpdateOne(
                    query,
                    update,
                    upsert=True,
                )
            )

        if not operations:
            continue

        try:
            result = mongo.run_with_retry(
                lambda batch_ops=operations: collection.bulk_write(
                    batch_ops,
                    ordered=False,
                )
            )
            inserted += result.upserted_count
            updated += result.modified_count
            unchanged += result.matched_count - result.modified_count
        except BulkWriteError as exc:
            details = exc.details or {}
            write_errors = details.get("writeErrors", [])
            errored_indices = {
                item["index"] for item in write_errors if "index" in item
            }
            write_result = details.get("nUpserted", 0)
            inserted += write_result
            updated += details.get("nModified", 0)
            unchanged += max(
                0,
                details.get("nMatched", 0) - details.get("nModified", 0),
            )
            failed += len(errored_indices)
            error_details.extend(
                f"record {offset + item.get('index', index)}: MongoDB write failed "
                f"(code {item.get('code', 'unknown')})"
                for index, item in enumerate(write_errors)
            )
            if not write_errors:
                failed += len(operations)
                error_details.append(
                    "MongoDB bulk write failed without per-record details."
                )
            logger.error(
                "MongoDB bulk write partially failed for %s (%d records).",
                collection_name,
                len(errored_indices),
            )
        except PyMongoError as exc:
            failed += len(operations)
            error_details.append(
                f"MongoDB batch at offset {offset} failed: {type(exc).__name__}"
            )
            logger.error(
                "MongoDB write failed for collection %s at batch offset %d (%s).",
                collection_name,
                offset,
                type(exc).__name__,
            )

    return UpsertReport(
        collection_name=collection_name,
        result=UpsertResult(
            received=len(records),
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            failed=failed,
            error_details=error_details,
        ),
    )


def _serialize_record(
    record: BaseModel | dict[str, Any],
    key_fields: tuple[str, ...],
    content_hash_fields: tuple[str, ...] | None,
) -> dict[str, Any]:
    if isinstance(record, BaseModel):
        document = record.model_dump(mode="json")
    else:
        document = dict(record)

    missing = [field for field in key_fields if field not in document]
    if missing:
        raise ValueError(f"Record is missing business key fields: {missing}")
    business_key = [document[field] for field in key_fields]
    document_id = hashlib.sha256(
        json.dumps(
            business_key,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    ignored_content_fields = {
        "retrieved_at_utc",
        "source_retrieved_at",
        "ingestion_run_id",
    }
    content = (
        {field: document.get(field) for field in content_hash_fields}
        if content_hash_fields is not None
        else {
            field: value
            for field, value in document.items()
            if field not in ignored_content_fields
        }
    )
    document["_id"] = document_id
    document["content_hash"] = hashlib.sha256(
        json.dumps(
            content,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return document
