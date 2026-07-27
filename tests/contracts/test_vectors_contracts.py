"""Contract tests for the vector embedding schemas.

Verifies that vectors Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce numeric / length constraints.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from monitor_data.schemas.vectors import (
    VALID_COLLECTIONS,
    CollectionInfo,
    CollectionInfoRequest,
    CollectionInfoResponse,
    EntityChunkPayload,
    KnowledgeChunkPayload,
    MemoryChunkPayload,
    SceneChunkPayload,
    ScoredVector,
    SnippetChunkPayload,
    VectorBatchUpsertRequest,
    VectorCollection,
    VectorDeleteByFilterRequest,
    VectorDeleteRequest,
    VectorDeleteResponse,
    VectorFilter,
    VectorPoint,
    VectorSearchRequest,
    VectorSearchResponse,
    VectorUpsertRequest,
    VectorUpsertResponse,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# =============================================================================
# VectorCollection
# =============================================================================


class TestVectorCollection:
    def test_values(self):
        assert VectorCollection.SCENES.value == "scenes"
        assert VectorCollection.MEMORIES.value == "memories"
        assert VectorCollection.SNIPPETS.value == "snippets"
        assert VectorCollection.ENTITIES.value == "entities"
        assert VectorCollection.KNOWLEDGE.value == "knowledge"

    def test_iteration(self):
        assert len(list(VectorCollection)) == 5

    def test_valid_collections_set(self):
        assert {
            "scenes",
            "memories",
            "snippets",
            "entities",
            "knowledge",
        } == VALID_COLLECTIONS


# =============================================================================
# SceneChunkPayload
# =============================================================================


class TestSceneChunkPayload:
    def test_minimal(self):
        p = SceneChunkPayload(
            scene_id="scene-1",
            story_id="story-1",
            universe_id="u-1",
            text="The party entered the tavern.",
            type="scene_summary",
            timestamp="2026-06-01T12:00:00Z",
        )
        assert p.play_session_id is None
        assert p.temporal_mode is None

    def test_with_session(self):
        p = SceneChunkPayload(
            scene_id="s",
            story_id="s",
            universe_id="u",
            text="x",
            type="turn",
            play_session_id="ps-1",
            temporal_mode="flashback",
            timestamp="t",
        )
        assert p.play_session_id == "ps-1"
        assert p.temporal_mode == "flashback"

    def test_required_text(self):
        with pytest.raises(ValidationError):
            SceneChunkPayload(
                scene_id="s", story_id="s", universe_id="u", type="x", timestamp="t"
            )

    def test_required_type(self):
        with pytest.raises(ValidationError):
            SceneChunkPayload(
                scene_id="s", story_id="s", universe_id="u", text="x", timestamp="t"
            )


# =============================================================================
# MemoryChunkPayload
# =============================================================================


class TestMemoryChunkPayload:
    def test_minimal(self):
        p = MemoryChunkPayload(
            memory_id="m-1",
            entity_id="e-1",
            text="I remember the smell of the bakery.",
            importance=0.8,
            emotional_valence=0.5,
            certainty=0.95,
            timestamp="2026-06-01T12:00:00Z",
        )
        assert p.universe_id is None

    def test_with_universe(self):
        p = MemoryChunkPayload(
            memory_id="m",
            entity_id="e",
            universe_id="u",
            text="x",
            importance=0.5,
            emotional_valence=0.0,
            certainty=1.0,
            timestamp="t",
        )
        assert p.universe_id == "u"


# =============================================================================
# SnippetChunkPayload
# =============================================================================


class TestSnippetChunkPayload:
    def test_minimal(self):
        p = SnippetChunkPayload(
            snippet_id="sn-1",
            doc_id="d-1",
            source_id="src-1",
            universe_id="u-1",
            text="From the rulebook...",
        )
        assert p.page is None
        assert p.section is None
        assert p.ingestion_job_id is None

    def test_with_metadata(self):
        p = SnippetChunkPayload(
            snippet_id="sn",
            doc_id="d",
            source_id="s",
            universe_id="u",
            text="x",
            page=42,
            section="Chapter 3",
            ingestion_job_id="job-1",
        )
        assert p.page == 42
        assert p.section == "Chapter 3"


# =============================================================================
# EntityChunkPayload
# =============================================================================


class TestEntityChunkPayload:
    def test_minimal(self):
        p = EntityChunkPayload(
            entity_id="e-1",
            universe_id="u-1",
            name="Bartholomew",
            entity_type="character",
            is_archetype=False,
            text="Bartholomew is a gruff innkeeper.",
            timestamp="t",
        )
        assert p.detail_level is None
        assert p.tags == []

    def test_with_tags(self):
        p = EntityChunkPayload(
            entity_id="e",
            universe_id="u",
            name="x",
            entity_type="location",
            is_archetype=True,
            detail_level="detailed",
            tags=["tavern", "neutral"],
            text="x",
            timestamp="t",
        )
        assert "tavern" in p.tags
        assert p.detail_level == "detailed"


# =============================================================================
# KnowledgeChunkPayload
# =============================================================================


class TestKnowledgeChunkPayload:
    def test_minimal(self):
        p = KnowledgeChunkPayload(
            node_id="n-1",
            node_type="axiom",
            universe_id="u-1",
            text="The axiom text",
            canon_level="canon",
            timestamp="t",
        )
        assert p.domain is None

    def test_with_domain(self):
        p = KnowledgeChunkPayload(
            node_id="n",
            node_type="fact",
            universe_id="u",
            domain="magic",
            text="x",
            canon_level="proposed",
            timestamp="t",
        )
        assert p.domain == "magic"


# =============================================================================
# VectorPoint
# =============================================================================


class TestVectorPoint:
    def test_minimal(self):
        p = VectorPoint(
            id=uuid4(),
            vector=[0.1, 0.2, 0.3],
        )
        assert p.payload == {}
        assert len(p.vector) == 3

    def test_with_payload(self):
        p = VectorPoint(
            id=uuid4(),
            vector=[0.1] * 1536,
            payload={"scene_id": "s1", "type": "turn"},
        )
        assert p.payload["scene_id"] == "s1"

    def test_required_id(self):
        with pytest.raises(ValidationError):
            VectorPoint(vector=[0.1])  # type: ignore[call-arg]

    def test_required_vector(self):
        with pytest.raises(ValidationError):
            VectorPoint(id=uuid4())  # type: ignore[call-arg]


# =============================================================================
# VectorUpsertRequest / VectorBatchUpsertRequest
# =============================================================================


class TestVectorUpsertRequest:
    def test_minimal(self):
        r = VectorUpsertRequest(
            collection="scenes",
            id=uuid4(),
            vector=[0.1, 0.2],
        )
        assert r.payload == {}

    def test_with_payload(self):
        r = VectorUpsertRequest(
            collection="scenes",
            id=uuid4(),
            vector=[0.1],
            payload={"text": "x"},
        )
        assert r.payload["text"] == "x"


class TestVectorBatchUpsertRequest:
    def test_minimal(self):
        points = [
            VectorPoint(id=uuid4(), vector=[0.1]),
            VectorPoint(id=uuid4(), vector=[0.2]),
        ]
        r = VectorBatchUpsertRequest(collection="scenes", points=points)
        assert len(r.points) == 2

    def test_empty_points_rejected(self):
        with pytest.raises(ValidationError):
            VectorBatchUpsertRequest(collection="scenes", points=[])


# =============================================================================
# VectorUpsertResponse
# =============================================================================


class TestVectorUpsertResponse:
    def test_minimal(self):
        r = VectorUpsertResponse(
            success=True,
            collection="scenes",
            upserted_count=3,
            ids=[uuid4(), uuid4(), uuid4()],
        )
        assert r.success is True
        assert r.upserted_count == 3
        assert len(r.ids) == 3


# =============================================================================
# VectorFilter
# =============================================================================


class TestVectorFilter:
    def test_defaults(self):
        f = VectorFilter()
        assert f.story_id is None
        assert f.scene_id is None
        assert f.entity_id is None
        assert f.universe_id is None
        assert f.custom is None

    def test_with_uuids(self):
        f = VectorFilter(
            story_id=uuid4(),
            scene_id=uuid4(),
            entity_id=uuid4(),
            universe_id=uuid4(),
        )
        assert f.story_id is not None

    def test_with_entity_filter(self):
        f = VectorFilter(
            entity_type="character",
            is_archetype=False,
            detail_level="detailed",
        )
        assert f.entity_type == "character"
        assert f.is_archetype is False

    def test_with_knowledge_filter(self):
        f = VectorFilter(
            node_type="axiom",
            domain="magic",
            canon_level="canon",
        )
        assert f.node_type == "axiom"

    def test_with_custom(self):
        f = VectorFilter(custom={"must": [{"key": "x", "match": "y"}]})
        assert f.custom == {"must": [{"key": "x", "match": "y"}]}


# =============================================================================
# VectorSearchRequest
# =============================================================================


class TestVectorSearchRequest:
    def test_minimal(self):
        r = VectorSearchRequest(collection="scenes")
        assert r.top_k == 10
        assert r.query_vector == []
        assert r.query_text is None
        assert r.score_threshold is None
        assert r.filter is None
        assert r.keyword_filter is None

    def test_with_query_vector(self):
        r = VectorSearchRequest(collection="scenes", query_vector=[0.1, 0.2], top_k=20)
        assert r.top_k == 20

    def test_with_query_text(self):
        r = VectorSearchRequest(collection="scenes", query_text="find me a tavern")
        assert r.query_text == "find me a tavern"

    def test_top_k_min(self):
        with pytest.raises(ValidationError):
            VectorSearchRequest(collection="scenes", top_k=0)

    def test_score_threshold_bounds(self):
        with pytest.raises(ValidationError):
            VectorSearchRequest(collection="scenes", score_threshold=-0.01)
        with pytest.raises(ValidationError):
            VectorSearchRequest(collection="scenes", score_threshold=1.01)

    def test_score_threshold_bounds_ok(self):
        r = VectorSearchRequest(collection="scenes", score_threshold=0.0)
        assert r.score_threshold == 0.0
        r2 = VectorSearchRequest(collection="scenes", score_threshold=1.0)
        assert r2.score_threshold == 1.0

    def test_limit_alias_normalizes_to_top_k(self):
        r = VectorSearchRequest(collection="scenes", limit=25)
        assert r.top_k == 25


# =============================================================================
# ScoredVector / VectorSearchResponse
# =============================================================================


class TestScoredVector:
    def test_minimal(self):
        s = ScoredVector(id=uuid4(), score=0.92)
        assert s.payload == {}

    def test_with_payload(self):
        s = ScoredVector(id=uuid4(), score=0.5, payload={"text": "x"})
        assert s.payload["text"] == "x"


class TestVectorSearchResponse:
    def test_empty(self):
        r = VectorSearchResponse(collection="scenes", results=[], count=0)
        assert r.results == []
        assert r.count == 0

    def test_with_results(self):
        scored = ScoredVector(id=uuid4(), score=0.9)
        r = VectorSearchResponse(collection="scenes", results=[scored], count=1)
        assert len(r.results) == 1


# =============================================================================
# Delete schemas
# =============================================================================


class TestVectorDeleteRequest:
    def test_minimal(self):
        r = VectorDeleteRequest(collection="scenes", id=uuid4())
        assert r.collection == "scenes"


class TestVectorDeleteByFilterRequest:
    def test_minimal(self):
        f = VectorFilter(universe_id=uuid4())
        r = VectorDeleteByFilterRequest(collection="scenes", filter=f)
        assert r.filter.universe_id is not None

    def test_required_filter(self):
        with pytest.raises(ValidationError):
            VectorDeleteByFilterRequest(collection="scenes")  # type: ignore[call-arg]


class TestVectorDeleteResponse:
    def test_minimal(self):
        r = VectorDeleteResponse(success=True, collection="scenes", deleted_count=5)
        assert r.deleted_count == 5


# =============================================================================
# CollectionInfo schemas
# =============================================================================


class TestCollectionInfo:
    def test_minimal(self):
        c = CollectionInfo(
            name="scenes",
            vector_size=1536,
            points_count=100,
            distance="Cosine",
            status="green",
        )
        assert c.indexed_vectors_count is None

    def test_with_indexed(self):
        c = CollectionInfo(
            name="x",
            vector_size=1536,
            points_count=100,
            indexed_vectors_count=100,
            distance="Cosine",
            status="green",
        )
        assert c.indexed_vectors_count == 100

    def test_required_vector_size(self):
        with pytest.raises(ValidationError):
            CollectionInfo(name="x", points_count=0, distance="Cosine", status="green")

    def test_required_distance(self):
        with pytest.raises(ValidationError):
            CollectionInfo(
                name="x",
                vector_size=1536,
                points_count=0,
                status="green",
            )

    def test_required_status(self):
        with pytest.raises(ValidationError):
            CollectionInfo(
                name="x", vector_size=1536, points_count=0, distance="Cosine"
            )


class TestCollectionInfoRequest:
    def test_minimal(self):
        r = CollectionInfoRequest(collection="scenes")
        assert r.collection == "scenes"


class TestCollectionInfoResponse:
    def test_minimal(self):
        info = CollectionInfo(
            name="scenes",
            vector_size=1536,
            points_count=0,
            distance="Cosine",
            status="green",
        )
        r = CollectionInfoResponse(collection=info)
        assert r.collection.name == "scenes"

    def test_required_collection(self):
        with pytest.raises(ValidationError):
            CollectionInfoResponse()  # type: ignore[call-arg]
