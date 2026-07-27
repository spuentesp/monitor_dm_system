"""Contract tests for the GameSystem authoring endpoints (F2-2 phase 7).

``routers/game_systems.py`` was read-only; it now exposes create/update/delete
on ``/api/systems`` using the same builder pipeline as the long-standing
``/api/entities/systems`` routes. Also covers the ``/api/entities/systems``
DELETE, which now routes through ``mongodb_delete_game_system`` (the old raw
motor query matched on a UUID object against a string field and could never
hit).
"""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from monitor_data.schemas.game_systems import (
    CoreMechanic,
    CoreMechanicType,
    GameSystemResponse,
    SuccessType,
)

from monitor_ui.main import app

client = TestClient(app)

GS_ROUTER = "monitor_ui.routers.game_systems"
ENT_ROUTER = "monitor_ui.routers.entities"


def _response(**over) -> GameSystemResponse:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "name": "Homebrew System",
        "description": "",
        "version": None,
        "core_mechanic": CoreMechanic(
            type=CoreMechanicType.D20,
            formula="1d20",
            success_type=SuccessType.MEET_OR_BEAT,
        ),
        "attributes": [],
        "skills": [],
        "resources": [],
        "rules": [],
        "is_builtin": False,
        "source_document_id": None,
        "needs_review": False,
        "degenerate_reason": None,
        "created_at": now,
        "updated_at": None,
    }
    defaults.update(over)
    return GameSystemResponse(**defaults)


# ── POST /api/systems ─────────────────────────────────────────────


def test_create_system_returns_201():
    with patch(f"{GS_ROUTER}.mongodb_create_game_system") as mock_create:
        mock_create.return_value = _response(name="Tiny Homebrew")
        resp = client.post(
            "/api/systems",
            json={"name": "Tiny Homebrew", "description": "A minimal system."},
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Tiny Homebrew"
    assert body["rule_count"] == 0
    # Same builder pipeline as /api/entities/systems: hand-authored provenance
    assert mock_create.call_args.args[0].hand_authored is True


def test_create_system_validation_error():
    with patch(f"{GS_ROUTER}.mongodb_create_game_system") as mock_create:
        mock_create.side_effect = ValueError("provenance missing")
        resp = client.post("/api/systems", json={"name": "X"})
    assert resp.status_code == 422


# ── PUT /api/systems/{id} ─────────────────────────────────────────


def test_update_system_success():
    sid = uuid4()
    with patch(f"{GS_ROUTER}.mongodb_update_game_system") as mock_update:
        mock_update.return_value = _response(id=sid, name="Renamed")
        resp = client.put(f"/api/systems/{sid}", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    # Only the requested field is set on the data-layer update
    update = mock_update.call_args.args[1]
    assert update.name == "Renamed"
    assert update.attributes is None


def test_update_system_not_found():
    sid = uuid4()
    with patch(f"{GS_ROUTER}.mongodb_update_game_system") as mock_update:
        mock_update.side_effect = ValueError(f"Game system {sid} not found")
        resp = client.put(f"/api/systems/{sid}", json={"name": "X"})
    assert resp.status_code == 422


def test_update_system_bad_uuid():
    resp = client.put("/api/systems/not-a-uuid", json={"name": "X"})
    assert resp.status_code == 400


# ── DELETE /api/systems/{id} ──────────────────────────────────────


def test_delete_system_success():
    sid = uuid4()
    with patch(f"{GS_ROUTER}.mongodb_delete_game_system") as mock_delete:
        mock_delete.return_value = None
        resp = client.delete(f"/api/systems/{sid}")
    assert resp.status_code == 204
    assert mock_delete.call_args.args[0] == sid


def test_delete_system_not_found():
    sid = uuid4()
    with patch(f"{GS_ROUTER}.mongodb_delete_game_system") as mock_delete:
        mock_delete.side_effect = ValueError(f"Game system {sid} not found")
        resp = client.delete(f"/api/systems/{sid}")
    assert resp.status_code == 404


def test_delete_system_builtin_rejected():
    with patch(f"{GS_ROUTER}.mongodb_delete_game_system") as mock_delete:
        mock_delete.side_effect = ValueError("Cannot delete builtin game systems")
        resp = client.delete(f"/api/systems/{uuid4()}")
    assert resp.status_code == 422


# ── DELETE /api/entities/systems/{id} (fixed write path) ──────────


def test_entities_delete_system_success():
    sid = uuid4()
    with patch(f"{ENT_ROUTER}.mongodb_delete_game_system") as mock_delete:
        mock_delete.return_value = None
        resp = client.delete(f"/api/entities/systems/{sid}")
    assert resp.status_code == 204
    assert mock_delete.call_args.args[0] == sid


def test_entities_delete_system_not_found():
    sid = uuid4()
    with patch(f"{ENT_ROUTER}.mongodb_delete_game_system") as mock_delete:
        mock_delete.side_effect = ValueError(f"Game system {sid} not found")
        resp = client.delete(f"/api/entities/systems/{sid}")
    assert resp.status_code == 404
