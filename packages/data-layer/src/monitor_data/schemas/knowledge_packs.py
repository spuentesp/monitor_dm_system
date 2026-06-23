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
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

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
from monitor_data.schemas.plot_threads import ExtractedPlotThread
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
    SceneryRule,
    NPCCreationRules,
    NPCStatBlock,
    RecoveryModel,
    ResolutionMechanic,
    ResourceDefinition,
    SkillDefinition,
    TieredAbilitySystem,
    TrackDefinition,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class KnowledgePackType(str, Enum):
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


class KnowledgePackStatus(str, Enum):
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
    source_ref: Optional[Trimmed200] = Field(None, max_length=200)
    tags: List[str] = Field(default_factory=list)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this axiom — required for canon audit trail",
    )


class ExtractedEntityArchetype(BaseModel):
    """An entity category/template (race, class, faction type) extracted from source."""

    name: Trimmed200 = Field(max_length=200)
    entity_type: str = Field(
        description="character | faction | location | object | concept | organization"
    )
    sub_type: Optional[Trimmed100] = Field(
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
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value pairs (e.g. {'habitat': 'mountains'})",
    )

    @field_validator("properties", mode="before")
    @classmethod
    def _coerce_properties(cls, value: Any) -> Dict[str, Any]:
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

    parent_archetype: Optional[Trimmed200] = Field(
        None,
        max_length=200,
        description=(
            "Inheritance link within the current section hierarchy (e.g. 'Clans > Brujah')."
        ),
    )
    parent_entity_name: Optional[Trimmed200] = Field(None, max_length=200)
    source_ref: Optional[Trimmed200] = Field(None, max_length=200)
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    tags: List[str] = Field(default_factory=list)
    entity_roles: List[str] = Field(default_factory=list)
    is_container: bool = False
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this entity — required for canon audit trail",
    )


class ExtractedLoreFact(BaseModel):
    """A specific event, relationship, or state fact extracted from the source."""

    statement: Trimmed1000 = Field(max_length=1000)
    fact_type: str = Field(
        default="state", description="state | relationship | attribute | occurrence"
    )
    involved_entities: List[str] = Field(
        default_factory=list, description="Names of entities this fact concerns"
    )
    entity_names: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_ref: Optional[Trimmed200] = Field(None, max_length=200)
    tags: List[str] = Field(default_factory=list)
    canon_level: CanonLevel = Field(
        default=CanonLevel.PROPOSED,
        description="Status: proposed, canon, rumor, character_belief, player_knowledge",
    )
    knowledge_scope: KnowledgeScope = Field(
        default=KnowledgeScope.WORLD,
        description="Scope: world (everyone), character (belief), player (OOC), rumor",
    )
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this lore fact — required for canon audit trail",
    )


class ExtractedTableEntry(BaseModel):
    """A single roll entry in an extracted random table."""

    min_roll: int
    max_roll: int
    value: Trimmed1000 = Field(max_length=1000)
    subtable_name: Optional[str] = Field(None, description="Name of a subtable to roll on")


class ExtractedRandomTable(BaseModel):
    """A random table (e.g. encounter table, loot table) extracted from the source."""

    name: Trimmed200 = Field(max_length=200)
    description: TrimmedCoerce500 = Field(default="", max_length=500)
    table_type: str = Field(
        default="general", description="encounter | loot | name | rumor | quest"
    )
    dice_formula: str = Field(max_length=100, default="1d100")
    entries: List[ExtractedTableEntry] = Field(default_factory=list)
    source_ref: Optional[str] = Field(None, max_length=200)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this table",
    )


class ExtractedRelationship(BaseModel):
    """An entity-to-entity relationship extracted from the source."""

    from_entity: Trimmed200 = Field(max_length=200)
    to_entity: Trimmed200 = Field(max_length=200)
    rel_type: str = Field(default="related_to", max_length=100, description="e.g., 'allied_with', 'enemy_of'")
    description: TrimmedCoerce500 = Field(default="", max_length=500)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Optional key-value properties for the relationship "
            "(e.g., {'since': 'campaign_start', 'notes': 'Sworn fealty'})"
        ),
    )
    source_ref: Optional[Trimmed200] = Field(None, max_length=200)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this relationship",
    )


class ExtractedTopology(BaseModel):
    """Spatial connection between two locations extracted from the source."""

    from_location: Trimmed200 = Field(max_length=200)
    to_location: Trimmed200 = Field(max_length=200)
    connection_type: str = Field(
        default="adjacent", description="adjacent | beneath | above | portal"
    )
    description: TrimmedCoerce500 = Field(default="", max_length=500)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    source_ref: Optional[Trimmed200] = Field(None, max_length=200)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this topology",
    )


class ExtractedCharacterProfile(BaseModel):
    """Narrative & psychological profile extracted for a character or archetype."""

    name: Trimmed200 = Field(max_length=200)
    traits: Dict[str, float] = Field(
        default_factory=dict,
        description="Trait-name to score map (e.g., {'openness': 0.8, 'stoic': 0.4})",
    )
    values: List[str] = Field(default_factory=list, description="Core values or beliefs")
    fears: List[str] = Field(default_factory=list, description="What this character fears")
    desires: List[str] = Field(default_factory=list, description="What this character wants")
    speech_style: Optional[Trimmed200] = Field(None, max_length=200, description="How they speak")
    mannerisms: List[str] = Field(default_factory=list, description="Physical/behavioral tics")
    is_template: bool = Field(
        default=True,
        description="True if this is an archetypal profile (e.g. 'City Guard'), False if unique character.",
    )
    source_ref: Optional[Trimmed200] = Field(None, max_length=200)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this profile",
    )


class ExtractedGenerationTemplate(BaseModel):
    """The 'Recipe' to spawn an NPC on the fly."""

    name: Trimmed200 = Field(max_length=200, description="Template name, e.g. 'Brujah Enforcer'")
    archetype_name: Trimmed200 = Field(max_length=200, description="Link to EntityArchetype")
    stat_block_name: Optional[Trimmed200] = Field(
        None, max_length=200, description="Link to NPCStatBlock"
    )
    profile_name: Optional[Trimmed200] = Field(
        None, max_length=200, description="Link to NPCProfile"
    )
    random_table_names: List[str] = Field(default_factory=list)
    tier_override: Optional[str] = Field(None, description="Override NPC tier (minion, boss, etc.)")
    source_ref: Optional[Trimmed200] = Field(None, max_length=200)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this template",
    )


class ExtractedToneProfile(BaseModel):
    """Extracted mood, stylistic markers, and narrative instructions."""

    name: Trimmed100 = Field(max_length=100)
    instruction: TrimmedCoerce1000 = Field(max_length=1000)
    trigger_tags: List[str] = Field(default_factory=list)
    example_output: Optional[TrimmedCoerce1000] = Field(None, max_length=1000)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    evidence_refs: List[ProfileEvidenceRef] = Field(
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
    category: Optional[str] = Field(
        None, max_length=100, description="Categorization tag (lore, rules, characters, etc.)"
    )
    summary: str = Field(max_length=2000, description="AI-generated summary of chunk content")
    entities_mentioned: List[str] = Field(
        default_factory=list, description="Entity names found in this chunk"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_ref: Optional[str] = Field(
        None, max_length=200, description="Reference to source location"
    )
    tags: List[str] = Field(default_factory=list, description="Additional metadata tags")


class SectionSummaryArtifact(BaseModel):
    """Summary produced by the Analyzer for a document section."""

    section_key: str = Field(max_length=200, description="Unique identifier for this section")
    heading_path: List[str] = Field(default_factory=list, description="Section heading hierarchy")
    category: Optional[str] = Field(
        None, max_length=100, description="Categorization tag for the section"
    )
    summary: str = Field(max_length=3000, description="AI-generated summary of section content")
    key_topics: List[str] = Field(
        default_factory=list, description="Key topics covered in this section"
    )
    chunk_ids: List[str] = Field(default_factory=list, description="IDs of chunks in this section")
    semantic_category: Optional[str] = Field(
        None, max_length=100, description="Semantic classification"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class SourceMindscapeArtifact(BaseModel):
    """High-level mental model of the entire source document."""

    source_name: str = Field(max_length=500, description="Name of the source document")
    summary: str = Field(max_length=3000, description="Overall document synopsis")
    tone: Optional[str] = Field(None, max_length=200, description="Overall tone of the source")
    genre_tags: List[str] = Field(default_factory=list, description="Genre classifications")
    themes: List[str] = Field(default_factory=list, description="Major themes in the source")
    taxonomy_hints: List[str] = Field(
        default_factory=list, description="Concepts from game system taxonomies"
    )
    system_overview: Optional[str] = Field(
        None, max_length=2000, description="Game system overview if rulebook"
    )
    system_name: Optional[str] = Field(
        None, max_length=200, description="Game system name if rulebook"
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class EmbeddedSourceProfile(BaseModel):
    """Source document metadata snapshot embedded in a KnowledgePack."""

    title: str = Field(default="", max_length=500)
    source_type: str = Field(
        default="mixed", max_length=100, description="rulebook | lore | adventure | supplement"
    )
    edition: Optional[str] = Field(None, max_length=200)
    publisher: Optional[str] = Field(None, max_length=200)
    system_name: Optional[str] = Field(None, max_length=200)
    source_kind: Optional[str] = Field(None, max_length=100)
    world_kind: Optional[str] = Field(None, max_length=200)
    family: Optional[str] = Field(None, max_length=200)
    genre_tone: List[str] = Field(default_factory=list)
    narrative_frame: List[str] = Field(default_factory=list)
    lore_domains: List[str] = Field(default_factory=list)
    taxonomy_containers: List[str] = Field(default_factory=list)
    institution_model: List[str] = Field(default_factory=list)
    relationship_patterns: List[str] = Field(default_factory=list)
    term_lexicon: Dict[str, List[str]] = Field(default_factory=dict)
    aliases: Dict[str, List[str]] = Field(default_factory=dict)
    canon_signal_terms: List[str] = Field(default_factory=list)
    important_named_sets: List[str] = Field(default_factory=list)
    known_open_questions: List[str] = Field(default_factory=list)
    confidence_by_field: Dict[str, float] = Field(default_factory=dict)
    evidence_refs: List[ProfileEvidenceRef] = Field(default_factory=list)
    coverage_summary: Optional[str] = Field(None, max_length=2000)
    profile_version: Optional[str] = Field(None, max_length=50)
    prompt_version: Optional[str] = Field(None, max_length=50)
    model_used: Optional[str] = Field(None, max_length=200)
    world_name: Optional[str] = Field(None, max_length=200)
    multiverse_name: Optional[str] = Field(None, max_length=200)


class EmbeddedWorldProfile(BaseModel):
    """AI-extracted profile of a world's narrative identity and structure.

    This is the output of the World Architect LLM analysis: a structured
    summary of genre, tone, lore domains, entity taxonomy, relationship
    patterns, terminology, and canon signals extracted from source documents.
    """

    world_kind: Optional[str] = Field(
        None, max_length=200, description="World classification (e.g., 'ttrpg_dark_fantasy')"
    )
    profile_type: Optional[str] = Field(
        None, max_length=50, description="Profile type (e.g., 'world', 'source')"
    )
    system_name: Optional[str] = Field(None, max_length=200)
    edition: Optional[str] = Field(None, max_length=200)
    family: Optional[str] = Field(
        None, max_length=200, description="Game family (e.g., 'd20', 'pbta', 'vampire')"
    )
    genre_tone: List[str] = Field(default_factory=list, description="Genre and tone descriptors")
    narrative_frame: List[str] = Field(
        default_factory=list, description="Narrative framing conventions"
    )
    lore_domains: List[str] = Field(
        default_factory=list, description="Major world knowledge domains"
    )
    taxonomy_containers: List[str] = Field(
        default_factory=list, description="Entity type buckets (factions, clans, classes, etc.)"
    )
    institution_model: List[str] = Field(
        default_factory=list, description="How institutions/organizations are structured"
    )
    relationship_patterns: List[str] = Field(
        default_factory=list, description="Common relationship types in this world"
    )
    term_lexicon: Dict[str, List[str]] = Field(
        default_factory=dict, description="Domain-specific terminology mappings"
    )
    aliases: Dict[str, List[str]] = Field(
        default_factory=dict, description="Known name aliases for entities"
    )
    canon_signal_terms: List[str] = Field(
        default_factory=list, description="Terms that signal canonical content"
    )
    important_named_sets: List[str] = Field(
        default_factory=list, description="Named groups/sets of entities"
    )
    known_open_questions: List[str] = Field(
        default_factory=list, description="Unresolved questions raised during analysis"
    )
    confidence_by_field: Dict[str, float] = Field(
        default_factory=dict, description="Per-field confidence scores"
    )
    evidence_refs: List[ProfileEvidenceRef] = Field(
        default_factory=list, description="Source evidence backing this profile"
    )
    coverage_summary: Optional[str] = Field(
        None, max_length=2000, description="Coverage assessment summary"
    )
    profile_version: Optional[str] = Field(None, max_length=50)
    prompt_version: Optional[str] = Field(None, max_length=50)
    model_used: Optional[str] = Field(None, max_length=200)
    world_name: Optional[str] = Field(None, max_length=200)
    multiverse_name: Optional[str] = Field(None, max_length=200)


# =============================================================================
# MAIN KNOWLEDGE PACK SCHEMAS
# =============================================================================


class EmbeddedGameSystem(BaseModel):
    """Full mechanical ruleset snapshot stored directly inside a KnowledgePack."""

    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    core_mechanic: Optional[CoreMechanic] = None
    attributes: List[AttributeDefinition] = Field(default_factory=list)
    skills: List[SkillDefinition] = Field(default_factory=list)
    resources: List[ResourceDefinition] = Field(default_factory=list)
    rules: List[GameRule] = Field(default_factory=list)
    tracks: List[TrackDefinition] = Field(default_factory=list)
    tiered_abilities: List[TieredAbilitySystem] = Field(default_factory=list)
    advantages: List[AdvantageDefinition] = Field(default_factory=list)
    resolution_mechanics: List[ResolutionMechanic] = Field(
        default_factory=list,
        description="Detailed resolution mechanics beyond the core mechanic",
    )
    damage_model: Optional[DamageModel] = Field(
        None, description="Complete damage and wound system"
    )
    conditions: List[ConditionDefinition] = Field(
        default_factory=list, description="Status effects with trigger conditions"
    )
    scenery_rules: List[SceneryRule] = Field(
        default_factory=list, description="Scenery tag rules for dynamic evaluation"
    )
    action_economy: Optional[ActionEconomy] = Field(
        None, description="Full turn structure and action budget"
    )
    advancement_model: Optional[AdvancementModel] = Field(
        None, description="Full advancement system"
    )
    recovery_model: Optional[RecoveryModel] = Field(
        None, description="Complete recovery and rest system"
    )
    character_creation: Optional[CharacterCreationProcedure] = None
    npc_stat_blocks: List[NPCStatBlock] = Field(default_factory=list)
    npc_creation_rules: Optional[NPCCreationRules] = None
    random_tables: List[ExtractedRandomTable] = Field(default_factory=list)
    agendas: List[ExtractedAgenda] = Field(default_factory=list)
    topologies: List[ExtractedTopology] = Field(default_factory=list)
    character_profiles: List[ExtractedCharacterProfile] = Field(default_factory=list)
    generation_templates: List[ExtractedGenerationTemplate] = Field(default_factory=list)


class KnowledgePackCreate(BaseModel):
    """Request to create a new knowledge pack."""

    pack_id: Optional[UUID] = None
    name: Trimmed200 = Field(max_length=200)
    description: TrimmedCoerce1000 = Field(default="", max_length=1000)
    pack_type: KnowledgePackType = Field(default=KnowledgePackType.MISC)
    system_name: Optional[Trimmed200] = Field(None, max_length=200)
    status: KnowledgePackStatus = Field(default=KnowledgePackStatus.PENDING)
    source_document_ids: List[UUID] = Field(default_factory=list)
    ingestion_job_id: Optional[UUID] = None
    tags: List[str] = Field(default_factory=list)
    parent_pack_ids: List[UUID] = Field(default_factory=list)
    axioms: List[ExtractedAxiom] = Field(default_factory=list)
    entity_archetypes: List[ExtractedEntityArchetype] = Field(default_factory=list)
    lore_facts: List[ExtractedLoreFact] = Field(default_factory=list)
    entity_relationships: List[Any] = Field(default_factory=list)
    random_tables: List[ExtractedRandomTable] = Field(default_factory=list)
    agendas: List[ExtractedAgenda] = Field(default_factory=list)
    topologies: List[ExtractedTopology] = Field(default_factory=list)
    character_profiles: List[ExtractedCharacterProfile] = Field(default_factory=list)
    generation_templates: List[ExtractedGenerationTemplate] = Field(default_factory=list)
    tone_profiles: List[ExtractedToneProfile] = Field(default_factory=list)
    plot_threads: List[ExtractedPlotThread] = Field(default_factory=list)
    game_system_id: Optional[UUID] = None
    game_system_data: Optional[EmbeddedGameSystem] = None
    source_profile_data: Optional[Any] = None
    chunk_summaries: List[Any] = Field(default_factory=list)
    section_summaries: List[Any] = Field(default_factory=list)
    source_mindscape: Optional[Any] = None


class KnowledgePackUpdate(BaseModel):
    """Request to update an existing knowledge pack."""

    name: Optional[Trimmed200] = None
    description: Optional[Trimmed1000] = None
    status: Optional[KnowledgePackStatus] = None
    tags: Optional[List[str]] = None
    game_system_id: Optional[UUID] = None
    source_profile_data: Optional[EmbeddedSourceProfile] = None
    axioms: Optional[List[ExtractedAxiom]] = None
    entity_archetypes: Optional[List[ExtractedEntityArchetype]] = None
    lore_facts: Optional[List[ExtractedLoreFact]] = None
    random_tables: Optional[List[ExtractedRandomTable]] = None
    agendas: Optional[List[ExtractedAgenda]] = None
    topologies: Optional[List[ExtractedTopology]] = None
    character_profiles: Optional[List[ExtractedCharacterProfile]] = None
    generation_templates: Optional[List[ExtractedGenerationTemplate]] = None
    tone_profiles: Optional[List[ExtractedToneProfile]] = None
    plot_threads: Optional[List[ExtractedPlotThread]] = None
    game_system_data: Optional[EmbeddedGameSystem] = None
    chunk_summaries: Optional[List[Any]] = None
    section_summaries: Optional[List[Any]] = None
    source_mindscape: Optional[Any] = None


class AppliedToEntry(BaseModel):
    """Record of when and where this pack was applied."""

    multiverse_id: UUID
    universe_id: Optional[UUID] = None
    applied_at: datetime


class KnowledgePackResponse(BaseModel):
    """Complete knowledge pack data for the UI/Library."""

    id: UUID = Field(alias="pack_id")
    name: str
    description: str
    pack_type: KnowledgePackType
    system_name: Optional[str]
    status: KnowledgePackStatus
    source_document_ids: List[UUID]
    ingestion_job_id: Optional[UUID]
    tags: List[str]
    parent_pack_ids: List[UUID] = Field(default_factory=list)
    axioms: List[ExtractedAxiom] = Field(default_factory=list)
    entity_archetypes: List[ExtractedEntityArchetype] = Field(default_factory=list)
    lore_facts: List[ExtractedLoreFact] = Field(default_factory=list)
    entity_relationships: List[ExtractedRelationship] = Field(default_factory=list)
    random_tables: List[ExtractedRandomTable] = Field(default_factory=list)
    agendas: List[ExtractedAgenda] = Field(default_factory=list)
    topologies: List[ExtractedTopology] = Field(default_factory=list)
    character_profiles: List[ExtractedCharacterProfile] = Field(default_factory=list)
    generation_templates: List[ExtractedGenerationTemplate] = Field(default_factory=list)
    tone_profiles: List[ExtractedToneProfile] = Field(default_factory=list)
    plot_threads: List[ExtractedPlotThread] = Field(default_factory=list)
    game_system_id: Optional[UUID] = None
    game_system_data: Optional[EmbeddedGameSystem] = None
    source_profile_data: Optional[EmbeddedSourceProfile] = None
    chunk_summaries: List[ChunkSummaryArtifact] = Field(default_factory=list)
    section_summaries: List[SectionSummaryArtifact] = Field(default_factory=list)
    source_mindscape: Optional[SourceMindscapeArtifact] = None
    applied_to: List[AppliedToEntry] = Field(default_factory=list)
    axiom_count: int = Field(default_factory=lambda: 0)
    entity_count: int = Field(default_factory=lambda: 0)
    lore_fact_count: int = Field(default_factory=lambda: 0)
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class ApplyKnowledgePackRequest(BaseModel):
    """Parameters for applying a pack to a multiverse."""

    multiverse_id: UUID
    universe_id: Optional[UUID] = None
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


class KnowledgePackFilter(BaseModel):
    """Filter parameters for listing knowledge packs."""

    pack_type: Optional[KnowledgePackType] = None
    system_name: Optional[str] = Field(None, max_length=200)
    status: Optional[KnowledgePackStatus] = None
    tag: Optional[str] = Field(None, max_length=200)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class KnowledgePackListResponse(BaseModel):
    """Response for listing knowledge packs."""

    packs: List[KnowledgePackResponse]
    total: int
    limit: int
    offset: int


class PackConflict(BaseModel):
    """Represents a conflict detected during pack application."""

    entity_name: str = Field(max_length=200)
    existing_id: Optional[UUID] = None
    proposed_id: Optional[UUID] = None
    conflict_type: str = Field(
        max_length=100, description="duplicate | version_mismatch | overwrite"
    )
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
    conflicts: List[PackConflict] = Field(default_factory=list)
    applied_count: int = Field(default=0)
    skipped_count: int = Field(default=0)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class PackExportEnvelope(BaseModel):
    """Envelope for exporting a knowledge pack to a .monitorpack file."""

    exported_at: datetime
    pack: Dict[str, Any] = Field(description="Full serialized KnowledgePack")
