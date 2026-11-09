"""Tests for POST /api/gm/capture/insights — P1.2 per-entry capture insights.

The endpoint delegates to CaptureInsightAgent.analyze_entry (mocked here) and
returns the CaptureInsight verbatim. Invalid payloads (empty entry_text) are
rejected with 422.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from monitor_agents.ingestion.capture_insights import CaptureInsight

from monitor_ui.main import app

client = TestClient(app)


def test_insights_returned_200():
    insight = CaptureInsight(
        participants=["Mira"],
        locations=["The Sunken Chapel"],
        candidate_facts=["the key is now with Mira"],
        advances_thread="The sealed door",
    )
    with patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as mock_agent_cls:
        mock_agent_cls.return_value.analyze_entry = AsyncMock(return_value=insight)
        response = client.post(
            "/api/gm/capture/insights",
            json={
                "universe_id": str(uuid4()),
                "entry_text": "Mira pocketed the key beneath the chapel",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["participants"] == ["Mira"]
    assert body["locations"] == ["The Sunken Chapel"]
    assert body["candidate_facts"] == ["the key is now with Mira"]
    assert body["advances_thread"] == "The sealed door"


def test_empty_insight_shape_200():
    with patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as mock_agent_cls:
        mock_agent_cls.return_value.analyze_entry = AsyncMock(return_value=CaptureInsight())
        response = client.post(
            "/api/gm/capture/insights",
            json={
                "universe_id": str(uuid4()),
                "entry_text": "The party camped under the stars",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["participants"] == []
    assert body["locations"] == []
    assert body["candidate_facts"] == []
    assert body["advances_thread"] == ""


def test_empty_entry_text_rejected_422():
    response = client.post(
        "/api/gm/capture/insights",
        json={"universe_id": str(uuid4()), "entry_text": ""},
    )
    assert response.status_code == 422


def test_oversized_entry_text_rejected_422():
    response = client.post(
        "/api/gm/capture/insights",
        json={"universe_id": str(uuid4()), "entry_text": "x" * 4001},
    )
    assert response.status_code == 422


def test_agent_failure_returns_500():
    with patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as mock_agent_cls:
        mock_agent_cls.return_value.analyze_entry = AsyncMock(side_effect=RuntimeError("neo4j unreachable"))
        response = client.post(
            "/api/gm/capture/insights",
            json={
                "universe_id": str(uuid4()),
                "entry_text": "Mira pocketed the key beneath the chapel",
            },
        )
    assert response.status_code == 500
    assert "Failed to analyze capture entry" in response.json()["detail"]


def test_candidate_facts_create_story_scoped_proposals():
    from monitor_data.schemas.base import Authority, ProposalStatus, ProposalType
    from monitor_data.schemas.proposed_changes import (
        ProposedChangeCreate,
        ProposedChangeListResponse,
        ProposedChangeResponse,
    )

    insight = CaptureInsight(
        participants=["Mira"],
        locations=["The Sunken Chapel"],
        candidate_facts=["the key is now with Mira"],
        advances_thread="The sealed door",
    )
    entry_id = str(uuid4())
    story_id = uuid4()
    scene_id = uuid4()

    def _created(params):
        return ProposedChangeResponse(
            proposal_id=uuid4(),
            scene_id=params.scene_id,
            story_id=params.story_id,
            change_type=params.change_type,
            content=params.content,
            evidence=params.evidence,
            confidence=params.confidence,
            authority=params.authority,
            proposer=params.proposer,
            status=ProposalStatus.PENDING,
            source=params.source,
            proposal_type=params.proposal_type,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    with (
        patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as mock_agent_cls,
        patch("monitor_ui.routers.gm_tools.mongodb_list_proposed_changes") as mock_list,
        patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change", side_effect=_created) as mock_create,
    ):
        mock_agent_cls.return_value.analyze_entry = AsyncMock(return_value=insight)
        mock_list.return_value = ProposedChangeListResponse(proposed_changes=[], total=0, limit=500, offset=0)
        response = client.post(
            "/api/gm/capture/insights",
            json={
                "universe_id": str(uuid4()),
                "entry_text": "Mira pocketed the key beneath the chapel",
                "entry_id": entry_id,
                "story_id": str(story_id),
                "scene_id": str(scene_id),
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal_ids"]
    assert body["proposal_errors"] == []
    created = mock_create.call_args.args[0]
    assert isinstance(created, ProposedChangeCreate)
    assert created.scene_id == scene_id
    assert created.story_id == story_id
    assert created.change_type == ProposalType.FACT
    assert created.content["statement"] == "the key is now with Mira"
    assert created.content["source_excerpt"] == "Mira pocketed the key beneath the chapel"
    assert created.content["participants"] == ["Mira"]
    assert created.content["locations"] == ["The Sunken Chapel"]
    assert created.authority == Authority.GM
    assert created.proposal_type == "capture_candidate_fact"
    assert created.source == f"capture_entry:{entry_id}"
    assert created.evidence[0].type == "snippet"
    assert str(created.evidence[0].ref_id) == entry_id


def test_capture_proposals_are_idempotent_per_entry():
    from monitor_data.schemas.base import ProposalStatus
    from monitor_data.schemas.proposed_changes import ProposedChangeListResponse, ProposedChangeResponse

    insight = CaptureInsight(candidate_facts=["the key is now with Mira"])
    entry_id = str(uuid4())
    existing = ProposedChangeResponse(
        proposal_id=uuid4(),
        scene_id=uuid4(),
        story_id=uuid4(),
        change_type="fact",
        content={"statement": "the key is now with Mira"},
        confidence=0.75,
        authority="gm",
        proposer="CaptureInsightAgent",
        status=ProposalStatus.PENDING,
        source=f"capture_entry:{entry_id}",
        proposal_type="capture_candidate_fact",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    with (
        patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as mock_agent_cls,
        patch("monitor_ui.routers.gm_tools.mongodb_list_proposed_changes") as mock_list,
        patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change") as mock_create,
    ):
        mock_agent_cls.return_value.analyze_entry = AsyncMock(return_value=insight)
        mock_list.return_value = ProposedChangeListResponse(
            proposed_changes=[existing], total=1, limit=500, offset=0
        )
        response = client.post(
            "/api/gm/capture/insights",
            json={
                "universe_id": str(uuid4()),
                "entry_text": "Mira pocketed the key beneath the chapel",
                "entry_id": entry_id,
                "story_id": str(uuid4()),
                "scene_id": str(uuid4()),
            },
        )

    assert response.status_code == 200
    assert response.json()["proposal_ids"] == []
    mock_create.assert_not_called()
