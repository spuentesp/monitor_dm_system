"""Hermetic tests for POST /api/chat/{session_id}/rewind (UX-6 item 3).

Covers the rewind contract end to end against the in-process caches with
every persistence/canon boundary monkeypatched:

- removes the final player message plus every message after it,
- 404 when there is no player message, 409 while a turn is in flight,
- 409 when the exchange's canon is already accepted/committed,
- rejects the exchange's still-pending proposals with reason "rewound"
  through the data-layer tool seam (never a direct Neo4j write),
- rolls the scene's MongoDB checkpoint back before a scene-turn exchange
  (SceneLoop.backtrack) and refuses (409/503) before any mutation,
- trims an active NPC ConversationLoop's memory without ending it,
- clears session/loop state keyed to the exchange and leaves the rest of
  the transcript untouched,
- holds the in-flight mark across end-scene and wrap-up so rewind 409s
  while they run.
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

    def test_conversation_loop_is_left_alone_when_exchange_was_not_its_own(self, monkeypatch):
        """Only conversation_turn exchanges are trimmed; anything else (here:
        a plain exchange) leaves the cached loop untouched."""
        sid, _session = _seed(monkeypatch, [_msg("player", "Hi."), _msg("gm", "Hey.")])
        monkeypatch.setattr(chat_mod, "_rewind_list_proposals", _empty_list)
        chat_loops._CONVERSATION_LOOPS[sid] = object()

        r = _rewind(sid)
        assert r.status_code == 200, r.text
        assert sid in chat_loops._CONVERSATION_LOOPS


async def _empty_list(*, scene_uuid, story_uuid) -> list:
    return []


# ---------------------------------------------------------------------------
# Scene checkpoint rollback (Mongo LangGraph state, UX-6 limit 2)
# ---------------------------------------------------------------------------


def _patch_scene_loop(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: dict | None = None,
    on_backtrack=None,
) -> list:
    """Fake ``SceneLoop`` so the real checkpoint seam runs hermetically.

    Returns the list of constructed instances; ``on_backtrack`` (if given)
    is called with the instance when ``backtrack()`` runs.
    """
    created: list = []

    class _FakeSceneLoop:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.backtrack_calls = 0
            created.append(self)

        async def backtrack(self) -> dict:
            self.backtrack_calls += 1
            if on_backtrack is not None:
                on_backtrack(self)
            return dict(result or {})

    monkeypatch.setattr("monitor_agents.loops.scene_loop.SceneLoop", _FakeSceneLoop)
    return created


def _scene_turn_messages(scene_id: str, story_id: str) -> list[dict]:
    return [
        _msg("player", "I strike."),
        _msg(
            "gm",
            "Steel rings.",
            metadata={
                "type": "scene_turn",
                "scene_id": scene_id,
                "story_id": story_id,
                "turn_id": str(uuid4()),
            },
        ),
    ]


class TestRewindSceneCheckpoint:
    def test_scene_turn_exchange_rolls_back_before_transcript_mutation(self, monkeypatch):
        scene_id, story_id = str(uuid4()), str(uuid4())
        sid, _session = _seed(
            monkeypatch,
            _scene_turn_messages(scene_id, story_id),
            story_id=story_id,
            scene_id=scene_id,
        )
        _patch_proposals(monkeypatch, [])
        seen: dict = {}

        def _observe(loop) -> None:
            seen["messages_during_backtrack"] = len(chat_mod._MESSAGES[sid])
            seen["kwargs"] = loop.kwargs

        created = _patch_scene_loop(monkeypatch, on_backtrack=_observe)

        r = _rewind(sid)

        assert r.status_code == 200, r.text
        # The rollback ran while the transcript was still whole.
        assert seen["messages_during_backtrack"] == 2
        assert str(seen["kwargs"]["scene_id"]) == scene_id
        assert str(seen["kwargs"]["story_id"]) == story_id
        assert created[0].backtrack_calls == 1
        assert len(_messages(sid)) == 0  # mutation only after the rollback

    def test_non_scene_turn_exchange_leaves_the_checkpoint_alone(self, monkeypatch):
        sid, _session = _seed(monkeypatch, [_msg("player", "Hi."), _msg("gm", "Hey.")])
        monkeypatch.setattr(chat_mod, "_rewind_list_proposals", _empty_list)
        created = _patch_scene_loop(monkeypatch, result={"error": "should never run"})

        r = _rewind(sid)

        assert r.status_code == 200, r.text
        assert created == []
        assert len(_messages(sid)) == 0

    def test_checkpoint_canon_refusal_is_409_before_any_mutation(self, monkeypatch):
        scene_id, story_id = str(uuid4()), str(uuid4())
        sid, session = _seed(
            monkeypatch,
            _scene_turn_messages(scene_id, story_id),
            story_id=story_id,
            scene_id=scene_id,
        )
        _patch_proposals(monkeypatch, [])
        _patch_scene_loop(
            monkeypatch,
            result={
                "error": "2 change(s) from this turn were already accepted into canon, so the turn can't be undone."
            },
        )

        r = _rewind(sid)

        assert r.status_code == 409, r.text
        assert "accepted into canon" in r.json()["detail"]
        assert len(_messages(sid)) == 2  # fail closed: transcript untouched
        assert session.get("scene_id") == scene_id

    def test_checkpoint_storage_failure_is_503_before_any_mutation(self, monkeypatch):
        scene_id, story_id = str(uuid4()), str(uuid4())
        sid, _session = _seed(
            monkeypatch,
            _scene_turn_messages(scene_id, story_id),
            story_id=story_id,
            scene_id=scene_id,
        )
        _patch_proposals(monkeypatch, [])
        _patch_scene_loop(
            monkeypatch,
            result={
                "error": "The turn may be partly undone: the database stopped responding. "
                "Run /backtrack again to finish; it picks up where this stopped."
            },
        )

        r = _rewind(sid)

        assert r.status_code == 503, r.text
        assert r.json()["detail"] == chat_mod._REWIND_SCENE_CHECKPOINT_UNAVAILABLE
        assert len(_messages(sid)) == 2  # fail closed: nothing removed

    def test_nothing_to_roll_back_still_rewinds_the_transcript(self, monkeypatch):
        scene_id, story_id = str(uuid4()), str(uuid4())
        sid, _session = _seed(
            monkeypatch,
            _scene_turn_messages(scene_id, story_id),
            story_id=story_id,
            scene_id=scene_id,
        )
        _patch_proposals(monkeypatch, [])
        _patch_scene_loop(monkeypatch, result={"error": "Cannot backtrack further."})

        r = _rewind(sid)

        assert r.status_code == 200, r.text
        assert len(_messages(sid)) == 0


class TestRewindSceneCheckpointSeam:
    def test_skips_when_the_exchange_is_not_a_scene_turn(self, monkeypatch):
        created = _patch_scene_loop(monkeypatch, result={"error": "must not run"})
        asyncio.run(chat_mod._rewind_scene_checkpoint({"scene_id": None}, [_msg("gm", "Hey.")]))
        assert created == []

    def test_skips_when_the_scene_scope_is_missing(self, monkeypatch):
        created = _patch_scene_loop(monkeypatch, result={"error": "must not run"})
        removed = [_msg("gm", "Hit.", metadata={"type": "scene_turn"})]
        asyncio.run(chat_mod._rewind_scene_checkpoint({}, removed))
        assert created == []

    def test_prefers_the_exchanges_scope_over_the_session(self, monkeypatch):
        meta_scene, meta_story = str(uuid4()), str(uuid4())
        created = _patch_scene_loop(monkeypatch, result={})
        session = {"scene_id": str(uuid4()), "story_id": str(uuid4())}
        removed = [
            _msg(
                "gm",
                "Hit.",
                metadata={"type": "scene_turn", "scene_id": meta_scene, "story_id": meta_story},
            )
        ]

        asyncio.run(chat_mod._rewind_scene_checkpoint(session, removed))

        assert len(created) == 1
        assert str(created[0].kwargs["scene_id"]) == meta_scene
        assert str(created[0].kwargs["story_id"]) == meta_story


# ---------------------------------------------------------------------------
# ConversationLoop memory trim (UX-6 limit 1)
# ---------------------------------------------------------------------------


class _FakeConversationLoop:
    """Stands in for the cached ConversationLoop; records trim calls."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.trim_calls = 0

    async def trim_last_exchange(self) -> int:
        if self.fail:
            raise RuntimeError("mongo down")
        self.trim_calls += 1
        return 2


class TestRewindConversationLoop:
    def test_conversation_turn_exchange_trims_the_cached_loop_in_place(self, monkeypatch):
        sid, _session = _seed(
            monkeypatch,
            [
                _msg("player", "Hello."),
                _msg("gm", "Mira smiles.", metadata={"type": "conversation_turn"}),
            ],
        )
        loop = _FakeConversationLoop()
        chat_loops._CONVERSATION_LOOPS[sid] = loop
        try:
            r = _rewind(sid)
            assert r.status_code == 200, r.text
            assert loop.trim_calls == 1
            # Trimmed, not popped: popping would end the conversation.
            assert chat_loops.get_conversation_loop(sid) is loop
        finally:
            chat_loops._CONVERSATION_LOOPS.pop(sid, None)

    def test_trim_failure_keeps_the_loop_and_still_rewinds(self, monkeypatch):
        sid, _session = _seed(
            monkeypatch,
            [
                _msg("player", "Hello."),
                _msg("gm", "Mira smiles.", metadata={"type": "conversation_turn"}),
            ],
        )
        loop = _FakeConversationLoop(fail=True)
        chat_loops._CONVERSATION_LOOPS[sid] = loop
        try:
            r = _rewind(sid)
            assert r.status_code == 200, r.text
            assert len(_messages(sid)) == 0  # transcript still rewound
            assert chat_loops.get_conversation_loop(sid) is loop  # kept alive
        finally:
            chat_loops._CONVERSATION_LOOPS.pop(sid, None)

    def test_conversation_turn_without_a_cached_loop_is_a_noop(self, monkeypatch):
        sid, _session = _seed(
            monkeypatch,
            [
                _msg("player", "Hello."),
                _msg("gm", "Mira smiles.", metadata={"type": "conversation_turn"}),
            ],
        )
        assert chat_loops.get_conversation_loop(sid) is None
        r = _rewind(sid)
        assert r.status_code == 200, r.text
        assert len(_messages(sid)) == 0


# ---------------------------------------------------------------------------
# End-scene / wrap-up hold the in-flight mark (UX-6 limit 3)
# ---------------------------------------------------------------------------


def _patch_rewind_during(observed: dict):
    """Fake ``_run_end_scene`` that probes rewind while the mark is held."""

    async def _fake_end_scene(session_id, session, **kwargs):
        observed["in_flight"] = chat_mod.turn_in_flight(session_id)
        with pytest.raises(HTTPException) as exc_info:
            await chat_mod.rewind_last_exchange(session_id, principal=None)
        observed["rewind_status"] = exc_info.value.status_code
        observed["detail"] = exc_info.value.detail
        return ("Scene ended.", {"type": "end_scene"})

    return _fake_end_scene


class TestEndSceneWrapUpInFlight:
    def test_end_scene_marks_turn_and_rewind_answers_409_while_it_runs(self, monkeypatch):
        sid, _session = _seed(
            monkeypatch,
            [_msg("gm", "Opening.")],
            scene_id=str(uuid4()),
            story_id=str(uuid4()),
        )
        observed: dict = {}
        monkeypatch.setattr(chat_mod, "_run_end_scene", _patch_rewind_during(observed))
        monkeypatch.setattr(chat_mod, "fanout_completed_gm_message", AsyncMock())

        asyncio.run(chat_mod.end_scene(sid, principal=None))

        assert observed["in_flight"] is True
        assert observed["rewind_status"] == 409
        assert observed["detail"] == chat_mod._REWIND_IN_FLIGHT_DETAIL
        assert chat_mod.turn_in_flight(sid) is False  # cleared on the way out

    def test_wrap_up_marks_turn_and_rewind_answers_409_while_it_runs(self, monkeypatch):
        sid, session = _seed(
            monkeypatch,
            [_msg("gm", "Opening.")],
            mode="gm_assistant",
        )
        observed: dict = {}
        monkeypatch.setattr(chat_mod, "_run_end_scene", _patch_rewind_during(observed))
        monkeypatch.setattr(chat_mod, "fanout_completed_gm_message", AsyncMock())

        asyncio.run(chat_mod.wrap_up_session(sid, principal=None))

        assert observed["in_flight"] is True
        assert observed["rewind_status"] == 409
        assert observed["detail"] == chat_mod._REWIND_IN_FLIGHT_DETAIL
        assert chat_mod.turn_in_flight(sid) is False
        assert session.get("wrapped_up_at")  # the wrap-up itself completed

    def test_end_scene_clears_the_mark_when_the_scene_end_fails(self, monkeypatch):
        sid, _session = _seed(
            monkeypatch,
            [_msg("gm", "Opening.")],
            scene_id=str(uuid4()),
            story_id=str(uuid4()),
        )
        held: dict = {}

        async def _boom(session_id, session, **kwargs):
            held["in_flight"] = chat_mod.turn_in_flight(session_id)
            raise RuntimeError("scene end exploded")

        monkeypatch.setattr(chat_mod, "_run_end_scene", _boom)

        with pytest.raises(RuntimeError, match="scene end exploded"):
            asyncio.run(chat_mod.end_scene(sid, principal=None))

        assert held["in_flight"] is True
        assert chat_mod.turn_in_flight(sid) is False

    def test_wrap_up_clears_the_mark_when_the_operation_fails(self, monkeypatch):
        sid, _session = _seed(monkeypatch, [_msg("gm", "Opening.")], mode="gm_assistant")
        held: dict = {}

        async def _boom(session_id, session, **kwargs):
            held["in_flight"] = chat_mod.turn_in_flight(session_id)
            raise RuntimeError("wrap-up exploded")

        monkeypatch.setattr(chat_mod, "_run_end_scene", _boom)

        with pytest.raises(RuntimeError, match="wrap-up exploded"):
            asyncio.run(chat_mod.wrap_up_session(sid, principal=None))

        assert held["in_flight"] is True
        assert chat_mod.turn_in_flight(sid) is False
