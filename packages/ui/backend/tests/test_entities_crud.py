"""Contract tests for single-entity CRUD on the graph (M-36 / M-38).

These exercise the FastAPI surface with the underlying Neo4j tools patched,
mirroring the ``test_universes.py`` style. A companion integration suite
(``test_entities_crud_integration.py``) drives the same endpoints against a
real Neo4j instance.
"""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)

ENTITIES_TOOLS = "monitor_data.tools.neo4j_tools.entities"


def _entity(**over):
    """A stand-in EntityResponse exposing ``model_dump`` like the real schema."""
    data = {
        "id": str(uuid4()),
        "universe_id": str(uuid4()),
        "name": "Mira",
        "entity_type": "character",
        "is_archetype": False,
        "description": "An elven scout.",
        "properties": {},
        "state_tags": [],
        "canon_level": "canon",
        "confidence": 1.0,
        "authority": "gm",
    }
    data.update(over)
    return SimpleNamespace(
        is_archetype=data["is_archetype"],
        state_tags=data["state_tags"],
        model_dump=lambda mode=None: data,
    )


# ── create (M-38) ────────────────────────────────────────────────


def test_create_entity_returns_201():
    uni = str(uuid4())
    with patch(f"{ENTITIES_TOOLS}.neo4j_create_entity") as mock_create:
        mock_create.return_value = _entity(universe_id=uni, name="Iron Brotherhood",
                                           entity_type="faction")
        resp = client.post(
            "/api/entities/entities",
            json={"universe_id": uni, "name": "Iron Brotherhood",
                  "entity_type": "faction", "description": "A mercenary order."},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Iron Brotherhood"
    assert mock_create.called


def test_create_entity_rejects_bad_type():
    resp = client.post(
        "/api/entities/entities",
        json={"universe_id": str(uuid4()), "name": "X", "entity_type": "wizardish"},
    )
    assert resp.status_code == 422


# ── read (M-36) ──────────────────────────────────────────────────


def test_get_entity_found():
    eid = str(uuid4())
    with patch(f"{ENTITIES_TOOLS}.neo4j_get_entity") as mock_get:
        mock_get.return_value = _entity(id=eid)
        resp = client.get(f"/api/entities/entities/{eid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Mira"


def test_get_entity_404():
    with patch(f"{ENTITIES_TOOLS}.neo4j_get_entity") as mock_get:
        mock_get.return_value = None
        resp = client.get(f"/api/entities/entities/{uuid4()}")
    assert resp.status_code == 404


def test_get_entity_bad_uuid():
    resp = client.get("/api/entities/entities/not-a-uuid")
    assert resp.status_code == 400


# ── update (M-36) ────────────────────────────────────────────────


def test_patch_entity_fields():
    eid = str(uuid4())
    with patch(f"{ENTITIES_TOOLS}.neo4j_get_entity") as mock_get, patch(
        f"{ENTITIES_TOOLS}.neo4j_update_entity"
    ) as mock_update:
        mock_get.return_value = _entity(id=eid)
        mock_update.return_value = _entity(id=eid, description="A grizzled veteran scout.")
        resp = client.patch(
            f"/api/entities/entities/{eid}",
            json={"description": "A grizzled veteran scout."},
        )
    assert resp.status_code == 200
    assert resp.json()["description"] == "A grizzled veteran scout."
    # Only the field-update tool should fire when no tags are supplied.
    mock_update.assert_called_once()


def test_patch_entity_tags_diffs_add_and_remove():
    eid = str(uuid4())
    with patch(f"{ENTITIES_TOOLS}.neo4j_get_entity") as mock_get, patch(
        f"{ENTITIES_TOOLS}.neo4j_set_state_tags"
    ) as mock_tags:
        mock_get.return_value = _entity(id=eid, state_tags=["wounded", "hidden"])
        mock_tags.return_value = _entity(id=eid, state_tags=["hidden", "blessed"])
        resp = client.patch(
            f"/api/entities/entities/{eid}",
            json={"tags": ["hidden", "blessed"]},
        )
    assert resp.status_code == 200
    # diff of {hidden,blessed} vs {wounded,hidden} → add blessed, remove wounded
    _eid_arg, params = mock_tags.call_args.args
    assert params.add_tags == ["blessed"]
    assert params.remove_tags == ["wounded"]


def test_patch_entity_404():
    with patch(f"{ENTITIES_TOOLS}.neo4j_get_entity") as mock_get:
        mock_get.return_value = None
        resp = client.patch(
            f"/api/entities/entities/{uuid4()}", json={"name": "Nope"}
        )
    assert resp.status_code == 404


def test_patch_entity_noop_when_tags_unchanged():
    eid = str(uuid4())
    with patch(f"{ENTITIES_TOOLS}.neo4j_get_entity") as mock_get, patch(
        f"{ENTITIES_TOOLS}.neo4j_set_state_tags"
    ) as mock_tags:
        mock_get.return_value = _entity(id=eid, state_tags=["hidden"])
        resp = client.patch(
            f"/api/entities/entities/{eid}", json={"tags": ["hidden"]}
        )
    assert resp.status_code == 200
    mock_tags.assert_not_called()
