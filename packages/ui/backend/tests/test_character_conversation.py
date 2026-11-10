"""
Unit tests for the character conversatory service (character_conversation.py).

No live DB / LM / ConversationLoop — all collaborators are mocked. Async
functions are driven with asyncio.run() since the backend test suite does not
enable pytest-asyncio auto mode.
"""

from __future__ import annotations

import asyncio
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_ui.routers import character_conversation as cc

pytestmark = pytest.mark.usefixtures("local_auth_mode")

# ---------------------------------------------------------------------------
# ensure_character_backed
# ---------------------------------------------------------------------------


class TestEnsureCharacterBacked:
    def test_returns_existing_version_without_provisioning(self):
        card = {
            "id": "char-1",
            "name": "Maeve",
            "entity_id": "ent-1",
            "source_universe_id": "uni-1",
            "versions": [
                {
                    "version_id": "v1",
                    "universe_id": "uni-1",
                    "entity_id": "ent-1",
                    "npc_profile_id": None,
                    "created_at": "2026-01-01T00:00:00",
                    "last_chatted_at": None,
                }
            ],
        }
        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "_provision_entity_and_profile") as mock_provision,
        ):
            out = asyncio.run(cc.ensure_character_backed("char-1"))

        assert out["entity_id"] == "ent-1"
        assert out["universe_id"] == "uni-1"
        assert out["version_id"] == "v1"
        mock_provision.assert_not_called()

    def test_legacy_backing_promoted_to_default_version(self):
        """A character backed before versions existed gets one on first call."""
        card = {
            "id": "char-2",
            "name": "Maeve",
            "entity_id": "ent-old",
            "source_universe_id": "uni-1",
            "versions": [],
        }
        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "_provision_entity_and_profile") as mock_provision,
            patch.object(cc, "add_version", return_value={"version_id": "v-new"}),
        ):
            out = asyncio.run(cc.ensure_character_backed("char-2"))

        # Reuses the legacy entity id; no fresh provisioning.
        assert out["entity_id"] == "ent-old"
        assert out["universe_id"] == "uni-1"
        assert out["version_id"] == "v-new"
        mock_provision.assert_not_called()

    def test_expands_light_card_and_provisions_new_version(self):
        card = {"id": "char-3", "name": "Maeve", "versions": []}

        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"traits": {"wariness": 0.8}, "triggers": []}

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(
                cc,
                "ensure_conversatory_universe",
                new=AsyncMock(return_value="uni-conv"),
            ),
            patch(
                "monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value="ent-new"),
            patch.object(cc, "add_version", return_value={"version_id": "v3"}),
        ):
            out = asyncio.run(cc.ensure_character_backed("char-3"))

        assert out["entity_id"] == "ent-new"
        assert out["universe_id"] == "uni-conv"
        assert out["version_id"] == "v3"
        fake_gen.forward.assert_called_once()

    def test_per_universe_incarnation_returns_distinct_entity(self):
        """A character expanded in two universes has two incarnations."""
        from uuid import uuid4

        eid_a, eid_b, uni_a, uni_b = (str(uuid4()) for _ in range(4))
        card = {
            "id": "char-4",
            "name": "Maeve",
            "versions": [
                {
                    "version_id": "va",
                    "universe_id": uni_a,
                    "entity_id": eid_a,
                    "npc_profile_id": None,
                    "created_at": "2026-01-01T00:00:00",
                    "last_chatted_at": None,
                }
            ],
        }
        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"triggers": []}

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "ensure_conversatory_universe", new=AsyncMock(return_value=uni_b)),
            patch(
                "monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value=eid_b),
            patch.object(cc, "add_version", return_value={"version_id": "vb"}),
        ):
            out = asyncio.run(cc.ensure_character_backed("char-4", universe_id=uni_b))

        assert out["entity_id"] == eid_b
        assert out["universe_id"] == uni_b
        assert out["version_id"] == "vb"

    def test_uses_linked_universe_when_present(self):
        card = {
            "id": "char-5",
            "name": "Aldric",
            "versions": [],
            "source_universe_id": "uni-real",
        }
        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"triggers": []}

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "ensure_conversatory_universe", new=AsyncMock()) as mock_conv,
            patch(
                "monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value="ent-x") as prov,
            patch.object(cc, "add_version", return_value={"version_id": "vx"}),
        ):
            out = asyncio.run(cc.ensure_character_backed("char-5"))

        assert out["universe_id"] == "uni-real"
        mock_conv.assert_not_awaited()  # linked universe short-circuits the host lookup
        assert prov.call_args[0][0] == "uni-real"

    def test_missing_character_raises(self):
        with patch.object(cc, "get_character", return_value=None), pytest.raises(ValueError):
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
        entity_id, universe_id, version_id = str(uuid4()), str(uuid4()), str(uuid4())

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={
                        "entity_id": entity_id,
                        "universe_id": universe_id,
                        "version_id": version_id,
                    }
                ),
            ),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ) as mock_start,
        ):
            out = asyncio.run(cc.start_conversation("char-1"))

        assert out["conversation_id"] == "conv-1"
        assert out["opening"] == "Well met."
        assert out["version_id"] == version_id
        assert out["universe_id"] == universe_id
        assert cc.get_loop("conv-1") is fake_loop
        # Player sentinel is passed so NPCVoice can accumulate relationship deltas
        # across conversatory sessions (otherwise no relationship is tracked).
        assert mock_start.await_args.kwargs["player_entity_id"] == cc._CONVERSATORY_PLAYER_ID
        assert mock_start.await_args.kwargs["mode"].value == "direct"

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

    def test_send_message_resumes_from_transcript_when_loop_missing(self):
        """A loop orphaned by a backend restart is rebuilt from the persisted
        MongoDB transcript instead of failing with a 409."""
        from uuid import uuid4

        entity_id, universe_id = str(uuid4()), str(uuid4())
        conv_id = str(uuid4())
        doc = {
            "conversation_id": conv_id,
            "status": "active",
            "universe_id": universe_id,
            "npc_ids": [entity_id],
            "player_entity_id": str(cc._CONVERSATORY_PLAYER_ID),
            "turns": [
                {"turn_index": 0, "speaker_role": "player", "entity_name": "Player", "text": "hi"},
                {"turn_index": 1, "speaker_role": "npc", "entity_name": "Maeve", "text": "well met"},
            ],
        }
        mongo = MagicMock()
        mongo.get_collection.return_value.find_one.return_value = doc

        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(turns=[], turns_count=0)
        fake_loop.step = AsyncMock(return_value=[{"text": "we meet again", "emotional_state": "warm"}])

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={"entity_id": entity_id, "universe_id": universe_id, "version_id": str(uuid4())}
                ),
            ),
            patch("monitor_agents.loops.conversation_loop.ConversationLoop", return_value=fake_loop),
            patch("monitor_agents.loops.conversation_loop.load_npc_context", new=AsyncMock(return_value={})),
        ):
            reply = asyncio.run(cc.send_message(conv_id, "remember me?", character_id="char-1"))

        assert reply["text"] == "we meet again"
        # Transcript turns were restored before stepping, and the loop cached.
        # turns_count counts completed player exchanges (1 player line), not len(turns) (2).
        assert [t["text"] for t in fake_loop.state.turns] == ["hi", "well met"]
        assert fake_loop.state.turns_count == 1
        assert cc.get_loop(conv_id) is fake_loop

    def test_resume_rejects_other_incarnation(self):
        """A conversation belonging to a different incarnation is not resumed."""
        from uuid import uuid4

        doc = {
            "conversation_id": "conv-other",
            "status": "active",
            "universe_id": str(uuid4()),
            "npc_ids": [str(uuid4())],  # different entity
            "turns": [],
        }
        mongo = MagicMock()
        mongo.get_collection.return_value.find_one.return_value = doc

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={
                        "entity_id": str(uuid4()),
                        "universe_id": str(uuid4()),
                        "version_id": str(uuid4()),
                    }
                ),
            ),
        ):
            loop = asyncio.run(cc.resume_conversation("char-1", "conv-other"))

        assert loop is None
        assert cc.get_loop("conv-other") is None

    def test_resume_rejects_ended_conversation(self):
        mongo = MagicMock()
        mongo.get_collection.return_value.find_one.return_value = {
            "conversation_id": "conv-done",
            "status": "completed",
        }

        with patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo):
            loop = asyncio.run(cc.resume_conversation("char-1", "conv-done"))

        assert loop is None

    def test_send_message_persists_proposal_outbox(self):
        """After every turn, accumulated proposals are written onto the
        conversation doc so a mid-session crash can't lose them."""
        fake_loop = MagicMock()
        fake_loop.state.pending_proposals = [{"change_type": "relationship", "content": {}}]
        fake_loop.step = AsyncMock(return_value=[{"text": "aye", "emotional_state": "warm"}])
        cc._cache_loop("conv-outbox", fake_loop)
        mongo = MagicMock()

        with patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo):
            asyncio.run(cc.send_message("conv-outbox", "hi"))

        update = mongo.get_collection.return_value.update_one
        update.assert_called_once()
        args = update.call_args[0]
        assert args[0] == {"conversation_id": "conv-outbox"}
        assert args[1]["$set"]["pending_proposals"] == [{"change_type": "relationship", "content": {}}]

    def test_resume_restores_pending_proposals(self):
        from uuid import uuid4

        entity_id, universe_id, conv_id = str(uuid4()), str(uuid4()), str(uuid4())
        outbox = [{"change_type": "state_change", "content": {"mood": "wary"}}]
        doc = {
            "conversation_id": conv_id,
            "status": "active",
            "universe_id": universe_id,
            "npc_ids": [entity_id],
            "player_entity_id": str(cc._CONVERSATORY_PLAYER_ID),
            "turns": [],
            "pending_proposals": outbox,
        }
        mongo = MagicMock()
        mongo.get_collection.return_value.find_one.return_value = doc

        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(turns=[], turns_count=0, pending_proposals=[])

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={"entity_id": entity_id, "universe_id": universe_id, "version_id": str(uuid4())}
                ),
            ),
            patch("monitor_agents.loops.conversation_loop.ConversationLoop", return_value=fake_loop),
            patch("monitor_agents.loops.conversation_loop.load_npc_context", new=AsyncMock(return_value={})),
        ):
            loop = asyncio.run(cc.resume_conversation("char-1", conv_id))

        assert loop.state.pending_proposals == outbox


class TestRedistillConversation:
    def setup_method(self):
        cc._LOOPS.clear()

    def _doc(self, entity_id: str, universe_id: str, conv_id: str) -> dict:
        return {
            "conversation_id": conv_id,
            "status": "completed",
            "universe_id": universe_id,
            "npc_ids": [entity_id],
            "turns": [
                {"turn_index": 0, "speaker_role": "player", "text": "hi"},
                {"turn_index": 1, "speaker_role": "npc", "text": "well met"},
            ],
        }

    def test_redistill_is_idempotent_when_proposals_exist(self):
        from uuid import uuid4

        entity_id, universe_id, conv_id = str(uuid4()), str(uuid4()), str(uuid4())
        mongo = MagicMock()
        coll = mongo.get_collection.return_value
        coll.find_one.return_value = self._doc(entity_id, universe_id, conv_id)
        coll.find.return_value = [{"content": {"description": "Kessa accepted the helm."}, "status": "pending"}]

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={"entity_id": entity_id, "universe_id": universe_id, "version_id": str(uuid4())}
                ),
            ),
            patch(
                "monitor_agents.loops.conversation_loop.redistill_episodic_proposals",
                new=AsyncMock(return_value=[]),
            ) as mock_redistill,
        ):
            out = asyncio.run(cc.redistill_conversation("char-1", conv_id))

        assert out["staged"] == 0
        assert out["existing"] == 1
        assert out["descriptions"] == ["Kessa accepted the helm."]
        mock_redistill.assert_not_awaited()

    def test_redistill_force_restages(self):
        from uuid import uuid4

        entity_id, universe_id, conv_id = str(uuid4()), str(uuid4()), str(uuid4())
        mongo = MagicMock()
        coll = mongo.get_collection.return_value
        coll.find_one.return_value = self._doc(entity_id, universe_id, conv_id)
        coll.find.return_value = []

        staged = [{"change_type": "event", "content": {"description": "New take."}}]
        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={"entity_id": entity_id, "universe_id": universe_id, "version_id": str(uuid4())}
                ),
            ),
            patch(
                "monitor_agents.loops.conversation_loop.redistill_episodic_proposals",
                new=AsyncMock(return_value=staged),
            ) as mock_redistill,
        ):
            out = asyncio.run(cc.redistill_conversation("char-1", conv_id, force=True))

        assert out["staged"] == 1
        assert out["descriptions"] == ["New take."]
        mock_redistill.assert_awaited_once()

    def test_redistill_unknown_conversation_raises(self):
        mongo = MagicMock()
        mongo.get_collection.return_value.find_one.return_value = None

        with patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo):
            with pytest.raises(KeyError):
                asyncio.run(cc.redistill_conversation("char-1", "nope"))


# ---------------------------------------------------------------------------
# draft_card (LLM-assisted card filling)
# ---------------------------------------------------------------------------


class TestDraftCard:
    def test_returns_drafter_dict(self):
        fake_drafter = MagicMock()
        fake_drafter.forward.return_value = {
            "name": "Maeve",
            "description": "wary",
            "personality": "dry",
            "first_message": "Well met.",
            "gm_notes": "hidden past",
        }
        with (
            patch(
                "monitor_agents.character_creator.card_draft.CardDrafter",
                return_value=fake_drafter,
            ),
            patch.object(
                cc.asyncio,
                "to_thread",
                new=AsyncMock(side_effect=lambda f, *a, **k: f(*a, **k)),
            ),
        ):
            out = asyncio.run(cc.draft_card(concept="a wary tavern keeper"))

        assert out["name"] == "Maeve"
        assert out["first_message"] == "Well met."

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
        from datetime import datetime

        now = datetime(2026, 1, 1, tzinfo=UTC)
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


# ---------------------------------------------------------------------------
# Concurrency + edge cases
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_expand_same_character_documents_idempotency(self):
        """Two concurrent ensure_character_backed() on the same card must both
        succeed. Without a DB-level uniqueness constraint on versions[],
        concurrent calls can produce two incarnations — pin the contract
        (both succeed) without over-asserting perfect idempotency.
        """
        card = {"id": "char-cc", "name": "Twin", "entity_id": None, "versions": []}
        provision_count = {"n": 0}

        def slow_provision(universe_id, ch, fields):
            provision_count["n"] += 1
            return f"ent-{provision_count['n']}"

        call_count = {"n": 0}

        def fake_add_version(char_id, universe_id, entity_id, npc_profile_id=None):
            call_count["n"] += 1
            v = {
                "version_id": f"v{call_count['n']}",
                "universe_id": universe_id,
                "entity_id": entity_id,
                "npc_profile_id": npc_profile_id,
                "created_at": "2026-01-01T00:00:00",
                "last_chatted_at": None,
            }
            card["versions"] = list(card.get("versions", [])) + [v]
            return v

        async def driver():
            with (
                patch.object(cc, "get_character", return_value=card),
                patch.object(
                    cc,
                    "ensure_conversatory_universe",
                    new=AsyncMock(return_value="uni-conv"),
                ),
                patch(
                    "monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator",
                    return_value=MagicMock(forward=MagicMock(return_value={"triggers": []})),
                ),
                patch.object(cc, "_provision_entity_and_profile", side_effect=slow_provision),
                patch.object(cc, "add_version", side_effect=fake_add_version),
            ):
                return await asyncio.gather(
                    cc.ensure_character_backed("char-cc"),
                    cc.ensure_character_backed("char-cc"),
                )

        results = asyncio.run(driver())
        assert len(results) == 2
        # Both calls returned a valid incarnation in the conversatory universe.
        for r in results:
            assert r["universe_id"] == "uni-conv"
            assert r["entity_id"]
            assert r["version_id"]
        # Pin the behavior: 1 (perfect idempotency) or 2 (race) provisions.
        # The race is real because ensure_character_backed reads-then-writes
        # versions[] without a uniqueness constraint. Fixing it requires a
        # DB-level guarantee; until then the contract is "both succeed".
        assert provision_count["n"] in (1, 2)


class TestEdgeCases:
    def test_send_message_returns_text_when_response_empty(self):
        fake_loop = MagicMock()
        fake_loop.step = AsyncMock(return_value=[])
        cc._cache_loop("conv-empty", fake_loop)
        reply = asyncio.run(cc.send_message("conv-empty", "hi"))
        assert reply == {
            "text": "",
            "emotional_state": None,
            "relationship_snapshot": {},
        }

    def test_send_message_missing_input_does_not_corrupt_cache(self):
        fake_loop = MagicMock()
        fake_loop.step = AsyncMock(
            return_value=[
                {
                    "text": "ok",
                    "emotional_state": "neutral",
                    "relationship_snapshot": {},
                }
            ]
        )
        cc._cache_loop("conv-x", fake_loop)
        asyncio.run(cc.send_message("conv-x", ""))
        # Cache still has the loop — send_message does not evict.
        assert cc.get_loop("conv-x") is fake_loop

    def test_end_conversation_evicts_even_when_finish_raises(self):
        fake_loop = MagicMock()
        fake_loop.finish = AsyncMock(side_effect=RuntimeError("boom"))
        cc._cache_loop("conv-boom", fake_loop)
        out = asyncio.run(cc.end_conversation("conv-boom"))
        # Evicted despite the error — caller sees ended=False.
        assert out == {"ended": False, "proposals": 0}
        assert cc.get_loop("conv-boom") is None

    def test_list_conversations_empty_when_entity_id_missing(self):
        # Entity-less character: no entity_id, list returns [].
        with patch.object(cc, "get_character", return_value=None):
            # The list endpoint guards on the router side, but the service
            # function is tolerant: empty result if no entity_id.
            out = cc.list_conversations(None, limit=5)  # type: ignore[arg-type]
        assert out == []

    def test_loop_cache_evicts_oldest_when_full(self):
        # Pin the production cap to its real value (64). A mutation like
        # "_LOOPS_MAX = 1" would shrink the cache so far that nothing useful
        # is retained — this assertion catches it.
        assert cc._LOOPS_MAX == 64
        cap = cc._LOOPS_MAX
        try:
            for i in range(cap + 5):
                cc._cache_loop(f"id-{i}", MagicMock())
            # The cache size must be EXACTLY the cap — not "<=cap" — so the LRU
            # eviction is actually exercised.
            assert len(cc._LOOPS) == cap
            # Oldest entries gone.
            assert cc.get_loop("id-0") is None
            # Newest still present.
            assert cc.get_loop(f"id-{cap + 4}") is not None
            assert cc.get_loop(f"id-{cc._LOOPS_MAX + 4}") is not None
        finally:
            # Always restore the cap so other tests see the production value.
            cc._LOOPS_MAX = cap
            cc._LOOPS.clear()

    def test_draft_card_propagates_errors(self):
        # If the underlying generator raises, draft_card must surface it.
        with (
            patch(
                "monitor_agents.character_creator.card_draft.CardDrafter",
                return_value=MagicMock(forward=MagicMock(side_effect=RuntimeError("no LLM"))),
            ),
            pytest.raises(RuntimeError, match="no LLM"),
        ):
            asyncio.run(cc.draft_card("a tavern keeper"))

    def test_draft_card_returns_string_fields(self):
        fake = MagicMock(
            forward=MagicMock(
                return_value={
                    "name": "Lin",
                    "description": "d",
                    "personality": "p",
                    "first_message": "f",
                    "gm_notes": "g",
                }
            )
        )
        with patch("monitor_agents.character_creator.card_draft.CardDrafter", return_value=fake):
            out = asyncio.run(cc.draft_card("x"))
        assert out["name"] == "Lin"
        assert all(isinstance(v, str) for v in out.values())


# ---------------------------------------------------------------------------
# Character Versions — per-universe isolation contract
# ---------------------------------------------------------------------------


class TestVersionIsolation:
    """The leak fix contract: same character, two universes, no cross-talk."""

    def test_two_universes_get_distinct_incarnations(self):
        from uuid import uuid4

        eid_a, eid_b, uni_a, uni_b = (str(uuid4()) for _ in range(4))
        card = {
            "id": "char-iso",
            "name": "Maeve",
            "versions": [
                {
                    "version_id": "va",
                    "universe_id": uni_a,
                    "entity_id": eid_a,
                    "npc_profile_id": None,
                    "created_at": "2026-01-01T00:00:00",
                    "last_chatted_at": None,
                }
            ],
        }
        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"triggers": []}

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "ensure_conversatory_universe", new=AsyncMock(return_value=uni_b)),
            patch(
                "monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value=eid_b),
            patch.object(cc, "add_version", return_value={"version_id": "vb"}),
        ):
            out = asyncio.run(cc.ensure_character_backed("char-iso", universe_id=uni_b))

        # Distinct entity + version per universe.
        assert out["entity_id"] != eid_a
        assert out["universe_id"] == uni_b
        assert out["version_id"] == "vb"

    def test_send_message_propagates_cross_incarnation_flag(self):
        from uuid import uuid4

        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(conversation_id=uuid4(), universe_id=str(uuid4()))
        fake_loop.step = AsyncMock(return_value=[{"text": "x", "emotional_state": "ok"}])
        cc._cache_loop("conv-cross", fake_loop)

        with patch.object(cc, "asyncio") as mock_asyncio:
            mock_asyncio.to_thread = MagicMock()  # not used in send_message

            async def _go():
                return await cc.send_message("conv-cross", "hi", include_cross_incarnation=True)

            out = asyncio.run(_go())

        # Flag was set on the loop state before the step and reset after.
        assert out["text"] == "x"
        # State attribute should be reset to False so subsequent steps default strict.
        assert fake_loop.state.include_cross_incarnation is False
        # Step was called once with the player text.
        fake_loop.step.assert_awaited_once_with("hi")

    def test_delete_incarnation_calls_neo4j_and_storage_cleanup(self):
        from uuid import uuid4

        uni = str(uuid4())
        ent = str(uuid4())
        version = {
            "version_id": "vdel",
            "universe_id": uni,
            "entity_id": ent,
            "npc_profile_id": None,
            "created_at": "2026-01-01T00:00:00",
            "last_chatted_at": None,
        }

        with (
            patch.object(cc, "get_version", return_value=version),
            patch(
                "monitor_data.tools.neo4j_tools.entities.neo4j_delete_entity",
                MagicMock(),
            ) as mock_delete,
            patch(
                "monitor_data.db.mongodb.get_mongodb_client",
                MagicMock(get_collection=MagicMock(return_value=MagicMock())),
            ),
            patch.object(cc, "delete_version", return_value=version) as mock_dv,
        ):
            ok = asyncio.run(cc.delete_incarnation("char-x", uni))

        assert ok is True
        mock_delete.assert_called_once()
        mock_dv.assert_called_once_with("char-x", uni)


# ---------------------------------------------------------------------------
# Card macros ({{user}}/{{char}})
# ---------------------------------------------------------------------------


class TestCardMacros:
    def test_provisioning_substitutes_macros(self):
        """Imported card text reaches the profile generator macro-resolved."""
        card = {
            "id": "char-mac",
            "name": "Elara",
            "versions": [],
            "description": "{{char}} is a ranger who watches {{user}}.",
            "personality": "Wary of {{user}}.",
            "gm_notes": "Never let {{user}} see the map.",
        }
        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"triggers": []}

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(
                cc,
                "ensure_conversatory_universe",
                new=AsyncMock(return_value="uni-conv"),
            ),
            patch(
                "monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value="ent-new") as prov,
            patch.object(cc, "add_version", return_value={"version_id": "vm"}),
        ):
            asyncio.run(cc.ensure_character_backed("char-mac"))

        args = fake_gen.forward.call_args[0]
        assert args[1] == "Elara is a ranger who watches User."
        assert args[2] == "Wary of User."
        assert args[3] == "Never let User see the map."
        rendered_char = prov.call_args[0][1]
        assert rendered_char["description"] == "Elara is a ranger who watches User."
        # Stored card must stay raw (lossless export round-trip).
        assert card["description"] == "{{char}} is a ranger who watches {{user}}."

    def test_opening_substitutes_macros(self):
        from uuid import uuid4

        card = {
            "id": "char-1",
            "name": "Maeve",
            "first_message": "{{char}} sizes up {{user}} and nods.",
        }
        fake_loop = SimpleNamespace(state=SimpleNamespace(conversation_id="conv-mac"))

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={
                        "entity_id": str(uuid4()),
                        "universe_id": str(uuid4()),
                        "version_id": str(uuid4()),
                    }
                ),
            ),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ),
        ):
            out = asyncio.run(cc.start_conversation("char-1"))

        assert out["opening"] == "Maeve sizes up User and nods."

    def test_persona_binds_user_name(self):
        from uuid import uuid4

        card = {
            "id": "char-1",
            "name": "Maeve",
            "first_message": "{{char}} eyes {{user}} warily.",
        }
        persona = {"id": "persona-1", "name": "Kael", "is_ooc_persona": True}
        fake_loop = SimpleNamespace(state=SimpleNamespace(conversation_id="conv-p"))

        def _get(cid):
            return {"char-1": card, "persona-1": persona}.get(cid)

        with (
            patch.object(cc, "get_character", side_effect=_get),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={
                        "entity_id": str(uuid4()),
                        "universe_id": str(uuid4()),
                        "version_id": str(uuid4()),
                    }
                ),
            ) as mock_backed,
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ),
        ):
            out = asyncio.run(cc.start_conversation("char-1", persona_character_id="persona-1"))

        assert out["opening"] == "Maeve eyes Kael warily."
        assert mock_backed.await_args.kwargs["user_name"] == "Kael"

    def test_non_persona_card_rejected(self):
        card = {"id": "char-1", "name": "Maeve"}
        not_persona = {"id": "char-2", "name": "Aldric", "is_ooc_persona": False}

        def _get(cid):
            return {"char-1": card, "char-2": not_persona}.get(cid)

        with patch.object(cc, "get_character", side_effect=_get), pytest.raises(ValueError, match="not a persona"):
            asyncio.run(cc.start_conversation("char-1", persona_character_id="char-2"))

    def test_missing_persona_rejected(self):
        with patch.object(cc, "get_character", return_value=None), pytest.raises(ValueError):
            asyncio.run(cc.start_conversation("char-1", persona_character_id="ghost"))

    def test_provisioning_keeps_the_shared_profile_persona_neutral(self):
        """The profile is shared by every conversation with this incarnation, so the
        first persona's name must not be baked into it; each conversation's
        character_card carries its own persona instead."""
        card = {
            "id": "char-pn",
            "name": "Elara",
            "versions": [],
            "description": "{{char}} watches {{user}}.",
        }
        fake_gen = MagicMock()
        fake_gen.forward.return_value = {"triggers": []}

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(
                cc,
                "ensure_conversatory_universe",
                new=AsyncMock(return_value="uni-conv"),
            ),
            patch(
                "monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value="ent-new"),
            patch.object(cc, "add_version", return_value={"version_id": "vp"}),
        ):
            asyncio.run(cc.ensure_character_backed("char-pn", user_name="Kael"))

        assert fake_gen.forward.call_args[0][1] == "Elara watches User."

    def test_persona_threaded_to_loop_and_persisted(self):
        from uuid import uuid4

        card = {"id": "char-1", "name": "Maeve", "first_message": "Hi."}
        persona = {
            "id": "persona-1",
            "name": "Kael",
            "is_ooc_persona": True,
            "description": "a wandering sellsword",
        }
        fake_loop = SimpleNamespace(state=SimpleNamespace(conversation_id="conv-pt"))
        mongo = MagicMock()

        def _get(cid):
            return {"char-1": card, "persona-1": persona}.get(cid)

        with (
            patch.object(cc, "get_character", side_effect=_get),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={
                        "entity_id": str(uuid4()),
                        "universe_id": str(uuid4()),
                        "version_id": str(uuid4()),
                    }
                ),
            ),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ) as mock_start,
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        ):
            asyncio.run(cc.start_conversation("char-1", persona_character_id="persona-1"))

        assert mock_start.await_args.kwargs["player_persona"] == "Kael — a wandering sellsword"
        assert any(
            c.args[0] == {"conversation_id": "conv-pt"}
            and c.args[1] == {"$set": {"player_persona": "Kael — a wandering sellsword"}}
            for c in mongo.get_collection.return_value.update_one.call_args_list
        )

    def test_no_persona_skips_persistence(self):
        from uuid import uuid4

        card = {"id": "char-1", "name": "Maeve", "first_message": "Hi."}
        fake_loop = SimpleNamespace(state=SimpleNamespace(conversation_id="conv-np"))
        mongo = MagicMock()

        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={
                        "entity_id": str(uuid4()),
                        "universe_id": str(uuid4()),
                        "version_id": str(uuid4()),
                    }
                ),
            ),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ) as mock_start,
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        ):
            asyncio.run(cc.start_conversation("char-1"))

        assert mock_start.await_args.kwargs["player_persona"] is None
        assert not any(
            "player_persona" in ((c.args[1] if len(c.args) > 1 else {}).get("$set") or {})
            for c in mongo.get_collection.return_value.update_one.call_args_list
        )

    def test_resume_restores_persona(self):
        from uuid import uuid4

        entity_id, universe_id = str(uuid4()), str(uuid4())
        conv_id = str(uuid4())
        doc = {
            "conversation_id": conv_id,
            "status": "active",
            "universe_id": universe_id,
            "npc_ids": [entity_id],
            "player_persona": "Kael — a wandering sellsword",
            "turns": [],
        }
        mongo = MagicMock()
        mongo.get_collection.return_value.find_one.return_value = doc

        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(turns=[], turns_count=0)

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch.object(
                cc,
                "ensure_character_backed",
                new=AsyncMock(
                    return_value={
                        "entity_id": entity_id,
                        "universe_id": universe_id,
                        "version_id": str(uuid4()),
                    }
                ),
            ),
            patch("monitor_agents.loops.conversation_loop.ConversationLoop", return_value=fake_loop),
            patch(
                "monitor_agents.loops.conversation_loop.load_npc_context",
                new=AsyncMock(return_value={}),
            ),
        ):
            loop = asyncio.run(cc.resume_conversation("char-1", conv_id))

        assert loop.state.player_persona == "Kael — a wandering sellsword"


# ---------------------------------------------------------------------------
# Imported card content in conversations
# ---------------------------------------------------------------------------

_CARD = {
    "id": "char-1",
    "name": "Maeve",
    "description": "{{char}} keeps the inn.",
    "personality": "Dry, watchful.",
    "gm_notes": "A storm traps {{user}} at the inn.",
    "first_message": "Evening, {{user}}.",
}


def _started(**extra):
    from uuid import uuid4

    fake_loop = SimpleNamespace(
        state=SimpleNamespace(conversation_id="conv-card"),
        add_opening=AsyncMock(),
    )
    backing = {"entity_id": str(uuid4()), "universe_id": str(uuid4()), "version_id": str(uuid4())}
    return fake_loop, backing


class TestCardContent:
    def test_card_is_rendered_for_this_conversations_persona(self):
        text = cc.render_character_card(_CARD, "Kael")
        assert "Maeve keeps the inn." in text
        assert "Dry, watchful." in text
        assert "A storm traps Kael at the inn." in text
        assert "{{" not in text

    def test_empty_card_renders_nothing(self):
        assert cc.render_character_card({"name": "Maeve"}, None) == ""

    def test_start_passes_the_card_and_records_the_greeting(self):
        fake_loop, backing = _started()
        persona = {"name": "Kael", "is_ooc_persona": True}
        cards = {"char-1": _CARD, "persona-1": persona}
        with (
            patch.object(cc, "get_character", side_effect=cards.get),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=backing)),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ) as start,
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=MagicMock()),
        ):
            out = asyncio.run(cc.start_conversation("char-1", persona_character_id="persona-1"))

        assert "A storm traps Kael at the inn." in start.await_args.kwargs["character_card"]
        fake_loop.add_opening.assert_awaited_once_with("Evening, Kael.")
        assert out["opening"] == "Evening, Kael."

    def test_generated_fallback_opening_is_not_recorded_as_speech(self):
        fake_loop, backing = _started()
        with (
            patch.object(cc, "get_character", return_value={"id": "char-1", "name": "Maeve"}),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=backing)),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ),
        ):
            asyncio.run(cc.start_conversation("char-1"))
        fake_loop.add_opening.assert_not_awaited()

    def test_greeting_failure_does_not_stop_the_chat(self):
        fake_loop, backing = _started()
        fake_loop.add_opening = AsyncMock(side_effect=RuntimeError("db"))
        with (
            patch.object(cc, "get_character", return_value=_CARD),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=backing)),
            patch(
                "monitor_agents.loops.conversation_loop.ConversationLoop.start",
                new=AsyncMock(return_value=fake_loop),
            ),
        ):
            out = asyncio.run(cc.start_conversation("char-1"))
        assert out["conversation_id"] == "conv-card"

    def test_shared_profile_is_not_fixed_to_the_first_persona(self):
        card = {**_CARD, "versions": []}
        generator = MagicMock()
        generator.forward.return_value = {"triggers": []}
        with (
            patch.object(cc, "get_character", return_value=card),
            patch.object(cc, "ensure_conversatory_universe", new=AsyncMock(return_value="uni")),
            patch("monitor_agents.character_creator.npc_profile_gen.NPCProfileGenerator", return_value=generator),
            patch.object(cc, "_provision_entity_and_profile", return_value="ent"),
            patch.object(cc, "add_version", return_value={"version_id": "v"}),
        ):
            asyncio.run(cc.ensure_character_backed("char-1", user_name="Kael"))
        assert "Kael" not in str(generator.forward.call_args)

    def test_long_card_notes_fit_the_profile_limit(self):
        from uuid import uuid4

        created = {}
        with (
            patch("monitor_agents.canonkeeper.agent.CanonKeeper") as keeper,
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_npc_profile",
                side_effect=lambda params: created.setdefault("profile", params),
            ),
        ):
            keeper.return_value.create_entity = AsyncMock(return_value={"id": str(uuid4())})
            cc._provision_entity_and_profile(
                str(uuid4()),
                {"id": "char-1", "name": "Maeve", "gm_notes": "x" * 8000},
                {"triggers": []},
            )
        assert len(created["profile"].gm_notes) == 5000


def test_resume_rebuilds_the_card_with_the_conversations_persona():
    from uuid import uuid4

    entity = str(uuid4())
    doc = {
        "conversation_id": str(uuid4()),
        "status": "active",
        "universe_id": str(uuid4()),
        "npc_ids": [entity],
        "turns": [],
        "player_persona": "Kael — a wandering sellsword",
    }
    mongo = MagicMock()
    mongo.get_collection.return_value.find_one.return_value = doc
    backing = {"entity_id": entity, "universe_id": doc["universe_id"], "version_id": "v"}
    with (
        patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
        patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=backing)),
        patch.object(cc, "get_character", return_value=_CARD),
        patch("monitor_agents.loops.conversation_loop.load_npc_context", new=AsyncMock(return_value={})),
    ):
        loop = asyncio.run(cc.resume_conversation("char-1", doc["conversation_id"]))

    assert "A storm traps Kael at the inn." in loop.state.character_card


class TestLightRPHardening:
    def setup_method(self):
        cc._LOOPS.clear()
        cc._LOCKS.clear()

    def test_cross_incarnation_flag_resets_when_step_raises(self):
        from uuid import uuid4

        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(
            conversation_id=uuid4(),
            universe_id=str(uuid4()),
            include_cross_incarnation=False,
        )
        fake_loop.step = AsyncMock(side_effect=RuntimeError("llm boom"))
        cc._cache_loop("conv-err", fake_loop)

        with pytest.raises(RuntimeError, match="llm boom"):
            asyncio.run(cc.send_message("conv-err", "hi", include_cross_incarnation=True))

        assert fake_loop.state.include_cross_incarnation is False

    def test_cached_loop_rejects_wrong_character_without_evicting(self):
        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(lorebook_character_ids=["char-owner"])
        fake_loop.step = AsyncMock(return_value=[{"text": "ok"}])
        cc._cache_loop("conv-owned", fake_loop)

        with pytest.raises(KeyError):
            asyncio.run(cc.send_message("conv-owned", "hi", character_id="char-intruder"))

        out = asyncio.run(cc.end_conversation("conv-owned", character_id="char-intruder"))
        assert out == {"ended": False, "proposals": 0}
        assert cc.get_loop("conv-owned", character_id="char-owner") is fake_loop

    def test_per_conversation_lock_serializes_concurrent_sends(self):
        active = {"n": 0, "max": 0}

        async def slow_step(text: str):
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
            await asyncio.sleep(0.02)
            active["n"] -= 1
            return [{"text": f"echo:{text}", "emotional_state": "calm", "relationship_snapshot": {}}]

        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(
            lorebook_character_ids=["char-1"], pending_proposals=[], lorebook_overrides={}
        )
        fake_loop._closed = False
        fake_loop.step = AsyncMock(side_effect=slow_step)
        cc._cache_loop("conv-serial", fake_loop)

        async def _run_both():
            with patch("monitor_data.db.mongodb.get_mongodb_client", return_value=MagicMock()):
                return await asyncio.gather(
                    cc.send_message("conv-serial", "first", character_id="char-1"),
                    cc.send_message("conv-serial", "second", character_id="char-1"),
                )

        replies = asyncio.run(_run_both())
        assert [r["text"] for r in replies] == ["echo:first", "echo:second"]
        assert active["max"] == 1

    def test_distinct_personas_receive_distinct_player_entity_ids(self):
        from uuid import uuid4

        card = {"id": "char-1", "name": "Maeve", "first_message": "Hi."}
        personas = {
            "char-1": card,
            "persona-a": {"id": "persona-a", "name": "Kael", "is_ooc_persona": True},
            "persona-b": {"id": "persona-b", "name": "Lyra", "is_ooc_persona": True},
        }
        backing = {"entity_id": str(uuid4()), "universe_id": str(uuid4()), "version_id": str(uuid4())}
        seen_player_ids = []

        async def fake_start(**kwargs):
            seen_player_ids.append(kwargs["player_entity_id"])
            return SimpleNamespace(
                state=SimpleNamespace(conversation_id=f"conv-{len(seen_player_ids)}"),
                add_opening=AsyncMock(),
            )

        with (
            patch.object(cc, "get_character", side_effect=personas.get),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=backing)),
            patch("monitor_agents.loops.conversation_loop.ConversationLoop.start", side_effect=fake_start),
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=MagicMock()),
        ):
            asyncio.run(cc.start_conversation("char-1", persona_character_id="persona-a"))
            asyncio.run(cc.start_conversation("char-1", persona_character_id="persona-b"))
            asyncio.run(cc.start_conversation("char-1"))

        id_a, id_b, id_none = seen_player_ids
        assert id_a != id_b
        assert id_a != cc._CONVERSATORY_PLAYER_ID
        assert id_none == cc._CONVERSATORY_PLAYER_ID

    def test_closed_loop_evicts_and_maps_to_keyerror(self):
        from monitor_agents.loops.conversation_loop import ConversationClosedError

        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(lorebook_character_ids=["char-1"])
        fake_loop.step = AsyncMock(side_effect=ConversationClosedError("done"))
        cc._cache_loop("conv-ceil", fake_loop)

        with pytest.raises(KeyError):
            asyncio.run(cc.send_message("conv-ceil", "extra", character_id="char-1"))
        assert cc.get_loop("conv-ceil") is None

    def test_end_conversation_can_resume_at_turn_limit_and_find_skips_maxed(self):
        """F1: A conversation at 100 player turns can still be resumed by end_conversation,
        while find_client_conversation skips it so Risu starts a fresh conversation."""
        from uuid import uuid4

        entity_id, universe_id = str(uuid4()), str(uuid4())
        conv_id = str(uuid4())
        turns_100 = []
        for i in range(100):
            turns_100.append({"turn_index": i * 2, "speaker_role": "player", "text": f"p{i}"})
            turns_100.append({"turn_index": i * 2 + 1, "speaker_role": "npc", "text": f"n{i}"})

        doc = {
            "conversation_id": conv_id,
            "status": "active",
            "universe_id": universe_id,
            "npc_ids": [entity_id],
            "turns": turns_100,
            "pending_proposals": [{"change_type": "fact"}],
        }
        mongo = MagicMock()
        col = mongo.get_collection.return_value
        col.find_one.return_value = doc
        col.find.return_value.sort.return_value = [doc]

        backing = {"entity_id": entity_id, "universe_id": universe_id, "version_id": "v1"}
        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(
            turns=[], turns_count=0, pending_proposals=[{"change_type": "fact"}], lorebook_character_ids=["char-1"]
        )
        fake_loop.finish = AsyncMock(return_value=[{"change_type": "fact"}])

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=backing)),
            patch("monitor_agents.loops.conversation_loop.ConversationLoop", return_value=fake_loop),
            patch("monitor_agents.loops.conversation_loop.load_npc_context", new=AsyncMock(return_value={})),
        ):
            # Regular resume_conversation rejects >= 100 player turns by returning None
            assert asyncio.run(cc.resume_conversation("char-1", conv_id)) is None
            # find_client_conversation skips maxed conversation
            assert asyncio.run(cc.find_client_conversation("char-1", None, "Evening.")) is None
            # end_conversation succeeds via allow_at_limit=True
            ended = asyncio.run(cc.end_conversation(conv_id, character_id="char-1"))
            assert ended == {"ended": True, "proposals": 1}
            fake_loop.finish.assert_awaited_once()

    def test_resume_strips_orphan_trailing_player_turns(self):
        """F11a: Trailing unanswered player turns from a failed LLM call are stripped on resume."""
        from uuid import uuid4

        entity_id, universe_id = str(uuid4()), str(uuid4())
        conv_id = str(uuid4())
        doc = {
            "conversation_id": conv_id,
            "status": "active",
            "universe_id": universe_id,
            "npc_ids": [entity_id],
            "turns": [
                {"turn_index": 0, "speaker_role": "player", "text": "Hello"},
                {"turn_index": 1, "speaker_role": "npc", "text": "Greetings."},
                {"turn_index": 2, "speaker_role": "player", "text": "Orphan failed turn"},
            ],
        }
        mongo = MagicMock()
        mongo.get_collection.return_value.find_one.return_value = doc
        backing = {"entity_id": entity_id, "universe_id": universe_id, "version_id": "v1"}
        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(turns=[], turns_count=0)

        with (
            patch("monitor_data.db.mongodb.get_mongodb_client", return_value=mongo),
            patch.object(cc, "ensure_character_backed", new=AsyncMock(return_value=backing)),
            patch("monitor_agents.loops.conversation_loop.ConversationLoop", return_value=fake_loop),
            patch("monitor_agents.loops.conversation_loop.load_npc_context", new=AsyncMock(return_value={})),
        ):
            loop = asyncio.run(cc.resume_conversation("char-1", conv_id))

        assert len(loop.state.turns) == 2
        assert loop.state.turns_count == 1
        mongo.get_collection.return_value.update_one.assert_called_once()
