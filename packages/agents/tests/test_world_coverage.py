"""Tests for the formal world-coverage computation (F2-1 wave 1)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from monitor_data.schemas.base import Authority, CanonLevel, DetailLevel, EntityType
from monitor_data.schemas.coverage import (
    CoverageEdge,
    CoverageSnapshot,
    CoverageStatus,
    CoverageThresholds,
)
from monitor_data.schemas.entities import EntityResponse
from monitor_data.schemas.facts import AxiomResponse, FactResponse, FactType
from monitor_data.schemas.universe import UniverseResponse

from monitor_agents.utils.world_coverage import build_world_coverage
from monitor_agents.world_architect.agent import WorldArchitect

_UNIVERSE_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _universe(**overrides) -> UniverseResponse:
    base = {
        "id": _UNIVERSE_ID,
        "name": "Ashmar",
        "description": "A test world",
        "genre": "dark fantasy",
        "tone": "grim",
        "default_system_name": "Story System",
        "created_at": _NOW,
    }
    return UniverseResponse(**(base | overrides))


def _entity(
    name: str,
    entity_type: EntityType,
    detail: DetailLevel = DetailLevel.DETAILED,
    entity_id=None,
) -> EntityResponse:
    return EntityResponse(
        id=entity_id or uuid4(),
        created_at=_NOW,
        universe_id=_UNIVERSE_ID,
        name=name,
        entity_type=entity_type,
        is_archetype=False,
        description=f"{name} description",
        properties={},
        canon_level=CanonLevel.CANON,
        confidence=0.9,
        authority=Authority.GM,
        detail_level=detail,
    )


def _axiom(statement: str = "Magic is bound to blood.", domain: str = "metaphysics"):
    return AxiomResponse(
        id=uuid4(),
        universe_id=_UNIVERSE_ID,
        statement=statement,
        domain=domain,
        magnitude=8,
        scope="global",
        canon_level=CanonLevel.CANON,
        confidence=0.9,
        authority="metaphysics",
        source_ref=None,
        properties=None,
        created_at=_NOW,
    )


def _fact(
    statement: str,
    fact_type: FactType = FactType.STATE,
    magnitude: int = 1,
    entity_ids=None,
    source_ids=None,
    time_ref=None,
) -> FactResponse:
    return FactResponse(
        id=uuid4(),
        universe_id=_UNIVERSE_ID,
        statement=statement,
        fact_type=fact_type,
        magnitude=magnitude,
        canon_level=CanonLevel.CANON,
        confidence=0.9,
        authority=Authority.GM,
        created_at=_NOW,
        replaces=None,
        properties=None,
        entity_ids=entity_ids or [],
        source_ids=source_ids or [],
        time_ref=time_ref,
    )


# ---------------------------------------------------------------------------
# Empty universe → floor gaps
# ---------------------------------------------------------------------------


class TestEmptyUniverse:
    def test_empty_universe_reports_floor_gaps(self) -> None:
        snapshot = CoverageSnapshot(universe=_universe())
        coverage = build_world_coverage(snapshot)

        assert coverage.universe_id == _UNIVERSE_ID
        assert coverage.floor_met is False  # no axiom
        assert coverage.overall_status == CoverageStatus.MISSING
        assert coverage.entity_taxonomy.status == CoverageStatus.MISSING
        assert coverage.fact_taxonomy.status == CoverageStatus.MISSING
        assert coverage.axioms.status == CoverageStatus.MISSING
        assert coverage.relationships.status == CoverageStatus.MISSING
        assert coverage.mechanics.status == CoverageStatus.MISSING
        assert coverage.random_tables.status == CoverageStatus.MISSING
        assert {g.code for g in coverage.axioms.gaps} == {"no_axioms"}
        assert {g.code for g in coverage.entity_taxonomy.gaps} == {"no_entities"}

    def test_missing_universe_is_all_missing(self) -> None:
        coverage = build_world_coverage(CoverageSnapshot())
        assert coverage.universe_id is None
        assert coverage.identity.status == CoverageStatus.MISSING
        assert coverage.floor_met is False


# ---------------------------------------------------------------------------
# Populated universe → dimension statuses
# ---------------------------------------------------------------------------


def _populated_snapshot() -> CoverageSnapshot:
    npc = _entity("Sister Wrenna", EntityType.CHARACTER)
    faction = _entity("Ash Wardens", EntityType.FACTION)
    city = _entity("Hollowmere", EntityType.LOCATION)
    artifact = _entity("The Gloom Bell", EntityType.OBJECT)
    creed = _entity("The Quiet Creed", EntityType.CONCEPT)

    edges = [
        CoverageEdge(
            from_entity_id=str(npc.id),
            to_entity_id=str(faction.id),
            rel_type="MEMBER_OF",
            category="membership",
        ),
        CoverageEdge(
            from_entity_id=str(npc.id),
            to_entity_id=str(city.id),
            rel_type="LOCATED_IN",
            category="spatial",
        ),
        CoverageEdge(
            from_entity_id=str(faction.id),
            to_entity_id=str(artifact.id),
            rel_type="OWNS",
            category="ownership",
        ),
        CoverageEdge(
            from_entity_id=str(creed.id),
            to_entity_id=str(faction.id),
            rel_type="REVERES",
            category="social",
        ),
    ]
    facts = [
        _fact(
            f"Fact {i}",
            magnitude=6 if i == 0 else 1,
            entity_ids=[npc.id],
            source_ids=[uuid4()] if i == 0 else None,
        )
        for i in range(6)
    ]
    return CoverageSnapshot(
        universe=_universe(),
        entities=[npc, faction, city, artifact, creed],
        axioms=[_axiom()],
        facts=facts,
        edges=edges,
        narrative_frame_terms=["political"],
    )


class TestPopulatedUniverse:
    def test_populated_universe_dimensions(self) -> None:
        coverage = build_world_coverage(_populated_snapshot())

        assert coverage.floor_met is True
        assert coverage.identity.status == CoverageStatus.OK
        assert coverage.entity_taxonomy.status == CoverageStatus.OK
        assert coverage.entity_taxonomy.by_type == {
            "character": 1,
            "faction": 1,
            "location": 1,
            "object": 1,
            "concept": 1,
        }
        assert coverage.fact_taxonomy.status == CoverageStatus.OK
        assert coverage.fact_taxonomy.with_entity_refs == 6
        assert coverage.fact_taxonomy.with_provenance == 1
        assert coverage.fact_taxonomy.current_conflict == 1
        assert coverage.axioms.status == CoverageStatus.OK
        assert coverage.axioms.domains == ["metaphysics"]
        assert coverage.relationships.status == CoverageStatus.OK
        assert coverage.relationships.total_edges == 4
        assert coverage.relationships.by_category == {
            "membership": 1,
            "spatial": 1,
            "ownership": 1,
            "social": 1,
        }
        assert coverage.relationships.isolated_entities == []
        assert coverage.relationships.factions_without_members == []
        assert coverage.relationships.npcs_without_affiliations == []
        assert coverage.overall_status == CoverageStatus.OK

    def test_mechanics_and_tables_not_applicable_by_default(self) -> None:
        """Mechanics/tables are excluded from the rollup unless required."""
        coverage = build_world_coverage(_populated_snapshot())
        assert coverage.mechanics.applicable is False
        assert coverage.random_tables.applicable is False
        # Even though both are MISSING, the overall rollup ignores them.
        assert coverage.overall_status == CoverageStatus.OK

    def test_required_mechanics_drags_overall_down(self) -> None:
        thresholds = CoverageThresholds(require_mechanics=True)
        coverage = build_world_coverage(_populated_snapshot(), thresholds)
        assert coverage.mechanics.applicable is True
        assert coverage.mechanics.status == CoverageStatus.MISSING
        assert coverage.overall_status == CoverageStatus.THIN


# ---------------------------------------------------------------------------
# Isolated-entity / connectivity detection
# ---------------------------------------------------------------------------


class TestConnectivity:
    def test_isolated_entities_detected(self) -> None:
        a = _entity("Connected A", EntityType.CHARACTER)
        b = _entity("Connected B", EntityType.LOCATION)
        loner = _entity("Loner", EntityType.CHARACTER)
        snapshot = CoverageSnapshot(
            universe=_universe(),
            entities=[a, b, loner],
            axioms=[_axiom()],
            edges=[
                CoverageEdge(
                    from_entity_id=str(a.id),
                    to_entity_id=str(b.id),
                    rel_type="LOCATED_IN",
                    category="spatial",
                )
            ],
        )
        coverage = build_world_coverage(snapshot)
        rel = coverage.relationships
        assert rel.total_edges == 1
        assert rel.isolated_entities == ["Loner"]
        assert "Loner" in rel.npcs_without_affiliations
        assert rel.status == CoverageStatus.THIN
        assert any(g.code == "isolated_entities" for g in rel.gaps)

    def test_faction_without_members(self) -> None:
        faction = _entity("Empty Guild", EntityType.FACTION)
        npc = _entity("Drifter", EntityType.CHARACTER)
        snapshot = CoverageSnapshot(
            universe=_universe(),
            entities=[faction, npc],
            axioms=[_axiom()],
            edges=[
                CoverageEdge(
                    from_entity_id=str(npc.id),
                    to_entity_id=str(faction.id),
                    rel_type="KNOWS",
                    category="social",
                )
            ],
        )
        rel = build_world_coverage(snapshot).relationships
        assert rel.factions_without_members == ["Empty Guild"]
        assert rel.status == CoverageStatus.THIN

    def test_no_edges_at_all_is_missing(self) -> None:
        snapshot = CoverageSnapshot(
            universe=_universe(),
            entities=[_entity("Alone", EntityType.CHARACTER)],
            axioms=[_axiom()],
        )
        rel = build_world_coverage(snapshot).relationships
        assert rel.status == CoverageStatus.MISSING
        assert {g.code for g in rel.gaps} >= {"no_relationships"}


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------


class TestThresholds:
    def test_entity_threshold_configurable(self) -> None:
        snapshot = CoverageSnapshot(
            universe=_universe(),
            entities=[_entity(f"E{i}", EntityType.CONCEPT) for i in range(3)],
            axioms=[_axiom()],
        )
        assert build_world_coverage(snapshot).entity_taxonomy.status == CoverageStatus.THIN
        relaxed = CoverageThresholds(min_entities=3)
        coverage = build_world_coverage(snapshot, relaxed)
        assert coverage.entity_taxonomy.status == CoverageStatus.OK

    def test_stub_only_entities_are_thin(self) -> None:
        snapshot = CoverageSnapshot(
            universe=_universe(),
            entities=[_entity(f"Stub {i}", EntityType.LOCATION, detail=DetailLevel.STUB) for i in range(6)],
            axioms=[_axiom()],
        )
        taxonomy = build_world_coverage(snapshot).entity_taxonomy
        assert taxonomy.stub_count == 6
        assert taxonomy.status == CoverageStatus.THIN
        assert any(g.code == "stub_only_entities" for g in taxonomy.gaps)

    def test_axiom_floor_configurable(self) -> None:
        snapshot = CoverageSnapshot(universe=_universe(), axioms=[_axiom()])
        assert build_world_coverage(snapshot).axioms.status == CoverageStatus.OK
        strict = CoverageThresholds(min_axioms=3)
        assert build_world_coverage(snapshot, strict).axioms.status == CoverageStatus.THIN

    def test_isolated_ratio_threshold(self) -> None:
        # Locations: no faction/affiliation rules apply, so the isolated ratio
        # is the only thing that can make connectivity thin.
        ents = [_entity(f"Place {i}", EntityType.LOCATION) for i in range(4)]
        edges = [
            CoverageEdge(
                from_entity_id=str(ents[0].id),
                to_entity_id=str(ents[1].id),
                rel_type="CONTAINS",
                category="spatial",
            )
        ]
        snapshot = CoverageSnapshot(universe=_universe(), entities=ents, axioms=[_axiom()], edges=edges)
        # 2/4 isolated = 0.5, not above the default 0.5 → ok.
        assert build_world_coverage(snapshot).relationships.status == CoverageStatus.OK
        # A stricter threshold flags the same world as thin.
        stricter = CoverageThresholds(max_isolated_ratio=0.4)
        rel = build_world_coverage(snapshot, stricter).relationships
        assert rel.status == CoverageStatus.THIN
        assert any(g.code == "isolated_entities" for g in rel.gaps)


# ---------------------------------------------------------------------------
# Provenance semantics (ingested vs GM-declared)
# ---------------------------------------------------------------------------


class TestProvenance:
    def test_gm_declared_material_needs_no_provenance(self) -> None:
        snapshot = CoverageSnapshot(
            universe=_universe(),
            entities=[_entity("A", EntityType.CONCEPT)],
            axioms=[_axiom()],
            facts=[_fact("Something is true.")],
        )
        prov = build_world_coverage(snapshot).provenance
        assert prov.ingested_material is False
        assert prov.status == CoverageStatus.OK

    def test_ingested_material_without_refs_is_missing(self) -> None:
        source_id = uuid4()
        snapshot = CoverageSnapshot(
            universe=_universe(source_ids=[source_id]),
            axioms=[_axiom()],
            facts=[_fact("Unsourced fact.")],
        )
        prov = build_world_coverage(snapshot).provenance
        assert prov.ingested_material is True
        assert prov.status == CoverageStatus.MISSING
        assert any(g.code == "no_source_refs" for g in prov.gaps)


# ---------------------------------------------------------------------------
# WorldArchitect.compute_coverage (loader wiring with faked tools)
# ---------------------------------------------------------------------------


class TestComputeCoverage:
    @pytest.mark.asyncio
    async def test_compute_coverage_aggregates_all_dimensions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        npc = _entity("Sister Wrenna", EntityType.CHARACTER)
        universe = _universe()

        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.core.neo4j_get_universe",
            lambda _uid: universe,
        )
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_list_entities",
            lambda _f: type("R", (), {"entities": [npc]})(),
        )
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_list_axioms",
            lambda _f: [_axiom()],
        )
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_list_facts",
            lambda _f: [_fact("The court feasts at midnight.", magnitude=6)],
        )
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_get_universe_state",
            lambda _uid: {
                "entities": [],
                "facts": [],
                "axioms": [],
                "relationships": [
                    {
                        "from_id": str(npc.id),
                        "to_id": str(uuid4()),
                        "type": "KNOWS",
                        "category": "social",
                    }
                ],
            },
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_list_random_tables",
            lambda _f: type("R", (), {"tables": []})(),
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_world_profile",
            lambda _uid: None,
        )

        coverage = await WorldArchitect().compute_coverage(_UNIVERSE_ID)

        assert coverage.universe_id == _UNIVERSE_ID
        assert coverage.floor_met is True
        assert coverage.entity_taxonomy.total == 1
        assert coverage.fact_taxonomy.current_conflict == 1
        assert coverage.axioms.total == 1
        assert coverage.relationships.total_edges == 1
        assert coverage.relationships.by_category == {"social": 1}
        assert coverage.mechanics.has_linked_system is False

    @pytest.mark.asyncio
    async def test_compute_coverage_missing_universe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.core.neo4j_get_universe",
            lambda _uid: None,
        )
        coverage = await WorldArchitect().compute_coverage(_UNIVERSE_ID)
        assert coverage.universe_id is None
        assert coverage.overall_status == CoverageStatus.MISSING
