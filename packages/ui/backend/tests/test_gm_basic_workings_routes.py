"""Basic workings — the GM Assistant routes, end to end over fake stores.

The unit-level tests pin the agents and the tools. These pin the *routes*:
the HTTP surface a GM actually clicks, running the real agents and the real
data-layer tools over a mongomock Mongo and a fake Postgres registry.

Covered here:

- the world clock briefing (``/gm/clock/*``) — advance, deadline, briefing;
- the CF-8 canon queue — list, accept, reject;
- the Session Recorder corrections (G03) — strike, restore, retract;
- the share link — publish, then read it as a player would;
- the combat tracker — start, then read the encounter back.

Use Cases: CF-8, CF-9, CF-11, CF-14, CF-1 (G03)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_data.schemas.base import ProposalType
from monitor_data.schemas.proposed_changes import ProposedChangeCreate
from monitor_ui.main import app
from tests.behavior._hermetic_stack import HermeticStack

client = TestClient(app)

_local_auth = pytest.mark.usefixtures("local_auth_mode")


@pytest.fixture(autouse=True)
def stub_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the model boundary.

    The routes call the model for the off-screen tick and the per-entry
    insight. Both are advisory, so a scripted answer keeps the routes
    deterministic without a provider.
    """
    from monitor_agents.gm_table import GmTableAgent, OffScreenSummary

    async def _fake_llm(self: Any, response_model: type, messages: list, **kwargs: Any) -> Any:
        return OffScreenSummary(
            summary="While time passed, the harbour council met without Mira.",
            npc_activities=["The harbour council met"],
        )

    monkeypatch.setattr(GmTableAgent, "call_llm_structured", _fake_llm)


@pytest.fixture
def hermetic(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The hermetic stack, installed for the duration of the test."""
    import monitor_agents.base as agents_base
    from monitor_data.db import postgres as postgres_module

    from fake_postgres import FakePostgres

    stack = HermeticStack()
    stack.install(monkeypatch)

    # The agents resolve their model through the Postgres provider registry;
    # in a hermetic run there is none, so the calls fail fast and the routes
    # degrade the way they do in production without a provider.
    fake_pg = FakePostgres()
    monkeypatch.setattr(postgres_module, "get_postgres_client", lambda: fake_pg)
    monkeypatch.setattr(agents_base, "get_postgres_client", lambda: fake_pg)
    try:
        yield stack
    finally:
        stack.uninstall()


def _scene(universe_id: UUID, story_id: UUID) -> UUID:
    scene_id = uuid4()
    return scene_id


# ---------------------------------------------------------------------------
# World clock (CF-11)
# ---------------------------------------------------------------------------


class TestWorldClockRoutes:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_advance_then_read_the_briefing(self, hermetic: HermeticStack) -> None:
        universe_id = uuid4()
        story_id = uuid4()
        start = datetime(1012, 3, 1, 9, 0, tzinfo=UTC)

        first = client.post(
            "/api/gm/clock/advance",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "target_time": start.isoformat(),
            },
        )
        assert first.status_code == 200, first.text
        body = first.json()
        assert body["initialized"] is True
        assert body["changed"] is True

        read = client.get(
            f"/api/gm/clock/{story_id}",
            params={"universe_id": str(universe_id)},
        )
        assert read.status_code == 200, read.text
        assert read.json()["found"] is True
        assert read.json()["clock"]["current_at"].startswith("1012-03-01T09:00")

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_deadline_flips_when_time_passes_it(self, hermetic: HermeticStack) -> None:
        universe_id = uuid4()
        story_id = uuid4()
        start = datetime(1012, 3, 1, 9, 0, tzinfo=UTC)

        client.post(
            "/api/gm/clock/advance",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "target_time": start.isoformat(),
            },
        )
        deadline = client.post(
            "/api/gm/clock/deadline",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "title": "The tide turns",
                "due_at": (start + timedelta(days=5)).isoformat(),
            },
        )
        assert deadline.status_code == 200, deadline.text
        assert deadline.json()["deadlines"][0]["status"] == "upcoming"

        advanced = client.post(
            "/api/gm/clock/advance",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "delta": "+7 days",
            },
        )
        assert advanced.status_code == 200, advanced.text
        body = advanced.json()
        assert [d["title"] for d in body["crossed"]] == ["The tide turns"]
        assert [d["title"] for d in body["due"]] == ["The tide turns"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_backwards_move_is_refused(self, hermetic: HermeticStack) -> None:
        universe_id = uuid4()
        story_id = uuid4()
        start = datetime(1012, 3, 1, 9, 0, tzinfo=UTC)

        client.post(
            "/api/gm/clock/advance",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "target_time": start.isoformat(),
            },
        )
        backwards = client.post(
            "/api/gm/clock/advance",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "target_time": (start - timedelta(days=1)).isoformat(),
            },
        )

        assert backwards.status_code == 422
        assert "cannot move backwards" in backwards.json()["detail"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_both_delta_and_target_are_refused(self, hermetic: HermeticStack) -> None:
        resp = client.post(
            "/api/gm/clock/advance",
            json={
                "universe_id": str(uuid4()),
                "story_id": str(uuid4()),
                "delta": "+1 day",
                "target_time": datetime.now(UTC).isoformat(),
            },
        )
        assert resp.status_code == 422

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_story_with_no_clock_reads_as_not_found(self, hermetic: HermeticStack) -> None:
        resp = client.get(
            f"/api/gm/clock/{uuid4()}",
            params={"universe_id": str(uuid4())},
        )
        assert resp.status_code == 200
        assert resp.json() == {"found": False, "clock": None}


# ---------------------------------------------------------------------------
# Canon queue (CF-8)
# ---------------------------------------------------------------------------


def _pending_proposal(
    scene_id: UUID,
    story_id: UUID | None = None,
    statement: str = "Mira opened the sealed door.",
) -> str:
    from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change

    created = mongodb_create_proposed_change(
        ProposedChangeCreate(
            scene_id=scene_id,
            story_id=story_id,
            change_type=ProposalType.FACT,
            content={"statement": statement},
            authority="gm",
            proposer="Test",
            source="capture_entry:entry-1",
        )
    )
    return str(created.proposal_id)


class TestCanonQueueRoutes:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_accept_moves_a_proposal_out_of_the_queue(self, hermetic: HermeticStack) -> None:
        universe_id = uuid4()
        story_id = uuid4()
        scene_id = uuid4()
        hermetic.seed(
            "scenes",
            [
                {
                    "scene_id": str(scene_id),
                    "story_id": str(story_id),
                    "universe_id": str(universe_id),
                    "title": "The sealed door",
                    "purpose": "Advance the harbour investigation.",
                    "status": "active",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
        )
        proposal_id = _pending_proposal(scene_id, story_id)

        queue = client.get(f"/api/stories/{story_id}/canon-queue")
        assert queue.status_code == 200, queue.text
        queued = queue.json()
        assert queued["total_pending"] == 1
        assert [p["proposal_id"] for p in queued["scenes"][0]["pending"]] == [proposal_id]

        accepted = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Confirmed at the table."},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["status"] == "accepted"

        queue_after = client.get(f"/api/stories/{story_id}/canon-queue")
        assert queue_after.json()["total_pending"] == 0

    @pytest.mark.usefixtures("local_auth_mode")
    def test_reject_records_the_reason(self, hermetic: HermeticStack) -> None:
        universe_id = uuid4()
        story_id = uuid4()
        scene_id = uuid4()
        hermetic.seed(
            "scenes",
            [
                {
                    "scene_id": str(scene_id),
                    "story_id": str(story_id),
                    "universe_id": str(universe_id),
                    "title": "The sealed door",
                    "purpose": "Advance the harbour investigation.",
                    "status": "active",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
        )
        proposal_id = _pending_proposal(scene_id)

        rejected = client.post(
            f"/api/canon-review/{proposal_id}/reject",
            params={"reason": "Mira did not open it."},
        )

        assert rejected.status_code == 200, rejected.text
        body = rejected.json()
        assert body["status"] == "rejected"
        assert body["decision_metadata"]["reason"] == "Mira did not open it."

    @pytest.mark.usefixtures("local_auth_mode")
    def test_accepting_an_unknown_proposal_is_a_conflict(self, hermetic: HermeticStack) -> None:
        resp = client.post(
            f"/api/canon-review/{uuid4()}/accept",
            params={"reason": "why"},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Session Recorder corrections (G03)
# ---------------------------------------------------------------------------


class TestRecorderCorrectionRoutes:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_strike_then_restore_an_entry(self, hermetic: HermeticStack) -> None:
        entry_id = str(uuid4())
        hermetic.seed(
            "chat_messages",
            [
                {
                    "id": entry_id,
                    "session_id": "sess-1",
                    "role": "gm",
                    "content": "Mira opened the sealed door.",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
        )

        struck = client.delete(f"/api/gm/session-log/entries/{entry_id}")
        assert struck.status_code == 200, struck.text
        assert struck.json()["entry"]["struck"] is True
        assert struck.json()["entry"]["struck_reason"] == "struck at the table"

        restored = client.post(f"/api/gm/session-log/entries/{entry_id}/restore")
        assert restored.status_code == 200, restored.text
        assert restored.json()["entry"]["struck"] is False

    @pytest.mark.usefixtures("local_auth_mode")
    def test_editing_an_entry_keeps_the_correction_even_without_a_model(self, hermetic: HermeticStack) -> None:
        entry_id = str(uuid4())
        hermetic.seed(
            "chat_messages",
            [
                {
                    "id": entry_id,
                    "session_id": "sess-1",
                    "role": "gm",
                    "content": "Mira opened the sealed door.",
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            ],
        )

        edited = client.patch(
            f"/api/gm/session-log/entries/{entry_id}",
            json={"universe_id": str(uuid4()), "text": "Mira opened the sealed gate."},
        )

        assert edited.status_code == 200, edited.text
        body = edited.json()
        assert body["entry"]["content"] == "Mira opened the sealed gate."
        # The edit landed even though insight extraction had nothing to work
        # with — no candidate facts, so nothing is staged.
        assert body["insight"]["candidate_facts"] == []
        assert body["proposal_ids"] == []

    @pytest.mark.usefixtures("local_auth_mode")
    def test_striking_an_unknown_entry_is_a_404(self, hermetic: HermeticStack) -> None:
        resp = client.delete(f"/api/gm/session-log/entries/{uuid4()}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Share link (CF-14)
# ---------------------------------------------------------------------------


class TestShareRoutes:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_publish_then_read_as_a_player(self, hermetic: HermeticStack) -> None:
        hermetic.override("neo4j_list_parties", [])
        universe_id = uuid4()
        story_id = uuid4()

        published = client.post(
            "/api/gm/share/publish",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "artifact_type": "recap",
                "title": "Session 4 recap",
                "content": "They opened the sealed door.",
            },
        )
        assert published.status_code == 200, published.text
        token = published.json()["token"]

        # The public page needs no login: the token is the credential.
        player_view = client.get(f"/api/share/{token}")
        assert player_view.status_code == 200, player_view.text
        assert player_view.json()["story_id"] == str(story_id)

    @pytest.mark.usefixtures("local_auth_mode")
    def test_revoking_the_link_stops_the_page(self, hermetic: HermeticStack) -> None:
        hermetic.override("neo4j_list_parties", [])
        universe_id = uuid4()
        story_id = uuid4()

        published = client.post(
            "/api/gm/share/publish",
            json={
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "artifact_type": "recap",
                "title": "Session 4 recap",
                "content": "They opened the sealed door.",
            },
        )
        token = published.json()["token"]

        revoked = client.post(
            "/api/gm/share/revoke",
            json={"universe_id": str(universe_id), "story_id": str(story_id)},
        )
        assert revoked.status_code == 200, revoked.text

        after = client.get(f"/api/share/{token}")
        assert after.status_code == 404
        assert after.json() == {"detail": "Not found"}


# ---------------------------------------------------------------------------
# Combat tracker (CF-9)
# ---------------------------------------------------------------------------


class TestCombatRoutes:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_start_then_read_the_encounter(self, hermetic: HermeticStack) -> None:
        universe_id = uuid4()
        started = client.post(
            "/api/gm/combat/start",
            json={
                "universe_id": str(universe_id),
                "session_id": "sess-1",
                "combatants": [
                    {"name": "Mira", "side": "pc", "hp": 24, "max_hp": 24},
                    {"name": "Goblin", "side": "enemy", "hp": 7, "max_hp": 7},
                ],
            },
        )
        assert started.status_code == 200, started.text
        assert started.json()["status"] == "initiative"

        read = client.get(
            "/api/gm/combat/sess-1",
            params={"universe_id": str(universe_id)},
        )
        assert read.status_code == 200, read.text
        assert [c["name"] for c in read.json()["combatants"]] == ["Mira", "Goblin"]
