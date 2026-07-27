"""Tests for POST /api/gm/capture/contradiction-check — P1.1 live capture alerts.

The endpoint is advisory: it delegates to CanonKeeper.check_live_entry (mocked
here) and maps a hit into a Contradiction alert, or returns ``alert: null``.
Invalid payloads (empty entry_text) are rejected with 422.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)


def test_contradiction_returns_alert():
    with patch("monitor_ui.routers.gm_tools.CanonKeeper") as mock_keeper_cls:
        mock_keeper_cls.return_value.check_live_entry = AsyncMock(
            return_value={
                "has_contradiction": True,
                "explanation": "The king cannot greet anyone: canon says he is dead.",
            }
        )
        response = client.post(
            "/api/gm/capture/contradiction-check",
            json={
                "universe_id": str(uuid4()),
                "entry_text": "The king greeted the party at the gate",
            },
        )
    assert response.status_code == 200
    alert = response.json()["alert"]
    assert alert is not None
    assert alert["severity"] == "medium"
    assert "king" in alert["explanation"].lower()
    assert alert["suggestion"] == "Review this entry against canon before canonizing."
    assert alert["fact_a"].startswith("Established canon:")
    assert "The king greeted the party" in alert["fact_b"]


def test_no_contradiction_returns_null_alert():
    with patch("monitor_ui.routers.gm_tools.CanonKeeper") as mock_keeper_cls:
        mock_keeper_cls.return_value.check_live_entry = AsyncMock(
            return_value={"has_contradiction": False, "explanation": ""}
        )
        response = client.post(
            "/api/gm/capture/contradiction-check",
            json={
                "universe_id": str(uuid4()),
                "entry_text": "The party camped under the stars",
            },
        )
    assert response.status_code == 200
    assert response.json()["alert"] is None


def test_empty_entry_text_rejected_422():
    response = client.post(
        "/api/gm/capture/contradiction-check",
        json={"universe_id": str(uuid4()), "entry_text": ""},
    )
    assert response.status_code == 422


def test_oversized_entry_text_rejected_422():
    response = client.post(
        "/api/gm/capture/contradiction-check",
        json={"universe_id": str(uuid4()), "entry_text": "x" * 4001},
    )
    assert response.status_code == 422


def test_agent_failure_returns_500():
    with patch("monitor_ui.routers.gm_tools.CanonKeeper") as mock_keeper_cls:
        mock_keeper_cls.return_value.check_live_entry = AsyncMock(side_effect=RuntimeError("neo4j unreachable"))
        response = client.post(
            "/api/gm/capture/contradiction-check",
            json={
                "universe_id": str(uuid4()),
                "entry_text": "The king greeted the party at the gate",
            },
        )
    assert response.status_code == 500
    assert "Failed to check capture entry" in response.json()["detail"]
