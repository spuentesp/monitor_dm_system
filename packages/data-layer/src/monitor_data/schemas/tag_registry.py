"""
Pydantic schemas for Tag Registry operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum)
CALLED BY: mongodb_tools.py

TagRegistry provides a taxonomy of valid tags in the system. It enables:
- Validation of user-provided tags
- Tag suggestions and autocomplete
- Synonym resolution (e.g., 'dark' → 'grim')
- Tag categorization (tone, theme, style, concept)
- Documentation of what each tag means

Tags are used in:
- GMProfile.tone_tags (narrative style)
- GMProfile.theme_tags (recurring motifs)
- GMProfile.style_tags (prose mechanics)
- GMProfile.concept_tags (guiding principles)
- ToneProfile.trigger_tags (what activates a tone)

Without TagRegistry, tags are freeform strings. With TagRegistry, the system
can provide validation, suggestions, and documentation.

Usage:
1. System creates built-in TagDefinitions on startup
2. Packs can add their own tags via TagDefinitions
3. UI uses TagRegistry for autocomplete and validation
4. ToneResolver uses synonyms to match user tags to canonical tags
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# ENUMS
# =============================================================================


class TagCategory(str, Enum):
    """Category of a tag."""

    TONE = "tone"
    """Narrative style: grim, dramatic, whimsical, noir, lyrical, etc."""

    THEME = "theme"
    """Recurring motifs: corruption, redemption, isolation, urban_decay, etc."""

    STYLE = "style"
    """Prose mechanics: terse, lyrical, second_person, stream_of_consciousness, etc."""

    CONCEPT = "concept"
    """Guiding principles: the_city_owns_you, hope_is_earned, etc."""


# =============================================================================
# TAG DEFINITION CRUD SCHEMAS
# =============================================================================


class TagDefinitionCreate(BaseModel):
    """Request to create a Tag Definition."""

    tag: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Canonical tag name (lowercase, underscore separated)",
    )
    category: TagCategory = Field(
        ...,
        description="Category of the tag (tone, theme, style, concept)",
    )

    # Validation and normalization
    synonyms: List[str] = Field(
        default_factory=list,
        description=(
            "Accepted variants that map to this canonical tag. "
            "Example: 'grim' → ['dark', 'bleak', 'gritty']. "
            "When user provides 'dark', system normalizes to 'grim'."
        ),
    )

    # Documentation
    description: str = Field(
        default="",
        max_length=500,
        description="What this tag represents and when to use it",
    )

    # Cross-references
    example_tones: List[UUID] = Field(
        default_factory=list,
        description="IDs of ToneProfiles that use this tag in their trigger_tags",
    )

    # Scope
    pack_id: Optional[UUID] = Field(
        None,
        description="If from a Pack, ID of the Pack. None = global built-in.",
    )
    is_builtin: bool = Field(
        default=False,
        description="Built-in tags cannot be deleted by users.",
    )


class TagDefinitionUpdate(BaseModel):
    """Request to update a Tag Definition. All fields optional (partial update)."""

    synonyms: Optional[List[str]] = None
    description: Optional[str] = Field(None, max_length=500)
    example_tones: Optional[List[UUID]] = None


class TagDefinitionResponse(BaseModel):
    """TagDefinition with metadata for API responses."""

    tag: str
    category: TagCategory
    synonyms: List[str]
    description: str
    example_tones: List[UUID]
    pack_id: Optional[UUID]
    is_builtin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TagDefinitionListResponse(BaseModel):
    """Response for listing TagDefinitions."""

    tags: List[TagDefinitionResponse]
    total: int
    page: int
    page_size: int


class TagSuggestionRequest(BaseModel):
    """Request for tag suggestions (autocomplete)."""

    partial: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Partial tag to search for (e.g., 'grim' → ['grim', 'grim_noir'])",
    )
    category: Optional[TagCategory] = Field(
        None,
        description="Filter by category (if provided)",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of suggestions to return",
    )


class TagSuggestionResponse(BaseModel):
    """Response for tag suggestions."""

    suggestions: List[TagDefinitionResponse]
    partial: str
    total_found: int
