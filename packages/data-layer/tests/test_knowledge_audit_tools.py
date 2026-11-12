"""Tests for the knowledge audit tool (CF-15 / G09).

The audit is read-only aggregation over what the stores already hold:
the character's memories, the facts they witnessed, and the proposals still
waiting for review. What matters is that every item says where it came
from, and that a doubtful attribution is marked as doubtful.

Run:
    uv run pytest packages/data-layer/tests/test_knowledge_audit_tools.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from monitor_data.db.mongodb import MongoDBClient
from monitor_data.schemas.knowledge_audit import KnowledgeAuditFilter
from monitor_data.tools.mongodb_tools.knowledge_audit import (
    mongodb_list_knowledge_audit,
)


@pytest.fixture
def mock_mongo(monkeypatch: pytest.MonkeyPatch):
    """An in-memory Mongo, installed as the data layer's client."""
    import mongomock
    from monitor_data.db import mongodb as mongodb_module
    from monitor_data.tools.mongodb_tools import knowledge_audit as audit_module

    client = mongomock.MongoClient()
    db = client["monitor"]
    for name in ("character_memories", "proposed_changes"):
        db.create_collection(name)

    holder = MongoDBClient()
    holder._client = client
    holder._db = db
    holder._indexes_created = True

    monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: holder)
    monkeypatch.setattr(audit_module, "get_mongodb_client", lambda: holder)
    return client


@pytest.fixture
def entity_id():
    return uuid4()


@pytest.fixture
def universe_id():
    return uuid4()


def _memory_doc(entity_id, universe_id, **over) -> dict:
    doc = {
        "memory_id": str(uuid4()),
        "universe_id": str(universe_id),
        "entity_id": str(entity_id),
        "text": "The council met at dusk without Mira.",
        "scene_id": str(uuid4()),
        "importance": 0.4,
        "certainty": 1.0,
        "emotional_valence": 0.0,
        "witnesses": [str(entity_id)],
        "linked_fact_id": None,
        "created_at": datetime.now(UTC),
    }
    doc.update(over)
    return doc


def _patch_facts(monkeypatch, facts) -> None:
    """Stub the canon facts the audit reads."""
    from monitor_data.tools.neo4j_tools import facts as facts_module

    class _Fact:
        def __init__(self, payload):
            self.id = payload["id"]
            self.statement = payload["statement"]
            self.witnesses = payload.get("witnesses", [])
            self.canon_level = payload.get("canon_level", "canon")
            self.confidence = payload.get("confidence", 1.0)

    monkeypatch.setattr(
        facts_module, "neo4j_list_facts", lambda filters=None: [_Fact(f) for f in facts]
    )


class TestKnowledgeAudit:
    def test_a_character_with_nothing_knows_nothing(
        self, entity_id, universe_id, mock_mongo
    ) -> None:
        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.entity_id == entity_id
        assert audit.items == []
        assert audit.memory_count == 0

    def test_memories_are_listed_with_their_provenance(
        self, entity_id, universe_id, mock_mongo
    ) -> None:
        scene_id = uuid4()
        mock_mongo["monitor"]["character_memories"].insert_one(
            _memory_doc(entity_id, universe_id, scene_id=str(scene_id))
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.memory_count == 1
        item = audit.items[0]
        assert item.kind == "memory"
        assert item.source == "memory"
        assert item.scene_id == scene_id
        assert item.importance == 0.4

    def test_another_characters_memories_are_not_included(
        self, entity_id, universe_id, mock_mongo
    ) -> None:
        mock_mongo["monitor"]["character_memories"].insert_one(
            _memory_doc(uuid4(), universe_id)
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.memory_count == 0

    def test_witnessed_facts_are_listed_as_witnessed(
        self, entity_id, universe_id, mock_mongo, monkeypatch
    ) -> None:
        fact_id = uuid4()
        _patch_facts(
            monkeypatch,
            [{"id": fact_id, "statement": "The gate opened.", "witnesses": [str(entity_id)]}],
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.fact_count == 1
        assert audit.items[0].source == "witnessed"

    def test_a_fact_with_no_witnesses_is_common_knowledge(
        self, entity_id, universe_id, mock_mongo, monkeypatch
    ) -> None:
        _patch_facts(
            monkeypatch,
            [{"id": uuid4(), "statement": "The tide turns at dusk.", "witnesses": []}],
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.fact_count == 1
        assert audit.items[0].source == "common"

    def test_a_fact_the_character_did_not_witness_is_left_out(
        self, entity_id, universe_id, mock_mongo, monkeypatch
    ) -> None:
        _patch_facts(
            monkeypatch,
            [{"id": uuid4(), "statement": "Someone else saw it.", "witnesses": [str(uuid4())]}],
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.fact_count == 0

    def test_pending_proposals_about_the_character_are_listed(
        self, entity_id, universe_id, mock_mongo
    ) -> None:
        mock_mongo["monitor"]["proposed_changes"].insert_one(
            {
                "proposal_id": str(uuid4()),
                "status": "pending",
                "universe_id": str(universe_id),
                "content": {
                    "statement": "Mira opened the sealed door.",
                    "participants": [str(entity_id)],
                },
                "confidence": 0.8,
            }
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.proposal_count == 1
        assert audit.items[0].source == "proposal"


class TestSuspicion:
    def test_an_unsure_memory_is_suspicious(
        self, entity_id, universe_id, mock_mongo
    ) -> None:
        mock_mongo["monitor"]["character_memories"].insert_one(
            _memory_doc(entity_id, universe_id, certainty=0.2, importance=0.3)
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.suspicious_count == 1
        assert audit.items[0].suspicious is True
        assert "not sure" in audit.items[0].suspicion_reason

    def test_an_important_but_unsure_memory_says_so(
        self, entity_id, universe_id, mock_mongo
    ) -> None:
        mock_mongo["monitor"]["character_memories"].insert_one(
            _memory_doc(entity_id, universe_id, certainty=0.3, importance=0.9)
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.items[0].suspicious is True
        assert "Important to them" in audit.items[0].suspicion_reason

    def test_a_confident_memory_is_not_suspicious(
        self, entity_id, universe_id, mock_mongo
    ) -> None:
        mock_mongo["monitor"]["character_memories"].insert_one(
            _memory_doc(entity_id, universe_id, certainty=1.0, importance=0.9)
        )

        audit = mongodb_list_knowledge_audit(
            KnowledgeAuditFilter(entity_id=entity_id, universe_id=universe_id)
        )

        assert audit.suspicious_count == 0
        assert audit.items[0].suspicious is False
