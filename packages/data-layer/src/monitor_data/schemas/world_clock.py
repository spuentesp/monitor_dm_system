"""
Pydantic schemas for the per-story world clock (in-fiction time, CF-11).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime)
CALLED BY: mongodb_tools/world_clock.py, routers/gm_tools.py, monitor_agents/gm_table.py

The world clock is one document per (universe, story): a sortable epoch
(``current_at``, ISO-8601 internally) plus a free-form ``display`` string for
the surface the GM reads. Time only moves forward — ``mongodb_advance_world_clock``
enforces monotonicity, so advancing is idempotent (same target → no-op) and
backwards moves are refused; every real advance appends an audit record.

Deadlines live on the clock document (story-scoped MongoDB scratch state —
no canon, no Neo4j writes). Their status is computed against the clock's
current time on every read: ``upcoming`` (due date still ahead), ``due``
(due date reached today) or ``overdue`` (due date passed).
"""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator

DeadlineStatus = Literal["upcoming", "due", "overdue"]

# Audit log cap: one advance record per GM action; keep the doc bounded.
MAX_ADVANCE_RECORDS = 50

# Relative-delta grammar: "+3 days", "2 hours", "+30 minutes" (sign optional,
# a leading "-" is rejected — see parse_time_delta).
_DELTA_UNITS = {
    "second": "seconds",
    "seconds": "seconds",
    "minute": "minutes",
    "minutes": "minutes",
    "hour": "hours",
    "hours": "hours",
    "day": "days",
    "days": "days",
    "week": "weeks",
    "weeks": "weeks",
}


# =============================================================================
# DEADLINES
# =============================================================================


class WorldClockDeadline(BaseModel):
    """One time-sensitive deadline on the story's clock (stored form)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str = Field(min_length=1, max_length=300)
    due_at: datetime
    notes: str = Field(default="", max_length=2000)


class WorldClockDeadlineView(BaseModel):
    """A deadline with its status computed against the current world time."""

    id: str
    title: str
    due_at: datetime
    notes: str = ""
    status: DeadlineStatus = "upcoming"


def deadline_status(due_at: datetime, current_at: datetime) -> DeadlineStatus:
    """Deterministic deadline status at ``current_at`` (date-level compare).

    A GM thinks in days: a deadline is *due* when its date arrives and
    *overdue* once that date has passed; time-of-day on the due date keeps it
    ``due``.
    """
    due = due_at if due_at.tzinfo else due_at.replace(tzinfo=UTC)
    current = current_at if current_at.tzinfo else current_at.replace(tzinfo=UTC)
    if current.date() > due.date():
        return "overdue"
    if current.date() == due.date():
        return "due"
    return "upcoming"


def view_deadline(deadline: WorldClockDeadline, current_at: datetime) -> WorldClockDeadlineView:
    """Project a stored deadline into its read view at ``current_at``."""
    return WorldClockDeadlineView(
        id=deadline.id,
        title=deadline.title,
        due_at=deadline.due_at,
        notes=deadline.notes,
        status=deadline_status(deadline.due_at, current_at),
    )


# =============================================================================
# CLOCK
# =============================================================================


class ClockAdvanceRecord(BaseModel):
    """One entry in the clock's append-only advance audit log (CF-2 timeline)."""

    from_at: datetime | None = Field(default=None, description="World time before the advance; None on first set")
    to_at: datetime
    delta: str = Field(description="The request as the GM wrote it ('+3 days') or an ISO target")
    advanced_at: datetime = Field(description="Real-world timestamp of the advance action")


class WorldClockResponse(BaseModel):
    """The story's world clock with deadlines/statuses and the advance log."""

    universe_id: UUID
    story_id: UUID
    current_at: datetime
    display: str = Field(default="", description="Display string; ISO-8601 of current_at unless overridden")
    deadlines: list[WorldClockDeadlineView] = Field(default_factory=list)
    advances: list[ClockAdvanceRecord] = Field(default_factory=list)
    offscreen_summary: str = Field(
        default="",
        description="The NPC off-screen summary generated for the last real advance (CF-7 prep)",
    )
    offscreen_summary_at: datetime | None = None
    updated_at: datetime


class WorldClockQuery(BaseModel):
    """Lookup key for clock tools called over MCP."""

    universe_id: UUID
    story_id: UUID


def parse_time_delta(delta: str) -> timedelta:
    """Parse a GM-written relative advance ('+3 days', '2 hours').

    Raises ``ValueError`` on anything else: a leading '-' is rejected
    (the clock never moves backwards) and only second/minute/hour/day/week
    units are recognized — complex calendar math is out of scope for v1.
    """
    text = delta.strip().lower()
    if not text:
        raise ValueError("Empty time delta — write something like '+3 days' or '+2 hours'")
    if text.startswith("-") or text.lstrip("+").startswith("-"):
        raise ValueError(f"Time cannot move backwards: {delta!r}")
    cleaned = text.lstrip("+").strip()
    parts = cleaned.split()
    if len(parts) != 2 or not parts[0].isdigit():
        raise ValueError(f"Unrecognized time delta: {delta!r} — expected e.g. '+3 days' or '+2 hours'")
    amount = int(parts[0])
    unit = parts[1]
    if unit not in _DELTA_UNITS:
        raise ValueError(f"Unrecognized time unit: {unit!r} — use seconds, minutes, hours, days or weeks")
    if amount == 0:
        raise ValueError(f"Time delta must be positive: {delta!r}")
    return timedelta(**{_DELTA_UNITS[unit]: amount})


class WorldClockAdvance(BaseModel):
    """Request to advance the story's world clock (exactly one mode)."""

    universe_id: UUID
    story_id: UUID
    delta: str | None = Field(default=None, description="Relative advance, e.g. '+3 days'")
    target_time: datetime | None = Field(default=None, description="Absolute world time to jump to")
    display: str | None = Field(default=None, max_length=200, description="Display override; '' resets to ISO")

    @model_validator(mode="after")
    def _exactly_one_mode(self) -> "WorldClockAdvance":
        if (self.delta is None) == (self.target_time is None):
            raise ValueError("Provide exactly one of 'delta' or 'target_time'")
        if self.delta is not None and not self.delta.strip():
            raise ValueError("'delta' must not be empty")
        return self


class WorldClockAdvanceResult(BaseModel):
    """Outcome of one advance call: clock state, movement, crossed deadlines."""

    clock: WorldClockResponse
    changed: bool = Field(description="False when the advance was an idempotent no-op")
    initialized: bool = Field(
        default=False,
        description="True when this call created the clock (first absolute set)",
    )
    crossed: list[WorldClockDeadlineView] = Field(
        default_factory=list,
        description="Deadlines that flipped from upcoming in this advance",
    )


class WorldClockDeadlineUpsert(BaseModel):
    """Create or replace one deadline on an existing world clock."""

    universe_id: UUID
    story_id: UUID
    title: str = Field(min_length=1, max_length=300)
    due_at: datetime
    notes: str = Field(default="", max_length=2000)
    deadline_id: str | None = Field(default=None, description="Set to replace an existing deadline")


class OffScreenSummaryRecord(BaseModel):
    """Persist the LLM off-screen summary onto the clock after an advance."""

    universe_id: UUID
    story_id: UUID
    summary: str = Field(max_length=4000)
    recorded_at: datetime | None = None
