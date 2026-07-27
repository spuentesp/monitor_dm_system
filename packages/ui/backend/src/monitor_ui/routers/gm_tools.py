"""
GM Tools router — Plot hooks, contradiction detection, session prep, and dice.

Exposes the PlotHookAgent's capabilities to the UI for the GM toolkit, plus a
server-authoritative dice roller (rolls happen server-side, not client-cheatable).

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: monitor_agents (Layer 2), monitor_data.utils (Layer 1)
"""

from __future__ import annotations

import re
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.ingestion.capture_insights import CaptureInsight, CaptureInsightAgent
from monitor_agents.plot_hooks import (
    Contradiction,
    Handout,
    PlotHook,
    PlotHookAgent,
    SessionPrep,
)
from monitor_data.utils.dice import roll_dice
from pydantic import BaseModel, Field

router = APIRouter()
log = structlog.get_logger()

# Bounds for the /gm/roll endpoint. ``roll_dice`` enforces no upper cap, so an
# unbounded ``NdS`` would let one request allocate arbitrarily many rolls; these
# mirror the limits the old client-side roller used.
_MAX_DICE = 100
_MAX_SIDES = 1000
_AMOUNT_RE = re.compile(r"^(?P<amount>\d*)d(?P<sides>\d+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class SuggestHooksRequest(BaseModel):
    """Request body for plot hook suggestions."""

    universe_id: UUID
    story_id: UUID | None = None
    max_hooks: int = Field(default=5, ge=1, le=20)


class SuggestHooksResponse(BaseModel):
    """Response with suggested plot hooks."""

    hooks: list[PlotHook]


class DetectContradictionsRequest(BaseModel):
    """Request body for contradiction detection."""

    universe_id: UUID
    focus_entity_id: UUID | None = None


class DetectContradictionsResponse(BaseModel):
    """Response with detected contradictions."""

    contradictions: list[Contradiction]


class SessionPrepRequest(BaseModel):
    """Request body for session preparation."""

    universe_id: UUID
    story_id: UUID
    session_number: int | None = None


class SessionPrepResponse(BaseModel):
    """Response with session preparation materials."""

    prep: SessionPrep


class GenerateHandoutRequest(BaseModel):
    """Request body for player handout generation."""

    universe_id: UUID
    handout_type: str = Field(
        default="letter",
        description="Type: letter, map_note, prophecy, journal_entry, notice, rumor",
    )
    focus_entity_id: UUID | None = None
    tone: str = Field(
        default="mysterious",
        description="Tone: mysterious, urgent, warm, ominous, neutral",
    )
    spoiler_level: str = Field(default="safe", description="Spoiler level: safe, partial, full")


class GenerateHandoutResponse(BaseModel):
    """Response with generated player handout."""

    handout: Handout


class RollDiceRequest(BaseModel):
    """Request body for a server-authoritative dice roll."""

    expression: str = Field(min_length=1, max_length=100)


class RollDiceResponse(BaseModel):
    """Response with the server's dice roll result."""

    total: int
    rolls: list[int]
    expression: str
    kept_rolls: list[int]
    modifier: int


class CaptureContradictionCheckRequest(BaseModel):
    """Request body for a live capture-entry contradiction check."""

    universe_id: UUID
    entry_text: str = Field(min_length=1, max_length=4000)


class CaptureContradictionCheckResponse(BaseModel):
    """Advisory alert for a capture entry, or None when canon-consistent."""

    alert: Contradiction | None = None


class CaptureInsightsRequest(BaseModel):
    """Request body for per-entry capture insights (P1.2)."""

    universe_id: UUID
    entry_text: str = Field(min_length=1, max_length=4000)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/gm/hooks", response_model=SuggestHooksResponse)
async def suggest_hooks(req: SuggestHooksRequest) -> SuggestHooksResponse:
    """Suggest narrative hooks based on open plot threads and recent events."""
    agent = PlotHookAgent()
    try:
        hooks = await agent.suggest_hooks(
            universe_id=req.universe_id,
            story_id=req.story_id,
            max_hooks=req.max_hooks,
        )
        return SuggestHooksResponse(hooks=hooks)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to suggest hooks: {exc}") from exc


@router.post("/gm/contradictions", response_model=DetectContradictionsResponse)
async def detect_contradictions(
    req: DetectContradictionsRequest,
) -> DetectContradictionsResponse:
    """Detect contradictions in the canon for a given universe."""
    agent = PlotHookAgent()
    try:
        contradictions = await agent.detect_contradictions(
            universe_id=req.universe_id,
            focus_entity_id=req.focus_entity_id,
        )
        return DetectContradictionsResponse(contradictions=contradictions)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to detect contradictions: {exc}") from exc


@router.post("/gm/session-prep", response_model=SessionPrepResponse)
async def generate_session_prep(req: SessionPrepRequest) -> SessionPrepResponse:
    """Generate session preparation materials for the GM."""
    agent = PlotHookAgent()
    try:
        prep = await agent.generate_session_prep(
            universe_id=req.universe_id,
            story_id=req.story_id,
            session_number=req.session_number,
        )
        return SessionPrepResponse(prep=prep)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate session prep: {exc}") from exc


@router.post("/gm/handouts", response_model=GenerateHandoutResponse)
async def generate_handout(req: GenerateHandoutRequest) -> GenerateHandoutResponse:
    """Generate a player handout from world data."""
    agent = PlotHookAgent()
    try:
        handout = await agent.generate_handout(
            universe_id=req.universe_id,
            handout_type=req.handout_type,
            focus_entity_id=req.focus_entity_id,
            tone=req.tone,
            spoiler_level=req.spoiler_level,
        )
        return GenerateHandoutResponse(handout=handout)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate handout: {exc}") from exc


@router.post("/gm/roll", response_model=RollDiceResponse)
async def roll_gm_dice(req: RollDiceRequest) -> RollDiceResponse:
    """Roll dice server-side (authoritative; not client-cheatable).

    Pure utility call — no DB, no agent, no LLM.
    """
    cleaned = req.expression.strip().replace(" ", "")
    m = _AMOUNT_RE.match(cleaned)
    if m:
        amount = int(m.group("amount") or 1)
        sides = int(m.group("sides"))
        if amount > _MAX_DICE or sides > _MAX_SIDES:
            raise HTTPException(
                status_code=422,
                detail=(f"Dice expression out of bounds: {amount}d{sides} (max {_MAX_DICE} dice, {_MAX_SIDES} sides)"),
            )
    try:
        result = roll_dice(req.expression)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # roll_dice applies the modifier on top of the kept rolls; recover it for display.
    modifier = result.total - sum(result.kept_rolls)
    log.info("gm_dice_rolled", expression=result.expression, total=result.total)
    return RollDiceResponse(
        total=result.total,
        rolls=result.rolls,
        expression=result.expression,
        kept_rolls=result.kept_rolls,
        modifier=modifier,
    )


@router.post(
    "/gm/capture/contradiction-check",
    response_model=CaptureContradictionCheckResponse,
)
async def check_capture_contradiction(
    req: CaptureContradictionCheckRequest,
) -> CaptureContradictionCheckResponse:
    """Advisory live contradiction check for a Session Recorder entry (CF-1).

    Read-only: CanonKeeper.check_live_entry never creates proposals and
    never writes to Neo4j. Returns an alert only when the entry collides
    with established canon.
    """
    agent = CanonKeeper()
    try:
        result = await agent.check_live_entry(
            universe_id=req.universe_id,
            entry_text=req.entry_text,
        )
    except Exception as exc:
        log.warning(
            "capture_contradiction_check_failed",
            universe_id=str(req.universe_id),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Failed to check capture entry: {exc}") from exc

    if not result.get("has_contradiction"):
        return CaptureContradictionCheckResponse(alert=None)

    explanation = result.get("explanation") or "Entry conflicts with established canon."
    excerpt = req.entry_text if len(req.entry_text) <= 200 else f"{req.entry_text[:197]}..."
    return CaptureContradictionCheckResponse(
        alert=Contradiction(
            fact_a=f"Established canon: {explanation}",
            fact_b=f"Logged entry: {excerpt}",
            severity="medium",
            explanation=explanation,
            suggestion="Review this entry against canon before canonizing.",
        )
    )


@router.post("/gm/capture/insights", response_model=CaptureInsight)
async def capture_entry_insights(req: CaptureInsightsRequest) -> CaptureInsight:
    """Per-entry capture insights for the Session Recorder (CF-1, P1.2).

    Advisory: analyzes the entry for participants, locations, and candidate
    facts. Candidate facts are visible, not proposed — promotion happens via
    the scene-end canon review (CF-8).
    """
    agent = CaptureInsightAgent()
    try:
        return await agent.analyze_entry(
            universe_id=req.universe_id,
            entry_text=req.entry_text,
        )
    except Exception as exc:
        log.warning(
            "capture_insights_failed",
            universe_id=str(req.universe_id),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Failed to analyze capture entry: {exc}") from exc
