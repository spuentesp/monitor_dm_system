"""Tests for the image-generation settings MongoDB persistence tools (Task 10).

The settings live in a single MongoDB singleton document (``_id="global"``)
keyed by the five :class:`ImageGenerationSettings` fields. The two
operations are:

- ``mongodb_get_image_generation_settings`` — return the merged
  settings (env defaults with Mongo overrides applied on top). Returns
  the merged :class:`ImageGenerationSettings` typed model.
- ``mongodb_update_image_generation_settings`` — merge ``params`` over
  the current document, upsert the singleton, and return the resulting
  merged settings. Pydantic bounds are enforced by the schema itself;
  the tool calls ``model_validate`` so a 422 surface is impossible
  (the caller has to send a valid model).

The merging semantics are per-field: every value present in the Mongo
document wins over the environment default. The env defaults come from
:meth:`monitor_data.config.settings`; the tests pin the env values
explicitly so the assertions are deterministic.
"""

from __future__ import annotations


import pytest

import monitor_data.tools.mongodb_tools.image_settings as image_settings_tools
from monitor_data.config import Settings, get_settings
from monitor_data.schemas.image_settings import ImageGenerationSettings


# ---------------------------------------------------------------------------
# Fake Mongo
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_mongo(monkeypatch: pytest.MonkeyPatch) -> _FakeMongoClient:
    client = _FakeMongoClient()
    monkeypatch.setattr(image_settings_tools, "get_mongodb_client", lambda: client)
    return client


@pytest.fixture
def env_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Pin the env defaults the tool merges over."""
    get_settings.cache_clear()
    monkeypatch.setenv("IMAGE_MODERATION_MODE", "provider_default")
    monkeypatch.setenv("IMAGE_MAX_PER_SCENE", "4")
    monkeypatch.setenv("IMAGE_MAX_PER_CONVERSATION", "8")
    monkeypatch.setenv("IMAGE_MAX_PER_ACTOR_HOUR", "12")
    monkeypatch.setenv("IMAGE_SUGGESTIONS_ENABLED", "true")
    get_settings.cache_clear()
    return get_settings()


# ---------------------------------------------------------------------------
# mongodb_get_image_generation_settings
# ---------------------------------------------------------------------------


def test_get_returns_env_defaults_when_mongo_singleton_absent(
    fake_mongo: _FakeMongoClient, env_settings: Settings
) -> None:
    settings = image_settings_tools.mongodb_get_image_generation_settings()
    assert settings.image_moderation_mode == "provider_default"
    assert settings.image_max_per_scene == 4
    assert settings.image_max_per_conversation == 8
    assert settings.image_max_per_actor_hour == 12
    assert settings.image_suggestions_enabled is True


def test_get_merges_mongo_overrides_over_env_defaults(
    fake_mongo: _FakeMongoClient, env_settings: Settings
) -> None:
    """Per-field: every Mongo value overrides the env default."""
    fake_mongo.get_collection("image_generation_settings").insert_one(
        {
            "_id": "global",
            "image_max_per_scene": 10,
            "image_suggestions_enabled": False,
        }
    )

    settings = image_settings_tools.mongodb_get_image_generation_settings()

    assert settings.image_max_per_scene == 10  # overridden
    assert settings.image_suggestions_enabled is False  # overridden
    # Untouched fields come from the env defaults.
    assert settings.image_moderation_mode == "provider_default"
    assert settings.image_max_per_conversation == 8
    assert settings.image_max_per_actor_hour == 12


# ---------------------------------------------------------------------------
# mongodb_update_image_generation_settings
# ---------------------------------------------------------------------------


def test_update_creates_singleton_when_absent(
    fake_mongo: _FakeMongoClient, env_settings: Settings
) -> None:
    params = ImageGenerationSettings(
        image_moderation_mode="lines_and_veils",
        image_max_per_scene=2,
        image_max_per_conversation=6,
        image_max_per_actor_hour=20,
        image_suggestions_enabled=False,
    )

    returned = image_settings_tools.mongodb_update_image_generation_settings(params)

    assert returned == params
    coll = fake_mongo.get_collection("image_generation_settings")
    assert len(coll.docs) == 1
    assert coll.docs[0]["_id"] == "global"
    assert coll.docs[0]["image_moderation_mode"] == "lines_and_veils"
    assert coll.docs[0]["image_max_per_scene"] == 2
    assert coll.docs[0]["image_suggestions_enabled"] is False


def test_update_partial_merges_with_existing_singleton(
    fake_mongo: _FakeMongoClient, env_settings: Settings
) -> None:
    """Updating only a subset of fields leaves the rest of the document alone."""
    image_settings_tools.mongodb_update_image_generation_settings(
        ImageGenerationSettings(image_max_per_scene=20)
    )
    image_settings_tools.mongodb_update_image_generation_settings(
        ImageGenerationSettings(image_suggestions_enabled=False)
    )

    coll = fake_mongo.get_collection("image_generation_settings")
    assert len(coll.docs) == 1
    assert coll.docs[0]["_id"] == "global"
    assert coll.docs[0]["image_max_per_scene"] == 20
    assert coll.docs[0]["image_suggestions_enabled"] is False
    # Other fields can be absent — the merge step on read brings env
    # defaults for anything the singleton never wrote.


def test_update_rejects_out_of_range_value(
    fake_mongo: _FakeMongoClient, env_settings: Settings
) -> None:
    """Pydantic ge/le bounds reject invalid update payloads at validation time."""
    with pytest.raises(ValueError):
        ImageGenerationSettings(image_max_per_scene=200)  # > 100
    with pytest.raises(ValueError):
        ImageGenerationSettings(image_max_per_actor_hour=-1)  # < 0
    with pytest.raises(ValueError):
        ImageGenerationSettings(
            image_moderation_mode="something_else"  # not in Literal
        )
    # The Mongo singleton stays untouched.
    assert fake_mongo.get_collection("image_generation_settings").docs == []


def test_get_returns_what_update_wrote(
    fake_mongo: _FakeMongoClient, env_settings: Settings
) -> None:
    """Round-trip: write updates, then read with merge returns the merged values."""
    image_settings_tools.mongodb_update_image_generation_settings(
        ImageGenerationSettings(
            image_moderation_mode="lines_and_veils",
            image_max_per_scene=3,
            image_suggestions_enabled=False,
        )
    )

    settings = image_settings_tools.mongodb_get_image_generation_settings()

    assert settings.image_moderation_mode == "lines_and_veils"
    assert settings.image_max_per_scene == 3
    assert settings.image_suggestions_enabled is False
    # Env defaults still win for fields the update never touched.
    assert settings.image_max_per_conversation == 8
    assert settings.image_max_per_actor_hour == 12


def test_update_then_clear_uses_env_defaults(
    fake_mongo: _FakeMongoClient, env_settings: Settings
) -> None:
    image_settings_tools.mongodb_update_image_generation_settings(
        ImageGenerationSettings(image_max_per_scene=42)
    )
    fake_mongo.get_collection("image_generation_settings").delete_one({"_id": "global"})

    settings = image_settings_tools.mongodb_get_image_generation_settings()
    assert settings.image_max_per_scene == 4
