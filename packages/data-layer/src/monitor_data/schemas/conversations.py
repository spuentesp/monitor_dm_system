"""
Pydantic schemas for NPC Conversation Session operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools.py

A ConversationSession is a lightweight MongoDB document that tracks a
focused dialogue exchange — either a real-time chat with one or more NPCs
(DIRECT mode) or an out-of-character "actor reflection" session (ACTOR mode).

It differs from a Scene in that:
- No dice rolls / Resolver involvement
- No scene-level canonization at end (only memory writes + proposals)
- Exists INSIDE a scene (scene_id is optional reference) or as standalone
- Uses fast/cheap LLM (LIGHT role) for NPC responses

Three conversation modes:
  DIRECT  — Real-time chat with NPC(s). Player speaks, NPC(s) respond in
             character. Used inside an active scene (P-17).
  ACTOR   — Out-of-character reflection. GM speaks TO the NPC who responds
             as an actor analysing their role (M-31).
  SCENE   — Embedded in scene narration; Narrator mediates NPC voices.
             This mode is handled by the Narrator agent (P-5), not this loop.
             Included here as a marker so sessions are fully queryable.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class ConversationMode(StrEnum):
    """How the conversation session is framed."""

    DIRECT = "direct"
    """Real-time in-character dialogue with NPC(s) inside a scene."""

    ACTOR = "actor"
    """Out-of-character actor reflection — GM talks to NPC as a role analyst."""

    SCENE = "scene"
    """Embedded NPC voice within GM narration (Narrator-mediated, read-only here)."""


class ConversationStatus(StrEnum):
    """Lifecycle status of a conversation session."""

    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# =============================================================================
# SUB-MODELS
# =============================================================================


class ConversationTurn(BaseModel):
    """A single exchange within a ConversationSession."""

    turn_index: int = Field(ge=0, description="Zero-based turn index within session")
    speaker_role: str = Field(description="'player', 'npc', or 'gm' (actor-mode framing messages)")
    entity_id: UUID | None = Field(None, description="NPC entity UUID when speaker_role='npc'")
    entity_name: str | None = Field(
        None,
        max_length=200,
        description="Cached NPC name for display (avoids re-querying Neo4j)",
    )
    text: str = Field(min_length=1, max_length=8000)
    emotional_state: str | None = Field(
        None,
        max_length=100,
        description="NPC's dominant emotion at time of response (extracted by NPCVoice)",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# =============================================================================
# CONVERSATION SESSION CRUD SCHEMAS
# =============================================================================


class ConversationSessionCreate(BaseModel):
    """Request to open a new NPC conversation session."""

    universe_id: UUID
    mode: ConversationMode
    npc_ids: list[UUID] = Field(
        min_length=1,
        description="One or more NPC EntityInstance UUIDs participating in this conversation",
    )
    scene_id: UUID | None = Field(
        None,
        description="Active scene during which this conversation takes place (DIRECT mode)",
    )
    story_id: UUID | None = Field(
        None,
        description="Story this conversation belongs to",
    )
    player_entity_id: UUID | None = Field(
        None,
        description="PC entity UUID (used to personalise NPC memories of the player)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata (GM notes, actor session goals, etc.)",
    )


class ConversationSessionResponse(BaseModel):
    """Full conversation session document returned from MongoDB."""

    conversation_id: UUID
    universe_id: UUID
    mode: ConversationMode
    status: ConversationStatus
    npc_ids: list[UUID]
    scene_id: UUID | None
    story_id: UUID | None
    player_entity_id: UUID | None
    turns: list[ConversationTurn] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ConversationSessionUpdate(BaseModel):
    """Request to close or update a conversation session."""

    status: ConversationStatus | None = None
    metadata: dict[str, Any] | None = None


class ConversationSessionFilter(BaseModel):
    """Filter for listing conversation sessions."""

    universe_id: UUID | None = None
    scene_id: UUID | None = None
    story_id: UUID | None = None
    npc_id: UUID | None = Field(None, description="Filter sessions that include this NPC")
    mode: ConversationMode | None = None
    status: ConversationStatus | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class ConversationSessionListResponse(BaseModel):
    """Paginated list of conversation sessions."""

    sessions: list[ConversationSessionResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# TURN APPEND SCHEMA
# =============================================================================


class AppendConversationTurn(BaseModel):
    """Request to append a single turn to an existing session."""

    speaker_role: str = Field(
        pattern="^(player|npc|gm)$",
        description="'player', 'npc', or 'gm'",
    )
    entity_id: UUID | None = Field(None, description="NPC entity UUID if speaker_role='npc'")
    entity_name: str | None = Field(None, max_length=200)
    text: str = Field(min_length=1, max_length=8000)
    emotional_state: str | None = Field(None, max_length=100)
