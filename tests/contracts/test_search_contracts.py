"""
Contract tests for the semantic search router (Q-1 to Q-5).

Tests the search endpoint schemas and basic contract behavior
without requiring real Qdrant/embedding connections.

pytest --test-run-type=unit tests/contracts/test_search_contracts.py
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4, UUID


# =============================================================================
# Schema contract tests
# =============================================================================


class TestSearchResultItemContract:
    """SearchResultItem schema: all fields present and typed correctly."""

    def test_search_result_item_basic(self):
        from monitor_ui.routers.search import SearchResultItem

        item = SearchResultItem(
            id=str(uuid4()),
            collection="entities",
            score=0.95,
            payload={"name": "Gandalf", "entity_type": "character"},
            text="The wizard Gandalf",
            entity_type="character",
            universe_id=str(uuid4()),
        )
        assert item.collection == "entities"
        assert item.score == 0.95
        assert item.text == "The wizard Gandalf"
        assert item.entity_type == "character"

    def test_search_result_item_optional_fields(self):
        from monitor_ui.routers.search import SearchResultItem

        item = SearchResultItem(
            id=str(uuid4()),
            collection="scenes",
            score=0.87,
            payload={},
        )
        assert item.text is None
        assert item.entity_type is None
        assert item.universe_id is None
        assert item.story_id is None
        assert item.scene_id is None
        assert item.node_type is None
        assert item.canon_level is None

    def test_search_result_item_knowledge(self):
        from monitor_ui.routers.search import SearchResultItem

        item = SearchResultItem(
            id=str(uuid4()),
            collection="knowledge",
            score=0.78,
            payload={
                "node_type": "fact",
                "canon_level": "canon",
                "domain": "history",
                "universe_id": str(uuid4()),
            },
            text="The One Ring was forged by Sauron",
            node_type="fact",
            canon_level="canon",
        )
        assert item.node_type == "fact"
        assert item.canon_level == "canon"


class TestSemanticSearchResponseContract:
    """SemanticSearchResponse schema: merged + ranked results."""

    def test_response_basic(self):
        from monitor_ui.routers.search import SemanticSearchResponse, SearchResultItem

        results = [
            SearchResultItem(
                id=str(uuid4()),
                collection="entities",
                score=0.95,
                payload={},
            ),
            SearchResultItem(
                id=str(uuid4()),
                collection="knowledge",
                score=0.88,
                payload={},
            ),
        ]
        response = SemanticSearchResponse(
            query="wizard rings",
            collections_searched=["entities", "knowledge"],
            total_results=2,
            results=results,
        )
        assert response.query == "wizard rings"
        assert response.total_results == 2
        assert len(response.results) == 2
        assert response.collections_searched == ["entities", "knowledge"]

    def test_response_empty(self):
        from monitor_ui.routers.search import SemanticSearchResponse

        response = SemanticSearchResponse(
            query="nothing matches",
            collections_searched=["entities", "scenes", "knowledge"],
            total_results=0,
            results=[],
        )
        assert response.total_results == 0
        assert response.results == []

    def test_response_collections_tracked(self):
        from monitor_ui.routers.search import SemanticSearchResponse, SearchResultItem

        # Different collections
        results = [
            SearchResultItem(id=str(uuid4()), collection="entities", score=0.9, payload={}),
            SearchResultItem(id=str(uuid4()), collection="scenes", score=0.85, payload={}),
            SearchResultItem(id=str(uuid4()), collection="snippets", score=0.8, payload={}),
            SearchResultItem(id=str(uuid4()), collection="knowledge", score=0.75, payload={}),
        ]
        response = SemanticSearchResponse(
            query="ancient temple",
            collections_searched=["entities", "scenes", "snippets", "knowledge"],
            total_results=4,
            results=results,
        )
        assert set(response.collections_searched) == {
            "entities", "scenes", "snippets", "knowledge"
        }


# =============================================================================
# Route existence / import contract tests
# =============================================================================


class TestSearchRouterContract:
    """Verify search router is importable and has the expected routes."""

    def test_search_router_importable(self):
        """Search router should be importable without errors."""
        try:
            from monitor_ui.routers.search import router
            assert router is not None
        except ImportError as exc:
            pytest.fail(f"Failed to import search router: {exc}")

    def test_search_router_has_semantic_search_route(self):
        """Router should have a GET /search endpoint."""
        from monitor_ui.routers.search import router

        # List all registered routes
        routes = {r.path: r.methods for r in router.routes}
        assert "/search" in routes, f"Expected /search route, got {routes}"
        assert "GET" in routes["/search"], f"Expected GET method on /search"

    def test_search_router_has_universe_search_route(self):
        """Router should have a GET /universes/{universe_id}/search endpoint."""
        from monitor_ui.routers.search import router

        routes = {r.path: r.methods for r in router.routes}
        # Find universe-scoped search route
        universe_routes = [p for p in routes if "/universes/" in p and "/search" in p]
        assert len(universe_routes) >= 1, f"Expected universe search route, got {routes}"


# =============================================================================
# Parameter contract tests (via FastAPI TestClient)
# =============================================================================


class TestSearchParameterValidation:
    """Validate query parameter constraints are enforced by FastAPI."""

    def test_empty_query_rejected(self):
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/search/search?q=")
        # Empty string should fail min_length validation
        assert response.status_code == 422, f"Expected 422 for empty query, got {response.status_code}"

    def test_query_too_long_rejected(self):
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        long_query = "x" * 600  # > 500 char limit
        response = client.get(f"/api/search/search?q={long_query}")
        assert response.status_code == 422

    def test_limit_bounds_enforced(self):
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        # limit > 100 should be rejected
        response = client.get("/api/search/search?q=wizard&limit=200")
        assert response.status_code == 422

        # limit < 1 should be rejected
        response = client.get("/api/search/search?q=wizard&limit=0")
        assert response.status_code == 422

    def test_score_threshold_bounds_enforced(self):
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        # score_threshold > 1.0 should be rejected
        response = client.get("/api/search/search?q=wizard&score_threshold=1.5")
        assert response.status_code == 422

        # score_threshold < 0.0 should be rejected
        response = client.get("/api/search/search?q=wizard&score_threshold=-0.1")
        assert response.status_code == 422

    def test_universe_id_invalid_uuid_rejected(self):
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        response = client.get("/api/search/search?q=wizard&universe_id=not-a-uuid")
        assert response.status_code == 422


# =============================================================================
# Mock integration tests (Qdrant unavailable — graceful degradation)
# =============================================================================


class TestSearchGracefulDegradation:
    """Search should return 503 when embedding service is unavailable."""

    def test_embed_failure_returns_503(self):
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        with patch("monitor_ui.routers.search._embed_query_text") as mock_embed:
            mock_embed.side_effect = Exception("Embedding service unavailable")

            response = client.get("/api/search/search?q=wizard")
            # Should get a 503 (or 500) when embedding fails
            assert response.status_code in (500, 503), (
                f"Expected 500/503 on embed failure, got {response.status_code}: {response.text}"
            )

    def test_qdrant_failure_partial_results(self):
        """If one collection fails, return results from other collections."""
        from fastapi.testclient import TestClient
        from monitor_ui.main import create_app
        from monitor_data.schemas.vectors import VectorSearchResponse, ScoredVector
        from uuid import UUID

        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)

        # Track which collections were called
        called_collections: list[str] = []

        def mock_qdrant_search(params):
            col = params.collection
            called_collections.append(col)
            if col == "entities":
                # Simulate entities search succeeding
                return VectorSearchResponse(
                    collection=col,
                    results=[
                        ScoredVector(
                            id=UUID("00000000-0000-0000-0000-000000000001"),
                            score=0.9,
                            payload={"name": "Gandalf", "entity_type": "character"},
                        )
                    ],
                    count=1,
                )
            else:
                # Other collections fail
                raise RuntimeError(f"Qdrant unavailable for {col}")

        with patch("monitor_ui.routers.search.qdrant_search", mock_qdrant_search):
            with patch("monitor_ui.routers.search._embed_query_text", return_value=[0.1] * 1536):
                response = client.get("/api/search/search?q=wizard")
                # Should still return 200 with partial results
                assert response.status_code == 200, f"Expected 200 with partial results: {response.text}"
                data = response.json()
                assert data["query"] == "wizard"
                # entities collection should have been called and returned result
                assert "entities" in called_collections