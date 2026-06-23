"""
Pydantic models for the entities router.

Separated from the router module to follow SRP.
These models are UI-specific DTOs (Data Transfer Objects) used only
for request/response serialization in the entities endpoints.
"""

from __future__ import annotations

from typing import Any, Literal

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


class RPGSystemUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    version: str | None = None
    rules: list[RuleInfo] | None = None


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
    first_message: str = Field(
        default="", description="Opening message when chat starts"
    )
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
    entity_id: str | None = None  # Neo4j entity ID if linked to universe
    memory_count: int = 0
    created_at: str
    updated_at: str


class CharacterImportRequest(BaseModel):
    """Import a universe NPC as a standalone character."""

    source_entity_id: str = Field(
        ..., description="Neo4j entity ID of the NPC to import"
    )
    as_ooc_persona: bool = Field(
        default=False,
        description="If True, import without universe/memory context",
    )
