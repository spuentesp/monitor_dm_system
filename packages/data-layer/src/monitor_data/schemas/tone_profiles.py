"""
Pydantic schemas for Tone Profile operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools.py

ToneProfile represents a reusable narrative style definition that can be
shared across universes and GM profiles. Unlike the old BUILTIN_TONE_PROFILES
(hardcoded in Python), ToneProfiles are data-driven and stored in MongoDB.

Key differences from BUILTIN_TONE_PROFILES:
- Stored in MongoDB (dynamic, not hardcoded)
- Can be created by users (not just system)
- Can be packaged with Packs (system-specific tones)
- Support multiple trigger tags (not just single key)
- Include example outputs for LLM training
- Have metadata (category, language, pack_id)

Usage:
1. User creates a ToneProfile (or Pack includes one)
2. GMProfile references a ToneLibrary (collection of ToneProfiles)
3. ToneResolver loads ToneLibrary and matches tone_tags to ToneProfiles
4. Narrator receives merged instruction from matched ToneProfiles
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# TONE PROFILE CRUD SCHEMAS
# =============================================================================


class ToneProfileCreate(BaseModel):
    """Request to create a Tone Profile."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Unique name of the tone (e.g., 'grim_noir')",
    )
    description: str = Field(
        ...,
        max_length=500,
        description="Short description of this tone",
    )

    # Core definition
    instruction: str = Field(
        ...,
        max_length=2000,
        description=(
            "Complete narrator instruction for this tone. "
            "This replaces BUILTIN_TONE_PROFILES[key] from the old system."
        ),
    )

    # Trigger mechanism
    trigger_tags: List[str] = Field(
        default_factory=list,
        description=(
            "Tags that trigger this tone. "
            "When a GMProfile has these tone_tags, this profile is matched. "
            "Examples: ['grim', 'noir'] for a profile named 'grim_noir'"
        ),
    )

    # Metadata
    category: str = Field(
        default="narrative",
        max_length=50,
        description=(
            "Category of the tone: narrative, genre, mood, pacing. "
            "Helps with organization and UI grouping."
        ),
    )
    language: str = Field(
        default="en",
        max_length=10,
        description="Language code for this tone (e.g., 'en', 'es', 'fr')",
    )

    # Scope
    pack_id: Optional[UUID] = Field(
        None,
        description=(
            "If from a Pack, ID of the Pack. None = global built-in or user-created profile."
        ),
    )
    is_builtin: bool = Field(
        default=False,
        description="Built-in tones cannot be deleted by users.",
    )

    # Examples
    example_output: Optional[str] = Field(
        None,
        max_length=1000,
        description="Example narrative generated with this tone (for LLM training)",
    )


class ToneProfileUpdate(BaseModel):
    """Request to update a Tone Profile. All fields optional (partial update)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=500)
    instruction: Optional[str] = Field(None, max_length=2000)
    trigger_tags: Optional[List[str]] = None
    category: Optional[str] = Field(None, max_length=50)
    language: Optional[str] = Field(None, max_length=10)
    example_output: Optional[str] = Field(None, max_length=1000)


class ToneProfileResponse(BaseModel):
    """ToneProfile with metadata for API responses."""

    profile_id: UUID
    name: str
    description: str
    instruction: str
    trigger_tags: List[str]
    category: str
    language: str
    pack_id: Optional[UUID]
    is_builtin: bool
    example_output: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ToneProfileListResponse(BaseModel):
    """Response for listing ToneProfiles."""

    profiles: List[ToneProfileResponse]
    total: int
    page: int
    page_size: int
