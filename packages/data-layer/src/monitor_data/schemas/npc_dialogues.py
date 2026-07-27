"""
Pydantic schemas for NPC Dialogue operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

An NPCDialogue is a persistent, persona-driven chat session between the
player and a specific NPC. It is fundamentally different from a Scene:

  Scene  = GM narrates; NPC lines are short; player takes action.
  Dialogue = Player directly chats with NPC; NPC holds conversation.

The dialogue system:
1. Loads the NPC's EntityInstance (identity), NPCProfile (personality),
   and relevant CharacterMemories (what the NPC remembers).
2. Builds a dynamic system prompt embodying the NPC persona.
3. Maintains the full message history here in MongoDB.
4. Tracks which memories were activated (for memory access updates).
5. If embedded_in_scene=True, the dialogue turns are also injected into
   the parent scene as entity turns.

Dialogues are NOT scenes and do NOT trigger canonization directly.
Any canonical changes (new facts, relationship changes) are created as
ProposedChanges that CanonKeeper evaluates at the next scene end.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import DialogueStatus

# =============================================================================
# MESSAGE SCHEMA
# =============================================================================


class DialogueMessage(BaseModel):
    """A single message in an NPC dialogue exchange."""

    message_id: UUID
    role: str = Field(
        max_length=20,
        description="Message role: 'player', 'npc', 'system', 'narrator'",
    )
    text: str = Field(min_length=1, max_length=10000)
    timestamp: datetime
    # Memory tracking: which memories were consulted/activated for this message
    memory_refs_read: list[UUID] = Field(
        default_factory=list,
        description="Memory IDs the NPC consulted when generating this response",
    )
    # NPC emotional state at this moment (snapshot per message)
    npc_emotional_state: str | None = Field(
        None,
        max_length=200,
        description="NPC's dominant emotional state during this message",
    )
    # Any proposals triggered by this exchange
    proposed_change_ids: list[UUID] = Field(
        default_factory=list,
        description="ProposedChange IDs created as a result of this message",
    )


# =============================================================================
# DIALOGUE CRUD SCHEMAS
# =============================================================================


class NPCDialogueCreate(BaseModel):
    """Request to create/start an NPC dialogue session.

    persona_snapshot is captured at session start so the NPC's state is
    consistent throughout the dialogue even if their EntityInstance changes mid-story.
    """

    entity_id: UUID = Field(description="The NPC being spoken to")
    universe_id: UUID
    player_entity_id: UUID | None = Field(None, description="Player character doing the talking (if applicable)")
    scene_id: UUID | None = Field(None, description="Scene this dialogue is part of (if during a scene)")
    story_id: UUID | None = Field(None, description="Story context for this dialogue")
    embedded_in_scene: bool = Field(
        default=False,
        description="If True, NPC replies are also written as entity turns in the parent scene",
    )
    # NPC persona snapshot at dialogue start
    persona_snapshot: dict[str, Any] = Field(
        default_factory=dict,
        description="Snapshot of NPC entity properties + profile at dialogue start (for consistency)",
    )
    # Opening context
    opening_context: str | None = Field(
        None,
        max_length=1000,
        description="Narrator-written context for how this conversation starts",
    )


class AppendDialogueMessage(BaseModel):
    """Request to append a message to an NPC dialogue."""

    dialogue_id: UUID
    role: str = Field(
        max_length=20,
        description="Message role: 'player', 'npc', 'system', 'narrator'",
    )
    text: str = Field(min_length=1, max_length=10000)
    memory_refs_read: list[UUID] = Field(default_factory=list)
    npc_emotional_state: str | None = Field(None, max_length=200)
    proposed_change_ids: list[UUID] = Field(default_factory=list)


class NPCDialogueUpdate(BaseModel):
    """Request to update dialogue status or metadata."""

    status: DialogueStatus | None = None
    summary: str | None = Field(
        None,
        max_length=2000,
        description="Summary of what was discussed (written at dialogue end)",
    )


class NPCDialogueResponse(BaseModel):
    """Response with NPCDialogue data."""

    dialogue_id: UUID
    entity_id: UUID
    universe_id: UUID
    player_entity_id: UUID | None = None
    scene_id: UUID | None = None
    story_id: UUID | None = None
    status: DialogueStatus
    embedded_in_scene: bool
    persona_snapshot: dict[str, Any]
    opening_context: str | None = None
    messages: list[DialogueMessage] = Field(default_factory=list)
    summary: str | None = None
    created_at: datetime
    updated_at: datetime
    ended_at: datetime | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class NPCDialogueFilter(BaseModel):
    """Filter for listing NPC dialogues."""

    entity_id: UUID | None = Field(None, description="Filter by NPC")
    player_entity_id: UUID | None = Field(None, description="Filter by player")
    scene_id: UUID | None = None
    story_id: UUID | None = None
    status: DialogueStatus | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class NPCDialogueListResponse(BaseModel):
    """Response for list operations."""

    dialogues: list[NPCDialogueResponse]
    total: int
    limit: int
    offset: int
