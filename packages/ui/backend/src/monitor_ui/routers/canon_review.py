"""CanonKeeper review queue router — CF-8.

Exposes the scene-by-scene review surface that lets a human GM audit what
MONITOR is about to add to the world. Wires ``mongodb_list_proposed_changes``
and ``mongodb_update_proposed_change`` to a UI-friendly aggregate payload.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: data-layer only
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from monitor_data.schemas.base import ProposalStatus
from monitor_data.schemas.proposed_changes import (
    DecisionMetadata,
    ProposedChangeFilter,
    ProposedChangeResponse,
    ProposedChangeUpdate,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_list_proposed_changes,
    mongodb_update_proposed_change,
)

from .ingest_shared import db_op, validate_uuid

router = APIRouter()


# ---------------------------------------------------------------------------
# UI-layer request/response shapes
# ---------------------------------------------------------------------------


class VerdictItem(BaseModel):
    """Single review item: which proposal, accept/reject, why."""

    proposal_id: UUID
    decision: ProposalStatus  # ACCEPTED or REJECTED
    reason: str


class BatchVerdictRequest(BaseModel):
    """Apply multiple accept/reject decisions at once (one round-trip)."""

    decided_by: str = Field(default="GM", description="Who is making the decision")
    items: List[VerdictItem]


class SceneReviewResponse(BaseModel):
    """Per-scene CanonKeeper review payload."""

    scene_id: UUID
    pending: List[ProposedChangeResponse]
    accepted: List[ProposedChangeResponse]
    rejected: List[ProposedChangeResponse]
    by_change_type: Dict[str, int]


class CanonQueueResponse(BaseModel):
    """Story-level CanonKeeper queue: every scene that has any pending items."""

    story_id: UUID
    scenes: List[SceneReviewResponse]
    total_pending: int


from pydantic import Field  # noqa: E402  (late import for the default-arg trick above)


BatchVerdictRequest.model_rebuild()  # noqa: E402


# ---------------------------------------------------------------------------
# Per-scene review
# ---------------------------------------------------------------------------


@router.get("/scenes/{scene_id}/canon-review", response_model=SceneReviewResponse)
async def scene_canon_review(scene_id: str) -> SceneReviewResponse:
    """Return every proposal for a scene, grouped by status and change type.

    This is the data behind the CF-8 "CanonKeeper Review" panel.
    """
    scene_uuid = validate_uuid(scene_id, "scene_id")
    with db_op():
        # Single round-trip: filter by scene_id, all statuses.
        resp = mongodb_list_proposed_changes(
            ProposedChangeFilter(scene_id=scene_uuid, limit=500)
        )

    pending: List[ProposedChangeResponse] = []
    accepted: List[ProposedChangeResponse] = []
    rejected: List[ProposedChangeResponse] = []
    by_type: Dict[str, int] = defaultdict(int)

    for proposal in resp.proposed_changes:
        if proposal.status == ProposalStatus.PENDING:
            pending.append(proposal)
        elif proposal.status == ProposalStatus.ACCEPTED:
            accepted.append(proposal)
        elif proposal.status == ProposalStatus.REJECTED:
            rejected.append(proposal)
        by_type[proposal.change_type.value] += 1

    return SceneReviewResponse(
        scene_id=scene_uuid,
        pending=pending,
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
    one review card per scene.
    """
    story_uuid = validate_uuid(story_id, "story_id")
    with db_op():
        resp = mongodb_list_proposed_changes(
            ProposedChangeFilter(story_id=story_uuid, limit=1000)
        )

    # Group by scene_id, preserving insertion order
    per_scene: Dict[UUID, List[ProposedChangeResponse]] = defaultdict(list)
    for proposal in resp.proposed_changes:
        if proposal.scene_id is None:
            continue
        per_scene[proposal.scene_id].append(proposal)

    scenes_out: List[SceneReviewResponse] = []
    total_pending = 0
    for scene_id, proposals in per_scene.items():
        pending = [p for p in proposals if p.status == ProposalStatus.PENDING]
        accepted = [p for p in proposals if p.status == ProposalStatus.ACCEPTED]
        rejected = [p for p in proposals if p.status == ProposalStatus.REJECTED]
        if only_pending and not pending:
            continue
        by_type: Dict[str, int] = defaultdict(int)
        for p in proposals:
            by_type[p.change_type.value] += 1
        scenes_out.append(
            SceneReviewResponse(
                scene_id=scene_id,
                pending=pending,
                accepted=accepted,
                rejected=rejected,
                by_change_type=dict(by_type),
            )
        )
        total_pending += len(pending)

    return CanonQueueResponse(
        story_id=story_uuid, scenes=scenes_out, total_pending=total_pending
    )


# ---------------------------------------------------------------------------
# Verdict actions
# ---------------------------------------------------------------------------


@router.post("/canon-review/verdicts", response_model=List[ProposedChangeResponse])
async def apply_verdicts(body: BatchVerdictRequest) -> List[ProposedChangeResponse]:
    """Apply a batch of accept/reject decisions in one call.

    Each item is processed independently; failures for one item do not
    block the others. The response contains one ``ProposedChangeResponse``
    per item, in the same order.
    """
    results: List[ProposedChangeResponse] = []
    for item in body.items:
        if item.decision not in (ProposalStatus.ACCEPTED, ProposalStatus.REJECTED):
            raise HTTPException(
                status_code=400,
                detail=f"Decision for {item.proposal_id} must be ACCEPTED or REJECTED",
            )
        with db_op():
            try:
                updated = mongodb_update_proposed_change(
                    item.proposal_id,
                    ProposedChangeUpdate(
                        status=item.decision,
                        decision_metadata=DecisionMetadata(
                            decided_by=body.decided_by or "GM",
                            decided_at=datetime.now(timezone.utc),
                            reason=item.reason,
                        ),
                    ),
                )
                results.append(updated)
            except ValueError as exc:
                # Surface as a 409 so the UI can re-fetch and re-try
                raise HTTPException(status_code=409, detail=str(exc)) from exc
    return results


@router.post(
    "/canon-review/{proposal_id}/accept", response_model=ProposedChangeResponse
)
async def accept_proposal(
    proposal_id: str, reason: str = Query(..., min_length=1, max_length=2000)
) -> ProposedChangeResponse:
    """Single-shot accept for a proposal."""
    proposal_uuid = validate_uuid(proposal_id, "proposal_id")
    with db_op():
        try:
            return mongodb_update_proposed_change(
                proposal_uuid,
                ProposedChangeUpdate(
                    status=ProposalStatus.ACCEPTED,
                    decision_metadata=DecisionMetadata(
                        decided_by="GM",
                        decided_at=datetime.now(timezone.utc),
                        reason=reason,
                    ),
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/canon-review/{proposal_id}/reject", response_model=ProposedChangeResponse
)
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
                        decided_at=datetime.now(timezone.utc),
                        reason=reason,
                    ),
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
