"""
Pydantic schemas for the formal World Coverage model (F2-1).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and other
              data-layer schemas (universe, entities, facts, relationships,
              game_systems, random_tables)
CALLED BY: monitor_agents.utils.world_coverage (computation),
           WorldArchitect.compute_coverage, monitor_ui architect router

Coverage is the set of world-building and play-enabling primitives currently
represented, connected, sufficiently detailed, and trusted in a universe,
compared against a context-dependent baseline (FORGE_EXPANSION.md §2).

A complete world does not require every dimension. Identity + at least one
axiom is the floor. Game-system mechanics and random tables are required only
for mechanical play / procedural generation (see ``CoverageThresholds``).
Provenance is required for ingested material but not for direct GM
declarations. Thresholds are configurable per world intent.

Dimensions (8, per spec §2):
  A. identity           — name, genre, tone, narrative frame, default system
  B. entity_taxonomy    — counts + detail-level histogram per entity type
  C. fact_taxonomy      — active facts by FactType, entity refs, provenance,
                          current conflict, historical/founding
  D. axioms             — count + domains covered
  E. relationships      — edges, categories, isolated entities, factions
                          without members, NPCs without affiliations
  F. mechanics          — linked system, core mechanic, success method,
                          attributes/skills, resolution, combat/social,
                          conditions, advancement, character creation
  G. random_tables      — table count, types covered, universe/system links
  H. provenance         — source refs, evidence, confidence, canon level,
                          review status
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.entities import EntityResponse
from monitor_data.schemas.facts import AxiomResponse, FactResponse
from monitor_data.schemas.game_systems import GameSystemResponse
from monitor_data.schemas.random_tables import RandomTableResponse
from monitor_data.schemas.universe import UniverseResponse

# =============================================================================
# ENUMS & SHARED PRIMITIVES
# =============================================================================


class CoverageStatus(StrEnum):
    """Health of a single coverage dimension."""

    MISSING = "missing"  # Nothing (or nothing usable) present
    THIN = "thin"  # Present but below the configured baseline
    OK = "ok"  # Meets the baseline


class CoverageDimension(StrEnum):
    """The 8 formal coverage dimensions (FORGE_EXPANSION.md §2)."""

    IDENTITY = "identity"
    ENTITY_TAXONOMY = "entity_taxonomy"
    FACT_TAXONOMY = "fact_taxonomy"
    AXIOMS = "axioms"
    RELATIONSHIPS = "relationships"
    MECHANICS = "mechanics"
    RANDOM_TABLES = "random_tables"
    PROVENANCE = "provenance"


class CoverageGap(BaseModel):
    """A single identified gap inside a dimension."""

    code: str = Field(description="Stable machine-readable gap identifier")
    message: str = Field(description="Human-readable description of the gap")


class CoverageThresholds(BaseModel):
    """Configurable baselines driving missing/thin/ok status per dimension.

    Defaults implement the spec §2 semantics: identity + >=1 axiom is the
    floor; mechanics and random tables are only *applicable* (counted toward
    the overall rollup) when the world is intended for mechanical play or
    procedural generation.
    """

    min_axioms: int = Field(default=1, ge=0, description="Axiom floor for a viable world")
    min_entities: int = Field(default=5, ge=0, description="Entity count below this is 'thin'")
    min_facts: int = Field(default=1, ge=0, description="Active-fact floor ('missing' below)")
    thin_fact_count: int = Field(default=5, ge=0, description="Active-fact count below this is 'thin'")
    conflict_magnitude: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Active facts with magnitude >= this count as current-conflict signals",
    )
    max_isolated_ratio: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Isolated-entity ratio above this marks connectivity 'thin'",
    )
    min_provenance_ratio: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=("For universes with ingested sources, the fraction of facts/axioms expected to carry source refs"),
    )
    min_random_tables: int = Field(default=3, ge=0, description="Table count below this is 'thin'")
    require_mechanics: bool = Field(
        default=False,
        description="True when the world is intended for mechanical play",
    )
    require_random_tables: bool = Field(
        default=False,
        description="True when the world relies on procedural generation",
    )


class CoverageEdge(BaseModel):
    """A relationship edge inside the universe, as needed for connectivity."""

    from_entity_id: str
    to_entity_id: str
    rel_type: str
    category: str | None = None


class CoverageSnapshot(BaseModel):
    """Typed input for coverage computation — everything the loader gathered.

    ``narrative_frame_terms`` carries the persisted world profile's narrative
    frame (MongoDB); it is not derivable from Neo4j primitives alone.
    """

    universe: UniverseResponse | None = None
    entities: list[EntityResponse] = Field(default_factory=list)
    axioms: list[AxiomResponse] = Field(default_factory=list)
    facts: list[FactResponse] = Field(default_factory=list)
    edges: list[CoverageEdge] = Field(default_factory=list)
    game_system: GameSystemResponse | None = None
    random_tables: list[RandomTableResponse] = Field(default_factory=list)
    narrative_frame_terms: list[str] = Field(default_factory=list)


# =============================================================================
# DIMENSION MODELS (A-H)
# =============================================================================


class DimensionCoverage(BaseModel):
    """Shared shape of every coverage dimension: status + identified gaps."""

    status: CoverageStatus
    gaps: list[CoverageGap] = Field(default_factory=list)


class IdentityCoverage(DimensionCoverage):
    """A. Identity — name, genre, tone, narrative frame, default system."""

    has_name: bool = False
    has_genre: bool = False
    has_tone: bool = False
    has_narrative_frame: bool = False
    has_default_system: bool = False
    name: str | None = None
    genre: str | None = None
    tone: str | None = None
    default_system_name: str | None = None


class EntityTaxonomyCoverage(DimensionCoverage):
    """B. Entity taxonomy — counts + detail-level histogram per entity type."""

    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    detail_histogram: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="entity_type -> detail_level -> count",
    )
    stub_count: int = 0


class FactTaxonomyCoverage(DimensionCoverage):
    """C. Fact taxonomy — active facts by FactType, refs, provenance, signals."""

    total_active: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    with_entity_refs: int = 0
    with_provenance: int = 0
    current_conflict: int = 0
    historical_founding: int = 0


class AxiomCoverage(DimensionCoverage):
    """D. Foundational axioms — count + domains covered."""

    total: int = 0
    domains: list[str] = Field(default_factory=list)


class RelationshipCoverage(DimensionCoverage):
    """E. Relationships & connectivity."""

    total_edges: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    isolated_entities: list[str] = Field(default_factory=list, description="Names of entities with no edges")
    factions_without_members: list[str] = Field(default_factory=list)
    npcs_without_affiliations: list[str] = Field(default_factory=list)


class MechanicsCoverage(DimensionCoverage):
    """F. Game system & mechanics (applicable only for mechanical play)."""

    applicable: bool = True
    has_linked_system: bool = False
    system_name: str | None = None
    has_core_mechanic: bool = False
    success_method: str | None = None
    attribute_count: int = 0
    skill_count: int = 0
    resolution_mechanic_count: int = 0
    has_combat_rules: bool = False
    has_social_rules: bool = False
    condition_count: int = 0
    has_advancement: bool = False
    has_character_creation: bool = False


class RandomTableCoverage(DimensionCoverage):
    """G. Random generation assets (applicable only for procedural play)."""

    applicable: bool = True
    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    linked_to_universe: int = 0
    linked_to_system: int = 0


class ProvenanceCoverage(DimensionCoverage):
    """H. Provenance & confidence across facts/axioms/entities."""

    primitives_total: int = 0
    with_source_refs: int = 0
    with_evidence: int = 0
    avg_confidence: float | None = None
    by_canon_level: dict[str, int] = Field(default_factory=dict)
    pending_review: int = Field(default=0, description="Primitives still at canon_level 'proposed'")
    ingested_material: bool = Field(default=False, description="Universe has ingested Source nodes attached")


# =============================================================================
# TOP-LEVEL MODEL
# =============================================================================


class WorldCoverage(BaseModel):
    """Structured coverage report for one universe (F2-1 wave 1).

    ``floor_met`` implements the spec floor: identity present + at least one
    axiom. ``overall_status`` is the rollup over applicable dimensions.
    """

    universe_id: UUID | None = None
    computed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    thresholds: CoverageThresholds = Field(default_factory=CoverageThresholds)

    identity: IdentityCoverage
    entity_taxonomy: EntityTaxonomyCoverage
    fact_taxonomy: FactTaxonomyCoverage
    axioms: AxiomCoverage
    relationships: RelationshipCoverage
    mechanics: MechanicsCoverage
    random_tables: RandomTableCoverage
    provenance: ProvenanceCoverage

    floor_met: bool = False
    overall_status: CoverageStatus = CoverageStatus.MISSING
