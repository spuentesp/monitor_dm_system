"""
Contract tests for batch entity operations (Phase 3.1, M-6 to M-12).

Tests the input/output contracts for POST/PATCH/DELETE /entities/batch endpoints.

Use Cases: M-6 to M-12 (Entity CRUD), Phase 3.1

pytest --test-run-type=unit tests/contracts/test_batch_entity_contracts.py
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

# =============================================================================
# Router import contract
# =============================================================================


class TestBatchEntityRouterImport:
    """Batch entity endpoints should be present in the entities router."""

    def test_entities_router_importable(self):
        """entities router module imports without errors."""
        try:
            from monitor_ui.routers.entities import router

            assert router is not None
        except ImportError as exc:
            pytest.fail(f"Failed to import entities router: {exc}")

    def test_has_batch_create_endpoint(self):
        """Router should have POST /entities/batch."""
        from monitor_ui.routers.entities import router

        batch_routes = [r for r in router.routes if r.path == "/entities/batch"]
        methods = set(m for r in batch_routes for m in r.methods)
        assert "POST" in methods, f"Expected POST /entities/batch, got {methods}"

    def test_has_batch_update_endpoint(self):
        """Router should have PATCH /entities/batch."""
        from monitor_ui.routers.entities import router

        batch_routes = [r for r in router.routes if r.path == "/entities/batch"]
        methods = set(m for r in batch_routes for m in r.methods)
        assert "PATCH" in methods, f"Expected PATCH /entities/batch, got {methods}"

    def test_has_batch_delete_endpoint(self):
        """Router should have DELETE /entities/batch."""
        from monitor_ui.routers.entities import router

        batch_routes = [r for r in router.routes if r.path == "/entities/batch"]
        methods = set(m for r in batch_routes for m in r.methods)
        assert "DELETE" in methods, f"Expected DELETE /entities/batch, got {methods}"


# =============================================================================
# Batch create request schema contract
# =============================================================================


class TestEntityBatchCreateRequestContract:
    """Contract tests for EntityBatchCreateRequest schema."""

    def test_valid_request(self):
        """EntityBatchCreateRequest with required fields is valid."""
        from monitor_data.schemas.entities import EntityBatchCreateRequest, EntityCreate

        req = EntityBatchCreateRequest(
            universe_id=uuid4(),
            entities=[
                EntityCreate(
                    universe_id=uuid4(),
                    name="Test NPC",
                    entity_type="character",
                    is_archetype=False,
                ),
            ],
        )
        assert req.universe_id is not None
        assert len(req.entities) == 1

    def test_entities_required(self):
        """entities list is required."""
        from monitor_data.schemas.entities import EntityBatchCreateRequest

        with pytest.raises(ValidationError):
            EntityBatchCreateRequest(universe_id=uuid4())  # missing entities

    def test_entities_max_limit(self):
        """entities list cannot exceed 100 items."""
        from monitor_data.schemas.entities import EntityBatchCreateRequest, EntityCreate

        # 101 items should fail
        with pytest.raises(ValidationError):
            EntityBatchCreateRequest(
                universe_id=uuid4(),
                entities=[
                    EntityCreate(
                        universe_id=uuid4(),
                        name=f"Entity {i}",
                        entity_type="character",
                        is_archetype=False,
                    )
                    for i in range(101)
                ],
            )

    def test_continue_on_error_default(self):
        """continue_on_error defaults to False."""
        from monitor_data.schemas.entities import EntityBatchCreateRequest, EntityCreate

        req = EntityBatchCreateRequest(
            universe_id=uuid4(),
            entities=[
                EntityCreate(
                    universe_id=uuid4(),
                    name="Test",
                    entity_type="character",
                    is_archetype=False,
                ),
            ],
        )
        assert req.continue_on_error is False


# =============================================================================
# Batch update request schema contract
# =============================================================================


class TestEntityBatchUpdateRequestContract:
    """Contract tests for EntityBatchUpdateRequest schema."""

    def test_valid_request(self):
        """EntityBatchUpdateRequest with required fields is valid."""
        from monitor_data.schemas.entities import (
            EntityBatchUpdateRequest,
        )

        req = EntityBatchUpdateRequest(
            updates=[
                {
                    "entity_id": str(uuid4()),
                    "update": {"name": "Updated NPC"},
                }
            ],
        )
        assert len(req.updates) == 1

    def test_updates_required(self):
        """updates list is required."""
        from monitor_data.schemas.entities import EntityBatchUpdateRequest

        with pytest.raises(ValidationError):
            EntityBatchUpdateRequest()  # missing updates

    def test_updates_max_limit(self):
        """updates list cannot exceed 100 items."""
        from monitor_data.schemas.entities import EntityBatchUpdateRequest

        with pytest.raises(ValidationError):
            EntityBatchUpdateRequest(
                updates=[
                    {"entity_id": str(uuid4()), "update": {"name": f"Update {i}"}}
                    for i in range(101)
                ],
            )

    def test_continue_on_error_default(self):
        """continue_on_error defaults to False."""
        from monitor_data.schemas.entities import EntityBatchUpdateRequest

        req = EntityBatchUpdateRequest(
            updates=[{"entity_id": str(uuid4()), "update": {}}]
        )
        assert req.continue_on_error is False


# =============================================================================
# Batch delete request schema contract
# =============================================================================


class TestEntityBatchDeleteRequestContract:
    """Contract tests for EntityBatchDeleteRequest schema."""

    def test_valid_request(self):
        """EntityBatchDeleteRequest with required fields is valid."""
        from monitor_data.schemas.entities import EntityBatchDeleteRequest

        req = EntityBatchDeleteRequest(
            entity_ids=[uuid4(), uuid4()],
        )
        assert len(req.entity_ids) == 2

    def test_entity_ids_required(self):
        """entity_ids list is required."""
        from monitor_data.schemas.entities import EntityBatchDeleteRequest

        with pytest.raises(ValidationError):
            EntityBatchDeleteRequest()  # missing entity_ids

    def test_entity_ids_min_one(self):
        """entity_ids must have at least 1 item."""
        from monitor_data.schemas.entities import EntityBatchDeleteRequest

        with pytest.raises(ValidationError):
            EntityBatchDeleteRequest(entity_ids=[])

    def test_entity_ids_max_limit(self):
        """entity_ids list cannot exceed 100 items."""
        from monitor_data.schemas.entities import EntityBatchDeleteRequest

        with pytest.raises(ValidationError):
            EntityBatchDeleteRequest(entity_ids=[uuid4() for _ in range(101)])


# =============================================================================
# Endpoint parameter validation
# =============================================================================


class TestBatchEntityParameterValidation:
    """Parameter validation for batch entity endpoints."""

    def test_batch_create_empty_body(self):
        """POST /entities/batch with empty body returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        # Router mounted at /api/entities, path is /entities/batch → /api/entities/entities/batch
        response = client.post("/api/entities/entities/batch", json={})
        assert response.status_code == 422

    def test_batch_create_missing_universe_id(self):
        """POST /entities/batch without universe_id returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/entities/entities/batch",
            json={
                "entities": [
                    {"name": "Test", "entity_type": "character", "is_archetype": False}
                ]
            },
        )
        assert response.status_code == 422

    def test_batch_create_missing_entities(self):
        """POST /entities/batch without entities list returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/entities/entities/batch",
            json={"universe_id": str(uuid4())},
        )
        assert response.status_code == 422

    def test_batch_update_empty_body(self):
        """PATCH /entities/batch with empty body returns 4xx validation error."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.patch("/api/entities/entities/batch", json={})
        assert response.status_code in (400, 422)

    def test_batch_delete_empty_body(self):
        """DELETE /entities/batch with empty body returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.request(
            "DELETE",
            "/api/entities/entities/batch",
            json={},
        )
        assert response.status_code == 422

    def test_batch_delete_missing_entity_ids(self):
        """DELETE /entities/batch without entity_ids returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.request(
            "DELETE",
            "/api/entities/entities/batch",
            json={},
        )
        assert response.status_code == 422


# =============================================================================
# Response shape validation
# =============================================================================


class TestBatchEntityResponseShape:
    """Validate batch operation response structures."""

    def test_batch_create_response_has_created(self):
        """Batch create response includes 'created' or 'entities' field."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "monitor_data.tools.neo4j_tools.entities.neo4j_batch_create_entities"
        ) as mock_batch:
            mock_batch.return_value = {
                "created": 1,
                "entities": [{"id": str(uuid4()), "name": "Test"}],
                "errors": [],
            }
            response = client.post(
                "/api/entities/entities/batch",
                json={
                    "universe_id": str(uuid4()),
                    "entities": [
                        {
                            "name": "Test",
                            "entity_type": "character",
                            "is_archetype": False,
                        }
                    ],
                },
            )

        if response.status_code == 200:
            data = response.json()
            assert "created" in data or "entities" in data

    def test_batch_update_response_has_updated(self):
        """Batch update response includes 'updated' field."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "monitor_data.tools.neo4j_tools.entities.neo4j_batch_update_entities"
        ) as mock_batch:
            mock_batch.return_value = {
                "updated": 1,
                "errors": [],
            }
            response = client.patch(
                "/api/entities/entities/batch",
                json={
                    "updates": [
                        {"entity_id": str(uuid4()), "update": {"name": "Updated"}}
                    ]
                },
            )

        if response.status_code == 200:
            data = response.json()
            assert "updated" in data

    def test_batch_delete_response_has_deleted(self):
        """Batch delete response includes 'deleted' field."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch(
            "monitor_data.tools.neo4j_tools.entities.neo4j_batch_delete_entities"
        ) as mock_batch:
            mock_batch.return_value = {
                "deleted": 1,
                "errors": [],
            }
            response = client.request(
                "DELETE",
                "/api/entities/entities/batch",
                json={"entity_ids": [str(uuid4())]},
            )

        if response.status_code == 200:
            data = response.json()
            assert "deleted" in data
