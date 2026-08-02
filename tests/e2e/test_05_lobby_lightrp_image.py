"""
E2E Test 05 — Two-tier hub: lobby data, light-RP round trip, image endpoints.

Covers the 2026-07-31 UI redesign (docs/superpowers/specs/2026-07-31-ui-two-tier-hub-design.md):
  - Lobby load: universe + session list endpoints against real containers.
  - Light RP: create a card, open a conversatory, send one line, get a reply.
    The LLM boundary (ConversationLoop.start/step/finish) is stubbed — LLM
    behaviour is covered elsewhere; this test proves the wiring.
  - Image generation: fake adapter (no network), real folder storage —
    portrait arrives PENDING; approving it with use_as_avatar sets avatar_url
    to the MinIO key (the only avatar-mutation path since Task 8).
  - Asset gallery: list endpoint includes the generated portrait and (after
    approval) supports filtering by approval_status / reference_status.

Run with::

    RUN_INTEGRATION=1 RUN_E2E=1 uv run pytest tests/e2e/test_05_lobby_lightrp_image.py -v
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

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
    def capabilities(self):
        from monitor_data.llm.image_providers import ImageCapabilities

        return ImageCapabilities(
            provider_id="e2e-fake",
            model="e2e-image-1",
            supports_reference_images=False,
            supported_aspect_ratios=frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"}),
        )

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        return PNG

    async def generate_image_structured(self, input) -> bytes:
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

                # ── Image endpoints (fake adapter, real folder storage) ───
                # Generate → preview (PENDING) → approve with use_as_avatar.
                res = client.post("/api/image/portrait", json={"character_id": char_id})
                assert res.status_code == 200, res.text
                portrait = res.json()
                assert portrait["key"].startswith(
                    f"assets/portrait/character-{char_id}/"
                )
                assert portrait["avatar_url"]  # presigned (or file://) URL
                # Task 8: generation always produces a PENDING asset and never
                # mutates the avatar directly.
                assert UUID(portrait["asset_id"])  # parses as a UUID
                assert portrait["approval_status"] == "pending"
                assert isinstance(portrait["prompt_warnings"], list)

                # The avatar is unchanged until the asset is approved.
                res = client.get(f"/api/entities/characters/{char_id}")
                assert res.json()["avatar_url"] is None

                # Approving with use_as_avatar is the only avatar-mutation path;
                # avatar_url is persisted as the object key, not the URL.
                res = client.post(
                    f"/api/image/assets/{portrait['asset_id']}/approve",
                    json={"use_as_avatar": True},
                )
                assert res.status_code == 200, res.text
                assert res.json()["approval_status"] == "approved"
                res = client.get(f"/api/entities/characters/{char_id}")
                assert res.json()["avatar_url"] == portrait["key"]

                res = client.get(f"/api/image/avatar/{char_id}", follow_redirects=False)
                assert res.status_code in (302, 307)

                # ── Asset gallery (Task 6 + Task 8 surface) ───────────────
                # The default listing excludes rejected assets and surfaces
                # the just-approved portrait at scope ``character_id``.
                res = client.get(f"/api/image/assets?character_id={char_id}")
                assert res.status_code == 200, res.text
                listing = res.json()
                listed_ids = {asset["asset_id"] for asset in listing}
                assert portrait["asset_id"] in listed_ids
                listed_portrait = next(
                    a for a in listing if a["asset_id"] == portrait["asset_id"]
                )
                assert listed_portrait["approval_status"] == "approved"
                assert listed_portrait["character_id"] == char_id
                # Approved portrait (use_as_avatar) — has its key recorded
                # as the avatar object key (avatar_url is the object key,
                # not a presigned URL).
                assert listed_portrait["minio_key"] == portrait["key"]

                # Scene image while the conversation is still active → 200.
                # Uses the same conversation the portrait step ran against,
                # proving the scene endpoint renders a real asset (asset_id +
                # pending status + key prefix), decoupled from the chat loop.
                #
                # The conversation API keeps sessions process-local; the scene
                # endpoint looks the conversation up in Mongo, so we seed a
                # doc matching the schema ``_load_scene_source`` reads.
                from monitor_data.db.mongodb import get_mongodb_client
                mongo = get_mongodb_client()
                mongo.get_collection("conversations").insert_one(
                    {
                        "conversation_id": conv_id,
                        "character_id": char_id,
                        "turns": [
                            {
                                "turn_index": i,
                                "role": "user" if i % 2 == 0 else "assistant",
                                "content": f"Turn {i}",
                            }
                            for i in range(3)
                        ],
                        "universe_id": None,
                    }
                )
                res = client.post(
                    "/api/image/scene",
                    json={"conversation_id": conv_id},
                )
                assert res.status_code == 200, res.text
                scene = res.json()
                assert scene["key"].startswith("assets/scene/")
                assert UUID(scene["asset_id"])
                assert scene["approval_status"] == "pending"
                assert isinstance(scene["prompt_warnings"], list)

                # Scene asset shows up in the gallery at the conversation scope.
                res = client.get(f"/api/image/assets?conversation_id={conv_id}")
                assert res.status_code == 200
                listed_ids = {asset["asset_id"] for asset in res.json()}
                assert scene["asset_id"] in listed_ids

                client.post(
                    f"/api/entities/characters/{char_id}/conversations/{conv_id}/end"
                )

                # Scene image with a missing conversation → 404 (no spend).
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
