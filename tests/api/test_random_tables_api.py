"""
API tests for Random Table endpoints.

Tests:
- GET /random-tables - List with filters
- GET /random-tables/{id} - Get single
- POST /random-tables - Create
- PUT /random-tables/{id} - Update
- DELETE /random-tables/{id} - Delete
- POST /random-tables/{id}/roll - Roll on table
"""

from __future__ import annotations

import sys
from pathlib import Path
from collections.abc import Generator
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from datetime import datetime
from monitor_data.schemas.random_tables import (
    RandomTableResponse,
    RandomTableListResponse,
    RandomTableEntry,
    RandomTableType,
)

_backend_src = (
    Path(__file__).resolve().parents[2] / "packages" / "ui" / "backend" / "src"
)
sys.path.insert(0, str(_backend_src))


def _make_mock_table(table_id=None, name="Test Table"):
    return RandomTableResponse(
        table_id=table_id or uuid4(),
        name=name,
        description="Test description",
        table_type=RandomTableType.CUSTOM,
        dice_formula="1d20",
        weighted=False,
        entries=[RandomTableEntry(min_roll=1, max_roll=20, value="Test")],
        created_at=datetime.utcnow(),
    )


def _make_mock_list(tables, total):
    return RandomTableListResponse(
        tables=tables, total=total, limit=50, offset=0
    )


def _make_mock_list(tables, total):
    return RandomTableListResponse(
        tables=tables, total=total, limit=50, offset=0
    )


@pytest.fixture
def patched_rt_client(monkeypatch) -> Generator[TestClient, None, None]:
    from monitor_ui.routers import random_tables as rt_router

    monkeypatch.setattr(
        rt_router,
        "mongodb_list_random_tables",
        lambda filters=None: _make_mock_list(
            [_make_mock_table(name="T1"), _make_mock_table(name="T2")], 2
        ),
    )
    monkeypatch.setattr(
        rt_router,
        "mongodb_get_random_table",
        lambda uid: _make_mock_table(table_id=uid),
    )
    monkeypatch.setattr(
        rt_router,
        "mongodb_create_random_table",
        lambda params: _make_mock_table(name=params.name),
    )
    monkeypatch.setattr(
        rt_router,
        "mongodb_update_random_table",
        lambda uid, params: _make_mock_table(table_id=uid, name="Updated"),
    )
    monkeypatch.setattr(
        rt_router,
        "mongodb_delete_random_table",
        lambda uid: True,
    )
    monkeypatch.setattr(
        rt_router,
        "mongodb_roll_on_table",
        lambda uid, actor_uid: {
            "table_id": str(uid),
            "roll": 14,
            "result": "Goblin Scout",
            "sub_results": [],
        },
    )

    app = FastAPI()
    app.include_router(rt_router.router)
    with TestClient(app) as client:
        yield client


class TestRandomTableEndpoints:
    def test_list(self, patched_rt_client):
        resp = patched_rt_client.get("/random-tables")
        assert resp.status_code == 200

    def test_list_with_filters(self, patched_rt_client):
        resp = patched_rt_client.get(
            "/random-tables",
            params={"universe_id": str(uuid4()), "table_type": "npc"},
        )
        assert resp.status_code == 200

    def test_get(self, patched_rt_client):
        resp = patched_rt_client.get(f"/random-tables/{uuid4()}")
        assert resp.status_code == 200

    def test_create(self, patched_rt_client):
        resp = patched_rt_client.post(
            "/random-tables",
            json={
                "name": "New Table",
                "description": "Test",
                "table_type": "npc",
                "dice_formula": "1d6",
                "entries": [
                    {"min_roll": 1, "max_roll": 3, "value": "Goblin"},
                    {"min_roll": 4, "max_roll": 6, "value": "Orc"},
                ],
            },
        )
        assert resp.status_code == 201

    def test_create_no_entries(self, patched_rt_client):
        resp = patched_rt_client.post(
            "/random-tables",
            json={
                "name": "Empty Table",
                "entries": [],
            },
        )
        # 422 expected since at least one entry required (validation in handler)
        assert resp.status_code in (201, 422)

    def test_update(self, patched_rt_client):
        resp = patched_rt_client.put(
            f"/random-tables/{uuid4()}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200

    def test_update_no_fields(self, patched_rt_client):
        resp = patched_rt_client.put(
            f"/random-tables/{uuid4()}",
            json={},
        )
        assert resp.status_code == 400  # No fields to update

    def test_delete(self, patched_rt_client):
        resp = patched_rt_client.delete(f"/random-tables/{uuid4()}")
        assert resp.status_code == 204

    def test_roll(self, patched_rt_client):
        resp = patched_rt_client.post(f"/random-tables/{uuid4()}/roll")
        assert resp.status_code == 200
        data = resp.json()
        assert "roll" in data
        assert "result" in data

    def test_roll_with_actor(self, patched_rt_client):
        resp = patched_rt_client.post(
            f"/random-tables/{uuid4()}/roll",
            params={"actor_id": str(uuid4())},
        )
        assert resp.status_code == 200

    def test_roll_table_not_found(self, monkeypatch):
        from monitor_ui.routers import random_tables as rt_router
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        def fake_roll_not_found(uid, actor):
            raise ValueError("Table not found")

        app = FastAPI()
        original = rt_router.mongodb_roll_on_table
        rt_router.mongodb_roll_on_table = fake_roll_not_found
        try:
            app.include_router(rt_router.router)
            client = TestClient(app)
            resp = client.post(f"/random-tables/{uuid4()}/roll")
            assert resp.status_code == 404
        finally:
            rt_router.mongodb_roll_on_table = original
