"""
DL-2: Entity CRUD — Contract Tests

Tests the input/output contracts for Neo4j entity tools.
These tests validate schema constraints, not database interactions.

Use Cases: DL-2 (Entity CRUD), M-6 to M-12
"""

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.base import (
    Authority,
    CanonLevel,
    DetailLevel,
    EntityClass,
    EntityType,
)
from monitor_data.schemas.entities import (
    EntityCreate,
    EntityFilter,
    EntityListResponse,
    EntityResponse,
    EntityUpdate,
    StateTagsUpdate,
)

# =============================================================================
# EntityCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityCreateContract:
    """Contract tests for EntityCreate schema."""

    def test_entity_create_minimal(self):
        """EntityCreate with only required fields is valid."""
        params = EntityCreate(
            universe_id=uuid4(),
            name="Gandalf",
            entity_type=EntityType.CHARACTER,
        )
        assert params.name == "Gandalf"
        assert params.entity_type == EntityType.CHARACTER
        assert params.is_archetype is False
        assert params.description == ""
        assert params.properties == {}
        assert params.state_tags == []
        assert params.archetype_id is None
        assert params.authority == Authority.SYSTEM
        assert params.canon_level == CanonLevel.CANON
        assert params.confidence == 1.0
        assert params.detail_level == DetailLevel.STUB

    def test_entity_create_with_all_fields(self):
        """EntityCreate with all optional fields populated."""
        uid = uuid4()
        aid = uuid4()
        params = EntityCreate(
            universe_id=uid,
            name="Legolas",
            entity_type=EntityType.CHARACTER,
            sub_type="elf",
            is_archetype=False,
            description="An elf from Mirkwood.",
            properties={"level": 10, "class": "ranger"},
            state_tags=["alive", "friendly"],
            archetype_id=aid,
            authority=Authority.GM,
            canon_level=CanonLevel.CANON,
            confidence=0.95,
            detail_level=DetailLevel.DETAILED,
        )
        assert params.sub_type == "elf"
        assert params.is_archetype is False
        assert params.description == "An elf from Mirkwood."
        assert params.properties["level"] == 10
        assert "alive" in params.state_tags
        assert params.archetype_id == aid
        assert params.detail_level == DetailLevel.DETAILED

    def test_entity_create_archetype(self):
        """EntityCreate can create an archetype."""
        params = EntityCreate(
            universe_id=uuid4(),
            name="Elf",
            entity_type=EntityType.CHARACTER,
            is_archetype=True,
        )
        assert params.is_archetype is True

    def test_entity_create_empty_name_fails(self):
        """EntityCreate with empty name raises ValidationError."""
        with pytest.raises(Exception):
            EntityCreate(
                universe_id=uuid4(),
                name="",
                entity_type=EntityType.CHARACTER,
            )

    def test_entity_create_too_long_name_fails(self):
        """EntityCreate with name > 200 chars raises ValidationError."""
        with pytest.raises(Exception):
            EntityCreate(
                universe_id=uuid4(),
                name="x" * 201,
                entity_type=EntityType.CHARACTER,
            )

    def test_entity_create_confidence_range(self):
        """EntityCreate confidence must be between 0.0 and 1.0."""
        with pytest.raises(Exception):
            EntityCreate(
                universe_id=uuid4(),
                name="test",
                entity_type=EntityType.CHARACTER,
                confidence=1.5,
            )
        with pytest.raises(Exception):
            EntityCreate(
                universe_id=uuid4(),
                name="test",
                entity_type=EntityType.CHARACTER,
                confidence=-0.1,
            )

    def test_entity_create_all_entity_types(self):
        """All EntityType enum values are valid."""
        for et in EntityType:
            params = EntityCreate(
                universe_id=uuid4(),
                name=f"Test {et.value}",
                entity_type=et,
            )
            assert params.entity_type == et

    def test_entity_create_all_canon_levels(self):
        """All CanonLevel enum values are valid for entities."""
        for cl in CanonLevel:
            params = EntityCreate(
                universe_id=uuid4(),
                name="test",
                entity_type=EntityType.CHARACTER,
                canon_level=cl,
            )
            assert params.canon_level == cl

    def test_entity_create_all_detail_levels(self):
        """All DetailLevel enum values are valid."""
        for dl in DetailLevel:
            params = EntityCreate(
                universe_id=uuid4(),
                name="test",
                entity_type=EntityType.CHARACTER,
                detail_level=dl,
            )
            assert params.detail_level == dl

    def test_entity_create_all_authority_types(self):
        """All Authority enum values are valid for entities."""
        for auth in Authority:
            params = EntityCreate(
                universe_id=uuid4(),
                name="test",
                entity_type=EntityType.CHARACTER,
                authority=auth,
            )
            assert params.authority == auth


# =============================================================================
# EntityUpdate contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityUpdateContract:
    """Contract tests for EntityUpdate schema."""

    def test_entity_update_all_none(self):
        """EntityUpdate with all fields None is valid (no-op update)."""
        update = EntityUpdate()
        assert update.name is None
        assert update.description is None
        assert update.properties is None

    def test_entity_update_name_only(self):
        """EntityUpdate can update just the name."""
        update = EntityUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.description is None

    def test_entity_update_properties(self):
        """EntityUpdate can update properties."""
        update = EntityUpdate(properties={"level": 5})
        assert update.properties == {"level": 5}

    def test_entity_update_empty_name_fails(self):
        """EntityUpdate with empty name raises ValidationError."""
        with pytest.raises(Exception):
            EntityUpdate(name="")


# =============================================================================
# StateTagsUpdate contract tests
# =============================================================================


@pytest.mark.unit
class TestStateTagsUpdateContract:
    """Contract tests for StateTagsUpdate schema."""

    def test_state_tags_update_defaults(self):
        """StateTagsUpdate with defaults is valid."""
        update = StateTagsUpdate()
        assert update.add_tags == []
        assert update.remove_tags == []

    def test_state_tags_update_add(self):
        """StateTagsUpdate can add tags."""
        update = StateTagsUpdate(add_tags=["alive", "friendly"])
        assert "alive" in update.add_tags
        assert "friendly" in update.add_tags

    def test_state_tags_update_remove(self):
        """StateTagsUpdate can remove tags."""
        update = StateTagsUpdate(remove_tags=["dead", "hostile"])
        assert "dead" in update.remove_tags

    def test_state_tags_update_add_and_remove(self):
        """StateTagsUpdate can add and remove tags simultaneously."""
        update = StateTagsUpdate(
            add_tags=["friendly"],
            remove_tags=["hostile"],
        )
        assert "friendly" in update.add_tags
        assert "hostile" in update.remove_tags

    def test_state_tags_update_overlapping_fails(self):
        """StateTagsUpdate with overlapping add/remove tags raises ValidationError."""
        with pytest.raises(Exception):
            StateTagsUpdate(
                add_tags=["alive"],
                remove_tags=["alive"],
            )


# =============================================================================
# EntityFilter contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityFilterContract:
    """Contract tests for EntityFilter schema."""

    def test_entity_filter_defaults(self):
        """EntityFilter has sensible defaults."""
        f = EntityFilter()
        assert f.universe_id is None
        assert f.entity_type is None
        assert f.is_archetype is None
        assert f.name is None
        assert f.state_tags is None
        assert f.limit == 50
        assert f.offset == 0
        assert f.sort_by == "created_at"
        assert f.sort_order == "desc"

    def test_entity_filter_with_universe(self):
        """EntityFilter can filter by universe_id."""
        uid = uuid4()
        f = EntityFilter(universe_id=uid)
        assert f.universe_id == uid

    def test_entity_filter_by_entity_type(self):
        """EntityFilter can filter by entity_type."""
        f = EntityFilter(entity_type=EntityType.CHARACTER)
        assert f.entity_type == EntityType.CHARACTER

    def test_entity_filter_by_archetype(self):
        """EntityFilter can filter by is_archetype."""
        f = EntityFilter(is_archetype=True)
        assert f.is_archetype is True

    def test_entity_filter_by_name(self):
        """EntityFilter can filter by name (case-insensitive contains)."""
        f = EntityFilter(name="gandalf")
        assert f.name == "gandalf"

    def test_entity_filter_by_state_tags(self):
        """EntityFilter can filter by state tags (AND logic)."""
        f = EntityFilter(state_tags=["alive", "friendly"])
        assert "alive" in f.state_tags
        assert "friendly" in f.state_tags

    def test_entity_filter_limit_range(self):
        """EntityFilter limit must be between 1 and 1000."""
        with pytest.raises(Exception):
            EntityFilter(limit=0)
        with pytest.raises(Exception):
            EntityFilter(limit=1001)

    def test_entity_filter_offset_range(self):
        """EntityFilter offset must be >= 0."""
        with pytest.raises(Exception):
            EntityFilter(offset=-1)

    def test_entity_filter_sort_options(self):
        """EntityFilter supports created_at and name sort."""
        f1 = EntityFilter(sort_by="created_at")
        assert f1.sort_by == "created_at"
        f2 = EntityFilter(sort_by="name")
        assert f2.sort_by == "name"

    def test_entity_filter_sort_order(self):
        """EntityFilter supports asc and desc sort order."""
        f1 = EntityFilter(sort_order="asc")
        assert f1.sort_order == "asc"
        f2 = EntityFilter(sort_order="desc")
        assert f2.sort_order == "desc"


# =============================================================================
# EntityResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityResponseContract:
    """Contract tests for EntityResponse schema."""

    def _make_response(self, **overrides):
        defaults = {
            "id": uuid4(),
            "universe_id": uuid4(),
            "name": "Gandalf",
            "entity_type": EntityType.CHARACTER,
            "sub_type": None,
            "is_archetype": False,
            "description": "A wizard.",
            "properties": {},
            "state_tags": [],
            "archetype_id": None,
            "canon_level": CanonLevel.CANON,
            "confidence": 1.0,
            "authority": Authority.GM,
            "detail_level": DetailLevel.STUB,
            "created_at": datetime.now(UTC),
            "updated_at": None,
        }
        defaults.update(overrides)
        return EntityResponse(**defaults)

    def test_entity_response_minimal(self):
        """EntityResponse with required fields is valid."""
        resp = self._make_response()
        assert resp.name == "Gandalf"
        assert resp.entity_type == EntityType.CHARACTER
        assert resp.state_tags == []

    def test_entity_response_with_archetype(self):
        """EntityResponse can represent an archetype."""
        resp = self._make_response(
            is_archetype=True,
            name="Elf",
        )
        assert resp.is_archetype is True
        assert resp.name == "Elf"

    def test_entity_response_with_properties(self):
        """EntityResponse can include type-specific properties."""
        resp = self._make_response(
            properties={"level": 10, "class": "ranger"},
        )
        assert resp.properties["level"] == 10

    def test_entity_response_with_state_tags(self):
        """EntityResponse can include state tags."""
        resp = self._make_response(
            state_tags=["alive", "friendly"],
        )
        assert "alive" in resp.state_tags
        assert "friendly" in resp.state_tags


# =============================================================================
# EntityListResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityListResponseContract:
    """Contract tests for EntityListResponse schema."""

    def test_entity_list_response_empty(self):
        """EntityListResponse with empty list is valid."""
        resp = EntityListResponse(
            entities=[],
            total=0,
            limit=50,
            offset=0,
        )
        assert resp.entities == []
        assert resp.total == 0

    def test_entity_list_response_with_entities(self):
        """EntityListResponse can include entities."""
        entity = EntityResponse(
            id=uuid4(),
            universe_id=uuid4(),
            name="Gandalf",
            entity_type=EntityType.CHARACTER,
            sub_type=None,
            is_archetype=False,
            description="A wizard.",
            properties={},
            state_tags=[],
            archetype_id=None,
            canon_level=CanonLevel.CANON,
            confidence=1.0,
            authority=Authority.GM,
            detail_level=DetailLevel.STUB,
            created_at=datetime.now(UTC),
            updated_at=None,
        )
        resp = EntityListResponse(
            entities=[entity],
            total=1,
            limit=50,
            offset=0,
        )
        assert resp.total == 1
        assert resp.entities[0].name == "Gandalf"


# =============================================================================
# EntityType enum contract tests
# =============================================================================


@pytest.mark.unit
class TestEntityTypeContract:
    """Contract tests for EntityType enum."""

    def test_entity_type_values(self):
        """EntityType has expected values."""
        assert EntityType.CHARACTER == "character"
        assert EntityType.FACTION == "faction"
        assert EntityType.LOCATION == "location"
        assert EntityType.OBJECT == "object"
        assert EntityType.CONCEPT == "concept"
        assert EntityType.ORGANIZATION == "organization"

    def test_entity_type_count(self):
        """EntityType has 6 values."""
        assert len(EntityType) == 6

    def test_entity_class_values(self):
        """EntityClass has expected values."""
        assert EntityClass.AXIOMATICA == "EntityArchetype"
        assert EntityClass.CONCRETA == "EntityInstance"

    def test_detail_level_values(self):
        """DetailLevel has expected values."""
        assert DetailLevel.STUB == "stub"
        assert DetailLevel.SKETCHED == "sketched"
        assert DetailLevel.DETAILED == "detailed"
        assert DetailLevel.ELABORATED == "elaborated"
