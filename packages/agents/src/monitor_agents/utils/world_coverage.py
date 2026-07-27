"""Formal world-coverage computation (F2-1).

Pure, deterministic mapping from a :class:`CoverageSnapshot` (everything the
loader gathered for a universe) to a structured :class:`WorldCoverage` report
with the 8 dimensions from FORGE_EXPANSION.md §2. Kept side-effect-free so it
is unit-testable without databases; ``WorldArchitect.compute_coverage`` owns
the loading.

Semantics (spec §2):
- Identity + at least one axiom is the floor (``floor_met``).
- Mechanics / random tables only count toward the rollup when the thresholds
  mark them applicable (mechanical play / procedural generation).
- Provenance is enforced only for universes with ingested source material.
"""

from __future__ import annotations

from datetime import UTC, datetime

from monitor_data.schemas.base import CanonLevel, DetailLevel, EntityType
from monitor_data.schemas.coverage import (
    AxiomCoverage,
    CoverageGap,
    CoverageSnapshot,
    CoverageStatus,
    CoverageThresholds,
    DimensionCoverage,
    EntityTaxonomyCoverage,
    FactTaxonomyCoverage,
    IdentityCoverage,
    MechanicsCoverage,
    ProvenanceCoverage,
    RandomTableCoverage,
    RelationshipCoverage,
    WorldCoverage,
)
from monitor_data.schemas.entities import EntityResponse
from monitor_data.schemas.facts import AxiomResponse, FactResponse
from monitor_data.schemas.game_systems import GameRuleType

# Relationship types that establish membership of a faction/organization.
_MEMBERSHIP_INCOMING = {"MEMBER_OF", "SUBGROUP_OF"}
# Relationship types that affiliate a character with something.
_AFFILIATION_TYPES = {
    "MEMBER_OF",
    "SUBGROUP_OF",
    "AFFILIATED_WITH",
    "WORKS_FOR",
    "LEADS",
}
_FACTION_TYPES = {EntityType.FACTION, EntityType.ORGANIZATION}


def _gap(code: str, message: str) -> CoverageGap:
    return CoverageGap(code=code, message=message)


def _identity(snapshot: CoverageSnapshot) -> IdentityCoverage:
    u = snapshot.universe
    has_name = bool(u and u.name and u.name.strip())
    has_genre = bool(u and u.genre)
    has_tone = bool(u and u.tone)
    has_frame = bool(snapshot.narrative_frame_terms)
    has_system = bool(u and (u.default_game_system_id or u.default_system_name))

    gaps: list[CoverageGap] = []
    if not has_name:
        gaps.append(_gap("no_world_name", "The world has no name."))
    if not has_genre:
        gaps.append(_gap("no_genre", "No genre is defined for this universe."))
    if not has_tone:
        gaps.append(_gap("no_tone", "No tone is defined for this universe."))
    if not has_frame:
        gaps.append(
            _gap(
                "no_narrative_frame",
                "No narrative frame has emerged yet (playstyle perspective).",
            )
        )
    if not has_system:
        gaps.append(_gap("no_default_system", "No default game system is bound."))

    if not has_name:
        status = CoverageStatus.MISSING
    elif gaps:
        status = CoverageStatus.THIN
    else:
        status = CoverageStatus.OK

    return IdentityCoverage(
        status=status,
        gaps=gaps,
        has_name=has_name,
        has_genre=has_genre,
        has_tone=has_tone,
        has_narrative_frame=has_frame,
        has_default_system=has_system,
        name=u.name if u else None,
        genre=u.genre if u else None,
        tone=u.tone if u else None,
        default_system_name=(u.default_system_name if u else None),
    )


def _entity_taxonomy(snapshot: CoverageSnapshot, thresholds: CoverageThresholds) -> EntityTaxonomyCoverage:
    by_type: dict[str, int] = {}
    histogram: dict[str, dict[str, int]] = {}
    stub_count = 0
    for e in snapshot.entities:
        etype = e.entity_type.value
        level = (e.detail_level or DetailLevel.STUB).value
        by_type[etype] = by_type.get(etype, 0) + 1
        histogram.setdefault(etype, {})[level] = histogram.setdefault(etype, {}).get(level, 0) + 1
        if level == DetailLevel.STUB.value:
            stub_count += 1

    total = len(snapshot.entities)
    gaps: list[CoverageGap] = []
    if total == 0:
        gaps.append(_gap("no_entities", "No entities are defined yet."))
    elif total < thresholds.min_entities:
        gaps.append(
            _gap(
                "few_entities",
                f"Only {total} entities (baseline: {thresholds.min_entities}).",
            )
        )
    if total > 0 and stub_count == total:
        gaps.append(_gap("stub_only_entities", "Every entity is a stub (name + type only)."))

    if total == 0:
        status = CoverageStatus.MISSING
    elif total < thresholds.min_entities or stub_count == total:
        status = CoverageStatus.THIN
    else:
        status = CoverageStatus.OK

    return EntityTaxonomyCoverage(
        status=status,
        gaps=gaps,
        total=total,
        by_type=by_type,
        detail_histogram=histogram,
        stub_count=stub_count,
    )


def _fact_taxonomy(snapshot: CoverageSnapshot, thresholds: CoverageThresholds) -> FactTaxonomyCoverage:
    by_type: dict[str, int] = {}
    with_refs = 0
    with_prov = 0
    conflict = 0
    historical = 0
    for f in snapshot.facts:
        ftype = f.fact_type.value
        by_type[ftype] = by_type.get(ftype, 0) + 1
        if f.entity_ids:
            with_refs += 1
        if f.source_ids or f.snippet_ids:
            with_prov += 1
        if f.magnitude >= thresholds.conflict_magnitude:
            conflict += 1
        if f.time_ref is not None:
            historical += 1

    total = len(snapshot.facts)
    gaps: list[CoverageGap] = []
    if total == 0:
        gaps.append(_gap("no_facts", "No active lore facts recorded."))
    elif total < thresholds.thin_fact_count:
        gaps.append(
            _gap(
                "few_facts",
                f"Only {total} active facts (baseline: {thresholds.thin_fact_count}).",
            )
        )
    if total > 0 and with_refs == 0:
        gaps.append(_gap("no_entity_refs", "No facts reference any entity."))
    if total > 0 and conflict == 0:
        gaps.append(
            _gap(
                "no_current_conflict",
                "No high-impact active fact signals a current conflict.",
            )
        )

    if total < thresholds.min_facts:
        status = CoverageStatus.MISSING
    elif total < thresholds.thin_fact_count:
        status = CoverageStatus.THIN
    else:
        status = CoverageStatus.OK

    return FactTaxonomyCoverage(
        status=status,
        gaps=gaps,
        total_active=total,
        by_type=by_type,
        with_entity_refs=with_refs,
        with_provenance=with_prov,
        current_conflict=conflict,
        historical_founding=historical,
    )


def _axioms(snapshot: CoverageSnapshot, thresholds: CoverageThresholds) -> AxiomCoverage:
    total = len(snapshot.axioms)
    domains = sorted({a.domain for a in snapshot.axioms if a.domain})

    gaps: list[CoverageGap] = []
    if total == 0:
        gaps.append(_gap("no_axioms", "No foundational axioms — the world has no rules."))

    if total == 0:
        status = CoverageStatus.MISSING
    elif total < thresholds.min_axioms:
        status = CoverageStatus.THIN
    else:
        status = CoverageStatus.OK

    return AxiomCoverage(status=status, gaps=gaps, total=total, domains=domains)


def _relationships(snapshot: CoverageSnapshot, thresholds: CoverageThresholds) -> RelationshipCoverage:
    total_edges = len(snapshot.edges)
    by_category: dict[str, int] = {}
    connected: set[str] = set()
    incoming_membership: dict[str, int] = {}
    affiliated: set[str] = set()
    for edge in snapshot.edges:
        cat = edge.category or "generic"
        by_category[cat] = by_category.get(cat, 0) + 1
        connected.add(edge.from_entity_id)
        connected.add(edge.to_entity_id)
        if edge.rel_type in _MEMBERSHIP_INCOMING:
            incoming_membership[edge.to_entity_id] = incoming_membership.get(edge.to_entity_id, 0) + 1
        if edge.rel_type in _AFFILIATION_TYPES:
            affiliated.add(edge.from_entity_id)
            affiliated.add(edge.to_entity_id)

    isolated: list[str] = []
    factions_without_members: list[str] = []
    npcs_without_affiliations: list[str] = []
    for e in snapshot.entities:
        eid = str(e.id)
        if eid not in connected:
            isolated.append(e.name)
        if e.entity_type in _FACTION_TYPES and incoming_membership.get(eid, 0) == 0:
            factions_without_members.append(e.name)
        if e.entity_type == EntityType.CHARACTER and eid not in affiliated:
            npcs_without_affiliations.append(e.name)

    total_entities = len(snapshot.entities)
    isolated_ratio = len(isolated) / total_entities if total_entities else 0.0

    gaps: list[CoverageGap] = []
    if total_edges == 0:
        gaps.append(_gap("no_relationships", "No relationships connect the entities."))
    if isolated:
        gaps.append(
            _gap(
                "isolated_entities",
                f"{len(isolated)} entities have no relationships (ratio {isolated_ratio:.0%}).",
            )
        )
    if factions_without_members:
        gaps.append(
            _gap(
                "factions_without_members",
                f"Factions without members: {', '.join(factions_without_members[:5])}.",
            )
        )
    if npcs_without_affiliations:
        gaps.append(
            _gap(
                "npcs_without_affiliations",
                f"{len(npcs_without_affiliations)} NPCs have no affiliations.",
            )
        )

    if total_edges == 0:
        status = CoverageStatus.MISSING
    elif isolated_ratio > thresholds.max_isolated_ratio or factions_without_members or npcs_without_affiliations:
        status = CoverageStatus.THIN
    else:
        status = CoverageStatus.OK

    return RelationshipCoverage(
        status=status,
        gaps=gaps,
        total_edges=total_edges,
        by_category=by_category,
        isolated_entities=isolated,
        factions_without_members=factions_without_members,
        npcs_without_affiliations=npcs_without_affiliations,
    )


def _mechanics(snapshot: CoverageSnapshot, thresholds: CoverageThresholds) -> MechanicsCoverage:
    applicable = thresholds.require_mechanics
    system = snapshot.game_system
    u = snapshot.universe

    if system is None:
        gaps = []
        if u and u.default_system_name and not u.default_game_system_id:
            gaps.append(
                _gap(
                    "system_not_linked",
                    f"System '{u.default_system_name}' is named but not linked.",
                )
            )
        else:
            gaps.append(_gap("no_linked_system", "No game system is linked to this universe."))
        return MechanicsCoverage(
            status=CoverageStatus.MISSING,
            gaps=gaps,
            applicable=applicable,
            has_linked_system=False,
            system_name=(u.default_system_name if u else None),
        )

    rule_types = {r.rule_type for r in system.rules}
    has_combat = GameRuleType.COMBAT in rule_types
    has_social = GameRuleType.SOCIAL in rule_types
    has_core = bool(system.core_mechanic and system.core_mechanic.formula)
    has_advancement = system.advancement_model is not None
    has_creation = system.character_creation is not None

    gaps = []
    if not has_core:
        gaps.append(_gap("no_core_mechanic", "The system has no core mechanic formula."))
    if not system.attributes:
        gaps.append(_gap("no_attributes", "No attributes are defined."))
    if not system.skills:
        gaps.append(_gap("no_skills", "No skills are defined."))
    if not system.resolution_mechanics:
        gaps.append(_gap("no_resolution_mechanics", "No resolution mechanics defined."))
    if not has_combat:
        gaps.append(_gap("no_combat_rules", "No combat rules defined."))
    if not has_social:
        gaps.append(_gap("no_social_rules", "No social rules defined."))
    if not system.conditions:
        gaps.append(_gap("no_conditions", "No conditions defined."))
    if not has_advancement:
        gaps.append(_gap("no_advancement", "No advancement model defined."))
    if not has_creation:
        gaps.append(_gap("no_character_creation", "No character creation procedure."))

    core_missing = (
        not has_core
        or not system.attributes
        or not system.resolution_mechanics
        or (not has_combat and not has_social)
        or not has_creation
    )
    status = CoverageStatus.THIN if core_missing else CoverageStatus.OK

    return MechanicsCoverage(
        status=status,
        gaps=gaps,
        applicable=applicable,
        has_linked_system=True,
        system_name=system.name,
        has_core_mechanic=has_core,
        success_method=system.core_mechanic.success_type.value,
        attribute_count=len(system.attributes),
        skill_count=len(system.skills),
        resolution_mechanic_count=len(system.resolution_mechanics),
        has_combat_rules=has_combat,
        has_social_rules=has_social,
        condition_count=len(system.conditions),
        has_advancement=has_advancement,
        has_character_creation=has_creation,
    )


def _random_tables(snapshot: CoverageSnapshot, thresholds: CoverageThresholds) -> RandomTableCoverage:
    applicable = thresholds.require_random_tables
    by_type: dict[str, int] = {}
    linked_universe = 0
    linked_system = 0
    universe_id = snapshot.universe.id if snapshot.universe else None
    for t in snapshot.random_tables:
        ttype = t.table_type.value
        by_type[ttype] = by_type.get(ttype, 0) + 1
        if universe_id and t.universe_id == universe_id:
            linked_universe += 1
        if t.game_system_id is not None:
            linked_system += 1

    total = len(snapshot.random_tables)
    gaps: list[CoverageGap] = []
    if total == 0:
        gaps.append(_gap("no_random_tables", "No random tables available."))
    elif linked_universe == 0 and linked_system == 0:
        gaps.append(
            _gap(
                "unlinked_tables",
                "Tables exist but none are linked to this universe or its system.",
            )
        )

    if total == 0:
        status = CoverageStatus.MISSING
    elif total < thresholds.min_random_tables:
        status = CoverageStatus.THIN
    else:
        status = CoverageStatus.OK

    return RandomTableCoverage(
        status=status,
        gaps=gaps,
        applicable=applicable,
        total=total,
        by_type=by_type,
        linked_to_universe=linked_universe,
        linked_to_system=linked_system,
    )


def _provenance(snapshot: CoverageSnapshot, thresholds: CoverageThresholds) -> ProvenanceCoverage:
    entities = snapshot.entities
    facts = snapshot.facts
    axioms = snapshot.axioms
    total = len(entities) + len(facts) + len(axioms)

    with_refs = sum(1 for f in facts if f.source_ids) + sum(1 for a in axioms if a.source_ids or a.source_ref)
    with_evidence = sum(1 for f in facts if f.snippet_ids)

    primitives: list[EntityResponse | FactResponse | AxiomResponse] = [
        *entities,
        *facts,
        *axioms,
    ]
    confidences = [p.confidence for p in primitives]
    avg_confidence = round(sum(confidences) / len(confidences), 4) if confidences else None

    by_canon: dict[str, int] = {}
    pending = 0
    for p in primitives:
        level = p.canon_level.value
        by_canon[level] = by_canon.get(level, 0) + 1
        if p.canon_level == CanonLevel.PROPOSED:
            pending += 1

    ingested = bool(snapshot.universe and snapshot.universe.source_ids)
    sourced_primitives = len(facts) + len(axioms)
    ratio = with_refs / sourced_primitives if sourced_primitives else 1.0

    gaps: list[CoverageGap] = []
    if ingested and with_refs == 0 and sourced_primitives > 0:
        gaps.append(
            _gap(
                "no_source_refs",
                "Universe has ingested sources but no fact/axiom carries a source ref.",
            )
        )
    elif ingested and ratio < thresholds.min_provenance_ratio:
        gaps.append(
            _gap(
                "low_provenance",
                f"Only {ratio:.0%} of facts/axioms have source refs (baseline: {thresholds.min_provenance_ratio:.0%}).",
            )
        )
    if pending > 0:
        gaps.append(_gap("pending_review", f"{pending} primitives are still proposed (unreviewed)."))

    if total == 0:
        status = CoverageStatus.MISSING
    elif not ingested:
        # GM-declared material does not require provenance (spec §2).
        status = CoverageStatus.OK
    elif sourced_primitives > 0 and ratio == 0:
        status = CoverageStatus.MISSING
    elif ratio < thresholds.min_provenance_ratio:
        status = CoverageStatus.THIN
    else:
        status = CoverageStatus.OK

    return ProvenanceCoverage(
        status=status,
        gaps=gaps,
        primitives_total=total,
        with_source_refs=with_refs,
        with_evidence=with_evidence,
        avg_confidence=avg_confidence,
        by_canon_level=by_canon,
        pending_review=pending,
        ingested_material=ingested,
    )


def build_world_coverage(
    snapshot: CoverageSnapshot,
    thresholds: CoverageThresholds | None = None,
) -> WorldCoverage:
    """Compute the structured :class:`WorldCoverage` report for a snapshot."""
    thresholds = thresholds or CoverageThresholds()

    identity = _identity(snapshot)
    entity_taxonomy = _entity_taxonomy(snapshot, thresholds)
    fact_taxonomy = _fact_taxonomy(snapshot, thresholds)
    axioms = _axioms(snapshot, thresholds)
    relationships = _relationships(snapshot, thresholds)
    mechanics = _mechanics(snapshot, thresholds)
    random_tables = _random_tables(snapshot, thresholds)
    provenance = _provenance(snapshot, thresholds)

    universe_id = snapshot.universe.id if snapshot.universe else None

    # Spec floor: identity + at least one axiom.
    floor_met = identity.has_name and axioms.total >= 1

    dimensions: list[DimensionCoverage] = [
        identity,
        entity_taxonomy,
        fact_taxonomy,
        axioms,
        relationships,
        provenance,
    ]
    if mechanics.applicable:
        dimensions.append(mechanics)
    if random_tables.applicable:
        dimensions.append(random_tables)

    if not floor_met:
        overall = CoverageStatus.MISSING
    elif any(d.status != CoverageStatus.OK for d in dimensions):
        overall = CoverageStatus.THIN
    else:
        overall = CoverageStatus.OK

    return WorldCoverage(
        universe_id=universe_id,
        computed_at=datetime.now(UTC),
        thresholds=thresholds,
        identity=identity,
        entity_taxonomy=entity_taxonomy,
        fact_taxonomy=fact_taxonomy,
        axioms=axioms,
        relationships=relationships,
        mechanics=mechanics,
        random_tables=random_tables,
        provenance=provenance,
        floor_met=floor_met,
        overall_status=overall,
    )
