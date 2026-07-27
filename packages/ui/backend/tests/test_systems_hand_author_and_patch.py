"""Contract tests for hand-authoring / targeted-patch endpoints on RPG systems.

INGESTION_PIPELINE_AUDIT.md Finding 8: before this, the only way to fix one
field of an already-ingested ``game_systems`` document (e.g. relabel a
mislabeled character-creation step, add a missing attribute, correct a
placeholder core_mechanic) was a raw, ad-hoc Mongo ``update_one``. These
tests exercise the two new/extended REST endpoints:

  - ``POST /api/entities/systems``      — hand-author a system from scratch
  - ``PUT  /api/entities/systems/{id}``  — targeted field patch (extended
    beyond name/description/version/rules to also cover attributes/skills/
    resources/core_mechanic/character_creation)

Both route through the same builders (``_build_attributes`` /
``_build_core_mechanic`` / ``_build_character_creation``) that ingestion
uses, so the Finding 2 semantic step_type check applies here too.
"""

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from monitor_data.schemas.game_systems import (
    AttributeDefinition,
    CoreMechanic,
    CoreMechanicType,
    GameSystemResponse,
    SuccessType,
)

from monitor_ui.main import app

client = TestClient(app)

ROUTER = "monitor_ui.routers.entities"


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


# ── POST /systems — hand-authoring ──────────────────────────────────


def test_create_system_minimal() -> None:
    with patch(f"{ROUTER}.mongodb_create_game_system") as mock_create:
        mock_create.return_value = _response(name="Tiny Homebrew")
        resp = client.post(
            "/api/entities/systems",
            json={"name": "Tiny Homebrew", "description": "A minimal test system."},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Tiny Homebrew"
    assert mock_create.called


def test_create_system_with_attributes_and_core_mechanic() -> None:
    with patch(f"{ROUTER}.mongodb_create_game_system") as mock_create:
        mock_create.return_value = _response(
            name="Dice Pool System",
            core_mechanic=CoreMechanic(
                type=CoreMechanicType.DICE_POOL,
                formula="Attribute + Skill",
                success_type=SuccessType.COUNT_SUCCESSES,
            ),
            attributes=[
                AttributeDefinition(
                    name="Might",
                    abbreviation="MGT",
                    min_value=1,
                    max_value=5,
                    default_value=2,
                )
            ],
        )
        resp = client.post(
            "/api/entities/systems",
            json={
                "name": "Dice Pool System",
                "attributes": [{"name": "Might", "abbreviation": "MGT"}],
                "core_mechanic": {
                    "mechanic_type": "dice_pool",
                    "formula": "Attribute + Skill",
                    "success_type": "count_successes",
                },
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["core_mechanic"]["mechanic_type"] == "dice_pool"
    assert body["attributes"][0]["name"] == "Might"

    # The builder call received a real GameSystemCreate with typed attributes
    call_params = mock_create.call_args[0][0]
    assert call_params.attributes[0].name == "Might"
    assert call_params.core_mechanic.type == CoreMechanicType.DICE_POOL


def test_create_system_with_creation_steps_gets_semantic_validation() -> None:
    """Finding 8 bullet 3: hand-authored steps go through the same
    step_type/content check as ingestion (Finding 2)."""
    with patch(f"{ROUTER}.mongodb_create_game_system") as mock_create:
        mock_create.return_value = _response(name="Homebrew With Steps")
        resp = client.post(
            "/api/entities/systems",
            json={
                "name": "Homebrew With Steps",
                "character_creation": {
                    "steps": [
                        {
                            "step_number": 1,
                            "step_type": "choose_skills",
                            "title": "Choose a Background",
                            "instructions": "Pick a Background: Wanderer, Scholar, or Guardian.",
                        }
                    ]
                },
            },
        )
    assert resp.status_code == 201
    call_params = mock_create.call_args[0][0]
    assert call_params.character_creation is not None
    # Mislabeled step_type relabeled to CUSTOM, same as ingestion would do.
    assert call_params.character_creation.steps[0].step_type.value == "custom"


# ── PUT /systems/{id} — targeted patch ──────────────────────────────


def test_patch_system_attributes_only() -> None:
    sid = uuid4()
    with patch(f"{ROUTER}.mongodb_update_game_system") as mock_update:
        mock_update.return_value = _response(
            id=sid,
            attributes=[
                AttributeDefinition(
                    name="Cunning",
                    abbreviation="CUN",
                    min_value=1,
                    max_value=5,
                    default_value=2,
                )
            ],
        )
        resp = client.put(
            f"/api/entities/systems/{sid}",
            json={"attributes": [{"name": "Cunning", "abbreviation": "CUN"}]},
        )
    assert resp.status_code == 200
    assert resp.json()["attributes"][0]["name"] == "Cunning"

    call_params = mock_update.call_args[0][1]
    # Only attributes were requested — every other field stays unset so the
    # data-layer update only touches what was asked for.
    assert call_params.attributes is not None
    assert call_params.name is None
    assert call_params.core_mechanic is None
    assert call_params.character_creation is None


def test_patch_system_character_creation_relabels_mismatched_step() -> None:
    sid = uuid4()
    with patch(f"{ROUTER}.mongodb_update_game_system") as mock_update:
        mock_update.return_value = _response(id=sid)
        resp = client.put(
            f"/api/entities/systems/{sid}",
            json={
                "character_creation": {
                    "steps": [
                        {
                            "step_number": 4,
                            "step_type": "choose_class",
                            "title": "Select Disciplines",
                            "instructions": "Choose three starting supernatural powers.",
                        }
                    ]
                }
            },
        )
    assert resp.status_code == 200
    call_params = mock_update.call_args[0][1]
    assert call_params.character_creation.steps[0].step_type.value == "custom"


def test_patch_system_not_found_returns_422_or_404() -> None:
    sid = uuid4()
    with patch(f"{ROUTER}.mongodb_update_game_system") as mock_update:
        mock_update.side_effect = ValueError(f"Game system {sid} not found")
        resp = client.put(f"/api/entities/systems/{sid}", json={"name": "New Name"})
    assert resp.status_code == 422
