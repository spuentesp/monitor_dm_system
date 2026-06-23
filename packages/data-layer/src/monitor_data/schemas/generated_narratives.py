"""
Pydantic schemas for GeneratedNarrative operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

GeneratedNarratives are post-processed, human-readable accounts of play.
They sit on top of the raw scene/session data and can be:

  LITERARY   — prose fiction, third-person narrator style
  DRAMATIC   — screenplay / stage directions style
  SUMMARY    — bullet-point factual recap
  LOG        — raw chronological event list with rolls/outcomes

Multiple narratives can be generated for the same source (different styles,
different perspectives, regenerated after corrections).

Source types:
  SESSION  — covers an entire play session (one chapter)
  SCENE    — covers a single scene (shorter piece)
  STORY    — covers the whole story arc (end-of-campaign write-up)
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import NarrativeStyle, NarrativeSourceType


# =============================================================================
# GENERATED NARRATIVE CRUD SCHEMAS
# =============================================================================


class GeneratedNarrativeCreate(BaseModel):
    """Request to store a generated narrative."""

    source_type: NarrativeSourceType = Field(
        description="What was narrated: SESSION, SCENE, or STORY"
    )
    source_id: UUID = Field(description="ID of the session/scene/story being narrated")
    universe_id: UUID
    story_id: UUID
    style: NarrativeStyle = Field(
        default=NarrativeStyle.LITERARY,
        description="LITERARY/DRAMATIC/SUMMARY/LOG",
    )
    text: str = Field(min_length=1, description="The generated narrative text")
    perspective: Optional[str] = Field(
        None,
        max_length=50,
        description="Narrative perspective: 'third_person', 'first_person', 'second_person'",
    )
    model_used: Optional[str] = Field(
        None,
        max_length=200,
        description="LLM model used for generation (for audit/comparison)",
    )
    # Scene/session range this narrative covers
    scene_ids_covered: List[UUID] = Field(
        default_factory=list,
        description="Scene IDs included in this narrative",
    )


class GeneratedNarrativeUpdate(BaseModel):
    """Request to update a generated narrative (e.g., hand-edit corrections)."""

    text: Optional[str] = Field(None, min_length=1)
    is_edited_by_user: Optional[bool] = Field(
        None,
        description="True if a human has manually edited the generated text",
    )


class GeneratedNarrativeResponse(BaseModel):
    """Response with GeneratedNarrative data."""

    narrative_id: UUID
    source_type: NarrativeSourceType
    source_id: UUID
    universe_id: UUID
    story_id: UUID
    style: NarrativeStyle
    text: str
    perspective: Optional[str] = None
    model_used: Optional[str] = None
    scene_ids_covered: List[UUID]
    word_count: int = Field(description="Word count of the text")
    is_edited_by_user: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class GeneratedNarrativeFilter(BaseModel):
    """Filter for listing generated narratives."""

    source_type: Optional[NarrativeSourceType] = None
    source_id: Optional[UUID] = None
    story_id: Optional[UUID] = None
    universe_id: Optional[UUID] = None
    style: Optional[NarrativeStyle] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class GeneratedNarrativeListResponse(BaseModel):
    """Response for list operations."""

    narratives: List[GeneratedNarrativeResponse]
    total: int
    limit: int
    offset: int
