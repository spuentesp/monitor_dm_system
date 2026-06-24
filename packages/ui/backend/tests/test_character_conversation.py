"""
Unit tests for the character conversatory service (character_conversation.py).

No live DB / LM / ConversationLoop — all collaborators are mocked. Async
functions are driven with asyncio.run() since the backend test suite does not
enable pytest-asyncio auto mode.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_ui.routers import character_conversation as cc


# ---------------------------------------------------------------------------
# ensure_character_backed
# ---------------------------------------------------------------------------


class TestEnsureCharacterBacked:
    def test_returns_existing_backing_without_provisioning(self):
        card = {
            "id": "char-1",
            "name": "Maeve",
            "entity_id": "ent-1",
            "source_universe_id": "uni-1",
        }
        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "_provision_entity_and_profile") as mock_provision,
            patch.object(cc, "update_character") as mock_update,
        ):
            out = asyncio.run(cc.ensure_character_backed("char-1"))

        assert out == {"entity_id": "ent-1", "universe_id": "uni-1"}
        mock_provision.assert_not_called()
        mock_update.assert_not_called()

    def test_expands_light_card_and_persists_entity_id(self):
        card = {"id": "char-2", "name": "Maeve", "entity_id": None, "description": "wary"}

        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"traits": {"wariness": 0.8}, "triggers": []}

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(
                cc, "ensure_conversatory_universe", new=AsyncMock(return_value="uni-conv")
            ),
            patch(
                "monitor_agents.prompts.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value="ent-new"),
            patch.object(cc, "update_character") as mock_update,
        ):
            out = asyncio.run(cc.ensure_character_backed("char-2"))

        assert out == {"entity_id": "ent-new", "universe_id": "uni-conv"}
        mock_update.assert_called_once_with(
            "char-2", {"entity_id": "ent-new", "source_universe_id": "uni-conv"}
        )
        fake_gen.forward.assert_called_once()

    def test_uses_linked_universe_when_present(self):
        card = {
            "id": "char-3",
            "name": "Aldric",
            "entity_id": None,
            "source_universe_id": "uni-real",
        }
        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"triggers": []}

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "ensure_conversatory_universe", new=AsyncMock()) as mock_conv,
            patch(
                "monitor_agents.prompts.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value="ent-x") as prov,
            patch.object(cc, "update_character"),
        ):
            out = asyncio.run(cc.ensure_character_backed("char-3"))

        assert out["universe_id"] == "uni-real"
        mock_conv.assert_not_awaited()  # linked universe short-circuits the host lookup
        assert prov.call_args[0][0] == "uni-real"

    def test_missing_character_raises(self):
        with patch.object(cc, "get_character", return_value=None):
            with pytest.raises(ValueError):
                asyncio.run(cc.ensure_character_backed("nope"))


# ---------------------------------------------------------------------------
# start / send / end
# ---------------------------------------------------------------------------


class TestConversationLifecycle:
    def setup_method(self):
        cc._LOOPS.clear()

    def test_start_conversation_caches_loop_and_opening(self):
        from uuid import uuid4

        card = {"id": "char-1", "name": "Maeve", "first_message": "Well met."}
        fake_loop = SimpleNamespace(state=SimpleNamespace(conversation_id="conv-1"))
        entity_id, universe_id = str(uuid4()), str(uuid4())

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={"entity_id": entity_id, "universe_id": universe_id}
                ),
            ),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ),
        ):
            out = asyncio.run(cc.start_conversation("char-1"))

        assert out["conversation_id"] == "conv-1"
        assert out["opening"] == "Well met."
        assert cc.get_loop("conv-1") is fake_loop

    def test_send_message_maps_reply_fields(self):
        fake_loop = MagicMock()
        fake_loop.step = AsyncMock(
            return_value=[
                {
                    "text": "We don't get trouble here.",
                    "emotional_state": "guarded",
                    "relationship_snapshot": {"stance": "guarded", "trust": -0.1},
                }
            ]
        )
        cc._cache_loop("conv-2", fake_loop)

        reply = asyncio.run(cc.send_message("conv-2", "hi"))
        assert reply["text"] == "We don't get trouble here."
        assert reply["emotional_state"] == "guarded"
        assert reply["relationship_snapshot"]["stance"] == "guarded"

    def test_send_message_missing_loop_raises_keyerror(self):
        with pytest.raises(KeyError):
            asyncio.run(cc.send_message("does-not-exist", "hi"))

    def test_end_conversation_finishes_and_evicts(self):
        fake_loop = MagicMock()
        fake_loop.finish = AsyncMock(return_value=[{"change_type": "fact"}])
        cc._cache_loop("conv-3", fake_loop)

        out = asyncio.run(cc.end_conversation("conv-3"))
        assert out == {"ended": True, "proposals": 1}
        assert cc.get_loop("conv-3") is None

    def test_end_conversation_unknown_is_noop(self):
        out = asyncio.run(cc.end_conversation("ghost"))
        assert out == {"ended": True, "proposals": 0}


# ---------------------------------------------------------------------------
# list_conversations
# ---------------------------------------------------------------------------


class TestListConversations:
    def test_maps_mongo_docs(self):
        from datetime import datetime, timezone

        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        docs = [
            {
                "conversation_id": "c1",
                "status": "completed",
                "turns": [{}, {}],
                "created_at": now,
                "updated_at": now,
            }
        ]

        cursor = MagicMock()
        cursor.sort.return_value = cursor
        cursor.limit.return_value = docs
        coll = MagicMock()
        coll.find.return_value = cursor
        client = MagicMock()
        client.get_collection.return_value = coll

        with patch("monitor_data.db.mongodb.get_mongodb_client", return_value=client):
            out = cc.list_conversations("ent-1", limit=10)

        assert len(out) == 1
        assert out[0]["conversation_id"] == "c1"
        assert out[0]["turn_count"] == 2
        coll.find.assert_called_once_with({"npc_ids": "ent-1"})
