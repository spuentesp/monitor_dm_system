"""POST /packs/{id}/prepare-start — the pack apply starting-situation offer.

Phase 2 task 6: after apply/new-world the client may offer "prepare a
starting situation", which runs the world seed against the new universe so
an ingested book yields somewhere to stand.

Cross-component: the route invokes
``monitor_agents.world_seed.prepare_starting_situation`` with the universe
id and the pack id.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from monitor_ui.main import create_app

pytestmark = pytest.mark.usefixtures("local_auth_mode")

app = create_app()
client = TestClient(app)


def test_prepare_start_offered_in_apply_new_world_response() -> None:
    from types import SimpleNamespace

    from monitor_data.schemas.knowledge_packs import KnowledgePackStatus

    pack_id = uuid.uuid4()
    pack = SimpleNamespace(
        name="Book Pack",
        status=KnowledgePackStatus.READY,
        game_system_id=None,
    )
    with (
        patch("monitor_ui.routers.pack_library.mongodb_get_knowledge_pack", return_value=pack),
        patch(
            "monitor_ui.routers.pack_library._create_setting",
            return_value=(uuid.uuid4(), uuid.uuid4()),
        ),
        patch(
            "monitor_ui.routers.pack_library.CanonKeeper.apply_pack_to_universe",
            return_value={"proposals_created": 1, "committed": 0, "errors": [], "review_status": "pending"},
        ),
    ):
        response = client.post(
            f"/api/ingest/packs/{pack_id}/apply/new-world",
            json={"world_name": "Walkthrough World"},
        )
    assert response.status_code == 201, response.json()
    assert response.json()["can_prepare_starting_situation"] is True
    assert response.json()["universe_id"]


def test_prepare_start_invokes_world_seed_preparation() -> None:
    """Cross-component: the real callee is invoked with the expected args."""
    pack_id = uuid.uuid4()
    universe_id = uuid.uuid4()
    called: dict[str, Any] = {}

    async def _fake_prepare(universe_uid: Any, **kwargs: Any) -> dict[str, Any]:
        called["universe_id"] = str(universe_uid)
        called["pack_ids"] = kwargs.get("pack_ids")
        return {
            "universe_id": str(universe_uid),
            "source": "canon",
            "options": [{"option_id": "dockside-heist-1", "title": "Dockside Heist"}],
            "materialized": {"option_id": "dockside-heist-1"},
        }

    with (
        patch("monitor_ui.routers.pack_library.mongodb_get_knowledge_pack", return_value=object()),
        patch("monitor_agents.world_seed.prepare_starting_situation", _fake_prepare),
    ):
        response = client.post(
            f"/api/ingest/packs/{pack_id}/prepare-start",
            json={"universe_id": str(universe_id)},
        )

    assert response.status_code == 201, response.json()
    assert called["universe_id"] == str(universe_id)
    assert called["pack_ids"] == [str(pack_id)]
    data = response.json()
    assert data["options"][0]["title"] == "Dockside Heist"
    assert data["materialized"]["option_id"] == "dockside-heist-1"


def test_prepare_start_unknown_pack_is_404() -> None:
    with patch("monitor_ui.routers.pack_library.mongodb_get_knowledge_pack", return_value=None):
        response = client.post(
            f"/api/ingest/packs/{uuid.uuid4()}/prepare-start",
            json={"universe_id": str(uuid.uuid4())},
        )
    assert response.status_code == 404
