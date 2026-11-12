"""Tests for the G03 entry-correction routes (CF-1 amendment).

Local-mode wiring tests assert the cross-component contract: the routes
delegate to SessionIngestAgent / CaptureInsightAgent with the expected
arguments, striking retracts the entry's pending capture proposals, and the
insight re-run on edit is fail-open. A second class runs in enforced auth
mode and proves owner-only strike/edit/restore (foreign session entries get
the generic 404 before the handler runs).

Run:
    uv run pytest packages/ui/backend/tests/test_gm_entry_correction_routes.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_agents.ingestion.capture_insights import CaptureInsight
from monitor_data.schemas.base import ProposalStatus, ProposalType
from monitor_data.schemas.proposed_changes import (
    ProposedChangeListResponse,
    ProposedChangeResponse,
)

from monitor_ui.main import app

client = TestClient(app)


def _entry(entry_id: str | None = None, **overrides: Any) -> dict[str, Any]:
    doc = {
        "id": entry_id or str(uuid4()),
        "session_id": "rec-1",
        "role": "player",
        "content": "Mira pocketed the key",
        "timestamp": "2026-11-10T20:00:00+00:00",
        "struck": False,
        "struck_at": None,
        "struck_reason": None,
        "struck_proposal_ids": [],
        "edited_at": None,
    }
    doc.update(overrides)
    return doc


def _pending_proposal(entry_id: str) -> ProposedChangeResponse:
    return ProposedChangeResponse(
        proposal_id=uuid4(),
        scene_id=uuid4(),
        story_id=uuid4(),
        change_type=ProposalType.FACT,
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


def _list_response(proposals: list[ProposedChangeResponse]) -> ProposedChangeListResponse:
    return ProposedChangeListResponse(
        proposed_changes=proposals,
        total=len(proposals),
        limit=500,
        offset=0,
    )


# ---------------------------------------------------------------------------
# Local-mode wiring tests
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("local_auth_mode")
class TestEntryCorrectionRoutes:
    def test_patch_entry_updates_transcript_and_reruns_insight(self):
        entry = _entry()
        insight = CaptureInsight(
            participants=["Mira"],
            candidate_facts=["the key is now with Mira"],
        )
        with (
            patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls,
            patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls,
            patch("monitor_ui.routers.gm_tools.mongodb_list_proposed_changes") as mock_list,
            patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change") as mock_create,
        ):
            ingest_cls.return_value.update_entry = AsyncMock(return_value={**entry, "content": "corrected"})
            capture_cls.return_value.analyze_entry = AsyncMock(return_value=insight)
            mock_list.return_value = _list_response([])
            resp = client.patch(
                f"/api/gm/session-log/entries/{entry['id']}",
                json={
                    "universe_id": str(uuid4()),
                    "text": "corrected",
                    "story_id": str(uuid4()),
                    "scene_id": str(uuid4()),
                },
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["entry"]["content"] == "corrected"
        assert body["entry"]["id"] == entry["id"]
        assert body["insight_skipped"] is False
        assert body["insight"]["candidate_facts"] == ["the key is now with Mira"]
        ingest_cls.return_value.update_entry.assert_awaited_once_with(entry["id"], "corrected")
        capture_cls.return_value.analyze_entry.assert_awaited_once()
        # New candidate facts from the edited text are staged for CF-8.
        mock_create.assert_called_once()

    def test_patch_entry_insight_failure_is_fail_open(self):
        entry = _entry()
        with (
            patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls,
            patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls,
        ):
            ingest_cls.return_value.update_entry = AsyncMock(return_value=entry)
            capture_cls.return_value.analyze_entry = AsyncMock(side_effect=RuntimeError("LLM down"))
            resp = client.patch(
                f"/api/gm/session-log/entries/{entry['id']}",
                json={"universe_id": str(uuid4()), "text": "corrected"},
            )

        assert resp.status_code == 200
        body = resp.json()
        # Entry kept, insight skipped — the GM's correction is never lost.
        assert body["entry"]["content"] == "Mira pocketed the key"
        assert body["insight"] is None
        assert body["insight_skipped"] is True

    def test_patch_missing_entry_returns_404(self):
        with patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls:
            ingest_cls.return_value.update_entry = AsyncMock(side_effect=ValueError("Session entry nope not found"))
            resp = client.patch(
                "/api/gm/session-log/entries/nope",
                json={"universe_id": str(uuid4()), "text": "x"},
            )
        assert resp.status_code == 404

    def test_patch_empty_text_rejected_422(self):
        resp = client.patch(
            f"/api/gm/session-log/entries/{uuid4()}",
            json={"universe_id": str(uuid4()), "text": ""},
        )
        assert resp.status_code == 422

    def test_strike_retracts_pending_capture_proposals_then_strikes(self):
        entry = _entry()
        proposal = _pending_proposal(entry["id"])
        with (
            patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls,
            patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls,
            patch("monitor_ui.routers.gm_tools.mongodb_list_proposed_changes") as mock_list,
        ):
            ingest_cls.return_value.get_entry = AsyncMock(return_value=entry)
            ingest_cls.return_value.strike_entry = AsyncMock(
                return_value={
                    **entry,
                    "struck": True,
                    "struck_at": "2026-11-10T20:10:00+00:00",
                    "struck_reason": "struck at the table",
                    "struck_proposal_ids": [str(proposal.proposal_id)],
                }
            )
            capture_cls.return_value.retract_proposal = AsyncMock(
                return_value={"proposal_id": str(proposal.proposal_id), "status": "rejected"}
            )
            mock_list.return_value = _list_response([proposal])

            resp = client.delete(f"/api/gm/session-log/entries/{entry['id']}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entry"]["struck"] is True
        assert body["retracted_proposal_ids"] == [str(proposal.proposal_id)]
        assert body["retract_errors"] == []
        # Only this entry's pending capture proposals are considered.
        filt = mock_list.call_args.args[0]
        assert filt.source == f"capture_entry:{entry['id']}"
        assert filt.status == ProposalStatus.PENDING
        capture_cls.return_value.retract_proposal.assert_awaited_once_with(
            str(proposal.proposal_id),
            reason="struck at the table",
            entry_id=entry["id"],
        )
        ingest_cls.return_value.strike_entry.assert_awaited_once_with(
            entry["id"],
            retracted_proposal_ids=[str(proposal.proposal_id)],
            reason="struck at the table",
        )

    def test_strike_missing_entry_returns_404(self):
        with patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls:
            ingest_cls.return_value.get_entry = AsyncMock(return_value=None)
            ingest_cls.return_value.strike_entry = AsyncMock()
            resp = client.delete(f"/api/gm/session-log/entries/{uuid4()}")
        assert resp.status_code == 404
        ingest_cls.return_value.strike_entry.assert_not_awaited()

    def test_strike_still_lands_when_a_retract_fails(self):
        entry = _entry()
        proposal = _pending_proposal(entry["id"])
        with (
            patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls,
            patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls,
            patch("monitor_ui.routers.gm_tools.mongodb_list_proposed_changes") as mock_list,
        ):
            ingest_cls.return_value.get_entry = AsyncMock(return_value=entry)
            ingest_cls.return_value.strike_entry = AsyncMock(
                return_value={**entry, "struck": True, "struck_proposal_ids": []}
            )
            capture_cls.return_value.retract_proposal = AsyncMock(side_effect=ValueError("Proposal already decided"))
            mock_list.return_value = _list_response([proposal])

            resp = client.delete(f"/api/gm/session-log/entries/{entry['id']}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["retracted_proposal_ids"] == []
        assert body["retract_errors"]
        ingest_cls.return_value.strike_entry.assert_awaited_once()

    def test_restore_puts_the_entry_and_its_proposals_back(self):
        entry = _entry()
        proposal_id = str(uuid4())
        with (
            patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls,
            patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls,
        ):
            ingest_cls.return_value.restore_entry = AsyncMock(
                return_value={**entry, "struck": False, "restored_proposal_ids": [proposal_id]}
            )
            capture_cls.return_value.restore_proposal = AsyncMock(
                return_value={"proposal_id": proposal_id, "status": "pending"}
            )
            resp = client.post(f"/api/gm/session-log/entries/{entry['id']}/restore")

        assert resp.status_code == 200
        body = resp.json()
        assert body["entry"]["struck"] is False
        assert body["restored_proposal_ids"] == [proposal_id]
        assert body["restore_errors"] == []
        capture_cls.return_value.restore_proposal.assert_awaited_once_with(proposal_id)

    def test_retract_proposal_route_defaults_to_strike_reason(self):
        proposal_id = str(uuid4())
        with patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls:
            capture_cls.return_value.retract_proposal = AsyncMock(
                return_value={"proposal_id": proposal_id, "status": "rejected"}
            )
            resp = client.post(f"/api/gm/session-log/proposals/{proposal_id}/retract", json={})

        assert resp.status_code == 200
        body = resp.json()
        assert body["proposal_id"] == proposal_id
        assert body["status"] == "rejected"
        assert body["reason"] == "struck at the table"
        capture_cls.return_value.retract_proposal.assert_awaited_once_with(proposal_id, reason="struck at the table")

    def test_retract_proposal_accepts_a_custom_reason(self):
        proposal_id = str(uuid4())
        with patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls:
            capture_cls.return_value.retract_proposal = AsyncMock(
                return_value={"proposal_id": proposal_id, "status": "rejected"}
            )
            resp = client.post(
                f"/api/gm/session-log/proposals/{proposal_id}/retract",
                json={"reason": "logged in error"},
            )
        assert resp.status_code == 200
        assert resp.json()["reason"] == "logged in error"

    def test_retract_malformed_proposal_id_returns_404(self):
        resp = client.post("/api/gm/session-log/proposals/not-a-uuid/retract", json={})
        assert resp.status_code == 404

    def test_retract_unknown_proposal_returns_404(self):
        proposal_id = str(uuid4())
        with patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls:
            capture_cls.return_value.retract_proposal = AsyncMock(
                side_effect=ValueError(f"Proposal {proposal_id} not found")
            )
            resp = client.post(f"/api/gm/session-log/proposals/{proposal_id}/retract", json={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Enforced-mode ownership tests (owner-only strike/edit/restore)
# ---------------------------------------------------------------------------


class _Coll:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def find_one(self, query: dict[str, Any], *_args: Any, **_kwargs: Any) -> dict[str, Any] | None:
        for doc in self._docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return dict(doc)
        return None


class _FakeMongo:
    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self._collections = {name: _Coll(docs) for name, docs in collections.items()}

    def get_collection(self, name: str) -> _Coll:
        return self._collections.get(name, _Coll([]))


def _signup(c: TestClient, email: str, username: str) -> dict:
    if not c.cookies.get("monitor_csrf"):
        c.get("/api/auth/config")
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
        headers={"X-CSRF-Token": c.cookies.get("monitor_csrf", "")},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


def _own_world(fake_db: Any, owner_id: str) -> str:
    from uuid import UUID as _UUID

    uid = str(uuid4())
    fake_db.worlds[uid] = {
        "id": uid,
        "owner_id": _UUID(owner_id),
        "multiverse_id": str(uuid4()),
        "label": "w",
        "active": True,
    }
    return uid


@pytest.fixture
def enforced(monkeypatch: pytest.MonkeyPatch):
    """Two-user-capable client in enforced auth mode with fake registries."""
    from fake_postgres import FakePostgres

    from monitor_ui.auth import get_postgres
    from monitor_ui.config import get_settings

    monkeypatch.delenv("MONITOR_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    import monitor_ui.auth as auth_mod

    monkeypatch.setattr(auth_mod, "_signup_limiter", None)
    monkeypatch.setattr(auth_mod, "_login_limiter", None)
    get_settings.cache_clear()

    fake_db = FakePostgres()

    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres

    sessions = _FakeMongo({"chat_sessions": [], "chat_messages": []})
    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: sessions)

    c = TestClient(app, raise_server_exceptions=False)
    yield SimpleNamespace(client=c, db=fake_db, mongo=sessions)
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _seed_session(
    mongo: _FakeMongo,
    owner_id: str,
    entry_id: str,
    session_id: str = "rec-owned",
) -> None:
    mongo._collections["chat_sessions"]._docs.append({"id": session_id, "owner_id": owner_id, "mode": "gm_assistant"})
    mongo._collections["chat_messages"]._docs.append(
        {
            "id": entry_id,
            "session_id": session_id,
            "role": "player",
            "content": "logged",
            "timestamp": "2026-11-10T20:00:00+00:00",
        }
    )


class TestEntryCorrectionOwnership:
    def test_unauthenticated_requests_get_401(self, enforced):
        entry_id = str(uuid4())
        c = enforced.client
        assert (
            c.patch(
                f"/api/gm/session-log/entries/{entry_id}",
                json={"universe_id": str(uuid4()), "text": "x"},
            ).status_code
            == 401
        )
        assert c.delete(f"/api/gm/session-log/entries/{entry_id}").status_code == 401
        assert c.post(f"/api/gm/session-log/entries/{entry_id}/restore").status_code == 401

    def test_foreign_session_entry_is_404_before_the_handler_runs(self, enforced):
        owner = _signup(enforced.client, "alice@example.com", "alice")
        entry_id = str(uuid4())
        _seed_session(enforced.mongo, owner["id"], entry_id)

        outsider = TestClient(app, raise_server_exceptions=False)
        _signup(outsider, "bob@example.com", "bob")

        with patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls:
            ingest_cls.return_value.get_entry = AsyncMock(return_value=_entry(entry_id))
            strike = outsider.delete(f"/api/gm/session-log/entries/{entry_id}", headers=_csrf(outsider))
            edit = outsider.patch(
                f"/api/gm/session-log/entries/{entry_id}",
                json={"universe_id": str(uuid4()), "text": "hijack"},
                headers=_csrf(outsider),
            )
            restore = outsider.post(f"/api/gm/session-log/entries/{entry_id}/restore", headers=_csrf(outsider))

        assert strike.status_code == 404 and strike.json() == {"detail": "Not found"}
        assert edit.status_code == 404 and edit.json() == {"detail": "Not found"}
        assert restore.status_code == 404 and restore.json() == {"detail": "Not found"}
        # The guard rejected all three before any agent work happened.
        ingest_cls.assert_not_called()

    def test_owner_can_strike_and_edit_their_entry(self, enforced):
        owner = _signup(enforced.client, "carol@example.com", "carol")
        entry_id = str(uuid4())
        _seed_session(enforced.mongo, owner["id"], entry_id)
        universe_id = _own_world(enforced.db, owner["id"])

        with (
            patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls,
            patch("monitor_ui.routers.gm_tools.CaptureInsightAgent") as capture_cls,
            patch(
                "monitor_ui.routers.gm_tools.mongodb_list_proposed_changes",
                return_value=_list_response([]),
            ),
        ):
            ingest_cls.return_value.get_entry = AsyncMock(return_value=_entry(entry_id))
            ingest_cls.return_value.strike_entry = AsyncMock(return_value=_entry(entry_id, struck=True))
            ingest_cls.return_value.update_entry = AsyncMock(
                return_value=_entry(entry_id, content="edited", edited_at="now")
            )
            capture_cls.return_value.retract_proposal = AsyncMock(return_value={})
            capture_cls.return_value.analyze_entry = AsyncMock(return_value=CaptureInsight())

            strike = enforced.client.delete(f"/api/gm/session-log/entries/{entry_id}", headers=_csrf(enforced.client))
            edit = enforced.client.patch(
                f"/api/gm/session-log/entries/{entry_id}",
                json={"universe_id": universe_id, "text": "edited"},
                headers=_csrf(enforced.client),
            )

        assert strike.status_code == 200
        assert strike.json()["entry"]["struck"] is True
        assert edit.status_code == 200
        assert edit.json()["entry"]["content"] == "edited"
        ingest_cls.return_value.strike_entry.assert_awaited_once()
        ingest_cls.return_value.update_entry.assert_awaited_once()

    def test_missing_entry_is_404_not_500(self, enforced):
        owner = _signup(enforced.client, "dave@example.com", "dave")
        # No message docs seeded — the resolver fails closed.
        with patch("monitor_ui.routers.gm_tools.SessionIngestAgent") as ingest_cls:
            resp = enforced.client.delete(f"/api/gm/session-log/entries/{uuid4()}", headers=_csrf(enforced.client))
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Not found"}
        ingest_cls.assert_not_called()
        assert owner["id"]
