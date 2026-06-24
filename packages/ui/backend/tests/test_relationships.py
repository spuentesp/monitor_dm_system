"""Contract tests for inline graph-edge creation (M-37).

FastAPI surface with the Neo4j relationship tools patched. A companion
integration test drives the same endpoints against real Neo4j.
"""

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)

REL_TOOLS = "monitor_data.tools.neo4j_tools.relationships"


def _rel(**over):
    data = {
        "relationship_id": "5:abc:1",
        "from_entity_id": str(uuid4()),
        "to_entity_id": str(uuid4()),
        "rel_type": "ALLIED_WITH",
        "category": "social",
        "subcategory": None,
        "properties": {},
        "tags": [],
        "created_at": None,
    }
    data.update(over)
    return SimpleNamespace(model_dump=lambda mode=None: data)


def test_create_edge_infers_category_from_rel_type():
    a, b = str(uuid4()), str(uuid4())
    with patch(f"{REL_TOOLS}.neo4j_create_relationship") as mock_create:
        mock_create.return_value = _rel(from_entity_id=a, to_entity_id=b)
        resp = client.post(
            "/api/entities/entities/edges",
            json={"from_id": a, "to_id": b, "rel_type": "ALLIED_WITH"},
        )
    assert resp.status_code == 201, resp.text
    # category inferred → "social" for ALLIED_WITH
    sent = mock_create.call_args.args[0]
    assert sent.category.value == "social"
    assert sent.rel_type.value == "ALLIED_WITH"


def test_create_edge_rejects_unknown_rel_type():
    resp = client.post(
        "/api/entities/entities/edges",
        json={"from_id": str(uuid4()), "to_id": str(uuid4()), "rel_type": "BEFRIENDS"},
    )
    assert resp.status_code == 422


def test_create_edge_propagates_missing_entity_as_400():
    with patch(f"{REL_TOOLS}.neo4j_create_relationship") as mock_create:
        mock_create.side_effect = ValueError("Entity not found")
        resp = client.post(
            "/api/entities/entities/edges",
            json={"from_id": str(uuid4()), "to_id": str(uuid4()), "rel_type": "KNOWS"},
        )
    assert resp.status_code == 400


def test_list_edges_returns_relationships():
    eid = str(uuid4())
    with patch(f"{REL_TOOLS}.neo4j_list_relationships") as mock_list:
        mock_list.return_value = SimpleNamespace(
            model_dump=lambda mode=None: {
                "relationships": [_rel().model_dump()],
                "total": 1,
                "limit": 200,
                "offset": 0,
            }
        )
        resp = client.get(f"/api/entities/entities/{eid}/edges")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    # entity filter wired through, both directions
    sent = mock_list.call_args.args[0]
    assert str(sent.entity_id) == eid
    assert sent.direction.value == "both"


def test_list_edges_bad_uuid():
    resp = client.get("/api/entities/entities/not-a-uuid/edges")
    assert resp.status_code == 400
