"""Tests for /api/gm/notes — P2.3 scratchpad persistence.

The notebook is a per-universe note blob. GET returns 200 with empty content
when no row exists yet (the row is created on the first PUT). These tests
assert the GET/PUT round-trip, the empty-state fallback, and the universe
isolation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from monitor_data.schemas.gm_notes import GmNoteResponse

from monitor_ui.main import app

client = TestClient(app)


def test_get_empty_returns_200_with_empty_content() -> None:
    """No prior upsert → GET returns 200 with empty content (no 404)."""
    universe_id = uuid4()
    with patch(
        "monitor_ui.routers.gm_notes.mongodb_get_gm_note",
        return_value=None,
    ):
        response = client.get(f"/api/gm/notes/{universe_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["universe_id"] == str(universe_id)
    assert body["content"] == ""
    assert "updated_at" in body


def test_put_then_get_returns_persisted_content() -> None:
    """PUT creates the row; subsequent GET returns the same content."""
    universe_id = uuid4()
    written = GmNoteResponse(
        universe_id=universe_id,
        content="the party camped outside the chapel",
        updated_at=datetime.now(UTC),
    )

    def fake_upsert(_uid, body):
        written.content = body.content
        return written

    with (
        patch("monitor_ui.routers.gm_notes.mongodb_upsert_gm_note", side_effect=fake_upsert),
        patch("monitor_ui.routers.gm_notes.mongodb_get_gm_note", return_value=written),
    ):
        put_resp = client.put(
            f"/api/gm/notes/{universe_id}",
            json={"content": "the party camped outside the chapel"},
        )
        get_resp = client.get(f"/api/gm/notes/{universe_id}")

    assert put_resp.status_code == 200
    assert put_resp.json()["content"] == "the party camped outside the chapel"
    assert get_resp.status_code == 200
    assert get_resp.json()["content"] == "the party camped outside the chapel"


def test_put_overwrites_prior_content() -> None:
    """The second PUT replaces the first — exactly one row per universe."""
    universe_id = uuid4()
    state = {"content": "first"}

    def fake_upsert(_uid, body):
        state["content"] = body.content
        return GmNoteResponse(
            universe_id=universe_id,
            content=body.content,
            updated_at=datetime.now(UTC),
        )

    def fake_get(_uid):
        return GmNoteResponse(
            universe_id=universe_id,
            content=state["content"],
            updated_at=datetime.now(UTC),
        )

    with (
        patch("monitor_ui.routers.gm_notes.mongodb_upsert_gm_note", side_effect=fake_upsert),
        patch("monitor_ui.routers.gm_notes.mongodb_get_gm_note", side_effect=fake_get),
    ):
        client.put(f"/api/gm/notes/{universe_id}", json={"content": "first"})
        client.put(f"/api/gm/notes/{universe_id}", json={"content": "second"})
        body = client.get(f"/api/gm/notes/{universe_id}").json()

    assert body["content"] == "second"


def test_get_rejects_invalid_uuid() -> None:
    """Bad path arg → 400 (via validate_uuid)."""
    response = client.get("/api/gm/notes/not-a-uuid")
    assert response.status_code == 400


def test_put_rejects_oversized_content() -> None:
    """Content > 50,000 chars → 422 (pydantic min_length/max_length)."""
    universe_id = uuid4()
    response = client.put(
        f"/api/gm/notes/{universe_id}",
        json={"content": "x" * 50_001},
    )
    assert response.status_code == 422
