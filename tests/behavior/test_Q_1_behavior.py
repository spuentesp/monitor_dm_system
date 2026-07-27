"""
Behavior tests for Q-1 to Q-5: Search & Query.

Verifies search schemas, vector operations, and search router
without real DB/LLM connections.
"""

from __future__ import annotations

from uuid import uuid4

from monitor_data.schemas.vectors import (
    ScoredVector,
    VectorBatchUpsertRequest,
    VectorCollection,
    VectorDeleteByFilterRequest,
    VectorDeleteRequest,
    VectorFilter,
    VectorPoint,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorUpsertRequest,
)

# =============================================================================
# Vector Collection Enum
# =============================================================================


class TestVectorCollectionEnum:
    def test_all_collections(self):
        """All vector collections exist."""
        assert VectorCollection.SCENES.value == "scenes"
        assert VectorCollection.MEMORIES.value == "memories"
        assert VectorCollection.SNIPPETS.value == "snippets"
        assert VectorCollection.ENTITIES.value == "entities"
        assert VectorCollection.KNOWLEDGE.value == "knowledge"


# =============================================================================
# Vector Upsert Schema
# =============================================================================


class TestVectorUpsertRequestSchema:
    def test_upsert_request(self):
        """VectorUpsertRequest requires collection, id, vector, payload."""
        req = VectorUpsertRequest(
            collection=VectorCollection.ENTITIES,
            id=uuid4(),
            vector=[0.1] * 384,
            payload={"name": "Test Entity"},
        )
        assert req.collection == VectorCollection.ENTITIES
        assert len(req.vector) == 384
        assert req.payload["name"] == "Test Entity"


class TestVectorBatchUpsertRequestSchema:
    def test_batch_upsert(self):
        """VectorBatchUpsertRequest accepts multiple points."""
        points = [
            VectorPoint(id=uuid4(), vector=[0.1] * 384, payload={"name": f"Entity {i}"})
            for i in range(3)
        ]
        req = VectorBatchUpsertRequest(
            collection=VectorCollection.ENTITIES, points=points
        )
        assert len(req.points) == 3


# =============================================================================
# Vector Search Schema
# =============================================================================


class TestVectorSearchRequestSchema:
    def test_search_with_vector(self):
        """VectorSearchRequest can search with a query vector."""
        req = VectorSearchRequest(
            collection=VectorCollection.ENTITIES,
            query_vector=[0.1] * 384,
            top_k=10,
        )
        assert req.collection == VectorCollection.ENTITIES
        assert req.top_k == 10

    def test_search_with_text(self):
        """VectorSearchRequest can search with query text."""
        req = VectorSearchRequest(
            collection=VectorCollection.SNIPPETS,
            query_text="ancient dragon lore",
            top_k=5,
        )
        assert req.query_text == "ancient dragon lore"
        assert req.top_k == 5

    def test_search_with_filter(self):
        """VectorSearchRequest can include filters."""
        uid = uuid4()
        vf = VectorFilter(universe_id=uid)
        req = VectorSearchRequest(
            collection=VectorCollection.ENTITIES,
            query_text="wizard",
            top_k=10,
            filter=vf,
        )
        assert req.filter.universe_id == uid

    def test_search_with_score_threshold(self):
        """VectorSearchRequest can set a minimum score threshold."""
        req = VectorSearchRequest(
            collection=VectorCollection.KNOWLEDGE,
            query_text="magic rules",
            top_k=20,
            score_threshold=0.7,
        )
        assert req.score_threshold == 0.7


class TestVectorFilterSchema:
    def test_empty_filter(self):
        """VectorFilter with no constraints matches everything."""
        vf = VectorFilter()
        assert vf.universe_id is None
        assert vf.entity_type is None
        assert vf.canon_level is None
        assert vf.story_id is None
        assert vf.scene_id is None

    def test_filter_by_universe(self):
        """VectorFilter can scope to a universe."""
        uid = uuid4()
        vf = VectorFilter(universe_id=uid)
        assert vf.universe_id == uid

    def test_filter_by_entity_type(self):
        """VectorFilter can scope to an entity type."""
        vf = VectorFilter(entity_type="character")
        assert vf.entity_type == "character"

    def test_filter_by_canon_level(self):
        """VectorFilter can scope to a canon level."""
        vf = VectorFilter(canon_level="canon")
        assert vf.canon_level == "canon"

    def test_filter_combined(self):
        """VectorFilter can combine multiple constraints."""
        uid = uuid4()
        vf = VectorFilter(universe_id=uid, entity_type="location", canon_level="canon")
        assert vf.universe_id == uid
        assert vf.entity_type == "location"
        assert vf.canon_level == "canon"


# =============================================================================
# Vector Search Response
# =============================================================================


class TestVectorSearchResponseSchema:
    def test_empty_response(self):
        """VectorSearchResponse with no results."""
        resp = VectorSearchResponse(
            collection=VectorCollection.ENTITIES, results=[], count=0
        )
        assert resp.count == 0
        assert resp.results == []

    def test_response_with_results(self):
        """VectorSearchResponse with scored results."""
        scored = ScoredVector(id=uuid4(), score=0.95, payload={"name": "Dragon"})
        resp = VectorSearchResponse(
            collection=VectorCollection.ENTITIES,
            results=[scored],
            count=1,
        )
        assert resp.count == 1
        assert resp.results[0].score == 0.95


class TestScoredVectorSchema:
    def test_scored_vector(self):
        """ScoredVector holds id, score, and payload."""
        vid = uuid4()
        sv = ScoredVector(id=vid, score=0.88, payload={"name": "Gandalf"})
        assert sv.id == vid
        assert sv.score == 0.88
        assert sv.payload["name"] == "Gandalf"


# =============================================================================
# Vector Delete Schemas
# =============================================================================


class TestVectorDeleteRequestSchema:
    def test_delete_by_id(self):
        """VectorDeleteRequest deletes a single vector by ID."""
        vid = uuid4()
        req = VectorDeleteRequest(collection=VectorCollection.ENTITIES, id=vid)
        assert req.collection == VectorCollection.ENTITIES
        assert req.id == vid


class TestVectorDeleteByFilterRequestSchema:
    def test_delete_by_filter(self):
        """VectorDeleteByFilterRequest deletes vectors matching a filter."""
        uid = uuid4()
        vf = VectorFilter(universe_id=uid)
        req = VectorDeleteByFilterRequest(
            collection=VectorCollection.ENTITIES, filter=vf
        )
        assert req.filter.universe_id == uid


# =============================================================================
# Qdrant Tool Functions
# =============================================================================


class TestQdrantToolFunctions:
    def test_upsert_exists(self):
        """qdrant_upsert tool function is importable."""
        from monitor_data.tools.qdrant_tools import qdrant_upsert

        assert callable(qdrant_upsert)

    def test_upsert_batch_exists(self):
        """qdrant_upsert_batch tool function is importable."""
        from monitor_data.tools.qdrant_tools import qdrant_upsert_batch

        assert callable(qdrant_upsert_batch)

    def test_search_exists(self):
        """qdrant_search tool function is importable."""
        from monitor_data.tools.qdrant_tools import qdrant_search

        assert callable(qdrant_search)

    def test_delete_exists(self):
        """qdrant_delete tool function is importable."""
        from monitor_data.tools.qdrant_tools import qdrant_delete

        assert callable(qdrant_delete)

    def test_delete_by_filter_exists(self):
        """qdrant_delete_by_filter tool function is importable."""
        from monitor_data.tools.qdrant_tools import qdrant_delete_by_filter

        assert callable(qdrant_delete_by_filter)


# =============================================================================
# Search Router
# =============================================================================


class TestSearchRouter:
    def test_router_importable(self):
        """Search router module is importable."""
        from monitor_ui.routers.search import router

        assert router is not None

    def test_router_has_search_route(self):
        """Search router has a search endpoint."""
        from monitor_ui.routers.search import router

        route_paths = [r.path for r in router.routes]
        assert any("search" in p for p in route_paths)


# =============================================================================
# Graph Router (Q-11 World Graph Explorer)
# =============================================================================


class TestGraphRouter:
    def test_router_importable(self):
        """Graph router module is importable."""
        from monitor_ui.routers.graph import router

        assert router is not None

    def test_router_has_world_route(self):
        """Graph router has a world endpoint."""
        from monitor_ui.routers.graph import router

        route_paths = [r.path for r in router.routes]
        assert any("world" in p or "graph" in p for p in route_paths)
