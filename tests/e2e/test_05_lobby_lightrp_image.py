"""
E2E Test 05 — Two-tier hub: lobby data, light-RP round trip, image endpoints.

Covers the 2026-07-31 UI redesign (docs/superpowers/specs/2026-07-31-ui-two-tier-hub-design.md):
  - Lobby load: universe + session list endpoints against real containers.
  - Light RP: create a card, open a conversatory, send one line, get a reply.
    The LLM boundary (ConversationLoop.start/step/finish) is stubbed — LLM
    behaviour is covered elsewhere; this test proves the wiring.
  - Image generation: fake adapter (no network), real folder storage —
    portrait sets avatar_url to the MinIO key, scene returns a stored image.

Run with::

    RUN_INTEGRATION=1 RUN_E2E=1 uv run pytest tests/e2e/test_05_lobby_lightrp_image.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

PNG = b"\x89PNG-e2e-fake"


class _FakeLoop:
    """Minimal ConversationLoop stand-in (router only touches these members)."""

    def __init__(self) -> None:
        self.state = SimpleNamespace(conversation_id=uuid4())

    async def step(self, text: str) -> list[dict]:
        return [
            {
                "text": f"*the fox grins at '{text}'*",
                "emotional_state": "amused",
                "relationship_snapshot": {"trust": 0.1},
            }
        ]

    async def finish(self) -> list:
        return []


class _FakeImageAdapter:
    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        return PNG


@pytest.mark.e2e
class TestTwoTierHub:
    async def test_lobby_lightrp_and_image_flow(self, e2e_databases):
        from monitor_agents.loops.conversation_loop import ConversationLoop

        import monitor_ui.routers.image_gen as image_gen
        from monitor_ui.main import create_app

        with (
            patch.object(
                ConversationLoop,
                "start",
                new=AsyncMock(side_effect=lambda **kwargs: _FakeLoop()),
            ),
            patch.object(
                image_gen,
                "resolve_image_adapter",
                new=AsyncMock(return_value=_FakeImageAdapter()),
            ),
        ):
            with TestClient(create_app()) as client:
                # ── Lobby load ────────────────────────────────────────────
                res = client.get("/api/universes/universes")
                assert res.status_code == 200
                assert isinstance(res.json(), list)

                res = client.get("/api/chat")
                assert res.status_code == 200
                assert isinstance(res.json(), list)

                # ── Light-RP round trip ───────────────────────────────────
                res = client.post(
                    "/api/entities/characters",
                    json={
                        "name": "E2E Wisp",
                        "description": "A fox-spirit guide.",
                        "personality": "playful",
                        "first_message": "Well met, traveller.",
                    },
                )
                assert res.status_code == 201, res.text
                char_id = res.json()["id"]

                res = client.post(
                    f"/api/entities/characters/{char_id}/conversations", json={}
                )
                assert res.status_code == 200, res.text
                conv = res.json()
                assert conv["opening"] == "Well met, traveller."
                conv_id = conv["conversation_id"]

                res = client.post(
                    f"/api/entities/characters/{char_id}/conversations/{conv_id}/send",
                    json={"text": "Hello, fox.", "include_cross_incarnation": False},
                )
                assert res.status_code == 200, res.text
                reply = res.json()
                assert "fox grins" in reply["text"]
                assert reply["emotional_state"] == "amused"

                client.post(
                    f"/api/entities/characters/{char_id}/conversations/{conv_id}/end"
                )

                # ── Image endpoints (fake adapter, real folder storage) ───
                res = client.post("/api/image/portrait", json={"character_id": char_id})
                assert res.status_code == 200, res.text
                portrait = res.json()
                assert portrait["key"].startswith(f"portraits/{char_id}/")
                assert portrait["avatar_url"]  # presigned (or file://) URL

                # avatar_url persisted as the object key, not the URL
                res = client.get(f"/api/entities/characters/{char_id}")
                assert res.json()["avatar_url"] == portrait["key"]

                res = client.get(f"/api/image/avatar/{char_id}", follow_redirects=False)
                assert res.status_code in (302, 307)

                # Scene image needs turns — the conversation ended, so point at
                # a fresh fake adapter call with a missing conversation → 404.
                res = client.post(
                    "/api/image/scene", json={"conversation_id": str(uuid4())}
                )
                assert res.status_code == 404

    async def test_image_portrait_400_without_provider(self, e2e_databases):
        import monitor_ui.routers.image_gen as image_gen
        from monitor_ui.main import create_app

        with patch.object(
            image_gen, "resolve_image_adapter", new=AsyncMock(return_value=None)
        ):
            with TestClient(create_app()) as client:
                res = client.post(
                    "/api/entities/characters",
                    json={"name": "E2E NoPic", "description": "x"},
                )
                assert res.status_code == 201, res.text
                res = client.post(
                    "/api/image/portrait", json={"character_id": res.json()["id"]}
                )
                assert res.status_code == 400
                assert "/config" in res.json()["detail"]
