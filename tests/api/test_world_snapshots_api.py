"""
API tests for world snapshot endpoints (M-34).

Tests:
- POST /universes/{universe_id}/snapshots - Create snapshot
- GET /universes/{universe_id}/snapshots - List snapshots
- POST /universes/{universe_id}/snapshots/{snapshot_id}/restore - Restore
- GET /universes/{universe_id}/snapshots/compare - Compare two

M-34: Snapshot diff (compare entities/facts/relationships)
"""

from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Generator
from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from uuid import uuid4

# Add UI backend to path
_backend_src = (
    Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
)
sys.path.insert(0, str(_backend_src))


def _make_mock_snapshot(snapshot_id=None, name="Test Snap", entity_count=10, fact_count=5):
    snap = MagicMock()
    snap.snapshot_id = snapshot_id or uuid4()
    snap.name = name
    snap.description = "Test description"
    snap.entity_count = entity_count
    snap.fact_count = fact_count
    snap.created_at = "2024-01-01T00:00:00"
    return snap


def _make_mock_list_response(snapshots, total):
    resp = MagicMock()
    resp.snapshots = snapshots
    resp.total = total
    return resp


def _make_mock_compare_response(a_id=None, b_id=None, universe_id=None):
    resp = MagicMock()
    resp.snapshot_a_id = a_id or uuid4()
    resp.snapshot_b_id = b_id or uuid4()
    resp.universe_id = universe_id or uuid4()
    resp.entities_added = 3
    resp.entities_removed = 1
    resp.entities_modified = 2
    resp.facts_added = 5
    resp.facts_removed = 0
    resp.facts_modified = 1
    resp.relationships_added = 2
    resp.relationships_removed = 0
    resp.entity_diffs = []
    resp.fact_diffs = []
    resp.relationship_diffs = []
    resp.snapshot_a_name = "Year 1000"
    resp.snapshot_b_name = "Year 1001"
    resp.snapshot_a_created_at = "2024-01-01T00:00:00"
    resp.snapshot_b_created_at = "2024-01-02T00:00:00"
    return resp


@pytest.fixture
def patched_snapshot_client(monkeypatch) -> Generator[TestClient, None, None]:
    """Test client with snapshot endpoints patched."""
    from monitor_ui.routers import universes as universes_router

    # Patch neo4j_get_universe to return a mock universe
    monkeypatch.setattr(
        universes_router,
        "neo4j_get_universe",
        lambda uid: MagicMock(id=uid, name="Test"),
    )

    # Patch mongodb tools (deferred import inside endpoints)
    import sys
    mock_snapshots_module = MagicMock()
    mock_snapshots_module.mongodb_create_world_snapshot = lambda req: _make_mock_snapshot(
        snapshot_id=uuid4(), name=req.name, entity_count=10, fact_count=5
    )
    mock_snapshots_module.mongodb_list_world_snapshots = (
        lambda fltr: _make_mock_list_response(
            [_make_mock_snapshot(name="S1"), _make_mock_snapshot(name="S2")], 2
        )
    )
    mock_snapshots_module.mongodb_restore_world_snapshot = (
        lambda sid: {"entities_restored": 42, "facts_restored": 15, "snapshot_id": str(sid)}
    )
    mock_snapshots_module.mongodb_compare_snapshots = lambda a, b: _make_mock_compare_response(
        a_id=a, b_id=b
    )

    sys.modules["monitor_data.tools.mongodb_tools.snapshots"] = mock_snapshots_module

    # Create minimal app
    app = FastAPI(title="Test")
    app.include_router(universes_router.router)

    with TestClient(app) as client:
        yield client

    # Cleanup
    if "monitor_data.tools.mongodb_tools.snapshots" in sys.modules:
        del sys.modules["monitor_data.tools.mongodb_tools.snapshots"]


class TestSnapshotEndpoints:
    def test_create_snapshot(self, patched_snapshot_client):
        uid = str(uuid4())
        resp = patched_snapshot_client.post(
            f"/universes/{uid}/snapshots",
            json={"name": "Pre-battle save", "description": "Before the boss fight"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Pre-battle save"
        assert "snapshot_id" in data
        assert data["status"] == "created"
        assert data["entity_count"] == 10

    def test_create_snapshot_universe_not_found(self, monkeypatch):
        from monitor_ui.routers import universes as universes_router
        monkeypatch.setattr(
            universes_router, "neo4j_get_universe", lambda uid: None
        )

        import sys
        mock_module = MagicMock()
        sys.modules["monitor_data.tools.mongodb_tools.snapshots"] = mock_module

        app = FastAPI()
        app.include_router(universes_router.router)
        client = TestClient(app)
        resp = client.post(
            f"/universes/{uuid4()}/snapshots",
            json={"name": "X"},
        )
        assert resp.status_code == 404

    def test_list_snapshots(self, patched_snapshot_client):
        uid = str(uuid4())
        resp = patched_snapshot_client.get(f"/universes/{uid}/snapshots")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_list_snapshots_universe_not_found(self, monkeypatch):
        from monitor_ui.routers import universes as universes_router
        monkeypatch.setattr(
            universes_router, "neo4j_get_universe", lambda uid: None
        )

        app = FastAPI()
        app.include_router(universes_router.router)
        client = TestClient(app)
        resp = client.get(f"/universes/{uuid4()}/snapshots")
        assert resp.status_code == 404

    def test_restore_snapshot_without_confirm(self, patched_snapshot_client):
        sid = str(uuid4())
        resp = patched_snapshot_client.post(
            f"/universes/{uuid4()}/snapshots/{sid}/restore",
            json={"confirm": False},
        )
        assert resp.status_code == 400
        assert "confirm" in resp.json()["detail"].lower()

    def test_restore_snapshot_with_confirm(self, patched_snapshot_client):
        sid = str(uuid4())
        resp = patched_snapshot_client.post(
            f"/universes/{uuid4()}/snapshots/{sid}/restore",
            json={"confirm": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "restored"
        assert data["entities_restored"] == 42

    def test_compare_snapshots(self, patched_snapshot_client):
        uid = str(uuid4())
        sa = str(uuid4())
        sb = str(uuid4())
        resp = patched_snapshot_client.get(
            f"/universes/{uid}/snapshots/compare",
            params={"snapshot_a_id": sa, "snapshot_b_id": sb},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "entity_summary" in data
        assert "fact_summary" in data
        assert "relationship_summary" in data
        assert data["entity_summary"]["added"] == 3
        assert data["entity_summary"]["modified"] == 2

    def test_compare_snapshots_universe_not_found(self, monkeypatch):
        from monitor_ui.routers import universes as universes_router
        monkeypatch.setattr(
            universes_router, "neo4j_get_universe", lambda uid: None
        )

        app = FastAPI()
        app.include_router(universes_router.router)
        client = TestClient(app)
        resp = client.get(
            f"/universes/{uuid4()}/snapshots/compare",
            params={"snapshot_a_id": str(uuid4()), "snapshot_b_id": str(uuid4())},
        )
        assert resp.status_code == 404
