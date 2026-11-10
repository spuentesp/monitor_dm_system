"""Shared fakes for the multi-tenancy tool-guard and usage tests.

Not a test module — helpers only. The fakes stand in for Mongo, Neo4j and
the Postgres ownership registry so the tool-boundary assertions can be
exercised hermetically; spies record what each fake was called with so the
tests can assert the real cross-component callees were invoked with the
expected arguments.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


class FakeCollection:
    """In-memory stand-in for a MongoDB collection with call recording."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self.insert_calls: list[dict[str, Any]] = []
        self.update_calls: int = 0
        self.delete_calls: int = 0
        self.find_one_result: Any = None

    def find_one(self, query: Any, projection: Any = None) -> Any:
        return self.find_one_result

    def find(self, query: Any, projection: Any = None) -> list[dict[str, Any]]:
        return list(self.docs)

    def insert_one(self, doc: dict[str, Any]) -> Any:
        self.insert_calls.append(dict(doc))
        self.docs.append(dict(doc))
        return MagicMock(inserted_id=doc.get("id") or doc.get("entry_id"))

    def update_one(self, query: Any, update: Any, **kwargs: Any) -> Any:
        self.update_calls += 1
        return MagicMock(modified_count=1, matched_count=1)

    def delete_one(self, query: Any) -> Any:
        self.delete_calls += 1
        return MagicMock(deleted_count=1)

    def delete_many(self, query: Any) -> Any:
        self.delete_calls += 1
        return MagicMock(deleted_count=0)

    def count_documents(self, query: Any) -> int:
        return len(self.docs)

    @property
    def write_calls(self) -> int:
        return len(self.insert_calls) + self.update_calls + self.delete_calls


class FakeMongo:
    """Collection store supporting both get_collection and subscript access."""

    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def get_collection(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())

    def __getitem__(self, name: str) -> FakeCollection:
        return self.get_collection(name)

    @property
    def total_write_calls(self) -> int:
        return sum(c.write_calls for c in self.collections.values())


class FakeNeo4j:
    """execute_read fake: resolves ids to universes, permissive elsewhere."""

    def __init__(self) -> None:
        self.universe_by_id: dict[str, str] = {}

    def execute_read(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        params = params or {}
        for label_return in (
            "RETURN s.universe_id AS uid",
            "RETURN e.universe_id AS uid",
            "RETURN sc.universe_id AS uid",
        ):
            if label_return in query:
                uid = self.universe_by_id.get(str(params.get("id")))
                return [{"uid": uid}] if uid else []
        # Generic existence probes (story/entity verify queries) are permissive.
        return [{"id": str(params.get("story_id") or params.get("entity_id") or "ok"), "uid": None}]

    def execute_write(self, query: str, params: dict[str, Any] | None = None) -> Any:
        return MagicMock()


class FakePostgres:
    """Ownership-registry fake: records world_get_for_owner calls."""

    def __init__(self) -> None:
        self.owned_universes: set[str] = set()
        self.world_get_for_owner_calls: list[tuple[str, str]] = []

    async def world_get_for_owner(self, world_id: str, owner_id: Any) -> dict[str, Any] | None:
        self.world_get_for_owner_calls.append((str(world_id), str(owner_id)))
        if str(world_id) in self.owned_universes:
            return {"id": str(world_id), "owner_id": str(owner_id)}
        return None


_TOOL_MODULES = (
    "characters",
    "character_sheets",
    "character_templates",
    "conversations",
    "ingestion_jobs",
    "knowledge_packs",
    "memories",
    "npc_profiles",
    "proposals",
    "scenes",
    "stories",
    "snapshots",
    "play_sessions",
)


def install_fakes(monkeypatch: Any) -> tuple[FakeMongo, FakeNeo4j, FakePostgres]:
    """Patch every client accessor the guarded tools and tenancy use."""
    mongo, neo4j, pg = FakeMongo(), FakeNeo4j(), FakePostgres()
    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: mongo)
    monkeypatch.setattr("monitor_data.db.neo4j.get_neo4j_client", lambda: neo4j)
    monkeypatch.setattr("monitor_data.db.postgres.get_postgres_client", lambda: pg)
    for mod in _TOOL_MODULES:
        monkeypatch.setattr(
            f"monitor_data.tools.mongodb_tools.{mod}.get_mongodb_client",
            lambda: mongo,
            raising=False,
        )
        monkeypatch.setattr(
            f"monitor_data.tools.mongodb_tools.{mod}.get_neo4j_client",
            lambda: neo4j,
            raising=False,
        )
    # Memory writes fire a best-effort embedding thread; keep it offline.
    monkeypatch.setattr("monitor_data.tools.qdrant_tools.qdrant_embed_memory", lambda *a, **k: None)
    return mongo, neo4j, pg
