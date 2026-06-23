"""
Behavior tests for M-4 to M-12: Entity CRUD operations.

Verifies entity schemas, Neo4j entity tools, and entity router
without real DB connections.
"""

from __future__ import annotations

import pytest
from uuid import uuid4

from monitor_data.schemas.entities import (
    EntityCreate,
    EntityUpdate,
    StateTagsUpdate,
    EntityFilter,
    EntityListResponse,
    EntityBatchCreateRequest,
    BatchError,
)
from monitor_data.schemas.base import EntityType, CanonLevel, Authority, DetailLevel


# =============================================================================
# Entity Type Enum
# =============================================================================


class TestEntityTypeEnum:
    def test_all_types(self):
        """All entity types exist."""
        assert EntityType.CHARACTER.value == "character"
        assert EntityType.FACTION.value == "faction"
        assert EntityType.LOCATION.value == "location"
        assert EntityType.OBJECT.value == "object"
        assert EntityType.CONCEPT.value == "concept"
        assert EntityType.ORGANIZATION.value == "organization"


class TestCanonLevelEnum:
    def test_all_levels(self):
        """All canon levels exist."""
        assert CanonLevel.PROPOSED.value == "proposed"
        assert CanonLevel.CANON.value == "canon"
        assert CanonLevel.RUMOR.value == "rumor"
        assert CanonLevel.CHARACTER_BELIEF.value == "character_belief"
        assert CanonLevel.PLAYER_KNOWLEDGE.value == "player_knowledge"
        assert CanonLevel.RETCONNED.value == "retconned"
        assert CanonLevel.SUPERSEDED.value == "superseded"


class TestAuthorityEnum:
    def test_all_authorities(self):
        """All authority levels exist."""
        assert Authority.SOURCE.value == "source"
        assert Authority.GM.value == "gm"
        assert Authority.SYSTEM.value == "system"
        assert Authority.PLAYER.value == "player"


class TestDetailLevelEnum:
    def test_all_levels(self):
        """All detail levels exist."""
        assert DetailLevel.STUB.value == "stub"
        assert DetailLevel.SKETCHED.value == "sketched"
        assert DetailLevel.DETAILED.value == "detailed"
        assert DetailLevel.ELABORATED.value == "elaborated"


# =============================================================================
# Entity Create Schema
# =============================================================================


class TestEntityCreateSchema:
    def test_minimal_create(self):
        """EntityCreate with only required fields."""
        uid = uuid4()
        e = EntityCreate(
            universe_id=uid, name="Gandalf", entity_type=EntityType.CHARACTER
        )
        assert e.name == "Gandalf"
        assert e.entity_type == EntityType.CHARACTER
        assert e.is_archetype is False
        assert e.canon_level == CanonLevel.CANON
        assert e.confidence == 1.0
        assert e.detail_level == DetailLevel.STUB

    def test_create_with_all_fields(self):
        """EntityCreate can specify all fields."""
        uid = uuid4()
        e = EntityCreate(
            universe_id=uid,
            name="Mordor",
            entity_type=EntityType.LOCATION,
            description="A dark land",
            properties={"climate": "volcanic"},
            state_tags=["dangerous"],
            canon_level=CanonLevel.CANON,
            confidence=0.9,
            detail_level=DetailLevel.DETAILED,
            authority=Authority.GM,
        )
        assert e.description == "A dark land"
        assert e.canon_level == CanonLevel.CANON
        assert e.confidence == 0.9
        assert e.detail_level == DetailLevel.DETAILED
        assert e.authority == Authority.GM

    def test_create_archetype(self):
        """EntityCreate can create an archetype."""
        uid = uuid4()
        e = EntityCreate(
            universe_id=uid,
            name="Dragon",
            entity_type=EntityType.CHARACTER,
            is_archetype=True,
        )
        assert e.is_archetype is True

    def test_create_with_archetype_link(self):
        """EntityCreate can link to a parent archetype."""
        uid, aid = uuid4(), uuid4()
        e = EntityCreate(
            universe_id=uid,
            name="Smaug",
            entity_type=EntityType.CHARACTER,
            archetype_id=aid,
        )
        assert e.archetype_id == aid


# =============================================================================
# Entity Update Schema
# =============================================================================


class TestEntityUpdateSchema:
    def test_update_name(self):
        """EntityUpdate can change the name."""
        u = EntityUpdate(name="New Name")
        assert u.name == "New Name"
        assert u.description is None
        assert u.properties is None

    def test_update_description(self):
        """EntityUpdate can change the description."""
        u = EntityUpdate(description="Updated description")
        assert u.description == "Updated description"

    def test_update_properties(self):
        """EntityUpdate can change properties."""
        u = EntityUpdate(properties={"level": 5})
        assert u.properties == {"level": 5}


# =============================================================================
# State Tags Update Schema
# =============================================================================


class TestStateTagsUpdateSchema:
    def test_add_tags(self):
        """StateTagsUpdate can add tags."""
        s = StateTagsUpdate(add_tags=["wounded", "exhausted"])
        assert "wounded" in s.add_tags
        assert "exhausted" in s.add_tags
        assert s.remove_tags == []

    def test_remove_tags(self):
        """StateTagsUpdate can remove tags."""
        s = StateTagsUpdate(remove_tags=["hidden"])
        assert "hidden" in s.remove_tags
        assert s.add_tags == []

    def test_add_and_remove(self):
        """StateTagsUpdate can add and remove simultaneously."""
        s = StateTagsUpdate(add_tags=["wounded"], remove_tags=["hidden"])
        assert "wounded" in s.add_tags
        assert "hidden" in s.remove_tags

    def test_no_overlap_allowed(self):
        """StateTagsUpdate rejects overlapping add/remove tags."""
        with pytest.raises(Exception):
            StateTagsUpdate(add_tags=["wounded"], remove_tags=["wounded"])

    def test_no_duplicates_in_add(self):
        """StateTagsUpdate rejects duplicate add tags."""
        with pytest.raises(Exception):
            StateTagsUpdate(add_tags=["wounded", "wounded"])


# =============================================================================
# Entity Filter Schema
# =============================================================================


class TestEntityFilterSchema:
    def test_filter_defaults(self):
        """EntityFilter defaults to reasonable pagination."""
        f = EntityFilter()
        assert f.limit == 50
        assert f.offset == 0
        assert f.universe_id is None
        assert f.entity_type is None
        assert f.is_archetype is None
        assert f.name is None
        assert f.state_tags is None

    def test_filter_by_universe(self):
        """EntityFilter can filter by universe."""
        uid = uuid4()
        f = EntityFilter(universe_id=uid)
        assert f.universe_id == uid

    def test_filter_by_type(self):
        """EntityFilter can filter by entity type."""
        f = EntityFilter(entity_type=EntityType.CHARACTER)
        assert f.entity_type == EntityType.CHARACTER

    def test_filter_by_state_tags(self):
        """EntityFilter can filter by state tags (AND logic)."""
        f = EntityFilter(state_tags=["wounded", "hidden"])
        assert len(f.state_tags) == 2

    def test_filter_with_sort(self):
        """EntityFilter can specify sort order."""
        f = EntityFilter(sort_by="name", sort_order="asc")
        assert f.sort_by == "name"
        assert f.sort_order == "asc"


# =============================================================================
# Entity List Response Schema
# =============================================================================


class TestEntityListResponseSchema:
    def test_empty_response(self):
        """EntityListResponse with no entities."""
        r = EntityListResponse(entities=[], total=0, limit=50, offset=0)
        assert r.total == 0
        assert r.entities == []

    def test_response_with_pagination(self):
        """EntityListResponse includes pagination info."""
        r = EntityListResponse(entities=[], total=100, limit=50, offset=0)
        assert r.total == 100
        assert r.limit == 50


# =============================================================================
# Entity Batch Create Schema
# =============================================================================


class TestEntityBatchCreateSchema:
    def test_batch_create(self):
        """EntityBatchCreateRequest accepts multiple entities."""
        uid = uuid4()
        entities = [
            EntityCreate(
                universe_id=uid, name=f"Entity {i}", entity_type=EntityType.CHARACTER
            )
            for i in range(3)
        ]
        req = EntityBatchCreateRequest(universe_id=uid, entities=entities)
        assert len(req.entities) == 3
        assert req.continue_on_error is False

    def test_batch_create_continue_on_error(self):
        """EntityBatchCreateRequest can continue on error."""
        uid = uuid4()
        e = EntityCreate(universe_id=uid, name="Test", entity_type=EntityType.CHARACTER)
        req = EntityBatchCreateRequest(
            universe_id=uid,
            entities=[e],
            continue_on_error=True,
        )
        assert req.continue_on_error is True


class TestBatchErrorSchema:
    def test_batch_error(self):
        """BatchError describes a single failed entity creation."""
        err = BatchError(
            index=2, entity_id=None, message="Name too long", code="VALIDATION_ERROR"
        )
        assert err.index == 2
        assert err.message == "Name too long"
        assert err.code == "VALIDATION_ERROR"


# =============================================================================
# Neo4j Entity Tool Functions
# =============================================================================


class TestNeo4jEntityTools:
    def test_create_entity_exists(self):
        """neo4j_create_entity tool function is importable."""
        from monitor_data.tools.neo4j_tools.entities import neo4j_create_entity

        assert callable(neo4j_create_entity)

    def test_get_entity_exists(self):
        """neo4j_get_entity tool function is importable."""
        from monitor_data.tools.neo4j_tools.entities import neo4j_get_entity

        assert callable(neo4j_get_entity)

    def test_list_entities_exists(self):
        """neo4j_list_entities tool function is importable."""
        from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities

        assert callable(neo4j_list_entities)

    def test_update_entity_exists(self):
        """neo4j_update_entity tool function is importable."""
        from monitor_data.tools.neo4j_tools.entities import neo4j_update_entity

        assert callable(neo4j_update_entity)

    def test_delete_entity_exists(self):
        """neo4j_delete_entity tool function is importable."""
        from monitor_data.tools.neo4j_tools.entities import neo4j_delete_entity

        assert callable(neo4j_delete_entity)

    def test_set_state_tags_exists(self):
        """neo4j_set_state_tags tool function is importable."""
        from monitor_data.tools.neo4j_tools.entities import neo4j_set_state_tags

        assert callable(neo4j_set_state_tags)


# =============================================================================
# Entity Router
# =============================================================================


class TestEntityRouter:
    def test_router_importable(self):
        """Entity router module is importable."""
        from monitor_ui.routers.entities import router

        assert router is not None

    def test_router_has_list_route(self):
        """Entity router has a list endpoint."""
        from monitor_ui.routers.entities import router

        route_paths = [r.path for r in router.routes]
        assert any("entities" in p for p in route_paths)

    def test_router_has_create_route(self):
        """Entity router has a create endpoint."""
        from monitor_ui.routers.entities import router

        methods = [(r.path, r.methods) for r in router.routes if hasattr(r, "methods")]
        has_post = any("POST" in m for _, m in methods)
        assert has_post
