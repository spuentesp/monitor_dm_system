"""
Pydantic schemas for structured roleplay error tracking.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) only.
CALLED BY: mongodb_tools.roleplay_errors, monitor_agents (Layer 2)

A RoleplayError is a single, append-only record of a failure that occurred
during a live play/roleplay session (full GM Play loop or light-RP character
conversation) — the play-loop analogue of IngestionJob.last_error, but
scoped as one document per event rather than one field on a parent job.
Sessions are open-ended (hours, many turns/scenes) and can accumulate many
errors, so a growing array on a narrative document (Scene/Story/Turn) would
hit the same unbounded-growth problem IngestionJob.failed_sections already
caps at 200 entries — a dedicated collection avoids that and makes
cross-session queries ("every memory_persist_not_found in the last 24h")
possible without a scatter query across every Scene document.

``llm_error_class`` is intentionally a plain string, not the
``monitor_agents.llm_errors.LLMErrorClass`` enum — Layer 1 must not import
Layer 2. Callers in monitor_agents pass ``LLMErrorClass.value`` when the
category is ``RoleplayErrorCategory.LLM``.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RoleplayErrorSource(StrEnum):
    """Which subsystem raised the error — the call-site identity, not a guess."""

    SCENE_LOOP = "scene_loop"
    GM_AGENT = "gm_agent"
    RESOLVER = "resolver"
    NARRATOR = "narrator"
    CANONKEEPER = "canonkeeper"
    PREPLAY = "preplay_support"
    CHARACTER_CONVERSATION = "character_conversation"


class RoleplayErrorCategory(StrEnum):
    """Finite set of failure categories the play loop records.

    Adding a new category means adding an enum member. Non-LLM members are
    chosen by call site / exception type only, never by matching free-text
    on the error message.
    """

    SCENE_BOOTSTRAP_FAILED = "scene_bootstrap_failed"
    MEMORY_PERSIST_NOT_FOUND = "memory_persist_not_found"
    NEO4J_SCHEMA_DRIFT = "neo4j_schema_drift"
    COMMIT_DISPATCHER_UNKNOWN_TYPE = "commit_dispatcher_unknown_type"
    CANONKEEPER_MISSING_UNIVERSE_ID = "canonkeeper_missing_universe_id"
    CANONKEEPER_WRITE_FAILED = "canonkeeper_write_failed"
    NARRATOR_PARSE_FAILED = "narrator_parse_failed"
    RESOLVER_CHECK_FAILED = "resolver_check_failed"
    GM_DECISION_FAILED = "gm_decision_failed"
    LLM = "llm"
    UNKNOWN = "unknown"


class RoleplayError(BaseModel):
    """Structured, append-only failure record for a play/roleplay session.

    One document per error event. Never updated after insert, and never
    read back and reconciled against a competing plain-string shape — this
    is the single representation, by design (see module docstring for why
    that matters: a two-shapes-for-one-field split caused a real production
    crash in the ingestion module's ``last_error`` handling).
    """

    error_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: RoleplayErrorSource
    category: RoleplayErrorCategory
    llm_error_class: str | None = Field(
        None,
        description="LLMErrorClass.value from monitor_agents.llm_errors, set only when category == LLM",
    )
    message: str
    detail: str | None = None
    fatal: bool = Field(default=False, description="Whether this error aborted the turn/action")
    # Correlation — optional since not every call site has all of these.
    universe_id: UUID | None = None
    story_id: UUID | None = None
    scene_id: UUID | None = None
    conversation_id: str | None = None
    turn_id: UUID | None = None
    entity_id: UUID | None = None


class RoleplayErrorResponse(BaseModel):
    """Response with a single RoleplayError record."""

    error_id: UUID
    occurred_at: datetime
    source: RoleplayErrorSource
    category: RoleplayErrorCategory
    llm_error_class: str | None = None
    message: str
    detail: str | None = None
    fatal: bool = False
    universe_id: UUID | None = None
    story_id: UUID | None = None
    scene_id: UUID | None = None
    conversation_id: str | None = None
    turn_id: UUID | None = None
    entity_id: UUID | None = None

    model_config = {"from_attributes": True}


class RoleplayErrorFilter(BaseModel):
    """Filter for listing roleplay errors."""

    source: RoleplayErrorSource | None = None
    category: RoleplayErrorCategory | None = None
    fatal: bool | None = None
    universe_id: UUID | None = None
    story_id: UUID | None = None
    scene_id: UUID | None = None
    conversation_id: str | None = None
    since: datetime | None = Field(None, description="Only errors at/after this timestamp")
    until: datetime | None = Field(None, description="Only errors at/before this timestamp")
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort_order: str = Field(
        default="desc",
        description="Sort by occurred_at: desc=newest first",
        pattern="^(asc|desc)$",
    )


class RoleplayErrorListResponse(BaseModel):
    """Response for list operations."""

    errors: list[RoleplayErrorResponse]
    total: int
    limit: int
    offset: int
