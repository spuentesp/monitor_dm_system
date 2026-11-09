"""Tests for the story-level canon queue and batch verdict contract (CF-8, F2-3).

Covers:
- story-scoped proposals with no scene_id surface in the story queue as a
  story-level lane (scene_id=None) instead of being dropped
- batch verdicts report per-item failures (partial success) instead of
  aborting the whole batch on the first conflict
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from monitor_data.schemas.base import Authority, ProposalStatus, ProposalType
from monitor_data.schemas.proposed_changes import (
    ProposedChangeListResponse,
    ProposedChangeResponse,
)

from monitor_ui.main import app

client = TestClient(app)


def _proposal(
    status: ProposalStatus = ProposalStatus.PENDING,
    story_id: UUID | None = None,
    scene_id: UUID | None = None,
    change_type: ProposalType = ProposalType.FACT,
) -> ProposedChangeResponse:
    now = datetime.now(UTC)
    return ProposedChangeResponse(
        proposal_id=uuid4(),
        change_type=change_type,
        content={"statement": "The moon is hollow"},
        confidence=0.9,
        authority=Authority.GM,
        proposer="CanonKeeper",
        status=status,
        story_id=story_id,
        scene_id=scene_id,
        created_at=now,
        updated_at=now,
    )


def _list_response(proposals: list[ProposedChangeResponse]) -> ProposedChangeListResponse:
    return ProposedChangeListResponse(
        proposed_changes=proposals,
        total=len(proposals),
        limit=1000,
        offset=0,
    )


class TestStoryQueueStoryLevelLane:
    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_story_level_proposals_surface_in_ungrouped_lane(self, mock_list: Mock) -> None:
        story_id = uuid4()
        scene_id = uuid4()
        mock_list.return_value = _list_response(
            [
                _proposal(story_id=story_id, scene_id=scene_id),
                _proposal(story_id=story_id, scene_id=None),  # story-level
            ]
        )

        resp = client.get(f"/api/stories/{story_id}/canon-queue")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_pending"] == 2
        lanes = {s["scene_id"]: s for s in data["scenes"]}
        assert str(scene_id) in lanes
        assert None in lanes  # story-level lane present
        assert len(lanes[None]["pending"]) == 1

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_only_pending_still_filters_story_level_lane(self, mock_list: Mock) -> None:
        story_id = uuid4()
        mock_list.return_value = _list_response(
            [
                _proposal(ProposalStatus.ACCEPTED, story_id=story_id, scene_id=None),
            ]
        )

        resp = client.get(f"/api/stories/{story_id}/canon-queue?only_pending=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scenes"] == []
        assert data["total_pending"] == 0

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_only_pending_false_keeps_story_level_lane(self, mock_list: Mock) -> None:
        story_id = uuid4()
        mock_list.return_value = _list_response(
            [
                _proposal(ProposalStatus.ACCEPTED, story_id=story_id, scene_id=None),
            ]
        )

        resp = client.get(f"/api/stories/{story_id}/canon-queue?only_pending=false")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["scenes"]) == 1
        assert data["scenes"][0]["scene_id"] is None
        assert len(data["scenes"][0]["accepted"]) == 1


class TestBatchVerdicts:
    @patch("monitor_ui.routers.canon_review.mongodb_update_proposed_change")
    def test_partial_failure_reported_per_item(self, mock_update: Mock) -> None:
        ok = _proposal()
        failing_id = uuid4()

        def _update(proposal_id: UUID, _update_body: object) -> ProposedChangeResponse:
            if proposal_id == failing_id:
                raise ValueError("Proposal already decided")
            return ok

        mock_update.side_effect = _update

        resp = client.post(
            "/api/canon-review/verdicts",
            json={
                "decided_by": "GM",
                "items": [
                    {"proposal_id": str(ok.proposal_id), "decision": "accepted", "reason": "good"},
                    {"proposal_id": str(failing_id), "decision": "rejected", "reason": "bad"},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["results"]) == 1
        assert data["results"][0]["proposal_id"] == str(ok.proposal_id)
        assert data["errors"] == [{"proposal_id": str(failing_id), "error": "Proposal already decided"}]

    @patch("monitor_ui.routers.canon_review.mongodb_update_proposed_change")
    def test_invalid_decision_fails_fast(self, mock_update: Mock) -> None:
        resp = client.post(
            "/api/canon-review/verdicts",
            json={
                "decided_by": "GM",
                "items": [
                    {"proposal_id": str(uuid4()), "decision": "pending", "reason": "nope"},
                ],
            },
        )
        assert resp.status_code == 400
        mock_update.assert_not_called()


class TestDeferAndEdit:
    @patch("monitor_ui.routers.canon_review.mongodb_defer_proposed_change")
    def test_defer_keeps_the_proposal_pending_and_records_a_reason(self, mock_defer: Mock) -> None:
        proposal = _proposal()
        proposal.deferred = True
        proposal.defer_reason = "Need a second look"
        mock_defer.return_value = proposal

        resp = client.post(
            f"/api/canon-review/{proposal.proposal_id}/defer",
            json={"reason": "Need a second look", "deferred_by": "GM"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert resp.json()["deferred"] is True
        assert resp.json()["defer_reason"] == "Need a second look"
        mock_defer.assert_called_once_with(
            proposal.proposal_id,
            reason="Need a second look",
            deferred_by="GM",
        )

    @patch("monitor_ui.routers.canon_review.mongodb_edit_proposed_change")
    def test_edit_merges_the_statement_patch_before_a_verdict(self, mock_edit: Mock) -> None:
        proposal = _proposal()
        proposal.content = {"statement": "The moon is hollow", "source_excerpt": "old evidence"}
        proposal.edit_reason = "Clarified wording"
        mock_edit.return_value = proposal

        resp = client.post(
            f"/api/canon-review/{proposal.proposal_id}/edit",
            json={
                "content_patch": {"statement": "The moon is hollow and ancient"},
                "reason": "Clarified wording",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["edit_reason"] == "Clarified wording"
        mock_edit.assert_called_once_with(
            proposal.proposal_id,
            content_patch={"statement": "The moon is hollow and ancient"},
            reason="Clarified wording",
            edited_by="GM",
        )

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_story_queue_groups_deferred_proposals_separately(self, mock_list: Mock) -> None:
        story_id = uuid4()
        scene_id = uuid4()
        deferred = _proposal(story_id=story_id, scene_id=scene_id)
        deferred.deferred = True
        deferred.defer_reason = "Wait for the next session"
        mock_list.return_value = _list_response([deferred])

        resp = client.get(f"/api/stories/{story_id}/canon-queue")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_pending"] == 0
        assert data["total_deferred"] == 1
        assert data["scenes"][0]["pending"] == []
        assert data["scenes"][0]["deferred"][0]["defer_reason"] == "Wait for the next session"
