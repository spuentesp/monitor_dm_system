"""Tests for POST /api/gm/capture/insights — P1.2 per-entry capture insights.

The endpoint delegates to CaptureInsightAgent.analyze_entry (mocked here) and
returns the CaptureInsight verbatim. Invalid payloads (empty entry_text) are
rejected with 422.
"""

from __future__ import annotations

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
