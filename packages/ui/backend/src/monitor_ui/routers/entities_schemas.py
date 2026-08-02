"""
Pydantic models for the entities router.

Separated from the router module to follow SRP.
These models are UI-specific DTOs (Data Transfer Objects) used only
for request/response serialization in the entities endpoints.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from monitor_data.schemas.base import Authority, CanonLevel
from monitor_data.schemas.facts import AxiomCreate, EventCreate, FactCreate
from monitor_data.schemas.npc_profiles import (
    BehavioralTrigger,
    CharacterPreference,
    EmotionalTendency,
)
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# NPC models
# ---------------------------------------------------------------------------


class NPC(BaseModel):
    id: str
    name: str
    entity_type: str
    universe_id: str | None = None
    universe_name: str | None = None
    description: str | None = None
    state_tags: list[str] = []
    properties: dict[str, Any] = {}
    memory_count: int = 0
    canon_level: str = "canon"
    is_archetype: bool = False


class NPCMemory(BaseModel):
    id: str
    content: str
    timestamp: str
    importance: float = 0.5
    memory_type: str = "episodic"


class NPCDetail(NPC):
    memories: list[NPCMemory] = []
    stats: dict[str, Any] = {}
    relationships: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []


class PaginatedNPCs(BaseModel):
    items: list[NPC]
    total: int
    limit: int
    offset: int


# ---------------------------------------------------------------------------
# RPG system models
# ---------------------------------------------------------------------------


class CoreMechanicInfo(BaseModel):
    mechanic_type: str = "roll_under"
    formula: str | None = None
    success_type: str | None = None
    target_number: int | None = None
    description: str | None = None


class AttributeInfo(BaseModel):
    name: str
    abbreviation: str | None = None
    min_value: int | None = None
    max_value: int | None = None
    description: str | None = None


class SkillInfo(BaseModel):
    name: str
    linked_attribute: str | None = None
    description: str | None = None
    untrained_allowed: bool = True


class ResourceInfo(BaseModel):
    name: str
    abbreviation: str | None = None
    max_value: int | None = None
    recovers_on: str | None = None
    depleted_effect: str | None = None


class RuleInfo(BaseModel):
    name: str
    rule_type: str = "custom"
    description: str | None = None
    formula: str | None = None
    examples: list[str] = []
    exceptions: list[str] = []


class RPGSystem(BaseModel):
    id: str
    name: str
    description: str | None = None
    version: str | None = None
    core_mechanic: CoreMechanicInfo | None = None
    attributes: list[AttributeInfo] = []
    skills: list[SkillInfo] = []
    resources: list[ResourceInfo] = []
    rules: list[RuleInfo] = []
    is_builtin: bool = False
    source_document_id: str | None = None
    character_count: int = 0
    session_count: int = 0
    needs_review: bool = False
    degenerate_reason: str | None = None


class RPGSystemUpdateRequest(BaseModel):
    """Targeted field patch for an ingested/hand-authored game system.

    INGESTION_PIPELINE_AUDIT.md Finding 8: before this, the only way to fix
    one field of an already-ingested system (e.g. relabel a mislabeled
    character-creation step, correct a placeholder core_mechanic, add a
    missing attribute) was a raw, ad-hoc Mongo ``update_one`` run by hand.
    ``attributes``/``core_mechanic``/``character_creation`` are optional so a
    caller can patch just one field without resending the whole document.
    """

    name: str | None = None
    description: str | None = None
    version: str | None = None
    rules: list[RuleInfo] | None = None
    attributes: list[AttributeInfo] | None = None
    skills: list[SkillInfo] | None = None
    resources: list[ResourceInfo] | None = None
    core_mechanic: CoreMechanicInfo | None = None
    character_creation: dict[str, Any] | None = Field(
        None,
        description=(
            "Raw character_creation dict — {steps: [...], backgrounds: [...], ...}. "
            "Routed through the same _build_character_creation semantic "
            "validation (Finding 2) as ingestion, so a hand-patch can't "
            "introduce a step_type/content mismatch either."
        ),
    )


class RPGSystemCreateRequest(BaseModel):
    """Hand-author a game system from scratch, with no source PDF.

    INGESTION_PIPELINE_AUDIT.md Finding 8, second gap: there was no
    supported path for authoring a homebrew system (or a well-known system
    chosen to hand-author deliberately) other than editing
    ``vtm_game_system.py``-style seed scripts by hand. This runs through the
    exact same schema validation as ingestion (``_build_attributes`` /
    ``_build_core_mechanic`` / ``_build_character_creation``), so
    hand-authored and ingested systems are structurally identical.
    """

    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    version: str | None = None
    core_mechanic: CoreMechanicInfo | None = None
    attributes: list[AttributeInfo] = Field(default_factory=list)
    skills: list[SkillInfo] = Field(default_factory=list)
    resources: list[ResourceInfo] = Field(default_factory=list)
    character_creation: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Character models
# ---------------------------------------------------------------------------


class Character(BaseModel):
    id: str
    name: str
    system_id: str | None = None
    system_name: str | None = None
    universe_id: str | None = None
    description: str | None = None
    attributes: dict[str, Any] = {}
    state_tags: list[str] = []
    canon_level: str = "canon"


class GenerateEntityRequest(BaseModel):
    """Unified request for previewing or saving a PC/NPC from a system source."""

    system_id: str | None = None
    pack_id: str | None = None
    universe_id: str | None = None
    kind: Literal["pc", "npc"] = "pc"
    save: bool = False
    name: str | None = None
    description: str | None = None
    concept: str | None = None
    tier: str | None = None
    state_tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Standalone Character CRUD (Roleplay UI)
# ---------------------------------------------------------------------------


class CharacterCreate(BaseModel):
    """Create a standalone character (no universe dependency)."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    avatar_url: str | None = Field(default=None)
    personality: str = Field(default="", description="Free-text personality notes")
    gm_notes: str = Field(
        default="",
        description="Author's Note — instructions for the AI, not shown to players",
    )
    first_message: str = Field(default="", description="Opening message when chat starts")
    is_ooc_persona: bool = Field(
        default=False,
        description="If True, this character is a bare AI persona (no memory/world context in OOC mode)",
    )


class CharacterUpdate(BaseModel):
    """Update an existing standalone character."""

    name: str | None = None
    description: str | None = None
    avatar_url: str | None = None
    personality: str | None = None
    gm_notes: str | None = None
    first_message: str | None = None
    is_ooc_persona: bool | None = None


class CharacterDetail(CharacterCreate):
    """Full character response with runtime stats."""

    id: str
    entity_id: str | None = None  # Neo4j entity ID of the *default* incarnation
    default_universe_id: str | None = None
    versions: list[CharacterVersion] = Field(default_factory=list)
    memory_count: int = 0
    created_at: str
    updated_at: str


class CharacterImportRequest(BaseModel):
    """Import a universe NPC as a standalone character."""

    source_entity_id: str = Field(..., description="Neo4j entity ID of the NPC to import")
    as_ooc_persona: bool = Field(
        default=False,
        description="If True, import without universe/memory context",
    )


# ---------------------------------------------------------------------------
# Conversatory (MONITOR-backed chat with a roster character)
# ---------------------------------------------------------------------------


class CharacterExpandResponse(BaseModel):
    """Result of expanding a light card into a MONITOR-backed character."""

    character_id: str
    version_id: str
    entity_id: str
    universe_id: str


class CharacterVersion(BaseModel):
    """One incarnation of a character in a specific universe.

    A character card is the source of truth; each version is a separate
    (entity_id, universe_id) pair with its own NPCProfile, memory set,
    emotional state, and relationship deltas. Versions are isolated — no
    cross-incarnation leak unless the caller opts in.
    """

    version_id: str
    universe_id: str
    entity_id: str
    npc_profile_id: str | None = None
    created_at: str
    last_chatted_at: str | None = None


class CharacterVersionCreateRequest(BaseModel):
    """Request to create (or fetch) a per-universe incarnation of a character."""

    universe_id: str | None = Field(
        default=None,
        description=(
            "Target universe. If omitted, the character's default incarnation "
            "is used (or the hidden Conversatory if no default is set)."
        ),
    )


class CardDraftRequest(BaseModel):
    """Ask the LLM to draft/fill a character card from a concept."""

    concept: str = Field(..., min_length=1, description="Short premise for the character")
    name: str = Field(default="", description="Name the user already chose (optional)")
    description: str = Field(default="", description="Partial description to refine (optional)")
    personality: str = Field(default="", description="Partial personality to refine (optional)")


class CardDraftResponse(BaseModel):
    """A drafted card — not persisted; the UI shows it for review/edit."""

    name: str
    description: str = ""
    personality: str = ""
    first_message: str = ""
    gm_notes: str = ""


class ConversationStartRequest(BaseModel):
    """Open a conversatory session. Optional universe routes to a version."""

    universe_id: str | None = Field(
        default=None,
        description=(
            "Target universe for this session. If omitted, the character's "
            "default incarnation is used. A new incarnation is created if the "
            "character hasn't been expanded into this universe yet."
        ),
    )
    persona_character_id: str | None = Field(
        default=None,
        description=(
            "Optional persona card (a character with is_ooc_persona=true) to "
            "play as. Its name resolves {{user}} when card text is rendered."
        ),
    )


class ConversationStartResponse(BaseModel):
    """A freshly opened conversatory session."""

    conversation_id: str
    character_id: str
    version_id: str
    entity_id: str
    universe_id: str
    opening: str


class ConversationSendRequest(BaseModel):
    """A single player line in a conversatory session."""

    text: str = Field(..., min_length=1)
    include_cross_incarnation: bool = Field(
        default=False,
        description=(
            "If True, the NPC's memory recall also surfaces memories from "
            "this character's other incarnations (other universes). Default "
            "False — keeps each universe's memory strictly partitioned."
        ),
    )


class ConversationReply(BaseModel):
    """The character's response plus its live emotional/relationship read."""

    text: str
    emotional_state: str | None = None
    relationship_snapshot: dict[str, Any] = Field(default_factory=dict)


class ConversationSummary(BaseModel):
    """A past conversatory session (for resume/history lists)."""

    conversation_id: str | None = None
    status: str | None = None
    turn_count: int = 0
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Ontology CRUD models (F2-2 — facts / axioms / events)
# ---------------------------------------------------------------------------


class FactCreateRequest(FactCreate):
    """FactCreate with ``universe_id`` supplied by the path, not the body.

    UI-authored facts default to GM-authored canon, matching the
    single-entity create precedent (``POST /entities``).
    """

    universe_id: UUID | None = None  # type: ignore[assignment]
    canon_level: CanonLevel = CanonLevel.CANON
    authority: Authority = Authority.GM


class AxiomCreateRequest(AxiomCreate):
    """AxiomCreate with ``universe_id`` supplied by the path, not the body."""

    universe_id: UUID | None = None  # type: ignore[assignment]
    canon_level: CanonLevel = CanonLevel.CANON


class EventCreateRequest(EventCreate):
    """EventCreate with ``universe_id`` supplied by the path, not the body."""

    universe_id: UUID | None = None  # type: ignore[assignment]
    canon_level: CanonLevel = CanonLevel.CANON
    authority: Authority = Authority.GM


# ---------------------------------------------------------------------------
# NPC profile editor (F2-2 phase 5)
# ---------------------------------------------------------------------------


class NPCProfileUpsertRequest(BaseModel):
    """Editable NPCProfile fields for the profile editor modal.

    Mirrors the writable subset of ``NPCProfileUpdate`` (the in-session
    append helpers and per-universe partitions are intentionally excluded —
    the editor replaces whole lists).
    """

    traits: dict[str, float] | None = None
    values: list[str] | None = None
    fears: list[str] | None = None
    desires: list[str] | None = None
    speech_style: str | None = Field(None, max_length=200)
    catchphrases: list[str] | None = None
    mannerisms: list[str] | None = None
    emotional_tendencies: list[EmotionalTendency] | None = None
    preferences: list[CharacterPreference] | None = None
    triggers: list[BehavioralTrigger] | None = None
    secrets: list[str] | None = None
    gm_notes: str | None = Field(None, max_length=5000)
    current_emotional_state: str | None = Field(None, max_length=200)
