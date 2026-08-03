"""
Pydantic schemas for KnowledgePack operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and base schemas
CALLED BY: mongodb_tools.py, Analyzer agent (Layer 2)

A KnowledgePack is a pre-digested extraction snapshot produced by the Analyzer
agent after processing an ingested source document.  It can be stored,
reviewed, and applied to any multiverse — including ones created later.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from monitor_data.schemas.agendas import ExtractedAgenda
from monitor_data.schemas.base import (
    CanonLevel,
    KnowledgeScope,
    ProfileEvidenceRef,
    Trimmed100,
    Trimmed200,
    Trimmed500,
    Trimmed1000,
    TrimmedCoerce500,
    TrimmedCoerce1000,
)
from monitor_data.schemas.entity_subtypes import (
    GroupType,
    PlaceType,
    coerce_group_subtype,
    coerce_place_subtype,
)
from monitor_data.schemas.relationships import RelationshipType
from monitor_data.schemas.game_systems import (
    ActionEconomy,
    AdvancementModel,
    AdvantageDefinition,
    AttributeDefinition,
    CharacterCreationProcedure,
    ConditionDefinition,
    CoreMechanic,
    DamageModel,
    GameRule,
    NPCCreationRules,
    NPCStatBlock,
    RecoveryModel,
    ResolutionMechanic,
    ResourceDefinition,
    SceneryRule,
    SkillDefinition,
    TieredAbilitySystem,
    TrackDefinition,
)
from monitor_data.schemas.plot_threads import ExtractedPlotThread

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class KnowledgePackType(StrEnum):
    """The intended use of the extracted content."""

    GAME_SYSTEM = "game_system"  # Defines core mechanics and procedures
    SETTING_SUPPLEMENT = "setting_supplement"  # Adds lore, entities, and flavor
    ADVENTURE_MODULE = "adventure_module"  # Premade scenario/campaign
    RULEBOOK = "rulebook"  # Core rulebook extraction
    LORE = "lore"  # Setting/lore extraction
    WIKI = "wiki"  # Wiki-style reference material
    CUSTOM = "custom"  # User-defined custom pack
    HOMEBREW = "homebrew"  # Homebrew/house rules content
    SESSION_NOTES = "session_notes"  # Session notes/transcript pack
    CHARACTER_COLLECTION = "character_collection"  # Roster of NPCs/PCs
    MISC = "general"

    @classmethod
    def coerce(cls, value: KnowledgePackType | str | None) -> KnowledgePackType | None:
        """Interpret a pack_type that crossed a process boundary (CLI string
        option, API payload) as a KnowledgePackType; None when absent or
        unrecognized. Raw strings must never reach ``.value`` call sites —
        live bug: the CLI's ``--type`` typer.Option is a plain ``str`` with
        zero conversion before reaching the analyzer, which reproduced the
        exact 'str' object has no attribute 'value' crash that cost a full
        day to diagnose before logger.exception() caught its traceback.
        """
        if value is None or isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return None


class KnowledgePackStatus(StrEnum):
    """The current availability of the pack."""

    PENDING = "pending"  # Ingestion in progress
    READY = "ready"  # Fully extracted and ready to review/apply
    REVIEW_PENDING = "review_pending"  # Ready for user review
    APPLIED = "applied"  # Already used in at least one multiverse
    FAILED = "failed"  # Critical error during extraction
    ARCHIVED = "archived"  # Hidden from library but preserved


# =============================================================================
# EXTRACTED ITEM SCHEMAS
# These are lightweight snapshots of what the Analyzer extracted.
# They become ProposedChanges when applied to a multiverse.
# =============================================================================


class ExtractedAxiom(BaseModel):
    """A fundamental world truth extracted from the source."""

    statement: Trimmed500 = Field(max_length=500)
    domain: Trimmed100 = Field(default="general", max_length=100)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source_ref: Trimmed200 | None = Field(None, max_length=200)
    tags: list[str] = Field(default_factory=list)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this axiom — required for canon audit trail",
    )


class ExtractedEntityArchetype(BaseModel):
    """An entity category/template (race, class, faction type) extracted from source."""

    name: Trimmed200 = Field(max_length=200)
    entity_type: str = Field(description="character | faction | location | object | concept | organization")
    sub_type: Trimmed100 | None = Field(
        None,
        max_length=100,
        description=(
            "Short fine-grained classification WITHIN entity_type. "
            "E.g. for character: 'clan', 'class', 'species', 'deity'; "
            "for concept: 'discipline', 'power_system', 'spell_school'; "
            "for location: 'plane', 'city', 'dungeon'; "
        ),
    )
    description: TrimmedCoerce1000 = Field(default="", max_length=1000)
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value pairs (e.g. {'habitat': 'mountains'})",
    )

    # === Sub-plan 1: Cross-validated sub_type enums ===
    # When entity_type == "organization", group_type is auto-populated
    # from sub_type via the GroupType enum (clan/sect/organization/race/
    # species/faction/party/team/crew/house/tribe/brood/coven/cult/band/
    # gang/dynasty/cabal/fellowship/alliance/other). When entity_type
    # == "location", place_type is auto-populated from sub_type via the
    # PlaceType enum (world/plane/dimension/continent/region/kingdom/
    # country/city/town/district/neighborhood/structure/building/room/
    # landmark/dungeon/wilderness/other). Use these fields for graph
    # queries; sub_type retains the original string.
    group_type: GroupType | None = Field(
        default=None,
        description=(
            "Set automatically when entity_type == 'organization'. "
            "Coerced from sub_type via GroupType. Use this field "
            "for graph queries; sub_type retains the original string."
        ),
    )
    place_type: PlaceType | None = Field(
        default=None,
        description=(
            "Set automatically when entity_type == 'location'. "
            "Coerced from sub_type via PlaceType. Use this field "
            "for graph queries; sub_type retains the original string."
        ),
    )

    @field_validator("properties", mode="before")
    @classmethod
    def _coerce_properties(cls, value: Any) -> dict[str, Any]:
        """Tolerate non-dict ``properties`` from the LLM instead of failing the
        whole extraction batch.

        Models occasionally emit a bare string (e.g. ``"rules:vague"``) or a list
        for ``properties``. Rather than reject 26 otherwise-valid entities in a
        batch, coerce these into a dict so extraction stays robust.
        """
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            if ":" in text:
                key, _, val = text.partition(":")
                return {key.strip() or "note": val.strip()}
            return {"note": text}
        if isinstance(value, (list, tuple)):
            return {f"item_{i}": v for i, v in enumerate(value)}
        return {"value": value}

    @model_validator(mode="after")
    def _populate_group_and_place_type(self) -> "ExtractedEntityArchetype":
        """Cross-field: when entity_type is organization/location,
        coerce sub_type to GroupType/PlaceType. Preserves the original
        sub_type string and stores it in properties['_original_sub_type']
        when it differs from the canonical enum value, so the LLM can
        emit game-system-specific labels without breaking the schema.
        """
        if self.entity_type == "organization":
            coerced = coerce_group_subtype(self.sub_type)
            if coerced != GroupType.OTHER and self.sub_type != coerced.value:
                # LLM used a known group term but in a non-canonical
                # case (e.g. "Clan" or "CLAN" raw). Normalise to
                # the lowercase enum value.
                self.sub_type = coerced.value
            elif coerced == GroupType.OTHER and self.sub_type:
                # Unknown term — preserve original for auditability.
                if self.properties is None:
                    self.properties = {}
                self.properties.setdefault(
                    "_original_sub_type", self.sub_type
                )
            self.group_type = coerced
        elif self.entity_type == "location":
            coerced = coerce_place_subtype(self.sub_type)
            if coerced != PlaceType.OTHER and self.sub_type != coerced.value:
                self.sub_type = coerced.value
            elif coerced == PlaceType.OTHER and self.sub_type:
                if self.properties is None:
                    self.properties = {}
                self.properties.setdefault(
                    "_original_sub_type", self.sub_type
                )
            self.place_type = coerced
        else:
            # For character/faction/object/concept, group/place_type
            # stay None. The cross-field invariant is: only
            # organizations and locations carry group/place_type.
            self.group_type = None
            self.place_type = None
        return self

    parent_archetype: Trimmed200 | None = Field(
        None,
        max_length=200,
        description=("Inheritance link within the current section hierarchy (e.g. 'Clans > Brujah')."),
    )
    parent_entity_name: Trimmed200 | None = Field(None, max_length=200)
    source_ref: Trimmed200 | None = Field(None, max_length=200)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    entity_roles: list[str] = Field(default_factory=list)
    is_container: bool = False
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this entity — required for canon audit trail",
    )


class ExtractedLoreFact(BaseModel):
    """A specific event, relationship, or state fact extracted from the source."""

    statement: Trimmed1000 = Field(max_length=1000)
    fact_type: str = Field(default="state", description="state | relationship | attribute | occurrence")
    involved_entities: list[str] = Field(default_factory=list, description="Names of entities this fact concerns")
    entity_names: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_ref: Trimmed200 | None = Field(None, max_length=200)
    tags: list[str] = Field(default_factory=list)
    canon_level: CanonLevel = Field(
        default=CanonLevel.PROPOSED,
        description="Status: proposed, canon, rumor, character_belief, player_knowledge",
    )
    knowledge_scope: KnowledgeScope = Field(
        default=KnowledgeScope.WORLD,
        description="Scope: world (everyone), character (belief), player (OOC), rumor",
    )
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this lore fact — required for canon audit trail",
    )


class ExtractedTableEntry(BaseModel):
    """A single roll entry in an extracted random table."""

    min_roll: int
    max_roll: int
    value: Trimmed1000 = Field(max_length=1000)
    subtable_name: str | None = Field(None, description="Name of a subtable to roll on")


class ExtractedRandomTable(BaseModel):
    """A random table (e.g. encounter table, loot table) extracted from the source."""

    name: Trimmed200 = Field(max_length=200)
    description: TrimmedCoerce500 = Field(default="", max_length=500)
    table_type: str = Field(default="general", description="encounter | loot | name | rumor | quest")
    dice_formula: str = Field(max_length=100, default="1d100")
    entries: list[ExtractedTableEntry] = Field(default_factory=list)
    source_ref: str | None = Field(None, max_length=200)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this table",
    )


class ExtractedRelationship(BaseModel):
    """An entity-to-entity relationship extracted from the source."""

    from_entity: Trimmed200 = Field(max_length=200)
    to_entity: Trimmed200 = Field(max_length=200)
    rel_type: str = Field(
        default="related_to",
        max_length=100,
        description=(
            "Game-system-agnostic canonical relationship type (e.g. "
            "'MEMBER_OF_GROUP', 'GRANTS_POWER'). LLM-side aliases "
            "like 'member_of_clan' are normalised to the canonical "
            "form. Unknown values are preserved unchanged."
        ),
    )
    description: TrimmedCoerce500 = Field(default="", max_length=500)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional key-value properties for the relationship "
            "(e.g., {'since': 'campaign_start', 'notes': 'Sworn fealty'})"
        ),
    )
    source_ref: Trimmed200 | None = Field(None, max_length=200)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this relationship",
    )

    @field_validator("rel_type", mode="before")
    @classmethod
    def _normalise_rel_type(cls, value: Any) -> str:
        """Normalise LLM-emitted rel_type to the canonical RelationshipType.

        Steps:
          1. If empty/None, return the default ``related_to``.
          2. Strip whitespace, lowercase, replace spaces and dashes with
             underscores. This makes ``"Member Of Clan"`` and
             ``"member-of-clan"`` both match the alias key.
          3. If the normalised string is in ``_REL_TYPE_ALIASES``,
             return the canonical value (e.g. ``"member_of_clan"`` →
             ``"MEMBER_OF_GROUP"``).
          4. Otherwise check if the value (case-preserved) is already a
             valid ``RelationshipType`` and return it as-is. This lets
             the LLM emit canonical uppercase values directly.
          5. Otherwise return the original (un-normalised) value. Unknown
             terms pass through so the canonkeeper can decide what to
             do with them (e.g. log and skip, or surface as a new alias
             candidate for the next enum update).
        """
        if not value:
            return "related_to"
        original = str(value)
        normalised = (
            original.strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
        )
        if normalised in _REL_TYPE_ALIASES:
            return _REL_TYPE_ALIASES[normalised]
        # Already-canonical values (uppercase enum) pass through.
        try:
            RelationshipType(original)
            return original
        except ValueError:
            return original


# Aliases that the LLM is most likely to emit. Each value maps to the
# canonical RelationshipType. Add to this dict as new game systems
# are tested. Keys are case-insensitive after whitespace/dash
# normalisation; values must be a valid RelationshipType value.
_REL_TYPE_ALIASES: dict[str, str] = {
    # Group membership aliases
    "member_of": "MEMBER_OF_GROUP",
    "member_of_sect": "MEMBER_OF_GROUP",
    "member_of_clan": "MEMBER_OF_GROUP",
    "member_of_faction": "MEMBER_OF_GROUP",
    "member_of_organization": "MEMBER_OF_GROUP",
    "member_of_party": "MEMBER_OF_GROUP",
    "member_of_race": "MEMBER_OF_GROUP",
    "member_of_team": "MEMBER_OF_GROUP",
    "member_of_crew": "MEMBER_OF_GROUP",
    "member_of_house": "MEMBER_OF_GROUP",
    "member_of_tribe": "MEMBER_OF_GROUP",
    "member_of_brood": "MEMBER_OF_GROUP",
    "member_of_coven": "MEMBER_OF_GROUP",
    "member_of_cult": "MEMBER_OF_GROUP",
    "member_of_band": "MEMBER_OF_GROUP",
    "member_of_gang": "MEMBER_OF_GROUP",
    "member_of_dynasty": "MEMBER_OF_GROUP",
    "member_of_cabal": "MEMBER_OF_GROUP",
    "member_of_fellowship": "MEMBER_OF_GROUP",
    "member_of_alliance": "MEMBER_OF_GROUP",
    "belongs_to": "MEMBER_OF_GROUP",
    "belongs_to_clan": "MEMBER_OF_GROUP",
    "belongs_to_sect": "MEMBER_OF_GROUP",
    "serves_in": "MEMBER_OF_GROUP",
    "is_a_member_of": "MEMBER_OF_GROUP",
    "of_clan": "MEMBER_OF_GROUP",
    "of_sect": "MEMBER_OF_GROUP",
    "of_faction": "MEMBER_OF_GROUP",
    # Sub-group aliases
    "subgroup_of": "SUBGROUP_OF_GROUP",
    "subclan_of": "SUBGROUP_OF_GROUP",
    "subfaction_of": "SUBGROUP_OF_GROUP",
    "house_of": "SUBGROUP_OF_GROUP",
    "under_sect": "SUBGROUP_OF_GROUP",
    # Leadership aliases
    "leads": "LEADS_GROUP",
    "leads_sect": "LEADS_GROUP",
    "leads_clan": "LEADS_GROUP",
    "leads_faction": "LEADS_GROUP",
    "commands": "LEADS_GROUP",
    "rules_over": "LEADS_GROUP",
    "founded": "FOUNDED_GROUP",
    "created": "FOUNDED_GROUP",
    "controls": "CONTROLS_GROUP",
    "allied_with": "ALLIED_WITH_GROUP",
    "enemy_of": "HOSTILE_TO_GROUP",
    "hostile_to": "HOSTILE_TO_GROUP",
    "rivals": "HOSTILE_TO_GROUP",
    # Power aliases
    "grants": "GRANTS_POWER",
    "grants_power": "GRANTS_POWER",
    "gives": "GRANTS_POWER",
    "has_power": "PRACTICES_DISCIPLINE",
    "practices": "PRACTICES_DISCIPLINE",
    "uses_power": "PRACTICES_DISCIPLINE",
    "learns": "PRACTICES_DISCIPLINE",
    "knows_power": "PRACTICES_DISCIPLINE",
    "has_discipline": "PRACTICES_DISCIPLINE",
    "has_ability": "PRACTICES_DISCIPLINE",
    "affected_by": "AFFECTED_BY",
    "cursed_by": "AFFECTED_BY",
    "blessed_by": "AFFECTED_BY",
    "has_background": "IS_BACKGROUND",
    "has_merit": "IS_BACKGROUND",
    "has_flaw": "IS_BACKGROUND",
    "has_edge": "IS_BACKGROUND",
    "has_hindrance": "IS_BACKGROUND",
    "has_touchstone": "IS_TOUCHSTONE",
    "has_conviction": "IS_TOUCHSTONE",
    "has_tenet": "IS_TOUCHSTONE",
    "has_resource": "IS_RESOURCE",
    # Place aliases
    "located_in": "LOCATED_IN_PLACE",
    "based_in": "LOCATED_IN_PLACE",
    "found_in": "LOCATED_IN_PLACE",
    "in_city": "LOCATED_IN_PLACE",
    "in_world": "LOCATED_IN_PLACE",
    "in_region": "LOCATED_IN_PLACE",
    "contains": "CONTAINS_PLACE",
    "within": "LOCATED_IN_PLACE",

    # === Aliases observed in the live VtM ingest (2026-08-02) ===
    # The LLM doesn't always use the canonical vocabulary from the
    # prompt; it also invents lowercase game-system-specific terms.
    # These aliases are added based on what the LLM actually emitted
    # so the next canonicalisation picks them up.

    # "power_of" / "powers" — LLM tends to write "Discipline is the
    # power_of Blood Pool" or "Blood Pool powers Discipline". Both
    # are AFFECTED_BY (the discipline is affected by the resource).
    "power_of": "AFFECTED_BY",
    "powers": "AFFECTED_BY",
    "powered_by": "AFFECTED_BY",
    "has_power_source": "AFFECTED_BY",
    "granted_by": "GRANTS_POWER",
    "grants_access_to": "GRANTS_POWER",

    # "is_example_of" / "has_example" / "example_of" — example-of
    # is a taxonomic relationship (an example is a subtype).
    "is_example_of": "SUBTYPE_OF",
    "has_example": "SUBTYPE_OF",
    "example_of": "SUBTYPE_OF",

    # "has_member" / "possesses" — generic "has" for groups/entities.
    # Maps to MEMBER_OF_GROUP (the canonical way to express
    # "X is a member of Y" or "X has Y as a member").
    "has_member": "MEMBER_OF_GROUP",
    "possesses": "MEMBER_OF_GROUP",

    # "works_with" — collaboration, mapped to ALLIED_WITH_GROUP.
    "works_with": "ALLIED_WITH_GROUP",

    # "defined_by" / "causes" / "subject_to" / "involved_in" / "leads_to"
    # — generic causal / affected relationships. Map to AFFECTED_BY
    # which is the universal "X is affected by Y" type.
    "defined_by": "AFFECTED_BY",
    "causes": "AFFECTED_BY",
    "subject_to": "AFFECTED_BY",
    "involved_in": "AFFECTED_BY",
    "leads_to": "AFFECTED_BY",

    # "uses" / "used_by" / "used_in" / "uses_ability" / "applies_to" /
    # "available_to" — generic "X uses Y" relationship, mapped to
    # PRACTICES_DISCIPLINE (X practices a power Y).
    "uses": "PRACTICES_DISCIPLINE",
    "used_by": "PRACTICES_DISCIPLINE",
    "used_in": "PRACTICES_DISCIPLINE",
    "uses_ability": "PRACTICES_DISCIPLINE",
    "applies_to": "PRACTICES_DISCIPLINE",
    "available_to": "PRACTICES_DISCIPLINE",

    # "leader_of" — leadership, maps to LEADS_GROUP.
    "leader_of": "LEADS_GROUP",

    # "also_known_as" — alias relationship. Map to SUBTYPE_OF
    # (an alias is a kind of name-substitution; semantically closest
    # available in our enum). Future: add an ALIAS_OF type.
    "also_known_as": "SUBTYPE_OF",
}


class ExtractedTopology(BaseModel):
    """Spatial connection between two locations extracted from the source."""

    from_location: Trimmed200 = Field(max_length=200)
    to_location: Trimmed200 = Field(max_length=200)
    connection_type: str = Field(default="adjacent", description="adjacent | beneath | above | portal")
    description: TrimmedCoerce500 = Field(default="", max_length=500)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_ref: Trimmed200 | None = Field(None, max_length=200)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this topology",
    )


class ExtractedCharacterProfile(BaseModel):
    """Narrative & psychological profile extracted for a character or archetype."""

    name: Trimmed200 = Field(max_length=200)
    traits: dict[str, float] = Field(
        default_factory=dict,
        description="Trait-name to score map (e.g., {'openness': 0.8, 'stoic': 0.4})",
    )
    values: list[str] = Field(default_factory=list, description="Core values or beliefs")
    fears: list[str] = Field(default_factory=list, description="What this character fears")
    desires: list[str] = Field(default_factory=list, description="What this character wants")
    speech_style: Trimmed200 | None = Field(None, max_length=200, description="How they speak")
    mannerisms: list[str] = Field(default_factory=list, description="Physical/behavioral tics")
    is_template: bool = Field(
        default=True,
        description="True if this is an archetypal profile (e.g. 'City Guard'), False if unique character.",
    )
    source_ref: Trimmed200 | None = Field(None, max_length=200)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this profile",
    )


class ExtractedGenerationTemplate(BaseModel):
    """The 'Recipe' to spawn an NPC on the fly."""

    name: Trimmed200 = Field(max_length=200, description="Template name, e.g. 'Brujah Enforcer'")
    archetype_name: Trimmed200 = Field(max_length=200, description="Link to EntityArchetype")
    stat_block_name: Trimmed200 | None = Field(None, max_length=200, description="Link to NPCStatBlock")
    profile_name: Trimmed200 | None = Field(None, max_length=200, description="Link to NPCProfile")
    random_table_names: list[str] = Field(default_factory=list)
    tier_override: str | None = Field(None, description="Override NPC tier (minion, boss, etc.)")
    source_ref: Trimmed200 | None = Field(None, max_length=200)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this template",
    )


class ExtractedToneProfile(BaseModel):
    """Extracted mood, stylistic markers, and narrative instructions."""

    name: Trimmed100 = Field(max_length=100)
    instruction: TrimmedCoerce1000 = Field(max_length=1000)
    trigger_tags: list[str] = Field(default_factory=list)
    example_output: TrimmedCoerce1000 | None = Field(None, max_length=1000)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this tone profile",
    )


# =============================================================================
# INGESTION ARTIFACT SCHEMAS  (produced during document analysis)
# =============================================================================


class ChunkSummaryArtifact(BaseModel):
    """Summary produced by the Analyzer for a single text chunk."""

    chunk_id: str = Field(max_length=200, description="Unique identifier for this chunk")
    chunk_index: int = Field(ge=0, description="Index of the chunk in the source document")
    category: str | None = Field(None, max_length=100, description="Categorization tag (lore, rules, characters, etc.)")
    summary: str = Field(max_length=2000, description="AI-generated summary of chunk content")
    entities_mentioned: list[str] = Field(default_factory=list, description="Entity names found in this chunk")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_ref: str | None = Field(None, max_length=200, description="Reference to source location")
    tags: list[str] = Field(default_factory=list, description="Additional metadata tags")


class SectionSummaryArtifact(BaseModel):
    """Summary produced by the Analyzer for a document section."""

    section_key: str = Field(max_length=200, description="Unique identifier for this section")
    heading_path: list[str] = Field(default_factory=list, description="Section heading hierarchy")
    category: str | None = Field(None, max_length=100, description="Categorization tag for the section")
    summary: str = Field(max_length=3000, description="AI-generated summary of section content")
    key_topics: list[str] = Field(default_factory=list, description="Key topics covered in this section")
    chunk_ids: list[str] = Field(default_factory=list, description="IDs of chunks in this section")
    semantic_category: str | None = Field(None, max_length=100, description="Semantic classification")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SourceMindscapeArtifact(BaseModel):
    """High-level mental model of the entire source document."""

    source_name: str = Field(max_length=500, description="Name of the source document")
    summary: str = Field(max_length=3000, description="Overall document synopsis")
    tone: str | None = Field(None, max_length=200, description="Overall tone of the source")
    genre_tags: list[str] = Field(default_factory=list, description="Genre classifications")
    themes: list[str] = Field(default_factory=list, description="Major themes in the source")
    taxonomy_hints: list[str] = Field(default_factory=list, description="Concepts from game system taxonomies")
    system_overview: str | None = Field(None, max_length=2000, description="Game system overview if rulebook")
    system_name: str | None = Field(None, max_length=200, description="Game system name if rulebook")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class EmbeddedSourceProfile(BaseModel):
    """Source document metadata snapshot embedded in a KnowledgePack."""

    title: str = Field(default="", max_length=500)
    source_type: str = Field(default="mixed", max_length=100, description="rulebook | lore | adventure | supplement")
    edition: str | None = Field(None, max_length=200)
    publisher: str | None = Field(None, max_length=200)
    system_name: str | None = Field(None, max_length=200)
    source_kind: str | None = Field(None, max_length=100)
    world_kind: str | None = Field(None, max_length=200)
    family: str | None = Field(None, max_length=200)
    genre_tone: list[str] = Field(default_factory=list)
    narrative_frame: list[str] = Field(default_factory=list)
    lore_domains: list[str] = Field(default_factory=list)
    taxonomy_containers: list[str] = Field(default_factory=list)
    institution_model: list[str] = Field(default_factory=list)
    relationship_patterns: list[str] = Field(default_factory=list)
    term_lexicon: dict[str, list[str]] = Field(default_factory=dict)
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    canon_signal_terms: list[str] = Field(default_factory=list)
    important_named_sets: list[str] = Field(default_factory=list)
    known_open_questions: list[str] = Field(default_factory=list)
    confidence_by_field: dict[str, float] = Field(default_factory=dict)
    evidence_refs: list[ProfileEvidenceRef] = Field(default_factory=list)
    coverage_summary: str | None = Field(None, max_length=2000)
    profile_version: str | None = Field(None, max_length=50)
    prompt_version: str | None = Field(None, max_length=50)
    model_used: str | None = Field(None, max_length=200)
    world_name: str | None = Field(None, max_length=200)
    multiverse_name: str | None = Field(None, max_length=200)


class EmbeddedWorldProfile(BaseModel):
    """AI-extracted profile of a world's narrative identity and structure.

    This is the output of the World Architect LLM analysis: a structured
    summary of genre, tone, lore domains, entity taxonomy, relationship
    patterns, terminology, and canon signals extracted from source documents.
    """

    world_kind: str | None = Field(
        None, max_length=200, description="World classification (e.g., 'ttrpg_dark_fantasy')"
    )
    profile_type: str | None = Field(None, max_length=50, description="Profile type (e.g., 'world', 'source')")
    system_name: str | None = Field(None, max_length=200)
    edition: str | None = Field(None, max_length=200)
    family: str | None = Field(None, max_length=200, description="Game family (e.g., 'd20', 'pbta', 'vampire')")
    genre_tone: list[str] = Field(default_factory=list, description="Genre and tone descriptors")
    narrative_frame: list[str] = Field(default_factory=list, description="Narrative framing conventions")
    lore_domains: list[str] = Field(default_factory=list, description="Major world knowledge domains")
    taxonomy_containers: list[str] = Field(
        default_factory=list, description="Entity type buckets (factions, clans, classes, etc.)"
    )
    institution_model: list[str] = Field(
        default_factory=list, description="How institutions/organizations are structured"
    )
    relationship_patterns: list[str] = Field(
        default_factory=list, description="Common relationship types in this world"
    )
    term_lexicon: dict[str, list[str]] = Field(default_factory=dict, description="Domain-specific terminology mappings")
    aliases: dict[str, list[str]] = Field(default_factory=dict, description="Known name aliases for entities")
    canon_signal_terms: list[str] = Field(default_factory=list, description="Terms that signal canonical content")
    important_named_sets: list[str] = Field(default_factory=list, description="Named groups/sets of entities")
    known_open_questions: list[str] = Field(
        default_factory=list, description="Unresolved questions raised during analysis"
    )
    confidence_by_field: dict[str, float] = Field(default_factory=dict, description="Per-field confidence scores")
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list, description="Source evidence backing this profile"
    )
    coverage_summary: str | None = Field(None, max_length=2000, description="Coverage assessment summary")
    profile_version: str | None = Field(None, max_length=50)
    prompt_version: str | None = Field(None, max_length=50)
    model_used: str | None = Field(None, max_length=200)
    world_name: str | None = Field(None, max_length=200)
    multiverse_name: str | None = Field(None, max_length=200)


# =============================================================================
# MAIN KNOWLEDGE PACK SCHEMAS
# =============================================================================


class EmbeddedGameSystem(BaseModel):
    """Full mechanical ruleset snapshot stored directly inside a KnowledgePack."""

    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    core_mechanic: CoreMechanic | None = None
    attributes: list[AttributeDefinition] = Field(default_factory=list)
    skills: list[SkillDefinition] = Field(default_factory=list)
    resources: list[ResourceDefinition] = Field(default_factory=list)
    rules: list[GameRule] = Field(default_factory=list)
    tracks: list[TrackDefinition] = Field(default_factory=list)
    tiered_abilities: list[TieredAbilitySystem] = Field(default_factory=list)
    advantages: list[AdvantageDefinition] = Field(default_factory=list)
    resolution_mechanics: list[ResolutionMechanic] = Field(
        default_factory=list,
        description="Detailed resolution mechanics beyond the core mechanic",
    )
    damage_model: DamageModel | None = Field(None, description="Complete damage and wound system")
    conditions: list[ConditionDefinition] = Field(
        default_factory=list, description="Status effects with trigger conditions"
    )
    scenery_rules: list[SceneryRule] = Field(
        default_factory=list, description="Scenery tag rules for dynamic evaluation"
    )
    action_economy: ActionEconomy | None = Field(None, description="Full turn structure and action budget")
    advancement_model: AdvancementModel | None = Field(None, description="Full advancement system")
    recovery_model: RecoveryModel | None = Field(None, description="Complete recovery and rest system")
    character_creation: CharacterCreationProcedure | None = None
    npc_stat_blocks: list[NPCStatBlock] = Field(default_factory=list)
    npc_creation_rules: NPCCreationRules | None = None
    random_tables: list[ExtractedRandomTable] = Field(default_factory=list)
    agendas: list[ExtractedAgenda] = Field(default_factory=list)
    topologies: list[ExtractedTopology] = Field(default_factory=list)
    character_profiles: list[ExtractedCharacterProfile] = Field(default_factory=list)
    generation_templates: list[ExtractedGenerationTemplate] = Field(default_factory=list)
    needs_review: bool = Field(
        default=False,
        description=(
            "True when extraction produced a degenerate result (zero "
            "populated schema fields, or a placeholder-only core_mechanic) "
            "instead of a genuine success. See INGESTION_PIPELINE_AUDIT.md "
            "Finding 5 — this replaces a silent default-value fallback."
        ),
    )
    degenerate_reason: str | None = Field(None, max_length=500)


class KnowledgePackCreate(BaseModel):
    """Request to create a new knowledge pack."""

    pack_id: UUID | None = None
    name: Trimmed200 = Field(max_length=200)
    description: TrimmedCoerce1000 = Field(default="", max_length=1000)
    # [G-2] Authored verbatim intro the GM reads aloud when this pack is the
    # session's campaign setting. Optional — packs without it fall back to
    # the resume-recap or generated cold-open path in ``build_gm_opening``.
    # Max 8000 chars to cover a chapter-sized read-aloud prologue. Not
    # trimmed: verbatim fidelity matters for the player-facing text.
    intro_text: str | None = Field(
        None,
        max_length=8000,
        description=(
            "Optional verbatim opening the GM reads aloud when this pack is "
            "the campaign setting. See P&F §5 — authoritative case-3 of "
            "build_gm_opening; takes precedence over resume-recap and the "
            "generated cold-open."
        ),
    )
    pack_type: KnowledgePackType = Field(default=KnowledgePackType.MISC)
    system_name: Trimmed200 | None = Field(None, max_length=200)
    status: KnowledgePackStatus = Field(default=KnowledgePackStatus.PENDING)
    source_document_ids: list[UUID] = Field(default_factory=list)
    ingestion_job_id: UUID | None = None
    tags: list[str] = Field(default_factory=list)
    parent_pack_ids: list[UUID] = Field(default_factory=list)
    axioms: list[ExtractedAxiom] = Field(default_factory=list)
    entity_archetypes: list[ExtractedEntityArchetype] = Field(default_factory=list)
    lore_facts: list[ExtractedLoreFact] = Field(default_factory=list)
    entity_relationships: list[Any] = Field(default_factory=list)
    random_tables: list[ExtractedRandomTable] = Field(default_factory=list)
    agendas: list[ExtractedAgenda] = Field(default_factory=list)
    topologies: list[ExtractedTopology] = Field(default_factory=list)
    character_profiles: list[ExtractedCharacterProfile] = Field(default_factory=list)
    generation_templates: list[ExtractedGenerationTemplate] = Field(default_factory=list)
    tone_profiles: list[ExtractedToneProfile] = Field(default_factory=list)
    plot_threads: list[ExtractedPlotThread] = Field(default_factory=list)
    game_system_id: UUID | None = None
    game_system_data: EmbeddedGameSystem | None = None
    source_profile_data: Any | None = None
    chunk_summaries: list[Any] = Field(default_factory=list)
    section_summaries: list[Any] = Field(default_factory=list)
    source_mindscape: Any | None = None


class KnowledgePackUpdate(BaseModel):
    """Request to update an existing knowledge pack."""

    name: Trimmed200 | None = None
    description: Trimmed1000 | None = None
    # [G-2] Optional — patch endpoint accepts ``intro_text`` updates.
    intro_text: str | None = Field(None, max_length=8000)
    status: KnowledgePackStatus | None = None
    tags: list[str] | None = None
    game_system_id: UUID | None = None
    source_profile_data: EmbeddedSourceProfile | None = None
    axioms: list[ExtractedAxiom] | None = None
    entity_archetypes: list[ExtractedEntityArchetype] | None = None
    lore_facts: list[ExtractedLoreFact] | None = None
    random_tables: list[ExtractedRandomTable] | None = None
    agendas: list[ExtractedAgenda] | None = None
    topologies: list[ExtractedTopology] | None = None
    character_profiles: list[ExtractedCharacterProfile] | None = None
    generation_templates: list[ExtractedGenerationTemplate] | None = None
    tone_profiles: list[ExtractedToneProfile] | None = None
    plot_threads: list[ExtractedPlotThread] | None = None
    game_system_data: EmbeddedGameSystem | None = None
    chunk_summaries: list[Any] | None = None
    section_summaries: list[Any] | None = None
    source_mindscape: Any | None = None


class AppliedToEntry(BaseModel):
    """Record of when and where this pack was applied."""

    multiverse_id: UUID
    universe_id: UUID | None = None
    applied_at: datetime


class KnowledgePackResponse(BaseModel):
    """Complete knowledge pack data for the UI/Library."""

    id: UUID = Field(alias="pack_id")
    name: str
    description: str
    # [G-2] Authored verbatim intro — surfaced in the UI for re-reading and
    # resolved by ``build_gm_opening`` when this pack is the session source.
    intro_text: str | None = Field(None, max_length=8000)
    pack_type: KnowledgePackType
    system_name: str | None
    status: KnowledgePackStatus
    source_document_ids: list[UUID]
    ingestion_job_id: UUID | None
    tags: list[str]
    parent_pack_ids: list[UUID] = Field(default_factory=list)
    axioms: list[ExtractedAxiom] = Field(default_factory=list)
    entity_archetypes: list[ExtractedEntityArchetype] = Field(default_factory=list)
    lore_facts: list[ExtractedLoreFact] = Field(default_factory=list)
    entity_relationships: list[ExtractedRelationship] = Field(default_factory=list)
    random_tables: list[ExtractedRandomTable] = Field(default_factory=list)
    agendas: list[ExtractedAgenda] = Field(default_factory=list)
    topologies: list[ExtractedTopology] = Field(default_factory=list)
    character_profiles: list[ExtractedCharacterProfile] = Field(default_factory=list)
    generation_templates: list[ExtractedGenerationTemplate] = Field(default_factory=list)
    tone_profiles: list[ExtractedToneProfile] = Field(default_factory=list)
    plot_threads: list[ExtractedPlotThread] = Field(default_factory=list)
    game_system_id: UUID | None = None
    game_system_data: EmbeddedGameSystem | None = None
    source_profile_data: EmbeddedSourceProfile | None = None
    chunk_summaries: list[ChunkSummaryArtifact] = Field(default_factory=list)
    section_summaries: list[SectionSummaryArtifact] = Field(default_factory=list)
    source_mindscape: SourceMindscapeArtifact | None = None
    applied_to: list[AppliedToEntry] = Field(default_factory=list)
    axiom_count: int = Field(default_factory=lambda: 0)
    entity_count: int = Field(default_factory=lambda: 0)
    lore_fact_count: int = Field(default_factory=lambda: 0)
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class ApplyKnowledgePackRequest(BaseModel):
    """Parameters for applying a pack to a multiverse."""

    multiverse_id: UUID
    universe_id: UUID | None = None
    conflict_resolution: str = Field(default="merge", description="merge | overwrite | skip")
    apply_axioms: bool = Field(default=True)
    apply_entities: bool = Field(default=True)
    apply_lore_facts: bool = Field(default=True)
    apply_relationships: bool = Field(default=True)
    apply_random_tables: bool = Field(default=True)
    apply_agendas: bool = Field(default=True)
    apply_topologies: bool = Field(default=True)
    apply_tone_profiles: bool = Field(default=True)
    apply_character_profiles: bool = Field(default=True)
    apply_generation_templates: bool = Field(default=True)
    apply_plot_threads: bool = Field(default=True)
    proposer: str = Field(default="Agent")
    # Subset selection (F1-6): None means "apply all items of that type";
    # a list restricts application to those pack indices.
    entity_indices: list[int] | None = Field(default=None)
    axiom_indices: list[int] | None = Field(default=None)
    lore_indices: list[int] | None = Field(default=None)
    # Payload overrides for individually resolved items, keyed
    # "entity:{i}" | "axiom:{i}" | "lore:{i}" (human_picked resolutions).
    item_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class KnowledgePackFilter(BaseModel):
    """Filter parameters for listing knowledge packs."""

    pack_type: KnowledgePackType | None = None
    system_name: str | None = Field(None, max_length=200)
    status: KnowledgePackStatus | None = None
    tag: str | None = Field(None, max_length=200)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class KnowledgePackListResponse(BaseModel):
    """Response for listing knowledge packs."""

    packs: list[KnowledgePackResponse]
    total: int
    limit: int
    offset: int


class PackConflict(BaseModel):
    """Represents a conflict detected during pack application."""

    entity_name: str = Field(max_length=200)
    existing_id: UUID | None = None
    proposed_id: UUID | None = None
    conflict_type: str = Field(max_length=100, description="duplicate | version_mismatch | overwrite")
    resolution: str = Field(
        default="pending",
        max_length=50,
        description="pending | resolved_keep_existing | resolved_use_proposed | resolved_merge",
    )


class PackApplySession(BaseModel):
    """Tracks the state of a pack application session."""

    session_id: UUID
    pack_id: UUID
    multiverse_id: UUID
    status: str = Field(default="in_progress", max_length=50)
    conflicts: list[PackConflict] = Field(default_factory=list)
    applied_count: int = Field(default=0)
    skipped_count: int = Field(default=0)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


class PackExportEnvelope(BaseModel):
    """Envelope for exporting a knowledge pack to a .monitorpack file."""

    exported_at: datetime
    pack: dict[str, Any] = Field(description="Full serialized KnowledgePack")
