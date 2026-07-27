"""
Pydantic schemas for PromptCollection operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) only
CALLED BY: mongodb_tools.prompt_collections

KEY DESIGN: A PromptCollection is a curated, authorable set of prompts /
interview questions used to drive story onboarding (Session Zero) and, later,
character creation. It turns the previously hard-coded / LLM-only Session Zero
interview into configurable *data* that a human curates in the Forge UI.

A collection has a `category` ("session_zero" | "character_creation" | ...),
an optional binding to a game system and/or universe, and an ordered list of
`PromptEntry` items. At runtime the agents layer resolves the best-matching
collection for a session and feeds its entries into the interview loop as
authored questions (falling back to the LLM when the authored queue is
exhausted).

NOTE ON `category`: the agents layer owns the canonical `QuestionCategory`
enum (monitor_agents.session_zero.QuestionCategory). The data layer must not
import from Layer 2, so entry categories are stored as plain strings here.
Canonical values: name, origin, bond, fear, motivation, conflict, secret,
loss, appearance, skill, faith, relationship, custom, campaign_intent.
The loop maps them back leniently via `_parse_category`.
"""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

# =============================================================================
# PROMPT ENTRY (sub-document)
# =============================================================================


class PromptEntry(BaseModel):
    """A single authored prompt / interview question within a collection."""

    entry_id: UUID = Field(default_factory=uuid4)
    order: int = Field(default=0, ge=0, description="Position in the interview (0-based)")
    category: str = Field(
        default="custom",
        max_length=50,
        description=(
            "What aspect of the character this question explores. See module "
            "docstring for canonical values (mirrors QuestionCategory)."
        ),
    )
    question_text: str = Field(
        max_length=2000,
        description="The in-fiction question the GM asks the player.",
    )
    answer_options: list[str] = Field(
        default_factory=list,
        description="Optional pre-authored answer choices ('configurable answers').",
    )
    guidance: str | None = Field(
        default=None,
        max_length=2000,
        description="Curator note / guidance for how this question should be used.",
    )
    is_final: bool = Field(
        default=False,
        description="True if this is the last authored question before summarizing.",
    )


# =============================================================================
# PROMPT COLLECTION CRUD SCHEMAS
# =============================================================================


class PromptCollectionCreate(BaseModel):
    """Request to create a PromptCollection."""

    name: str = Field(max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: str = Field(
        default="session_zero",
        max_length=100,
        description="Collection purpose: session_zero | character_creation | ...",
    )
    system_id: UUID | None = Field(
        default=None,
        description="Optional binding to a game_systems system_id.",
    )
    universe_id: UUID | None = Field(
        default=None,
        description="Optional binding to a specific universe.",
    )
    tags: list[str] = Field(default_factory=list)
    entries: list[PromptEntry] = Field(default_factory=list)
    version: str | None = Field(default=None, max_length=50)
    is_builtin: bool = Field(default=False)
    hand_authored: bool = Field(default=True)


class PromptCollectionUpdate(BaseModel):
    """Request to update a PromptCollection. All fields optional."""

    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    category: str | None = Field(default=None, max_length=100)
    system_id: UUID | None = None
    universe_id: UUID | None = None
    tags: list[str] | None = None
    entries: list[PromptEntry] | None = None
    version: str | None = Field(default=None, max_length=50)
    change_description: str | None = Field(
        default=None,
        max_length=500,
        description="Reason for update (reserved for future history log).",
    )


class PromptCollectionResponse(BaseModel):
    """Response with PromptCollection data."""

    collection_id: UUID
    name: str
    description: str | None = None
    category: str
    system_id: UUID | None = None
    universe_id: UUID | None = None
    tags: list[str]
    entries: list[PromptEntry]
    version: str | None = None
    is_builtin: bool
    hand_authored: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class PromptCollectionFilter(BaseModel):
    """Filter for listing prompt collections."""

    category: str | None = Field(default=None, description="e.g. 'session_zero'")
    system_id: UUID | None = None
    universe_id: UUID | None = None
    tag: str | None = Field(default=None, description="Match a single tag")
    include_builtin: bool = Field(default=True)
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class PromptCollectionListResponse(BaseModel):
    """Response for list operations."""

    collections: list[PromptCollectionResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# VERSIONING (immutable published snapshots)
# =============================================================================


class PromptCollectionPublish(BaseModel):
    """Request to publish an immutable snapshot of a prompt collection."""

    version: str | None = Field(
        default=None,
        max_length=50,
        description="Version label; auto-assigned (v1, v2, …) if omitted.",
    )
    note: str | None = Field(default=None, max_length=500, description="Optional changelog note.")


class PromptCollectionVersionResponse(BaseModel):
    """A published, immutable snapshot of a prompt collection."""

    version_id: UUID
    collection_id: UUID
    version: str
    name: str
    description: str | None = None
    category: str
    tags: list[str]
    entries: list[PromptEntry]
    note: str | None = None
    published_at: datetime

    model_config = {"from_attributes": True}


class PromptCollectionVersionListResponse(BaseModel):
    """Response for listing a collection's published versions (newest first)."""

    versions: list[PromptCollectionVersionResponse]
    total: int
