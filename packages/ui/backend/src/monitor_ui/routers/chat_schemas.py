"""
Pydantic models for the chat router.

Extracted from chat.py to keep the router focused on endpoint logic.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = "New Session"
    mode: str = "autonomous_gm"
    multiverse_id: str | None = None
    multiverse_label: str | None = None
    universe_id: str | None = None
    universe_label: str | None = None
    world_id: str | None = None
    character_id: str | None = None
    speaker_character_id: str | None = None
    speaker_label: str | None = None
    controlled_character_ids: list[str] = Field(default_factory=list)
    system_id: str | None = None
    pack_id: str | None = None
    system_source_type: str | None = None
    system_source_id: str | None = None
    system_label: str | None = None
    benchmark_id: str | None = None
    benchmark_label: str | None = None
    tone: str = "dramatic"
    tone_profile_id: UUID | None = Field(
        None,
        description=(
            "Optional UUID of a ToneProfile. When set, the Narrator uses this profile's "
            "instruction directly instead of resolving via tag matching. "
            "Overrides the tone string. If not set, tone is resolved via "
            "GMProfile.tone_library_id and tone_tags."
        ),
    )
    gm_profile_id: str | None = None  # GM Profile UUID — overrides tone when set
    play_mode: str = (
        "dice_game_system"  # "narrative" | "dice_standard" | "dice_game_system"
    )
    scene_id: str | None = None  # resume an existing scene
    story_id: str | None = None  # resume an existing story
    chat_mode: str = "ic"  # "ic" | "ooc"
    phase: str = (
        "awaiting_character"  # "awaiting_character" | "char_creation" | "active_play"
    )


class MessageSend(BaseModel):
    content: str
    chat_mode: str = Field(
        default="ic",
        description='"ic" (in-character, full memory+world) or "ooc" (AI persona, no context)',
    )
    character_id: str | None = Field(
        default=None,
        description="Which character/NPC to chat as (for OOC and IC modes)",
    )
    is_ooc_persona: bool = Field(
        default=False,
        description="If True, treat character as bare AI persona (no world/memory context)",
    )


class Session(BaseModel):
    id: str
    title: str
    mode: str
    multiverse_id: str | None = None
    multiverse_label: str | None = None
    universe_id: str | None = None
    universe_label: str | None = None
    world_id: str | None = None
    character_id: str | None = None
    speaker_character_id: str | None = None
    speaker_label: str | None = None
    controlled_character_ids: list[str] = Field(default_factory=list)
    system_id: str | None = None
    pack_id: str | None = None
    system_source_type: str | None = None
    system_source_id: str | None = None
    system_label: str | None = None
    benchmark_id: str | None = None
    benchmark_label: str | None = None
    tone: str = "dramatic"
    tone_profile_id: UUID | None = None
    gm_profile_id: str | None = None  # GM Profile UUID — overrides tone when set
    play_mode: str = (
        "dice_game_system"  # "narrative" | "dice_standard" | "dice_game_system"
    )
    scene_id: str | None = None
    story_id: str | None = None
    chat_mode: str = "ic"
    phase: str = (
        "awaiting_character"  # "awaiting_character" | "char_creation" | "active_play"
    )
    created_at: str
    updated_at: str
    message_count: int = 0


class Message(BaseModel):
    id: str
    session_id: str
    role: str  # "gm" | "player" | "system" | "character"
    content: str
    timestamp: str
    metadata: dict[str, Any] = {}
    chat_mode: str = "ic"  # "ic" | "ooc"
    character_id: str | None = None


class SessionStateResponse(BaseModel):
    """Lightweight session-state view for the play UI, debugging, and benchmarks."""

    session: Session
    message_count: int
    latest_gm_message_id: str | None = None
    latest_gm_metadata: dict[str, Any] = Field(default_factory=dict)
    recent_phase_sequence: list[str] = Field(default_factory=list)
    recent_success_levels: list[str] = Field(default_factory=list)
    recent_npc_stances: list[str] = Field(default_factory=list)
    pending_consequence: dict[str, Any] = Field(default_factory=dict)
    last_consequence_choice: str | None = None
    latest_working_state: dict[str, Any] = Field(default_factory=dict)
    latest_scene_checkpoint: dict[str, Any] = Field(default_factory=dict)
    latest_social_read: dict[str, Any] = Field(default_factory=dict)
    latest_relationship_snapshot: dict[str, Any] = Field(default_factory=dict)


class SessionPatch(BaseModel):
    """Partial update for a session."""

    title: str | None = None
    tone: str | None = None
    gm_profile_id: str | None = None
    scene_id: str | None = None
    story_id: str | None = None
    chat_mode: str | None = None


class StoryResponse(BaseModel):
    """View of a Story Loop state."""

    story_id: UUID
    universe_id: UUID
    arc_label: str
    tension_score: float
    active_threads: list[str]
    completed_threads: list[str]
    current_scene_id: UUID | None = None
    story_complete: bool = False
    in_game_time: str
    world_ticks: int
    scenes_completed: int


class StoryPatch(BaseModel):
    """Partial update for a story's narrative state (DM override)."""

    arc_label: str | None = None
    tension_score: float | None = None
    active_threads: list[str] | None = None
