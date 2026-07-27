"""F1-3 — coverage for POST /api/forge/quick-world and /api/forge/demo-world.

Both endpoints were previously untested. Mocks sit at the tool/agent boundary:
``QuickWorldBuilder`` (agents layer), ``mongodb_list_game_systems`` /
``neo4j_*`` (data layer), and ``create_session`` (chat router) for the
optional session bootstrap.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)


def _build_result(world_name: str = "Fogharbor") -> SimpleNamespace:
    """Stand-in for monitor_agents.quick_world.agent.QuickWorldResult."""
    mv_id = uuid4()
    universe_id = uuid4()
    payload = {
        "multiverse_id": str(mv_id),
        "universe_id": str(universe_id),
        "world_name": world_name,
        "world_description": "A rain-soaked harbor city.",
        "axiom": "The drowned barter for memories.",
        "opening_scene": "You step off the last ferry.",
        "pc_concept": "A debt-ridden ferryman",
        "entities": [],
        "lore_facts": [],
        "committed": 6,
        "errors": [],
    }
    return SimpleNamespace(
        multiverse_id=mv_id,
        universe_id=universe_id,
        world_name=world_name,
        summary=lambda: payload,
    )


def _no_systems() -> SimpleNamespace:
    return SimpleNamespace(systems=[])


# ─── quick-world ──────────────────────────────────────────────


def test_quick_world_success_without_session():
    result = _build_result()
    with (
        patch("monitor_agents.quick_world.agent.QuickWorldBuilder") as mock_builder_cls,
        patch(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            return_value=_no_systems(),
        ),
    ):
        mock_builder_cls.return_value.build = AsyncMock(return_value=result)
        response = client.post(
            "/api/forge/quick-world",
            json={"seed": "A rain-soaked harbor city", "start_playing": False},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["world_name"] == "Fogharbor"
    assert body["universe_id"] == str(result.universe_id)
    assert body["multiverse_id"] == str(result.multiverse_id)
    assert body["committed"] == 6
    assert body["session_id"] is None


def test_quick_world_with_session_bootstrap():
    result = _build_result()
    with (
        patch("monitor_agents.quick_world.agent.QuickWorldBuilder") as mock_builder_cls,
        patch(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            return_value=_no_systems(),
        ),
        patch(
            "monitor_ui.routers.forge._ensure_demo_pc",
            return_value="pc-1",
        ),
        patch(
            "monitor_ui.routers.chat.create_session",
            new=AsyncMock(return_value=SimpleNamespace(id="sess-1")),
        ) as mock_create_session,
    ):
        mock_builder_cls.return_value.build = AsyncMock(return_value=result)
        response = client.post(
            "/api/forge/quick-world",
            json={"seed": "A rain-soaked harbor city", "start_playing": True},
        )

    assert response.status_code == 200
    assert response.json()["session_id"] == "sess-1"
    mock_create_session.assert_awaited_once()


def test_quick_world_session_failure_still_returns_world():
    """A broken session bootstrap degrades to an error note, not a 5xx."""
    result = _build_result()
    with (
        patch("monitor_agents.quick_world.agent.QuickWorldBuilder") as mock_builder_cls,
        patch(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            return_value=_no_systems(),
        ),
        patch(
            "monitor_ui.routers.chat.create_session",
            new=AsyncMock(side_effect=RuntimeError("chat down")),
        ),
    ):
        mock_builder_cls.return_value.build = AsyncMock(return_value=result)
        response = client.post(
            "/api/forge/quick-world",
            json={"seed": "A rain-soaked harbor city", "start_playing": True},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] is None
    assert any("Session bootstrap failed" in e for e in body["errors"])


def test_quick_world_build_failure_is_502():
    with patch("monitor_agents.quick_world.agent.QuickWorldBuilder") as mock_builder_cls:
        mock_builder_cls.return_value.build = AsyncMock(side_effect=RuntimeError("LLM exploded"))
        response = client.post(
            "/api/forge/quick-world",
            json={"seed": "A rain-soaked harbor city"},
        )

    assert response.status_code == 502
    assert "LLM exploded" in response.json()["detail"]


def test_quick_world_seed_too_short_is_422():
    response = client.post("/api/forge/quick-world", json={"seed": "ab"})
    assert response.status_code == 422


# ─── demo-world ───────────────────────────────────────────────


def test_demo_world_reuses_existing_millhaven():
    """Idempotent path: an existing Millhaven universe is reused, not rebuilt."""
    universe_id = uuid4()
    mv_id = uuid4()
    existing = SimpleNamespace(name="Millhaven", id=universe_id, multiverse_id=mv_id)
    with (
        patch(
            "monitor_data.tools.neo4j_tools.neo4j_list_universes",
            return_value=[existing],
        ),
        patch(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            return_value=_no_systems(),
        ),
        patch("monitor_agents.quick_world.agent.QuickWorldBuilder") as mock_builder_cls,
    ):
        response = client.post("/api/forge/demo-world", params={"start_playing": "false"})

    assert response.status_code == 200
    body = response.json()
    assert body["reused"] is True
    assert body["world_name"] == "Millhaven"
    assert body["universe_id"] == str(universe_id)
    assert body["session_id"] is None
    # Reuse means no re-canonization pass.
    mock_builder_cls.assert_not_called()


def test_demo_world_creates_and_canonizes_on_first_run():
    """Fresh path: setting + universe are created, then content is canonized."""
    universe_id = uuid4()
    mv_id = uuid4()
    with (
        patch(
            "monitor_data.tools.neo4j_tools.neo4j_list_universes",
            return_value=[],
        ),
        patch(
            "monitor_data.tools.neo4j_tools.neo4j_ensure_omniverse",
            return_value={"omniverse_id": str(uuid4())},
        ),
        patch(
            "monitor_data.tools.neo4j_tools.neo4j_create_multiverse",
            return_value=SimpleNamespace(id=mv_id),
        ),
        patch(
            "monitor_data.tools.neo4j_tools.neo4j_create_universe",
            return_value=SimpleNamespace(id=universe_id),
        ),
        patch(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            return_value=_no_systems(),
        ),
        patch("monitor_agents.quick_world.agent.QuickWorldBuilder") as mock_builder_cls,
    ):
        mock_builder_cls.return_value._canonize = AsyncMock(return_value=(9, []))
        response = client.post("/api/forge/demo-world", params={"start_playing": "false"})

    assert response.status_code == 200
    body = response.json()
    assert body["reused"] is False
    assert body["world_name"] == "Millhaven"
    assert body["universe_id"] == str(universe_id)
    assert body["committed"] == 9
    mock_builder_cls.return_value._canonize.assert_awaited_once()


def test_demo_world_bootstraps_session_when_start_playing():
    universe_id = uuid4()
    mv_id = uuid4()
    existing = SimpleNamespace(name="Millhaven", id=universe_id, multiverse_id=mv_id)
    with (
        patch(
            "monitor_data.tools.neo4j_tools.neo4j_list_universes",
            return_value=[existing],
        ),
        patch(
            "monitor_data.tools.mongodb_tools.mongodb_list_game_systems",
            return_value=_no_systems(),
        ),
        patch("monitor_ui.routers.forge._ensure_demo_pc", return_value="pc-1"),
        patch(
            "monitor_ui.routers.chat.create_session",
            new=AsyncMock(return_value=SimpleNamespace(id="sess-9")),
        ),
    ):
        response = client.post("/api/forge/demo-world", params={"start_playing": "true"})

    assert response.status_code == 200
    assert response.json()["session_id"] == "sess-9"
