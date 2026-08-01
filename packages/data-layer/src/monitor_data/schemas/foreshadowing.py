"""Schemas for the scene_foreshadowing collection."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ForeshadowingCreate(BaseModel):
    scene_id: UUID
    story_id: UUID
    kind: str = Field(pattern="^(plant|payoff)$")
    summary: str = Field(min_length=1, max_length=200)
    planted_by_turn: int = Field(ge=0)
    target_turn: int = Field(ge=0)


class ForeshadowingUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(open|paid)$")
    paid_at: datetime | None = None


class ForeshadowingFilter(BaseModel):
    scene_id: UUID | None = None
    story_id: UUID | None = None
    status: str | None = None
    status_in: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=100)


class ForeshadowingResponse(BaseModel):
    foreshadowing_id: UUID
    scene_id: UUID
    story_id: UUID
    kind: str
    summary: str
    planted_by_turn: int
    target_turn: int
    status: str
    created_at: datetime
    paid_at: datetime | None = None
    paid_at_turn: int | None = None