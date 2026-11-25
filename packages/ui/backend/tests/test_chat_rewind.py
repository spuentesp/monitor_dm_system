"""Hermetic tests for POST /api/chat/{session_id}/rewind (UX-6 item 3).

Covers the rewind contract end to end against the in-process caches with
every persistence/canon boundary monkeypatched:

- removes the final player message plus every message after it,
- 404 when there is no player message, 409 while a turn is in flight,
- 409 when the exchange's canon is already accepted/committed,
- rejects the exchange's still-pending proposals with reason "rewound"
  through the data-layer tool seam (never a direct Neo4j write),
- clears session/loop state keyed to the exchange and leaves the rest of
  the transcript untouched.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import monitor_ui.routers.chat as chat_mod
import monitor_ui.routers.chat_loops as chat_loops
from monitor_data.schemas.base import ProposalStatus
from monitor_data.schemas.proposed_changes import ProposedChangeUpdate
from monitor_ui.main import app

pytestmark = pytest.mark.usefixtures("local_auth_mode")

client = TestClient(app, raise_server_exceptions=False)

BASE = "/api/chat"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _msg(role: str, content: str, *, metadata: dict | None = None, timestamp: str | None = None) -> dict:
    return {
        "id": str(uuid4()),
        "session_id": "",  # filled by _seed
        "role": role,
        "content": content,
        "timestamp": timestamp or _now(),
        "metadata": metadata or {},
    }


def _seed(
    monkeypatch: pytest.MonkeyPatch,
    messages: list[dict],
    **session_overrides,
) -> tuple[str, dict]:
    """Install a session + transcript into the chat module caches.

    Stubs every persistence boundary (session/message save, Redis-backed
    delete, WS fanout) so the test is hermetic, and leaves
    ``_db_delete_messages`` patchable per test.
    """
    sid = str(uuid4())
    session = {
        "id": sid,
        "title": "Rewind",
        "mode": "autonomous_gm",
        "phase": "active_play",
        "owner_id": None,
        "created_at": _now(),
        "updated_at": _now(),
        **session_overrides,
    }
    for m in messages:
        m["session_id"] = sid
    monkeypatch.setattr(chat_mod, "_SESSIONS", {sid: session})
    monkeypatch.setattr(chat_mod, "_MESSAGES", {sid: list(messages)})
    monkeypatch.setattr(chat_mod, "_ensure_sessions_loaded", lambda: None)
    monkeypatch.setattr(chat_mod, "_db_save_session", lambda s: None)
    monkeypatch.setattr(chat_mod, "_db_save_message", lambda m: None)
    monkeypatch.setattr(chat_mod, "_db_delete_messages", lambda sid_, ids: len(ids))
    monkeypatch.setattr(chat_mod, "fanout_event", AsyncMock())
    return sid, session


def _messages(sid: str) -> list[dict]:
    return chat_mod._MESSAGES[sid]


def _rewind(sid: str):
    return client.post(f"{BASE}/{sid}/rewind")


def _patch_proposals(monkeypatch: pytest.MonkeyPatch, proposals: list) -> list:
    """Replace the proposal list/reject seams; return the reject calls."""
    rejected: list[UUID] = []

    async def _list(*, scene_uuid, story_uuid):
        return proposals

    async def _reject(proposal_id: UUID) -> None:
        rejected.append(proposal_id)

    monkeypatch.setattr(chat_mod, "_rewind_list_proposals", _list)
    monkeypatch.setattr(chat_mod, "_rewind_reject_proposal", _reject)
    return rejected


def _proposal(
    *,
    status: ProposalStatus,
    turn_id: UUID | None = None,
    created_at: datetime | None = None,
    scene_id: UUID | None = None,
    story_id: UUID | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        proposal_id=uuid4(),
        status=status,
        turn_id=turn_id,
        created_at=created_at or datetime.now(UTC),
        scene_id=scene_id,
        story_id=story_id,
    )


# ---------------------------------------------------------------------------
# Transcript surgery
# ---------------------------------------------------------------------------


class TestRewindTranscript:
    def test_removes_final_player_message_and_everything_after_it(self, monkeypatch):
        sid, _session = _seed(monkeypatch, [])
        old_turn_id = str(uuid4())
        old = [
            _msg("gm", "Opening."),
            _msg("player", "I enter."),
            _msg("gm", "It is dark.", metadata={"turn_id": str(uuid4())}),
            _msg("player", "I light a torch."),
            _msg("gm", "Flames bloom.", metadata={"turn_id": old_turn_id}),
            _msg("system", "Scene checkpoint saved."),
        ]
        monkeypatch.setattr(chat_mod, "_MESSAGES", {sid: old})
        removed_ids = [m["id"] for m in old[3:]]
        delete_mock = MockDelete()
        monkeypatch.setattr(chat_mod, "_db_delete_messages", delete_mock)

        r = _rewind(sid)

        assert r.status_code == 200, r.text
        assert r.json() == {"removed": 3, "last_player_text": "I light a torch."}
        assert [m["content"] for m in _messages(sid)] == ["Opening.", "I enter.", "It is dark."]
        assert delete_mock.calls == [(sid, removed_ids)]

    def test_trailing_player_message_with_no_gm_reply_is_removed(self, monkeypatch):
        sid, _session = _seed(
            monkeypatch,
            [_msg("gm", "Opening."), _msg("player", "Knock knock.")],
        )
        r = _rewind(sid)
        assert r.status_code == 200, r.text
        assert r.json() == {"removed": 1, "last_player_text": "Knock knock."}
        assert [m["role"] for m in _messages(sid)] == ["gm"]

    def test_404_when_no_player_message_exists(self, monkeypatch):
        sid, _session = _seed(monkeypatch, [_msg("gm", "Opening."), _msg("system", "Note.")])
        r = _rewind(sid)
        assert r.status_code == 404, r.text
        assert "No player message" in r.json()["detail"]
        assert len(_messages(sid)) == 2  # untouched

    def test_404_for_unknown_session(self):
        assert _rewind(str(uuid4())).status_code == 404


class MockDelete:
    """Recording stand-in for the persistence delete wrapper."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, session_id: str, message_ids: list[str]) -> int:
        self.calls.append((session_id, list(message_ids)))
        return len(message_ids)


# ---------------------------------------------------------------------------
# In-flight guard
# ---------------------------------------------------------------------------


class TestRewindInFlight:
    def test_409_while_a_turn_is_in_flight(self, monkeypatch):
        sid, _session = _seed(
            monkeypatch,
            [_msg("gm", "Opening."), _msg("player", "Hi.")],
        )
        chat_mod._begin_turn(sid)
        try:
            r = _rewind(sid)
            assert r.status_code == 409, r.text
            assert "still in flight" in r.json()["detail"]
            assert len(_messages(sid)) == 2  # untouched
        finally:
            chat_mod._end_turn(sid)
        assert _rewind(sid).status_code == 200

    def test_send_marks_and_clears_the_turn(self, monkeypatch):
        from monitor_ui.routers.chat_schemas import MessageSend

        sid, _session = _seed(monkeypatch, [])
        seen: dict[str, bool] = {}

        async def _fake_execute(session_id, body, principal, db):
            seen["during"] = chat_mod.turn_in_flight(session_id)
            return None

        monkeypatch.setattr(chat_mod, "_execute_send_message", _fake_execute)
        asyncio.run(chat_mod.send_message(sid, MessageSend(content="hi"), principal=None, db=None))
        assert seen["during"] is True
        assert chat_mod.turn_in_flight(sid) is False

    def test_ws_frame_holds_the_mark_only_while_processing(self, monkeypatch):
        """Each WS frame marks the session in-flight for exactly its own
        processing span; every exit path (incl. disconnect) clears it."""
        sid, _session = _seed(monkeypatch, [])
        marks: list[bool] = []

        class _FakeSocket:
            def __init__(self) -> None:
                self._frames = ["one", "two"]

            async def receive_text(self) -> str:
                if self._frames:
                    return self._frames.pop(0)
                from starlette.websockets import WebSocketDisconnect

                raise WebSocketDisconnect(1000)

        async def _run() -> None:
            from starlette.websockets import WebSocketDisconnect

            ws = _FakeSocket()
            try:
                async for _raw in chat_mod._ws_turn_frames(ws, sid):  # type: ignore[arg-type]
                    marks.append(chat_mod.turn_in_flight(sid))
            except WebSocketDisconnect:
                pass  # the handler's own except clause in miniature

        asyncio.run(_run())
        assert marks == [True, True]
        assert chat_mod.turn_in_flight(sid) is False

    def test_ws_frame_end_is_idempotent_across_generator_and_handler(self, monkeypatch):
        """Handler teardown calling _end_ws_frame again must not eat another
        socket's mark (per-socket pop)."""
        sid, _session = _seed(monkeypatch, [])

        class _FakeSocket:
            async def receive_text(self) -> str:
                return "frame"

        ws = _FakeSocket()
        other_ws = object()

        chat_mod._begin_ws_frame(ws, sid)  # type: ignore[arg-type]
        chat_mod._begin_ws_frame(other_ws, sid)  # type: ignore[arg-type]
        chat_mod._end_ws_frame(ws)  # type: ignore[arg-type]
        assert chat_mod.turn_in_flight(sid) is True  # other socket still in flight
        chat_mod._end_ws_frame(ws)  # second teardown: no-op
        assert chat_mod.turn_in_flight(sid) is True
        chat_mod._end_ws_frame(other_ws)  # type: ignore[arg-type]
        assert chat_mod.turn_in_flight(sid) is False


# ---------------------------------------------------------------------------
# Canon gate + pending rejection
# ---------------------------------------------------------------------------


class TestRewindCanonGate:
    def test_409_when_exchange_canon_is_already_accepted(self, monkeypatch):
        turn_id = uuid4()
        sid, _session = _seed(
            monkeypatch,
            [
                _msg("player", "I swear fealty."),
                _msg("gm", "It is done.", metadata={"turn_id": str(turn_id)}),
            ],
            story_id=str(uuid4()),
        )
        rejected = _patch_proposals(monkeypatch, [_proposal(status=ProposalStatus.ACCEPTED, turn_id=turn_id)])

        r = _rewind(sid)
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == "The GM's last turn already changed canon; it can't be rewound."
        assert rejected == []  # no mutation of any kind
        assert len(_messages(sid)) == 2  # transcript untouched

    def test_committed_status_counts_as_accepted(self, monkeypatch):
        """Legacy 'committed' rows coerce to ACCEPTED at the API boundary."""
        turn_id = uuid4()
        sid, _session = _seed(
            monkeypatch,
            [
                _msg("player", "Do it."),
                _msg("gm", "Done.", metadata={"turn_id": str(turn_id)}),
            ],
            story_id=str(uuid4()),
        )
        committed = SimpleNamespace(
            proposal_id=uuid4(),
            status=ProposalStatus.ACCEPTED,  # what _coerce_proposal_status returns for 'committed'
            turn_id=turn_id,
            created_at=datetime.now(UTC),
            scene_id=None,
            story_id=None,
        )
        _patch_proposals(monkeypatch, [committed])
        assert _rewind(sid).status_code == 409

    def test_pending_proposal_from_exchange_is_rejected(self, monkeypatch):
        turn_id = uuid4()
        sid, _session = _seed(
            monkeypatch,
            [
                _msg("player", "I draw steel."),
                _msg("gm", "Clang.", metadata={"turn_id": str(turn_id)}),
            ],
            story_id=str(uuid4()),
        )
        pending = _proposal(status=ProposalStatus.PENDING, turn_id=turn_id)
        unrelated = _proposal(status=ProposalStatus.PENDING, turn_id=uuid4())
        rejected = _patch_proposals(monkeypatch, [pending, unrelated])

        r = _rewind(sid)
        assert r.status_code == 200, r.text
        assert rejected == [pending.proposal_id]  # other turn untouched

    def test_proposal_without_turn_link_matches_exchange_time_window(self, monkeypatch):
        now = datetime.now(UTC)
        player_ts = (now - timedelta(seconds=5)).isoformat()
        sid, _session = _seed(
            monkeypatch,
            [
                _msg("player", "Hi.", timestamp=player_ts),
                _msg("gm", "Hello."),
            ],
            story_id=str(uuid4()),
        )
        in_window = _proposal(status=ProposalStatus.PENDING, turn_id=None, created_at=now)
        older = _proposal(
            status=ProposalStatus.PENDING,
            turn_id=None,
            created_at=now - timedelta(minutes=10),
        )
        rejected = _patch_proposals(monkeypatch, [in_window, older])

        r = _rewind(sid)
        assert r.status_code == 200, r.text
        assert rejected == [in_window.proposal_id]

    def test_reject_payload_uses_reason_rewound_via_data_layer_tool(self, monkeypatch):
        """_rewind_reject_proposal builds pending -> rejected with reason
        "rewound" and runs it through the data-layer tool (no Neo4j)."""
        pid = uuid4()
        captured: dict = {}

        async def _fake_run_read(fn, *args):
            captured["fn"] = fn
            captured["args"] = args
            return None

        monkeypatch.setattr(chat_mod, "_rewind_run_read", _fake_run_read)
        monkeypatch.setattr(chat_mod, "_REWIND_PROPOSALS_AVAILABLE", True)

        asyncio.run(chat_mod._rewind_reject_proposal(pid))
        assert captured["fn"] is chat_mod.mongodb_update_proposed_change
        arg_pid, update = captured["args"]
        assert arg_pid == pid
        assert isinstance(update, ProposedChangeUpdate)
        assert update.status == ProposalStatus.REJECTED
        assert update.decision_metadata is not None
        assert update.decision_metadata.reason == "rewound"
        assert update.decision_metadata.decided_by == "rewind"

    def test_listing_failure_fails_closed_with_503(self, monkeypatch):
        sid, session = _seed(
            monkeypatch,
            [_msg("player", "Hi."), _msg("gm", "Hey.")],
            story_id=str(uuid4()),
        )

        async def _boom(*, scene_uuid, story_uuid):
            raise HTTPException(status_code=503, detail="Couldn't verify canon changes for this turn — rewind aborted.")

        monkeypatch.setattr(chat_mod, "_rewind_list_proposals", _boom)
        r = _rewind(sid)
        assert r.status_code == 503, r.text
        assert len(_messages(sid)) == 2  # fail closed: nothing removed
        assert session is chat_mod._SESSIONS[sid]


# ---------------------------------------------------------------------------
# Session state + loop caches
# ---------------------------------------------------------------------------


class TestRewindSideState:
    def test_clears_pending_fields_and_latest_state_of_the_exchange(self, monkeypatch):
        turn_id = str(uuid4())
        prior_turn = str(uuid4())
        sid, session = _seed(
            monkeypatch,
            [
                _msg("player", "Old action."),
                _msg(
                    "gm",
                    "Old reply.",
                    metadata={"turn_id": prior_turn, "working_state": {"hp": 9}},
                ),
                _msg("player", "New action."),
                _msg(
                    "gm",
                    "New reply.",
                    metadata={
                        "turn_id": turn_id,
                        "requires_player_choice": True,
                        "dice_request": {"spec": "1d20"},
                    },
                ),
            ],
            story_id=str(uuid4()),
            scene_id=str(uuid4()),
            pending_consequence={"turn_id": turn_id, "options": ["a"]},
            pending_dice_request={"turn_id": turn_id, "spec": "1d20"},
            latest_working_state={"hp": 1},
            latest_social_read={"deltas": {"x": 1}},
        )
        # Scope is present (story/scene uuids) but no proposal tools are
        # touched in this test: no turn-less proposals match, no turns listed.
        monkeypatch.setattr(chat_mod, "_rewind_list_proposals", _empty_list)

        r = _rewind(sid)
        assert r.status_code == 200, r.text
        assert "pending_consequence" not in session
        assert "pending_dice_request" not in session
        # latest state re-derived from the new last GM message
        assert session["latest_working_state"] == {"hp": 9}
        assert "latest_social_read" not in session
        assert session["updated_at"]

    def test_pops_cached_scene_and_preplay_loops(self, monkeypatch):
        from monitor_agents.loops import preplay_orchestrator as preplay_mod

        sid, _session = _seed(monkeypatch, [_msg("player", "Hi."), _msg("gm", "Hey.")])
        monkeypatch.setattr(chat_mod, "_rewind_list_proposals", _empty_list)
        chat_loops._SCENE_LOOPS[sid] = ("signature", object())
        preplay_mod._CHAR_CREATION_LOOPS[sid] = None
        preplay_mod._CHARACTER_INTERVIEW_LOOPS[sid] = None
        preplay_mod._STORY_AGREEMENT_LOOPS[sid] = None
        try:
            r = _rewind(sid)
            assert r.status_code == 200, r.text
            assert sid not in chat_loops._SCENE_LOOPS
            assert sid not in preplay_mod._CHAR_CREATION_LOOPS
            assert sid not in preplay_mod._CHARACTER_INTERVIEW_LOOPS
            assert sid not in preplay_mod._STORY_AGREEMENT_LOOPS
        finally:
            chat_loops._SCENE_LOOPS.pop(sid, None)
            preplay_mod._CHAR_CREATION_LOOPS.pop(sid, None)
            preplay_mod._CHARACTER_INTERVIEW_LOOPS.pop(sid, None)
            preplay_mod._STORY_AGREEMENT_LOOPS.pop(sid, None)

    def test_conversation_loop_is_left_alone(self, monkeypatch):
        """No clean trim API exists for ConversationLoop — documented decision."""
        sid, _session = _seed(monkeypatch, [_msg("player", "Hi."), _msg("gm", "Hey.")])
        monkeypatch.setattr(chat_mod, "_rewind_list_proposals", _empty_list)
        chat_loops._CONVERSATION_LOOPS[sid] = object()

        r = _rewind(sid)
        assert r.status_code == 200, r.text
        assert sid in chat_loops._CONVERSATION_LOOPS


async def _empty_list(*, scene_uuid, story_uuid) -> list:
    return []
