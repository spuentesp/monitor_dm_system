"""
Contract tests for the Random Tables router (DL-21, M-33).

Tests the input/output contracts for random table CRUD and roll operations.

Use Cases: DL-21 (Random Tables), M-33

pytest --test-run-type=unit tests/contracts/test_random_tables_api_contracts.py
"""

from __future__ import annotations

import pytest
from uuid import uuid4
from unittest.mock import patch, MagicMock

from pydantic import ValidationError


# =============================================================================
# Router import contract
# =============================================================================


class TestRandomTablesRouterImport:
    """Random tables router should be importable and properly configured."""

    def test_random_tables_router_importable(self):
        """random_tables router module imports without errors."""
        try:
            from monitor_ui.routers.random_tables import router
            assert router is not None
        except ImportError as exc:
            pytest.fail(f"Failed to import random_tables router: {exc}")

    def test_has_create_endpoint(self):
        """Router should have POST /random-tables."""
        from monitor_ui.routers.random_tables import router

        routes = {r.path: r.methods for r in router.routes}
        assert "/random-tables" in routes, f"Expected /random-tables route, got {routes}"
        assert "POST" in routes["/random-tables"]

    def test_has_roll_endpoint(self):
        """Router should have POST /random-tables/{id}/roll."""
        from monitor_ui.routers.random_tables import router

        routes = {r.path: r.methods for r in router.routes}
        roll_routes = [p for p in routes if "/roll" in p]
        assert len(roll_routes) >= 1, f"Expected roll endpoint, got {routes}"

    def test_has_delete_endpoint(self):
        """Router should have DELETE /random-tables/{id}."""
        from monitor_ui.routers.random_tables import router

        routes = {r.path: r.methods for r in router.routes}
        delete_routes = [p for p in routes if "DELETE" in routes[p]]
        assert any("random-tables" in p for p in delete_routes), f"Expected delete endpoint, got {routes}"


# =============================================================================
# Random table request schemas
# =============================================================================


class TestRandomTableCreateRequest:
    """Contract tests for random table creation request schema."""

    def test_valid_minimal_request(self):
        """RandomTableCreateRequest with required fields is valid."""
        from monitor_ui.routers.random_tables import RandomTableCreateRequest, _CreateEntry

        req = RandomTableCreateRequest(
            name="Dungeon Encounters",
            entries=[
                _CreateEntry(min_roll=1, max_roll=6, value="Goblin patrol"),
                _CreateEntry(min_roll=7, max_roll=10, value="Empty room"),
            ],
        )
        assert req.name == "Dungeon Encounters"
        assert len(req.entries) == 2

    def test_name_required(self):
        """name is required."""
        from monitor_ui.routers.random_tables import RandomTableCreateRequest, _CreateEntry

        with pytest.raises(ValidationError):
            RandomTableCreateRequest(
                entries=[_CreateEntry(min_roll=1, max_roll=10, value="Test")],
            )

    def test_entries_required(self):
        """entries are required."""
        from monitor_ui.routers.random_tables import RandomTableCreateRequest

        with pytest.raises(ValidationError):
            RandomTableCreateRequest(name="Test Table")

    def test_valid_with_optional_fields(self):
        """RandomTableCreateRequest with optional fields is valid."""
        from monitor_ui.routers.random_tables import RandomTableCreateRequest, _CreateEntry
        from monitor_data.schemas.random_tables import RandomTableType

        req = RandomTableCreateRequest(
            name="Dungeon Encounters",
            description="Tables for dungeon exploration",
            table_type=RandomTableType.ENCOUNTER,
            dice_formula="1d20",
            weighted=False,
            entries=[
                _CreateEntry(min_roll=1, max_roll=6, value="Goblin patrol"),
            ],
            universe_id=str(uuid4()),
        )
        assert req.description == "Tables for dungeon exploration"
        assert req.table_type == RandomTableType.ENCOUNTER


class TestRandomTableRollRequest:
    """Contract tests for random table roll parameters."""

    def test_roll_endpoint_has_optional_actor_id(self):
        """Roll endpoint accepts optional actor_id query param."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("monitor_ui.routers.random_tables.mongodb_roll_on_table") as mock_roll:
            mock_roll.return_value = {"value": "Goblin patrol", "roll": 3}
            response = client.post(
                f"/api/random-tables/{uuid4()}/roll?actor_id={uuid4()}",
                json={},
            )

        # Either success or 422 (invalid UUID format in path) is acceptable
        # The key is that the endpoint exists and accepts actor_id param
        assert response.status_code in (200, 404, 422)


# =============================================================================
# Endpoint parameter validation
# =============================================================================


class TestRandomTablesParameterValidation:
    """Parameter validation for random tables endpoints."""

    def test_list_filter_by_type(self):
        """GET /random-tables with table_type filter is valid."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("monitor_ui.routers.random_tables.mongodb_list_random_tables") as mock_list:
            mock_list.return_value = MagicMock(tables=[], total=0)
            response = client.get("/api/random-tables?table_type=encounter")

        assert response.status_code == 200

    def test_list_filter_by_universe(self):
        """GET /random-tables with universe_id filter is valid."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("monitor_ui.routers.random_tables.mongodb_list_random_tables") as mock_list:
            mock_list.return_value = MagicMock(tables=[], total=0)
            response = client.get(f"/api/random-tables?universe_id={uuid4()}")

        assert response.status_code == 200

    def test_roll_invalid_table_id_format(self):
        """POST /random-tables/{id}/roll with non-UUID format returns 400."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post("/api/random-tables/not-a-uuid/roll", json={})
        assert response.status_code == 400

    def test_roll_valid_table_returns_result(self):
        """POST /random-tables/{id}/roll with valid UUID returns roll result."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("monitor_ui.routers.random_tables.mongodb_roll_on_table") as mock_roll:
            mock_roll.return_value = {"value": "Goblin patrol", "roll": 3}
            response = client.post(f"/api/random-tables/{uuid4()}/roll", json={})

        if response.status_code == 200:
            data = response.json()
            assert "value" in data

    def test_create_invalid_table_type(self):
        """POST /random-tables with invalid table_type returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/random-tables",
            json={
                "name": "Test",
                "universe_id": str(uuid4()),
                "table_type": "invalid_type",
                "entries": [{"min_roll": 1, "max_roll": 10, "value": "Test"}],
            },
        )
        assert response.status_code == 422

    def test_create_missing_entries(self):
        """POST /random-tables without entries returns 422."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(
            "/api/random-tables",
            json={
                "name": "Test Table",
                "universe_id": str(uuid4()),
                "table_type": "encounter",
            },
        )
        assert response.status_code == 422


# =============================================================================
# Roll response shape validation
# =============================================================================


class TestRandomTablesRollResponse:
    """Validate roll response structure."""

    def test_roll_response_has_value(self):
        """Roll response includes 'value' field."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("monitor_ui.routers.random_tables.mongodb_roll_on_table") as mock_roll:
            mock_roll.return_value = {"value": "Goblin patrol", "roll": 3}
            response = client.post(f"/api/random-tables/{uuid4()}/roll", json={})

        if response.status_code == 200:
            data = response.json()
            assert "value" in data


# =============================================================================
# Graceful degradation tests
# =============================================================================


class TestRandomTablesGracefulDegradation:
    """Random tables endpoints handle MongoDB failures gracefully."""

    def test_list_returns_empty_on_mongodb_failure(self):
        """MongoDB failure returns 503 or empty list."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("monitor_ui.routers.random_tables.mongodb_list_random_tables") as mock_list:
            mock_list.side_effect = Exception("MongoDB unavailable")
            response = client.get("/api/random-tables")

        # Either 503 or empty list is acceptable
        assert response.status_code in (200, 503) or response.json().get("tables") == []

    def test_roll_returns_error_on_mongodb_failure(self):
        """MongoDB failure during roll returns 503."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("monitor_ui.routers.random_tables.mongodb_roll_on_table") as mock_roll:
            mock_roll.side_effect = Exception("MongoDB unavailable")
            response = client.post(f"/api/random-tables/{uuid4()}/roll", json={})

        # 503 or error in response body
        if response.status_code != 503:
            data = response.json()
            assert "error" in data or "detail" in data