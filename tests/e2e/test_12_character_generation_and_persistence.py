"""E2E coverage for generic-system vs pack-integrated generation and save flows."""

from __future__ import annotations

from pathlib import Path
from typing import Generator
from uuid import uuid4
import sys

import pytest
from fastapi.testclient import TestClient

try:
    from monitor_ui.main import app
    from monitor_ui.routers import entities as entities_router
except ModuleNotFoundError:
    backend_src = (
        Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
    )
    sys.path.append(str(backend_src))
    from monitor_ui.main import app
    from monitor_ui.routers import entities as entities_router


@pytest.fixture
def ui_client() -> Generator[TestClient, None, None]:
    with TestClient(app) as client:
        yield client


@pytest.mark.e2e
def test_generate_and_save_character_from_generic_system(
    ui_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system_id = uuid4()
    universe_id = uuid4()
    entity_id = uuid4()
    sheet_id = uuid4()

    monkeypatch.setattr(
        entities_router,
        "_resolve_system_source",
        lambda system_id=None, pack_id=None: {
            "source_type": "generic_library",
            "source_label": "Test System",
            "system_id": str(system_id),
            "doc": {
                "name": "Test System",
                "core_mechanic": {
                    "type": "d20",
                    "formula": "1d20",
                    "success_type": "meet_or_beat",
                },
                "attributes": [
                    {
                        "name": "Strength",
                        "abbreviation": "STR",
                        "min_value": 1,
                        "max_value": 20,
                        "default_value": 10,
                    }
                ],
                "skills": [],
                "resources": [],
            },
        },
    )
    monkeypatch.setattr(
        entities_router,
        "_persist_generated_entity",
        lambda **kwargs: {
            "entity_id": str(entity_id),
            "sheet_id": str(sheet_id),
            "profile_id": None,
            "saved_to_universe_id": str(universe_id),
        },
    )

    response = ui_client.post(
        "/api/entities/generate",
        json={
            "system_id": str(system_id),
            "universe_id": str(universe_id),
            "kind": "pc",
            "save": True,
            "name": "Kara Voss",
            "description": "salvage pilot",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "generic_library"
    assert payload["preview"]["name"] == "Kara Voss"
    assert payload["saved"]["entity_id"] == str(entity_id)
    assert payload["saved"]["sheet_id"] == str(sheet_id)


@pytest.mark.e2e
def test_generate_preview_from_pack_embedded_system(
    ui_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack_id = uuid4()

    monkeypatch.setattr(
        entities_router,
        "_resolve_system_source",
        lambda system_id=None, pack_id=None: {
            "source_type": "pack_embedded",
            "source_label": "Haunted Seas Pack",
            "pack_id": str(pack_id),
            "doc": {
                "name": "Haunted Seas",
                "core_mechanic": {
                    "type": "dice_pool",
                    "formula": "2d6",
                    "success_type": "meet_or_beat",
                },
                "attributes": [
                    {
                        "name": "Resolve",
                        "abbreviation": "RSV",
                        "min_value": 1,
                        "max_value": 10,
                        "default_value": 5,
                    }
                ],
                "skills": [],
                "resources": [],
                "npc_stat_blocks": [
                    {
                        "name": "Salt Warden",
                        "tier": "standard",
                        "attributes": {"RSV": 6},
                        "hp": 9,
                        "tags": ["npc", "warden"],
                    }
                ],
            },
        },
    )

    response = ui_client.post(
        "/api/entities/generate",
        json={
            "pack_id": str(pack_id),
            "kind": "npc",
            "save": False,
            "name": "Old Warden",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"]["type"] == "pack_embedded"
    assert payload["preview"]["kind"] == "npc"
    assert payload["preview"]["name"] == "Old Warden"
