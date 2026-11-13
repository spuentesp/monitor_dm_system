"""CanonKeeper review queue router — CF-8 (scene review) + I-4 (Forge mount).

Exposes the scene-by-scene review surface that lets a human GM audit what
MONITOR is about to add to the world. Wires ``mongodb_list_proposed_changes``
and ``mongodb_update_proposed_change`` to a UI-friendly aggregate payload.
The by-ingest commit endpoint goes through CanonKeeper (agents layer) —
the only Neo4j writer.

Mounted by the CF-8 CanonReviewPanel (Play/GM consoles) and by the unified
three-scope review page at ``/forge/review`` (F1-4): pack proposals,
ingestion jobs (``/canon-review/by-ingest/*``), and story/scene queues.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer, agents (CanonKeeper — same pattern as pack_library)
"""

from __future__ import annotations

import hashlib
import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_data.schemas.base import ProposalStatus, ProposalType
from monitor_data.schemas.proposed_changes import (
    CanonOverrideRecord,
    DecisionMetadata,
    ProposalReviewFlag,
    ProposedChangeFilter,
    ProposedChangeResponse,
    ProposedChangeUpdate,
)
from monitor_data.db.postgres import PostgresClient
from monitor_data.tools.mongodb_tools import (
    mongodb_defer_proposed_change,
    mongodb_edit_proposed_change,
    mongodb_flag_proposal_review,
    mongodb_get_ingestion_job,
    mongodb_get_proposed_change,
    mongodb_get_scene,
    mongodb_list_proposed_changes,
    mongodb_record_canon_override,
    mongodb_update_proposed_change,
)
from monitor_data.config import get_settings
from monitor_ui.auth import Principal, get_current_user, get_postgres, is_local_mode
from monitor_ui.ownership import (
    _universe_of_scene,
    _universe_of_story,
    require_proposal_owner,
    require_scene_owner,
    require_story_owner,
    require_universe_owner,
    resource_route_guard,
)
from pydantic import BaseModel, Field

from .ingest_shared import db_op, validate_uuid


router = APIRouter(dependencies=[Depends(resource_route_guard)])
log = structlog.get_logger()


# ---------------------------------------------------------------------------
# UI-layer request/response shapes
# ---------------------------------------------------------------------------


class VerdictItem(BaseModel):
    """Single review item: which proposal, accept/reject, why."""

    proposal_id: UUID
    decision: ProposalStatus  # ACCEPTED or REJECTED
    reason: str


class ProposalDeferRequest(BaseModel):
    """Defer a pending proposal without making a final verdict."""

    reason: str = Field(min_length=1, max_length=2000)
    deferred_by: str = Field(default="GM", max_length=100)


class ProposalEditRequest(BaseModel):
    """Edit a pending proposal before accepting or rejecting it."""

    content_patch: dict[str, Any] = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=2000)
    edited_by: str = Field(default="GM", max_length=100)


class BatchVerdictRequest(BaseModel):
    """Apply multiple accept/reject decisions at once (one round-trip)."""

    decided_by: str = Field(default="GM", description="Who is making the decision")
    items: list[VerdictItem]


class BatchVerdictError(BaseModel):
    """A single verdict that failed inside a batch (e.g. 409 conflict)."""

    proposal_id: UUID
    error: str


class BatchVerdictResponse(BaseModel):
    """Per-item outcome of a batch verdict request.

    Each item is processed independently: successes land in ``results``,
    failures in ``errors`` — one item's failure never blocks the others.
    """

    results: list[ProposedChangeResponse]
    errors: list[BatchVerdictError] = Field(default_factory=list)


class VerdictByFilterRequest(BaseModel):
    """Server-side bulk verdict over every proposal matching a filter set.

    Used by the "select all matching active filters" flow (F2-3c): the
    client first calls with ``dry_run=True`` to get the affected count and a
    ``preview_token``, then re-calls with ``dry_run=False`` and the token to
    execute. The token binds the decision payload to the exact set of
    proposal IDs matched at preview time, so a changed filter or a changed
    dataset between preview and execute is rejected instead of silently
    applying to a different set.
    """

    decided_by: str = Field(default="GM", description="Who is making the decision")
    decision: ProposalStatus  # ACCEPTED or REJECTED
    reason: str = Field(min_length=1, max_length=2000)
    # Scope + filter set (mirrors the workbench filter bar).
    story_id: UUID | None = None
    scene_id: UUID | None = None
    source: str | None = Field(
        default=None,
        description="Source tag, e.g. 'knowledge_pack:<uuid>' or 'ingestion_job:<uuid>'",
    )
    status: ProposalStatus | None = Field(default=None, description="Defaults to PENDING when omitted")
    change_type: ProposalType | None = None
    # G-9 Phase 2 — restrict the bulk set to flagged / unflagged proposals.
    needs_review: bool | None = Field(default=None)
    confidence_min: float | None = Field(default=None, ge=0.0, le=1.0)
    confidence_max: float | None = Field(default=None, ge=0.0, le=1.0)
    created_after: datetime | None = None
    created_before: datetime | None = None
    search: str | None = Field(
        default=None,
        description="Case-insensitive substring match over content, proposer, proposal_type",
    )
    dry_run: bool = Field(
        default=True,
        description="True: preview only (count + token). False: execute (token required).",
    )
    preview_token: str | None = None


class VerdictByFilterResponse(BaseModel):
    """Outcome of a by-filter verdict call.

    Dry-run: only ``affected_count`` and ``preview_token`` are meaningful.
    Execute: ``results``/``errors`` carry the per-item outcome (same
    partial-failure contract as ``BatchVerdictResponse``).
    """

    affected_count: int
    preview_token: str | None = None
    results: list[ProposedChangeResponse] = Field(default_factory=list)
    errors: list[BatchVerdictError] = Field(default_factory=list)


class SceneReviewResponse(BaseModel):
    """Per-scene CanonKeeper review payload.

    ``scene_id`` is ``None`` for the story-level lane: proposals that belong
    to the story but were not attributed to any scene (F2-3).
    """

    scene_id: UUID | None = None
    summary: str | None = None
    participants: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    pending: list[ProposedChangeResponse]
    deferred: list[ProposedChangeResponse] = Field(default_factory=list)
    accepted: list[ProposedChangeResponse]
    rejected: list[ProposedChangeResponse]
    by_change_type: dict[str, int]


class CanonQueueResponse(BaseModel):
    """Story-level CanonKeeper queue: every scene that has any open items."""

    story_id: UUID
    scenes: list[SceneReviewResponse]
    total_pending: int
    total_deferred: int = 0


class IngestProposalItem(BaseModel):
    """Normalized proposal shape for the by-ingest review surface.

    Field-for-field compatible with the pack-proposal shape the frontend
    already renders (``ProposalItem`` — proposal_id, change_type, content,
    confidence, authority, proposer, status, evidence, created_at), plus
    the extraction subtype (``proposal_type``) and source lineage
    (``source``) required by F1-4.
    """

    proposal_id: str
    change_type: str
    proposal_type: str | None = None
    status: str
    source: str | None = None
    content: dict[str, Any]
    confidence: float
    authority: str
    proposer: str
    evidence: list[dict[str, str]] = Field(default_factory=list)
    created_at: str | None = None


class IngestionJobReviewResponse(BaseModel):
    """Per-ingestion-job CanonKeeper review payload.

    Surfaces every proposal tagged ``source=ingestion_job:<uuid>`` so the
    UI can group them under the ingest that produced them — distinct from
    scene-runtime proposals, which appear under
    ``/scenes/{scene_id}/canon-review``.
    """

    ingestion_job_id: UUID
    pending: list[IngestProposalItem]
    accepted: list[IngestProposalItem]
    rejected: list[IngestProposalItem]
    by_change_type: dict[str, int]


BatchVerdictRequest.model_rebuild()


# ---------------------------------------------------------------------------
# Per-scene review
# ---------------------------------------------------------------------------


def _scene_review_context(
    proposals: list[ProposedChangeResponse],
) -> tuple[str | None, list[str], list[str]]:
    """Derive the scene summary and its participants/locations from proposals."""
    participants: list[str] = []
    locations: list[str] = []
    summary: str | None = None
    for proposal in proposals:
        content = proposal.content if isinstance(proposal.content, dict) else {}
        participants.extend(str(p) for p in content.get("participants", []) if str(p).strip())
        locations.extend(str(loc) for loc in content.get("locations", []) if str(loc).strip())
        if summary is None:
            candidate = content.get("summary") or content.get("scene_summary") or content.get("source_excerpt")
            if candidate:
                summary = str(candidate)[:500]
    return summary, sorted(set(participants)), sorted(set(locations))


@router.get("/scenes/{scene_id}/canon-review", response_model=SceneReviewResponse)
async def scene_canon_review(scene_id: str) -> SceneReviewResponse:
    """Return every proposal for a scene, grouped by status and change type.

    This is the data behind the CF-8 "CanonKeeper Review" panel.
    """
    scene_uuid = validate_uuid(scene_id, "scene_id")
    with db_op():
        # Single round-trip: filter by scene_id, all statuses.
        resp = mongodb_list_proposed_changes(ProposedChangeFilter(scene_id=scene_uuid, limit=500))

    pending: list[ProposedChangeResponse] = []
    deferred: list[ProposedChangeResponse] = []
    accepted: list[ProposedChangeResponse] = []
    rejected: list[ProposedChangeResponse] = []
    by_type: dict[str, int] = defaultdict(int)

    for proposal in resp.proposed_changes:
        if proposal.status == ProposalStatus.PENDING:
            (deferred if proposal.deferred else pending).append(proposal)
        elif proposal.status == ProposalStatus.ACCEPTED:
            accepted.append(proposal)
        elif proposal.status == ProposalStatus.REJECTED:
            rejected.append(proposal)
        by_type[proposal.change_type.value] += 1

    summary, participants, locations = _scene_review_context(resp.proposed_changes)
    return SceneReviewResponse(
        scene_id=scene_uuid,
        summary=summary,
        participants=participants,
        locations=locations,
        pending=pending,
        deferred=deferred,
        accepted=accepted,
        rejected=rejected,
        by_change_type=dict(by_type),
    )


# ---------------------------------------------------------------------------
# Story-level queue
# ---------------------------------------------------------------------------


@router.get("/stories/{story_id}/canon-queue", response_model=CanonQueueResponse)
async def story_canon_queue(
    story_id: str,
    only_pending: bool = Query(
        default=True,
        description="If true, only scenes with at least one PENDING proposal are listed",
    ),
) -> CanonQueueResponse:
    """List every scene in a story that has canon-worthy proposals.

    Each entry is a full :class:`SceneReviewResponse` so the UI can render
    one review card per scene. Proposals with no ``scene_id`` (story-level)
    are grouped into a lane with ``scene_id=None`` — they used to be dropped
    silently (F2-3).
    """
    story_uuid = validate_uuid(story_id, "story_id")
    with db_op():
        resp = mongodb_list_proposed_changes(ProposedChangeFilter(story_id=story_uuid, limit=1000))

    # Group by scene_id, preserving insertion order. The None key is the
    # story-level lane (proposals not attributed to any scene).
    per_scene: dict[UUID | None, list[ProposedChangeResponse]] = defaultdict(list)
    for proposal in resp.proposed_changes:
        per_scene[proposal.scene_id].append(proposal)

    scenes_out: list[SceneReviewResponse] = []
    total_pending = 0
    total_deferred = 0
    for scene_id, proposals in per_scene.items():
        pending = [p for p in proposals if p.status == ProposalStatus.PENDING and not p.deferred]
        deferred = [p for p in proposals if p.status == ProposalStatus.PENDING and p.deferred]
        accepted = [p for p in proposals if p.status == ProposalStatus.ACCEPTED]
        rejected = [p for p in proposals if p.status == ProposalStatus.REJECTED]
        if only_pending and not pending and not deferred:
            continue
        by_type: dict[str, int] = defaultdict(int)
        for p in proposals:
            by_type[p.change_type.value] += 1
        summary, participants, locations = _scene_review_context(proposals)
        scenes_out.append(
            SceneReviewResponse(
                scene_id=scene_id,
                summary=summary,
                participants=participants,
                locations=locations,
                pending=pending,
                deferred=deferred,
                accepted=accepted,
                rejected=rejected,
                by_change_type=dict(by_type),
            )
        )
        total_pending += len(pending)
        total_deferred += len(deferred)

    return CanonQueueResponse(
        story_id=story_uuid,
        scenes=scenes_out,
        total_pending=total_pending,
        total_deferred=total_deferred,
    )


# ---------------------------------------------------------------------------
# Per-ingestion-job review (Gap 5)
# ---------------------------------------------------------------------------


def _to_ingest_item(p: ProposedChangeResponse) -> IngestProposalItem:
    """Map a ProposedChangeResponse to the normalized by-ingest shape."""
    return IngestProposalItem(
        proposal_id=str(p.proposal_id),
        change_type=p.change_type.value,
        proposal_type=p.proposal_type,
        status=p.status.value,
        source=p.source,
        content=p.content,
        confidence=p.confidence,
        authority=p.authority.value if hasattr(p.authority, "value") else str(p.authority),
        proposer=p.proposer,
        evidence=[{"type": e.type, "ref_id": str(e.ref_id)} for e in p.evidence],
        created_at=p.created_at.isoformat() if p.created_at else None,
    )


@router.get(
    "/canon-review/by-ingest/{ingestion_job_id}",
    response_model=IngestionJobReviewResponse,
)
async def ingestion_job_canon_review(
    ingestion_job_id: str,
    status_filter: ProposalStatus | None = Query(
        default=None,
        description="Optional status filter (default: all statuses, grouped)",
    ),
) -> IngestionJobReviewResponse:
    """Return every proposal tagged ``source=ingestion_job:<uuid>``.

    This is the review surface for ingest-time proposals — distinct from
    the scene-runtime queue at ``/scenes/{scene_id}/canon-review``. When
    ``MONITOR_AUTO_CANONIZE=0`` (the default), every ingest lands
    here for operator approval before any Neo4j write.

    Each proposal is returned in the normalized :class:`IngestProposalItem`
    shape — the same field names the pack-proposal review UI renders.
    """
    job_uuid = validate_uuid(ingestion_job_id, "ingestion_job_id")
    source_key = f"ingestion_job:{job_uuid}"
    with db_op():
        resp = mongodb_list_proposed_changes(
            ProposedChangeFilter(
                source=source_key,
                status=status_filter,
                limit=1000,
            )
        )

    pending: list[IngestProposalItem] = []
    accepted: list[IngestProposalItem] = []
    rejected: list[IngestProposalItem] = []
    by_type: dict[str, int] = defaultdict(int)

    for p in resp.proposed_changes:
        by_type[p.change_type.value] += 1
        item = _to_ingest_item(p)
        if p.status == ProposalStatus.PENDING:
            pending.append(item)
        elif p.status == ProposalStatus.ACCEPTED:
            accepted.append(item)
        elif p.status == ProposalStatus.REJECTED:
            rejected.append(item)

    return IngestionJobReviewResponse(
        ingestion_job_id=job_uuid,
        pending=pending,
        accepted=accepted,
        rejected=rejected,
        by_change_type=dict(by_type),
    )


@router.post("/canon-review/by-ingest/{ingestion_job_id}/commit")
async def commit_accepted_by_ingest(ingestion_job_id: str) -> dict[str, Any]:
    """Commit all ACCEPTED proposals for an ingestion job to Neo4j (I-4).

    By-ingest counterpart of ``POST /packs/{pack_id}/commit``: by-ingest
    proposals carry ``source=ingestion_job:<id>`` (not
    ``knowledge_pack:<id>``), so the pack commit path never sees them.
    Goes through CanonKeeper — the only Neo4j writer. Rejected proposals
    are left in MongoDB for audit.
    """
    job_uuid = validate_uuid(ingestion_job_id, "ingestion_job_id")

    try:
        keeper = CanonKeeper()
        result = await keeper.commit_accepted_for_job(job_uuid)
    except Exception as exc:
        raise HTTPException(500, f"Commit failed: {exc}") from exc

    return {
        "ingestion_job_id": ingestion_job_id,
        "committed": result["committed"],
        "errors": result["errors"],
        "status": "done" if not result["errors"] else "partial",
    }


# ---------------------------------------------------------------------------
# Verdict actions
# ---------------------------------------------------------------------------


@router.post("/canon-review/verdicts", response_model=BatchVerdictResponse)
async def apply_verdicts(
    body: BatchVerdictRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> BatchVerdictResponse:
    """Apply a batch of accept/reject decisions in one call.

    Each item is processed independently; failures for one item do not
    block the others. Successful updates are returned in ``results``;
    per-item failures (e.g. a proposal that was already decided) are
    collected in ``errors`` so the UI can report a partial failure
    instead of a blanket success.
    """
    # Request-shape errors still fail fast: a decision that is not
    # ACCEPTED/REJECTED is a client bug, not a per-item failure.
    for item in body.items:
        if item.decision not in (ProposalStatus.ACCEPTED, ProposalStatus.REJECTED):
            raise HTTPException(
                status_code=400,
                detail=f"Decision for {item.proposal_id} must be ACCEPTED or REJECTED",
            )
        await require_proposal_owner(db, principal, item.proposal_id)

    results: list[ProposedChangeResponse] = []
    errors: list[BatchVerdictError] = []
    for item in body.items:
        if item.decision == ProposalStatus.ACCEPTED:
            try:
                results.append(await accept_proposal(str(item.proposal_id), item.reason, None, principal, db, body.decided_by or "GM"))
            except HTTPException as exc:
                errors.append(BatchVerdictError(proposal_id=item.proposal_id, error=str(exc.detail)))
            continue
        with db_op():
            try:
                updated = mongodb_update_proposed_change(
                    item.proposal_id,
                    ProposedChangeUpdate(
                        status=item.decision,
                        decision_metadata=DecisionMetadata(
                            decided_by=body.decided_by or "GM",
                            decided_at=datetime.now(UTC),
                            reason=item.reason,
                        ),
                    ),
                )
                results.append(updated)
            except ValueError as exc:
                # Per-item failure (already decided, not found, ...) — record
                # and continue with the rest of the batch.
                errors.append(BatchVerdictError(proposal_id=item.proposal_id, error=str(exc)))
    return BatchVerdictResponse(results=results, errors=errors)


# ---------------------------------------------------------------------------
# Bulk verdicts by filter (F2-3c — "select all matching active filters")
# ---------------------------------------------------------------------------

_BY_FILTER_PAGE_SIZE = 1000


def _as_aware(dt: datetime) -> datetime:
    """Treat naive datetimes (pymongo's default) as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _matches_client_filters(p: ProposedChangeResponse, body: VerdictByFilterRequest) -> bool:
    """Post-filters MongoDB can't express via ProposedChangeFilter."""
    if body.needs_review is not None and bool(p.needs_review) != body.needs_review:
        return False
    if body.confidence_min is not None and p.confidence < body.confidence_min:
        return False
    if body.confidence_max is not None and p.confidence > body.confidence_max:
        return False
    if body.created_after is not None and (
        p.created_at is None or _as_aware(p.created_at) < _as_aware(body.created_after)
    ):
        return False
    if body.created_before is not None and (
        p.created_at is None or _as_aware(p.created_at) > _as_aware(body.created_before)
    ):
        return False
    if body.search:
        needle = body.search.strip().lower()
        if needle:
            haystack = json.dumps(
                {
                    "content": p.content,
                    "proposer": p.proposer,
                    "proposal_type": p.proposal_type,
                    "change_type": p.change_type.value,
                },
                default=str,
            ).lower()
            if needle not in haystack:
                return False
    return True


def _matching_proposals(body: VerdictByFilterRequest) -> list[ProposedChangeResponse]:
    """Page through EVERY proposal matching the filter set.

    This is the point of the endpoint: the UI lists cap at 200/500/1000
    loaded rows, so "all matching" must be resolved server-side without a
    silent page cap.
    """
    matches: list[ProposedChangeResponse] = []
    offset = 0
    while True:
        with db_op():
            page = mongodb_list_proposed_changes(
                ProposedChangeFilter(
                    scene_id=body.scene_id,
                    story_id=body.story_id,
                    source=body.source,
                    status=body.status or ProposalStatus.PENDING,
                    change_type=body.change_type,
                    limit=_BY_FILTER_PAGE_SIZE,
                    offset=offset,
                )
            )
        matches.extend(p for p in page.proposed_changes if _matches_client_filters(p, body))
        offset += len(page.proposed_changes)
        if len(page.proposed_changes) < _BY_FILTER_PAGE_SIZE:
            break
    return matches


def _by_filter_token(body: VerdictByFilterRequest, ids: list[str]) -> str:
    """Bind the decision payload to the exact matched ID set."""
    fingerprint = body.model_dump(exclude={"dry_run", "preview_token"})
    payload = json.dumps(
        {"filters": fingerprint, "ids": sorted(ids)},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


@router.post("/canon-review/verdicts/by-filter", response_model=VerdictByFilterResponse)
async def apply_verdicts_by_filter(
    body: VerdictByFilterRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> VerdictByFilterResponse:
    """Preview then execute a verdict over every proposal matching a filter.

    Two-phase flow:

    1. ``dry_run=true`` — returns ``affected_count`` and a ``preview_token``
       binding the filters + decision + reason to the matched ID set.
    2. ``dry_run=false`` with that token — re-resolves the match set and
       rejects with 409 if it no longer matches the token (dataset or filter
       drift), otherwise applies the verdict per item.

    Verdicts only flip proposal status in MongoDB; no Neo4j writes happen
    here (CanonKeeper remains the only Neo4j writer — commit is a separate
    explicit step).
    """
    if body.decision not in (ProposalStatus.ACCEPTED, ProposalStatus.REJECTED):
        raise HTTPException(status_code=400, detail="decision must be ACCEPTED or REJECTED")

    # A by-filter verdict must be anchored to an owned scene/story/job —
    # an unscoped filter would sweep every tenant's proposals. Local
    # auth-disabled mode bypasses (the local admin owns everything).
    if not is_local_mode(principal):
        if body.scene_id is not None:
            await require_scene_owner(db, principal, body.scene_id)
        if body.story_id is not None:
            await require_story_owner(db, principal, body.story_id)
        if body.source and body.source.startswith("ingestion_job:"):
            job = mongodb_get_ingestion_job(validate_uuid(body.source.split(":", 1)[1], "ingestion_job_id"))
            if job is None:
                raise HTTPException(status_code=404, detail="Not found")
            await require_universe_owner(db, principal, job.universe_id)
        if body.scene_id is None and body.story_id is None and not body.source:
            raise HTTPException(
                status_code=400, detail="by-filter verdicts require a scene_id, story_id, or source scope"
            )

    matches = _matching_proposals(body)
    for proposal in matches:
        await require_proposal_owner(db, principal, proposal.proposal_id)
    ids = [str(p.proposal_id) for p in matches]
    token = _by_filter_token(body, ids)

    if body.dry_run:
        return VerdictByFilterResponse(affected_count=len(ids), preview_token=token)

    if not body.preview_token:
        raise HTTPException(
            status_code=400,
            detail="preview_token is required when dry_run is false — run a preview first",
        )
    if body.preview_token != token:
        raise HTTPException(
            status_code=409,
            detail=(
                "Preview token mismatch: the matching proposal set changed since the "
                "preview. Re-run the preview and confirm again."
            ),
        )

    results: list[ProposedChangeResponse] = []
    errors: list[BatchVerdictError] = []
    for proposal in matches:
        if body.decision == ProposalStatus.ACCEPTED:
            try:
                results.append(await accept_proposal(str(proposal.proposal_id), body.reason, None, principal, db, body.decided_by or "GM"))
            except HTTPException as exc:
                errors.append(BatchVerdictError(proposal_id=proposal.proposal_id, error=str(exc.detail)))
            continue
        with db_op():
            try:
                updated = mongodb_update_proposed_change(
                    proposal.proposal_id,
                    ProposedChangeUpdate(
                        status=body.decision,
                        decision_metadata=DecisionMetadata(
                            decided_by=body.decided_by or "GM",
                            decided_at=datetime.now(UTC),
                            reason=body.reason,
                        ),
                    ),
                )
                results.append(updated)
            except ValueError as exc:
                errors.append(BatchVerdictError(proposal_id=proposal.proposal_id, error=str(exc)))
    return VerdictByFilterResponse(affected_count=len(ids), results=results, errors=errors)


# ---------------------------------------------------------------------------
# G08 — contradiction flags at the accept decision (CF-5 / CF-8)
# ---------------------------------------------------------------------------
#
# A proposal can carry flags: a deterministic state-transition violation, or
# a contradiction the model found in the canon. Until now those flags were
# advisory and never reached the decision point — the GM could accept a
# proposal that contradicted canon without being told.
#
# The rule now:
#
# - **Soft block (default).** A proposal carrying a direct-contradiction
#   flag cannot be accepted without an explicit ``override_reason``. The
#   reason is persisted on the proposal and written to the override audit
#   trail, so "who let this through, and why" has an answer later.
# - **Hard rejection (opt-in, per owner).** With hard mode on, a flagged
#   proposal is refused with 409 and cannot be overridden. The default for
#   an owner who has expressed no preference comes from
#   ``CANONKEEPER_HARD_REJECTION_DEFAULT`` (off).
#
# A *failed* check never blocks an acceptance: the check is advisory, and a
# broken check must not stop a GM from doing their job.

CANONKEEPER_PREF_KEY = "canonkeeper"

# The flag kinds that block an acceptance.
CONTRADICTION_FLAG_KINDS: frozenset[str] = frozenset({"direct_contradiction"})
# The flag kinds that hard mode refuses outright.
HARD_REFUSABLE_FLAG_KINDS: frozenset[str] = frozenset({"direct_contradiction", "transition_rule"})


def _proposal_statement(proposal: ProposedChangeResponse) -> str:
    """The sentence a proposal asserts (what the canon is checked against)."""
    content = proposal.content or {}
    for key in ("statement", "summary", "description", "name", "title", "text"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _proposal_universe_id(proposal: ProposedChangeResponse) -> str | None:
    """The universe a proposal belongs to (its content, else its scene)."""
    content = proposal.content or {}
    universe_id = content.get("universe_id")
    if universe_id:
        return str(universe_id)
    if proposal.scene_id:
        try:
            scene = mongodb_get_scene(proposal.scene_id)
        except Exception:  # noqa: BLE001  # reason: an unreadable scene means "cannot check", not "must block"
            return None
        if scene is not None:
            return str(scene.universe_id)
    return None


async def _owner_canon_settings(db: PostgresClient, principal: Principal) -> dict[str, Any]:
    """The owner's CanonKeeper settings (per-owner, SYS-6 style).

    Stored as a JSON blob under the owner's preferences, so one owner can
    run strict mode while another keeps the advisory default.
    """
    from monitor_data.config import get_settings

    stored: dict[str, Any] = {}
    try:
        stored = await db.pref_get(principal.user_id, CANONKEEPER_PREF_KEY) or {}
    except Exception:  # noqa: BLE001  # reason: an unreadable preference falls back to the global default
        stored = {}
    settings = dict(stored)
    if "hard_rejection" not in settings:
        settings["hard_rejection"] = get_settings().canonkeeper_hard_rejection_default
    return settings


async def _detect_direct_contradiction(
    proposal: ProposedChangeResponse,
) -> list[ProposalReviewFlag]:
    """Check one proposal against the canon and record what was found.

    Best-effort: a failure yields no flags, because a check that cannot run
    is not evidence of a contradiction.
    """
    universe_id = _proposal_universe_id(proposal)
    statement = _proposal_statement(proposal)
    if not universe_id or not statement:
        return []
    try:
        found = await CanonKeeper().direct_contradiction_flags(UUID(universe_id), [statement])
    except Exception as exc:  # noqa: BLE001  # reason: an unavailable model must not block a GM's decision
        log.warning("canon contradiction check failed (proposal=%s): %s", proposal.proposal_id, exc)
        return []

    now = datetime.now(UTC)
    flags: list[ProposalReviewFlag] = []
    for flag in found:
        flags.append(
            ProposalReviewFlag(
                kind=str(flag.get("flag_kind") or "direct_contradiction"),
                severity=str(flag.get("severity") or "high"),
                explanation=str(flag.get("explanation") or ""),
                implications=str(flag.get("implications") or ""),
                detected_at=now,
            )
        )
    return flags


async def _resolve_review_flags(
    proposal: ProposedChangeResponse,
) -> list[ProposalReviewFlag]:
    """The flags that apply to a proposal, checking the canon if needed.

    Flags already on the proposal are trusted. A proposal with none is
    checked once; anything found is stamped on the proposal so the review
    UI shows the warning next to the item.
    """
    if any(flag.kind == "direct_contradiction" for flag in proposal.review_flags):
        return list(proposal.review_flags)
    detected = await _detect_direct_contradiction(proposal)
    flags = list(proposal.review_flags) + detected
    if not detected:
        return flags
    try:
        mongodb_flag_proposal_review(
            proposal.proposal_id,
            needs_review=True,
            reason=detected[0].explanation or "Contradicts established canon.",
            source=detected[0].kind,
            flags=flags,
        )
    except Exception as exc:  # noqa: BLE001  # reason: a failed stamp must not block the decision
        log.warning("could not stamp review flags on proposal %s: %s", proposal.proposal_id, exc)
    return flags


def _blocking_flag_kinds(flags: list[ProposalReviewFlag]) -> set[str]:
    """The kinds of flag that block an acceptance."""
    return {f.kind for f in flags} & CONTRADICTION_FLAG_KINDS


def _hard_flag_kinds(flags: list[ProposalReviewFlag]) -> set[str]:
    """The kinds of flag that hard mode refuses outright."""
    return {f.kind for f in flags} & HARD_REFUSABLE_FLAG_KINDS


@router.post("/canon-review/{proposal_id}/accept", response_model=ProposedChangeResponse)
async def accept_proposal(
    proposal_id: str,
    reason: str = Query(..., min_length=1, max_length=2000),
    override_reason: str | None = Query(
        None,
        min_length=1,
        max_length=2000,
        description=(
            "Why a flagged proposal is accepted anyway. Required when the proposal carries a direct-contradiction flag."
        ),
    ),
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
    decided_by: str = "GM",
) -> ProposedChangeResponse:
    """Single-shot accept for a proposal.

    A proposal that contradicts canon cannot be accepted silently (G08): it
    needs an explicit override reason, and the override is audited. With
    the owner's hard-rejection mode on, it cannot be accepted at all.
    """
    proposal_uuid = validate_uuid(proposal_id, "proposal_id")
    with db_op():
        proposal = mongodb_get_proposed_change(proposal_uuid)
    if proposal is None:
        # 409, not 404: the sibling verdict routes answer a missing
        # proposal the same way, and the accept path's contract has always
        # been "you cannot decide this".
        raise HTTPException(status_code=409, detail="Proposal not found.")
    if proposal.status != ProposalStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Proposal is already {proposal.status.value}.",
        )

    correction = proposal.content.get("knowledge_correction")
    if "knowledge_correction" in proposal.content and (not isinstance(correction, dict) or not correction):
        raise HTTPException(status_code=409, detail="The knowledge correction is malformed.")
    is_knowledge_correction = bool(correction)

    owner_settings = await _owner_canon_settings(db, principal)
    hard_mode = bool(owner_settings.get("hard_rejection"))
    require_override = get_settings().canonkeeper_require_override_reason

    is_retraction = isinstance(correction, dict) and correction.get("action") == "retract"
    flags = list(proposal.review_flags) if is_retraction else await _resolve_review_flags(proposal)
    blocking = _blocking_flag_kinds(flags)
    hard_kinds = _hard_flag_kinds(flags)

    if hard_kinds and hard_mode:
        kinds = ", ".join(sorted(hard_kinds))
        detail = (
            f"This proposal contradicts established canon ({kinds}) and hard "
            "rejection is on for this account. Reject it, or edit it so it "
            "no longer conflicts."
        )
        raise HTTPException(status_code=409, detail=detail)

    if blocking and require_override and not override_reason:
        detail = (
            "This proposal contradicts established canon. Accept it with an "
            "explicit override reason (override_reason) to record why, or "
            "reject it."
        )
        raise HTTPException(status_code=409, detail=detail)

    if is_knowledge_correction:
        try:
            universe_id = UUID(str(proposal.content.get("universe_id")))
            await require_universe_owner(db, principal, universe_id)
            if not is_local_mode(principal):
                scope_universe = (
                    await _universe_of_scene(proposal.scene_id) if proposal.scene_id
                    else await _universe_of_story(proposal.story_id) if proposal.story_id
                    else None
                )
                if str(scope_universe) != str(universe_id):
                    raise HTTPException(status_code=404, detail="Not found")
            assert isinstance(correction, dict)
            memory_already_absent = False
            keeper = CanonKeeper()
            if correction.get("item_kind") == "memory" and correction.get("action") in ("retract", "correct"):
                from monitor_data.tools.mongodb_tools.proposals import prepare_knowledge_memory_change

                participants = proposal.content.get("participants") or []
                if len(participants) != 1:
                    raise ValueError("A knowledge correction must identify one character")
                character = await keeper.call_tool("neo4j_get_entity", {"entity_id": str(UUID(str(participants[0])))})
                if not isinstance(character, dict) or str(character.get("universe_id")) != str(universe_id):
                    raise ValueError("The character is no longer available in this universe")
                memory_already_absent = await asyncio.to_thread(
                    prepare_knowledge_memory_change, proposal_uuid, proposal.content,
                )
            await keeper.apply_knowledge_correction(
                proposal.content, memory_already_absent=memory_already_absent,
            )
            try:
                from monitor_data.db.redis import get_redis_client

                await asyncio.to_thread(get_redis_client().delete_prefix, "solo_play:")
            except Exception as exc:  # noqa: BLE001  # cache failure must not undo an applied correction
                log.warning("could not invalidate knowledge cache: %s", exc)
        except HTTPException:
            raise
        except (ValueError, PermissionError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            log.warning("knowledge correction failed for %s: %s", proposal_id, exc)
            raise HTTPException(status_code=503, detail="Could not apply the knowledge correction.") from exc

    with db_op():
        try:
            updated = mongodb_update_proposed_change(
                proposal_uuid,
                ProposedChangeUpdate(
                    status=ProposalStatus.ACCEPTED,
                    knowledge_correction_applied=is_knowledge_correction,
                    decision_metadata=DecisionMetadata(
                        decided_by=decided_by or "GM",
                        decided_at=datetime.now(UTC),
                        reason=reason,
                        override_reason=override_reason if blocking else None,
                    ),
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    if override_reason and blocking:
        with db_op():
            try:
                mongodb_record_canon_override(
                    CanonOverrideRecord(
                        proposal_id=proposal_uuid,
                        owner_id=str(principal.user_id),
                        reason=override_reason,
                        universe_id=UUID(_proposal_universe_id(proposal)) if _proposal_universe_id(proposal) else None,
                        story_id=proposal.story_id,
                        scene_id=proposal.scene_id,
                        flag_kinds=sorted(blocking),
                        hard_mode=hard_mode,
                    )
                )
            except Exception as exc:  # noqa: BLE001  # reason: the audit write must not undo the acceptance
                log.warning("could not record canon override for %s: %s", proposal_id, exc)

    return updated


@router.post("/canon-review/{proposal_id}/reject", response_model=ProposedChangeResponse)
async def reject_proposal(
    proposal_id: str, reason: str = Query(..., min_length=1, max_length=2000)
) -> ProposedChangeResponse:
    """Single-shot reject for a proposal."""
    proposal_uuid = validate_uuid(proposal_id, "proposal_id")
    with db_op():
        try:
            return mongodb_update_proposed_change(
                proposal_uuid,
                ProposedChangeUpdate(
                    status=ProposalStatus.REJECTED,
                    decision_metadata=DecisionMetadata(
                        decided_by="GM",
                        decided_at=datetime.now(UTC),
                        reason=reason,
                    ),
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/canon-review/{proposal_id}/defer", response_model=ProposedChangeResponse)
async def defer_proposal(
    proposal_id: str,
    body: ProposalDeferRequest,
) -> ProposedChangeResponse:
    """Defer a pending proposal while keeping it in the CF-8 queue."""
    proposal_uuid = validate_uuid(proposal_id, "proposal_id")
    with db_op():
        try:
            return mongodb_defer_proposed_change(
                proposal_uuid,
                reason=body.reason,
                deferred_by=body.deferred_by,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/canon-review/{proposal_id}/edit", response_model=ProposedChangeResponse)
async def edit_proposal(
    proposal_id: str,
    body: ProposalEditRequest,
) -> ProposedChangeResponse:
    """Edit a pending proposal before accepting or rejecting it (CF-8)."""
    proposal_uuid = validate_uuid(proposal_id, "proposal_id")
    with db_op():
        try:
            return mongodb_edit_proposed_change(
                proposal_uuid,
                content_patch=body.content_patch,
                reason=body.reason,
                edited_by=body.edited_by,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
