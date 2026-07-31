"""
Lorebook schema — keyword-triggered memory injection entries for characters.

Each entry belongs to a character (or a universe) and has trigger keywords.
When any keyword appears in player input, the entry's content is injected
into the context passed to the DSPy module on that turn.

Use-case: Risuai-style lorebook where "dragon" → injects lore entry about dragons.

This schema also supports SillyTavern / character.ai lorebook semantics:
secondary keywords, selective logic, constant entries, probability, insertion
position/depth/order, scan-depth, token budgets, timing (sticky/cooldown/delay),
inclusion groups, and round-trip import/export of ST World Info JSON.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SelectiveLogic(IntEnum):
    """SillyTavern selective keyword logic modes.

    0 - AND ANY: at least one secondary keyword must match.
    1 - NOT ALL: none of the secondary keywords may match.
    2 - NOT ANY: at least one secondary keyword must NOT match.
    3 - AND ALL: all secondary keywords must match.
    """

    AND_ANY = 0
    NOT_ALL = 1
    NOT_ANY = 2
    AND_ALL = 3


class LorebookPosition(IntEnum):
    """SillyTavern insertion position for an entry's content."""

    BEFORE_CHAR = 0
    AFTER_CHAR = 1
    AN_TOP = 2
    AN_BOTTOM = 3
    AT_DEPTH = 4


class LorebookEntry(BaseModel):
    """A single lorebook entry for a character or universe."""

    model_config = ConfigDict(use_enum_values=True)

    id: str
    character_id: str = Field(
        description="ID of the character this entry belongs to. Use 'universe:<universe_id>' for universe-wide entries."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Primary trigger phrases. When ANY keyword appears in user input, "
            "this entry becomes a candidate. Case-insensitive by default. "
            "Example: ['dragon', 'wyrm', 'hoard', 'Smaug']"
        ),
    )
    secondary_keywords: list[str] = Field(
        default_factory=list,
        description="SillyTavern secondary keywords; used when selective=True.",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="The lore text injected when a keyword matches.",
    )
    comment: str = Field(
        default="",
        description="SillyTavern entry title / memo. Not injected into prompts.",
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
    order: int = Field(
        default=100,
        ge=0,
        le=1000,
        description="SillyTavern insertion order; lower numbers are injected first within a position group.",
    )
    position: int = Field(
        default=LorebookPosition.AFTER_CHAR,
        ge=0,
        le=4,
        description=(
            "SillyTavern position: 0=before_char, 1=after_char, 2=AN_top, 3=AN_bottom, 4=@depth. "
            "In MONITOR this groups entries into 'before' vs 'after' profile-context blocks."
        ),
    )
    depth: int = Field(
        default=4,
        ge=0,
        le=100,
        description="For position=4, how many turns back the entry should be inserted (@D depth).",
    )
    is_active: bool = Field(default=True)
    constant: bool = Field(
        default=False,
        description="If True, the entry is always injected (subject to probability/timing/budget).",
    )
    selective: bool = Field(
        default=False,
        description="If True, secondary_keywords must also satisfy selective_logic for the entry to trigger.",
    )
    selective_logic: int = Field(
        default=SelectiveLogic.AND_ANY,
        ge=0,
        le=3,
        description="SillyTavern selective logic mode (0=AND_ANY, 1=NOT_ALL, 2=NOT_ANY, 3=AND_ALL).",
    )
    probability: int = Field(
        default=100,
        ge=0,
        le=100,
        description="Percent chance (0-100) the entry triggers when it matches keywords.",
    )
    use_probability: bool = Field(default=True)
    case_sensitive: bool | None = Field(
        default=None,
        description="Override scan-level case sensitivity. None = inherit from scan config.",
    )
    match_whole_words: bool | None = Field(
        default=None,
        description="Override scan-level whole-word matching. None = inherit from scan config.",
    )
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
    group: str = Field(
        default="",
        description="SillyTavern inclusion group name. Members of the same group compete; only one is injected.",
    )
    group_override: bool = Field(
        default=False,
        description="If True, this entry ignores group competition and is always eligible.",
    )
    sticky: int = Field(
        default=0,
        ge=0,
        le=100,
        description="SillyTavern sticky: after triggering, keep injecting for N more turns without keyword match.",
    )
    cooldown: int = Field(
        default=0,
        ge=0,
        le=100,
        description="SillyTavern cooldown: after sticky expires, cannot re-trigger for N turns.",
    )
    delay: int = Field(
        default=0,
        ge=0,
        le=100,
        description="SillyTavern delay: cannot trigger until at least N turns have passed since entry creation.",
    )
    exclude_recursion: bool = Field(
        default=False,
        description="If True, this entry's content is excluded from recursive keyword scans.",
    )
    prevent_recursion: bool = Field(
        default=False,
        description="If True, matches from this entry do not initiate recursive scans of other entries.",
    )
    vectorized: bool = Field(
        default=False,
        description="Reserved for SillyTavern vectorized (embedding) triggers. Currently stored for round-trip; falls back to keyword matching at runtime.",
    )
    trigger_count: int = Field(
        default=0,
        description="How many times this entry has been matched and injected.",
    )
    last_triggered: str | None = Field(
        default=None,
        description="ISO timestamp of last trigger. Populated by inject_lorebook_entries.",
    )
    last_triggered_turn_index: int | None = Field(
        default=None,
        description="Turn index of last trigger; used for sticky/cooldown/delay calculations.",
    )
    created_turn_index: int | None = Field(
        default=None,
        description="Turn index when the entry was created; used for delay calculations.",
    )
    st_extensions: dict[str, Any] = Field(
        default_factory=dict,
        description="Unmapped SillyTavern fields preserved for lossless round-trip export.",
    )
    created_at: str


class LorebookEntryCreate(BaseModel):
    """Payload for creating a new lorebook entry."""

    keywords: list[str] = Field(
        default_factory=list,
        description="Trigger keywords. If empty and auto_generate_keywords=True, "
        "the system will auto-extract keywords from content.",
    )
    secondary_keywords: list[str] = Field(default_factory=list)
    content: str = Field(..., min_length=1, description="The lore content.")
    comment: str = Field(default="")
    priority: int = Field(default=0, ge=0, le=100)
    order: int = Field(default=100, ge=0, le=1000)
    position: int = Field(default=LorebookPosition.AFTER_CHAR, ge=0, le=4)
    depth: int = Field(default=4, ge=0, le=100)
    is_active: bool = True
    constant: bool = False
    selective: bool = False
    selective_logic: int = Field(default=SelectiveLogic.AND_ANY, ge=0, le=3)
    probability: int = Field(default=100, ge=0, le=100)
    use_probability: bool = True
    case_sensitive: bool | None = None
    match_whole_words: bool | None = None
    tags: list[str] = Field(default_factory=list)
    scene_filter: str | None = None
    group: str = Field(default="")
    group_override: bool = False
    sticky: int = Field(default=0, ge=0, le=100)
    cooldown: int = Field(default=0, ge=0, le=100)
    delay: int = Field(default=0, ge=0, le=100)
    exclude_recursion: bool = False
    prevent_recursion: bool = False
    vectorized: bool = False
    st_extensions: dict[str, Any] = Field(
        default_factory=dict,
        description="Unmapped SillyTavern fields preserved for lossless round-trip export.",
    )
    auto_generate_keywords: bool = Field(
        default=False,
        description="If True and keywords is empty, auto-extract keywords via DSPy.",
    )


class LorebookEntryUpdate(BaseModel):
    """Payload for updating an existing lorebook entry."""

    keywords: list[str] | None = None
    secondary_keywords: list[str] | None = None
    content: str | None = None
    comment: str | None = None
    priority: int | None = None
    order: int | None = None
    position: int | None = None
    depth: int | None = None
    is_active: bool | None = None
    constant: bool | None = None
    selective: bool | None = None
    selective_logic: int | None = None
    probability: int | None = None
    use_probability: bool | None = None
    case_sensitive: bool | None = None
    match_whole_words: bool | None = None
    tags: list[str] | None = None
    scene_filter: str | None = None
    group: str | None = None
    group_override: bool | None = None
    sticky: int | None = None
    cooldown: int | None = None
    delay: int | None = None
    exclude_recursion: bool | None = None
    prevent_recursion: bool | None = None
    vectorized: bool | None = None


class LorebookEntryDraft(BaseModel):
    """A proposed lorebook entry — used by AI ingestion pipelines."""

    keywords: list[str]
    secondary_keywords: list[str] = Field(default_factory=list)
    content: str
    priority: int = 50
    order: int = 100
    tags: list[str] = Field(default_factory=list)
    scene_filter: str | None = None
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="AI confidence score for this proposal. Low confidence entries should be reviewed before saving.",
    )


class LorebookScanConfig(BaseModel):
    """Per-character SillyTavern-style scan settings."""

    scan_depth: int = Field(default=2, ge=0, le=100, description="How many recent turns to scan in addition to the current input.")
    token_budget: int = Field(default=500, ge=0, le=10000, description="Approximate token budget for injected lore content.")
    recursive_scanning: bool = Field(default=True, description="Recursively scan triggered entry contents for further keywords.")
    case_sensitive: bool = Field(default=False)
    match_whole_words: bool = Field(default=False)
    include_names: bool = Field(default=True, description="Include speaker names/labels when scanning history.")


class LorebookScanResult(BaseModel):
    """Output of a lorebook scan, grouped by ST insertion position."""

    before: list[str] = Field(default_factory=list, description="Contents for position=before_char (0).")
    after: list[str] = Field(default_factory=list, description="Contents for positions after_char (1), AN_top (2), AN_bottom (3).")
    depth: list[str] = Field(default_factory=list, description="Contents for position=@depth (4).")
    triggered_entry_ids: list[str] = Field(default_factory=list)

    def all_contents(self) -> list[str]:
        return self.before + self.after + self.depth


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
