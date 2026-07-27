from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID

from fastapi.testclient import TestClient
from monitor_data.schemas.base import KnowledgeTreeType
from monitor_data.schemas.universe import MultiverseResponse, UniverseResponse

from monitor_ui.main import app

client = TestClient(app)

_UNIVERSE_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
_SYSTEM_ID = UUID("123e4567-e89b-12d3-a456-426614174999")
_MULTIVERSE_ID = UUID("123e4567-e89b-12d3-a456-426614174111")
_PARENT_MV_ID = UUID("123e4567-e89b-12d3-a456-426614174222")


def _multiverse(**overrides) -> MultiverseResponse:
    base = {
        "id": _MULTIVERSE_ID,
        "omniverse_id": UUID("123e4567-e89b-12d3-a456-426614174333"),
        "name": "The Mistlands",
        "system_name": "D&D 5e",
        "description": "A setting",
        "is_template": False,
        "knowledge_tree_type": KnowledgeTreeType.DYNAMIC,
        "parent_multiverse_id": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    base.update(overrides)
    return MultiverseResponse(**base)


def _universe(default_game_system_id: UUID | None = None) -> UniverseResponse:
    return UniverseResponse(
        id=_UNIVERSE_ID,
        multiverse_id=UUID("123e4567-e89b-12d3-a456-426614174111"),
        name="Test Universe",
        description="A universe bound to a system",
        default_game_system_id=default_game_system_id,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_get_universe_state_endpoint():
    with patch("monitor_ui.routers.universes.neo4j_get_universe_state") as mock_state:
        mock_state.return_value = {
            "entities": [],
            "facts": [],
            "axioms": [],
            "relationships": [],
        }
        # Router is mounted at /api/universes and defines /universes/... paths,
        # so the public path doubles the segment (matches frontend api.ts).
        response = client.get("/api/universes/universes/123e4567-e89b-12d3-a456-426614174000/state")
        assert response.status_code == 200
        assert "entities" in response.json()


def test_get_universe_includes_default_game_system_id():
    """The universe detail response carries the bound game system (P2.2)."""
    with (
        patch(
            "monitor_ui.routers.universes.neo4j_get_universe",
            return_value=_universe(_SYSTEM_ID),
        ),
        patch("monitor_ui.routers.universes._universe_counts", return_value={}),
    ):
        response = client.get(f"/api/universes/universes/{_UNIVERSE_ID}")
        assert response.status_code == 200
        assert response.json()["default_game_system_id"] == str(_SYSTEM_ID)


def test_list_universes_includes_default_game_system_id():
    """The universe list response carries the field, null when unbound."""
    with (
        patch(
            "monitor_ui.routers.universes.neo4j_list_universes",
            return_value=[_universe()],
        ),
        patch("monitor_ui.routers.universes._universe_counts", return_value={}),
    ):
        response = client.get("/api/universes/universes")
        assert response.status_code == 200
        assert response.json()[0]["default_game_system_id"] is None


def test_seed_universe_endpoint():
    """Seed endpoint awaits WorldArchitect.seed_universe and maps the result (M-33/M-4)."""
    seed_result = {
        "generated": 8,
        "entities": [{"id": "e1", "name": "NPC One"}],
        "errors": [],
    }
    mock_seed = AsyncMock(return_value=seed_result)
    with (
        patch(
            "monitor_ui.routers.universes.neo4j_get_universe",
            return_value=_universe(),
        ),
        patch("monitor_agents.world_architect.agent.WorldArchitect") as mock_architect_cls,
    ):
        mock_architect_cls.return_value.seed_universe = mock_seed
        response = client.post(
            f"/api/universes/universes/{_UNIVERSE_ID}/seed",
            json={"entity_count": 8, "location_count": 2, "npc_count": 6},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["universe_id"] == str(_UNIVERSE_ID)
        assert body["entities_created"] == 8
        assert body["entities"] == seed_result["entities"]
        assert body["errors"] == []
        assert body["status"] == "seeded"
        mock_seed.assert_awaited_once_with(
            universe_id=_UNIVERSE_ID,
            num_entities=8,
            location_count=2,
            npc_count=6,
        )


def test_fork_universe_endpoint():
    """Fork deep-clones canon into a new universe and returns a summary (M-35)."""
    with (
        patch(
            "monitor_ui.routers.universes.neo4j_get_universe",
            return_value=_universe(),
        ),
        patch(
            "monitor_data.tools.neo4j_tools.neo4j_fork_universe",
            return_value={
                "new_universe_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "entities_cloned": 12,
                "relationships_cloned": 5,
            },
        ) as mock_fork,
    ):
        response = client.post(
            f"/api/universes/universes/{_UNIVERSE_ID}/fork",
            json={"name": "Forked Vale"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "forked"
        assert body["name"] == "Forked Vale"
        assert body["source_universe_id"] == str(_UNIVERSE_ID)
        assert body["new_universe_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        assert body["entities_cloned"] == 12
        assert body["relationships_cloned"] == 5
        mock_fork.assert_called_once_with(
            source_universe_id=_UNIVERSE_ID,
            name="Forked Vale",
            description="Fork of Test Universe",
        )


def test_fork_universe_missing_source_is_404():
    with patch(
        "monitor_ui.routers.universes.neo4j_get_universe",
        return_value=None,
    ):
        response = client.post(
            f"/api/universes/universes/{_UNIVERSE_ID}/fork",
            json={"name": "Forked Vale"},
        )
        assert response.status_code == 404


# ─── F3-3: multiverse metadata shape ──────────────────────────


def test_list_multiverses_includes_metadata():
    """The multiverse list carries the fields the Worlds UI needs (F3-3 phase 1)."""
    mv = _multiverse(is_template=True, parent_multiverse_id=_PARENT_MV_ID)
    with (
        patch("monitor_ui.routers.universes.neo4j_list_multiverses", return_value=[mv]),
        patch("monitor_ui.routers.universes.neo4j_list_universes", return_value=[]),
    ):
        response = client.get("/api/universes/multiverses")
        assert response.status_code == 200
        body = response.json()[0]
        assert body["system_name"] == "D&D 5e"
        assert body["is_template"] is True
        assert body["knowledge_tree_type"] == KnowledgeTreeType.DYNAMIC.value
        assert body["parent_multiverse_id"] == str(_PARENT_MV_ID)
        assert body["universe_count"] == 0


def test_list_universes_includes_template_flag_and_tone():
    u = _universe()
    with (
        patch("monitor_ui.routers.universes.neo4j_list_universes", return_value=[u]),
        patch("monitor_ui.routers.universes._universe_counts", return_value={}),
    ):
        response = client.get("/api/universes/universes")
        assert response.status_code == 200
        body = response.json()[0]
        assert body["is_template"] is False
        assert "tone" in body


# ─── F3-3: multiverse update ──────────────────────────────────


def test_update_multiverse_endpoint():
    updated = _multiverse(name="Renamed", system_name="Pathfinder 2e")
    with patch("monitor_ui.routers.universes.neo4j_update_multiverse", return_value=updated) as mock_update:
        response = client.put(
            f"/api/universes/multiverses/{_MULTIVERSE_ID}",
            json={"name": "Renamed", "system_name": "Pathfinder 2e"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "Renamed"
        assert body["system_name"] == "Pathfinder 2e"
        params = mock_update.call_args.args[1]
        assert params.name == "Renamed"
        assert params.system_name == "Pathfinder 2e"
        assert params.description is None


def test_update_multiverse_unknown_is_404():
    with patch(
        "monitor_ui.routers.universes.neo4j_update_multiverse",
        side_effect=ValueError(f"Multiverse {_MULTIVERSE_ID} not found"),
    ):
        response = client.put(
            f"/api/universes/multiverses/{_MULTIVERSE_ID}",
            json={"name": "Renamed"},
        )
        assert response.status_code == 404


# ─── F3-3: safe multiverse deletion ───────────────────────────


def test_delete_multiverse_empty_is_204():
    with (
        patch(
            "monitor_ui.routers.universes.neo4j_get_multiverse",
            return_value=_multiverse(),
        ),
        patch("monitor_ui.routers.universes.neo4j_list_universes", return_value=[]),
        patch("monitor_ui.routers.universes.neo4j_delete_multiverse") as mock_delete,
    ):
        response = client.delete(f"/api/universes/multiverses/{_MULTIVERSE_ID}")
        assert response.status_code == 204
        mock_delete.assert_called_once_with(_MULTIVERSE_ID, force=False)


def test_delete_multiverse_non_empty_is_409():
    with (
        patch(
            "monitor_ui.routers.universes.neo4j_get_multiverse",
            return_value=_multiverse(),
        ),
        patch(
            "monitor_ui.routers.universes.neo4j_list_universes",
            return_value=[_universe()],
        ),
        patch("monitor_ui.routers.universes.neo4j_delete_multiverse") as mock_delete,
    ):
        response = client.delete(f"/api/universes/multiverses/{_MULTIVERSE_ID}")
        assert response.status_code == 409
        assert "1 universe(s)" in response.json()["detail"]
        mock_delete.assert_not_called()


def test_delete_multiverse_unknown_is_404():
    with patch("monitor_ui.routers.universes.neo4j_get_multiverse", return_value=None):
        response = client.delete(f"/api/universes/multiverses/{_MULTIVERSE_ID}")
        assert response.status_code == 404


def test_delete_multiverse_force_cascades():
    """?force=true is the explicit escape hatch for non-empty settings."""
    with (
        patch(
            "monitor_ui.routers.universes.neo4j_get_multiverse",
            return_value=_multiverse(),
        ),
        patch(
            "monitor_ui.routers.universes.neo4j_list_universes",
            return_value=[_universe()],
        ),
        patch("monitor_ui.routers.universes.neo4j_delete_multiverse") as mock_delete,
    ):
        response = client.delete(f"/api/universes/multiverses/{_MULTIVERSE_ID}?force=true")
        assert response.status_code == 204
        mock_delete.assert_called_once_with(_MULTIVERSE_ID, force=True)


# ─── F3-3: universe update preserves multiverse ownership ─────


def test_update_universe_preserves_multiverse_ownership():
    with patch("monitor_ui.routers.universes.neo4j_update_universe", return_value=_universe()) as mock_update:
        response = client.put(
            f"/api/universes/universes/{_UNIVERSE_ID}",
            json={"name": "New Name", "tone": "dark"},
        )
        assert response.status_code == 200
        # The update schema has no multiverse_id field — ownership can't move.
        params = mock_update.call_args.args[1]
        assert not hasattr(params, "multiverse_id") or params.multiverse_id is None
        assert params.tone == "dark"
        assert response.json()["multiverse_id"] == str(_MULTIVERSE_ID)
