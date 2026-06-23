"""Contract tests for the Memory schemas.

Verifies that memories Pydantic models:
- instantiate with valid data,
- enforce required fields and length / range constraints,
- enforce float range bounds (importance, certainty, emotional_valence).
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from monitor_data.schemas.memories import (
    MemoryCreate,
    MemoryEmbedRequest,
    MemoryEmbedResponse,
    MemoryFilter,
    MemoryListResponse,
    MemoryResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryUpdate,
)
from pydantic import ValidationError


pytestmark = pytest.mark.unit


# =============================================================================
# MemoryCreate
# =============================================================================


class TestMemoryCreate:
    def test_minimal(self):
        m = MemoryCreate(universe_id=uuid4(), entity_id=uuid4(), text="I remember the smell of the cave.")
        assert m.scene_id is None
        assert m.linked_fact_id is None
        assert m.emotional_valence == 0.0
        assert m.importance == 0.5
        assert m.certainty == 1.0
        assert m.metadata == {}

    def test_full(self):
        m = MemoryCreate(
            universe_id=uuid4(),
            entity_id=uuid4(),
            text="a vivid memory",
            scene_id=uuid4(),
            linked_fact_id=uuid4(),
            emotional_valence=0.8,
            importance=0.9,
            certainty=0.7,
            metadata={"tags": ["combat", "victory"]},
        )
        assert m.emotional_valence == 0.8
        assert m.importance == 0.9

    def test_text_required(self):
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), entity_id=uuid4())  # type: ignore[call-arg]

    def test_entity_id_required(self):
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), text="x")  # type: ignore[call-arg]

    def test_universe_id_required(self):
        with pytest.raises(ValidationError):
            MemoryCreate(entity_id=uuid4(), text="x")  # type: ignore[call-arg]

    def test_text_too_short(self):
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), entity_id=uuid4(), text="")

    def test_text_too_long(self):
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), entity_id=uuid4(), text="x" * 5001)

    def test_emotional_valence_out_of_range(self):
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), entity_id=uuid4(), text="x", emotional_valence=1.5)
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), entity_id=uuid4(), text="x", emotional_valence=-1.5)

    def test_importance_out_of_range(self):
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), entity_id=uuid4(), text="x", importance=2.0)
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), entity_id=uuid4(), text="x", importance=-0.1)

    def test_certainty_out_of_range(self):
        with pytest.raises(ValidationError):
            MemoryCreate(universe_id=uuid4(), entity_id=uuid4(), text="x", certainty=1.5)


# =============================================================================
# MemoryUpdate
# =============================================================================


class TestMemoryUpdate:
    def test_empty_update(self):
        u = MemoryUpdate()
        assert u.importance is None
        assert u.certainty is None
        assert u.emotional_valence is None
        assert u.metadata is None

    def test_partial_update(self):
        u = MemoryUpdate(importance=0.9, certainty=0.5)
        assert u.importance == 0.9
        assert u.certainty == 0.5

    def test_importance_bounds(self):
        with pytest.raises(ValidationError):
            MemoryUpdate(importance=-0.1)
        with pytest.raises(ValidationError):
            MemoryUpdate(importance=1.5)

    def test_certainty_bounds(self):
        with pytest.raises(ValidationError):
            MemoryUpdate(certainty=2.0)

    def test_valence_bounds(self):
        with pytest.raises(ValidationError):
            MemoryUpdate(emotional_valence=2.0)
        with pytest.raises(ValidationError):
            MemoryUpdate(emotional_valence=-2.0)


# =============================================================================
# MemoryFilter
# =============================================================================


class TestMemoryFilter:
    def test_defaults(self):
        f = MemoryFilter()
        assert f.universe_id is None
        assert f.entity_id is None
        assert f.scene_id is None
        assert f.min_importance is None
        assert f.max_importance is None
        assert f.min_emotional_valence is None
        assert f.max_emotional_valence is None
        assert f.limit == 100
        assert f.offset == 0

    def test_with_values(self):
        eid = uuid4()
        f = MemoryFilter(
            entity_id=eid, min_importance=0.5, max_importance=1.0, limit=50
        )
        assert f.entity_id == eid
        assert f.min_importance == 0.5
        assert f.limit == 50

    def test_importance_bounds(self):
        with pytest.raises(ValidationError):
            MemoryFilter(min_importance=-0.1)
        with pytest.raises(ValidationError):
            MemoryFilter(max_importance=1.5)

    def test_valence_bounds(self):
        with pytest.raises(ValidationError):
            MemoryFilter(min_emotional_valence=-2.0)
        with pytest.raises(ValidationError):
            MemoryFilter(max_emotional_valence=1.5)

    def test_limit_min(self):
        with pytest.raises(ValidationError):
            MemoryFilter(limit=0)

    def test_limit_max(self):
        with pytest.raises(ValidationError):
            MemoryFilter(limit=1001)

    def test_offset_min(self):
        with pytest.raises(ValidationError):
            MemoryFilter(offset=-1)


# =============================================================================
# MemoryResponse
# =============================================================================


class TestMemoryResponse:
    def test_minimal(self):
        now = datetime.now(timezone.utc)
        r = MemoryResponse(
            memory_id=uuid4(),
            universe_id=uuid4(),
            entity_id=uuid4(),
            text="x",
            scene_id=None,
            linked_fact_id=None,
            emotional_valence=0.5,
            importance=0.5,
            certainty=1.0,
            metadata={},
            created_at=now,
            last_accessed=now,
            access_count=0,
        )
        assert r.access_count == 0
        assert r.scene_id is None
        assert r.linked_fact_id is None

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            MemoryResponse()  # type: ignore[call-arg]


# =============================================================================
# MemoryListResponse
# =============================================================================


class TestMemoryListResponse:
    def test_empty(self):
        r = MemoryListResponse(memories=[], total=0, limit=100, offset=0)
        assert r.memories == []
        assert r.total == 0

    def test_with_memory(self):
        now = datetime.now(timezone.utc)
        mem = MemoryResponse(
            memory_id=uuid4(),
            universe_id=uuid4(),
            entity_id=uuid4(),
            text="x",
            scene_id=None,
            linked_fact_id=None,
            emotional_valence=0.0,
            importance=0.5,
            certainty=1.0,
            metadata={},
            created_at=now,
            last_accessed=now,
            access_count=1,
        )
        r = MemoryListResponse(memories=[mem], total=1, limit=100, offset=0)
        assert len(r.memories) == 1


# =============================================================================
# MemoryEmbedRequest
# =============================================================================


class TestMemoryEmbedRequest:
    def test_minimal(self):
        r = MemoryEmbedRequest(memory_id=uuid4(), universe_id=uuid4(), text="x", entity_id=uuid4())
        assert r.importance == 0.5
        assert r.scene_id is None
        assert r.metadata == {}

    def test_text_required(self):
        with pytest.raises(ValidationError):
            MemoryEmbedRequest(memory_id=uuid4(), universe_id=uuid4(), entity_id=uuid4())  # type: ignore[call-arg]

    def test_text_too_short(self):
        with pytest.raises(ValidationError):
            MemoryEmbedRequest(memory_id=uuid4(), universe_id=uuid4(), entity_id=uuid4(), text="")

    def test_text_too_long(self):
        with pytest.raises(ValidationError):
            MemoryEmbedRequest(
                memory_id=uuid4(), universe_id=uuid4(), entity_id=uuid4(), text="x" * 5001
            )

    def test_importance_bounds(self):
        with pytest.raises(ValidationError):
            MemoryEmbedRequest(
                memory_id=uuid4(), universe_id=uuid4(), entity_id=uuid4(), text="x", importance=-0.1
            )
        with pytest.raises(ValidationError):
            MemoryEmbedRequest(
                memory_id=uuid4(), universe_id=uuid4(), entity_id=uuid4(), text="x", importance=1.1
            )


# =============================================================================
# MemoryEmbedResponse
# =============================================================================


class TestMemoryEmbedResponse:
    def test_minimal(self):
        r = MemoryEmbedResponse(memory_id=uuid4(), point_id="x", success=True)
        assert r.collection == "memories"
        assert r.success is True

    def test_with_collection(self):
        r = MemoryEmbedResponse(
            memory_id=uuid4(), point_id="x", collection="custom", success=False
        )
        assert r.collection == "custom"
        assert r.success is False


# =============================================================================
# MemorySearchRequest
# =============================================================================


class TestMemorySearchRequest:
    def test_minimal(self):
        r = MemorySearchRequest(query_text="a query")
        assert r.universe_id is None
        assert r.entity_id is None
        assert r.scene_id is None
        assert r.min_importance is None
        assert r.top_k == 10

    def test_with_filters(self):
        r = MemorySearchRequest(
            query_text="x",
            universe_id=uuid4(),
            entity_id=uuid4(),
            scene_id=uuid4(),
            min_importance=0.5,
            top_k=20,
        )
        assert r.top_k == 20

    def test_query_required(self):
        with pytest.raises(ValidationError):
            MemorySearchRequest()  # type: ignore[call-arg]

    def test_query_too_short(self):
        with pytest.raises(ValidationError):
            MemorySearchRequest(query_text="")

    def test_query_too_long(self):
        with pytest.raises(ValidationError):
            MemorySearchRequest(query_text="x" * 5001)

    def test_top_k_bounds(self):
        with pytest.raises(ValidationError):
            MemorySearchRequest(query_text="x", top_k=0)
        with pytest.raises(ValidationError):
            MemorySearchRequest(query_text="x", top_k=101)

    def test_importance_bounds(self):
        with pytest.raises(ValidationError):
            MemorySearchRequest(query_text="x", min_importance=-0.1)


# =============================================================================
# MemorySearchResult
# =============================================================================


class TestMemorySearchResult:
    def test_minimal(self):
        r = MemorySearchResult(
            memory_id=uuid4(),
            entity_id=uuid4(),
            scene_id=None,
            importance=0.5,
            score=0.9,
            metadata={},
        )
        assert r.text is None
        assert r.scene_id is None
        assert r.score == 0.9

    def test_with_text(self):
        r = MemorySearchResult(
            memory_id=uuid4(),
            entity_id=uuid4(),
            text="the matched memory",
            scene_id=uuid4(),
            importance=0.8,
            score=0.95,
            metadata={},
        )
        assert r.text == "the matched memory"

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            MemorySearchResult()  # type: ignore[call-arg]


# =============================================================================
# MemorySearchResponse
# =============================================================================


class TestMemorySearchResponse:
    def test_empty(self):
        r = MemorySearchResponse(results=[], query="x", top_k=10)
        assert r.results == []
        assert r.query == "x"
        assert r.top_k == 10

    def test_with_result(self):
        result = MemorySearchResult(
            memory_id=uuid4(),
            entity_id=uuid4(),
            scene_id=None,
            importance=0.5,
            score=0.9,
            metadata={},
        )
        r = MemorySearchResponse(results=[result], query="x", top_k=10)
        assert len(r.results) == 1
