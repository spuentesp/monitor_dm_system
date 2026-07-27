"""Tests for KnowledgePack MongoDB tool behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.knowledge_packs import (
    ApplyKnowledgePackRequest,
    ExtractedCharacterProfile,
    ExtractedGenerationTemplate,
    ExtractedToneProfile,
    KnowledgePackCreate,
    KnowledgePackFilter,
    KnowledgePackStatus,
    KnowledgePackType,
    KnowledgePackUpdate,
)
from monitor_data.tools.mongodb_tools.knowledge_packs import (
    mongodb_apply_knowledge_pack,
)

# =============================================================================
# FAKE MONGODB IMPLEMENTATION
# =============================================================================


class _FakePacksCollection:
    def __init__(self):
        self.packs = {}
        self._insert_called = False

    def insert_one(self, doc):
        self._insert_called = True
        if "_id" not in doc:
            doc["_id"] = "mocked_mongo_id"
        # Convert UUIDs to strings to match production code behavior
        doc_copy = doc.copy()
        if "source_document_ids" in doc_copy:
            doc_copy["source_document_ids"] = [str(d) for d in doc_copy["source_document_ids"]]
        if "parent_pack_ids" in doc_copy:
            doc_copy["parent_pack_ids"] = [str(p) for p in doc_copy["parent_pack_ids"]]
        if "ingestion_job_id" in doc_copy and doc_copy["ingestion_job_id"] is not None:
            doc_copy["ingestion_job_id"] = str(doc_copy["ingestion_job_id"])
        self.packs[doc["pack_id"]] = doc_copy

    def find_one(self, query):
        if "pack_id" in query:
            return self.packs.get(query["pack_id"])
        return None

    def find_one_and_update(self, query, update, return_document=True):
        if "pack_id" not in query:
            return None
        pack_id = query["pack_id"]
        if pack_id not in self.packs:
            return None

        pack_doc = self.packs[pack_id].copy()

        # Apply $set operations
        for key, value in update.get("$set", {}).items():
            pack_doc[key] = value

        # Apply $push operations
        for key, spec in update.get("$push", {}).items():
            existing = list(pack_doc.get(key, []))
            existing.append(spec)
            pack_doc[key] = existing

        self.packs[pack_id] = pack_doc
        return pack_doc.copy()

    def count_documents(self, query):
        count = 0
        for pack in self.packs.values():
            match = True
            if "pack_type" in query and pack.get("pack_type") != query["pack_type"]:
                match = False
            if "system_name" in query:
                system_name_query = query["system_name"]
                system_name_value = pack.get("system_name", "")
                if isinstance(system_name_query, dict):
                    # Handle regex queries like {'$regex': 'Dungeons', '$options': 'i'}
                    regex_pattern = system_name_query.get("$regex", "")
                    regex_options = system_name_query.get("$options", "")
                    if "i" in regex_options:
                        match = regex_pattern.lower() in system_name_value.lower()
                    else:
                        match = regex_pattern in system_name_value
                else:
                    match = system_name_query in system_name_value
            if "status" in query and pack.get("status") != query["status"]:
                match = False
            if "tags" in query and query["tags"] not in pack.get("tags", []):
                match = False
            if "parent_pack_ids" in query and query["parent_pack_ids"] not in pack.get("parent_pack_ids", []):
                match = False
            if match:
                count += 1
        return count

    def find(self, query):
        results = []
        for pack in self.packs.values():
            match = True
            if "pack_type" in query and pack.get("pack_type") != query["pack_type"]:
                match = False
            if "system_name" in query:
                system_name_query = query["system_name"]
                system_name_value = pack.get("system_name", "")
                if isinstance(system_name_query, dict):
                    # Handle regex queries like {'$regex': 'Dungeons', '$options': 'i'}
                    regex_pattern = system_name_query.get("$regex", "")
                    regex_options = system_name_query.get("$options", "")
                    if "i" in regex_options:
                        match = regex_pattern.lower() in system_name_value.lower()
                    else:
                        match = regex_pattern in system_name_value
                else:
                    match = system_name_query in system_name_value
            if "status" in query and pack.get("status") != query["status"]:
                match = False
            if "tags" in query and query["tags"] not in pack.get("tags", []):
                match = False
            if match:
                results.append(pack)
        return _FakeCursor(results)

    def update_one(self, query, update):
        if "pack_id" in query and query["pack_id"] in self.packs:
            for key, value in update.get("$set", {}).items():
                self.packs[query["pack_id"]][key] = value
            for key, spec in update.get("$push", {}).items():
                existing = list(self.packs[query["pack_id"]].get(key, []))
                existing.append(spec)
                self.packs[query["pack_id"]][key] = existing
            return type("UpdateResult", (), {"matched_count": 1})()
        return type("UpdateResult", (), {"matched_count": 0})()

    def delete_one(self, query):
        if "pack_id" in query and query["pack_id"] in self.packs:
            del self.packs[query["pack_id"]]
            return type("DeleteResult", (), {"deleted_count": 1})()
        return type("DeleteResult", (), {"deleted_count": 0})()


class _FakeCursor:
    def __init__(self, results):
        self.results = results

    def sort(self, key, direction):
        if direction == -1:  # desc
            self.results = sorted(self.results, key=lambda x: x.get(key, ""), reverse=True)
        else:  # asc
            self.results = sorted(self.results, key=lambda x: x.get(key, ""))
        return self

    def skip(self, offset):
        self.results = self.results[offset:]
        return self

    def limit(self, limit):
        self.results = self.results[:limit]
        return self

    def __iter__(self):
        return iter(self.results)


class _FakeMongo:
    def __init__(self):
        self.packs = _FakePacksCollection()
        self.proposals = _FakePacksCollection()  # Reuse same structure for proposals

    def get_collection(self, name):
        if name == "knowledge_packs":
            return self.packs
        if name == "proposed_changes":
            return self.proposals
        raise ValueError(f"Unknown collection: {name}")


# =============================================================================
# TESTS FOR mongodb_create_knowledge_pack
# =============================================================================


def test_create_knowledge_pack_basic(monkeypatch):
    """Test basic pack creation with required fields."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    create_params = KnowledgePackCreate(
        name="Test Pack",
        description="Test description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
    )

    pack = mongodb_create_knowledge_pack(create_params)

    assert pack.name == "Test Pack"
    assert pack.description == "Test description"
    assert pack.pack_type == KnowledgePackType.RULEBOOK
    assert pack.status == KnowledgePackStatus.PENDING
    assert len(pack.source_document_ids) == 1
    assert fake_mongo.packs._insert_called


def test_create_knowledge_pack_with_explicit_pack_id(monkeypatch):
    """Test pack creation with explicit pack_id."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    pack_id = uuid4()

    create_params = KnowledgePackCreate(
        name="Test Pack",
        description="Test description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
        pack_id=pack_id,
    )

    pack = mongodb_create_knowledge_pack(create_params)

    assert pack.id == pack_id


def test_create_knowledge_pack_with_ingestion_job_id(monkeypatch):
    """Test pack creation with ingestion_job_id."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    ingestion_job_id = uuid4()

    create_params = KnowledgePackCreate(
        name="Test Pack",
        description="Test description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
        ingestion_job_id=ingestion_job_id,
    )

    pack = mongodb_create_knowledge_pack(create_params)

    assert pack.ingestion_job_id == ingestion_job_id


# =============================================================================
# TESTS FOR mongodb_get_knowledge_pack
# =============================================================================


def test_get_knowledge_pack_existing(monkeypatch):
    """Test getting an existing knowledge pack."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_get_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    create_params = KnowledgePackCreate(
        name="Test Pack",
        description="Test description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
    )

    created_pack = mongodb_create_knowledge_pack(create_params)
    retrieved_pack = mongodb_get_knowledge_pack(created_pack.id)

    assert retrieved_pack is not None
    assert retrieved_pack.id == created_pack.id
    assert retrieved_pack.name == "Test Pack"


def test_get_knowledge_pack_not_found(monkeypatch):
    """Test getting a non-existent knowledge pack returns None."""
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_get_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    pack_id = uuid4()
    result = mongodb_get_knowledge_pack(pack_id)

    assert result is None


# =============================================================================
# TESTS FOR mongodb_update_knowledge_pack
# =============================================================================


def test_update_knowledge_pack_status(monkeypatch):
    """Test updating pack status."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
        KnowledgePackUpdate,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_update_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    create_params = KnowledgePackCreate(
        name="Test Pack",
        description="Test description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
    )

    created_pack = mongodb_create_knowledge_pack(create_params)

    updated_pack = mongodb_update_knowledge_pack(
        created_pack.id,
        KnowledgePackUpdate(status=KnowledgePackStatus.READY),
    )

    assert updated_pack.status == KnowledgePackStatus.READY
    assert updated_pack.updated_at is not None


def test_update_knowledge_pack_tags(monkeypatch):
    """Test updating pack tags."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
        KnowledgePackUpdate,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_update_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    create_params = KnowledgePackCreate(
        name="Test Pack",
        description="Test description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
    )

    created_pack = mongodb_create_knowledge_pack(create_params)

    updated_pack = mongodb_update_knowledge_pack(
        created_pack.id,
        KnowledgePackUpdate(tags=["fantasy", "medieval"]),
    )

    assert "fantasy" in updated_pack.tags
    assert "medieval" in updated_pack.tags


def test_update_knowledge_pack_not_found_raises_error(monkeypatch):
    """Test that updating a non-existent pack raises ValueError."""
    from monitor_data.schemas.knowledge_packs import KnowledgePackUpdate
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_update_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    pack_id = uuid4()

    with pytest.raises(ValueError, match="KnowledgePack .* not found"):
        mongodb_update_knowledge_pack(
            pack_id,
            KnowledgePackUpdate(name="Updated Name"),
        )


# =============================================================================
# TESTS FOR mongodb_list_knowledge_packs
# =============================================================================


def test_list_knowledge_packs_all(monkeypatch):
    """Test listing all knowledge packs without filters."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_list_knowledge_packs,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create 3 packs
    for i in range(3):
        create_params = KnowledgePackCreate(
            name=f"Test Pack {i}",
            description=f"Test description {i}",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
        mongodb_create_knowledge_pack(create_params)

    result = mongodb_list_knowledge_packs(KnowledgePackFilter())

    assert len(result.packs) == 3
    assert result.total == 3


def test_list_knowledge_packs_by_pack_type(monkeypatch):
    """Test listing packs filtered by pack_type."""
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_list_knowledge_packs,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create 2 rulebook packs and 1 source pack
    for i in range(2):
        create_params = KnowledgePackCreate(
            name=f"Rulebook Pack {i}",
            description=f"Test description {i}",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
        mongodb_create_knowledge_pack(create_params)

    create_params = KnowledgePackCreate(
        name="Source Pack",
        description="Test description",
        pack_type=KnowledgePackType.LORE,
        source_document_ids=[uuid4()],
    )
    mongodb_create_knowledge_pack(create_params)

    result = mongodb_list_knowledge_packs(KnowledgePackFilter(pack_type=KnowledgePackType.RULEBOOK))

    assert len(result.packs) == 2
    assert result.total == 2
    assert all(pack.pack_type == KnowledgePackType.RULEBOOK for pack in result.packs)


def test_list_knowledge_packs_by_status(monkeypatch):
    """Test listing packs filtered by status."""
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_list_knowledge_packs,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create 3 packs
    for i in range(3):
        create_params = KnowledgePackCreate(
            name=f"Test Pack {i}",
            description=f"Test description {i}",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
        mongodb_create_knowledge_pack(create_params)

    # Update first 2 packs to READY
    created_packs = list(fake_mongo.packs.packs.values())
    for i in range(2):
        from monitor_data.tools.mongodb_tools.knowledge_packs import (
            mongodb_update_knowledge_pack,
        )

        mongodb_update_knowledge_pack(
            created_packs[i]["pack_id"],
            KnowledgePackUpdate(status=KnowledgePackStatus.READY),
        )

    result = mongodb_list_knowledge_packs(KnowledgePackFilter(status=KnowledgePackStatus.PENDING))

    assert len(result.packs) == 1
    assert result.total == 1
    assert all(pack.status == KnowledgePackStatus.PENDING for pack in result.packs)


def test_list_knowledge_packs_with_pagination(monkeypatch):
    """Test listing packs with offset and limit pagination."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_list_knowledge_packs,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create 5 packs
    for i in range(5):
        create_params = KnowledgePackCreate(
            name=f"Test Pack {i}",
            description=f"Test description {i}",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
        mongodb_create_knowledge_pack(create_params)

    # Request page with offset=1, limit=2 (should return packs 2 and 3)
    result = mongodb_list_knowledge_packs(KnowledgePackFilter(offset=1, limit=2))

    assert len(result.packs) == 2
    assert result.total == 5
    assert result.offset == 1
    assert result.limit == 2


def test_list_knowledge_packs_by_tag(monkeypatch):
    """Test listing packs filtered by tag."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_list_knowledge_packs,
        mongodb_update_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create packs with different tags
    pack1 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="Fantasy Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
    )
    pack2 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="Sci-Fi Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
    )
    pack3 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="Horror Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
    )

    # Add tags to packs
    mongodb_update_knowledge_pack(pack1.id, KnowledgePackUpdate(tags=["fantasy", "medieval"]))
    mongodb_update_knowledge_pack(pack2.id, KnowledgePackUpdate(tags=["sci-fi", "space"]))
    mongodb_update_knowledge_pack(pack3.id, KnowledgePackUpdate(tags=["fantasy", "horror"]))

    # Filter by tag "fantasy"
    result = mongodb_list_knowledge_packs(KnowledgePackFilter(tag="fantasy"))

    assert len(result.packs) == 2
    assert result.total == 2
    assert all("fantasy" in pack.tags for pack in result.packs)
    pack_names = {pack.name for pack in result.packs}
    assert pack_names == {"Fantasy Pack", "Horror Pack"}


def test_list_knowledge_packs_by_system_name(monkeypatch):
    """Test listing packs filtered by system_name (case-insensitive regex)."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_list_knowledge_packs,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create packs with different system names
    mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="D&D Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            system_name="Dungeons & Dragons 5e",
            source_document_ids=[uuid4()],
        )
    )
    mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="Pathfinder Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            system_name="Pathfinder 2e",
            source_document_ids=[uuid4()],
        )
    )
    mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="D20 Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            system_name="d20 system",
            source_document_ids=[uuid4()],
        )
    )

    # Filter by system_name "dungeons" (case-insensitive)
    result = mongodb_list_knowledge_packs(KnowledgePackFilter(system_name="dungeons"))

    assert len(result.packs) == 1
    assert result.total == 1
    assert result.packs[0].name == "D&D Pack"


def test_list_knowledge_packs_applied_to(monkeypatch):
    """Test listing packs filtered by multiverse_id in applied_to field."""
    import uuid

    from monitor_data.schemas.knowledge_packs import (
        AppliedToEntry,
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_get_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    multiverse_id_1 = uuid.uuid4()
    multiverse_id_2 = uuid.uuid4()

    # Create packs
    pack1 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="Pack 1",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
    )
    pack2 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="Pack 2",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
    )
    pack3 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="Pack 3",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
        )
    )

    # Apply packs to multiverses by adding to applied_to list
    entry1 = AppliedToEntry(
        multiverse_id=multiverse_id_1,
        universe_id=None,
        applied_at=datetime.now(UTC),
    )
    entry2 = AppliedToEntry(
        multiverse_id=multiverse_id_2,
        universe_id=None,
        applied_at=datetime.now(UTC),
    )

    # Update packs with applied_to entries
    pack1_doc = fake_mongo.packs.packs[str(pack1.id)]
    pack1_doc["applied_to"] = [entry1.model_dump(mode="json")]

    pack2_doc = fake_mongo.packs.packs[str(pack2.id)]
    pack2_doc["applied_to"] = [entry1.model_dump(mode="json"), entry2.model_dump(mode="json")]

    # Pack 3 has no applied_to entries

    # Retrieve packs and verify applied_to
    retrieved_pack1 = mongodb_get_knowledge_pack(pack1.id)
    retrieved_pack2 = mongodb_get_knowledge_pack(pack2.id)
    retrieved_pack3 = mongodb_get_knowledge_pack(pack3.id)

    assert len(retrieved_pack1.applied_to) == 1
    assert retrieved_pack1.applied_to[0].multiverse_id == multiverse_id_1

    assert len(retrieved_pack2.applied_to) == 2
    multiverse_ids_in_pack2 = {entry.multiverse_id for entry in retrieved_pack2.applied_to}
    assert multiverse_id_1 in multiverse_ids_in_pack2
    assert multiverse_id_2 in multiverse_ids_in_pack2

    assert len(retrieved_pack3.applied_to) == 0


def test_list_knowledge_packs_with_multiple_filters(monkeypatch):
    """Test listing packs with multiple filters combined."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_list_knowledge_packs,
        mongodb_update_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create packs with various attributes
    pack1 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="D&D Fantasy Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            system_name="Dungeons & Dragons 5e",
            source_document_ids=[uuid4()],
        )
    )
    pack2 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="D&D Horror Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            system_name="Dungeons & Dragons 5e",
            source_document_ids=[uuid4()],
        )
    )
    pack3 = mongodb_create_knowledge_pack(
        KnowledgePackCreate(
            name="Pathfinder Fantasy Pack",
            description="Test description",
            pack_type=KnowledgePackType.RULEBOOK,
            system_name="Pathfinder 2e",
            source_document_ids=[uuid4()],
        )
    )

    # Add tags
    mongodb_update_knowledge_pack(pack1.id, KnowledgePackUpdate(tags=["fantasy", "medieval"]))
    mongodb_update_knowledge_pack(pack2.id, KnowledgePackUpdate(tags=["horror", "gothic"]))
    mongodb_update_knowledge_pack(pack3.id, KnowledgePackUpdate(tags=["fantasy", "adventure"]))

    # Filter by system_name="Dungeons" AND tag="fantasy"
    result = mongodb_list_knowledge_packs(KnowledgePackFilter(system_name="Dungeons", tag="fantasy"))

    assert len(result.packs) == 1
    assert result.total == 1
    assert result.packs[0].name == "D&D Fantasy Pack"
    assert "fantasy" in result.packs[0].tags


# =============================================================================
# TESTS FOR mongodb_delete_knowledge_pack
# =============================================================================


def test_delete_knowledge_pack_soft(monkeypatch):
    """Test soft deleting a knowledge pack (archive)."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_create_knowledge_pack,
        mongodb_delete_knowledge_pack,
        mongodb_get_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    create_params = KnowledgePackCreate(
        name="Test Pack",
        description="Test description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
    )

    created_pack = mongodb_create_knowledge_pack(create_params)

    # Soft delete (default)
    result = mongodb_delete_knowledge_pack(created_pack.id, soft=True)

    assert result is True

    # Verify pack is archived, not deleted
    archived_pack = mongodb_get_knowledge_pack(created_pack.id)
    assert archived_pack is not None
    assert archived_pack.status == KnowledgePackStatus.ARCHIVED


def test_delete_knowledge_pack_not_found(monkeypatch):
    """Test deleting a non-existent pack returns False."""
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_delete_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    pack_id = uuid4()
    result = mongodb_delete_knowledge_pack(pack_id)

    assert result is False


# =============================================================================
# TESTS FOR mongodb_count_pack_dependents
# =============================================================================


def test_count_pack_dependents_none(monkeypatch):
    """Test counting dependents when pack has no dependents."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_count_pack_dependents,
        mongodb_create_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    create_params = KnowledgePackCreate(
        name="Test Pack",
        description="Test description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
    )

    created_pack = mongodb_create_knowledge_pack(create_params)

    count = mongodb_count_pack_dependents(created_pack.id)

    assert count == 0


def test_count_pack_dependents_with_children(monkeypatch):
    """Test counting dependents when pack has child packs."""
    from monitor_data.schemas.knowledge_packs import (
        KnowledgePackType,
    )
    from monitor_data.tools.mongodb_tools.knowledge_packs import (
        mongodb_count_pack_dependents,
        mongodb_create_knowledge_pack,
    )

    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create parent pack
    parent_params = KnowledgePackCreate(
        name="Parent Pack",
        description="Parent description",
        pack_type=KnowledgePackType.RULEBOOK,
        source_document_ids=[uuid4()],
    )

    parent_pack = mongodb_create_knowledge_pack(parent_params)

    # Create 2 child packs
    for i in range(2):
        child_params = KnowledgePackCreate(
            name=f"Child Pack {i}",
            description=f"Child description {i}",
            pack_type=KnowledgePackType.RULEBOOK,
            source_document_ids=[uuid4()],
            parent_pack_ids=[str(parent_pack.id)],
        )
        mongodb_create_knowledge_pack(child_params)

    count = mongodb_count_pack_dependents(parent_pack.id)

    assert count == 2


# =============================================================================
# ORIGINAL TEST FOR mongodb_apply_knowledge_pack
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.knowledge_packs.get_mongodb_client")
def test_apply_knowledge_pack_proposes_narrative_support_items(mock_mongo: Mock) -> None:
    """Tone/profile/template extractions should survive into review proposals."""
    pack_id = uuid4()
    multiverse_id = uuid4()
    now = datetime.now(UTC)
    tone = ExtractedToneProfile(
        name="Gothic Pressure",
        description="Dark social dread.",
        instruction="Keep narration tense and intimate.",
        trigger_tags=["gothic", "dread"],
        confidence=0.91,
    )
    character_profile = ExtractedCharacterProfile(
        name="Camarilla Elder",
        values=["control"],
        fears=["irrelevance"],
        confidence=0.82,
    )
    template = ExtractedGenerationTemplate(
        name="Harpy Envoy",
        archetype_name="Harpy",
        profile_name="Camarilla Elder",
        confidence=0.77,
    )

    pack_doc = {
        "_id": "mock_id",
        "pack_id": str(pack_id),
        "name": "V20 Narrative Pack",
        "description": "",
        "pack_type": KnowledgePackType.RULEBOOK.value,
        "system_name": "V20",
        "status": KnowledgePackStatus.READY.value,
        "source_document_ids": [],
        "ingestion_job_id": None,
        "tags": [],
        "parent_pack_ids": [],
        "axioms": [],
        "entity_archetypes": [],
        "lore_facts": [],
        "entity_relationships": [],
        "random_tables": [],
        "agendas": [],
        "topologies": [],
        "tone_profiles": [tone.model_dump(mode="json")],
        "character_profiles": [character_profile.model_dump(mode="json")],
        "generation_templates": [template.model_dump(mode="json")],
        "game_system_id": None,
        "game_system_data": None,
        "source_profile_data": None,
        "chunk_summaries": [],
        "section_summaries": [],
        "source_mindscape": None,
        "applied_to": [],
        "created_at": now,
        "updated_at": None,
    }

    packs_collection = Mock()
    packs_collection.find_one.return_value = pack_doc
    proposals_collection = Mock()

    def _get_collection(name: str) -> Mock:
        return {
            "knowledge_packs": packs_collection,
            "proposed_changes": proposals_collection,
        }[name]

    mock_mongo.return_value.get_collection.side_effect = _get_collection

    result = mongodb_apply_knowledge_pack(
        pack_id,
        ApplyKnowledgePackRequest(multiverse_id=multiverse_id),
    )

    assert result["proposals_created"] == 3
    assert result["tone_profiles_proposed"] == 1
    assert result["character_profiles_proposed"] == 1
    assert result["generation_templates_proposed"] == 1

    proposal_docs = proposals_collection.insert_many.call_args.args[0]
    assert {doc["proposal_type"] for doc in proposal_docs} == {
        "create_tone_profile",
        "create_character_profile",
        "create_generation_template",
    }
    assert {doc["source"] for doc in proposal_docs} == {f"knowledge_pack:{pack_id}"}
