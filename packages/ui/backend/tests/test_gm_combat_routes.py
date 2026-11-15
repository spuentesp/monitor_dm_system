"""Tests for the CF-9 session-combat routes on /api/gm/combat/*.

Two layers of assertion:

1. **Wiring** (local auth): each route delegates to CombatAgent with the
   expected arguments and maps state-machine failures to HTTP codes. The
   agent and the proposal store are mocked — no LLM, no databases.
2. **Authz regression** (two-user style from test_cf_authz_regressions.py):
   unauthenticated requests are refused, a foreign universe_id is a 404, and
   no state mutation happens for the foreign caller.

Run:
    uv run pytest packages/ui/backend/tests/test_gm_combat_routes.py -q -p no:cacheprovider
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_data.schemas.base import CombatSide, CombatStatus
from monitor_data.schemas.combat import (
    CombatSessionState,
    CombatantState,
)
from monitor_agents.combat import ConditionExplanation
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app

client = TestClient(app)

# Wiring tests run in local-auth mode (owner checks pass, no signup needed).
# The authz class at the bottom deliberately does NOT use it.
_local_auth = pytest.mark.usefixtures("local_auth_mode")


def _state(universe_id: UUID | None = None, **over: Any) -> CombatSessionState:
    base: dict[str, Any] = dict(
        universe_id=universe_id or uuid4(),
        session_id="sess-1",
        status=CombatStatus.ACTIVE,
        round=1,
        turn_order=[],
        combatants=[
            CombatantState(
                id=uuid4(),
                name="Mira",
                side=CombatSide.PC,
                hp=24,
                max_hp=24,
            ),
            CombatantState(
                id=uuid4(),
                name="Goblin",
                side=CombatSide.ENEMY,
                hp=7,
                max_hp=7,
            ),
        ],
        started_at=None,  # filled below
    )
    from datetime import UTC, datetime

    base["started_at"] = datetime.now(UTC)
    base.update(over)
    return CombatSessionState(**base)


def _start_body(universe_id: str, **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "universe_id": universe_id,
        "session_id": "sess-1",
        "combatants": [
            {"name": "Mira", "side": "pc", "hp": 24, "max_hp": 24},
            {"name": "Goblin", "side": "enemy", "hp": 7, "max_hp": 7},
        ],
    }
    body.update(over)
    return body


def _patch_agent(**method_returns: Any):
    """Patch CombatAgent in the router namespace; returns the class mock."""
    mock_cls = patch("monitor_ui.routers.gm_tools.CombatAgent")
    return mock_cls


# ---------------------------------------------------------------------------
# Wiring (local auth)
# ---------------------------------------------------------------------------


class TestCombatStartRoute:
    pytestmark = _local_auth

    def test_start_delegates_with_expected_args(self):
        universe_id = uuid4()
        state = _state(universe_id)
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.start_encounter = AsyncMock(return_value=state)
            resp = client.post("/api/gm/combat/start", json=_start_body(str(universe_id)))

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["session_id"] == "sess-1"
        assert body["status"] == "active"
        assert [c["name"] for c in body["combatants"]] == ["Mira", "Goblin"]
        mock_cls.return_value.start_encounter.assert_awaited_once()
        sent = mock_cls.return_value.start_encounter.call_args.args[0]
        assert sent.universe_id == universe_id
        assert sent.session_id == "sess-1"
        assert len(sent.combatants) == 2

    def test_start_maps_value_error_to_http(self):
        universe_id = uuid4()
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.start_encounter = AsyncMock(
                side_effect=ValueError("Mira: hp (30) cannot exceed max_hp (20)")
            )
            resp = client.post("/api/gm/combat/start", json=_start_body(str(universe_id)))

        assert resp.status_code == 400
        assert "cannot exceed max_hp" in resp.json()["detail"]


class TestCombatGetRoute:
    pytestmark = _local_auth

    def test_get_returns_state(self):
        universe_id = uuid4()
        state = _state(universe_id)
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.get_state = AsyncMock(return_value=state)
            resp = client.get(f"/api/gm/combat/sess-1?universe_id={universe_id}")

        assert resp.status_code == 200
        assert resp.json()["round"] == 1
        mock_cls.return_value.get_state.assert_awaited_once_with(universe_id, "sess-1")

    def test_get_404_when_absent(self):
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.get_state = AsyncMock(return_value=None)
            resp = client.get(f"/api/gm/combat/missing?universe_id={uuid4()}")

        assert resp.status_code == 404


class TestCombatInitiativeRoute:
    pytestmark = _local_auth

    def test_initiative_delegates_and_returns_state(self):
        universe_id = uuid4()
        state = _state(universe_id)
        cid = state.combatants[0].id
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.set_initiative = AsyncMock(return_value=state)
            mock_cls.return_value.narrate_initiative = AsyncMock(return_value="Mira first!")
            resp = client.post(
                "/api/gm/combat/sess-1/initiative",
                json={
                    "universe_id": str(universe_id),
                    "entries": [{"combatant_id": str(cid), "initiative": 18, "tiebreak": 2}],
                    "narrate": True,
                },
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["narration"] == "Mira first!"
        assert body["state"]["session_id"] == "sess-1"
        sent = mock_cls.return_value.set_initiative.call_args.args[0]
        assert sent.session_id == "sess-1"
        assert sent.entries[0].initiative == 18
        mock_cls.return_value.narrate_initiative.assert_awaited_once()

    def test_initiative_narration_failure_degrades_to_none(self):
        universe_id = uuid4()
        state = _state(universe_id)
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.set_initiative = AsyncMock(return_value=state)
            mock_cls.return_value.narrate_initiative = AsyncMock(side_effect=RuntimeError("LLM down"))
            resp = client.post(
                "/api/gm/combat/sess-1/initiative",
                json={
                    "universe_id": str(universe_id),
                    "entries": [{"combatant_id": str(state.combatants[0].id), "initiative": 10}],
                    "narrate": True,
                },
            )

        # The order is stored; only the optional enrichment failed.
        assert resp.status_code == 200
        assert resp.json()["narration"] is None

    def test_initiative_maps_missing_encounter_to_404(self):
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.set_initiative = AsyncMock(
                side_effect=ValueError("No combat encounter for session sess-1 in universe x")
            )
            resp = client.post(
                "/api/gm/combat/sess-1/initiative",
                json={
                    "universe_id": str(uuid4()),
                    "entries": [{"combatant_id": str(uuid4()), "initiative": 10}],
                },
            )
        assert resp.status_code == 404


class TestCombatPatchCombatantRoute:
    pytestmark = _local_auth

    def test_patch_delegates_path_ids_and_body_fields(self):
        universe_id = uuid4()
        state = _state(universe_id)
        combatant_id = state.combatants[1].id
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.update_combatant = AsyncMock(return_value=state)
            resp = client.patch(
                f"/api/gm/combat/sess-1/combatant/{combatant_id}",
                json={
                    "universe_id": str(universe_id),
                    "hp_delta": -4,
                    "conditions_add": ["poisoned"],
                },
            )

        assert resp.status_code == 200, resp.text
        sent = mock_cls.return_value.update_combatant.call_args.args[0]
        assert sent.session_id == "sess-1"
        assert sent.combatant_id == combatant_id
        assert sent.hp_delta == -4
        assert sent.conditions_add == ["poisoned"]

    def test_patch_maps_unknown_combatant_to_404(self):
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.update_combatant = AsyncMock(
                side_effect=ValueError("Combatant x not found in encounter")
            )
            resp = client.patch(
                f"/api/gm/combat/sess-1/combatant/{uuid4()}",
                json={"universe_id": str(uuid4()), "hp_delta": -1},
            )
        assert resp.status_code == 404


class TestCombatNextRoundRoute:
    pytestmark = _local_auth

    def test_next_round_delegates(self):
        universe_id = uuid4()
        state = _state(universe_id, round=3)
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.next_round = AsyncMock(return_value=state)
            resp = client.post(
                "/api/gm/combat/sess-1/next-round",
                json={"universe_id": str(universe_id)},
            )

        assert resp.status_code == 200
        assert resp.json()["round"] == 3
        sent = mock_cls.return_value.next_round.call_args.args[0]
        assert sent.session_id == "sess-1"

    def test_next_round_after_end_maps_to_409(self):
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.next_round = AsyncMock(side_effect=ValueError("Encounter has already ended"))
            resp = client.post(
                "/api/gm/combat/sess-1/next-round",
                json={"universe_id": str(uuid4())},
            )
        assert resp.status_code == 409


class TestCombatEndRoute:
    pytestmark = _local_auth

    def test_end_stages_casualty_and_world_effect_proposals(self):
        universe_id = uuid4()
        state = _state(universe_id)
        story_id = uuid4()
        # Mark the Goblin dead so end stages a casualty proposal.
        state.combatants[1].dead = True
        state.combatants[1].hp = 0
        from datetime import UTC, datetime

        resolved = _state(
            universe_id,
            status=CombatStatus.RESOLVED,
            ended_at=datetime.now(UTC),
        )
        resolved.combatants[1].dead = True
        resolved.combatants[1].hp = 0
        created_ids = ["p-1", "p-2"]

        with (
            patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls,
            patch(
                "monitor_ui.routers.gm_tools.mongodb_list_proposed_changes",
                return_value=SimpleNamespace(proposed_changes=[]),
            ),
            patch(
                "monitor_ui.routers.gm_tools.mongodb_create_proposed_change",
                side_effect=[SimpleNamespace(proposal_id=pid) for pid in created_ids],
            ) as mock_create,
        ):
            mock_cls.return_value.get_state = AsyncMock(return_value=state)
            mock_cls.return_value.end_encounter = AsyncMock(return_value=resolved)
            mock_cls.return_value.summarize_encounter = AsyncMock(return_value="Two rounds; the Goblin fell.")
            resp = client.post(
                "/api/gm/combat/sess-1/end",
                json={
                    "universe_id": str(universe_id),
                    "story_id": str(story_id),
                    "world_effects": ["The goblin warband swears vengeance"],
                },
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["proposal_ids"] == created_ids
        assert body["proposal_errors"] == []
        assert body["summary"] == "Two rounds; the Goblin fell."
        assert body["state"]["status"] == "resolved"

        # One FACT proposal per casualty + one per world effect.
        assert mock_create.call_count == 2
        first = mock_create.call_args_list[0].args[0]
        assert first.story_id == story_id
        assert first.content["statement"] == "Goblin died in combat"
        assert first.content["participants"] == ["Goblin"]
        assert first.source == "combat_end:sess-1"
        assert first.authority.value == "gm"
        second = mock_create.call_args_list[1].args[0]
        assert second.content["statement"] == "The goblin warband swears vengeance"
        assert second.proposal_type == "combat_world_effect"

    def test_end_without_deaths_or_effects_stages_nothing(self):
        universe_id = uuid4()
        state = _state(universe_id)
        with (
            patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls,
            patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change") as mock_create,
            patch(
                "monitor_ui.routers.gm_tools.mongodb_list_proposed_changes",
                return_value=SimpleNamespace(proposed_changes=[]),
            ),
        ):
            mock_cls.return_value.get_state = AsyncMock(return_value=state)
            mock_cls.return_value.end_encounter = AsyncMock(return_value=state)
            mock_cls.return_value.summarize_encounter = AsyncMock(return_value="Quiet win.")
            resp = client.post(
                "/api/gm/combat/sess-1/end",
                json={"universe_id": str(universe_id)},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["proposal_ids"] == []
        assert body["summary"] == "Quiet win."
        mock_create.assert_not_called()

    def test_end_with_casualties_but_no_story_or_scene_is_422(self):
        universe_id = uuid4()
        state = _state(universe_id)
        state.combatants[1].dead = True
        with (
            patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls,
            patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change") as mock_create,
        ):
            mock_cls.return_value.get_state = AsyncMock(return_value=state)
            mock_cls.return_value.end_encounter = AsyncMock(return_value=state)
            resp = client.post(
                "/api/gm/combat/sess-1/end",
                json={"universe_id": str(universe_id)},
            )

        assert resp.status_code == 422
        mock_create.assert_not_called()
        # The state must not be ended when staging scope is missing.
        mock_cls.return_value.end_encounter.assert_not_awaited()

    def test_end_summary_failure_still_returns_200(self):
        universe_id = uuid4()
        state = _state(universe_id)
        with (
            patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls,
            patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change"),
            patch(
                "monitor_ui.routers.gm_tools.mongodb_list_proposed_changes",
                return_value=SimpleNamespace(proposed_changes=[]),
            ),
        ):
            mock_cls.return_value.get_state = AsyncMock(return_value=state)
            mock_cls.return_value.end_encounter = AsyncMock(return_value=state)
            mock_cls.return_value.summarize_encounter = AsyncMock(side_effect=RuntimeError("LLM down"))
            resp = client.post(
                "/api/gm/combat/sess-1/end",
                json={"universe_id": str(universe_id)},
            )

        assert resp.status_code == 200
        assert resp.json()["summary"] is None

    def test_end_dedupes_by_source_tag(self):
        universe_id = uuid4()
        state = _state(universe_id, story_id=uuid4())
        state.combatants[1].dead = True
        already = SimpleNamespace(
            proposed_changes=[
                SimpleNamespace(content={"statement": "Goblin died in combat"}),
            ]
        )
        with (
            patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls,
            patch(
                "monitor_ui.routers.gm_tools.mongodb_list_proposed_changes",
                return_value=already,
            ),
            patch("monitor_ui.routers.gm_tools.mongodb_create_proposed_change") as mock_create,
        ):
            mock_cls.return_value.get_state = AsyncMock(return_value=state)
            mock_cls.return_value.end_encounter = AsyncMock(return_value=state)
            mock_cls.return_value.summarize_encounter = AsyncMock(return_value="s")
            resp = client.post(
                "/api/gm/combat/sess-1/end",
                json={"universe_id": str(universe_id)},
            )

        assert resp.status_code == 200
        assert resp.json()["proposal_ids"] == []
        mock_create.assert_not_called()

    def test_end_404_when_no_encounter(self):
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.get_state = AsyncMock(return_value=None)
            resp = client.post(
                "/api/gm/combat/sess-1/end",
                json={"universe_id": str(uuid4())},
            )
        assert resp.status_code == 404


class TestConditionExplainRoute:
    pytestmark = _local_auth

    def test_explain_uses_agent_and_resolves_bound_system(self):
        universe_id = uuid4()
        explanation = ConditionExplanation(condition="poisoned", source="system", description="-2 to attacks")
        with (
            patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls,
            patch(
                "monitor_ui.routers.gm_tools.resolve_universe_system_binding",
                return_value={"system_id": str(uuid4()), "system_name": "Test System"},
            ),
        ):
            mock_cls.return_value.explain_condition = AsyncMock(return_value=explanation)
            resp = client.post(
                "/api/gm/combat/condition-explain",
                json={"universe_id": str(universe_id), "condition": "poisoned"},
            )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source"] == "system"
        assert body["description"] == "-2 to attacks"
        kwargs = mock_cls.return_value.explain_condition.call_args.kwargs
        assert kwargs["system_name"] == "Test System"
        assert isinstance(kwargs["system_id"], UUID)

    def test_explain_passes_explicit_system_id_without_binding_lookup(self):
        universe_id = uuid4()
        system_id = uuid4()
        explanation = ConditionExplanation(condition="prone", source="free_text", description="generic")
        with (
            patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls,
            patch("monitor_ui.routers.gm_tools.resolve_universe_system_binding") as mock_bind,
        ):
            mock_cls.return_value.explain_condition = AsyncMock(return_value=explanation)
            resp = client.post(
                "/api/gm/combat/condition-explain",
                json={
                    "universe_id": str(universe_id),
                    "condition": "prone",
                    "system_id": str(system_id),
                },
            )

        assert resp.status_code == 200
        mock_bind.assert_not_called()
        kwargs = mock_cls.return_value.explain_condition.call_args.kwargs
        assert kwargs["system_id"] == system_id


# ---------------------------------------------------------------------------
# Authz regression (two-user style, cf. test_cf_authz_regressions.py)
# ---------------------------------------------------------------------------


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def sort(self, *a: Any, **k: Any) -> "_Cursor":
        return self

    def skip(self, n: int) -> "_Cursor":
        self.docs = self.docs[n:]
        return self

    def limit(self, n: int) -> "_Cursor":
        self.docs = self.docs[:n]
        return self

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.docs)


class _Coll:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def _match(self, d: dict[str, Any], q: dict[str, Any]) -> bool:
        return all(d.get(k) == v for k, v in q.items() if not isinstance(v, dict))

    def insert_one(self, doc: dict[str, Any]) -> None:
        self.docs.append(doc)

    def find_one(self, q: dict[str, Any], *a: Any, **k: Any) -> dict[str, Any] | None:
        return next((d for d in self.docs if self._match(d, q)), None)

    def find(self, q: dict[str, Any], *a: Any, **k: Any) -> _Cursor:
        return _Cursor([d for d in self.docs if self._match(d, q)])

    def count_documents(self, q: dict[str, Any]) -> int:
        return sum(1 for d in self.docs if self._match(d, q))


class TestCombatAuthz:
    @pytest.fixture
    def fake_db(self):
        from fake_postgres import FakePostgres

        return FakePostgres()

    @pytest.fixture
    def auth_client(self, fake_db, monkeypatch: pytest.MonkeyPatch):
        # Session cookies must round-trip over the test client's http scheme.
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
        get_settings.cache_clear()

        async def _db() -> Any:
            return fake_db

        app.dependency_overrides[get_postgres] = _db
        yield TestClient(app)
        app.dependency_overrides.pop(get_postgres, None)
        get_settings.cache_clear()

    def _signup(self, c: TestClient, email: str, username: str) -> dict[str, Any]:
        r = c.post(
            "/api/auth/signup",
            json={"email": email, "username": username, "password": "correct horse battery"},
        )
        assert r.status_code == 201, r.text
        return r.json()  # type: ignore[no-any-return]

    def _csrf(self, c: TestClient) -> dict[str, str]:
        return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}

    def test_unauthenticated_denied(self, auth_client: TestClient) -> None:
        assert auth_client.get(f"/api/gm/combat/x?universe_id={uuid4()}").status_code in (401, 403)
        assert auth_client.post("/api/gm/combat/start", json=_start_body(str(uuid4()))).status_code in (401, 403)

    def test_foreign_universe_is_404_and_never_reaches_agent(self, auth_client: TestClient, fake_db: Any) -> None:
        user_a = self._signup(auth_client, "a@example.com", "alice")
        world = str(uuid4())
        fake_db.worlds[world] = {
            "id": world,
            "owner_id": UUID(user_a["id"]),
            "multiverse_id": str(uuid4()),
            "label": "w",
            "active": True,
        }

        client_b = TestClient(app)
        self._signup(client_b, "b@example.com", "bob")

        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            resp = client_b.post(
                "/api/gm/combat/start",
                json=_start_body(world),
                headers=self._csrf(client_b),
            )

        assert resp.status_code == 404
        mock_cls.assert_not_called()  # owner check fails before any agent work

        # Bob also cannot read or mutate Alice's encounter by session id.
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            r_get = client_b.get(
                f"/api/gm/combat/sess-1?universe_id={world}",
                headers=self._csrf(client_b),
            )
            r_patch = client_b.patch(
                f"/api/gm/combat/sess-1/combatant/{uuid4()}",
                json={"universe_id": world, "hp_delta": -1},
                headers=self._csrf(client_b),
            )
            r_end = client_b.post(
                "/api/gm/combat/sess-1/end",
                json={"universe_id": world},
                headers=self._csrf(client_b),
            )
        assert r_get.status_code == 404
        assert r_patch.status_code == 404
        assert r_end.status_code == 404
        mock_cls.assert_not_called()

    def test_owner_can_start(self, auth_client: TestClient, fake_db: Any) -> None:
        user_a = self._signup(auth_client, "a@example.com", "alice")
        world = str(uuid4())
        fake_db.worlds[world] = {
            "id": world,
            "owner_id": UUID(user_a["id"]),
            "multiverse_id": str(uuid4()),
            "label": "w",
            "active": True,
        }
        state = _state(UUID(world))
        with patch("monitor_ui.routers.gm_tools.CombatAgent") as mock_cls:
            mock_cls.return_value.start_encounter = AsyncMock(return_value=state)
            resp = auth_client.post(
                "/api/gm/combat/start",
                json=_start_body(world),
                headers=self._csrf(auth_client),
            )
        assert resp.status_code == 200, resp.text
