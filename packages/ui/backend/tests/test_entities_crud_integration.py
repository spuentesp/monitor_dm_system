"""Real-usage integration tests for graph entity CRUD (M-36 / M-38).

Drives the live FastAPI endpoints against a **real Neo4j** — no mocks. Each run
provisions its own multiverse/universe via the data-layer tools, performs the
create → read → edit (fields + tags) → read-back round-trip through HTTP, then
tears everything down.

Gated behind ``RUN_INTEGRATION=1`` (see ``pytest.ini`` / root ``conftest.py``).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from monitor_ui.main import app

pytestmark = [pytest.mark.integration, pytest.mark.e2e]

client = TestClient(app)


@pytest.fixture()
def universe_id():
    """Provision an isolated universe in Neo4j and tear it down after."""
    from monitor_data.schemas.universe import MultiverseCreate, UniverseCreate
    from monitor_data.tools.neo4j_tools import (
        neo4j_create_multiverse,
        neo4j_create_universe,
        neo4j_delete_multiverse,
        neo4j_ensure_omniverse,
    )

    omni = neo4j_ensure_omniverse()
    mv = neo4j_create_multiverse(
        MultiverseCreate(
            omniverse_id=UUID(omni["omniverse_id"]),
            name="CRUD Test Multiverse",
            system_name="generic",
            description="ephemeral test fixture",
            is_template=False,
            source_document_id=None,
            parent_multiverse_id=None,
        )
    )
    universe = neo4j_create_universe(
        UniverseCreate(
            multiverse_id=mv.id,
            name="CRUD Test Universe",
            description="ephemeral",
        )
    )
    yield str(universe.id)

    # Cascade delete the multiverse (removes universe + entities).
    try:
        neo4j_delete_multiverse(mv.id)
    except Exception:
        pass


def test_entity_crud_roundtrip(universe_id):
    # ── create (M-38) ───────────────────────────────────────────
    create = client.post(
        "/api/entities/entities",
        json={
            "universe_id": universe_id,
            "name": "Mira",
            "entity_type": "character",
            "description": "An elven scout.",
        },
    )
    assert create.status_code == 201, create.text
    eid = create.json()["id"]

    # ── read (M-36) ─────────────────────────────────────────────
    got = client.get(f"/api/entities/entities/{eid}")
    assert got.status_code == 200
    assert got.json()["name"] == "Mira"

    # ── update fields (M-36) ────────────────────────────────────
    patched = client.patch(
        f"/api/entities/entities/{eid}",
        json={
            "description": "A grizzled veteran scout.",
            "properties": {"allegiance": "Iron Brotherhood"},
        },
    )
    assert patched.status_code == 200, patched.text

    # ── update tags (M-36) ──────────────────────────────────────
    tagged = client.patch(f"/api/entities/entities/{eid}", json={"tags": ["wounded", "hidden"]})
    assert tagged.status_code == 200, tagged.text

    # ── read-back: edits persisted to canon ─────────────────────
    final = client.get(f"/api/entities/entities/{eid}").json()
    assert final["description"] == "A grizzled veteran scout."
    assert final["properties"].get("allegiance") == "Iron Brotherhood"
    assert set(final["state_tags"]) == {"wounded", "hidden"}

    # ── tag diff: drop "wounded", add "blessed" ─────────────────
    client.patch(f"/api/entities/entities/{eid}", json={"tags": ["hidden", "blessed"]})
    after = client.get(f"/api/entities/entities/{eid}").json()
    assert set(after["state_tags"]) == {"hidden", "blessed"}


def test_edge_roundtrip(universe_id):
    """M-37: draw a relationship between two real entities and read it back."""
    a = client.post(
        "/api/entities/entities",
        json={"universe_id": universe_id, "name": "Mira", "entity_type": "character"},
    ).json()["id"]
    b = client.post(
        "/api/entities/entities",
        json={
            "universe_id": universe_id,
            "name": "Iron Brotherhood",
            "entity_type": "faction",
        },
    ).json()["id"]

    edge = client.post(
        "/api/entities/entities/edges",
        json={"from_id": a, "to_id": b, "rel_type": "MEMBER_OF"},
    )
    assert edge.status_code == 201, edge.text
    assert edge.json()["rel_type"] == "MEMBER_OF"
    assert edge.json()["category"] == "membership"

    listed = client.get(f"/api/entities/entities/{a}/edges")
    assert listed.status_code == 200
    rels = listed.json()["relationships"]
    assert any(r["to_entity_id"] == b and r["rel_type"] == "MEMBER_OF" for r in rels)
