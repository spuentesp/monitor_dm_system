from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from monitor_data.schemas.knowledge_packs import KnowledgePackStatus
from monitor_ui.routers import pack_library


@pytest.mark.asyncio
async def test_update_pack_rejects_edits_while_backing_job_is_running(monkeypatch):
    pack_id = str(uuid4())
    job_id = uuid4()

    monkeypatch.setattr(
        pack_library,
        "mongodb_get_knowledge_pack",
        lambda _uid: SimpleNamespace(
            pack_id=uuid4(),
            name="Vampire Pack",
            status=KnowledgePackStatus.PENDING,
            ingestion_job_id=job_id,
        ),
    )
    monkeypatch.setattr(
        pack_library,
        "mongodb_get_ingestion_job",
        lambda _job_id: SimpleNamespace(
            status=SimpleNamespace(value="running"),
            source_title="Vampire: The Masquerade",
            current_stage=SimpleNamespace(value="analyze"),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await pack_library.update_pack(
            pack_id, pack_library.PackUpdateRequest(name="Renamed")
        )

    assert exc.value.status_code == 409
    assert "still being built" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_clone_pack_rejects_use_while_backing_job_is_running(monkeypatch):
    pack_id = str(uuid4())
    job_id = uuid4()

    monkeypatch.setattr(
        pack_library,
        "mongodb_get_knowledge_pack",
        lambda _uid: SimpleNamespace(
            pack_id=uuid4(),
            name="Vampire Pack",
            status=KnowledgePackStatus.PENDING,
            ingestion_job_id=job_id,
        ),
    )
    monkeypatch.setattr(
        pack_library,
        "mongodb_get_ingestion_job",
        lambda _job_id: SimpleNamespace(
            status=SimpleNamespace(value="running"),
            source_title="Vampire: The Masquerade",
            current_stage=SimpleNamespace(value="analyze"),
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await pack_library.clone_pack(pack_id, pack_library.ClonePackRequest(name="Clone"))

    assert exc.value.status_code == 409
    assert "still being built" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_pack_returns_pack_data(monkeypatch):
    """Test get_pack returns the pack data correctly."""
    pack_id = str(uuid4())
    pack_data = SimpleNamespace(
        pack_id=uuid4(),
        name="Test Pack",
        status=KnowledgePackStatus.READY,
        description="Test description",
        tags=["test"],
    )

    monkeypatch.setattr(pack_library, "mongodb_get_knowledge_pack", lambda _uid: pack_data)
    monkeypatch.setattr(pack_library, "_pack_to_dict", lambda pack: {"name": pack.name, "status": str(pack.status.value)})

    result = await pack_library.get_pack(pack_id)

    assert result["name"] == "Test Pack"
    assert result["status"] == "ready"


@pytest.mark.asyncio
async def test_list_packs_filters_by_status(monkeypatch):
    """Test list_packs filters packs by status."""
    pack1 = SimpleNamespace(pack_id=uuid4(), name="Pack 1", status=KnowledgePackStatus.READY, tags=[])
    pack2 = SimpleNamespace(pack_id=uuid4(), name="Pack 2", status=KnowledgePackStatus.PENDING, tags=[])

    def list_packs_mock(filter_obj):
        if filter_obj.status == KnowledgePackStatus.READY:
            return SimpleNamespace(packs=[pack1])
        elif filter_obj.status == KnowledgePackStatus.PENDING:
            return SimpleNamespace(packs=[pack2])
        else:
            return SimpleNamespace(packs=[pack1, pack2])

    monkeypatch.setattr(pack_library, "mongodb_list_knowledge_packs", list_packs_mock)
    monkeypatch.setattr(pack_library, "_pack_to_dict", lambda pack: {"name": pack.name})

    result_ready = await pack_library.list_packs(status="ready")
    assert len(result_ready) == 1
    assert result_ready[0]["name"] == "Pack 1"

    result_pending = await pack_library.list_packs(status="pending")
    assert len(result_pending) == 1
    assert result_pending[0]["name"] == "Pack 2"


@pytest.mark.asyncio
async def test_delete_pack_soft_deletes_pack(monkeypatch):
    """Test delete_pack archives a pack (soft delete)."""
    pack_id = uuid4()
    delete_called = []

    def delete_mock(uid, soft):
        delete_called.append((uid, soft))
        return True

    monkeypatch.setattr(pack_library, "mongodb_delete_knowledge_pack", delete_mock)

    result = await pack_library.delete_pack(str(pack_id), hard=False)

    assert delete_called[0][0] == pack_id
    assert delete_called[0][1] is True  # soft=True
    assert result["action"] == "archived"


@pytest.mark.asyncio
async def test_delete_pack_hard_delete_fails_with_dependents(monkeypatch):
    """Test delete_pack hard delete fails when pack has dependents."""
    pack_id = uuid4()

    monkeypatch.setattr(pack_library, "mongodb_count_pack_dependents", lambda _uid: 5)

    with pytest.raises(HTTPException) as exc:
        await pack_library.delete_pack(str(pack_id), hard=True)

    assert exc.value.status_code == 409
    assert "Cannot hard-delete" in str(exc.value.detail)
    assert "5 pack(s) reference this pack" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_pack_creates_new_pack(monkeypatch):
    """Test create_pack creates a new pack successfully."""
    create_called = []

    def create_mock(create_obj):
        create_called.append(create_obj)
        return SimpleNamespace(
            pack_id=uuid4(),
            name=create_obj.name,
            description=create_obj.description,
            status=create_obj.status,
            tags=create_obj.tags,
        )

    monkeypatch.setattr(pack_library, "_pack_to_dict", lambda pack: {"name": pack.name, "status": str(pack.status.value)})
    monkeypatch.setattr(pack_library, "mongodb_create_knowledge_pack", create_mock)

    body = pack_library.CreatePackRequest(
        name="New Pack", description="New description", pack_type="custom", tags=["test"]
    )

    result = await pack_library.create_pack(body)

    assert len(create_called) == 1
    assert create_called[0].name == "New Pack"
    assert result["name"] == "New Pack"
    assert result["status"] == "ready"


class TestPackLibraryRequestSchemas:
    """Tests for pack library request/response schemas."""

    def test_create_pack_request_schema(self):
        """CreatePackRequest should accept required fields."""
        req = pack_library.CreatePackRequest(
            name="Test Pack",
            description="A test pack",
            pack_type="custom",
            tags=["test", "demo"],
        )
        assert req.name == "Test Pack"
        assert req.description == "A test pack"
        assert req.pack_type == "custom"
        assert "test" in req.tags

    def test_pack_update_request_schema(self):
        """PackUpdateRequest should accept update fields."""
        req = pack_library.PackUpdateRequest(name="Updated Name")
        assert req.name == "Updated Name"

    def test_clone_pack_request_schema(self):
        """ClonePackRequest should accept clone parameters."""
        req = pack_library.ClonePackRequest(name="Cloned Pack")
        assert req.name == "Cloned Pack"

    def test_promote_request_schema(self):
        """PromoteRequest should accept direction and source_index."""
        req = pack_library.PromoteRequest(
            direction="up",
            source_index=0,
        )
        assert req.direction == "up"
        assert req.source_index == 0


class TestPackLibraryHelperFunctions:
    """Tests for pack library helper functions."""

    def test_assert_pack_not_building_raises_when_running(self, monkeypatch):
        """_assert_pack_not_building should raise HTTPException when job is running."""
        from fastapi import HTTPException

        job_id = uuid4()
        pack = SimpleNamespace(
            pack_id=uuid4(),
            name="Test Pack",
            status=KnowledgePackStatus.PENDING,
            ingestion_job_id=job_id,
        )

        monkeypatch.setattr(
            pack_library,
            "mongodb_get_ingestion_job",
            lambda _job_id: SimpleNamespace(
                status=SimpleNamespace(value="running"),
                source_title="Test Source",
                current_stage=SimpleNamespace(value="analyze"),
            ),
        )

        with pytest.raises(HTTPException) as exc:
            pack_library._assert_pack_not_building(pack, action="update")

        assert exc.value.status_code == 409
        assert "still being built" in str(exc.value.detail)
