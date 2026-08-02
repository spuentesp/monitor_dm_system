"""Tests for the image-settings API endpoints (Task 10).

These exercise the ``GET /api/image/settings`` and ``PUT /api/image/settings``
endpoints (the GET endpoints are added to ``image_assets.py`` to keep the
image surface together). The data-layer merge step is exercised end-to-end
through the real :func:`mongodb_get_image_generation_settings` /
:func:`mongodb_update_image_generation_settings` tool functions, with an
in-memory Mongo fake — only the env defaults are mocked.
"""

from __future__ import annotations


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import monitor_data.tools.mongodb_tools.image_settings as image_settings_tools

from monitor_ui.routers.image_assets import router

app = FastAPI()
app.include_router(router, prefix="/api/image")
client = TestClient(app)


# ---------------------------------------------------------------------------
# In-memory Mongo fake (shared with the image_settings tools)
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = list(rows)

    def sort(self, key: str, direction: int) -> _FakeCursor:
        self.rows.sort(
            key=lambda row: (row.get(key) is None, row.get(key)),
            reverse=direction == -1,
        )
        return self

    def __iter__(self):
        return iter(self.rows)


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    @staticmethod
    def _matches(doc: dict, query: dict) -> bool:
        for key, expected in query.items():
            if doc.get(key) != expected:
                return False
        return True

    def find_one(self, query: dict) -> dict | None:
        return next((doc for doc in self.docs if self._matches(doc, query)), None)

    def find(self, query: dict) -> _FakeCursor:
        return _FakeCursor([doc for doc in self.docs if self._matches(doc, query)])

    def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        existing = self.find_one(query)
        if existing is None:
            if not upsert:
                return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
            merged = {**query, **update.get("$set", {})}
            self.docs.append(merged)
            return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()
        for key, value in update.get("$set", {}).items():
            existing[key] = value
        return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()

    def delete_one(self, query: dict) -> None:
        self.docs = [doc for doc in self.docs if not self._matches(doc, query)]


class _FakeMongoClient:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeCollection] = {}

    def get_collection(self, name: str) -> _FakeCollection:
        if name not in self.collections:
            self.collections[name] = _FakeCollection()
        return self.collections[name]


@pytest.fixture
def fake_mongo(monkeypatch: pytest.MonkeyPatch) -> _FakeMongoClient:
    client = _FakeMongoClient()
    monkeypatch.setattr(image_settings_tools, "get_mongodb_client", lambda: client)
    return client


@pytest.fixture
def pinned_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the env defaults for predictable assertions."""
    monkeypatch.setenv("IMAGE_MODERATION_MODE", "provider_default")
    monkeypatch.setenv("IMAGE_MAX_PER_SCENE", "4")
    monkeypatch.setenv("IMAGE_MAX_PER_CONVERSATION", "8")
    monkeypatch.setenv("IMAGE_MAX_PER_ACTOR_HOUR", "12")
    monkeypatch.setenv("IMAGE_SUGGESTIONS_ENABLED", "true")
    from monitor_data.config import get_settings

    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# GET /api/image/settings
# ---------------------------------------------------------------------------


def test_get_settings_returns_env_defaults_when_no_singleton(
    fake_mongo: _FakeMongoClient, pinned_env: None
) -> None:
    res = client.get("/api/image/settings")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "image_moderation_mode": "provider_default",
        "image_max_per_scene": 4,
        "image_max_per_conversation": 8,
        "image_max_per_actor_hour": 12,
        "image_suggestions_enabled": True,
    }


def test_get_settings_returns_merged_view(
    fake_mongo: _FakeMongoClient, pinned_env: None
) -> None:
    fake_mongo.get_collection("image_generation_settings").insert_one(
        {"_id": "global", "image_max_per_scene": 10, "image_suggestions_enabled": False}
    )

    res = client.get("/api/image/settings")

    assert res.status_code == 200
    body = res.json()
    assert body["image_max_per_scene"] == 10
    assert body["image_suggestions_enabled"] is False
    # Untouched fields still come from env
    assert body["image_moderation_mode"] == "provider_default"
    assert body["image_max_per_conversation"] == 8
    assert body["image_max_per_actor_hour"] == 12


# ---------------------------------------------------------------------------
# PUT /api/image/settings
# ---------------------------------------------------------------------------


def test_put_settings_updates_singleton_and_returns_merged_view(
    fake_mongo: _FakeMongoClient, pinned_env: None
) -> None:
    res = client.put(
        "/api/image/settings",
        json={"image_max_per_scene": 20, "image_suggestions_enabled": False},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["image_max_per_scene"] == 20
    assert body["image_suggestions_enabled"] is False
    # Untouched fields still come from env
    assert body["image_modemode_mode" if "image_modemode_mode" in body else "image_moderation_mode"] == "provider_default"
    assert body["image_max_per_conversation"] == 8
    assert body["image_max_per_actor_hour"] == 12

    # Singleton was written
    coll = fake_mongo.get_collection("image_generation_settings")
    assert len(coll.docs) == 1
    assert coll.docs[0]["_id"] == "global"
    assert coll.docs[0]["image_max_per_scene"] == 20
    assert coll.docs[0]["image_suggestions_enabled"] is False


def test_put_settings_round_trip_persists_changes(
    fake_mongo: _FakeMongoClient, pinned_env: None
) -> None:
    """Update then GET round-trips: the new merged view is what we'd see next time."""
    res = client.put(
        "/api/image/settings",
        json={
            "image_moderation_mode": "lines_and_veils",
            "image_max_per_scene": 3,
            "image_max_per_conversation": 6,
            "image_max_per_actor_hour": 20,
            "image_suggestions_enabled": False,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["image_moderation_mode"] == "lines_and_veils"
    assert body["image_max_per_scene"] == 3
    assert body["image_max_per_conversation"] == 6
    assert body["image_max_per_actor_hour"] == 20
    assert body["image_suggestions_enabled"] is False

    # GET returns the merged view
    get = client.get("/api/image/settings")
    assert get.status_code == 200
    assert get.json() == body


def test_put_settings_rejects_out_of_range_value(
    fake_mongo: _FakeMongoClient, pinned_env: None
) -> None:
    """Pydantic bounds = 422; the singleton is not written."""
    res = client.put("/api/image/settings", json={"image_max_per_scene": 200})
    assert res.status_code == 422
    assert fake_mongo.get_collection("image_generation_settings").docs == []


def test_put_settings_rejects_negative_value(
    fake_mongo: _FakeMongoClient, pinned_env: None
) -> None:
    res = client.put("/api/image/settings", json={"image_max_per_actor_hour": -1})
    assert res.status_code == 422


def test_put_settings_rejects_invalid_mode(
    fake_mongo: _FakeMongoClient, pinned_env: None
) -> None:
    res = client.put("/api/image/settings", json={"image_moderation_mode": "off"})
    assert res.status_code == 422


def test_put_settings_partial_update_keeps_other_fields(
    fake_mongo: _FakeMongoClient, pinned_env: None
) -> None:
    """A PUT with only one field leaves the rest alone."""
    client.put("/api/image/settings", json={"image_max_per_scene": 25})
    res = client.put("/api/image/settings", json={"image_suggestions_enabled": False})

    assert res.status_code == 200
    body = res.json()
    assert body["image_max_per_scene"] == 25  # first update kept
    assert body["image_suggestions_enabled"] is False  # second update applied
    # Other fields remain at env defaults
    assert body["image_moderation_mode"] == "provider_default"
    assert body["image_max_per_conversation"] == 8
    assert body["image_max_per_actor_hour"] == 12


# ---------------------------------------------------------------------------
# Review fix round 1: PUT /api/image/settings must be auth-scoped.
# The data-layer tool's authority matrix already lists
# ``mongodb_update_image_generation_settings`` under
# ``["ImageRouter", "CanonKeeper"]``; the router used to call the tool
# directly and bypass that check. With ``IMAGE_SETTINGS_ADMIN_KEY`` set,
# the PUT endpoint now requires a matching ``X-Monitor-Admin-Key`` header.
# Read-open stays unchanged.
# ---------------------------------------------------------------------------


def test_put_settings_requires_admin_key_when_configured(
    fake_mongo: _FakeMongoClient, pinned_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When IMAGE_SETTINGS_ADMIN_KEY is set, PUT without the matching header is 401."""
    monkeypatch.setenv("IMAGE_SETTINGS_ADMIN_KEY", "secret-key-1")
    res = client.put("/api/image/settings", json={"image_max_per_scene": 5})
    assert res.status_code == 401
    # The singleton was not written.
    assert fake_mongo.get_collection("image_generation_settings").docs == []


def test_put_settings_rejects_wrong_admin_key(
    fake_mongo: _FakeMongoClient, pinned_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mismatched X-Monitor-Admin-Key is rejected with 401."""
    monkeypatch.setenv("IMAGE_SETTINGS_ADMIN_KEY", "secret-key-1")
    res = client.put(
        "/api/image/settings",
        json={"image_max_per_scene": 5},
        headers={"X-Monitor-Admin-Key": "wrong"},
    )
    assert res.status_code == 401


def test_put_settings_accepts_correct_admin_key(
    fake_mongo: _FakeMongoClient, pinned_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The correct X-Monitor-Admin-Key unlocks the write."""
    monkeypatch.setenv("IMAGE_SETTINGS_ADMIN_KEY", "secret-key-1")
    res = client.put(
        "/api/image/settings",
        json={"image_max_per_scene": 9},
        headers={"X-Monitor-Admin-Key": "secret-key-1"},
    )
    assert res.status_code == 200
    assert res.json()["image_max_per_scene"] == 9


def test_get_settings_stays_open_when_admin_key_configured(
    fake_mongo: _FakeMongoClient, pinned_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read-open: the GET endpoint is unaffected by the admin-key policy."""
    monkeypatch.setenv("IMAGE_SETTINGS_ADMIN_KEY", "secret-key-1")
    res = client.get("/api/image/settings")
    assert res.status_code == 200
