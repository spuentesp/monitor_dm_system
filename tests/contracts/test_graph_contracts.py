"""
Contract tests for the world graph explorer (Q-11).

Tests the graph endpoints for universe-scoped graphs and entity ego-graphs.

pytest --test-run-type=unit tests/contracts/test_graph_contracts.py
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4, UUID


# =============================================================================
# Schema / import contract tests
# =============================================================================


class TestGraphRouterContract:
    """Verify graph router has the expected Q-11 routes."""

    def test_graph_router_importable(self):
        """Graph router should be importable without errors."""
        try:
            from monitor_ui.routers.graph import router
            assert router is not None
        except ImportError as exc:
            pytest.fail(f"Failed to import graph router: {exc}")

    def test_has_world_graph_route(self):
        """Router should have GET /world."""
        from monitor_ui.routers.graph import router

        routes = {r.path: r.methods for r in router.routes}
        assert "/world" in routes, f"Expected /world route, got {routes}"
        assert "GET" in routes["/world"]

    def test_has_universe_graph_route(self):
        """Router should have GET /universes/{id}/graph."""
        from monitor_ui.routers.graph import router

        routes = {r.path: r.methods for r in router.routes}
        universe_graph_routes = [p for p in routes if "/universes/" in p and "/graph" in p and "/entity/" not in p]
        assert len(universe_graph_routes) >= 1, f"Expected universe graph route, got {routes}"

    def test_has_entity_ego_graph_route(self):
        """Router should have GET /universes/{id}/graph/entity/{eid}."""
        from monitor_ui.routers.graph import router

        routes = {r.path: r.methods for r in router.routes}
        ego_routes = [p for p in routes if "/entity/" in p and "/graph" in p]
        assert len(ego_routes) >= 1, f"Expected ego-graph route, got {routes}"


# =============================================================================
# Parameter validation tests
# =============================================================================


class TestGraphParameterValidation:
    """Validate query parameter constraints on graph endpoints."""

    def test_universe_graph_depth_bounds(self):
        """depth > 5 should be rejected."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        uid = str(uuid4())
        response = client.get(f"/api/graph/universes/{uid}/graph?depth=10")
        assert response.status_code == 422

    def test_universe_graph_negative_depth(self):
        """depth < 1 should be rejected."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        uid = str(uuid4())
        response = client.get(f"/api/graph/universes/{uid}/graph?depth=0")
        assert response.status_code == 422

    def test_ego_graph_invalid_universe_id(self):
        """universe_id must be a valid UUID."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        eid = str(uuid4())
        response = client.get(f"/api/graph/universes/not-a-uuid/graph/entity/{eid}")
        assert response.status_code == 422

    def test_ego_graph_invalid_entity_id(self):
        """entity_id must be a valid UUID."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        uid = str(uuid4())
        response = client.get(f"/api/graph/universes/{uid}/graph/entity/not-a-uuid")
        assert response.status_code == 422

    def test_ego_graph_depth_bounds(self):
        """depth > 3 should be rejected on ego graph."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        uid = str(uuid4())
        eid = str(uuid4())
        response = client.get(f"/api/graph/universes/{uid}/graph/entity/{eid}?depth=10")
        assert response.status_code == 422


# =============================================================================
# Response shape contract tests
# =============================================================================


class TestGraphResponseShape:
    """Validate graph response structures are correct."""

    def test_world_graph_response_shape(self):
        """GET /world returns {nodes, edges, entity_types, rel_types} on success."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app
        from unittest.mock import MagicMock

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        # Mock all Neo4j calls to avoid real DB - route is at monitor_ui.routers.graph
        with patch("monitor_ui.routers.graph.neo4j_ensure_omniverse"):
            with patch("monitor_ui.routers.graph.neo4j_list_multiverses", return_value=MagicMock(multiverses=[])):
                with patch("monitor_ui.routers.graph.neo4j_list_universes", return_value=MagicMock(entities=[])):
                    with patch("monitor_ui.routers.graph.neo4j_list_entities", return_value=MagicMock(entities=[])):
                        with patch("monitor_ui.routers.graph.neo4j_list_relationships", return_value=MagicMock(relationships=[])):
                            response = client.get("/api/graph/world")

        # Shape is always valid: either 200 with full data or error dict (fallback)
        data = response.json()
        if response.status_code == 200:
            assert "nodes" in data
            assert "edges" in data
            assert "entity_types" in data
            assert "rel_types" in data
        else:
            # Fallback error response still has valid shape
            assert data["nodes"] == []
            assert data["edges"] == []
            assert "error" in data


# =============================================================================
# Graceful degradation tests
# =============================================================================


class TestGraphGracefulDegradation:
    """Graph endpoints handle Neo4j failures gracefully."""

    def test_universe_graph_neox_failure_returns_error_dict(self):
        """Neo4j failure returns empty graph with error message."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        uid = str(uuid4())

        # Mock at the router level where it's imported
        with patch("monitor_ui.routers.graph.neo4j_list_universes", side_effect=RuntimeError("Neo4j unavailable")):
            response = client.get(f"/api/graph/universes/{uid}/graph")
            assert response.status_code == 200
            data = response.json()
            assert data["nodes"] == []
            assert data["edges"] == []
            assert "error" in data

    def test_ego_graph_entity_not_found(self):
        """Ego graph returns error when entity not found."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        uid = str(uuid4())
        eid = str(uuid4())

        with patch("monitor_ui.routers.graph.neo4j_list_entities", return_value=MagicMock(entities=[])):
            response = client.get(f"/api/graph/universes/{uid}/graph/entity/{eid}")
            assert response.status_code == 200
            data = response.json()
            assert data["nodes"] == []
            assert data["edges"] == []
            assert "error" in data