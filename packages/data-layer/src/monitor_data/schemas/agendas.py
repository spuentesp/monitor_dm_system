"""
Pydantic schemas for Faction Agendas and Clocks.

LAYER: 1 (data-layer)
Use Case: M-36 (Faction Drive)
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import ProfileEvidenceRef


class AgendaStatus(StrEnum):
    """The current state of an agenda."""

    DORMANT = "dormant"
    ACTIVE = "active"
    COMPLETED = "completed"
    THWARTED = "failed"


class AgendaType(StrEnum):
    """The nature of the drive."""

    FACTION_GOAL = "faction_goal"
    WORLD_EVENT = "world_event"
    PERSONAL_VENDETTA = "personal_vendetta"
    MINDSCAPE_EVOLUTION = "mindscape_evolution"


class ExtractedAgenda(BaseModel):
    """An agenda or clock extracted from source text."""

    title: str = Field(max_length=200)
    description: str = Field(max_length=2000)
    agenda_type: str = Field(default="faction_goal")
    suggested_segments: int = Field(default=6)
    confidence: float = Field(default=0.8)
    evidence_refs: list[ProfileEvidenceRef] = Field(
        default_factory=list,
        description="Source snippets/sections backing this agenda",
    )


class AgendaCreate(BaseModel):
    """Request to create a new agenda."""

    universe_id: UUID
    owner_id: UUID | None = None  # Faction/Character ID
    title: str = Field(max_length=200)
    description: str = Field(max_length=2000)
    agenda_type: AgendaType = Field(default=AgendaType.FACTION_GOAL)
    status: AgendaStatus = Field(default=AgendaStatus.ACTIVE)
    total_segments: int = Field(default=6, ge=1, le=12)
    current_segments: int = Field(default=0, ge=0)
    properties: dict[str, Any] | None = None


class AgendaResponse(BaseModel):
    """Full agenda data including its current clock state."""

    id: UUID
    universe_id: UUID
    owner_id: UUID | None
    title: str
    description: str
    agenda_type: AgendaType
    status: AgendaStatus
    total_segments: int
    current_segments: int
    properties: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgendaFilter(BaseModel):
    """Filter parameters for listing agendas."""

    universe_id: UUID | None = None
    owner_id: UUID | None = None
    status: AgendaStatus | None = None
    agenda_type: AgendaType | None = None
