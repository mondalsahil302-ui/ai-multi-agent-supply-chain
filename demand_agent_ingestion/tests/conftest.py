from copy import deepcopy

import pytest

from demand_ingestion.config import Settings
from demand_ingestion.database.mongodb import MongoDatabase


class FakeCollection:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}
        self.indexes: list[tuple[object, dict]] = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))
        return kwargs.get("name")

    def find(self, query, projection=None):
        ids = query.get("_id", {}).get("$in", [])
        return [
            {"_id": key, "content_hash": self.documents[key].get("content_hash")}
            for key in ids
            if key in self.documents
        ]

    def find_one(self, query, projection=None, sort=None):
        if "_id" in query and isinstance(query["_id"], dict):
            ids = query["_id"].get("$in", [])
            return next(
                (deepcopy(self.documents[key]) for key in ids if key in self.documents),
                None,
            )
        matches = [
            document
            for document in self.documents.values()
            if _matches(document, query)
        ]
        if sort and matches:
            field, direction = sort[0]
            matches.sort(
                key=lambda item: item.get(field, ""),
                reverse=direction < 0,
            )
        return deepcopy(matches[0]) if matches else None

    def bulk_write(self, operations, ordered=False):
        upserted = modified = matched = 0
        for operation in operations:
            query = operation._filter
            values = operation._doc.get(
                "$set",
                operation._doc.get("$setOnInsert"),
            )
            existing_document = self.find_one(query)
            document_id = values["_id"]
            existing = (
                self.documents.get(existing_document["_id"])
                if existing_document is not None
                else None
            )
            if existing is None:
                self.documents[document_id] = deepcopy(values)
                upserted += 1
            else:
                matched += 1
                if "$set" in operation._doc and existing != values:
                    self.documents[document_id] = deepcopy(values)
                    modified += 1
        return FakeBulkWriteResult(upserted, modified, matched)

    def update_one(self, query, update):
        matched = self.find_one(query)
        if matched is None:
            return FakeUpdateResult(0)
        document = self.documents[matched["_id"]]
        document.update(deepcopy(update["$set"]))
        return FakeUpdateResult(1)


class FakeBulkWriteResult:
    def __init__(self, upserted: int, modified: int, matched: int) -> None:
        self.upserted_count = upserted
        self.modified_count = modified
        self.matched_count = matched


class FakeUpdateResult:
    def __init__(self, matched: int) -> None:
        self.matched_count = matched


class FakeDatabase:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())

    def list_collection_names(self) -> list[str]:
        return list(self.collections)

    def create_collection(self, name: str) -> FakeCollection:
        if name in self.collections:
            raise ValueError(f"collection already exists: {name}")
        return self.__getitem__(name)


class FakeAdmin:
    @staticmethod
    def command(command):
        assert command == "ping"
        return {"ok": 1}


class FakeMongoClient:
    def __init__(self) -> None:
        self.database = FakeDatabase()
        self.admin = FakeAdmin()

    def __getitem__(self, name: str) -> FakeDatabase:
        assert name
        return self.database

    def close(self) -> None:
        pass


def _matches(document, query):
    for key, expected in query.items():
        value = document.get(key)
        if isinstance(expected, dict):
            if "$in" in expected and value not in expected["$in"]:
                return False
            if "$gte" in expected and (value is None or value < expected["$gte"]):
                return False
        elif isinstance(value, list):
            if expected not in value:
                return False
        elif value != expected:
            return False
    return True


@pytest.fixture
def fake_mongo():
    return MongoDatabase(
        settings=Settings(_env_file=None, app_env="test"),
        client=FakeMongoClient(),
    )
