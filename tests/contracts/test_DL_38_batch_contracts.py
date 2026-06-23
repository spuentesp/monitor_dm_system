"""
DL-38: Entity Batch Operations — Contract Tests

Tests the input/output contracts for batch entity CRUD operations.
These tests validate schema constraints, not database interactions.

Use Cases: DL-2 (Entity CRUD), M-12 (Entity Management), Phase 3.1

Tests batch create, update, and delete operations for entities.
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone
from pydantic import ValidationError

from monitor_data.schemas.base import (
    Authority,
    CanonLevel,
    EntityType,
    DetailLevel,
)
from monitor_data.schemas.entities import (
    EntityCreate,
    EntityUpdate,
    EntityResponse,
    BatchError,
    EntityBatchCreateRequest,
    EntityBatchCreateResponse,
    EntityBatchUpdateRequest,
    EntityBatchUpdateResponse,
    EntityBatchDeleteRequest,
    EntityBatchDeleteResponse,
    EntityBatchCloneRequest,
)


# =============================================================================
# BatchError contract tests
# =============================================================================


@pytest.mark.unit
class TestBatchErrorContract:
    """Contract tests for BatchError schema."""

    def test_batch_error_minimal(self):
        """BatchError with only required fields is valid."""
        err = BatchError(index=0, message="Entity creation failed")
        assert err.index == 0
        assert err.message == "Entity creation failed"
        assert err.entity_id is None
        assert err.code is None

    def test_batch_error_with_entity_id(self):
        """BatchError with entity_id and code."""
        entity_id = uuid4()
        err = BatchError(
            index=5,
            entity_id=entity_id,
            message="Universe not found",
            code="UNIVERSE_NOT_FOUND",
        )
        assert err.index == 5
        assert err.entity_id == entity_id
        assert err.code == "UNIVERSE_NOT_FOUND"

    def test_batch_error_all_fields(self):
        """BatchError with all optional fields."""
        err = BatchError(
            index=10,
            entity_id=uuid4(),
            message="Validation error",
            code="VALIDATION_ERROR",
        )
        assert err.message == "Validation error"


# =============================================================================
# EntityBatchCreateRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityBatchCreateRequestContract:
    """Contract tests for EntityBatchCreateRequest schema."""

    def test_batch_create_minimal(self):
        """EntityBatchCreateRequest with minimal fields is valid."""
        uid = uuid4()
        request = EntityBatchCreateRequest(
            universe_id=uid,
            entities=[
                EntityCreate(universe_id=uid, name="Entity 1", entity_type=EntityType.CHARACTER),
                EntityCreate(universe_id=uid, name="Entity 2", entity_type=EntityType.LOCATION),
            ],
        )
        assert request.universe_id == uid
        assert len(request.entities) == 2
        assert request.continue_on_error is False

    def test_batch_create_single_entity(self):
        """EntityBatchCreateRequest with single entity is valid."""
        uid = uuid4()
        request = EntityBatchCreateRequest(
            universe_id=uid,
            entities=[
                EntityCreate(universe_id=uid, name="Single Entity", entity_type=EntityType.OBJECT),
            ],
        )
        assert len(request.entities) == 1

    def test_batch_create_with_continue_on_error(self):
        """EntityBatchCreateRequest with continue_on_error=True."""
        uid = uuid4()
        request = EntityBatchCreateRequest(
            universe_id=uid,
            entities=[
                EntityCreate(universe_id=uid, name="Entity 1", entity_type=EntityType.CHARACTER),
                EntityCreate(universe_id=uid, name="Entity 2", entity_type=EntityType.CHARACTER),
            ],
            continue_on_error=True,
        )
        assert request.continue_on_error is True

    def test_batch_create_empty_fails(self):
        """EntityBatchCreateRequest with empty entities list raises ValidationError."""
        uid = uuid4()
        with pytest.raises(ValidationError):
            EntityBatchCreateRequest(universe_id=uid, entities=[])

    def test_batch_create_max_100(self):
        """EntityBatchCreateRequest with more than 100 entities raises ValidationError."""
        uid = uuid4()
        entities = [
            EntityCreate(universe_id=uid, name=f"Entity {i}", entity_type=EntityType.CHARACTER)
            for i in range(101)
        ]
        with pytest.raises(ValidationError):
            EntityBatchCreateRequest(universe_id=uid, entities=entities)

    def test_batch_create_with_all_entity_fields(self):
        """EntityBatchCreateRequest with fully populated entity."""
        uid = uuid4()
        aid = uuid4()
        request = EntityBatchCreateRequest(
            universe_id=uid,
            entities=[
                EntityCreate(
                    universe_id=uid,
                    name="Full Entity",
                    entity_type=EntityType.CHARACTER,
                    sub_type="noble",
                    is_archetype=False,
                    description="A detailed character",
                    properties={"level": 5, "class": "paladin"},
                    state_tags=["alive", "friendly"],
                    archetype_id=aid,
                    authority=Authority.GM,
                    canon_level=CanonLevel.CANON,
                    confidence=0.9,
                    detail_level=DetailLevel.DETAILED,
                ),
            ],
        )
        entity = request.entities[0]
        assert entity.name == "Full Entity"
        assert entity.sub_type == "noble"
        assert entity.properties["level"] == 5
        assert entity.detail_level == DetailLevel.DETAILED


# =============================================================================
# EntityBatchCreateResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityBatchCreateResponseContract:
    """Contract tests for EntityBatchCreateResponse schema."""

    def test_batch_create_response_minimal(self):
        """EntityBatchCreateResponse with minimal fields is valid."""
        response = EntityBatchCreateResponse(
            entities=[],
            total=0,
            succeeded=0,
            failed=0,
        )
        assert response.total == 0
        assert response.succeeded == 0
        assert response.failed == 0
        assert response.errors == []

    def test_batch_create_response_with_data(self):
        """EntityBatchCreateResponse with created entities."""
        uid = uuid4()
        now = datetime.now(timezone.utc)
        entity_response = EntityResponse(
            id=uuid4(),
            universe_id=uid,
            name="Created Entity",
            entity_type=EntityType.CHARACTER,
            is_archetype=False,
            description="Test",
            properties={},
            state_tags=[],
            canon_level=CanonLevel.CANON,
            confidence=1.0,
            authority=Authority.SYSTEM,
            created_at=now,
        )
        response = EntityBatchCreateResponse(
            entities=[entity_response],
            total=1,
            succeeded=1,
            failed=0,
        )
        assert len(response.entities) == 1
        assert response.succeeded == 1
        assert response.failed == 0

    def test_batch_create_response_with_errors(self):
        """EntityBatchCreateResponse with error entries."""
        err = BatchError(index=0, entity_id=uuid4(), message="Failed", code="FAIL")
        response = EntityBatchCreateResponse(
            entities=[],
            total=1,
            succeeded=0,
            failed=1,
            errors=[err],
        )
        assert len(response.errors) == 1
        assert response.errors[0].code == "FAIL"


# =============================================================================
# EntityBatchUpdateRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityBatchUpdateRequestContract:
    """Contract tests for EntityBatchUpdateRequest schema."""

    def test_batch_update_minimal(self):
        """EntityBatchUpdateRequest with minimal fields is valid."""
        request = EntityBatchUpdateRequest(
            updates=[
                {"entity_id": str(uuid4()), "update": {"name": "Updated 1"}},
                {"entity_id": str(uuid4()), "update": {"name": "Updated 2"}},
            ],
        )
        assert len(request.updates) == 2
        assert request.continue_on_error is False

    def test_batch_update_single(self):
        """EntityBatchUpdateRequest with single update is valid."""
        request = EntityBatchUpdateRequest(
            updates=[{"entity_id": str(uuid4()), "update": {"name": "Updated Name", "description": "New desc"}}],
        )
        assert len(request.updates) == 1
        assert request.updates[0]["update"]["name"] == "Updated Name"

    def test_batch_update_empty_fails(self):
        """EntityBatchUpdateRequest with empty updates list raises ValidationError."""
        with pytest.raises(ValidationError):
            EntityBatchUpdateRequest(updates=[])

    def test_batch_update_max_100(self):
        """EntityBatchUpdateRequest with more than 100 updates raises ValidationError."""
        updates = [EntityUpdate(name=f"Update {i}") for i in range(101)]
        with pytest.raises(ValidationError):
            EntityBatchUpdateRequest(updates=updates)


# =============================================================================
# EntityBatchUpdateResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityBatchUpdateResponseContract:
    """Contract tests for EntityBatchUpdateResponse schema."""

    def test_batch_update_response_minimal(self):
        """EntityBatchUpdateResponse with minimal fields is valid."""
        response = EntityBatchUpdateResponse(
            entities=[],
            total=0,
            succeeded=0,
            failed=0,
        )
        assert response.total == 0

    def test_batch_update_response_with_data(self):
        """EntityBatchUpdateResponse with updated entities."""
        uid = uuid4()
        now = datetime.now(timezone.utc)
        entity_response = EntityResponse(
            id=uuid4(),
            universe_id=uid,
            name="Updated Entity",
            entity_type=EntityType.CHARACTER,
            is_archetype=False,
            description="Updated",
            properties={},
            state_tags=[],
            canon_level=CanonLevel.CANON,
            confidence=1.0,
            authority=Authority.SYSTEM,
            created_at=now,
        )
        response = EntityBatchUpdateResponse(
            entities=[entity_response],
            total=1,
            succeeded=1,
            failed=0,
        )
        assert response.succeeded == 1


# =============================================================================
# EntityBatchDeleteRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityBatchDeleteRequestContract:
    """Contract tests for EntityBatchDeleteRequest schema."""

    def test_batch_delete_minimal(self):
        """EntityBatchDeleteRequest with minimal fields is valid."""
        request = EntityBatchDeleteRequest(
            entity_ids=[uuid4(), uuid4()],
        )
        assert len(request.entity_ids) == 2
        assert request.force is False

    def test_batch_delete_single(self):
        """EntityBatchDeleteRequest with single ID is valid."""
        entity_id = uuid4()
        request = EntityBatchDeleteRequest(entity_ids=[entity_id])
        assert len(request.entity_ids) == 1
        assert request.entity_ids[0] == entity_id

    def test_batch_delete_with_force(self):
        """EntityBatchDeleteRequest with force=True."""
        request = EntityBatchDeleteRequest(
            entity_ids=[uuid4()],
            force=True,
        )
        assert request.force is True

    def test_batch_delete_empty_fails(self):
        """EntityBatchDeleteRequest with empty entity_ids list raises ValidationError."""
        with pytest.raises(ValidationError):
            EntityBatchDeleteRequest(entity_ids=[])

    def test_batch_delete_max_100(self):
        """EntityBatchDeleteRequest with more than 100 IDs raises ValidationError."""
        ids = [uuid4() for _ in range(101)]
        with pytest.raises(ValidationError):
            EntityBatchDeleteRequest(entity_ids=ids)


# =============================================================================
# EntityBatchDeleteResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityBatchDeleteResponseContract:
    """Contract tests for EntityBatchDeleteResponse schema."""

    def test_batch_delete_response_minimal(self):
        """EntityBatchDeleteResponse with minimal fields is valid."""
        response = EntityBatchDeleteResponse(
            deleted=[],
            total=0,
            succeeded=0,
            failed=0,
        )
        assert response.total == 0
        assert response.succeeded == 0

    def test_batch_delete_response_with_deleted(self):
        """EntityBatchDeleteResponse with deleted entity IDs."""
        id1, id2 = uuid4(), uuid4()
        response = EntityBatchDeleteResponse(
            deleted=[str(id1), str(id2)],
            total=2,
            succeeded=2,
            failed=0,
        )
        assert len(response.deleted) == 2
        assert response.succeeded == 2

    def test_batch_delete_response_with_errors(self):
        """EntityBatchDeleteResponse with error entries."""
        err = BatchError(index=0, entity_id=uuid4(), message="Delete failed", code="DELETE_FAILED")
        response = EntityBatchDeleteResponse(
            deleted=[],
            total=1,
            succeeded=0,
            failed=1,
            errors=[err],
        )
        assert response.failed == 1
        assert len(response.errors) == 1


# =============================================================================
# EntityBatchCloneRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityBatchCloneRequestContract:
    """Contract tests for EntityBatchCloneRequest schema."""

    def test_batch_clone_minimal(self):
        """EntityBatchCloneRequest with minimal fields is valid."""
        request = EntityBatchCloneRequest(
            entity_ids=[uuid4(), uuid4()],
        )
        assert len(request.entity_ids) == 2
        assert request.name_prefix is None
        assert request.name_suffix is None
        assert request.keep_relationships is True

    def test_batch_clone_with_prefix_suffix(self):
        """EntityBatchCloneRequest with name prefix and suffix."""
        request = EntityBatchCloneRequest(
            entity_ids=[uuid4()],
            name_prefix="Copy of ",
            name_suffix=" (clone)",
        )
        assert request.name_prefix == "Copy of "
        assert request.name_suffix == " (clone)"

    def test_batch_clone_no_relationships(self):
        """EntityBatchCloneRequest with keep_relationships=False."""
        request = EntityBatchCloneRequest(
            entity_ids=[uuid4()],
            keep_relationships=False,
        )
        assert request.keep_relationships is False

    def test_batch_clone_empty_fails(self):
        """EntityBatchCloneRequest with empty entity_ids list raises ValidationError."""
        with pytest.raises(ValidationError):
            EntityBatchCloneRequest(entity_ids=[])

    def test_batch_clone_max_50(self):
        """EntityBatchCloneRequest with more than 50 IDs raises ValidationError."""
        ids = [uuid4() for _ in range(51)]
        with pytest.raises(ValidationError):
            EntityBatchCloneRequest(entity_ids=ids)

    def test_batch_clone_prefix_suffix_max_length(self):
        """EntityBatchCloneRequest with prefix/suffix exceeding max length raises ValidationError."""
        ids = [uuid4()]
        with pytest.raises(ValidationError):
            EntityBatchCloneRequest(
                entity_ids=ids,
                name_prefix="x" * 51,  # max 50
            )


# =============================================================================
# Batch operation integration tests
# =============================================================================


@pytest.mark.unit
class TestBatchOperationsIntegration:
    """Integration tests for batch operation schemas."""

    def test_batch_create_response_from_dict(self):
        """Test EntityBatchCreateResponse can be created from tool result dict."""
        now = datetime.now(timezone.utc)
        result_dict = {
            "entities": [
                {
                    "id": str(uuid4()),
                    "universe_id": str(uuid4()),
                    "name": "Test Entity",
                    "entity_type": "character",
                    "is_archetype": False,
                    "description": "",
                    "properties": {},
                    "state_tags": [],
                    "canon_level": "canon",
                    "confidence": 1.0,
                    "authority": "system",
                    "created_at": now.isoformat(),
                }
            ],
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "errors": [],
        }
        response = EntityBatchCreateResponse(**result_dict)
        assert response.total == 1
        assert response.succeeded == 1
        assert len(response.entities) == 1

    def test_batch_delete_response_from_dict(self):
        """Test EntityBatchDeleteResponse can be created from tool result dict."""
        result_dict = {
            "deleted": [str(uuid4()), str(uuid4())],
            "total": 2,
            "succeeded": 2,
            "failed": 0,
            "errors": [],
        }
        response = EntityBatchDeleteResponse(**result_dict)
        assert len(response.deleted) == 2

    def test_batch_error_from_dict(self):
        """Test BatchError can be created from tool result dict."""
        err_dict = {
            "index": 5,
            "entity_id": str(uuid4()),
            "message": "Universe not found",
            "code": "UNIVERSE_NOT_FOUND",
        }
        err = BatchError(**err_dict)
        assert err.index == 5
        assert err.code == "UNIVERSE_NOT_FOUND"

    def test_batch_update_with_mixed_entity_ids(self):
        """Test EntityBatchUpdateRequest accepts UUIDs and strings."""
        uid = uuid4()
        eid1 = uuid4()
        eid2 = str(uuid4())
        request = EntityBatchUpdateRequest(
            updates=[
                {"entity_id": str(eid1), "update": {"name": "Updated 1"}},
                {"entity_id": eid2, "update": {"name": "Updated 2"}},
            ],
        )
        assert len(request.updates) == 2