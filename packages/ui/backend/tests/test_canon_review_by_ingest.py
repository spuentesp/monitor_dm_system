"""Tests for the by-ingest canon review surface (I-4, CF-8).

Covers the F1-4 lifecycle corrections:
- grouping + normalized proposal shape on GET /api/canon-review/by-ingest/{job_id}
- status filter pass-through
- exact job attribution (source == "ingestion_job:<uuid>")
- commit path for accepted by-ingest proposals via CanonKeeper
  (POST /api/canon-review/by-ingest/{job_id}/commit)
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
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
    status: ProposalStatus,
    job_id: UUID,
    change_type: ProposalType = ProposalType.FACT,
    proposal_type: str = "create_lore_fact",
    confidence: float = 0.9,
) -> ProposedChangeResponse:
    now = datetime.now(UTC)
    return ProposedChangeResponse(
        proposal_id=uuid4(),
        change_type=change_type,
        content={"statement": "The moon is hollow", "confidence": confidence},
        confidence=confidence,
        authority=Authority.SOURCE,
        proposer="IngestionPipeline",
        status=status,
        source=f"ingestion_job:{job_id}",
        proposal_type=proposal_type,
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


class TestByIngestReview:
    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_groups_by_status_and_normalizes_shape(self, mock_list: Mock) -> None:
        job_id = uuid4()
        mock_list.return_value = _list_response(
            [
                _proposal(ProposalStatus.PENDING, job_id),
                _proposal(ProposalStatus.PENDING, job_id, change_type=ProposalType.ENTITY),
                _proposal(ProposalStatus.ACCEPTED, job_id),
                _proposal(ProposalStatus.REJECTED, job_id),
            ]
        )

        resp = client.get(f"/api/canon-review/by-ingest/{job_id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["ingestion_job_id"] == str(job_id)
        assert len(data["pending"]) == 2
        assert len(data["accepted"]) == 1
        assert len(data["rejected"]) == 1
        assert data["by_change_type"] == {"fact": 3, "entity": 1}

        # Normalized shape: same field names the pack-proposal UI renders
        item = data["pending"][0]
        assert set(item) == {
            "proposal_id",
            "change_type",
            "proposal_type",
            "status",
            "source",
            "content",
            "confidence",
            "authority",
            "proposer",
            "evidence",
            "created_at",
        }
        assert item["change_type"] == "fact"
        assert item["proposal_type"] == "create_lore_fact"
        assert item["status"] == "pending"
        assert item["source"] == f"ingestion_job:{job_id}"
        assert item["content"]["statement"] == "The moon is hollow"
        assert item["confidence"] == 0.9
        assert item["created_at"] is not None

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_queries_exact_job_source(self, mock_list: Mock) -> None:
        """Attribution is exact: only source == ingestion_job:<job_id>."""
        job_id = uuid4()
        mock_list.return_value = _list_response([])

        resp = client.get(f"/api/canon-review/by-ingest/{job_id}")
        assert resp.status_code == 200

        filt = mock_list.call_args.args[0]
        assert filt.source == f"ingestion_job:{job_id}"
        assert filt.status is None  # default: all statuses, grouped

    @patch("monitor_ui.routers.canon_review.mongodb_list_proposed_changes")
    def test_status_filter_passed_through(self, mock_list: Mock) -> None:
        job_id = uuid4()
        accepted = _proposal(ProposalStatus.ACCEPTED, job_id)
        mock_list.return_value = _list_response([accepted])

        resp = client.get(f"/api/canon-review/by-ingest/{job_id}?status_filter=accepted")
        assert resp.status_code == 200

        filt = mock_list.call_args.args[0]
        assert filt.status == ProposalStatus.ACCEPTED
        data = resp.json()
        assert len(data["accepted"]) == 1
        assert data["pending"] == []

    def test_invalid_job_id_rejected(self) -> None:
        resp = client.get("/api/canon-review/by-ingest/not-a-uuid")
        assert resp.status_code in (400, 422)


class TestByIngestCommit:
    @patch("monitor_ui.routers.canon_review.CanonKeeper")
    def test_commit_accepted_proposals(self, mock_keeper_cls: Mock) -> None:
        """Accepted by-ingest proposals commit through CanonKeeper."""
        job_id = uuid4()
        keeper = Mock()
        keeper.commit_accepted_for_job = AsyncMock(return_value={"committed": 2, "errors": []})
        mock_keeper_cls.return_value = keeper

        resp = client.post(f"/api/canon-review/by-ingest/{job_id}/commit")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {
            "ingestion_job_id": str(job_id),
            "committed": 2,
            "errors": [],
            "status": "done",
        }
        keeper.commit_accepted_for_job.assert_awaited_once_with(job_id)

    @patch("monitor_ui.routers.canon_review.CanonKeeper")
    def test_commit_partial_on_errors(self, mock_keeper_cls: Mock) -> None:
        job_id = uuid4()
        keeper = Mock()
        keeper.commit_accepted_for_job = AsyncMock(return_value={"committed": 1, "errors": ["boom"]})
        mock_keeper_cls.return_value = keeper

        resp = client.post(f"/api/canon-review/by-ingest/{job_id}/commit")
        assert resp.status_code == 200
        assert resp.json()["status"] == "partial"

    @patch("monitor_ui.routers.canon_review.CanonKeeper")
    def test_commit_nothing_accepted(self, mock_keeper_cls: Mock) -> None:
        job_id = uuid4()
        keeper = Mock()
        keeper.commit_accepted_for_job = AsyncMock(return_value={"committed": 0, "errors": []})
        mock_keeper_cls.return_value = keeper

        resp = client.post(f"/api/canon-review/by-ingest/{job_id}/commit")
        assert resp.status_code == 200
        assert resp.json()["committed"] == 0

    def test_commit_invalid_job_id_rejected(self) -> None:
        resp = client.post("/api/canon-review/by-ingest/not-a-uuid/commit")
        assert resp.status_code in (400, 422)
