"""
Fake MongoDB client using mongomock — a true 1:1 in-memory mirror.

Replaces the 17+ inline _FakeCollection/_FakeMongo classes across the repo.
mongomock implements the real pymongo API in-memory, so queries, cursors,
aggregations, and indexes all work without a real MongoDB server.

Usage::

    from tests.mocks.db.mongo import make_mock_mongo_client

    client = make_mock_mongo_client()
    # client is a mongomock.MongoClient — use exactly like real pymongo
    db = client["monitor"]
    db.scenes.insert_one({"scene_id": "s1", "status": "active"})
    result = db.scenes.find_one({"scene_id": "s1"})

As a pytest fixture::

    @pytest.fixture
    def mock_mongo(monkeypatch):
        client = make_mock_mongo_client()
        monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: client)
        return client
"""

from __future__ import annotations

from typing import Any

try:
    import mongomock

    HAS_MONGOMOCK = True
except ImportError:
    HAS_MONGOMOCK = False

# Collections that MONITOR expects to exist
MONITOR_COLLECTIONS = [
    "scenes",
    "turns",
    "character_sheets",
    "story_outlines",
    "proposed_changes",
    "memories",
    "documents",
    "snippets",
    "lorebook_entries",
    "tone_libraries",
    "tone_profiles",
    "play_sessions",
    "npc_profiles",
    "knowledge_packs",
    "ingestion_jobs",
    "random_tables",
    "world_snapshots",
    "source_profiles",
    "character_versions",
    "combat_sessions",
]


def make_mock_mongo_client(
    db_name: str = "monitor",
    seed_data: dict[str, list[dict[str, Any]]] | None = None,
) -> Any:
    """Return a mongomock client pre-seeded with MONITOR's collections.

    Args:
        db_name: Database name (default: "monitor").
        seed_data: Optional dict mapping collection name → list of docs to insert.

    Returns:
        A mongomock.MongoClient instance.
    """
    if not HAS_MONGOMOCK:
        raise ImportError("mongomock is not installed. Run: uv pip install mongomock")

    client = mongomock.MongoClient()
    db = client[db_name]

    # Pre-create all MONITOR collections
    for name in MONITOR_COLLECTIONS:
        db.create_collection(name)

    # Seed with initial data if provided
    if seed_data:
        for coll_name, docs in seed_data.items():
            if coll_name not in db.list_collection_names():
                db.create_collection(coll_name)
            for doc in docs:
                db[coll_name].insert_one(doc)

    return client


def make_mock_mongo_client_with_data(
    collections: dict[str, list[dict[str, Any]]],
    db_name: str = "monitor",
) -> Any:
    """Return a mongomock client with pre-seeded collection data.

    Args:
        collections: Dict of collection name → list of documents.
        db_name: Database name.

    Example::

        client = make_mock_mongo_client_with_data({
            "scenes": [
                {"scene_id": "s1", "status": "active", "title": "The Tavern"},
                {"scene_id": "s2", "status": "completed", "title": "The Forest"},
            ],
            "turns": [
                {"turn_id": "t1", "scene_id": "s1", "speaker": "user", "text": "I enter."},
            ],
        })
    """
    return make_mock_mongo_client(db_name=db_name, seed_data=collections)


# ---------------------------------------------------------------------------
# Fallback fake for when mongomock is not available
# ---------------------------------------------------------------------------


class FakeMongoCollection:
    """Minimal in-memory MongoDB collection fake.

    Used as a fallback when mongomock is not installed.
    Supports: insert_one, insert_many, find_one, find, find_one_and_update,
    find_one_and_delete, update_one, update_many, delete_one, delete_many,
    count_documents, create_index.
    """

    def __init__(self, name: str = "test"):
        self.name = name
        self._docs: list[dict[str, Any]] = []

    def insert_one(self, doc: dict[str, Any]) -> Any:
        self._docs.append(doc)
        result = MagicMock()
        result.inserted_id = doc.get("_id", "mock-id")
        return result

    def insert_many(self, docs: list[dict[str, Any]]) -> Any:
        for doc in docs:
            self._docs.append(doc)
        result = MagicMock()
        result.inserted_ids = [d.get("_id", f"mock-{i}") for i, d in enumerate(docs)]
        return result

    def find_one(
        self, filter: dict | None = None, *args, **kwargs
    ) -> dict[str, Any] | None:
        if not filter:
            return self._docs[0] if self._docs else None
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in filter.items()):
                return doc
        return None

    def find(self, filter: dict | None = None, *args, **kwargs) -> list[dict[str, Any]]:
        if not filter:
            return list(self._docs)
        return [
            doc for doc in self._docs if all(doc.get(k) == v for k, v in filter.items())
        ]

    def find_one_and_update(
        self, filter: dict, update: dict, *args, **kwargs
    ) -> dict[str, Any] | None:
        doc = self.find_one(filter)
        if doc is None:
            return None
        if "$set" in update:
            doc.update(update["$set"])
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        return doc

    def find_one_and_delete(
        self, filter: dict, *args, **kwargs
    ) -> dict[str, Any] | None:
        for i, doc in enumerate(self._docs):
            if all(doc.get(k) == v for k, v in filter.items()):
                return self._docs.pop(i)
        return None

    def update_one(self, filter: dict, update: dict, *args, **kwargs) -> Any:
        doc = self.find_one(filter)
        if doc and "$set" in update:
            doc.update(update["$set"])
        result = MagicMock()
        result.modified_count = 1 if doc else 0
        return result

    def update_many(self, filter: dict, update: dict, *args, **kwargs) -> Any:
        count = 0
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in (filter or {}).items()):
                if "$set" in update:
                    doc.update(update["$set"])
                count += 1
        result = MagicMock()
        result.modified_count = count
        return result

    def delete_one(self, filter: dict) -> Any:
        for i, doc in enumerate(self._docs):
            if all(doc.get(k) == v for k, v in filter.items()):
                self._docs.pop(i)
                break
        result = MagicMock()
        result.deleted_count = 1
        return result

    def delete_many(self, filter: dict) -> Any:
        before = len(self._docs)
        self._docs = [
            doc
            for doc in self._docs
            if not all(doc.get(k) == v for k, v in filter.items())
        ]
        result = MagicMock()
        result.deleted_count = before - len(self._docs)
        return result

    def count_documents(self, filter: dict | None = None) -> int:
        if not filter:
            return len(self._docs)
        return sum(
            1 for doc in self._docs if all(doc.get(k) == v for k, v in filter.items())
        )

    def create_index(self, *args, **kwargs) -> str:
        return "mock-index-name"

    def aggregate(self, pipeline: list) -> list:
        """Minimal aggregation support — just returns all docs."""
        return list(self._docs)


class FakeMongoClient:
    """Minimal MongoDB client fake using FakeMongoCollection.

    Used as a fallback when mongomock is not installed.
    Provides get_database() and __getitem__ access.
    """

    def __init__(self, db_name: str = "monitor"):
        self._db_name = db_name
        self._collections: dict[str, FakeMongoCollection] = {}
        for name in MONITOR_COLLECTIONS:
            self._collections[name] = FakeMongoCollection(name)

    def get_database(self, name: str | None = None) -> FakeMongoDatabase:
        return FakeMongoDatabase(self._collections)

    def __getitem__(self, name: str) -> FakeMongoDatabase:
        return self.get_database(name)

    def close(self) -> None:
        pass


class FakeMongoDatabase:
    """Minimal MongoDB database fake."""

    def __init__(self, collections: dict[str, FakeMongoCollection]):
        self._collections = collections

    def __getitem__(self, name: str) -> FakeMongoCollection:
        if name not in self._collections:
            self._collections[name] = FakeMongoCollection(name)
        return self._collections[name]

    def get_collection(self, name: str) -> FakeMongoCollection:
        return self.__getitem__(name)

    def list_collection_names(self) -> list[str]:
        return list(self._collections.keys())

    def create_collection(self, name: str) -> FakeMongoCollection:
        if name not in self._collections:
            self._collections[name] = FakeMongoCollection(name)
        return self._collections[name]


# Convenience: always use mongomock if available, fall back to FakeMongoClient
def make_mongo_client(db_name: str = "monitor") -> Any:
    """Return the best available MongoDB fake.

    Uses mongomock if installed, otherwise falls back to FakeMongoClient.
    """
    if HAS_MONGOMOCK:
        return make_mock_mongo_client(db_name=db_name)
    return FakeMongoClient(db_name=db_name)


# Re-export for convenience
from unittest.mock import MagicMock
