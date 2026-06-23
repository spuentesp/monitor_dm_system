"""
Pydantic schemas for GM Profile operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools.py

GMProfile is the narrative personality of the GM — separate from:
  - game_system     (mechanical rules — dice, stats, tracks)
  - source_profile  (extracted world knowledge from ingested docs)
  - session config  (play_mode, system_id, etc.)

A GMProfile contains what a good GM keeps behind the screen:
  - Tone tags   (voice register: grim, dramatic, whimsical, etc.)
  - Theme tags  (recurring motifs: corruption, redemption, isolation)
  - Style tags  (prose mechanics: terse, lyrical, second_person, etc.)
  - Concept tags (guiding principles: "the city owns you", "hope is earned")
  - Custom tone instructions (freeform text override)
  - Narrator constraints (what NOT to do — no gore, no romance, etc.)

Profiles are stored in MongoDB (gm_profiles collection) and referenced by
session.gm_profile_id. If no profile is set, the session falls back to the
legacy session_tone string (backward compatible).

Profile resolution priority:
  1. tone_instructions (custom override) — if present, USE THIS as the base
  2. tone_tags → lookup in Narrator._TONE_PROFILES → merge matched entries
  3. theme/style/concept_tags → always injected as additional narrator context
  4. source_profile hints (from ingestion) → merged at the end
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# GM PROFILE CRUD SCHEMAS
# =============================================================================


class GMProfileCreate(BaseModel):
    """Request to create a GM Profile."""

    profile_id: Optional[UUID] = Field(None, description="Optional explicit Profile ID")
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Human-readable profile name (e.g. 'Grim Noir Detective')",
    )
    description: str = Field(
        default="",
        max_length=1000,
        description="Short description of this GM personality",
    )

    # --- Tag dimensions (all optional, all composable) ---

    tone_tags: List[str] = Field(
        default_factory=list,
        description=(
            "Voice register tags. Merged with built-in tone profiles. "
            "Examples: grim, dramatic, noir, lyrical, clinical, whimsical, "
            "baroque, minimalist, conversational"
        ),
    )
    theme_tags: List[str] = Field(
        default_factory=list,
        description=(
            "Recurring narrative motifs injected into every scene. "
            "Examples: corruption, redemption, isolation, coming_of_age, "
            "urban_decay, cosmic_indifference, found_family"
        ),
    )
    style_tags: List[str] = Field(
        default_factory=list,
        description=(
            "Prose mechanics — how the narrator writes. "
            "Examples: terse_prose, long_sentences, second_person, "
            "stream_of_consciousness, present_tense, past_tense, "
            "cold_sensory, warm_sensory, unreliable_narrator"
        ),
    )
    concept_tags: List[str] = Field(
        default_factory=list,
        description=(
            "Guiding principles — idea-phrases that shape GM decisions. "
            "Examples: the_city_owns_you, violence_has_consequences, "
            "hope_is_earned, everyone_has_a_price, knowledge_costs"
        ),
    )

    # --- Freeform overrides ---

    tone_instructions: Optional[str] = Field(
        None,
        max_length=2000,
        description=(
            "Custom tone override. If present, this replaces the built-in tone "
            "profile as the base narrator instruction. Tags are still appended."
        ),
    )
    narrator_constraints: Optional[str] = Field(
        None,
        max_length=1000,
        description=(
            "What the narrator should NOT do. "
            "Examples: 'no graphic violence', 'no romance subplots', "
            "'never break the fourth wall', 'no deus ex machina'"
        ),
    )

    # --- Extensible Tone System ---

    tone_library_id: Optional[UUID] = Field(
        None,
        description="ID of the ToneLibrary to use for extensible tone resolution.",
    )
    merge_with_default_library: bool = Field(
        default=True,
        description="If true, merge specific library with the default system library.",
    )

    # --- Scope ---

    universe_id: Optional[UUID] = Field(
        None,
        description="If set, profile is only visible within this universe. "
        "If null, profile is global (available everywhere).",
    )
    game_system_id: Optional[UUID] = Field(
        None,
        description="If set, profile is suggested when this game system is active.",
    )

    # --- Meta ---

    is_builtin: bool = Field(
        default=False,
        description="Built-in profiles are seed data, protected from deletion.",
    )


class GMProfileUpdate(BaseModel):
    """Request to update a GM Profile. All fields optional (partial update)."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    tone_tags: Optional[List[str]] = None
    theme_tags: Optional[List[str]] = None
    style_tags: Optional[List[str]] = None
    concept_tags: Optional[List[str]] = None
    tone_instructions: Optional[str] = Field(None, max_length=2000)
    narrator_constraints: Optional[str] = Field(None, max_length=1000)
    tone_library_id: Optional[UUID] = None
    merge_with_default_library: Optional[bool] = None
    universe_id: Optional[UUID] = None
    game_system_id: Optional[UUID] = None


class GMProfileResponse(BaseModel):
    """Response with GM Profile data."""

    profile_id: UUID
    name: str
    description: str
    tone_tags: List[str]
    theme_tags: List[str]
    style_tags: List[str]
    concept_tags: List[str]
    tone_instructions: Optional[str] = None
    narrator_constraints: Optional[str] = None
    tone_library_id: Optional[UUID] = None
    merge_with_default_library: bool = True
    universe_id: Optional[UUID] = None
    game_system_id: Optional[UUID] = None
    is_builtin: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class GMProfileFilter(BaseModel):
    """Filter for listing GM profiles."""

    universe_id: Optional[UUID] = None
    game_system_id: Optional[UUID] = None
    tone_tag: Optional[str] = Field(
        None,
        description="Filter to profiles containing this tone tag",
    )
    is_builtin: Optional[bool] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class GMProfileListResponse(BaseModel):
    """Response for list operations."""

    profiles: List[GMProfileResponse]
    total: int
    limit: int
    offset: int
