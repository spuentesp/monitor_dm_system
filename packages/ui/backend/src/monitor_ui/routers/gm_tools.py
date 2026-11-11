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
from monitor_agents.combat import CombatAgent, ConditionExplanation
from monitor_agents.encounter_difficulty import EncounterDifficultyAgent
from monitor_agents.knowledge_audit import KnowledgeAuditAgent
from monitor_agents.gm_table import (
    GmTableAgent,
    PartyKnowledgeAnswer,
    PrepExtraction,
    RulesAnswer,
    SessionLogExtraction,
    light_table_agent,
)
from monitor_agents.ingestion.capture_insights import CaptureInsight, CaptureInsightAgent
from monitor_agents.ingestion.session_ingest import SessionIngestAgent
from monitor_agents.player_share import ShareAgent, ShareError
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
    EntityType,
    PlotThreadType,
    ProposalStatus,
    ProposalType,
    ThreadPriority,
    ThreadUrgency,
)
from monitor_data.schemas.combat import (
    CombatEnd,
    CombatInitiativeEntry,
    CombatNextRound,
    CombatSessionState,
    CombatSetInitiative,
    CombatStart,
    CombatUpdateCombatant,
)
from monitor_data.schemas.entities import EntityResponse
from monitor_data.schemas.facts import FactFilter, FactResponse
from monitor_data.schemas.gm_prep import (
    GmPrepBundleResponse,
    GmPrepBundleUpsert,
    GmPrepLocation,
    GmPrepNpc,
    GmPrepThread,
)
from monitor_data.schemas.proposed_changes import (
    Evidence,
    ProposedChangeCreate,
    ProposedChangeFilter,
)
from monitor_data.schemas.knowledge_audit import KnowledgeChallenge, KnowledgeItem
from monitor_data.schemas.player_share import ShareArtifactType, ShareSpoilerLevel
from monitor_data.schemas.relationships import RelationshipFilter, RelationshipResponse
from monitor_data.schemas.stories import StoryLedgerEntry
from monitor_data.schemas.story_outlines import PlotThreadCreate
from monitor_data.schemas.world_clock import (
    ClockAdvanceRecord,
    OffScreenSummaryRecord,
    WorldClockDeadlineUpsert,
    WorldClockDeadlineView,
    WorldClockQuery,
    WorldClockResponse,
)
from monitor_data.tools.mongodb_tools import (
    STRIKE_REASON,
    mongodb_create_proposed_change,
    mongodb_get_gm_prep_bundle,
    mongodb_get_world_clock,
    mongodb_list_proposed_changes,
    mongodb_list_story_ledger_entries,
    mongodb_record_offscreen_summary,
    mongodb_upsert_gm_prep_bundle,
    mongodb_upsert_world_deadline,
)
from monitor_data.tools.neo4j_tools import (
    neo4j_create_plot_thread,
    neo4j_get_entity,
    neo4j_get_party,
    neo4j_list_agendas,
    neo4j_list_facts,
    neo4j_list_relationships,
    neo4j_search_entities,
)
from monitor_data.utils.dice import roll_dice
from monitor_ui.auth import Principal, get_current_user, get_postgres
from monitor_ui.ownership import require_story_owner, require_universe_owner, resource_route_guard
from monitor_ui.routers.chat_game_system import (
    get_game_system_doc,
    resolve_universe_system_binding,
)
from monitor_ui.routers.chat_persistence import db_load_messages, db_load_sessions
from pydantic import BaseModel, Field

router = APIRouter(dependencies=[Depends(resource_route_guard)])
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
        description="Type: letter, map_note, prophecy, journal_entry, notice, rumor, campaign_summary",
    )
    focus_entity_id: UUID | None = None
    story_id: UUID | None = Field(
        None,
        description="Story for campaign_summary handouts (CF-12 arc recap source); defaults to the universe's latest story",
    )
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
            story_id=req.story_id,
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


# ---------------------------------------------------------------------------
# Phase 7 Part B — GM assistant at a real table (tasks 2-4)
#
# Prep to table (CF-7): ingest the GM's notes, review what was extracted,
# open the /gm page with tonight's NPCs, locations and threads ready.
# At the table (CF-3/Q-2/Q-4/Q-7): fast lookups — NPC dossier, party
# knowledge, last session, names/complications on demand, rules with source.
# After the session (CF-5/CF-8): paste what happened; the assistant stages
# canon proposals for review and flags contradictions (direct + G-9).
# ---------------------------------------------------------------------------


class PrepExtractRequest(BaseModel):
    """Extract tonight's prep items from the GM's session notes."""

    universe_id: UUID
    story_id: UUID | None = None
    notes: str = Field(min_length=1, max_length=50000)


class PrepCommitRequest(BaseModel):
    """Persist the reviewed prep bundle and stage its canon work."""

    universe_id: UUID
    story_id: UUID
    npcs: list[GmPrepNpc] = Field(default_factory=list)
    locations: list[GmPrepLocation] = Field(default_factory=list)
    threads: list[GmPrepThread] = Field(default_factory=list)


class PrepCommitResponse(BaseModel):
    """The saved bundle plus what was written where."""

    bundle: GmPrepBundleResponse
    committed_thread_ids: list[str] = Field(default_factory=list)
    staged_proposal_ids: list[str] = Field(default_factory=list)
    staging_errors: list[str] = Field(default_factory=list)


class PrepBundleGetResponse(BaseModel):
    """The saved prep bundle for a (universe, story), if any."""

    found: bool
    bundle: GmPrepBundleResponse | None = None


# ---------------------------------------------------------------------------
# World clock (CF-11 Advance World Time) — request / response schemas
# ---------------------------------------------------------------------------


class ClockGetResponse(BaseModel):
    """The story's world clock briefing (CF-7), when one has been set."""

    found: bool
    clock: WorldClockResponse | None = None


class ClockAdvanceRequest(BaseModel):
    """Advance in-fiction time: a relative delta or an absolute target."""

    universe_id: UUID
    story_id: UUID
    delta: str | None = Field(default=None, description="Relative advance, e.g. '+3 days'")
    target_time: datetime | None = Field(default=None, description="Absolute world time to jump to")


class ClockAdvanceResponse(BaseModel):
    """Post-advance briefing: clock, deadline flips, summary, staged proposals."""

    clock: WorldClockResponse
    changed: bool
    initialized: bool
    crossed: list[WorldClockDeadlineView] = Field(default_factory=list)
    due: list[WorldClockDeadlineView] = Field(default_factory=list)
    offscreen_summary: str = ""
    npc_activities: list[str] = Field(default_factory=list)
    staged_proposal_ids: list[str] = Field(default_factory=list)
    staging_errors: list[str] = Field(default_factory=list)


class ClockDeadlineRequest(BaseModel):
    """Create or replace one deadline on the story's world clock."""

    universe_id: UUID
    story_id: UUID
    title: str = Field(min_length=1, max_length=300)
    due_at: datetime
    notes: str = Field(default="", max_length=2000)
    deadline_id: str | None = Field(default=None, description="Set to replace an existing deadline")


class NpcLookupRequest(BaseModel):
    """Look up one NPC (or entity) dossier at the table."""

    universe_id: UUID
    name: str | None = Field(default=None, max_length=200)
    entity_id: UUID | None = None


class NpcDossierResponse(BaseModel):
    """Who this NPC is and what they want."""

    found: bool
    entity: EntityResponse | None = None
    agendas: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[RelationshipResponse] = Field(default_factory=list)
    recent_facts: list[FactResponse] = Field(default_factory=list)
    note: str = ""


class PartyKnowledgeRequest(BaseModel):
    """What does the party know about a topic?"""

    universe_id: UUID
    party_id: UUID | None = None
    character_ids: list[UUID] = Field(default_factory=list)
    topic: str | None = Field(default=None, max_length=400)


class LastSessionRequest(BaseModel):
    """What was said / happened last session?"""

    universe_id: UUID
    story_id: UUID
    transcript_limit: int = Field(default=20, ge=1, le=100)


class TranscriptLine(BaseModel):
    """One line of the prior session's transcript."""

    role: str
    content: str
    timestamp: str


class LastSessionResponse(BaseModel):
    """The previous session's ledger entry and transcript tail."""

    found: bool
    session_id: str | None = None
    session_title: str | None = None
    ledger_entry: StoryLedgerEntry | None = None
    transcript: list[TranscriptLine] = Field(default_factory=list)
    world_time: str = Field(default="", description="Current world-clock readout (CF-11)")
    time_line: list[ClockAdvanceRecord] = Field(
        default_factory=list,
        description="World-clock advances, newest first — the recap's time line (CF-2)",
    )
    note: str = ""


class ImproviseRequest(BaseModel):
    """On-demand name or complication at the table."""

    universe_id: UUID
    story_id: UUID | None = None
    kind: Literal["name", "complication"]
    context: str = Field(default="", max_length=2000)
    count: int = Field(default=3, ge=1, le=10)


class ImproviseResponse(BaseModel):
    """Suggestions with the rationale behind them."""

    kind: str
    suggestions: list[str] = Field(default_factory=list)
    rationale: str = ""


class RulesLookupRequest(BaseModel):
    """A rules question answered from the system's own rules."""

    system_id: UUID | None = None
    universe_id: UUID | None = None
    question: str = Field(min_length=1, max_length=2000)


class SessionLogFlag(BaseModel):
    """One advisory contradiction flag on a session-log statement."""

    kind: Literal["direct", "implication"]
    severity: str = "medium"
    explanation: str = ""


class SessionLogItem(BaseModel):
    """One staged canon change from a pasted session log."""

    statement: str
    participants: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    proposal_id: str | None = None
    flags: list[SessionLogFlag] = Field(default_factory=list)


class SessionLogProposeRequest(BaseModel):
    """Paste what happened; propose canon changes and flag contradictions."""

    universe_id: UUID
    story_id: UUID | None = None
    scene_id: UUID | None = None
    log_text: str = Field(min_length=1, max_length=40000)


class SessionLogProposeResponse(BaseModel):
    """Staged proposals, each with its contradiction flags (G-9)."""

    batch_id: str
    items: list[SessionLogItem] = Field(default_factory=list)
    proposal_errors: list[str] = Field(default_factory=list)


@router.post("/gm/prep/extract", response_model=PrepExtraction)
async def prep_extract(
    req: PrepExtractRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PrepExtraction:
    """Extract tonight's NPCs, locations and threads from the GM's notes (CF-7).

    Review-only: nothing is saved or staged — the GM reviews the extraction
    and then commits it via ``POST /gm/prep/commit``.
    """
    await require_universe_owner(db, principal, req.universe_id)
    agent = GmTableAgent()
    try:
        return await agent.extract_prep(universe_id=req.universe_id, notes=req.notes)
    except Exception as exc:
        log.warning("prep_extract_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to extract prep items: {exc}") from exc


@router.post("/gm/prep/commit", response_model=PrepCommitResponse)
async def prep_commit(
    req: PrepCommitRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PrepCommitResponse:
    """Save the reviewed prep bundle and stage its canon work (CF-7 → CF-8).

    Accepted threads become story plot threads (same path as ``/gm/hooks/save``);
    new NPCs/locations are staged as pending ENTITY proposals for the CF-8
    review queue (CanonKeeper remains the only Neo4j writer). The bundle itself
    is the "tonight" view the /gm page opens with.
    """
    await require_universe_owner(db, principal, req.universe_id)
    bundle_id = uuid4()

    committed_thread_ids: list[str] = []
    staged_proposal_ids: list[str] = []
    threads: list[GmPrepThread] = []
    for item in req.threads:
        urgency = _parse_thread_urgency(item.urgency)
        plot_thread = PlotThreadCreate(
            story_id=req.story_id,
            title=item.title,
            thread_type=PlotThreadType.SUBPLOT,
            urgency=urgency,
            priority=ThreadPriority.SECONDARY,
            gm_notes=item.description,
        )
        try:
            thread = await asyncio.to_thread(neo4j_create_plot_thread, plot_thread)
        except Exception as exc:
            log.warning("prep_thread_commit_failed", title=item.title, error=str(exc))
            raise HTTPException(status_code=500, detail=f"Failed to save thread '{item.title}': {exc}") from exc
        thread_id = str(thread.id)
        committed_thread_ids.append(thread_id)
        threads.append(item.model_copy(update={"thread_id": thread_id}))

    def _stage_entities() -> tuple[list[str], list[str]]:
        ids: list[str] = []
        errs: list[str] = []
        proposals: list[tuple[str, str, str]] = [
            (
                npc.name,
                EntityType.CHARACTER.value,
                f"{npc.description}\n\nWants: {npc.want}" if npc.want else npc.description,
            )
            for npc in req.npcs
            if npc.existing_entity_id is None
        ]
        proposals += [
            (loc.name, EntityType.LOCATION.value, loc.description)
            for loc in req.locations
            if loc.existing_entity_id is None
        ]
        for name, entity_type, description in proposals:
            try:
                proposal = mongodb_create_proposed_change(
                    ProposedChangeCreate(
                        story_id=req.story_id,
                        change_type=ProposalType.ENTITY,
                        content={
                            "name": name,
                            "entity_type": entity_type,
                            "description": description,
                        },
                        evidence=_capture_evidence(str(bundle_id)),
                        confidence=0.7,
                        authority=Authority.GM,
                        proposer="GM",
                        source=_capture_proposal_source(str(bundle_id)),
                        proposal_type="prep_tonight",
                    )
                )
                ids.append(str(proposal.proposal_id))
            except Exception as exc:  # noqa: BLE001  # reason: one rejected staging must not lose the bundle (in prep_commit)
                log.warning("prep_entity_staging_failed", name=name, error=str(exc))
                errs.append(f"{name[:80]}: {exc}")
        return ids, errs

    staged_proposal_ids, staging_errors = await asyncio.to_thread(_stage_entities)

    try:
        bundle = await asyncio.to_thread(
            mongodb_upsert_gm_prep_bundle,
            GmPrepBundleUpsert(
                universe_id=req.universe_id,
                story_id=req.story_id,
                npcs=req.npcs,
                locations=req.locations,
                threads=threads,
                source=f"prep_bundle:{bundle_id}",
            ),
        )
    except Exception as exc:
        log.warning("prep_bundle_save_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to save the prep bundle: {exc}") from exc
    return PrepCommitResponse(
        bundle=bundle,
        committed_thread_ids=committed_thread_ids,
        staged_proposal_ids=staged_proposal_ids,
        staging_errors=staging_errors,
    )


@router.get("/gm/prep/{universe_id}", response_model=PrepBundleGetResponse)
async def prep_get(
    universe_id: str,
    story_id: str | None = None,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PrepBundleGetResponse:
    """Return the saved prep bundle ("tonight's" NPCs, locations, threads)."""
    universe_uuid = _uuid_or_400(universe_id, "universe_id")
    story_uuid = _uuid_or_400(story_id, "story_id") if story_id else None
    await require_universe_owner(db, principal, universe_uuid)
    bundle = await asyncio.to_thread(mongodb_get_gm_prep_bundle, universe_uuid, story_uuid)
    if bundle is None:
        return PrepBundleGetResponse(found=False, bundle=None)
    return PrepBundleGetResponse(found=True, bundle=bundle)


# ---------------------------------------------------------------------------
# World clock (CF-11 Advance World Time)
#
# The GM moves in-fiction time explicitly. Deadline flips are deterministic
# (Layer 1), the off-screen NPC summary is the agent's typed LLM call, and
# crossed deadlines are staged as ProposedChange items for the CF-8 queue —
# the clock itself is story-scoped MongoDB scratch state, so no Neo4j write
# happens here (CanonKeeper remains the only Neo4j writer).
# ---------------------------------------------------------------------------


def _stage_crossed_deadlines(
    story_id: UUID,
    crossed: list[WorldClockDeadlineView],
    world_time: datetime,
) -> tuple[list[str], list[str]]:
    """Stage one FACT proposal per deadline crossed by an advance (CF-11 → CF-8).

    Best-effort: one rejected staging must not lose the advance itself.
    """
    ids: list[str] = []
    errors: list[str] = []
    for deadline in crossed:
        source = f"world_clock:{story_id}:{deadline.id}:{world_time.isoformat()}"
        try:
            proposal = mongodb_create_proposed_change(
                ProposedChangeCreate(
                    story_id=story_id,
                    change_type=ProposalType.FACT,
                    content={
                        "statement": (f"{deadline.title} — deadline reached (world time {world_time.isoformat()})"),
                        "fact_type": "state",
                        "canon_level": "proposed",
                        "deadline_id": deadline.id,
                        "due_at": deadline.due_at.isoformat(),
                    },
                    confidence=0.7,
                    authority=Authority.GM,
                    proposer="GM",
                    source=source,
                    proposal_type="world_clock_deadline",
                    needs_review=True,
                    review_reason="World-clock deadline crossed — confirm the canon effect of time passing",
                    review_source="world_clock",
                )
            )
            ids.append(str(proposal.proposal_id))
        except Exception as exc:  # noqa: BLE001  # reason: one rejected staging must not lose the advance (in _stage_crossed_deadlines)
            log.warning("clock_deadline_staging_failed", deadline=deadline.title, error=str(exc))
            errors.append(f"{deadline.title}: {exc}")
    return ids, errors


@router.get("/gm/clock/{story_id}", response_model=ClockGetResponse)
async def get_world_clock(
    story_id: str,
    universe_id: str,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> ClockGetResponse:
    """The story's world clock briefing: readout, deadlines, last off-screen tick (CF-7)."""
    story_uuid = _uuid_or_400(story_id, "story_id")
    universe_uuid = _uuid_or_400(universe_id, "universe_id")
    await require_universe_owner(db, principal, universe_uuid)
    clock = await asyncio.to_thread(
        mongodb_get_world_clock,
        WorldClockQuery(universe_id=universe_uuid, story_id=story_uuid),
    )
    if clock is None:
        return ClockGetResponse(found=False)
    return ClockGetResponse(found=True, clock=clock)


@router.post("/gm/clock/advance", response_model=ClockAdvanceResponse)
async def advance_world_clock(
    req: ClockAdvanceRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> ClockAdvanceResponse:
    """Advance in-fiction time; return deadlines and the off-screen tick (CF-11).

    Tenancy: session/story ownership follows the universe owner (SYS-6).
    Backwards moves and deltas before the clock exists come back as 422 (the
    agent surfaces tool errors as ``ValueError``). Deadlines crossed by this
    advance are staged as pending CF-8 proposals — never written to Neo4j.
    """
    await require_universe_owner(db, principal, req.universe_id)
    if (req.delta is None) == (req.target_time is None):
        raise HTTPException(status_code=422, detail="Provide exactly one of 'delta' or 'target_time'.")
    agent = GmTableAgent()
    try:
        outcome = await agent.advance_and_summarize(
            universe_id=req.universe_id,
            story_id=req.story_id,
            delta=req.delta,
            target_time=req.target_time,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.warning("clock_advance_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to advance world time: {exc}") from exc

    offscreen_summary = outcome.offscreen.summary if outcome.offscreen else ""
    npc_activities = list(outcome.offscreen.npc_activities) if outcome.offscreen else []
    if outcome.offscreen is not None and outcome.changed:
        # The advance already happened — a failed summary persist must not
        # undo it; log and keep the response useful.
        try:
            await asyncio.to_thread(
                mongodb_record_offscreen_summary,
                OffScreenSummaryRecord(
                    universe_id=req.universe_id,
                    story_id=req.story_id,
                    summary=offscreen_summary,
                ),
            )
        except Exception as exc:  # noqa: BLE001  # reason: summary persistence must not fail the advance (in advance_world_clock)
            log.warning("clock_summary_persist_failed", universe_id=str(req.universe_id), error=str(exc))

    staged: list[str] = []
    staging_errors: list[str] = []
    if outcome.changed and outcome.crossed:
        staged, staging_errors = await asyncio.to_thread(
            _stage_crossed_deadlines,
            req.story_id,
            outcome.crossed,
            outcome.clock.current_at,
        )

    return ClockAdvanceResponse(
        clock=outcome.clock,
        changed=outcome.changed,
        initialized=outcome.initialized,
        crossed=outcome.crossed,
        due=outcome.due,
        offscreen_summary=offscreen_summary,
        npc_activities=npc_activities,
        staged_proposal_ids=staged,
        staging_errors=staging_errors,
    )


@router.post("/gm/clock/deadline", response_model=WorldClockResponse)
async def upsert_clock_deadline(
    req: ClockDeadlineRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> WorldClockResponse:
    """Attach a deadline to the story's world clock (CF-11; surfaces via CF-3)."""
    await require_universe_owner(db, principal, req.universe_id)
    try:
        return await asyncio.to_thread(
            mongodb_upsert_world_deadline,
            WorldClockDeadlineUpsert(
                universe_id=req.universe_id,
                story_id=req.story_id,
                title=req.title,
                due_at=req.due_at,
                notes=req.notes,
                deadline_id=req.deadline_id,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.warning("clock_deadline_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to save deadline: {exc}") from exc


@router.post("/gm/lookup/npc", response_model=NpcDossierResponse)
async def lookup_npc(
    req: NpcLookupRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> NpcDossierResponse:
    """Who is this NPC and what do they want (CF-3 / Q-2)."""
    await require_universe_owner(db, principal, req.universe_id)

    def _resolve_entity() -> EntityResponse | None:
        if req.entity_id is not None:
            return neo4j_get_entity(req.entity_id)
        query = (req.name or "").strip()
        if not query:
            return None
        matches = neo4j_search_entities(req.universe_id, query)
        if not matches:
            return None
        exact = [m for m in matches if str(m.get("name", "")).lower() == query.lower()]
        chosen = exact[0] if exact else matches[0]
        entity_id = chosen.get("id")
        return neo4j_get_entity(UUID(str(entity_id))) if entity_id else None

    entity = await asyncio.to_thread(_resolve_entity)
    if entity is None:
        return NpcDossierResponse(found=False, note="No entity with that name in this universe.")

    def _gather() -> tuple[list[dict[str, Any]], list[RelationshipResponse], list[FactResponse]]:
        agendas = [
            a
            for a in neo4j_list_agendas(req.universe_id, status=None)
            if str(a.get("owner_id") or "") == str(entity.id)
        ]
        relationships = neo4j_list_relationships(RelationshipFilter(entity_id=entity.id, limit=20)).relationships
        facts = neo4j_list_facts(FactFilter(universe_id=req.universe_id, entity_id=entity.id, limit=20))
        return agendas, relationships, facts

    agendas, relationships, facts = await asyncio.to_thread(_gather)
    return NpcDossierResponse(
        found=True,
        entity=entity,
        agendas=agendas,
        relationships=relationships,
        recent_facts=facts,
    )


@router.post("/gm/lookup/party-knowledge", response_model=PartyKnowledgeAnswer)
async def lookup_party_knowledge(
    req: PartyKnowledgeRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> PartyKnowledgeAnswer:
    """What does the party know about this? (CF-3 / Q-4)."""
    await require_universe_owner(db, principal, req.universe_id)
    character_ids = list(req.character_ids)
    if req.party_id is not None:
        party_id: UUID = req.party_id

        def _party_members() -> list[UUID]:
            party = neo4j_get_party(party_id)
            return [m.entity_id for m in (party.members if party else [])]

        character_ids.extend(await asyncio.to_thread(_party_members))
    if not character_ids:
        raise HTTPException(
            status_code=422,
            detail="Provide party_id or at least one character_id.",
        )

    agent = GmTableAgent()
    try:
        return await agent.party_knowledge(
            universe_id=req.universe_id,
            character_ids=character_ids,
            topic=req.topic,
        )
    except Exception as exc:
        log.warning("party_knowledge_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to look up party knowledge: {exc}") from exc


@router.post("/gm/lookup/last-session", response_model=LastSessionResponse)
async def lookup_last_session(
    req: LastSessionRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> LastSessionResponse:
    """What happened / was said last session (CF-2 / Q-10).

    Sources: the story's ledger (one append-only entry per finished scene)
    and the most recent session's transcript tail for the story.
    """
    await require_universe_owner(db, principal, req.universe_id)

    def _ledger() -> StoryLedgerEntry | None:
        entries = mongodb_list_story_ledger_entries(req.story_id, limit=2)
        return entries[-1] if entries else None

    def _clock() -> WorldClockResponse | None:
        return mongodb_get_world_clock(WorldClockQuery(universe_id=req.universe_id, story_id=req.story_id))

    def _prior_session() -> tuple[str | None, str | None, list[TranscriptLine]]:
        sessions = [s for s in db_load_sessions() if str(s.get("story_id") or "") == str(req.story_id)]
        if not sessions:
            return None, None, []
        sessions.sort(key=lambda s: str(s.get("updated_at") or ""), reverse=True)
        session = sessions[0]
        session_id = str(session.get("id") or session.get("session_id") or "")
        if not session_id:
            return None, None, []
        messages = db_load_messages(session_id)[-req.transcript_limit :]
        lines = [
            TranscriptLine(
                role=str(m.get("role") or ""),
                content=str(m.get("content") or ""),
                timestamp=str(m.get("timestamp") or ""),
            )
            for m in messages
        ]
        return session_id, str(session.get("title") or "") or None, lines

    entry, clock, (session_id, session_title, transcript) = await asyncio.to_thread(
        lambda: (_ledger(), _clock(), _prior_session())
    )
    world_time = clock.display if clock else ""
    time_line = list(clock.advances) if clock else []
    if entry is None and session_id is None:
        return LastSessionResponse(
            found=False,
            note="No previous session found for this story.",
            world_time=world_time,
            time_line=time_line,
        )
    return LastSessionResponse(
        found=True,
        session_id=session_id,
        session_title=session_title,
        ledger_entry=entry,
        transcript=transcript,
        world_time=world_time,
        time_line=time_line,
    )


@router.post("/gm/lookup/improvise", response_model=ImproviseResponse)
async def lookup_improvise(
    req: ImproviseRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> ImproviseResponse:
    """A name or a complication on demand (CF-4)."""
    await require_universe_owner(db, principal, req.universe_id)
    agent = light_table_agent()
    try:
        if req.kind == "name":
            names = await agent.suggest_names(
                universe_id=req.universe_id,
                context=req.context,
                count=req.count,
            )
            return ImproviseResponse(
                kind="name",
                suggestions=list(names.names),
                rationale=names.rationale,
            )
        complications = await agent.suggest_complications(
            universe_id=req.universe_id,
            context=req.context,
            count=req.count,
            story_id=req.story_id,
        )
        return ImproviseResponse(
            kind="complication",
            suggestions=list(complications.complications),
            rationale=complications.rationale,
        )
    except Exception as exc:
        log.warning("improvise_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {exc}") from exc


@router.post("/gm/lookup/rules", response_model=RulesAnswer)
async def lookup_rules(
    req: RulesLookupRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> RulesAnswer:
    """A rules question answered with its source (Q-7 / RS)."""
    system_id = req.system_id
    if system_id is None and req.universe_id is not None:
        await require_universe_owner(db, principal, req.universe_id)
        binding = await asyncio.to_thread(resolve_universe_system_binding, str(req.universe_id))
        bound = binding.get("system_id")
        system_id = UUID(str(bound)) if bound else None
    if system_id is None:
        raise HTTPException(
            status_code=422,
            detail="Provide system_id, or a universe with a bound game system.",
        )
    agent = GmTableAgent()
    try:
        return await agent.answer_rules(system_id=system_id, question=req.question)
    except Exception as exc:
        log.warning("rules_lookup_failed", system_id=str(system_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to answer the rules question: {exc}") from exc


def _session_log_flags(
    direct: list[dict[str, Any]],
    implication: list[dict[str, Any]],
) -> list[SessionLogFlag]:
    flags = [
        SessionLogFlag(kind="direct", severity="medium", explanation=str(d.get("explanation") or "")) for d in direct
    ]
    flags += [
        SessionLogFlag(
            kind="implication",
            severity=str(d.get("severity") or "high"),
            explanation=str(d.get("explanation") or ""),
        )
        for d in implication
    ]
    return flags


@router.post("/gm/session-log/propose", response_model=SessionLogProposeResponse)
async def session_log_propose(
    req: SessionLogProposeRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> SessionLogProposeResponse:
    """After the session: paste what happened, get canon proposals + flags (CF-5/CF-8).

    Each extracted world-state statement becomes one pending FACT proposal in
    the CF-8 review queue. Contradictions with existing canon are flagged in
    two passes — the direct check (``CanonKeeper.check_live_entry``) and the
    implication-level G-9 depth check (``implication_conflict_flags``) — and
    flagged proposals are created with ``needs_review`` set. The checks run
    before anything is staged, so a failed check writes nothing. Proposals are
    story- or scene-scoped, so one of the two ids is required.
    """
    await require_universe_owner(db, principal, req.universe_id)
    if req.story_id is None and req.scene_id is None:
        raise HTTPException(
            status_code=422,
            detail="Provide story_id or scene_id so proposals can be staged for review.",
        )
    agent = GmTableAgent()
    canonkeeper = CanonKeeper()
    per_statement_direct: list[dict[str, Any]] = []
    try:
        extraction: SessionLogExtraction = await agent.extract_session_log(
            universe_id=req.universe_id,
            log_text=req.log_text,
        )
        statements = [s for s in extraction.statements if s.statement.strip()]
        for item in statements:
            result = await canonkeeper.check_live_entry(
                universe_id=req.universe_id,
                entry_text=item.statement,
            )
            per_statement_direct.append(
                {"explanation": result.get("explanation") or ""} if result.get("has_contradiction") else {}
            )
        implication_flags = await canonkeeper.implication_conflict_flags(
            req.universe_id,
            [item.statement for item in statements],
        )
    except Exception as exc:
        log.warning("session_log_analysis_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze the session log: {exc}",
        ) from exc
    implication_by_statement: dict[str, list[dict[str, Any]]] = {}
    for flag in implication_flags:
        implication_by_statement.setdefault(str(flag.get("statement") or ""), []).append(flag)

    batch_id = str(uuid4())
    source = f"session_log:{batch_id}"
    created: list[str | None] = []
    errors: list[str] = []

    def _stage() -> tuple[list[str | None], list[str]]:
        ids: list[str | None] = []
        errs: list[str] = []
        for idx, item in enumerate(statements):
            direct_flag = per_statement_direct[idx]
            imp_flags = implication_by_statement.get(item.statement, [])
            flags = _session_log_flags([direct_flag] if direct_flag else [], imp_flags)
            needs_review = bool(flags)
            review_reason = "; ".join(f.explanation for f in flags if f.explanation)[:2000] or None
            try:
                proposal = mongodb_create_proposed_change(
                    ProposedChangeCreate(
                        scene_id=req.scene_id,
                        story_id=req.story_id,
                        change_type=ProposalType.FACT,
                        content={
                            "statement": item.statement,
                            "fact_type": "occurrence",
                            "canon_level": "proposed",
                            "source_excerpt": req.log_text[:2000],
                            "participants": list(item.participants),
                            "locations": list(item.locations),
                            "session_log_batch_id": batch_id,
                        },
                        evidence=_capture_evidence(batch_id),
                        confidence=0.75,
                        authority=Authority.GM,
                        proposer="GM",
                        source=source,
                        proposal_type="session_log_fact",
                        needs_review=needs_review,
                        review_reason=review_reason,
                        review_source="gm_session_log_flags" if needs_review else None,
                    )
                )
                ids.append(str(proposal.proposal_id))
            except Exception as exc:  # noqa: BLE001  # reason: one bad statement must not lose the rest of the batch (in session_log_propose)
                ids.append(None)
                errs.append(f"{item.statement[:80]}: {exc}")
        return ids, errs

    created, errors = await asyncio.to_thread(_stage)

    items = [
        SessionLogItem(
            statement=item.statement,
            participants=list(item.participants),
            locations=list(item.locations),
            proposal_id=created[idx],
            flags=_session_log_flags(
                [per_statement_direct[idx]] if per_statement_direct[idx] else [],
                implication_by_statement.get(item.statement, []),
            ),
        )
        for idx, item in enumerate(statements)
    ]
    return SessionLogProposeResponse(batch_id=batch_id, items=items, proposal_errors=errors)


# ---------------------------------------------------------------------------
# G03 — mid-session strike/edit of captured entries (CF-1 amendment)
#
# While recording, the GM can edit or strike any logged entry and retract or
# undo-retract any queued candidate proposal — one click, no wrap-up. Struck
# entries keep an audit trail (v1 soft-delete only); striking also retracts
# the entry's pending capture proposals with reason "struck at the table"
# (G03 open decision: recommended default, with one undo).
# ---------------------------------------------------------------------------


class SessionLogEntryPatchRequest(BaseModel):
    """Edit a logged recorder entry; insight extraction re-runs for it only."""

    universe_id: UUID
    text: str = Field(min_length=1, max_length=4000)
    story_id: UUID | None = None
    scene_id: UUID | None = None


class SessionLogEntry(BaseModel):
    """One logged (or struck) recorder entry as the correction routes see it."""

    id: str
    session_id: str
    role: str = "player"
    content: str
    timestamp: str = ""
    struck: bool = False
    struck_at: str | None = None
    struck_reason: str | None = None
    edited_at: str | None = None


class SessionLogEntryPatchResponse(BaseModel):
    """Edited entry plus the re-run insight (None when extraction was skipped)."""

    entry: SessionLogEntry
    insight: CaptureInsight | None = None
    insight_skipped: bool = False
    proposal_ids: list[str] = Field(default_factory=list)
    proposal_errors: list[str] = Field(default_factory=list)


class SessionLogEntryStrikeResponse(BaseModel):
    """Struck entry plus the proposals retracted with it."""

    entry: SessionLogEntry
    retracted_proposal_ids: list[str] = Field(default_factory=list)
    retract_errors: list[str] = Field(default_factory=list)


class SessionLogEntryRestoreResponse(BaseModel):
    """Restored entry plus the proposals put back to pending by the undo."""

    entry: SessionLogEntry
    restored_proposal_ids: list[str] = Field(default_factory=list)
    restore_errors: list[str] = Field(default_factory=list)


class SessionLogProposalRetractRequest(BaseModel):
    """Optional strike reason for a standalone proposal retract."""

    reason: str = Field(default=STRIKE_REASON, min_length=1, max_length=2000)


class SessionLogProposalRetractResponse(BaseModel):
    """The retracted proposal's id, new status, and the reason recorded."""

    proposal_id: str
    status: str
    reason: str


def _entry_from_doc(doc: dict[str, Any]) -> SessionLogEntry:
    return SessionLogEntry(
        id=str(doc.get("id") or ""),
        session_id=str(doc.get("session_id") or ""),
        role=str(doc.get("role") or "player"),
        content=str(doc.get("content") or ""),
        timestamp=str(doc.get("timestamp") or ""),
        struck=bool(doc.get("struck")),
        struck_at=doc.get("struck_at"),
        struck_reason=doc.get("struck_reason"),
        edited_at=doc.get("edited_at"),
    )


def _evict_recorder_messages(session_id: str) -> None:
    """Drop the chat router's in-process message cache after a correction."""
    if not session_id:
        return
    from monitor_ui.routers.chat import invalidate_messages_cache

    invalidate_messages_cache(session_id)


def _entry_http_error(exc: ValueError) -> HTTPException:
    if "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail="Not found")
    return HTTPException(status_code=409, detail=str(exc))


@router.patch(
    "/gm/session-log/entries/{log_entry_id}",
    response_model=SessionLogEntryPatchResponse,
)
async def update_session_log_entry(
    log_entry_id: str,
    req: SessionLogEntryPatchRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> SessionLogEntryPatchResponse:
    """Edit a logged entry in place and re-run insight extraction for it (G03).

    The transcript edit always lands; insight extraction is fail-open — an
    LLM/tool failure keeps the entry and sets ``insight_skipped`` so the GM's
    correction is never lost. New candidate facts from the edited text are
    staged as pending capture proposals (idempotent per entry).
    """
    await require_universe_owner(db, principal, req.universe_id)
    ingest = SessionIngestAgent()
    try:
        doc = await ingest.update_entry(log_entry_id, req.text)
    except ValueError as exc:
        raise _entry_http_error(exc) from exc
    _evict_recorder_messages(str(doc.get("session_id") or ""))

    insight: CaptureInsight | None = None
    insight_skipped = False
    try:
        insight = await CaptureInsightAgent().analyze_entry(
            universe_id=req.universe_id,
            entry_text=req.text,
        )
    except Exception as exc:  # noqa: BLE001  # reason: fail-open contract — entry kept, insight skipped (in update_session_log_entry)
        insight_skipped = True
        log.warning("session_entry_insight_rerun_failed", entry_id=log_entry_id, error=str(exc))

    proposal_ids: list[str] = []
    proposal_errors: list[str] = []
    if insight is not None:
        proposal_ids, proposal_errors = await _create_capture_proposals(
            CaptureInsightsRequest(
                universe_id=req.universe_id,
                entry_text=req.text,
                entry_id=log_entry_id,
                story_id=req.story_id,
                scene_id=req.scene_id,
            ),
            insight,
        )
    return SessionLogEntryPatchResponse(
        entry=_entry_from_doc(doc),
        insight=insight,
        insight_skipped=insight_skipped,
        proposal_ids=proposal_ids,
        proposal_errors=proposal_errors,
    )


@router.delete(
    "/gm/session-log/entries/{log_entry_id}",
    response_model=SessionLogEntryStrikeResponse,
)
async def strike_session_log_entry(log_entry_id: str) -> SessionLogEntryStrikeResponse:
    """Strike (soft-delete) a logged entry — session-owner only (G03).

    Also retracts the entry's still-pending capture proposals with reason
    "struck at the table", recording their ids on the entry so the undo can
    restore exactly those. Retracts are best-effort: one already-decided
    proposal never blocks the strike itself.
    """
    # Ownership: resource_route_guard resolves log_entry_id → session owner.
    ingest = SessionIngestAgent()
    try:
        existing = await ingest.get_entry(log_entry_id)
    except ValueError as exc:
        raise _entry_http_error(exc) from exc
    if existing is None:
        raise HTTPException(status_code=404, detail="Not found")

    capture = CaptureInsightAgent()
    retracted: list[str] = []
    errors: list[str] = []
    pending = await asyncio.to_thread(
        mongodb_list_proposed_changes,
        ProposedChangeFilter(
            source=_capture_proposal_source(log_entry_id),
            status=ProposalStatus.PENDING,
            limit=500,
        ),
    )
    for proposal in pending.proposed_changes:
        try:
            await capture.retract_proposal(
                str(proposal.proposal_id),
                reason=STRIKE_REASON,
                entry_id=log_entry_id,
            )
            retracted.append(str(proposal.proposal_id))
        except ValueError as exc:
            errors.append(f"{proposal.proposal_id}: {exc}")

    try:
        doc = await ingest.strike_entry(
            log_entry_id,
            retracted_proposal_ids=retracted,
            reason=STRIKE_REASON,
        )
    except ValueError as exc:
        raise _entry_http_error(exc) from exc
    _evict_recorder_messages(str(doc.get("session_id") or existing.get("session_id") or ""))
    return SessionLogEntryStrikeResponse(
        entry=_entry_from_doc(doc),
        retracted_proposal_ids=retracted,
        retract_errors=errors,
    )


@router.post(
    "/gm/session-log/entries/{log_entry_id}/restore",
    response_model=SessionLogEntryRestoreResponse,
)
async def restore_session_log_entry(log_entry_id: str) -> SessionLogEntryRestoreResponse:
    """Undo a strike: the entry returns to the recorder view (G03).

    The proposals retracted with the strike are flipped back to pending —
    only those recorded on the entry, and only when their decision metadata
    matches the strike (actor + reason), so a regular CF-8 rejection is never
    touched by the undo.
    """
    ingest = SessionIngestAgent()
    try:
        doc = await ingest.restore_entry(log_entry_id)
    except ValueError as exc:
        raise _entry_http_error(exc) from exc
    _evict_recorder_messages(str(doc.get("session_id") or ""))

    restored: list[str] = [str(p) for p in (doc.get("restored_proposal_ids") or [])]
    errors: list[str] = []
    capture = CaptureInsightAgent()
    for proposal_id in restored:
        try:
            await capture.restore_proposal(proposal_id)
        except ValueError as exc:
            errors.append(f"{proposal_id}: {exc}")
    return SessionLogEntryRestoreResponse(
        entry=_entry_from_doc(doc),
        restored_proposal_ids=restored,
        restore_errors=errors,
    )


@router.post(
    "/gm/session-log/proposals/{proposal_id}/retract",
    response_model=SessionLogProposalRetractResponse,
)
async def retract_session_log_proposal(
    proposal_id: str,
    body: SessionLogProposalRetractRequest | None = None,
) -> SessionLogProposalRetractResponse:
    """Retract a queued candidate proposal before wrap-up (G03).

    Owner-checked by the router guard (``proposal_id`` → scene/story chain).
    Pending → rejected with the strike reason, so CF-8 shows the proposal as
    rejected with *why* it disappeared.
    """
    try:
        UUID(proposal_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc
    reason = body.reason if body else STRIKE_REASON
    try:
        proposal = await CaptureInsightAgent().retract_proposal(proposal_id, reason=reason)
    except ValueError as exc:
        raise _entry_http_error(exc) from exc
    return SessionLogProposalRetractResponse(
        proposal_id=str(proposal.get("proposal_id") or proposal_id),
        status=str(proposal.get("status") or ""),
        reason=reason,
    )


def _parse_thread_urgency(value: str) -> ThreadUrgency:
    try:
        return ThreadUrgency(value)
    except ValueError:
        return ThreadUrgency.MEDIUM


def _uuid_or_400(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field}: {value}") from exc


# ---------------------------------------------------------------------------
# CF-14: Player-facing share links (G07)
# ---------------------------------------------------------------------------
# All four endpoints are owner-checked (universe + story) before ShareAgent
# touches storage; foreign IDs answer the same generic 404 as missing ones.


class ShareLinkRequest(BaseModel):
    """Create-or-return the story's share link."""

    universe_id: UUID
    story_id: UUID


class ShareLinkResponse(BaseModel):
    """The bearer token and the path players open."""

    story_id: str
    token: str
    share_path: str
    revoked: bool = False


class SharePublishRequest(BaseModel):
    """Publish a recap or handout to the story's share link."""

    universe_id: UUID
    story_id: UUID
    artifact_type: Literal["recap", "handout"]
    title: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1)
    spoiler_level: Literal["party", "character"] = "party"
    scope_character_id: UUID | None = None
    source_fact_ids: list[UUID] = Field(default_factory=list)
    session_id: UUID | None = None


class SharePublishResponse(BaseModel):
    """Published artifact plus the share link (auto-minted when absent)."""

    artifact_id: str
    token: str
    share_path: str
    published: bool = True


class ShareArtifactOpRequest(BaseModel):
    """Unpublish one artifact (blocks /share/* access immediately)."""

    universe_id: UUID
    artifact_id: UUID


class ShareArtifactOpResponse(BaseModel):
    artifact_id: str
    published: bool


class ShareRevokeRequest(BaseModel):
    """Revoke every live token for a story."""

    universe_id: UUID
    story_id: UUID


class ShareRevokeResponse(BaseModel):
    story_id: str
    revoked: bool


@router.get("/gm/share/link", response_model=ShareLinkResponse)
async def gm_share_link(
    universe_id: str,
    story_id: str,
    principal: Principal = Depends(get_current_user),
) -> ShareLinkResponse:
    """CF-14: fetch (or mint) the story's share link.

    Query params are owner-checked by the router-level resource_route_guard
    (story_id + universe_id are both in the resolver table).
    """
    uid = _uuid_or_400(universe_id, "universe_id")
    sid = _uuid_or_400(story_id, "story_id")
    share = await ShareAgent().ensure_share(universe_id=uid, story_id=sid, owner_id=str(principal.user_id))
    return ShareLinkResponse(
        story_id=str(sid),
        token=share.token,
        share_path=f"/share/{share.token}",
        revoked=share.revoked,
    )


@router.post("/gm/share/publish", response_model=SharePublishResponse)
async def gm_share_publish(
    req: SharePublishRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> SharePublishResponse:
    """CF-14: publish a recap/handout (Mongo only — canon untouched)."""
    await require_universe_owner(db, principal, req.universe_id)
    await require_story_owner(db, principal, req.story_id)
    try:
        share, artifact = await ShareAgent().publish(
            universe_id=req.universe_id,
            story_id=req.story_id,
            owner_id=str(principal.user_id),
            artifact_type=ShareArtifactType(req.artifact_type),
            title=req.title,
            content=req.content,
            spoiler_level=ShareSpoilerLevel(req.spoiler_level),
            scope_character_id=req.scope_character_id,
            source_fact_ids=req.source_fact_ids,
            session_id=req.session_id,
        )
    except ShareError as exc:
        log.warning("share_publish_failed", story_id=str(req.story_id), error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to publish") from exc
    return SharePublishResponse(
        artifact_id=str(artifact.id),
        token=share.token,
        share_path=f"/share/{share.token}",
        published=True,
    )


@router.post("/gm/share/unpublish", response_model=ShareArtifactOpResponse)
async def gm_share_unpublish(
    req: ShareArtifactOpRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> ShareArtifactOpResponse:
    """CF-14: unpublish an item — the /share/* routes stop serving it at once."""
    await require_universe_owner(db, principal, req.universe_id)
    ok = await ShareAgent().unpublish(
        artifact_id=req.artifact_id,
        universe_id=req.universe_id,
        owner_id=str(principal.user_id),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return ShareArtifactOpResponse(artifact_id=str(req.artifact_id), published=False)


@router.post("/gm/share/revoke", response_model=ShareRevokeResponse)
async def gm_share_revoke(
    req: ShareRevokeRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> ShareRevokeResponse:
    """CF-14: revoke the story's link — every token stops working immediately."""
    await require_universe_owner(db, principal, req.universe_id)
    await require_story_owner(db, principal, req.story_id)
    ok = await ShareAgent().revoke(
        story_id=req.story_id,
        universe_id=req.universe_id,
        owner_id=str(principal.user_id),
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return ShareRevokeResponse(story_id=str(req.story_id), revoked=True)


# ---------------------------------------------------------------------------
# Session combat tracker (CF-9)
# ---------------------------------------------------------------------------
# Ephemeral at-the-table state keyed by (universe_id, session_id): every route
# is owner-checked first, then delegates to CombatAgent (Layer 2), which calls
# the mongodb_combat_* tools over MCP. Nothing here writes Neo4j — permanent
# effects leave only as ProposedChange items in the CF-8 queue.


class CombatInitiativeRequest(BaseModel):
    """Initiative rolls for the encounter; ``narrate`` adds read-aloud text."""

    universe_id: UUID
    entries: list[CombatInitiativeEntry] = Field(min_length=1)
    narrate: bool = Field(default=False, description="Also return an LLM narration of the order")


class CombatInitiativeResponse(BaseModel):
    state: CombatSessionState
    narration: str | None = None


class CombatantPatchRequest(BaseModel):
    """HP / condition / flag adjustments for one combatant (path supplies ids).

    String fields follow the set/clear contract: ``None`` leaves the value
    unchanged, ``""`` clears it.
    """

    universe_id: UUID
    hp: int | None = Field(None, ge=0, description="Absolute HP (clamped to max_hp)")
    hp_delta: int | None = Field(
        None,
        description="Negative = damage (temp HP absorbed first), positive = healing",
    )
    temp_hp: int | None = Field(None, ge=0, description="Absolute temp HP")
    conditions_add: list[str] = Field(default_factory=list)
    conditions_remove: list[str] = Field(default_factory=list)
    dead: bool | None = None
    unconscious: bool | None = None
    concentration: str | None = Field(None, max_length=500, description="None = unchanged, '' = clear")
    notes: str | None = Field(None, max_length=2000, description="None = unchanged, '' = clear")


class CombatRoundRequest(BaseModel):
    universe_id: UUID


class CombatEndRequest(BaseModel):
    """End the encounter; optional ``world_effects`` are GM-declared faction /
    lore consequences staged for the CF-8 queue alongside casualty proposals."""

    universe_id: UUID
    story_id: UUID | None = None
    scene_id: UUID | None = None
    world_effects: list[str] = Field(
        default_factory=list,
        description="Faction/lore consequences the GM declares at the end",
    )


class CombatEndResponse(BaseModel):
    state: CombatSessionState
    proposal_ids: list[str] = Field(default_factory=list)
    proposal_errors: list[str] = Field(default_factory=list)
    summary: str | None = Field(None, description="Best-effort LLM summary; None when unavailable")


class ConditionExplainRequest(BaseModel):
    universe_id: UUID
    condition: str = Field(min_length=1, max_length=100)
    system_id: UUID | None = Field(None, description="Defaults to the universe's bound system")


def _combat_error(exc: Exception) -> HTTPException:
    """Map combat state-machine failures to HTTP errors."""
    detail = str(exc)
    if "No combat encounter" in detail or "not found in encounter" in detail:
        return HTTPException(status_code=404, detail=detail)
    if "already ended" in detail:
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=400, detail=detail)


@router.post("/gm/combat/start", response_model=CombatSessionState)
async def combat_start(
    req: CombatStart,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> CombatSessionState:
    """Start (or restart) the at-the-table encounter for (universe, session)."""
    await require_universe_owner(db, principal, req.universe_id)
    agent = CombatAgent()
    try:
        return await agent.start_encounter(req)
    except ValueError as exc:
        raise _combat_error(exc) from exc
    except Exception as exc:
        log.warning("combat_start_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to start combat: {exc}") from exc


@router.get("/gm/combat/{session_id}", response_model=CombatSessionState)
async def combat_get(
    session_id: str,
    universe_id: UUID,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> CombatSessionState:
    """The live encounter state, or 404 when no encounter exists for the key."""
    await require_universe_owner(db, principal, universe_id)
    agent = CombatAgent()
    try:
        state = await agent.get_state(universe_id, session_id)
    except ValueError as exc:
        raise _combat_error(exc) from exc
    except Exception as exc:
        log.warning("combat_get_failed", universe_id=str(universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to load combat: {exc}") from exc
    if state is None:
        raise HTTPException(status_code=404, detail="No combat encounter for this session")
    return state


@router.post("/gm/combat/{session_id}/initiative", response_model=CombatInitiativeResponse)
async def combat_set_initiative_route(
    session_id: str,
    req: CombatInitiativeRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> CombatInitiativeResponse:
    """Record initiative rolls; the turn order is computed deterministically.

    The optional narration is best-effort: the order is already stored when it
    runs, so an LLM failure degrades to ``narration=None`` instead of failing
    the initiative roll the GM is waiting on.
    """
    await require_universe_owner(db, principal, req.universe_id)
    agent = CombatAgent()
    try:
        state = await agent.set_initiative(
            CombatSetInitiative(
                universe_id=req.universe_id,
                session_id=session_id,
                entries=req.entries,
            )
        )
    except ValueError as exc:
        raise _combat_error(exc) from exc
    except Exception as exc:
        log.warning("combat_initiative_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to set initiative: {exc}") from exc

    narration: str | None = None
    if req.narrate:
        try:
            narration = await agent.narrate_initiative(state)
        except Exception as exc:  # noqa: BLE001  # reason: narration is optional enrichment; the order is already stored (in combat_set_initiative_route)
            log.warning("combat_narration_failed", session_id=session_id, error=str(exc))
    return CombatInitiativeResponse(state=state, narration=narration)


@router.patch("/gm/combat/{session_id}/combatant/{combatant_id}", response_model=CombatSessionState)
async def combat_patch_combatant(
    session_id: str,
    combatant_id: UUID,
    req: CombatantPatchRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> CombatSessionState:
    """Adjust one combatant's HP / temp HP / conditions / flags / notes."""
    await require_universe_owner(db, principal, req.universe_id)
    agent = CombatAgent()
    try:
        return await agent.update_combatant(
            CombatUpdateCombatant(
                universe_id=req.universe_id,
                session_id=session_id,
                combatant_id=combatant_id,
                hp=req.hp,
                hp_delta=req.hp_delta,
                temp_hp=req.temp_hp,
                conditions_add=req.conditions_add,
                conditions_remove=req.conditions_remove,
                dead=req.dead,
                unconscious=req.unconscious,
                concentration=req.concentration,
                notes=req.notes,
            )
        )
    except ValueError as exc:
        raise _combat_error(exc) from exc
    except Exception as exc:
        log.warning(
            "combat_update_combatant_failed",
            universe_id=str(req.universe_id),
            combatant_id=str(combatant_id),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Failed to update combatant: {exc}") from exc


@router.post("/gm/combat/{session_id}/next-round", response_model=CombatSessionState)
async def combat_next_round_route(
    session_id: str,
    req: CombatRoundRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> CombatSessionState:
    """Advance the encounter to the next round."""
    await require_universe_owner(db, principal, req.universe_id)
    agent = CombatAgent()
    try:
        return await agent.next_round(CombatNextRound(universe_id=req.universe_id, session_id=session_id))
    except ValueError as exc:
        raise _combat_error(exc) from exc
    except Exception as exc:
        log.warning("combat_next_round_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to advance round: {exc}") from exc


@router.post("/gm/combat/{session_id}/end", response_model=CombatEndResponse)
async def combat_end_route(
    session_id: str,
    req: CombatEndRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> CombatEndResponse:
    """End the encounter and stage its world effects for CanonKeeper (CF-8).

    Deterministic order: validate staging scope → end the state → stage one
    FACT proposal per casualty and per GM-declared world effect (deduped by
    the ``combat_end:<session>`` source tag) → best-effort LLM summary. The
    summary never blocks or rolls back the end.
    """
    await require_universe_owner(db, principal, req.universe_id)
    agent = CombatAgent()
    try:
        state = await agent.get_state(req.universe_id, session_id)
    except ValueError as exc:
        raise _combat_error(exc) from exc
    except Exception as exc:
        log.warning("combat_end_get_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to load combat: {exc}") from exc
    if state is None:
        raise HTTPException(status_code=404, detail="No combat encounter for this session")

    story_id = req.story_id or state.story_id
    scene_id = req.scene_id or state.scene_id
    deaths = [c for c in state.combatants if c.dead]
    effects = [e.strip() for e in req.world_effects if e.strip()]
    if (deaths or effects) and story_id is None and scene_id is None:
        raise HTTPException(
            status_code=422,
            detail="Provide story_id or scene_id so end-of-encounter proposals can be staged.",
        )

    try:
        state = await agent.end_encounter(CombatEnd(universe_id=req.universe_id, session_id=session_id))
    except ValueError as exc:
        raise _combat_error(exc) from exc
    except Exception as exc:
        log.warning("combat_end_failed", universe_id=str(req.universe_id), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to end combat: {exc}") from exc

    proposal_ids: list[str] = []
    proposal_errors: list[str] = []
    if deaths or effects:
        source = f"combat_end:{session_id}"
        staged: list[tuple[str, str, list[str]]] = [
            (f"{c.name} died in combat", "combat_casualty", [c.name]) for c in deaths
        ]
        staged += [(effect, "combat_world_effect", []) for effect in effects]

        def _stage() -> tuple[list[str | None], list[str]]:
            ids: list[str | None] = []
            errs: list[str] = []
            existing = mongodb_list_proposed_changes(ProposedChangeFilter(source=source, limit=1000))
            existing_statements = {
                str(p.content.get("statement") or "").strip()
                for p in existing.proposed_changes
                if isinstance(p.content, dict)
            }
            for statement, ptype, participants in staged:
                if statement in existing_statements:
                    continue
                try:
                    proposal = mongodb_create_proposed_change(
                        ProposedChangeCreate(
                            scene_id=scene_id,
                            story_id=story_id,
                            change_type=ProposalType.FACT,
                            content={
                                "statement": statement,
                                "fact_type": "occurrence",
                                "canon_level": "proposed",
                                "participants": participants,
                                "universe_id": str(state.universe_id),
                            },
                            confidence=0.9,
                            authority=Authority.GM,
                            proposer="CombatAgent",
                            source=source,
                            proposal_type=ptype,
                        )
                    )
                    ids.append(str(proposal.proposal_id))
                    existing_statements.add(statement)
                except Exception as exc:  # noqa: BLE001  # reason: one bad proposal must not lose the rest of the batch (in combat_end_route)
                    ids.append(None)
                    errs.append(f"{statement[:80]}: {exc}")
            return ids, errs

        created, proposal_errors = await asyncio.to_thread(_stage)
        proposal_ids = [pid for pid in created if pid]

    summary: str | None = None
    try:
        summary = await agent.summarize_encounter(state)
    except Exception as exc:  # noqa: BLE001  # reason: summary is optional enrichment; state is already ended (in combat_end_route)
        log.warning("combat_summary_failed", session_id=session_id, error=str(exc))

    return CombatEndResponse(
        state=state,
        proposal_ids=proposal_ids,
        proposal_errors=proposal_errors,
        summary=summary,
    )


@router.post("/gm/combat/condition-explain", response_model=ConditionExplanation)
async def combat_explain_condition(
    req: ConditionExplainRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> ConditionExplanation:
    """What a condition tag does: structured definition from the bound game
    system when it has one, free-text guidance otherwise (G01 open decision)."""
    await require_universe_owner(db, principal, req.universe_id)
    system_id = req.system_id
    system_name: str | None = None
    if system_id is None:
        binding = await asyncio.to_thread(resolve_universe_system_binding, str(req.universe_id))
        bound = binding.get("system_id")
        system_id = UUID(str(bound)) if bound else None
        system_name = binding.get("system_name")
    agent = CombatAgent()
    try:
        return await agent.explain_condition(req.condition, system_id=system_id, system_name=system_name)
    except Exception as exc:
        log.warning(
            "combat_condition_explain_failed",
            universe_id=str(req.universe_id),
            condition=req.condition,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Failed to explain condition: {exc}") from exc


# ---------------------------------------------------------------------------
# Encounter difficulty (CF-13 / G06)
# ---------------------------------------------------------------------------
# "Is this fight fair?" — the prep assistant suggests encounters and
# improvises NPCs, but nothing compared a suggested fight to the party that
# would actually fight it. The estimate is arithmetic (see
# ``monitor_agents.game_system.difficulty``) and shows its working, because
# a difficulty label the GM cannot check is a difficulty label they will
# not trust.


class EncounterFoeRequest(BaseModel):
    """One opponent in a proposed encounter."""

    name: str = Field(min_length=1, max_length=200)
    count: int = Field(default=1, ge=1, le=100)
    hit_points: int | None = Field(default=None, ge=0)
    attack_bonus: int | None = Field(default=None)
    entity_id: UUID | None = Field(default=None, description="Resolve the missing numbers from this entity")


class EncounterPartyMemberRequest(BaseModel):
    """One member of the party that would face the encounter."""

    name: str = Field(min_length=1, max_length=200)
    level: int | None = Field(default=None, ge=0)
    hit_points: int | None = Field(default=None, ge=0)
    character_id: UUID | None = Field(default=None, description="Resolve the missing numbers from this character")


class EncounterCheckRequest(BaseModel):
    """A proposed encounter and the party facing it."""

    universe_id: UUID
    foes: list[EncounterFoeRequest] = Field(min_length=1)
    party: list[EncounterPartyMemberRequest] = Field(min_length=1)


class EncounterCheckResponse(BaseModel):
    """The difficulty verdict and the arithmetic behind it."""

    label: str
    rationale: str
    threat: float = 0.0
    party_budget: float = 0.0
    ratio: float | None = None
    basis: str = "unrated"
    details: dict[str, Any] = Field(default_factory=dict)


@router.post("/gm/encounter/check", response_model=EncounterCheckResponse)
async def check_encounter_difficulty(
    req: EncounterCheckRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> EncounterCheckResponse:
    """Estimate how fair a proposed encounter is for a party (CF-13).

    The bound game system's own difficulty rules are used when it has any;
    otherwise the generic convention applies. A universe whose party or
    foes carry no numbers gets ``unrated`` rather than a guess.
    """
    await require_universe_owner(db, principal, req.universe_id)
    system_doc = await asyncio.to_thread(get_game_system_doc, str(req.universe_id))
    try:
        estimate = await EncounterDifficultyAgent().estimate(
            universe_id=req.universe_id,
            foes=[foe.model_dump(mode="json") for foe in req.foes],
            party=[member.model_dump(mode="json") for member in req.party],
            system_doc=system_doc,
        )
    except Exception as exc:
        log.warning(
            "encounter_difficulty_failed",
            universe_id=str(req.universe_id),
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail=f"Failed to estimate encounter difficulty: {exc}") from exc
    return EncounterCheckResponse(
        label=estimate.label,
        rationale=estimate.rationale,
        threat=estimate.threat,
        party_budget=estimate.party_budget,
        ratio=estimate.ratio,
        basis=estimate.basis,
        details=estimate.details,
    )


# ---------------------------------------------------------------------------
# Knowledge inspector (CF-15 / G09)
# ---------------------------------------------------------------------------
# "What do they know?" is answerable ("/gm/lookup/party-knowledge"). "Is
# that right?" was not: there was no view of the facts and memories the
# system attributes to a character, with their provenance, and no way to
# correct one that is wrong.


class KnowledgeAuditRequest(BaseModel):
    """Which character's knowledge to audit."""

    universe_id: UUID
    entity_id: UUID


class KnowledgeAuditResponse(BaseModel):
    """Everything the system attributes to the character."""

    entity_id: UUID
    universe_id: UUID | None = None
    items: list[KnowledgeItem] = Field(default_factory=list)
    fact_count: int = 0
    memory_count: int = 0
    proposal_count: int = 0
    suspicious_count: int = 0


class KnowledgeChallengeRequest(BaseModel):
    """A GM disputing one attribution."""

    universe_id: UUID
    statement: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    item_id: str = Field(min_length=1, max_length=200)
    item_kind: Literal["fact", "memory", "proposal"] = "memory"
    action: Literal["retract", "correct"] = "retract"
    story_id: UUID | None = None
    scene_id: UUID | None = None


class KnowledgeChallengeResponse(BaseModel):
    """The staged correction."""

    proposal_id: str
    entity_id: UUID


@router.get("/gm/knowledge/{entity_id}", response_model=KnowledgeAuditResponse)
async def audit_character_knowledge(
    entity_id: str,
    universe_id: str,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> KnowledgeAuditResponse:
    """What the system believes a character knows, with its provenance (CF-15).

    Every item says where it came from — the scene it was formed in, the
    fact they witnessed, the proposal still waiting for review — and the
    doubtful attributions are marked.
    """
    uid = _uuid_or_400(universe_id, "universe_id")
    eid = _uuid_or_400(entity_id, "entity_id")
    await require_universe_owner(db, principal, uid)
    try:
        audit = await KnowledgeAuditAgent().audit(entity_id=eid, universe_id=uid)
    except Exception as exc:
        log.warning("knowledge_audit_failed", entity_id=str(eid), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to audit knowledge: {exc}") from exc
    return KnowledgeAuditResponse(**audit.model_dump())


@router.post("/gm/knowledge/{entity_id}/challenge", response_model=KnowledgeChallengeResponse)
async def challenge_character_knowledge(
    entity_id: str,
    req: KnowledgeChallengeRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> KnowledgeChallengeResponse:
    """Challenge one attribution: stage a correction for the CF-8 queue (CF-15).

    The correction is a proposal, not a write — CanonKeeper decides, and the
    GM's objection shows up in the review trail like any other change.
    """
    eid = _uuid_or_400(entity_id, "entity_id")
    await require_universe_owner(db, principal, req.universe_id)
    try:
        proposal_id = await KnowledgeAuditAgent().challenge(
            entity_id=eid,
            universe_id=req.universe_id,
            challenge=KnowledgeChallenge(
                item_id=req.item_id,
                kind=req.item_kind,
                statement=req.statement,
                reason=req.reason,
                action=req.action,
            ),
            story_id=req.story_id,
            scene_id=req.scene_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.warning("knowledge_challenge_failed", entity_id=str(eid), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to stage the correction: {exc}") from exc
    return KnowledgeChallengeResponse(proposal_id=proposal_id, entity_id=eid)
