"""Contract tests for MP-1: Create Pack Manually.

Use case: MP-1 — A user authors a new knowledge pack from scratch
without a PDF source. The pack starts with the default status (PENDING)
and empty entity/axiom/lore arrays. Only `name` is required; everything
else is optional.

Acceptance criteria (from docs/use-cases/epic-10-packs-MP/MP-1/MP-1.yml):
  - POST /packs creates a KnowledgePack document in MongoDB
  - Pack is created with default status and empty entity/axiom/lore arrays
  - name is required; description, game_system_id, tags, source_ids are optional
  - Pack appears in pack library immediately after creation
  - Unit tests cover creation with and without optional fields
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from monitor_data.schemas.knowledge_packs import (
    KnowledgePackCreate,
    KnowledgePackResponse,
    KnowledgePackStatus,
    KnowledgePackType,
)
from monitor_data.tools.mongodb_tools.knowledge_packs import (
    mongodb_create_knowledge_pack,
    mongodb_get_knowledge_pack,
)


# ─── Fakes ─────────────────────────────────────────────────────


class _FakePacksCollection:
    """In-memory stand-in for the `knowledge_packs` MongoDB collection.

    Mirrors the production `insert_one` + `find_one` semantics enough to
    prove that the tool persists the doc and the get endpoint can read
    it back.
    """

    def __init__(self) -> None:
        self.packs: dict[str, dict] = {}

    def insert_one(self, doc: dict) -> None:
        # Defensive copy so subsequent in-place mutation of the caller's
        # `doc` doesn't leak into the stored record.
        self.packs[doc["pack_id"]] = dict(doc)

    def find_one(self, query: dict) -> dict | None:
        if "pack_id" in query:
            return self.packs.get(query["pack_id"])
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.collections: dict[str, _FakePacksCollection] = {}

    def get_collection(self, name: str) -> _FakePacksCollection:
        if name not in self.collections:
            self.collections[name] = _FakePacksCollection()
        return self.collections[name]


@pytest.fixture
def fake_packs_client() -> _FakeClient:
    client = _FakeClient()
    with patch(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        return_value=client,
    ):
        yield client


# ─── Tests ─────────────────────────────────────────────────────


class TestMongodbCreateKnowledgePackMp1:
    """MP-1 — Create Pack Manually."""

    def test_creation_minimal_required_fields_only(self, fake_packs_client: _FakeClient) -> None:
        """MP-1: name is the only required field; everything else defaults."""
        params = KnowledgePackCreate(name="Empty Pack")

        response = mongodb_create_knowledge_pack(params)

        # Response shape
        assert isinstance(response, KnowledgePackResponse)
        assert isinstance(response.id, UUID)
        assert response.name == "Empty Pack"
        assert response.description == ""
        # Default pack_type is MISC
        assert response.pack_type == KnowledgePackType.MISC
        # Default status is PENDING
        assert response.status == KnowledgePackStatus.PENDING
        # All collection arrays start empty
        assert response.axioms == []
        assert response.entity_archetypes == []
        assert response.lore_facts == []
        assert response.entity_relationships == []
        assert response.random_tables == []
        assert response.tags == []
        assert response.source_document_ids == []
        assert response.parent_pack_ids == []
        assert response.applied_to == []
        # Optional embedded system data is None
        assert response.game_system_id is None
        assert response.game_system_data is None
        # created_at was set to "now"
        assert isinstance(response.created_at, datetime)
        assert response.updated_at is None

    def test_creation_persists_to_collection(self, fake_packs_client: _FakeClient) -> None:
        """MP-1: the created pack lives in the collection after the call returns."""
        params = KnowledgePackCreate(name="Persisted Pack")
        response = mongodb_create_knowledge_pack(params)

        coll = fake_packs_client.get_collection("knowledge_packs")
        assert str(response.id) in coll.packs
        # The stored doc round-trips back to the same response
        stored = coll.packs[str(response.id)]
        assert stored["name"] == "Persisted Pack"
        assert stored["pack_id"] == str(response.id)

    def test_creation_with_all_optional_fields(self, fake_packs_client: _FakeClient) -> None:
        """MP-1: every optional field can be populated and is round-tripped."""
        game_system_id = uuid4()
        source_doc_id = uuid4()
        parent_pack_id = uuid4()

        params = KnowledgePackCreate(
            name="Full Pack",
            description="A pack created with every optional field populated",
            pack_type=KnowledgePackType.SETTING_SUPPLEMENT,
            system_name="Cortex Prime",
            status=KnowledgePackStatus.READY,
            source_document_ids=[source_doc_id],
            tags=["fantasy", "homebrew", "session-zero"],
            parent_pack_ids=[parent_pack_id],
            game_system_id=game_system_id,
        )

        response = mongodb_create_knowledge_pack(params)

        # All optionals round-trip
        assert response.description == "A pack created with every optional field populated"
        assert response.pack_type == KnowledgePackType.SETTING_SUPPLEMENT
        assert response.system_name == "Cortex Prime"
        assert response.status == KnowledgePackStatus.READY
        assert source_doc_id in response.source_document_ids
        assert response.tags == ["fantasy", "homebrew", "session-zero"]
        assert parent_pack_id in response.parent_pack_ids
        assert response.game_system_id == game_system_id

    def test_creation_assigns_unique_pack_ids(self, fake_packs_client: _FakeClient) -> None:
        """Two creates should produce two distinct UUIDs (no aliasing)."""
        a = mongodb_create_knowledge_pack(KnowledgePackCreate(name="A"))
        b = mongodb_create_knowledge_pack(KnowledgePackCreate(name="B"))
        assert a.id != b.id
        assert a.id != b.id

    def test_creation_with_explicit_pack_id(self, fake_packs_client: _FakeClient) -> None:
        """If the caller supplies pack_id, the tool honors it (idempotent re-create)."""
        chosen = uuid4()
        params = KnowledgePackCreate(pack_id=chosen, name="Deterministic")
        response = mongodb_create_knowledge_pack(params)
        assert response.id == chosen

    def test_creation_visible_via_get_immediately(self, fake_packs_client: _FakeClient) -> None:
        """MP-1: 'Pack appears in pack library immediately after creation'."""
        created = mongodb_create_knowledge_pack(KnowledgePackCreate(name="Visible"))

        fetched = mongodb_get_knowledge_pack(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Visible"

    def test_creation_validates_name_required_at_schema_level(self) -> None:
        """MP-1: name is required — Pydantic rejects a missing name field."""
        # Missing name — Pydantic enforces required
        with pytest.raises(ValueError):
            KnowledgePackCreate()  # type: ignore[call-arg]

    def test_creation_sets_created_at_to_recent_utc(self, fake_packs_client: _FakeClient) -> None:
        """created_at should be a UTC timestamp close to 'now'."""
        before = datetime.now(timezone.utc)
        response = mongodb_create_knowledge_pack(KnowledgePackCreate(name="Timestamped"))
        after = datetime.now(timezone.utc)
        # Allow a small margin (the tool may store a naive UTC datetime)
        assert before <= response.created_at.replace(tzinfo=timezone.utc) <= after
