"""
Pydantic schemas for Tone Library operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools.py

ToneLibrary represents a collection of ToneProfiles that can be used together.
Libraries provide a way to:
- Group related ToneProfiles (e.g., all tones for Cyberpunk 2020)
- Prioritize tone resolution (higher priority libraries are checked first)
- Provide fallback behavior (is_default libraries are used when no specific library is set)
- Package tones with a Pack (system-specific libraries)

Usage:
1. Pack creates a ToneLibrary with tone profiles for that system
2. GMProfile references a tone_library_id
3. ToneResolver loads the library and matches tone_tags
4. If merge_with_default_library=True, also loads default library
5. Profiles are merged with priority (higher priority first)
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# TONE LIBRARY CRUD SCHEMAS
# =============================================================================


class ToneLibraryCreate(BaseModel):
    """Request to create a Tone Library."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name of the library (e.g., 'Cyberpunk 2020')",
    )
    description: str = Field(
        default="",
        max_length=1000,
        description="Description of this library and its tones",
    )

    # Tone profiles in this library
    tone_profile_ids: list[UUID] = Field(
        default_factory=list,
        description="IDs of ToneProfiles included in this library",
    )

    # Scope
    pack_id: UUID | None = Field(
        None,
        description=("If from a Pack, ID of the Pack. None = global library (available to all universes)."),
    )
    universe_id: UUID | None = Field(
        None,
        description=(
            "If set, library is only visible within this universe. If None and pack_id is None, library is global."
        ),
    )

    # Priority (for merging multiple libraries)
    priority: int = Field(
        default=100,
        ge=0,
        le=1000,
        description=(
            "Priority when merging multiple libraries. "
            "Higher values are checked first. "
            "Default library typically has priority 100. "
            "Pack-specific libraries often have priority 150+."
        ),
    )

    # Default behavior
    is_default: bool = Field(
        default=False,
        description=(
            "If True, this library is used as a fallback when no specific "
            "library is set. Only one default library should exist globally."
        ),
    )


class ToneLibraryUpdate(BaseModel):
    """Request to update a Tone Library. All fields optional (partial update)."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    tone_profile_ids: list[UUID] | None = None
    universe_id: UUID | None = None
    priority: int | None = Field(None, ge=0, le=1000)
    is_default: bool | None = None


class ToneLibraryResponse(BaseModel):
    """ToneLibrary with metadata for API responses."""

    library_id: UUID
    name: str
    description: str
    tone_profile_ids: list[UUID]
    pack_id: UUID | None
    universe_id: UUID | None
    priority: int
    is_default: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ToneLibraryListResponse(BaseModel):
    """Response for listing ToneLibraries."""

    libraries: list[ToneLibraryResponse]
    total: int
    page: int
    page_size: int
