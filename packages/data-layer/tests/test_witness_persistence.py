"""Witness persistence in the write tools (join Task 5, DL-3/DL-7).

Facts and memories written in play carry ``witnesses`` (Phase 4 Task 8) —
the cast members actually present. These tests pin that the Neo4j fact tool
stores the witness record on the node and returns it, and that the MongoDB
memory tool stores it on the document.

Run:
    cd /path/to/monitor_dm_system && pytest packages/data-layer/tests/test_witness_persistence.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

from monitor_data.schemas.base import CanonLevel, KnowledgeScope
from monitor_data.schemas.facts import FactCreate, FactType
from monitor_data.schemas.memories import MemoryCreate
from monitor_data.tools.neo4j_tools.facts import neo4j_create_fact, neo4j_get_fact, neo4j_list_facts


class FakeNeo4j:
    """Captures writes and serves one canned read record."""

    def __init__(self, read_result):
        self.writes: list[tuple[str, dict]] = []
        self.read_result = read_result

    def execute_write(self, query: str, params: dict) -> None:
        self.writes.append((query, params))

    def execute_read(self, query: str, params: dict):
        return self.read_result


def _fact_row(**overrides):
    row = {
        "id": str(uuid4()),
        "universe_id": str(uuid4()),
        "statement": "the ledger vanished",
        "fact_type": "occurrence",
        "magnitude": 1,
        "scope": "local",
        "time_ref": None,
        "duration": None,
        "canon_level": "canon",
        "knowledge_scope": "world",
        "confidence": 0.9,
        "authority": "source",
        "status": "active",
        "created_at": datetime.now(UTC),
        "replaces": None,
        "properties": None,
        "witnesses": [str(uuid4()), str(uuid4())],
    }
    row.update(overrides)
    return row


class TestNeo4jFactWitnesses:
    def test_create_fact_stores_the_witness_record_on_the_node(self):
        witness_a = uuid4()
        witness_b = uuid4()
        row = _fact_row(witnesses=[str(witness_a), str(witness_b)])
        fake = FakeNeo4j([{"f": row, "entity_ids": [], "source_ids": [], "scene_ids": []}])

        params = FactCreate(
            universe_id=uuid4(),
            statement="the ledger vanished",
            fact_type=FactType.OCCURRENCE,
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
            confidence=0.9,
            witnesses=[witness_a, witness_b],
            properties={"told_to": []},
        )
        with patch("monitor_data.tools.neo4j_tools.facts.get_neo4j_client", lambda: fake):
            created = neo4j_create_fact(params)

        create_write = next((q, p) for q, p in fake.writes if "CREATE (f:Fact" in q)
        # The witness record reaches the Fact node...
        assert create_write[1]["witnesses"] == [str(witness_a), str(witness_b)]
        # ...and the proposal properties survive with it.
        assert "properties" in create_write[1]
        # And the created fact returns the field (not a silent default).
        assert set(created.witnesses) == {witness_a, witness_b}

    def test_get_fact_reads_the_witness_record_back(self):
        row = _fact_row()
        fake = FakeNeo4j([{"f": row, "entity_ids": [], "source_ids": [], "scene_ids": []}])

        with patch("monitor_data.tools.neo4j_tools.facts.get_neo4j_client", lambda: fake):
            fact = neo4j_get_fact(uuid4())

        assert fact is not None
        assert {str(w) for w in fact.witnesses} == set(row["witnesses"])

    def test_list_facts_reads_the_witness_record_back(self):
        row = _fact_row()
        fake = FakeNeo4j([{"f": row, "entity_ids": [], "source_ids": [], "scene_ids": []}])

        with patch("monitor_data.tools.neo4j_tools.facts.get_neo4j_client", lambda: fake):
            facts = neo4j_list_facts()

        assert len(facts) == 1
        assert {str(w) for w in facts[0].witnesses} == set(row["witnesses"])

    def test_a_fact_without_witnesses_reads_back_empty(self):
        row = _fact_row(witnesses=[])
        fake = FakeNeo4j([{"f": row, "entity_ids": [], "source_ids": [], "scene_ids": []}])

        with patch("monitor_data.tools.neo4j_tools.facts.get_neo4j_client", lambda: fake):
            fact = neo4j_get_fact(uuid4())

        assert fact is not None
        assert fact.witnesses == []


class FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def insert_one(self, doc: dict) -> MagicMock:
        self.docs.append(dict(doc))
        return MagicMock(inserted_id=doc.get("memory_id"))

    def find_one(self, query: dict):
        for doc in self.docs:
            if doc.get("memory_id") == query.get("memory_id"):
                return dict(doc)
        return None


class FakeMongo:
    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    def get_collection(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


class TestMongoMemoryWitnesses:
    def test_create_memory_stores_the_witness_record(self):
        witness_a = uuid4()
        witness_b = uuid4()
        mongo = FakeMongo()
        neo4j = MagicMock()
        neo4j.execute_read.return_value = [{"id": "found"}]

        params = MemoryCreate(
            universe_id=uuid4(),
            entity_id=uuid4(),
            text="I saw the door seal itself",
            importance=0.6,
            emotional_valence=0.0,
            witnesses=[witness_a, witness_b],
        )
        with (
            patch("monitor_data.tools.mongodb_tools.memories.get_mongodb_client", lambda: mongo),
            patch("monitor_data.tools.mongodb_tools.memories.get_neo4j_client", lambda: neo4j),
            patch("monitor_data.tools.qdrant_tools.qdrant_embed_memory", MagicMock()),
        ):
            from monitor_data.tools.mongodb_tools.memories import mongodb_create_memory

            created = mongodb_create_memory(params)

        doc = mongo.get_collection("character_memories").docs[0]
        assert doc["witnesses"] == [str(witness_a), str(witness_b)]
        assert set(created.witnesses) == {witness_a, witness_b}
