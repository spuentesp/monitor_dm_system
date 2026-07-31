"""Tests for the image generation router (provider + storage fully mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from monitor_data.llm.image_providers import ImageProviderError

import monitor_ui.routers.image_gen as image_gen
from monitor_ui.routers.image_gen import build_portrait_prompt, build_scene_prompt, router

app = FastAPI()
app.include_router(router, prefix="/api/image")
client = TestClient(app)

CHAR = {
    "id": "c-1",
    "name": "Wisp",
    "description": "A fox-spirit guide with ember eyes.",
    "personality": "playful, evasive",
    "gm_notes": "",
    "avatar_url": None,
}

PNG = b"\x89PNG-fake"


class _FakeAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        self.calls.append({"prompt": prompt, "aspect_ratio": aspect_ratio})
        return PNG


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


def test_build_portrait_prompt_uses_character_fields():
    prompt = build_portrait_prompt(CHAR)
    assert "Wisp" in prompt
    assert "fox-spirit guide" in prompt
    assert "playful, evasive" in prompt


def test_build_scene_prompt_includes_excerpt_and_speakers():
    messages = [
        {"speaker_role": "player", "entity_name": None, "text": "I light the lantern."},
        {"speaker_role": "npc", "entity_name": "Wisp", "text": "The dark notices."},
    ]
    prompt = build_scene_prompt(messages, CHAR)
    assert "I light the lantern." in prompt
    assert "Wisp" in prompt
    assert "The dark notices." in prompt


def test_portrait_happy_path(fake_adapter, mock_storage):
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "update_character", return_value=dict(CHAR)) as upd,
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})

    assert res.status_code == 200
    body = res.json()
    assert body["avatar_url"] == "https://minio.example.com/presigned/abc"
    assert body["key"].startswith("portraits/c-1/")
    # avatar_url is set to the *object key*, not the expiring presigned URL
    assert upd.call_args[0][1]["avatar_url"] == body["key"]
    mock_storage.upload.assert_awaited_once()
    assert mock_storage.upload.call_args[0][1] == PNG


def test_portrait_400_when_no_image_provider(mock_storage):
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=None)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 400
    assert "/config" in res.json()["detail"]


def test_portrait_400_when_image_row_is_keyless(mock_storage):
    """A role='image' row without an API key (and no env fallback) makes
    resolve_image_adapter raise ImageProviderError — must surface as 400,
    not an unhandled 500."""
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(
            image_gen,
            "resolve_image_adapter",
            new=AsyncMock(side_effect=ImageProviderError("No API key configured for image provider 'img-a'")),
        ),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 400
    assert "/config" in res.json()["detail"]


def test_portrait_404_for_unknown_character(mock_storage):
    with patch.object(image_gen, "get_character", return_value=None):
        res = client.post("/api/image/portrait", json={"character_id": "nope"})
    assert res.status_code == 404


def test_portrait_502_on_provider_failure(fake_adapter, mock_storage):
    async def _boom(prompt, *, aspect_ratio="1:1"):
        raise RuntimeError("rate limited")

    failing = AsyncMock()
    failing.generate_image.side_effect = _boom
    with (
        patch.object(image_gen, "get_character", return_value=dict(CHAR)),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=failing)),
    ):
        res = client.post("/api/image/portrait", json={"character_id": "c-1"})
    assert res.status_code == 502


def test_scene_from_conversation_turns(fake_adapter, mock_storage):
    mongo = MagicMock()  # pymongo calls are synchronous
    mongo.get_collection.return_value.find_one.return_value = {
        "conversation_id": "conv-1",
        "turns": [
            {"speaker_role": "player", "entity_name": None, "text": "I light the lantern."},
            {"speaker_role": "npc", "entity_name": "Wisp", "text": "The dark notices."},
        ],
    }
    with (
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/scene", json={"conversation_id": "conv-1", "last_n": 12})

    assert res.status_code == 200
    assert res.json()["key"].startswith("scenes/conversation-conv-1/")
    assert fake_adapter.calls[0]["aspect_ratio"] == "16:9"
    assert "I light the lantern." in fake_adapter.calls[0]["prompt"]


def test_scene_from_play_session(fake_adapter, mock_storage):
    rows = [
        {"role": "player", "content": "I open the gate.", "timestamp": "t1"},
        {"role": "gm", "content": "The courtyard is flooded.", "timestamp": "t2"},
    ]
    with (
        patch.object(image_gen, "db_load_messages", return_value=rows),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/scene", json={"session_id": "s-1", "last_n": 12})

    assert res.status_code == 200
    assert res.json()["key"].startswith("scenes/session-s-1/")
    assert "courtyard is flooded" in fake_adapter.calls[0]["prompt"]


def test_scene_400_without_any_source(mock_storage):
    res = client.post("/api/image/scene", json={"last_n": 12})
    assert res.status_code == 400


def test_scene_400_with_both_sources(mock_storage):
    res = client.post("/api/image/scene", json={"conversation_id": "c-1", "session_id": "s-1"})
    assert res.status_code == 400
    assert "not both" in res.json()["detail"]


def test_scene_404_for_unknown_conversation(fake_adapter, mock_storage):
    mongo = MagicMock()  # pymongo calls are synchronous
    mongo.get_collection.return_value.find_one.return_value = None
    with (
        patch.object(image_gen, "get_mongodb_client", return_value=mongo),
        patch.object(image_gen, "resolve_image_adapter", new=AsyncMock(return_value=fake_adapter)),
    ):
        res = client.post("/api/image/scene", json={"conversation_id": "ghost", "last_n": 12})
    assert res.status_code == 404


def test_avatar_redirects_to_presigned_url(mock_storage):
    with patch.object(image_gen, "get_character", return_value={**CHAR, "avatar_url": "portraits/c-1/x.png"}):
        res = client.get("/api/image/avatar/c-1", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"] == "https://minio.example.com/presigned/abc"


def test_avatar_404_without_avatar(mock_storage):
    with patch.object(image_gen, "get_character", return_value=dict(CHAR)):
        res = client.get("/api/image/avatar/c-1")
    assert res.status_code == 404
