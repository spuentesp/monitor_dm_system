"""Tests for POST /api/canon-review/verdicts/by-filter (F2-3c).

Covers the two-phase preview/execute contract behind "select all matching
active filters":
- dry-run returns an accurate affected count + preview token
- client-side filters (confidence range, date range, search) apply server-side
- execute without a token is rejected
- execute with a stale/forged token is rejected (409)
- execute applies verdicts per item and reports per-item failures
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

STORY_ID = uuid4()


def _proposal(
    status: ProposalStatus = ProposalStatus.PENDING,
    story_id: UUID | None = STORY_ID,
    change_type: ProposalType = ProposalType.FACT,
    confidence: float = 0.9,
    statement: str = "The moon is hollow",
    created_at: datetime | None = None,
) -> ProposedChangeResponse:
    now = datetime.now(UTC)
    return ProposedChangeResponse(
        proposal_id=uuid4(),
        story_id=story_id,
        change_type=change_type,
        content={"statement": statement},
        confidence=confidence,
        authority=Authority.GM,
        proposer="CanonKeeper",
        status=status,
        created_at=created_at or now,
        updated_at=created_at or now,
    )


def _list_response(proposals: list[ProposedChangeResponse]) -> ProposedChangeListResponse:
    return ProposedChangeListResponse(
        proposed_changes=proposals,
        total=len(proposals),
        limit=1000,
        offset=0,
    )


def _body(**overrides: object) -> dict:
    base: dict = {
        "decided_by": "GM",
        "decision": "accepted",
        "reason": "Triage sweep",
        "story_id": str(STORY_ID),
        "dry_run": True,
    }
    base.update(overrides)
    return base


class TestPreview:
    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_preview_count_and_token(self, mock_list: Mock) -> None:
        mock_list.return_value = _list_response([_proposal(), _proposal(), _proposal()])

        resp = client.post("/api/canon-review/verdicts/by-filter", json=_body())
        assert resp.status_code == 200
        data = resp.json()
        assert data["affected_count"] == 3
        assert data["preview_token"]
        assert data["results"] == []
        assert data["errors"] == []

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_preview_token_is_stable_for_same_set(self, mock_list: Mock) -> None:
        mock_list.return_value = _list_response([_proposal(), _proposal()])

        first = client.post("/api/canon-review/verdicts/by-filter", json=_body()).json()
        second = client.post("/api/canon-review/verdicts/by-filter", json=_body()).json()
        assert first["preview_token"] == second["preview_token"]

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_preview_defaults_to_pending_only(self, mock_list: Mock) -> None:
        mock_list.return_value = _list_response([])

        resp = client.post("/api/canon-review/verdicts/by-filter", json=_body())
        assert resp.status_code == 200
        filt = mock_list.call_args.args[0]
        assert filt.status == ProposalStatus.PENDING
        assert filt.story_id == STORY_ID

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_confidence_range_filters_server_side(self, mock_list: Mock) -> None:
        mock_list.return_value = _list_response(
            [
                _proposal(confidence=0.95),
                _proposal(confidence=0.75),
                _proposal(confidence=0.2),
            ]
        )

        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(confidence_min=0.9),
        )
        assert resp.json()["affected_count"] == 1

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_date_range_filters_server_side(self, mock_list: Mock) -> None:
        now = datetime.now(UTC)
        mock_list.return_value = _list_response(
            [
                _proposal(created_at=now - timedelta(days=10)),
                _proposal(created_at=now - timedelta(days=1)),
            ]
        )
        cutoff = (now - timedelta(days=5)).isoformat()

        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(created_after=cutoff),
        )
        assert resp.json()["affected_count"] == 1

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_search_filters_server_side(self, mock_list: Mock) -> None:
        mock_list.return_value = _list_response(
            [
                _proposal(statement="The moon is hollow"),
                _proposal(statement="The sun is a chariot"),
            ]
        )

        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(search="moon"),
        )
        assert resp.json()["affected_count"] == 1

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_naive_mongo_datetimes_compare_against_aware_bounds(self, mock_list: Mock) -> None:
        """pymongo returns naive datetimes; bounds from the client are aware."""
        naive_recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
        mock_list.return_value = _list_response([_proposal(created_at=naive_recent)])
        cutoff = (datetime.now(UTC) - timedelta(days=5)).isoformat()

        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(created_after=cutoff),
        )
        assert resp.status_code == 200
        assert resp.json()["affected_count"] == 1

    def test_invalid_decision_rejected(self) -> None:
        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(decision="pending"),
        )
        assert resp.status_code in (400, 422)


class TestExecute:
    @patch("monitor_ui.routers.canon_review.mongodb_update_proposed_change")
    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_execute_requires_token(self, mock_list: Mock, mock_update: Mock) -> None:
        mock_list.return_value = _list_response([_proposal()])

        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(dry_run=False),
        )
        assert resp.status_code == 400
        mock_update.assert_not_called()

    @patch("monitor_ui.routers.canon_review.mongodb_update_proposed_change")
    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_execute_rejects_forged_token(self, mock_list: Mock, mock_update: Mock) -> None:
        mock_list.return_value = _list_response([_proposal()])

        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(dry_run=False, preview_token="0" * 64),
        )
        assert resp.status_code == 409
        mock_update.assert_not_called()

    @patch("monitor_ui.routers.canon_review.mongodb_update_proposed_change")
    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_execute_rejects_stale_token_when_set_changes(self, mock_list: Mock, mock_update: Mock) -> None:
        preview_set = [_proposal(), _proposal()]
        mock_list.return_value = _list_response(preview_set)
        token = client.post("/api/canon-review/verdicts/by-filter", json=_body()).json()["preview_token"]

        # A third proposal arrives between preview and execute.
        mock_list.return_value = _list_response([*preview_set, _proposal()])
        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(dry_run=False, preview_token=token),
        )
        assert resp.status_code == 409
        mock_update.assert_not_called()

    @patch("monitor_ui.routers.canon_review.mongodb_update_proposed_change")
    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_execute_applies_verdicts_with_reason(self, mock_list: Mock, mock_update: Mock) -> None:
        proposals = [_proposal(), _proposal()]
        mock_list.return_value = _list_response(proposals)
        mock_update.side_effect = lambda pid, _u: next(p for p in proposals if p.proposal_id == pid)

        token = client.post("/api/canon-review/verdicts/by-filter", json=_body()).json()["preview_token"]
        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(dry_run=False, preview_token=token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["affected_count"] == 2
        assert len(data["results"]) == 2
        assert data["errors"] == []

        # Every update carried the shared decision metadata.
        for call in mock_update.call_args_list:
            update = call.args[1]
            assert update.status == ProposalStatus.ACCEPTED
            assert update.decision_metadata.reason == "Triage sweep"
            assert update.decision_metadata.decided_by == "GM"

    @patch("monitor_ui.routers.canon_review.mongodb_update_proposed_change")
    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_execute_reports_per_item_failures(self, mock_list: Mock, mock_update: Mock) -> None:
        ok = _proposal()
        failing = _proposal()
        mock_list.return_value = _list_response([ok, failing])

        def _update(pid: UUID, _u: object) -> ProposedChangeResponse:
            if pid == failing.proposal_id:
                raise ValueError("Proposal already decided")
            return ok

        mock_update.side_effect = _update

        token = client.post("/api/canon-review/verdicts/by-filter", json=_body()).json()["preview_token"]
        resp = client.post(
            "/api/canon-review/verdicts/by-filter",
            json=_body(dry_run=False, preview_token=token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["errors"] == [{"proposal_id": str(failing.proposal_id), "error": "Proposal already decided"}]

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_dry_run_never_updates(self, mock_list: Mock) -> None:
        mock_list.return_value = _list_response([_proposal()])
        with patch("monitor_ui.routers.canon_review.mongodb_update_proposed_change") as mock_update:
            resp = client.post("/api/canon-review/verdicts/by-filter", json=_body())
            assert resp.status_code == 200
            mock_update.assert_not_called()
