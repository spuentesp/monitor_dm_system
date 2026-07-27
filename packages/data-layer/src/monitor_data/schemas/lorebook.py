"""
Lorebook schema — keyword-triggered memory injection entries for characters.

Each entry belongs to a character (or a universe) and has trigger keywords.
When any keyword appears in player input, the entry's content is injected
into the context passed to the DSPy module on that turn.

Use-case: Risuai-style lorebook where "dragon" → injects lore entry about dragons.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LorebookEntry(BaseModel):
    """A single lorebook entry for a character or universe."""

    id: str
    character_id: str = Field(
        description="ID of the character this entry belongs to. Use 'universe:<universe_id>' for universe-wide entries."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Trigger phrases. When ANY keyword appears in user input, "
            "this entry's content is injected into context. Case-insensitive. "
            "Example: ['dragon', 'wyrm', 'hoard', 'Smaug']"
        ),
    )
    content: str = Field(
        ...,
        min_length=1,
        description="The lore text injected when a keyword matches.",
    )
    priority: int = Field(
        default=0,
        ge=0,
        le=100,
        description=(
            "Higher priority entries are injected first. "
            "Use 80-100 for essential world facts, 50-79 for important lore, "
            "0-49 for optional flavor. Entries with same priority: ordered by created_at."
        ),
    )
    is_active: bool = Field(default=True)
    tags: list[str] = Field(
        default_factory=list,
        description="Scene/topic tags for context-aware injection. "
        "Example: ['castle', 'combat', 'royalty']. "
        "If scene_filter is set, only inject in matching scenes.",
    )
    scene_filter: str | None = Field(
        default=None,
        description="Scope this entry to a specific scene type. "
        "Example: 'combat', 'social', 'exploration'. None = always active.",
    )
    trigger_count: int = Field(
        default=0,
        description="How many times this entry has been matched and injected.",
    )
    last_triggered: str | None = Field(
        default=None,
        description="ISO timestamp of last trigger. Populated by inject_lorebook_entries.",
    )
    created_at: str


class LorebookEntryCreate(BaseModel):
    """Payload for creating a new lorebook entry."""

    keywords: list[str] = Field(
        default_factory=list,
        description="Trigger keywords. If empty and auto_generate_keywords=True, "
        "the system will auto-extract keywords from content.",
    )
    content: str = Field(..., min_length=1, description="The lore content.")
    priority: int = Field(default=0, ge=0, le=100)
    is_active: bool = True
    tags: list[str] = Field(default_factory=list)
    scene_filter: str | None = None
    auto_generate_keywords: bool = Field(
        default=False,
        description="If True and keywords is empty, auto-extract keywords via DSPy.",
    )


class LorebookEntryUpdate(BaseModel):
    """Payload for updating an existing lorebook entry."""

    keywords: list[str] | None = None
    content: str | None = None
    priority: int | None = None
    is_active: bool | None = None
    tags: list[str] | None = None
    scene_filter: str | None = None


class LorebookEntryDraft(BaseModel):
    """A proposed lorebook entry — used by AI ingestion pipelines."""

    keywords: list[str]
    content: str
    priority: int = 50
    tags: list[str] = Field(default_factory=list)
    scene_filter: str | None = None
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="AI confidence score for this proposal. Low confidence entries should be reviewed before saving.",
    )


class LorebookIngestRequest(BaseModel):
    """Payload for bulk-ingesting a document into lorebook entries."""

    source: str = Field(..., description="Document name or source.")
    content: str = Field(..., min_length=10, description="Full text to ingest.")
    chunk_size: int = Field(
        default=2000,
        ge=500,
        le=10000,
        description="Max characters per chunk for analysis.",
    )
    character_id: str = Field(..., description="Target character_id.")
    auto_keywords: bool = Field(
        default=True,
        description="Auto-extract keywords from each chunk.",
    )
    priority_hint: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Base priority for auto-generated entries.",
    )
    tags: list[str] = Field(default_factory=list)
