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
                cc, "ensure_conversatory_universe", new=AsyncMock(return_value="uni-conv")
            ),
            patch(
                "monitor_agents.prompts.npc_profile_gen.NPCProfileGenerator",
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
                "monitor_agents.prompts.npc_profile_gen.NPCProfileGenerator",
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
                "monitor_agents.prompts.npc_profile_gen.NPCProfileGenerator",
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
        assert (
            mock_start.await_args.kwargs["player_entity_id"] == cc._CONVERSATORY_PLAYER_ID
        )
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
                "monitor_agents.prompts.card_draft.CardDrafter",
                return_value=fake_drafter,
            ),
            patch.object(cc.asyncio, "to_thread", new=AsyncMock(side_effect=lambda f, *a, **k: f(*a, **k))),
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
                    cc, "ensure_conversatory_universe", new=AsyncMock(return_value="uni-conv")
                ),
                patch(
                    "monitor_agents.prompts.npc_profile_gen.NPCProfileGenerator",
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
        fake_loop.step = AsyncMock(return_value=[{"text": "ok", "emotional_state": "neutral",
                                                   "relationship_snapshot": {}}])
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

    def test_draft_card_propagates_errors(self):
        # If the underlying generator raises, draft_card must surface it.
        with patch(
            "monitor_agents.prompts.card_draft.CardDrafter",
            return_value=MagicMock(forward=MagicMock(side_effect=RuntimeError("no LLM"))),
        ):
            with pytest.raises(RuntimeError, match="no LLM"):
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
        with patch("monitor_agents.prompts.card_draft.CardDrafter", return_value=fake):
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
            patch.object(
                cc, "ensure_conversatory_universe", new=AsyncMock(return_value=uni_b)
            ),
            patch(
                "monitor_agents.prompts.npc_profile_gen.NPCProfileGenerator",
                return_value=fake_gen,
            ),
            patch.object(cc, "_provision_entity_and_profile", return_value=eid_b),
            patch.object(cc, "add_version", return_value={"version_id": "vb"}),
        ):
            out = asyncio.run(
                cc.ensure_character_backed("char-iso", universe_id=uni_b)
            )

        # Distinct entity + version per universe.
        assert out["entity_id"] != eid_a
        assert out["universe_id"] == uni_b
        assert out["version_id"] == "vb"

    def test_send_message_propagates_cross_incarnation_flag(self):
        from uuid import uuid4

        fake_loop = MagicMock()
        fake_loop.state = SimpleNamespace(
            conversation_id=uuid4(), universe_id=str(uuid4())
        )
        fake_loop.step = AsyncMock(return_value=[{"text": "x", "emotional_state": "ok"}])
        cc._cache_loop("conv-cross", fake_loop)

        with patch.object(cc, "asyncio") as mock_asyncio:
            mock_asyncio.to_thread = MagicMock()  # not used in send_message

            async def _go():
                return await cc.send_message(
                    "conv-cross", "hi", include_cross_incarnation=True
                )

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
