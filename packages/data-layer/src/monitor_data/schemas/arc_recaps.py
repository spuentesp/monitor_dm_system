"""
Pydantic schemas for campaign-level (story-arc) recaps (CF-12).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and base schemas
CALLED BY: mongodb_tools/stories.py

An arc recap is the "where are we in the campaign" document for a story:
one MongoDB document per story (upserted, so persistence is idempotent),
stored with `generated_at` and a scene watermark so callers can tell how
far into the campaign the recap reaches.
"""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class ArcRecapDetail(StrEnum):
    """Length control for an arc recap (matches CF-6 detail levels)."""

    SHORT = "short"
    STANDARD = "standard"
    DETAILED = "detailed"


class ArcRecapCreate(BaseModel):
    """Request to save (upsert) a story's arc recap."""

    story_id: UUID
    universe_id: UUID | None = None
    recap_markdown: str = Field(min_length=1, max_length=60000, description="The campaign recap in markdown")
    detail: ArcRecapDetail = ArcRecapDetail.STANDARD
    scene_count: int = Field(default=0, ge=0, description="Watermark: how many scenes the recap covers")
    scenes_watermark: str = Field(
        default="",
        max_length=64,
        description="Watermark: ISO timestamp of the most recently updated scene covered",
    )
    last_scene_id: UUID | None = Field(None, description="Watermark: the newest scene covered by the recap")


class ArcRecap(ArcRecapCreate):
    """A persisted arc recap (one per story)."""

    recap_id: UUID
    generated_at: datetime
    updated_at: datetime


__all__ = [
    "ArcRecap",
    "ArcRecapCreate",
    "ArcRecapDetail",
]
