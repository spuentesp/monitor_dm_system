"""
GM Tools router — Plot hooks, contradiction detection, session prep, and dice.

Exposes the PlotHookAgent's capabilities to the UI for the GM toolkit, plus a
server-authoritative dice roller (rolls happen server-side, not client-cheatable).

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: monitor_agents (Layer 2), monitor_data.utils (Layer 1)
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.ingestion.capture_insights import CaptureInsight, CaptureInsightAgent
from monitor_agents.plot_hooks import (
    Contradiction,
    Handout,
    PlotHook,
    PlotHookAgent,
    SessionPrep,
)
from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.base import (
    Authority,
    PlotThreadType,
    ProposalType,
    ThreadPriority,
    ThreadUrgency,
)
from monitor_data.schemas.proposed_changes import (
    Evidence,
    ProposedChangeCreate,
    ProposedChangeFilter,
)
from monitor_data.schemas.story_outlines import PlotThreadCreate
from monitor_data.tools.mongodb_tools import (
    mongodb_create_proposed_change,
    mongodb_list_proposed_changes,
)
from monitor_data.tools.neo4j_tools import neo4j_create_plot_thread
from monitor_data.utils.dice import roll_dice
from monitor_ui.auth import Principal, get_current_user, get_postgres
from monitor_ui.ownership import require_universe_owner
from pydantic import BaseModel, Field

router = APIRouter(dependencies=[Depends(get_current_user)])
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


class SaveHookRequest(BaseModel):
    """Save a selected hook as a plot thread (CF-4)."""

    universe_id: UUID
    story_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    urgency: str = Field(default="medium", max_length=20)
    potential_outcomes: list[str] = Field(default_factory=list)
    connected_threads: list[str] = Field(default_factory=list)


class SaveHookResponse(BaseModel):
    """Saved hook thread reference."""

    thread_id: str


class GeneratePrepItemRequest(BaseModel):
    """Generate content for one session-prep checklist item (CF-7)."""

    universe_id: UUID
    story_id: UUID
    category: str = Field(default="lore", max_length=50)
    description: str = Field(min_length=1, max_length=1000)


class GeneratePrepItemResponse(BaseModel):
    """Generated content for a prep checklist item."""

    content: str


class DetectContradictionsRequest(BaseModel):
    """Request body for contradiction detection."""

    universe_id: UUID
    focus_entity_id: UUID | None = None
    scope: Literal["universe", "story", "scene"] = "universe"
    story_id: UUID | None = None
    scene_id: UUID | None = None


class ResolveContradictionRequest(BaseModel):
    """Resolve a detected contradiction through a pending canon proposal."""

    universe_id: UUID
    story_id: UUID | None = None
    scene_id: UUID | None = None
    fact_a: str = Field(min_length=1, max_length=2000)
    fact_b: str = Field(min_length=1, max_length=2000)
    conflict_type: str = Field(default="semantic", max_length=50)
    resolution: Literal[
        "retcon_older",
        "retcon_newer",
        "apparent_contradiction",
        "explanation_fact",
    ]
    explanation: str = Field(min_length=1, max_length=4000)


class ResolveContradictionResponse(BaseModel):
    """Resolution recorded as a pending proposal for CF-8 review."""

    proposal_id: str


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
    """Request body for per-entry capture insights (P1.2/CF-1)."""

    universe_id: UUID
    entry_text: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=100)
    entry_id: str | None = Field(default=None, max_length=100)
    story_id: UUID | None = None
    scene_id: UUID | None = None


class CaptureInsightsResponse(CaptureInsight):
    """Capture insights plus the draft proposals created for CF-8 review."""

    proposal_ids: list[str] = Field(default_factory=list)
    proposal_errors: list[str] = Field(default_factory=list)

    @property
    def proposals_created(self) -> int:
        return len(self.proposal_ids)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/gm/hooks", response_model=SuggestHooksResponse)
async def suggest_hooks(
    req: SuggestHooksRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> SuggestHooksResponse:
    """Suggest narrative hooks based on open plot threads and recent events."""
    await require_universe_owner(db, principal, req.universe_id)
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
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> DetectContradictionsResponse:
    """Detect contradictions in the canon for a given universe."""
    await require_universe_owner(db, principal, req.universe_id)
    agent = PlotHookAgent()
    try:
        contradictions = await agent.detect_contradictions(
            universe_id=req.universe_id,
            focus_entity_id=req.focus_entity_id,
            scope=req.scope,
            story_id=req.story_id,
            scene_id=req.scene_id,
        )
        return DetectContradictionsResponse(contradictions=contradictions)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to detect contradictions: {exc}") from exc


@router.post("/gm/session-prep", response_model=SessionPrepResponse)
async def generate_session_prep(
    req: SessionPrepRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> SessionPrepResponse:
    """Generate session preparation materials for the GM."""
    await require_universe_owner(db, principal, req.universe_id)
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
async def generate_handout(
    req: GenerateHandoutRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> GenerateHandoutResponse:
    """Generate a player handout from world data."""
    await require_universe_owner(db, principal, req.universe_id)
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
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> CaptureContradictionCheckResponse:
    """Advisory live contradiction check for a Session Recorder entry (CF-1).

    Read-only: CanonKeeper.check_live_entry never creates proposals and
    never writes to Neo4j. Returns an alert only when the entry collides
    with established canon.
    """
    await require_universe_owner(db, principal, req.universe_id)
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


def _capture_proposal_source(entry_id: str | None) -> str:
    return f"capture_entry:{entry_id}" if entry_id else "capture_entry:anonymous"


def _capture_evidence(entry_id: str | None) -> list[Evidence]:
    if not entry_id:
        return []
    try:
        return [Evidence(type="snippet", ref_id=UUID(entry_id))]
    except (TypeError, ValueError):
        return []


async def _create_capture_proposals(
    req: CaptureInsightsRequest,
    insight: CaptureInsight,
) -> tuple[list[str], list[str]]:
    """Create one pending FACT proposal per candidate fact (CF-1 → CF-8).

    Creation is best-effort: capture analysis must remain useful even when the
    proposal store rejects an item. Replaying the same entry is idempotent via
    the ``capture_entry:<entry_id>`` source tag.
    """
    if not req.story_id or not req.scene_id or not insight.candidate_facts:
        return [], []

    source = _capture_proposal_source(req.entry_id)
    created_ids: list[str] = []
    errors: list[str] = []

    def _create() -> tuple[list[str], list[str]]:
        existing = mongodb_list_proposed_changes(ProposedChangeFilter(source=source, limit=500))
        existing_statements = {
            str(p.content.get("statement") or "").strip()
            for p in existing.proposed_changes
            if isinstance(p.content, dict)
        }
        ids: list[str] = []
        errs: list[str] = []
        for fact in insight.candidate_facts:
            statement = str(fact or "").strip()
            if not statement or statement in existing_statements:
                continue
            content: dict[str, Any] = {
                "statement": statement,
                "fact_type": "occurrence",
                "canon_level": "proposed",
                "source_excerpt": req.entry_text,
                "participants": list(insight.participants),
                "locations": list(insight.locations),
                "captured_at": datetime.now(UTC).isoformat(),
                "capture_entry_id": req.entry_id,
            }
            try:
                proposal = mongodb_create_proposed_change(
                    ProposedChangeCreate(
                        scene_id=req.scene_id,
                        story_id=req.story_id,
                        change_type=ProposalType.FACT,
                        content=content,
                        evidence=_capture_evidence(req.entry_id),
                        confidence=0.75,
                        authority=Authority.GM,
                        proposer="CaptureInsightAgent",
                        source=source,
                        proposal_type="capture_candidate_fact",
                    )
                )
                ids.append(str(proposal.proposal_id))
                existing_statements.add(statement)
            except Exception as exc:  # noqa: BLE001  # reason: one bad candidate fact must not block the rest of the entry (in _create_capture_proposals)
                errs.append(f"{statement[:80]}: {exc}")
        return ids, errs

    created_ids, errors = await asyncio.to_thread(_create)
    return created_ids, errors


@router.post("/gm/capture/insights", response_model=CaptureInsightsResponse)
async def capture_entry_insights(
    req: CaptureInsightsRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> CaptureInsightsResponse:
    """Per-entry capture insights for the Session Recorder (CF-1, P1.2).

    Analyzes the entry for participants, locations, and candidate facts. When
    the request carries story/scene context, each candidate fact becomes a
    pending story-scoped FACT proposal for the CF-8 review queue, tagged with
    the entry text as evidence.
    """
    await require_universe_owner(db, principal, req.universe_id)
    agent = CaptureInsightAgent()
    try:
        insight = await agent.analyze_entry(
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

    proposal_ids, proposal_errors = await _create_capture_proposals(req, insight)
    return CaptureInsightsResponse(
        **insight.model_dump(),
        proposal_ids=proposal_ids,
        proposal_errors=proposal_errors,
    )


@router.post("/gm/contradictions/resolve", response_model=ResolveContradictionResponse)
async def resolve_contradiction(
    req: ResolveContradictionRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> ResolveContradictionResponse:
    """Record a CF-5 contradiction resolution as a pending canon proposal.

    Resolutions are intentionally staged as ProposedChange items rather than
    direct Neo4j writes: CanonKeeper remains the only writer, and the GM can
    review the resolution in the CF-8 queue before it becomes canon.
    """
    await require_universe_owner(db, principal, req.universe_id)
    resolution_source = f"contradiction_resolution:{uuid4()}"
    content = {
        "statement": req.explanation.strip(),
        "fact_type": "state",
        "canon_level": "proposed",
        "resolution": req.resolution,
        "conflict_type": req.conflict_type,
        "fact_a": req.fact_a,
        "fact_b": req.fact_b,
        "resolved_at": datetime.now(UTC).isoformat(),
    }
    try:
        proposal = await asyncio.to_thread(
            mongodb_create_proposed_change,
            ProposedChangeCreate(
                scene_id=req.scene_id,
                story_id=req.story_id,
                change_type=ProposalType.FACT,
                content=content,
                confidence=0.9,
                authority=Authority.GM,
                proposer="GM",
                source=resolution_source,
                proposal_type="contradiction_resolution",
            ),
        )
    except Exception as exc:
        log.warning(
            "contradiction_resolution_failed",
            universe_id=str(req.universe_id),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Failed to record contradiction resolution: {exc}") from exc
    return ResolveContradictionResponse(proposal_id=str(proposal.proposal_id))


@router.post("/gm/hooks/save", response_model=SaveHookResponse)
async def save_hook(
    req: SaveHookRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> SaveHookResponse:
    """CF-4: save a selected hook as a story plot thread."""
    await require_universe_owner(db, principal, req.universe_id)
    try:
        urgency = ThreadUrgency(req.urgency)
    except ValueError:
        urgency = ThreadUrgency.MEDIUM
    try:
        thread = await asyncio.to_thread(
            neo4j_create_plot_thread,
            PlotThreadCreate(
                story_id=req.story_id,
                title=req.title,
                thread_type=PlotThreadType.SUBPLOT,
                urgency=urgency,
                priority=ThreadPriority.SECONDARY,
                gm_notes=(
                    f"{req.description}\n\nPotential outcomes: "
                    f"{'; '.join(req.potential_outcomes) if req.potential_outcomes else 'unspecified'}"
                ),
            ),
        )
    except Exception as exc:
        log.warning("hook_save_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to save hook: {exc}") from exc
    return SaveHookResponse(thread_id=str(thread.id))


@router.post("/gm/session-prep/generate-item", response_model=GeneratePrepItemResponse)
async def generate_prep_item(
    req: GeneratePrepItemRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> GeneratePrepItemResponse:
    """CF-7: generate missing content for a prep checklist item."""
    await require_universe_owner(db, principal, req.universe_id)
    agent = PlotHookAgent()
    try:
        content = await agent.generate_prep_item(
            universe_id=req.universe_id,
            story_id=req.story_id,
            category=req.category,
            description=req.description,
        )
    except Exception as exc:
        log.warning("prep_item_generation_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to generate prep item: {exc}") from exc
    return GeneratePrepItemResponse(content=content)
