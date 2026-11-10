"""Regression tests for CF-3 thread actions and CF-5 contradiction resolution."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from fastapi.testclient import TestClient
from monitor_agents.plot_hooks import Contradiction
from monitor_data.schemas.base import PlotThreadStatus
from monitor_ui.main import app

pytestmark = pytest.mark.usefixtures("local_auth_mode")

client = TestClient(app)


def _thread(status=PlotThreadStatus.OPEN, gm_notes=""):
    return SimpleNamespace(
        id=uuid4(),
        story_id=uuid4(),
        title="The sealed door",
        thread_type="mystery",
        status=status,
        urgency="high",
        priority="major",
        gm_notes=gm_notes,
    )


class TestCF3ThreadActions:
    @patch("monitor_data.tools.neo4j_tools.neo4j_update_plot_thread")
    @patch("monitor_data.tools.neo4j_tools.neo4j_get_plot_thread")
    def test_resolve_thread(self, mock_get: Mock, mock_update: Mock) -> None:
        thread = _thread()
        mock_get.return_value = thread
        mock_update.return_value = _thread(PlotThreadStatus.RESOLVED, "Closing this out")

        resp = client.patch(
            f"/api/stories/{thread.story_id}/threads/{thread.id}",
            json={"action": "resolve", "note": "Closing this out"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "resolved"
        assert resp.json()["gm_notes"] == "Closing this out"
        assert mock_update.call_args.args[1].status == PlotThreadStatus.RESOLVED

    @patch("monitor_data.tools.neo4j_tools.neo4j_update_plot_thread")
    @patch("monitor_data.tools.neo4j_tools.neo4j_get_plot_thread")
    def test_dismiss_thread(self, mock_get: Mock, mock_update: Mock) -> None:
        thread = _thread()
        mock_get.return_value = thread
        mock_update.return_value = _thread(PlotThreadStatus.ABANDONED)

        resp = client.patch(
            f"/api/stories/{thread.story_id}/threads/{thread.id}",
            json={"action": "dismiss"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "abandoned"
        assert mock_update.call_args.args[1].status == PlotThreadStatus.ABANDONED

    @patch("monitor_data.tools.neo4j_tools.neo4j_get_plot_thread")
    def test_unknown_thread_is_404(self, mock_get: Mock) -> None:
        mock_get.return_value = None
        resp = client.patch(
            f"/api/stories/{uuid4()}/threads/{uuid4()}",
            json={"action": "note", "note": "missing"},
        )
        assert resp.status_code == 404


class TestCF5Contradictions:
    @patch("monitor_ui.routers.gm_tools.require_universe_owner", new_callable=AsyncMock)
    @patch("monitor_ui.routers.gm_tools.PlotHookAgent")
    def test_detect_contradictions_passes_scope(
        self,
        mock_agent_cls: Mock,
        _mock_owner: AsyncMock,
    ) -> None:
        mock_agent = mock_agent_cls.return_value
        mock_agent.detect_contradictions = AsyncMock(return_value=[])
        story_id = uuid4()
        scene_id = uuid4()

        resp = client.post(
            "/api/gm/contradictions",
            json={
                "universe_id": str(uuid4()),
                "scope": "scene",
                "story_id": str(story_id),
                "scene_id": str(scene_id),
            },
        )

        assert resp.status_code == 200
        mock_agent.detect_contradictions.assert_awaited_once()
        kwargs = mock_agent.detect_contradictions.await_args.kwargs
        assert kwargs["scope"] == "scene"
        assert kwargs["story_id"] == story_id
        assert kwargs["scene_id"] == scene_id

    @patch("monitor_ui.routers.gm_tools.require_universe_owner", new_callable=AsyncMock)
    @patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change")
    def test_resolution_is_staged_as_a_pending_proposal(
        self,
        mock_create: Mock,
        _mock_owner: AsyncMock,
    ) -> None:
        proposal_id = uuid4()
        mock_create.return_value = SimpleNamespace(proposal_id=proposal_id)
        story_id = uuid4()

        resp = client.post(
            "/api/gm/contradictions/resolve",
            json={
                "universe_id": str(uuid4()),
                "story_id": str(story_id),
                "fact_a": "The king is alive",
                "fact_b": "The king was killed",
                "conflict_type": "semantic",
                "resolution": "explanation_fact",
                "explanation": "The king faked his death.",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["proposal_id"] == str(proposal_id)
        params = mock_create.call_args.args[0]
        assert params.story_id == story_id
        assert params.content["resolution"] == "explanation_fact"
        assert params.content["fact_a"] == "The king is alive"
        assert params.proposal_type == "contradiction_resolution"

    def test_contradiction_schema_exposes_resolution_choices(self) -> None:
        contradiction = Contradiction(
            fact_a="A",
            fact_b="B",
            explanation="conflict",
            suggestion="resolve",
            conflict_type="timeline",
            scope="story",
        )
        assert contradiction.conflict_type == "timeline"
        assert contradiction.scope == "story"
        assert "retcon_older" in contradiction.suggested_resolutions

    def test_timeline_checks_detect_cycles_and_bad_ranges(self) -> None:
        from monitor_agents.plot_hooks import PlotHookAgent

        agent = PlotHookAgent.__new__(PlotHookAgent)
        events = [
            {
                "id": "a",
                "title": "The coronation",
                "start_time": "2026-01-02T00:00:00Z",
                "end_time": "2026-01-01T00:00:00Z",
                "timeline_before": ["b"],
            },
            {
                "id": "b",
                "title": "The coup",
                "start_time": "2026-01-03T00:00:00Z",
                "timeline_before": ["a"],
            },
        ]

        contradictions = agent._timeline_contradictions(events, scope="story")

        assert contradictions
        assert all(c.conflict_type == "timeline" for c in contradictions)
        assert all(c.scope == "story" for c in contradictions)
        assert any("ends at" in c.fact_b for c in contradictions)
        assert any("cycle" in c.explanation for c in contradictions)
