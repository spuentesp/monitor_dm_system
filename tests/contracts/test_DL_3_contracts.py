"""
DL-3: Facts, Events, and Axioms — Contract Tests

Tests the input/output contracts for Neo4j fact/event/axiom tools.
These tests validate schema constraints, not database interactions.

Use Cases: DL-3 (Facts/Events CRUD), DL-13 (Axioms)
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from monitor_data.schemas.base import (
    Authority,
    CanonLevel,
    AxiomAuthority,
    KnowledgeScope,
)
from monitor_data.schemas.facts import (
    FactCreate,
    FactUpdate,
    FactResponse,
    FactFilter,
    FactType,
    FactStatus,
    SimulationScope,
    EventCreate,
    EventResponse,
    EventFilter,
    AxiomCreate,
    AxiomUpdate,
    AxiomResponse,
)


# =============================================================================
# FactCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestFactCreateContract:
    """Contract tests for FactCreate schema."""

    def test_minimal_fact_create(self):
        """FactCreate with only required fields is valid."""
        params = FactCreate(
            universe_id=uuid4(),
            statement="The sky is blue.",
        )
        assert params.statement == "The sky is blue."
        assert params.fact_type == FactType.STATE
        assert params.canon_level == CanonLevel.PROPOSED
        assert params.confidence == 1.0
        assert params.authority == Authority.SYSTEM
        assert params.magnitude == 1
        assert params.scope == SimulationScope.LOCAL

    def test_fact_create_with_all_fields(self):
        """FactCreate with all optional fields populated."""
        uid = uuid4()
        eid = uuid4()
        sid = uuid4()
        params = FactCreate(
            universe_id=uid,
            statement="The dragon guards the treasure.",
            fact_type=FactType.RELATIONSHIP,
            magnitude=8,
            scope=SimulationScope.REGIONAL,
            time_ref=datetime.now(timezone.utc),
            duration=3600,
            properties={"location": "cave"},
            entity_ids=[eid],
            source_ids=[sid],
            snippet_ids=["snippet-1"],
            scene_ids=[uuid4()],
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
            confidence=0.95,
            authority=Authority.GM,
            status=FactStatus.ACTIVE,
            replaces=uuid4(),
        )
        assert params.fact_type == FactType.RELATIONSHIP
        assert params.magnitude == 8
        assert params.scope == SimulationScope.REGIONAL
        assert params.duration == 3600
        assert params.confidence == 0.95
        assert params.replaces is not None

    def test_fact_create_empty_statement_fails(self):
        """FactCreate with empty statement raises ValidationError."""
        with pytest.raises(Exception):
            FactCreate(universe_id=uuid4(), statement="")

    def test_fact_create_too_long_statement_fails(self):
        """FactCreate with statement > 2000 chars raises ValidationError."""
        with pytest.raises(Exception):
            FactCreate(universe_id=uuid4(), statement="x" * 2001)

    def test_fact_create_confidence_range(self):
        """FactCreate confidence must be between 0.0 and 1.0."""
        with pytest.raises(Exception):
            FactCreate(universe_id=uuid4(), statement="test", confidence=1.5)
        with pytest.raises(Exception):
            FactCreate(universe_id=uuid4(), statement="test", confidence=-0.1)

    def test_fact_create_magnitude_range(self):
        """FactCreate magnitude must be between 1 and 10."""
        with pytest.raises(Exception):
            FactCreate(universe_id=uuid4(), statement="test", magnitude=0)
        with pytest.raises(Exception):
            FactCreate(universe_id=uuid4(), statement="test", magnitude=11)

    def test_fact_create_all_fact_types(self):
        """All FactType enum values are valid."""
        for ft in FactType:
            params = FactCreate(
                universe_id=uuid4(),
                statement=f"Test {ft.value}",
                fact_type=ft,
            )
            assert params.fact_type == ft

    def test_fact_create_all_canon_levels(self):
        """All CanonLevel enum values are valid for facts."""
        for cl in CanonLevel:
            params = FactCreate(
                universe_id=uuid4(),
                statement=f"Test {cl.value}",
                canon_level=cl,
            )
            assert params.canon_level == cl

    def test_fact_create_all_scopes(self):
        """All SimulationScope values are valid."""
        for scope in SimulationScope:
            params = FactCreate(
                universe_id=uuid4(),
                statement=f"Test {scope.value}",
                scope=scope,
            )
            assert params.scope == scope


# =============================================================================
# FactUpdate contract tests
# =============================================================================


@pytest.mark.unit
class TestFactUpdateContract:
    """Contract tests for FactUpdate schema."""

    def test_fact_update_all_none(self):
        """FactUpdate with all fields None is valid (no-op update)."""
        update = FactUpdate()
        assert update.statement is None
        assert update.canon_level is None
        assert update.confidence is None
        assert update.status is None
        assert update.properties is None

    def test_fact_update_statement_only(self):
        """FactUpdate can update just the statement."""
        update = FactUpdate(statement="Updated statement")
        assert update.statement == "Updated statement"
        assert update.canon_level is None

    def test_fact_update_canon_level(self):
        """FactUpdate can promote canon level."""
        update = FactUpdate(canon_level=CanonLevel.CANON)
        assert update.canon_level == CanonLevel.CANON

    def test_fact_update_confidence_range(self):
        """FactUpdate confidence must be between 0.0 and 1.0."""
        with pytest.raises(Exception):
            FactUpdate(confidence=1.5)
        with pytest.raises(Exception):
            FactUpdate(confidence=-0.1)

    def test_fact_update_empty_statement_fails(self):
        """FactUpdate with empty statement raises ValidationError."""
        with pytest.raises(Exception):
            FactUpdate(statement="")


# =============================================================================
# FactFilter contract tests
# =============================================================================


@pytest.mark.unit
class TestFactFilterContract:
    """Contract tests for FactFilter schema."""

    def test_fact_filter_defaults(self):
        """FactFilter has sensible defaults."""
        f = FactFilter()
        assert f.universe_id is None
        assert f.entity_id is None
        assert f.fact_type is None
        assert f.canon_level is None
        assert f.status == FactStatus.ACTIVE
        assert f.min_magnitude == 1
        assert f.scope is None
        assert f.limit == 30
        assert f.offset == 0

    def test_fact_filter_with_universe(self):
        """FactFilter can filter by universe_id."""
        uid = uuid4()
        f = FactFilter(universe_id=uid)
        assert f.universe_id == uid

    def test_fact_filter_limit_range(self):
        """FactFilter limit must be between 1 and 100."""
        with pytest.raises(Exception):
            FactFilter(limit=0)
        with pytest.raises(Exception):
            FactFilter(limit=101)

    def test_fact_filter_offset_range(self):
        """FactFilter offset must be >= 0."""
        with pytest.raises(Exception):
            FactFilter(offset=-1)


# =============================================================================
# FactResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestFactResponseContract:
    """Contract tests for FactResponse schema."""

    def _make_response(self, **overrides):
        defaults = {
            "id": uuid4(),
            "universe_id": uuid4(),
            "statement": "The sky is blue.",
            "fact_type": FactType.STATE,
            "magnitude": 1,
            "scope": SimulationScope.LOCAL,
            "canon_level": CanonLevel.CANON,
            "knowledge_scope": KnowledgeScope.WORLD,
            "confidence": 1.0,
            "authority": Authority.GM,
            "status": FactStatus.ACTIVE,
            "created_at": datetime.now(timezone.utc),
            "replaces": None,
            "properties": None,
        }
        defaults.update(overrides)
        return FactResponse(**defaults)

    def test_fact_response_minimal(self):
        """FactResponse with required fields is valid."""
        resp = self._make_response()
        assert resp.statement == "The sky is blue."
        assert resp.entity_ids == []
        assert resp.source_ids == []
        assert resp.snippet_ids == []
        assert resp.scene_ids == []

    def test_fact_response_with_relationships(self):
        """FactResponse can include relationship IDs."""
        eid = uuid4()
        sid = uuid4()
        resp = self._make_response(
            entity_ids=[eid],
            source_ids=[sid],
            snippet_ids=["snippet-1"],
            scene_ids=[uuid4()],
        )
        assert eid in resp.entity_ids
        assert sid in resp.source_ids
        assert "snippet-1" in resp.snippet_ids


# =============================================================================
# EventCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestEventCreateContract:
    """Contract tests for EventCreate schema."""

    def test_event_create_minimal(self):
        """EventCreate with required fields is valid."""
        params = EventCreate(
            universe_id=uuid4(),
            title="The Battle of Helm's Deep",
            start_time=datetime.now(timezone.utc),
        )
        assert params.title == "The Battle of Helm's Deep"
        assert params.magnitude == 5
        assert params.scope == SimulationScope.LOCAL
        assert params.canon_level == CanonLevel.PROPOSED

    def test_event_create_with_all_fields(self):
        """EventCreate with all optional fields populated."""
        uid = uuid4()
        eid = uuid4()
        sid = uuid4()
        now = datetime.now(timezone.utc)
        params = EventCreate(
            universe_id=uid,
            title="The Battle",
            description="A great battle occurred.",
            start_time=now,
            end_time=now,
            scene_id=uuid4(),
            magnitude=9,
            scope=SimulationScope.GLOBAL,
            properties={"casualties": 100},
            entity_ids=[eid],
            source_ids=[sid],
            timeline_after=[uuid4()],
            timeline_before=[uuid4()],
            causes=[uuid4()],
            canon_level=CanonLevel.CANON,
            knowledge_scope=KnowledgeScope.WORLD,
            confidence=0.9,
            authority=Authority.GM,
        )
        assert params.magnitude == 9
        assert params.scope == SimulationScope.GLOBAL
        assert params.end_time is not None
        assert len(params.timeline_after) == 1

    def test_event_create_empty_title_fails(self):
        """EventCreate with empty title raises ValidationError."""
        with pytest.raises(Exception):
            EventCreate(
                universe_id=uuid4(),
                title="",
                start_time=datetime.now(timezone.utc),
            )

    def test_event_create_too_long_title_fails(self):
        """EventCreate with title > 200 chars raises ValidationError."""
        with pytest.raises(Exception):
            EventCreate(
                universe_id=uuid4(),
                title="x" * 201,
                start_time=datetime.now(timezone.utc),
            )

    def test_event_create_magnitude_range(self):
        """EventCreate magnitude must be between 0 and 10."""
        with pytest.raises(Exception):
            EventCreate(
                universe_id=uuid4(),
                title="test",
                start_time=datetime.now(timezone.utc),
                magnitude=-1,
            )
        with pytest.raises(Exception):
            EventCreate(
                universe_id=uuid4(),
                title="test",
                start_time=datetime.now(timezone.utc),
                magnitude=11,
            )


# =============================================================================
# EventFilter contract tests
# =============================================================================


@pytest.mark.unit
class TestEventFilterContract:
    """Contract tests for EventFilter schema."""

    def test_event_filter_defaults(self):
        """EventFilter has sensible defaults."""
        f = EventFilter()
        assert f.universe_id is None
        assert f.scene_id is None
        assert f.entity_id is None
        assert f.canon_level is None
        assert f.min_magnitude == 1
        assert f.scope is None
        assert f.start_after is None
        assert f.start_before is None
        assert f.limit == 30
        assert f.offset == 0

    def test_event_filter_with_time_range(self):
        """EventFilter can filter by time range."""
        now = datetime.now(timezone.utc)
        f = EventFilter(start_after=now, start_before=now)
        assert f.start_after == now
        assert f.start_before == now


# =============================================================================
# AxiomCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestAxiomCreateContract:
    """Contract tests for AxiomCreate schema."""

    def test_axiom_create_minimal(self):
        """AxiomCreate with required fields is valid."""
        params = AxiomCreate(
            universe_id=uuid4(),
            statement="Magic exists in this world.",
            domain="magic",
        )
        assert params.statement == "Magic exists in this world."
        assert params.domain == "magic"
        assert params.magnitude == 8
        assert params.scope == SimulationScope.GLOBAL
        assert params.canon_level == CanonLevel.PROPOSED
        assert params.confidence == 0.9
        assert params.authority == AxiomAuthority.METAPHYSICS

    def test_axiom_create_with_all_fields(self):
        """AxiomCreate with all optional fields populated."""
        params = AxiomCreate(
            universe_id=uuid4(),
            statement="The gods are real.",
            domain="religion",
            magnitude=10,
            scope=SimulationScope.GLOBAL,
            source_ids=[uuid4()],
            source_ref="Page 42",
            canon_level=CanonLevel.CANON,
            confidence=1.0,
            authority=AxiomAuthority.METAPHYSICS,
            tags=["core", "religion"],
            properties={"importance": "high"},
        )
        assert params.magnitude == 10
        assert params.authority == AxiomAuthority.METAPHYSICS
        assert "core" in params.tags

    def test_axiom_create_empty_statement_fails(self):
        """AxiomCreate with empty statement raises ValidationError."""
        with pytest.raises(Exception):
            AxiomCreate(universe_id=uuid4(), statement="", domain="magic")

    def test_axiom_create_empty_domain_fails(self):
        """AxiomCreate with empty domain raises ValidationError."""
        with pytest.raises(Exception):
            AxiomCreate(universe_id=uuid4(), statement="test", domain="")

    def test_axiom_create_confidence_range(self):
        """AxiomCreate confidence must be between 0.0 and 1.0."""
        with pytest.raises(Exception):
            AxiomCreate(
                universe_id=uuid4(),
                statement="test",
                domain="magic",
                confidence=1.5,
            )

    def test_axiom_create_all_authority_types(self):
        """All AxiomAuthority enum values are valid."""
        for auth in AxiomAuthority:
            params = AxiomCreate(
                universe_id=uuid4(),
                statement=f"Test {auth.value}",
                domain="test",
                authority=auth,
            )
            assert params.authority == auth


# =============================================================================
# AxiomUpdate contract tests
# =============================================================================


@pytest.mark.unit
class TestAxiomUpdateContract:
    """Contract tests for AxiomUpdate schema."""

    def test_axiom_update_all_none(self):
        """AxiomUpdate with all fields None is valid (no-op update)."""
        update = AxiomUpdate()
        assert update.statement is None
        assert update.domain is None
        assert update.magnitude is None
        assert update.scope is None
        assert update.canon_level is None
        assert update.confidence is None
        assert update.tags is None
        assert update.properties is None

    def test_axiom_update_statement_only(self):
        """AxiomUpdate can update just the statement."""
        update = AxiomUpdate(statement="Updated axiom")
        assert update.statement == "Updated axiom"
        assert update.domain is None

    def test_axiom_update_confidence_range(self):
        """AxiomUpdate confidence must be between 0.0 and 1.0."""
        with pytest.raises(Exception):
            AxiomUpdate(confidence=1.5)
        with pytest.raises(Exception):
            AxiomUpdate(confidence=-0.1)

    def test_axiom_update_magnitude_range(self):
        """AxiomUpdate magnitude must be between 1 and 10."""
        with pytest.raises(Exception):
            AxiomUpdate(magnitude=0)
        with pytest.raises(Exception):
            AxiomUpdate(magnitude=11)


# =============================================================================
# AxiomResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestAxiomResponseContract:
    """Contract tests for AxiomResponse schema."""

    def test_axiom_response_minimal(self):
        """AxiomResponse with required fields is valid."""
        resp = AxiomResponse(
            id=uuid4(),
            universe_id=uuid4(),
            statement="Magic exists.",
            domain="magic",
            magnitude=8,
            scope=SimulationScope.GLOBAL,
            canon_level=CanonLevel.CANON,
            confidence=0.9,
            authority=AxiomAuthority.METAPHYSICS,
            source_ref=None,
            tags=[],
            properties=None,
            created_at=datetime.now(timezone.utc),
        )
        assert resp.statement == "Magic exists."
        assert resp.source_ids == []

    def test_axiom_response_with_tags(self):
        """AxiomResponse can include tags."""
        resp = AxiomResponse(
            id=uuid4(),
            universe_id=uuid4(),
            statement="Magic exists.",
            domain="magic",
            magnitude=8,
            scope=SimulationScope.GLOBAL,
            canon_level=CanonLevel.CANON,
            confidence=0.9,
            authority=AxiomAuthority.METAPHYSICS,
            source_ref=None,
            tags=["core", "magic"],
            properties={"importance": "high"},
            created_at=datetime.now(timezone.utc),
        )
        assert "core" in resp.tags
        assert "magic" in resp.tags


# =============================================================================
# SimulationScope and FactType enum contract tests
# =============================================================================


@pytest.mark.unit
class TestFactEnumsContract:
    """Contract tests for Fact-related enums."""

    def test_fact_type_values(self):
        """FactType has expected values."""
        assert FactType.STATE == "state"
        assert FactType.RELATIONSHIP == "relationship"
        assert FactType.ATTRIBUTE == "attribute"
        assert FactType.OCCURRENCE == "occurrence"
        assert len(FactType) == 4

    def test_simulation_scope_values(self):
        """SimulationScope has expected values."""
        assert SimulationScope.LOCAL == "local"
        assert SimulationScope.REGIONAL == "regional"
        assert SimulationScope.GLOBAL == "global"
        # Unified with base.SimulationScope (adds COSMIC, T-020)
        assert SimulationScope.COSMIC == "cosmic"
        assert len(SimulationScope) == 4

    def test_fact_status_values(self):
        """FactStatus has expected values."""
        assert FactStatus.ACTIVE == "active"
        assert FactStatus.SUPERSEDED == "superseded"
        assert FactStatus.TOMBSTONED == "tombstoned"
        assert len(FactStatus) == 3

    def test_axiom_authority_values(self):
        """AxiomAuthority has expected values."""
        assert AxiomAuthority.PHYSICS == "physics"
        assert AxiomAuthority.SOCIETY == "society"
        assert AxiomAuthority.METAPHYSICS == "metaphysics"
        assert AxiomAuthority.GENRE == "genre"
        assert len(AxiomAuthority) == 4