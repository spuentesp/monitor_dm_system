"""
Light RP surfaces (Phase 7): the light_rp router and the graduate / memory
service wiring in character_conversation.

No live DB / LM — collaborators are mocked. The wiring tests assert the real
callee is invoked with the expected arguments (guided-start entry points,
ConversationLoop.start, memory write/delete tools).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from monitor_ui.main import app
from monitor_ui.routers import character_conversation as cc

pytestmark = pytest.mark.usefixtures("local_auth_mode")

client = TestClient(app)


# ---------------------------------------------------------------------------
# Router: one-click start with a universe character
# ---------------------------------------------------------------------------


class TestUniverseCharacterStart:
    def test_lists_chat_capable_universe_characters(self):
        universe_id = "11111111-1111-1111-1111-111111111111"
        entity = SimpleNamespace(
            id="ent-9",
            name="Sister Veil",
            description="A keeper of quiet oaths.",
            universe_id=universe_id,
            entity_type="character",
        )
        entity.model_dump = lambda: {  # type: ignore[attr-defined]
            "id": "ent-9",
            "name": "Sister Veil",
            "description": "A keeper of quiet oaths.",
            "universe_id": universe_id,
            "entity_type": "character",
        }
        with patch(
            "monitor_ui.routers.light_rp.neo4j_list_entities",
            return_value=SimpleNamespace(entities=[entity]),
        ) as mock_list:
            resp = client.get(f"/api/entities/universes/{universe_id}/characters")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body[0]["entity_id"] == "ent-9"
        assert body[0]["name"] == "Sister Veil"
        filt = mock_list.call_args.args[0]
        assert str(filt.universe_id) == universe_id
        assert filt.entity_type.value == "character"

    def test_start_calls_the_service_with_expected_arguments(self):
        opened = {"conversation_id": "conv-9", "character_id": "card-9", "opening": "Hello."}
        with patch(
            "monitor_ui.routers.character_conversation.start_universe_character_chat",
            new=AsyncMock(return_value=opened),
        ) as mock_start:
            resp = client.post(
                "/api/entities/universe-characters/start",
                json={"entity_id": "ent-9", "persona_character_id": "p-1"},
            )
        assert resp.status_code == 200, resp.text
        mock_start.assert_awaited_once()
        assert mock_start.await_args.args[0] == "ent-9"
        assert mock_start.await_args.kwargs["persona_character_id"] == "p-1"

    def test_start_unknown_entity_is_404(self):
        with patch(
            "monitor_ui.routers.character_conversation.start_universe_character_chat",
            new=AsyncMock(side_effect=ValueError("Character entity ent-x not found")),
        ):
            resp = client.post(
                "/api/entities/universe-characters/start",
                json={"entity_id": "ent-x"},
            )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Router: streaming send
# ---------------------------------------------------------------------------


class TestStreamSend:
    def test_streams_token_events_as_sse(self):
        async def _stream(*args: Any, **kwargs: Any):
            yield {"type": "token", "text": "The "}
            yield {"type": "token", "text": "road."}
            yield {
                "type": "done",
                "conversation_id": "conv-1",
                "text": "The road.",
                "emotional_state": "calm",
                "relationship_snapshot": {"trust": 0.1},
            }

        with patch(
            "monitor_ui.routers.character_conversation.send_message_stream",
            new=AsyncMock(return_value=_stream()),
        ) as mock_send:
            resp = client.post(
                "/api/entities/characters/c-1/conversations/conv-1/send-stream",
                json={"text": "Which way?"},
            )

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("text/event-stream")
        mock_send.assert_awaited_once()
        args = mock_send.await_args.args
        assert args[0] == "conv-1"
        assert args[1] == "Which way?"
        assert mock_send.await_args.kwargs["character_id"] == "c-1"
        frames = [
            json.loads(line[6:])
            for line in resp.text.splitlines()
            if line.startswith("data: ") and line != "data: [DONE]"
        ]
        assert "".join(f.get("text", "") for f in frames if f.get("type") == "token") == "The road."
        assert frames[-1]["type"] == "done"
        assert frames[-1]["emotional_state"] == "calm"
        assert resp.text.strip().endswith("data: [DONE]")

    def test_unknown_conversation_maps_to_409(self):
        async def _boom(*args: Any, **kwargs: Any):
            raise KeyError("conv-gone")
            yield  # pragma: no cover

        with patch(
            "monitor_ui.routers.character_conversation.send_message_stream",
            new=AsyncMock(return_value=_boom()),
        ):
            resp = client.post(
                "/api/entities/characters/c-1/conversations/conv-gone/send-stream",
                json={"text": "hi"},
            )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Router: memories about you
# ---------------------------------------------------------------------------


class TestMemoryRoutes:
    def test_list_calls_the_service_with_expected_arguments(self):
        payload = {"memories": [{"id": "mem-1", "text": "hi", "importance": 0.5, "created_at": ""}], "total": 1}
        with patch(
            "monitor_ui.routers.character_conversation.list_memories_about_you",
            return_value=payload,
        ) as mock_list:
            resp = client.get("/api/entities/characters/c-1/memories/about-you?limit=5")

        assert resp.status_code == 200, resp.text
        assert resp.json()["total"] == 1
        mock_list.assert_called_once_with("c-1", universe_id=None, limit=5)

    def test_delete_calls_the_service_with_expected_arguments(self):
        with patch(
            "monitor_ui.routers.character_conversation.delete_character_memory",
            return_value=True,
        ) as mock_delete:
            resp = client.delete("/api/entities/characters/c-1/memories/mem-1")
        assert resp.status_code == 204, resp.text
        mock_delete.assert_called_once_with("c-1", "mem-1")

    def test_delete_unknown_memory_is_404(self):
        with patch(
            "monitor_ui.routers.character_conversation.delete_character_memory",
            return_value=False,
        ):
            resp = client.delete("/api/entities/characters/c-1/memories/mem-x")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Router: graduate to a campaign
# ---------------------------------------------------------------------------


class TestGraduateRoutes:
    def test_prepare_calls_the_service_with_expected_arguments(self):
        payload = {
            "character_id": "c-1",
            "universe_id": "u-1",
            "entity_id": "e-1",
            "version_id": "v-1",
            "start_options": [],
            "start_options_source": "none",
            "question": "How would you like to begin?",
            "suggested_answers": [],
        }
        with patch(
            "monitor_ui.routers.character_conversation.graduate_prepare",
            new=AsyncMock(return_value=payload),
        ) as mock_prep:
            resp = client.get("/api/entities/characters/c-1/graduate/prepare?universe_id=u-1&tone=grim")

        assert resp.status_code == 200, resp.text
        mock_prep.assert_awaited_once_with("c-1", universe_id="u-1", tone="grim")

    def test_graduate_calls_the_service_with_expected_arguments(self):
        payload = {"chosen": {}, "session_create": {"mode": "autonomous_gm"}}
        with patch(
            "monitor_ui.routers.character_conversation.graduate_to_campaign",
            new=AsyncMock(return_value=payload),
        ) as mock_grad:
            resp = client.post(
                "/api/entities/characters/c-1/graduate",
                json={
                    "universe_id": "u-1",
                    "persona_character_id": "p-1",
                    "start_answer": "The storm",
                    "start_options": [{"option_id": "storm", "title": "The storm"}],
                    "question_text": "How would you like to begin?",
                },
            )

        assert resp.status_code == 200, resp.text
        mock_grad.assert_awaited_once_with(
            "c-1",
            universe_id="u-1",
            persona_character_id="p-1",
            start_answer="The storm",
            start_options=[{"option_id": "storm", "title": "The storm"}],
            question_text="How would you like to begin?",
            tone=None,
        )


# ---------------------------------------------------------------------------
# Service wiring: graduation hands off to the guided start's entry points
# ---------------------------------------------------------------------------

_CARD = {
    "id": "c-1",
    "name": "Wisp",
    "description": "A fox-spirit guide.",
    "is_ooc_persona": False,
    "default_universe_id": None,
    "source_universe_id": None,
    "entity_id": None,
    "versions": [],
}
_PERSONA_CARD = {
    "id": "p-1",
    "name": "Mira",
    "description": "A smuggler.",
    "is_ooc_persona": True,
    "versions": [],
}
_UNIVERSE_ID = "11111111-1111-1111-1111-111111111111"
_ENTITY_ID = "22222222-2222-2222-2222-222222222222"
_BACKING = {"entity_id": _ENTITY_ID, "universe_id": _UNIVERSE_ID, "version_id": "v-1", "npc_profile_id": None}


def _start_option():
    from monitor_agents.world_seed.models import StartOption

    return StartOption(
        option_id="storm", title="The storm at Blackreef", summary="A storm rolls in.", location="Blackreef"
    )


class TestGraduateWiring:
    def test_graduate_calls_the_start_choice_entry_point_with_expected_arguments(self):
        from monitor_agents.session_zero import StartChoice

        option = _start_option()
        choice = StartChoice(
            option_id="storm", option_title="The storm at Blackreef", is_surprise=False, free_answer=""
        )

        with (
            patch.object(cc, "get_character", side_effect=lambda cid: _CARD if cid == "c-1" else _PERSONA_CARD),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=dict(_BACKING))),
            patch.object(cc, "carry_memories_to_incarnation", return_value=4),
            patch(
                "monitor_agents.session_zero.resolve_start_choice",
                new=AsyncMock(return_value=choice),
            ) as mock_resolve,
        ):
            out = asyncio.run(
                cc.graduate_to_campaign(
                    "c-1",
                    universe_id="u-1",
                    persona_character_id="p-1",
                    start_answer="The storm at Blackreef",
                    start_options=[option.chip_dict()],
                    question_text="How would you like to begin?",
                    tone="grim",
                )
            )

        # Real callee: session_zero.resolve_start_choice gets the shown options.
        mock_resolve.assert_awaited_once()
        resolve_kwargs = mock_resolve.await_args.kwargs
        assert resolve_kwargs["question_text"] == "How would you like to begin?"
        assert resolve_kwargs["answer"] == "The storm at Blackreef"
        assert resolve_kwargs["options"] == [option.chip_dict()]

        assert out["memories_carried"] == 4
        assert out["story_premise"] == "A storm rolls in."
        session = out["session_create"]
        assert session["mode"] == "autonomous_gm"
        assert session["universe_id"] == _UNIVERSE_ID
        assert session["persona_id"] == "p-1"
        assert session["story_premise"] == "A storm rolls in."

    def test_prepare_calls_world_seed_and_the_start_question_entry_point(self):
        from monitor_agents.session_zero import QuestionCategory, SessionZeroQuestion

        option = _start_option()
        seed_result = SimpleNamespace(options=[option], source="canon")
        question = SessionZeroQuestion(
            question_text="How would you like to begin?",
            category=QuestionCategory.START_CHOICE,
            is_final=False,
            reasoning="test",
            suggested_answers=["The storm at Blackreef", "Surprise me"],
        )
        with (
            patch.object(cc, "get_character", return_value=dict(_CARD)),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=dict(_BACKING))),
            patch(
                "monitor_agents.world_seed.seed.WorldSeed.generate_start_options",
                new=AsyncMock(return_value=seed_result),
            ) as mock_seed,
            patch(
                "monitor_agents.session_zero.ask_start_options_question",
                new=AsyncMock(return_value=question),
            ) as mock_ask,
        ):
            out = asyncio.run(cc.graduate_prepare("c-1", universe_id="u-1", tone="grim"))

        # Real callee: WorldSeed.generate_start_options for the chosen universe.
        mock_seed.assert_awaited_once()
        seed_kwargs = mock_seed.await_args.kwargs
        assert seed_kwargs["universe_id"] == _UNIVERSE_ID
        assert seed_kwargs["tone"] == "grim"
        mock_ask.assert_awaited_once()
        ask_kwargs = mock_ask.await_args.kwargs
        assert ask_kwargs["tone"] == "grim"
        assert ask_kwargs["start_options"] == [option.chip_dict()]
        assert out["question"] == "How would you like to begin?"
        assert out["start_options_source"] == "canon"


# ---------------------------------------------------------------------------
# Service wiring: one-click start and memory tools
# ---------------------------------------------------------------------------


class TestStartConversationWiring:
    def test_start_conversation_passes_preset_and_persona_to_the_loop(self):
        card = dict(_CARD)
        fake_loop = SimpleNamespace(
            state=SimpleNamespace(conversation_id="conv-1"),
            add_opening=AsyncMock(),
        )
        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=dict(_BACKING))),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ) as mock_start,
            patch.object(cc, "_cache_loop"),
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=MagicMock()),
        ):
            out = asyncio.run(cc.start_conversation("c-1", persona_character_id=None, preset="light"))

        assert out["preset"] == "light"
        mock_start.assert_awaited_once()
        kwargs = mock_start.await_args.kwargs
        # The LightPreset instance (name "light") is what the loop receives.
        assert kwargs["preset"].name == "light"
        assert kwargs["preset"].stage_canon_proposals is False


class TestMemoryServiceWiring:
    def _mongo(self, docs: list[dict[str, Any]]) -> MagicMock:
        coll = MagicMock()
        coll.count_documents.return_value = len(docs)
        coll.find.return_value.sort.return_value.limit.return_value = docs
        mongo = MagicMock()
        mongo.get_collection.return_value = coll
        return mongo

    def test_list_memories_about_you_filters_conversation_memories(self):
        docs = [
            {
                "memory_id": "mem-1",
                "text": 'Player said: "The safe word is zephyr-abc."',
                "importance": 0.6,
                "entity_id": "e-1",
                "universe_id": "u-1",
                "metadata": {"conversation_id": "conv-1"},
                "created_at": "2026-11-01T00:00:00",
            }
        ]
        mongo = self._mongo(docs)
        with (
            patch.object(cc, "get_character", return_value={"id": "c-1", "versions": [{"entity_id": "e-1"}]}),
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        ):
            out = cc.list_memories_about_you("c-1", universe_id="u-1", limit=10)

        assert out["total"] == 1
        assert out["memories"][0]["id"] == "mem-1"
        assert out["memories"][0]["conversation_id"] == "conv-1"
        query = mongo.get_collection.return_value.find.call_args.args[0]
        assert query["metadata.conversation_id"] == {"$exists": True}
        assert query["universe_id"] == "u-1"

    def test_delete_memory_runs_the_real_delete_tools(self):
        memory_id = "22222222-2222-2222-2222-222222222222"
        coll = MagicMock()
        coll.find_one.return_value = {"memory_id": memory_id, "entity_id": "e-1"}
        mongo = MagicMock()
        mongo.get_collection.return_value = coll
        with (
            patch.object(cc, "get_character", return_value={"id": "c-1", "versions": [{"entity_id": "e-1"}]}),
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch(
                "monitor_data.tools.mongodb_tools.memories.mongodb_delete_memory",
                return_value=True,
            ) as mock_delete,
            patch("monitor_data.tools.qdrant_tools.qdrant_delete") as mock_vector,
        ):
            deleted = cc.delete_character_memory("c-1", memory_id)

        assert deleted is True
        mock_delete.assert_called_once()
        assert str(mock_delete.call_args.args[0]) == memory_id
        # The Qdrant vector goes too, so recall cannot surface a ghost.
        mock_vector.assert_called_once()
        request = mock_vector.call_args.args[0]
        assert request.collection == "memories"
        assert str(request.id) == memory_id

    def test_delete_memory_refuses_foreign_memories(self):
        coll = MagicMock()
        coll.find_one.return_value = {"memory_id": "m-9", "entity_id": "someone-else"}
        mongo = MagicMock()
        mongo.get_collection.return_value = coll
        with (
            patch.object(cc, "get_character", return_value={"id": "c-1", "versions": [{"entity_id": "e-1"}]}),
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        ):
            assert cc.delete_character_memory("c-1", "m-9") is False
