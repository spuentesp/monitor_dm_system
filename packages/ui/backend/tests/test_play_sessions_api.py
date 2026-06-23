"""Contract tests for the /api/play-sessions router (P-15)."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from monitor_data.schemas.base import SessionStatus
from monitor_data.schemas.play_sessions import (
    PlaySessionResponse,
    PlaySessionListResponse,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def client():
    from monitor_ui.main import create_app

    return TestClient(create_app())


def _fake_session(
    session_id=None,
    story_id=None,
    universe_id=None,
    session_number=1,
    status=SessionStatus.ACTIVE,
) -> PlaySessionResponse:
    return PlaySessionResponse(
        session_id=session_id or uuid4(),
        story_id=story_id or uuid4(),
        universe_id=universe_id or uuid4(),
        session_number=session_number,
        status=status,
        player_ids=[],
        scene_ids=[],
        gm_notes="notes",
        started_at=__import__("datetime").datetime(2026, 6, 3, 12, 0, 0),
        created_at=__import__("datetime").datetime(2026, 6, 3, 12, 0, 0),
        updated_at=__import__("datetime").datetime(2026, 6, 3, 12, 0, 0),
    )


# =============================================================================
# CRUD
# =============================================================================


def test_create_returns_201_and_calls_tool(client):
    body = {
        "story_id": str(uuid4()),
        "universe_id": str(uuid4()),
        "session_number": 1,
    }
    with patch(
        "monitor_ui.routers.play_sessions.mongodb_create_play_session",
        return_value=_fake_session(),
    ) as mock_create:
        response = client.post("/api/play-sessions", json=body)
    assert response.status_code == 201
    assert response.json()["status"] == "active"
    mock_create.assert_called_once()


def test_create_duplicate_session_number_returns_409(client):
    body = {
        "story_id": str(uuid4()),
        "universe_id": str(uuid4()),
        "session_number": 1,
    }
    with patch(
        "monitor_ui.routers.play_sessions.mongodb_create_play_session",
        side_effect=ValueError("Session #1 already exists"),
    ):
        response = client.post("/api/play-sessions", json=body)
    assert response.status_code == 409
    assert "Session #1" in response.json()["detail"]


def test_get_returns_session_or_404(client):
    session = _fake_session()
    with patch(
        "monitor_ui.routers.play_sessions.mongodb_get_play_session",
        return_value=session,
    ):
        response = client.get(f"/api/play-sessions/{session.session_id}")
    assert response.status_code == 200
    assert response.json()["session_id"] == str(session.session_id)

    with patch(
        "monitor_ui.routers.play_sessions.mongodb_get_play_session", return_value=None
    ):
        response = client.get(f"/api/play-sessions/{uuid4()}")
    assert response.status_code == 404


def test_get_rejects_invalid_uuid(client):
    response = client.get("/api/play-sessions/not-a-uuid")
    assert response.status_code == 400


def test_list_passes_filters(client):
    fake_list = PlaySessionListResponse(
        sessions=[_fake_session()], total=1, limit=50, offset=0
    )
    with patch(
        "monitor_ui.routers.play_sessions.mongodb_list_play_sessions",
        return_value=fake_list,
    ) as mock_list:
        response = client.get(
            "/api/play-sessions",
            params={"story_id": str(uuid4()), "status": "active", "limit": 25},
        )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    called_filters = mock_list.call_args.args[0]
    assert called_filters.limit == 25
    assert called_filters.status == SessionStatus.ACTIVE


def test_update_calls_tool_with_uuid(client):
    session = _fake_session()
    with patch(
        "monitor_ui.routers.play_sessions.mongodb_update_play_session",
        return_value=session,
    ) as mock_update:
        response = client.patch(
            f"/api/play-sessions/{session.session_id}",
            json={"status": "completed"},
        )
    assert response.status_code == 200
    assert mock_update.call_args.args[0] == session.session_id


def test_update_returns_404_when_missing(client):
    with patch(
        "monitor_ui.routers.play_sessions.mongodb_update_play_session",
        return_value=None,
    ):
        response = client.patch(
            f"/api/play-sessions/{uuid4()}", json={"status": "completed"}
        )
    assert response.status_code == 404


def test_add_scene_is_idempotent_via_tool(client):
    session = _fake_session()
    with patch(
        "monitor_ui.routers.play_sessions.mongodb_add_scene_to_play_session",
        return_value=session,
    ) as mock_add:
        scene_id = uuid4()
        response = client.post(
            f"/api/play-sessions/{session.session_id}/scenes/{scene_id}"
        )
    assert response.status_code == 200
    assert mock_add.call_args.args[1] == scene_id


# =============================================================================
# AGGREGATE
# =============================================================================


def test_play_home_returns_active_and_recent(client):
    universe_id = uuid4()
    active = _fake_session(universe_id=universe_id, status=SessionStatus.ACTIVE)
    completed = _fake_session(universe_id=universe_id, status=SessionStatus.COMPLETED)

    with (
        patch(
            "monitor_ui.routers.play_sessions.mongodb_list_play_sessions",
            return_value=PlaySessionListResponse(
                sessions=[active], total=1, limit=10, offset=0
            ),
        ),
        patch(
            "monitor_ui.routers.play_sessions.mongodb_list_recent_play_sessions",
            return_value=[active, completed],
        ),
    ):
        response = client.get(f"/api/universes/{universe_id}/play-home")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["active_sessions"]) == 1
    assert len(payload["recent_recaps"]) == 2


def test_play_home_rejects_invalid_universe_uuid(client):
    response = client.get("/api/universes/not-a-uuid/play-home")
    assert response.status_code == 400
