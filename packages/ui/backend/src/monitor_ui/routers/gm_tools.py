"""
GM Tools router — Plot hooks, contradiction detection, and session prep.

Exposes the PlotHookAgent's capabilities to the UI for the GM toolkit.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: monitor_agents (Layer 2)
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from monitor_agents.plot_hooks import (
    Contradiction,
    Handout,
    PlotHook,
    PlotHookAgent,
    SessionPrep,
)

router = APIRouter()


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
    spoiler_level: str = Field(
        default="safe", description="Spoiler level: safe, partial, full"
    )


class GenerateHandoutResponse(BaseModel):
    """Response with generated player handout."""

    handout: Handout


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
        raise HTTPException(
            status_code=500, detail=f"Failed to suggest hooks: {exc}"
        ) from exc


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
        raise HTTPException(
            status_code=500, detail=f"Failed to detect contradictions: {exc}"
        ) from exc


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
        raise HTTPException(
            status_code=500, detail=f"Failed to generate session prep: {exc}"
        ) from exc


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
        raise HTTPException(
            status_code=500, detail=f"Failed to generate handout: {exc}"
        ) from exc
