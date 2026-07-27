"""Tests for POST /api/chat/{session_id}/wrap-up — P1.3 guided end-of-session
wrap-up digest, and the P1.4 persisted recap artifacts it writes.

The endpoint is gm_assistant-only: it canonizes the open scene (when the
phase isn't already ``scene_ended``), builds the digest from RecapAgent +
the canon queue + PlotHookAgent (all mocked here), and persists
``recap_text``/``wrapped_up_at`` onto the session doc. After wrap-up,
GET /recap serves the persisted artifact without re-calling RecapAgent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from monitor_agents.plot_hooks import SessionPrep
from monitor_data.schemas.base import Authority, ProposalStatus, ProposalType
from monitor_data.schemas.proposed_changes import (
    ProposedChangeListResponse,
    ProposedChangeResponse,
)

from monitor_ui.main import app

client = TestClient(app)

BASE = "/api/chat"


def _make_recording(session_id: str | None = None, **overrides) -> dict:
    now = datetime.now(UTC).isoformat()
    sid = session_id or str(uuid4())
    session = {
        "id": sid,
        "title": "Table log",
        "mode": "gm_assistant",
        "universe_id": str(uuid4()),
        "world_id": None,
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "phase": "active_play",
        "tone": "dramatic",
        "chat_mode": "ic",
        "created_at": now,
        "updated_at": now,
    }
    session.update(overrides)
    return session


def _proposal(status: ProposalStatus, label: str) -> ProposedChangeResponse:
    now = datetime.now(UTC)
    return ProposedChangeResponse(
        proposal_id=uuid4(),
        story_id=uuid4(),
        change_type=ProposalType.FACT,
        content={"description": label},
        confidence=0.9,
        authority=Authority.GM,
        proposer="gm_assistant",
        status=status,
        created_at=now,
        updated_at=now,
    )


def _canon_list() -> ProposedChangeListResponse:
    items = [
        _proposal(ProposalStatus.ACCEPTED, "Mira pocketed the chapel key"),
        _proposal(ProposalStatus.ACCEPTED, "The sealed door is beneath the chapel"),
        _proposal(ProposalStatus.REJECTED, "The king greeted the party"),
        _proposal(ProposalStatus.PENDING, "The cult meets at dawn"),
    ]
    return ProposedChangeListResponse(proposed_changes=items, total=len(items), limit=1000, offset=0)


RECAP_TEXT = "The party found the sealed door beneath the chapel and Mira took the key."

PREP = SessionPrep(
    recap="Recent scenes recap",
    open_threads=["The sealed door", "The missing key"],
    hooks=[],
    npc_reminders=["Mira"],
    world_state_changes=[],
)


def _patch_agents(mock_list_changes):
    """Patch RecapAgent, PlotHookAgent, the canon-queue read, and run_end_scene."""
    recap_cls = patch("monitor_agents.recap.agent.RecapAgent")
    prep_cls = patch("monitor_agents.plot_hooks.PlotHookAgent")
    end_scene = patch(
        "monitor_ui.routers.chat._run_end_scene",
        new=AsyncMock(return_value=("Scene ended.", {"type": "end_scene"})),
    )
    changes = patch(
        "monitor_ui.routers.chat.mongodb_list_proposed_changes",
        new=MagicMock(return_value=mock_list_changes),
    )
    return recap_cls, prep_cls, end_scene, changes


@patch("monitor_ui.routers.chat._db_save_session")
@patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
@patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
def test_wrap_up_unknown_session_404(_msgs, _sessions, _save):
    resp = client.post(f"{BASE}/{uuid4()}/wrap-up")
    assert resp.status_code == 404


@patch("monitor_ui.routers.chat._db_save_session")
@patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
@patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
def test_wrap_up_non_gm_assistant_409(_msgs, _sessions, _save):
    sid = str(uuid4())
    _sessions[sid] = _make_recording(sid, mode="autonomous_gm")
    _msgs[sid] = []

    resp = client.post(f"{BASE}/{sid}/wrap-up")
    assert resp.status_code == 409
    assert "gm_assistant" in resp.json()["detail"]


@patch("monitor_ui.routers.chat._db_save_session")
@patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
@patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
def test_wrap_up_happy_path(_msgs, _sessions, _save):
    sid = str(uuid4())
    _sessions[sid] = _make_recording(sid, phase="active_play")
    _msgs[sid] = []

    recap_cls, prep_cls, end_scene, changes = _patch_agents(_canon_list())
    with recap_cls as MockRecap, prep_cls as MockPrep, end_scene as mock_end, changes:
        MockRecap.return_value.generate_recap = AsyncMock(return_value=RECAP_TEXT)
        MockPrep.return_value.generate_session_prep = AsyncMock(return_value=PREP)

        resp = client.post(f"{BASE}/{sid}/wrap-up")

    assert resp.status_code == 200
    body = resp.json()
    assert body["recap"] == RECAP_TEXT
    assert body["accepted"] == 2
    assert body["rejected"] == 1
    assert body["pending"] == 1
    assert len(body["canon_items"]) == 4
    labels = {item["label"] for item in body["canon_items"]}
    assert "Mira pocketed the chapel key" in labels
    statuses = {item["status"] for item in body["canon_items"]}
    assert statuses == {"accepted", "rejected", "pending"}
    assert body["open_threads"] == ["The sealed door", "The missing key"]
    assert body["next_prep"]["npc_reminders"] == ["Mira"]

    # Phase wasn't scene_ended -> scene canonization ran first.
    mock_end.assert_awaited_once()

    # P1.4 — artifacts persisted onto the session doc.
    session = _sessions[sid]
    assert session["recap_text"] == RECAP_TEXT
    assert session["wrapped_up_at"]
    _save.assert_called()


@patch("monitor_ui.routers.chat._db_save_session")
@patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
@patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
def test_wrap_up_skips_end_scene_when_already_scene_ended(_msgs, _sessions, _save):
    sid = str(uuid4())
    _sessions[sid] = _make_recording(sid, phase="scene_ended")
    _msgs[sid] = []

    recap_cls, prep_cls, end_scene, changes = _patch_agents(_canon_list())
    with recap_cls as MockRecap, prep_cls as MockPrep, end_scene as mock_end, changes:
        MockRecap.return_value.generate_recap = AsyncMock(return_value=RECAP_TEXT)
        MockPrep.return_value.generate_session_prep = AsyncMock(return_value=PREP)

        resp = client.post(f"{BASE}/{sid}/wrap-up")

    assert resp.status_code == 200
    mock_end.assert_not_awaited()


@patch("monitor_ui.routers.chat._db_save_session")
@patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
@patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
def test_recap_returns_persisted_text_without_recap_agent(_msgs, _sessions, _save):
    """P1.4 read path: a wrapped-up session serves its stored recap."""
    sid = str(uuid4())
    wrapped = datetime.now(UTC).isoformat()
    _sessions[sid] = _make_recording(sid, phase="scene_ended", recap_text=RECAP_TEXT, wrapped_up_at=wrapped)
    _msgs[sid] = []

    with patch("monitor_agents.recap.agent.RecapAgent") as MockRecap:
        resp = client.get(f"{BASE}/{sid}/recap")

    assert resp.status_code == 200
    body = resp.json()
    assert body["recap"] == RECAP_TEXT
    assert body["persisted"] is True
    MockRecap.assert_not_called()


@patch("monitor_ui.routers.chat._db_save_session")
@patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
@patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
def test_recap_still_generates_for_fresh_session(_msgs, _sessions, _save):
    """Sessions without a persisted recap keep the live RecapAgent path."""
    sid = str(uuid4())
    _sessions[sid] = _make_recording(sid)
    _msgs[sid] = []

    with patch("monitor_agents.recap.agent.RecapAgent") as MockRecap:
        MockRecap.return_value.generate_recap = AsyncMock(return_value=RECAP_TEXT)
        resp = client.get(f"{BASE}/{sid}/recap")

    assert resp.status_code == 200
    body = resp.json()
    assert body["recap"] == RECAP_TEXT
    assert "persisted" not in body
    MockRecap.return_value.generate_recap.assert_awaited_once()
