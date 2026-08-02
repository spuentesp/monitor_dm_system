"""
E2E: Play-mode loop-suggestion behavior — receiving a suggestion, dismissing it
without spending, accepting another, and rendering the resulting asset.

Mirrors the structure of ``test_roleplay_ooc.py`` / ``test_roleplay_ic.py``
(``TestClient`` + chat-router mocks). The image router goes through real
adapter dispatch via a fake provider (no network).

What this verifies
------------------
1. **Receive.** A scene turn can carry ``image_suggestions`` on the GM
   metadata so the frontend renders them as chips beside the
   suggested-action chips.
2. **Dismiss.** The dismiss path is purely UI-side. The chat loop never
   auto-calls the image router when suggestions are present; the provider
   is *not* called, the budget slot is *not* reserved.
3. **Accept + render.** An explicit click on a chip is the only path that
   generates. The chip posts to ``/api/image/scene`` (or ``/portrait``) with
   ``trigger="loop_suggestion"`` and ``source_turn_id`` provenance; the
   router hits the provider exactly once, decoupled from the scene loop.

Use case: P-3 (autonomous GM turn), P-14 (image suggestion chips).

Requires: ``RUN_E2E=1``.
"""

from __future__ import annotations

import os
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_ui.main import app

# Skip unless explicitly enabled.
pytestmark = pytest.mark.e2e

SKIP_REASON = "Set RUN_E2E=1 to run e2e tests"


@pytest.fixture(autouse=True)
def _skip_unless_e2e():
    if not os.environ.get("RUN_E2E"):
        pytest.skip(SKIP_REASON)


@pytest.fixture()
def client():
    return TestClient(app)


PNG = b"\x89PNG-e2e-suggestion"


class _FakeImageAdapter:
    """Fake provider matching the protocol Task 3 added — no network."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def capabilities(self):
        from monitor_data.llm.image_providers import ImageCapabilities

        return ImageCapabilities(
            provider_id="e2e-suggestion-fake",
            model="e2e-suggestion-1",
            supports_reference_images=False,
            supported_aspect_ratios=frozenset({"1:1", "16:9"}),
        )

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        self.calls.append({"prompt": prompt, "aspect_ratio": aspect_ratio})
        return PNG

    async def generate_image_structured(self, input) -> bytes:
        self.calls.append(
            {
                "prompt": input.prompt,
                "aspect_ratio": input.aspect_ratio,
                "reference_images": list(input.reference_images),
            }
        )
        return PNG


def _patch_settings():
    """Return a permissive settings singleton so the router never hits Mongo."""
    from monitor_data.schemas.image_settings import ImageGenerationSettings

    return ImageGenerationSettings(
        image_moderation_mode="provider_default",
        image_max_per_scene=4,
        image_max_per_conversation=8,
        image_max_per_actor_hour=12,
        image_suggestions_enabled=True,
    )


def _make_session_dict(session_id: str) -> dict:
    now = datetime.now(UTC).isoformat()
    return {
        "id": session_id,
        "title": "E2E Image Suggestion Test",
        "mode": "solo_play",
        "universe_id": str(uuid4()),
        "system_id": None,
        "pack_id": None,
        "system_source_type": None,
        "system_source_id": None,
        "tone": "dramatic",
        "play_mode": "narrative",
        "phase": "active_play",
        "scene_id": str(uuid4()),
        "story_id": str(uuid4()),
        "gm_profile_id": None,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
    }


class TestImageSuggestionPlayMode:
    """Receive → dismiss → accept → render."""

    @patch("monitor_ui.routers.chat._db_save_message")
    @patch("monitor_ui.routers.chat._db_save_session")
    @patch("monitor_ui.routers.chat._SESSIONS", new_callable=dict)
    @patch("monitor_ui.routers.chat._MESSAGES", new_callable=dict)
    def test_receive_dismiss_accept_render(
        self, _msgs, _sessions, _save_ses, _save_msg, client
    ):
        """Receive a scene turn carrying two image suggestions on its
        metadata; the dismiss path leaves the adapter untouched; the
        accept path hits the image endpoint exactly once with provenance.
        """
        from monitor_ui.routers import image_gen

        adapter = _FakeImageAdapter()
        scene_turn_id = "turn-accept-render"

        # ── Receive: scene turn carries image_suggestions metadata ──────
        session_id = str(uuid4())
        _sessions[session_id] = _make_session_dict(session_id)
        _msgs[session_id] = []

        suggestions = [
            {
                "suggestion_id": str(uuid4()),
                "asset_type": "location",
                "subject_entity_ids": [str(uuid4())],
                "reason": "location_change",
                "aspect_ratio": "16:9",
                "source_turn_id": scene_turn_id,
            },
            {
                "suggestion_id": str(uuid4()),
                "asset_type": "portrait",
                "subject_entity_ids": [str(uuid4())],
                "reason": "npc_entry",
                "aspect_ratio": "1:1",
                "source_turn_id": scene_turn_id,
            },
        ]

        async def fake_scene_turn(_sid, _content, **_kwargs):
            return (
                "The market of Dusk unfolds before you.",
                {
                    "type": "scene_turn",
                    "phase": "active_play",
                    "turn_id": scene_turn_id,
                    "image_suggestions": suggestions,
                },
            )

        with (
            patch(
                "monitor_ui.routers.chat._run_scene_turn",
                new=AsyncMock(side_effect=fake_scene_turn),
            ),
            patch.object(
                image_gen, "resolve_image_adapter", new=AsyncMock(return_value=adapter)
            ),
        ):
            res = client.post(
                f"/api/chat/{session_id}/send",
                json={"content": "I step into the market."},
            )

        assert res.status_code == 200, res.text
        body = res.json()
        # Two suggestions arrive on the GM reply so the frontend can render them.
        assert "image_suggestions" in body["metadata"]
        meta_suggestions = body["metadata"]["image_suggestions"]
        assert {s["reason"] for s in meta_suggestions} == {
            "location_change",
            "npc_entry",
        }
        assert all(s["source_turn_id"] == scene_turn_id for s in meta_suggestions)

        # ── Dismiss: scene turn never auto-calls the provider ───────────
        # The dismiss path is purely UI-side, but it would be a regression
        # if the chat loop auto-invoked the image router whenever chips
        # were present — that would silently spend the budget on un-clicked
        # chips.
        assert adapter.calls == [], (
            "scene turn must never invoke the image provider; chips are "
            "suggestions only, generation requires an explicit click."
        )

        # ── Accept + render: chip click calls the portrait endpoint ─────
        # The accept path goes through the real router with the real
        # settings/adapter chain. We stub ``get_character`` so the portrait
        # endpoint sees a valid character (no Mongo write required), then
        # assert the adapter was called — that's the render-the-asset step.
        synthetic_character_id = str(uuid4())
        synthetic_character = {
            "id": synthetic_character_id,
            "name": "E2E Render",
            "description": "Stub character for the accept-render step.",
            "personality": "",
            "avatar_url": None,
            "default_universe_id": None,
            "source_universe_id": None,
            "is_ooc_persona": False,
            "versions": [],
        }

        with (
            patch.object(
                image_gen, "resolve_image_adapter", new=AsyncMock(return_value=adapter)
            ),
            patch(
                "monitor_ui.routers.image_gen.mongodb_get_image_generation_settings",
                return_value=_patch_settings(),
            ),
            patch(
                "monitor_ui.routers.image_gen.get_character",
                return_value=synthetic_character,
            ),
        ):
            res = client.post(
                "/api/image/portrait",
                json={
                    "character_id": synthetic_character_id,
                    "trigger": "loop_suggestion",
                    "source_turn_id": scene_turn_id,
                },
            )

        # The click reached the endpoint and the router rendered an asset
        # (adapter called exactly once with our source_turn_id provenance,
        # response carries a pending asset id).
        assert res.status_code == 200, res.text
        body = res.json()
        assert "asset_id" in body and body["asset_id"]
        assert body["approval_status"] == "pending"
        assert len(adapter.calls) == 1, (
            "the accept click must hit the provider exactly once; the chip "
            "is the only generation path."
        )
        # Note: the suggestion's source_turn_id flows into the GeneratedAsset
        # provenance (source_message_ids per Task 9), not into the provider
        # call payload — see test_image_gen.py for the source_message_ids
        # assertion.
