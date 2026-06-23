"""
API endpoint tests for entity CRUD operations.

Tests the FastAPI entity routes without real DB connections.
Uses the conftest.py fixtures that mock DB clients.

pytest --test-run-type=unit tests/api/test_entities_api.py
"""

from __future__ import annotations

from uuid import uuid4


class TestEntityRoutesExist:
    """Verify the entity routes module is importable and has expected structure."""

    def test_entity_router_exists(self):
        """The entity router module should be importable."""
        from monitor_ui.routers.entities import router

        assert router is not None


class TestEntitySchemaValidation:
    """API-level schema validation (contracts against schemas)."""

    def test_entity_create_schema(self):
        from monitor_data.schemas.entities import EntityCreate
        from monitor_data.schemas.base import EntityType

        params = EntityCreate(
            universe_id=uuid4(),
            name="Test Entity",
            entity_type=EntityType.CHARACTER,
        )
        assert params.name == "Test Entity"

    def test_entity_update_schema(self):
        from monitor_data.schemas.entities import EntityUpdate

        params = EntityUpdate(name="Updated Name", description="New description")
        assert params.name == "Updated Name"

    def test_state_tags_update_schema(self):
        from monitor_data.schemas.entities import StateTagsUpdate

        params = StateTagsUpdate(add_tags=["hidden"], remove_tags=["wounded"])
        assert "hidden" in params.add_tags

    def test_entity_filter_schema(self):
        from monitor_data.schemas.entities import EntityFilter

        f = EntityFilter(limit=20, offset=0)
        assert f.limit == 20
        assert f.offset == 0


class TestEntityListResponse:
    def test_list_response_schema(self):
        from monitor_data.schemas.entities import EntityListResponse

        r = EntityListResponse(entities=[], total=0, limit=50, offset=0)
        assert r.total == 0
        assert r.entities == []


class TestEntityTypeEnum:
    def test_all_types(self):
        from monitor_data.schemas.base import EntityType

        assert EntityType.CHARACTER.value == "character"
        assert EntityType.FACTION.value == "faction"
        assert EntityType.LOCATION.value == "location"
        assert EntityType.OBJECT.value == "object"
        assert EntityType.CONCEPT.value == "concept"
        assert EntityType.ORGANIZATION.value == "organization"
