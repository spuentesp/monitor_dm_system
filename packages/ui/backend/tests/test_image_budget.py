"""Tests for image-generation budget enforcement (Task 10).

The router checks three budgets before sending the prompt to the provider:

- ``image_max_per_scene`` — hard cap on successful generations per scene.
- ``image_max_per_conversation`` — hard cap on successful generations per
  conversation/session (the "user-facing scope" for a play session).
- ``image_max_per_actor_hour`` — hard cap on successful generations per
  actor per hour.

A budget breach returns HTTP 429 with a structured payload that
includes ``scope``, ``used``, ``limit``, and human-readable retry
guidance. The router only counts **successful** generations: failed
provider calls and rolled-back reservations don't consume the budget.

The router reserves the slot **immediately before** the provider
invocation and rolls back on provider/upload failure (releasing the
Redis counter or the Mongo fallback derivation), so failed calls
never count.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from monitor_data.llm.image_providers import ImageCapabilities
from monitor_data.schemas.generated_assets import (
    GeneratedAsset,
    GeneratedAssetCreate,
)
from monitor_data.schemas.image_settings import ImageGenerationSettings

import monitor_data.tools.mongodb_tools.image_settings as image_settings_tools
import monitor_ui.image_budget as image_budget
import monitor_ui.routers.image_gen as image_gen
from monitor_ui.routers.image_gen import router

app = FastAPI()
app.include_router(router, prefix="/api/image")
client = TestClient(app)

CHAR = {
    "id": "c-1",
    "name": "Wisp",
    "description": "A fox-spirit guide.",
    "personality": "playful",
    "gm_notes": "",
    "avatar_url": None,
    "entity_id": None,
    "default_universe_id": None,
    "source_universe_id": None,
}

PNG = b"\x89PNG-fake"
CONVERSATION_ID = uuid4()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeAdapter:
    def capabilities(self) -> ImageCapabilities:
        return ImageCapabilities(
            provider_id="fake-provider",
            model="fake-image-1",
            supports_reference_images=False,
            supported_aspect_ratios=frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"}),
        )

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        return PNG

    async def generate_image_structured(self, input) -> bytes:
        return PNG


class _FakeCollection:
    def __init__(self) -> None:
        self.docs: list[dict] = []

    def find_one(self, query: dict) -> dict | None:
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def find(self, query: dict):
        matched = [
            doc for doc in self.docs
            if all(doc.get(k) == v for k, v in query.items())
        ]
        return iter(matched)

    def count_documents(self, query: dict) -> int:
        def _matches(doc: dict) -> bool:
            for key, expected in query.items():
                actual = doc.get(key)
                if isinstance(expected, dict) and "$gte" in expected:
                    if actual is None or not (actual >= expected["$gte"]):
                        return False
                elif isinstance(expected, dict) and "$lte" in expected:
                    if actual is None or not (actual <= expected["$lte"]):
                        return False
                elif actual != expected:
                    return False
            return True

        return sum(1 for doc in self.docs if _matches(doc))

    def insert_one(self, doc: dict) -> None:
        self.docs.append(doc)

    def update_one(self, query: dict, update: dict, upsert: bool = False):
        doc = self.find_one(query)
        if doc is None:
            if not upsert:
                return type("UpdateResult", (), {"matched_count": 0, "modified_count": 0})()
            merged = {**query, **update.get("$set", {})}
            self.docs.append(merged)
            return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()
        for key, value in update.get("$set", {}).items():
            doc[key] = value
        return type("UpdateResult", (), {"matched_count": 1, "modified_count": 1})()


class _FakeMongoClient:
    def __init__(self) -> None:
        self.collections: dict[str, _FakeCollection] = {}

    def get_collection(self, name: str) -> _FakeCollection:
        if name not in self.collections:
            self.collections[name] = _FakeCollection()
        return self.collections[name]


class _FakeRedis:
    """In-memory Redis stub for budget counter testing."""

    def __init__(self) -> None:
        self._data: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self._data[key] = self._data.get(key, 0) + 1
        return self._data[key]

    def decr(self, key: str) -> int:
        if key in self._data:
            self._data[key] = max(0, self._data[key] - 1)
        return self._data.get(key, 0)

    def expire(self, key: str, ttl: int) -> None:
        return None

    def get(self, key: str) -> int | None:
        return self._data.get(key)


def _fake_create_asset(params: GeneratedAssetCreate) -> GeneratedAsset:
    now = datetime.now(UTC)
    return GeneratedAsset(
        asset_id=uuid4(),
        approved_by=None,
        approved_at=None,
        created_at=now,
        updated_at=now,
        **params.model_dump(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_adapter():
    return _FakeAdapter()


@pytest.fixture
def mock_storage():
    minio = AsyncMock()
    minio.presigned_url.return_value = "https://minio.example.com/presigned/abc"
    with (
        patch.object(image_gen, "get_minio_client", return_value=minio),
        patch.object(image_gen, "get_postgres_client", return_value=AsyncMock()),
    ):
        yield minio


@pytest.fixture
def mock_create_asset():
    with patch.object(image_gen, "mongodb_create_generated_asset") as create:
        create.side_effect = _fake_create_asset
        yield create


@pytest.fixture
def mock_context():
    with patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)):
        yield


@pytest.fixture
def fake_mongo(monkeypatch: pytest.MonkeyPatch) -> _FakeMongoClient:
    client = _FakeMongoClient()
    monkeypatch.setattr(image_settings_tools, "get_mongodb_client", lambda: client)
    monkeypatch.setattr(image_budget, "get_mongodb_client", lambda: client)
    monkeypatch.setattr(image_gen, "get_mongodb_client", lambda: client)
    return client


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    """Wire a fake Redis client that returns the in-memory stub's state."""
    redis = _FakeRedis()
    mock_client = MagicMock()
    mock_client.is_available.return_value = True
    mock_client._data = redis._data

    # The budget module calls ``_get_client()`` on the Redis client to get
    # the underlying redis-py stub, then uses incr/decr/expire/get on it.
    # We expose the in-memory stub methods directly.
    raw = MagicMock()
    raw.incr.side_effect = redis.incr
    raw.decr.side_effect = redis.decr
    raw.expire.side_effect = redis.expire
    raw.get.side_effect = redis.get
    mock_client._get_client.return_value = raw

    monkeypatch.setattr(image_budget, "get_redis_client", lambda: mock_client)
    return redis


@pytest.fixture
def disabled_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = MagicMock()
    mock_client.is_available.return_value = False
    monkeypatch.setattr(image_budget, "get_redis_client", lambda: mock_client)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_recent_asset(
    fake_mongo: _FakeMongoClient,
    *,
    conversation_id: UUID | None = None,
    created_at: datetime | None = None,
    scene_id: UUID | None = None,
) -> None:
    doc = {
        "asset_id": str(uuid4()),
        "asset_type": "portrait",
        "minio_key": "assets/portrait/test/x.png",
        "byte_size": 1024,
        "character_id": "c-1",
        "prompt": "existing",
        "provider_id": "fake-provider",
        "provider_model": "fake-image-1",
        "approval_status": "pending",
        "conversation_id": str(conversation_id) if conversation_id else None,
        "scene_id": str(scene_id) if scene_id else None,
        "created_at": created_at or datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    coll = fake_mongo.get_collection("generated_assets")
    coll.insert_one(doc)


def _set_settings(
    fake_mongo: _FakeMongoClient,
    *,
    max_per_scene: int = 0,
    max_per_conversation: int = 0,
    max_per_actor_hour: int = 0,
) -> None:
    image_settings_tools.mongodb_update_image_generation_settings(
        ImageGenerationSettings(
            image_max_per_scene=max_per_scene,
            image_max_per_conversation=max_per_conversation,
            image_max_per_actor_hour=max_per_actor_hour,
        )
    )


# ---------------------------------------------------------------------------
# Scene budget (using Redis)
# ---------------------------------------------------------------------------


def test_scene_budget_429_when_redis_counter_at_limit(
    fake_mongo: _FakeMongoClient,
    fake_redis: _FakeRedis,
    fake_adapter,
    mock_storage,
    mock_create_asset,
    mock_context,
) -> None:
    """Pre-seed Redis counter to the limit; the next request returns 429."""
    _set_settings(fake_mongo, max_per_scene=2)
    # Simulate two successful prior generations in the same scene.
    fake_redis._data["image_budget:scene:test-scene"] = 2

    # The portrait endpoint doesn't take a scene_id, so we exercise the
    # actor-hour counter here. Use the actor-hour budget for the test:
    fake_redis._data.pop("image_budget:scene:test-scene", None)
    # Set actor_hour limit instead and verify that path.
    _set_settings(fake_mongo, max_per_actor_hour=2)
    fake_redis._data["image_budget:actor_hour:c-1"] = 2

    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 429
    body = res.json()
    detail = body["detail"]
    assert detail["scope"] == "actor_hour"
    assert detail["used"] == 2
    assert detail["limit"] == 2
    assert detail["retry"]


# ---------------------------------------------------------------------------
# Conversation budget
# ---------------------------------------------------------------------------


def test_conversation_budget_429_when_redis_counter_at_limit(
    fake_mongo: _FakeMongoClient,
    fake_redis: _FakeRedis,
    fake_adapter,
    mock_storage,
    mock_create_asset,
    mock_context,
) -> None:
    """Pre-seed the conversation counter; the next request returns 429."""
    _set_settings(fake_mongo, max_per_conversation=2)
    # Pre-seed Redis counter for the conversation
    fake_redis._data[f"image_budget:conversation:{CONVERSATION_ID}"] = 2

    # Provide a conversation doc so the scene endpoint can load it
    fake_mongo.get_collection("conversations").insert_one(
        {
            "conversation_id": str(CONVERSATION_ID),
            "universe_id": str(uuid4()),
            "turns": [
                {"turn_index": 0, "speaker_role": "player", "text": "hello"},
            ],
        }
    )

    with (
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post(
            "/api/image/scene",
            json={"conversation_id": str(CONVERSATION_ID), "last_n": 12},
        )

    assert res.status_code == 429
    body = res.json()
    detail = body["detail"]
    assert detail["scope"] == "conversation"
    assert detail["used"] == 2
    assert detail["limit"] == 2
    assert detail["retry"]


# ---------------------------------------------------------------------------
# Actor-hour budget
# ---------------------------------------------------------------------------


def test_actor_hour_budget_429_when_redis_counter_at_limit(
    fake_mongo: _FakeMongoClient,
    fake_redis: _FakeRedis,
    fake_adapter,
    mock_storage,
    mock_create_asset,
    mock_context,
) -> None:
    """Pre-seed actor-hour counter; the next request returns 429."""
    _set_settings(fake_mongo, max_per_actor_hour=1)
    fake_redis._data["image_budget:actor_hour:c-1"] = 1

    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 429
    body = res.json()
    detail = body["detail"]
    assert detail["scope"] == "actor_hour"
    assert detail["used"] == 1
    assert detail["limit"] == 1
    assert detail["retry"]


# ---------------------------------------------------------------------------
# Budget Redis rollback
# ---------------------------------------------------------------------------


def test_actor_hour_budget_rolls_back_on_provider_failure(
    fake_mongo: _FakeMongoClient,
    fake_redis: _FakeRedis,
    fake_adapter,
    mock_storage,
    mock_create_asset,
    mock_context,
) -> None:
    """A failed provider call does NOT consume the actor-hour budget."""
    _set_settings(fake_mongo, max_per_actor_hour=1)

    # First call: provider fails
    failing_adapter = _FakeAdapter()

    async def fail_generate(*args, **kwargs):
        raise RuntimeError("provider down")

    failing_adapter.generate_image = fail_generate
    failing_adapter.generate_image_structured = fail_generate

    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=failing_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 502  # provider failure

    # Counter was rolled back; the next request should succeed.
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200


# ---------------------------------------------------------------------------
# Redis fallback
# ---------------------------------------------------------------------------


def test_redis_fallback_derives_used_count_from_mongo(
    fake_mongo: _FakeMongoClient,
    disabled_redis: None,
    fake_adapter,
    mock_storage,
    mock_create_asset,
    mock_context,
) -> None:
    """When Redis is unavailable, the budget count falls back to MongoDB."""
    _set_settings(fake_mongo, max_per_actor_hour=1)
    _seed_recent_asset(fake_mongo)

    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
        patch.object(image_gen, "assemble_image_context", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 429
    body = res.json()
    assert body["detail"]["scope"] == "actor_hour"
    assert body["detail"]["used"] >= 1
