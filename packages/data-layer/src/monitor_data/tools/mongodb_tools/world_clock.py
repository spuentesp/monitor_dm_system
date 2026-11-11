"""
MongoDB tools for the per-story world clock (CF-11 Advance World Time).

LAYER: 1 (data-layer)
Authority: MongoDB (story-scoped scratch state — no canon, no Neo4j writes)
Use Case: CF-11 (world clock, deadlines, off-screen summary)

One document per (universe, story) in ``world_clocks``. Advances are
monotonic: a target at or before the current time is a no-op (idempotent),
backwards moves raise, and every real advance appends an audit record used
by the CF-7 prep briefing and the CF-2 recap time line.

Every tool takes a single Pydantic request model so the arguments pack
cleanly through ``validate_tool_input`` when agents call them over MCP.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.world_clock import (
    MAX_ADVANCE_RECORDS,
    ClockAdvanceRecord,
    OffScreenSummaryRecord,
    WorldClockAdvance,
    WorldClockAdvanceResult,
    WorldClockDeadline,
    WorldClockDeadlineUpsert,
    WorldClockDeadlineView,
    WorldClockQuery,
    WorldClockResponse,
    deadline_status,
    parse_time_delta,
    view_deadline,
)

log = structlog.get_logger()

WORLD_CLOCKS_COLLECTION = "world_clocks"


def _ensure_utc(value: datetime) -> datetime:
    """Normalize to tz-aware UTC (bare fantasy dates are treated as UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _doc_to_response(doc: dict[str, Any]) -> WorldClockResponse:
    """Convert a stored clock document into its read view (statuses computed)."""
    current_at = _ensure_utc(doc["current_at"])
    deadlines = [WorldClockDeadline.model_validate(d) for d in doc.get("deadlines", []) or []]
    return WorldClockResponse(
        universe_id=UUID(doc["universe_id"]),
        story_id=UUID(doc["story_id"]),
        current_at=current_at,
        display=str(doc.get("display") or "") or current_at.isoformat(),
        deadlines=[view_deadline(d, current_at) for d in deadlines],
        advances=[ClockAdvanceRecord.model_validate(a) for a in doc.get("advances", []) or []],
        offscreen_summary=str(doc.get("offscreen_summary") or ""),
        offscreen_summary_at=doc.get("offscreen_summary_at"),
        updated_at=doc["updated_at"],
    )


def _store(col: Any, doc: dict[str, Any]) -> None:
    """Persist the clock document (one doc per universe+story)."""
    col.update_one(
        {"universe_id": doc["universe_id"], "story_id": doc["story_id"]},
        {"$set": doc},
        upsert=True,
    )


def mongodb_get_world_clock(query: WorldClockQuery) -> WorldClockResponse | None:
    """The story's world clock, or ``None`` when it has never been set."""
    client = get_mongodb_client()
    collection = client.get_collection(WORLD_CLOCKS_COLLECTION)
    doc = collection.find_one({"universe_id": str(query.universe_id), "story_id": str(query.story_id)})
    if not doc:
        return None
    return _doc_to_response(doc)


def mongodb_list_due_deadlines(query: WorldClockQuery) -> list[WorldClockDeadlineView]:
    """Deadlines that are due or overdue at the clock's current world time.

    Empty for a story whose clock has never been set (nothing to be due).
    """
    clock = mongodb_get_world_clock(query)
    if clock is None:
        return []
    return sorted(
        [d for d in clock.deadlines if d.status in ("due", "overdue")],
        key=lambda d: d.due_at,
    )


def mongodb_advance_world_clock(params: WorldClockAdvance) -> WorldClockAdvanceResult:
    """Advance the story's world clock (relative delta or absolute target).

    Semantics:
    - No clock yet: only an absolute ``target_time`` may create one
      (``initialized=True``); relative deltas raise — there is no time to
      move forward from.
    - Target equal to the current time: idempotent no-op, no audit record.
    - Target before the current time, or a negative delta: ``ValueError``
      (the clock is monotonic).
    - A real advance appends an audit record and reports the deadlines that
      flipped from *upcoming* in this move (``crossed``).
    """
    client = get_mongodb_client()
    collection = client.get_collection(WORLD_CLOCKS_COLLECTION)
    key = {"universe_id": str(params.universe_id), "story_id": str(params.story_id)}
    doc = collection.find_one(key)
    now = datetime.now(UTC)

    if doc is None:
        if params.target_time is None:
            raise ValueError(
                "No world clock yet for this story — set an absolute world time first "
                "(e.g. target_time '1012-03-01T09:00'), then advance with deltas."
            )
        target = _ensure_utc(params.target_time)
        record = ClockAdvanceRecord(from_at=None, to_at=target, delta=target.isoformat(), advanced_at=now)
        new_doc = {
            **key,
            "current_at": target,
            # Stored value is the display *override* only; empty means
            # "show the ISO of current_at" (resolved in _doc_to_response).
            "display": (params.display or "").strip(),
            "deadlines": [],
            "advances": [record.model_dump(mode="json")],
            "offscreen_summary": "",
            "offscreen_summary_at": None,
            "updated_at": now,
        }
        _store(collection, new_doc)
        log.info("world_clock_initialized", story_id=key["story_id"], current_at=target.isoformat())
        return WorldClockAdvanceResult(
            clock=_doc_to_response(new_doc),
            changed=True,
            initialized=True,
        )

    current = _ensure_utc(doc["current_at"])
    if params.delta is not None:
        delta = parse_time_delta(params.delta)  # raises ValueError on bad/negative input
        target = current + delta
        delta_repr = params.delta.strip()
    else:
        target = _ensure_utc(params.target_time)  # type: ignore[arg-type]
        delta_repr = target.isoformat()
        if target < current:
            raise ValueError(f"World time cannot move backwards: {target.isoformat()} is before {current.isoformat()}")
        if target == current:
            # Idempotent: repeating the same advance changes nothing.
            return WorldClockAdvanceResult(
                clock=_doc_to_response(doc),
                changed=False,
            )

    stored_deadlines = [WorldClockDeadline.model_validate(d) for d in doc.get("deadlines", []) or []]
    crossed = [
        view_deadline(d, target)
        for d in stored_deadlines
        if _ensure_utc(d.due_at) > current and deadline_status(d.due_at, target) != "upcoming"
    ]

    record = ClockAdvanceRecord(from_at=current, to_at=target, delta=delta_repr, advanced_at=now)
    prior_advances = list(doc.get("advances", []) or [])
    # None → keep the stored override; a string (incl. '') replaces it.
    if params.display is None:
        display = str(doc.get("display") or "")
    else:
        display = params.display.strip()

    new_doc = {
        **doc,
        "current_at": target,
        "display": display,
        "advances": [record.model_dump(mode="json"), *prior_advances][:MAX_ADVANCE_RECORDS],
        "updated_at": now,
    }
    _store(collection, new_doc)
    log.info(
        "world_clock_advanced",
        story_id=key["story_id"],
        delta=delta_repr,
        current_at=target.isoformat(),
        crossed=len(crossed),
    )
    return WorldClockAdvanceResult(
        clock=_doc_to_response(new_doc),
        changed=True,
        crossed=crossed,
    )


def mongodb_upsert_world_deadline(params: WorldClockDeadlineUpsert) -> WorldClockResponse:
    """Create or replace one deadline on an existing world clock.

    Deadlines attach to the clock (not the plot threads), so the clock must
    exist first — set an absolute world time via ``mongodb_advance_world_clock``.
    """
    client = get_mongodb_client()
    collection = client.get_collection(WORLD_CLOCKS_COLLECTION)
    key = {"universe_id": str(params.universe_id), "story_id": str(params.story_id)}
    doc = collection.find_one(key)
    if not doc:
        raise ValueError("No world clock yet for this story — set an absolute world time before adding deadlines.")

    due_at = _ensure_utc(params.due_at)
    stored = [WorldClockDeadline.model_validate(d) for d in doc.get("deadlines", []) or []]
    if params.deadline_id is not None:
        replaced = False
        for i, existing in enumerate(stored):
            if existing.id == params.deadline_id:
                stored[i] = WorldClockDeadline(
                    id=existing.id,
                    title=params.title,
                    due_at=due_at,
                    notes=params.notes,
                )
                replaced = True
                break
        if not replaced:
            raise ValueError(f"Unknown deadline id: {params.deadline_id}")
    else:
        stored.append(WorldClockDeadline(title=params.title, due_at=due_at, notes=params.notes))

    new_doc = {
        **doc,
        "deadlines": [d.model_dump(mode="json") for d in stored],
        "updated_at": datetime.now(UTC),
    }
    _store(collection, new_doc)
    return _doc_to_response(new_doc)


def mongodb_record_offscreen_summary(params: OffScreenSummaryRecord) -> WorldClockResponse:
    """Persist the agent's off-screen NPC summary onto the clock (CF-7 prep)."""
    client = get_mongodb_client()
    collection = client.get_collection(WORLD_CLOCKS_COLLECTION)
    key = {"universe_id": str(params.universe_id), "story_id": str(params.story_id)}
    doc = collection.find_one(key)
    if not doc:
        raise ValueError("No world clock yet for this story — nothing to attach the summary to.")

    new_doc = {
        **doc,
        "offscreen_summary": params.summary,
        "offscreen_summary_at": params.recorded_at or datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    _store(collection, new_doc)
    return _doc_to_response(new_doc)
