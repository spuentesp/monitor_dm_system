"""
Schemas for audio capture transcripts (CF-10 / G02).

Audio is just another way to type into the Session Recorder: a recording
becomes a transcript, a transcript becomes segments, and a segment becomes
a capture entry — the same CF-1 pipeline a typed entry goes through.

These schemas hold the transcript and its segments, plus the record of
which provider made them (so a GM can tell where their words came from).

LAYER: 1 (data-layer)
IMPORTS FROM: external libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools/transcripts.py, UI backend routers
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TranscriptSegmentCreate(BaseModel):
    """One stretch of speech in a transcript."""

    index: int = Field(ge=0)
    start: float = Field(ge=0.0, description="Start time in seconds")
    end: float = Field(ge=0.0, description="End time in seconds")
    text: str = Field(min_length=1, max_length=10000)
    speaker: str | None = Field(
        default=None,
        max_length=200,
        description="Speaker label, when the provider or the GM assigned one",
    )
    reviewed: bool = Field(
        default=False,
        description="Whether the GM has confirmed this segment's text",
    )


class TranscriptCreate(BaseModel):
    """A transcript to store."""

    universe_id: UUID
    story_id: UUID | None = None
    session_id: UUID | None = Field(
        default=None, description="The recording session this transcript belongs to"
    )
    scene_id: UUID | None = Field(
        default=None,
        description="The scene this recording covers; a queued segment is scoped to it",
    )
    owner_id: str = Field(max_length=200)
    text: str = Field(default="", max_length=200000)
    language: str | None = Field(default=None, max_length=32)
    duration: float | None = Field(default=None, ge=0.0)
    provider: str = Field(default="", max_length=200)
    model: str = Field(default="", max_length=200)
    audio_key: str | None = Field(
        default=None,
        max_length=400,
        description="Where the recording is stored, when it was kept",
    )
    segments: list[TranscriptSegmentCreate] = Field(default_factory=list)


class TranscriptSegment(TranscriptSegmentCreate):
    """A stored segment."""

    id: UUID
    transcript_id: UUID


class Transcript(BaseModel):
    """A stored transcript."""

    transcript_id: UUID
    universe_id: UUID
    story_id: UUID | None = None
    session_id: UUID | None = None
    scene_id: UUID | None = None
    owner_id: str
    text: str = ""
    language: str | None = None
    duration: float | None = None
    provider: str = ""
    model: str = ""
    audio_key: str | None = None
    segments: list[TranscriptSegment] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TranscriptUpdate(BaseModel):
    """A GM's edits to a transcript."""

    text: str | None = Field(default=None, max_length=200000)
    segments: list[TranscriptSegmentCreate] | None = None


__all__ = [
    "Transcript",
    "TranscriptCreate",
    "TranscriptSegment",
    "TranscriptSegmentCreate",
    "TranscriptUpdate",
]
