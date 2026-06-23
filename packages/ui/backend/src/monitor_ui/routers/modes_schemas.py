"""
Pydantic models for the modes router.

Separated from the router module to follow SRP.
"""

from __future__ import annotations

from pydantic import BaseModel


class ModeConfig(BaseModel):
    id: str
    label: str
    tagline: str
    description: str
    capabilities: list[str]
    color: str
    icon: str


class ActiveMode(BaseModel):
    mode_id: str
    world_id: str | None = None
    character_id: str | None = None
    tone: str = "dramatic"
    context_depth: str = "standard"


class SetActiveMode(BaseModel):
    mode_id: str
    world_id: str | None = None
    character_id: str | None = None
    tone: str = "dramatic"
    context_depth: str = "standard"
