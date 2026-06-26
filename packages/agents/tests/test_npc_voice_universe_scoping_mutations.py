"""
Mutation-killing tests for NPCVoice universe-scoping (Character Versions).

Each test targets one branch site in npc_voice.py that the happy-path test
file `test_npc_voice_universe_scoping.py` does NOT pin down. The contract:
a mutation like "drop the `if universe_id is not None` guard" must fail at
least one test here.

No live DB — all collaborators are mocked. The DSPy direct-voice module is
replaced with a stub returning a fixed NPCDirectResponse so the LLM is never
called.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from monitor_agents import npc_voice as nv
from monitor_agents.npc_voice import NPCDirectResponse, NPCVoice


# ---------------------------------------------------------------------------
# Fixtures + helpers (mirrors test_npc_voice_universe_scoping.py exactly)
# ---------------------------------------------------------------------------


def _prediction(
    text: str = "We don't get trouble here.",
    emotion: str = "guarded",
    delta: str = "trust:+0.1",
) -> Any:
    return NPCDirectResponse(
        npc_response=text,
        emotional_state_after=emotion,
        relationship_delta=delta,
    )


def _patch_dspy_forward(agent: NPCVoice, prediction: Any) -> None:
    class _Mod:
        def __call__(self, **_kwargs: Any) -> Any:
            return prediction

    agent._direct_module = _Mod()  # type: ignore[assignment]


# Per-test captured-call log keyed by tool name; reset by the autouse fixture.
_captured: Dict[str, List[Dict[str, Any]]] = {}


@contextlib.contextmanager
def _patch_mongo_character_lookup(npc_id: UUID, universe_id: UUID):
    """Stub the Mongo fallback in `_write_npc_memory`.

    The production code's last fallback is `coll.find_one({"versions.entity_id": ...})`
    on the `characters` collection. Returning a doc with the conversatory
    universe id simulates the legacy field that drives `resolved_universe_id`.
    """
    coll = MagicMock()
    coll.find_one.return_value = {
        "versions": [{"entity_id": str(npc_id), "universe_id": str(universe_id)}]
    }
    client = MagicMock()
    client.get_collection.return_value = coll
    with patch("monitor_data.db.mongodb.get_mongodb_client", return_value=client):
        yield


def _stub_tool(agent: NPCVoice, side_effects: Dict[str, Any]) -> None:
    async def _call(name: str, params: Dict[str, Any]) -> Any:
        # NPCVoice wraps kwargs into {"params": ...}; unwrap so tests can
        # assert on the inner dict directly.
        inner = params.get("params", params) if isinstance(params, dict) else params
        _captured.setdefault(name, []).append(inner)
        return side_effects.get(name)

    agent.call_tool = _call  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _reset_captured():
    _captured.clear()


@pytest.fixture
def npc_id() -> UUID:
    return uuid4()


@pytest.fixture
def player_id() -> UUID:
    return uuid4()


@pytest.fixture
def universe_id() -> UUID:
    return uuid4()


@pytest.fixture
def conv_id() -> UUID:
    return uuid4()


@pytest.fixture
def agent() -> NPCVoice:
    """A NPCVoice with mocked tool dispatch and a stubbed DSPy module."""
    a = NPCVoice()
    _patch_dspy_forward(a, _prediction())
    _stub_tool(a, side_effects={"qdrant_search_memories": []})
    return a


@pytest.fixture
def npc_data(universe_id, player_id) -> Dict[str, Any]:
    return {
        "name": "Maeve",
        "role": "tavern keeper",
        "profile": {
            "triggers": [],
            "relationship_states": {},
            "relationship_states_by_universe": {
                str(universe_id): {str(player_id): {"trust": 0.1, "stance": "warm"}}
            },
            "current_emotional_state": "neutral",
            "current_emotional_state_by_universe": {str(universe_id): "guarded"},
        },
        "facts": [],
    }


# ---------------------------------------------------------------------------
# _format_emotional_context (npc_voice.py:511-535)
# ---------------------------------------------------------------------------


class TestFormatEmotionalContext:
    def test_per_universe_read_wins_over_legacy(self, agent, npc_data, universe_id):
        """Partition must override legacy. Mutation: drop the `if universe_id is not None` guard."""
        result = agent._format_emotional_context(
            npc_data["profile"], universe_id=universe_id
        )
        # Per-universe "guarded" wins over legacy "neutral".
        assert "guarded" in result
        assert not result.startswith("neutral")

    def test_neutral_per_universe_falls_back_to_legacy(self, agent, universe_id):
        """If the partition holds the literal 'neutral', read legacy instead.
        Mutation: drop the `if base == "neutral"` clause."""
        profile = {
            "current_emotional_state_by_universe": {str(universe_id): "neutral"},
            "current_emotional_state": "legacy-emotion",
        }
        result = agent._format_emotional_context(profile, universe_id=universe_id)
        assert "legacy-emotion" in result

    def test_no_universe_reads_legacy_only(self, agent):
        """No universe_id → only legacy field consulted. Sanity baseline."""
        profile = {"current_emotional_state": "guarded"}
        result = agent._format_emotional_context(profile, universe_id=None)
        assert result.startswith("guarded")


# ---------------------------------------------------------------------------
# _build_proposals (npc_voice.py:694-823) — universe stamping + gates
# ---------------------------------------------------------------------------


class TestBuildProposalsUniverseStamping:
    def test_state_change_stamps_universe_and_partition(
        self, agent, npc_data, universe_id, npc_id, player_id
    ):
        """state_change proposal must carry universe_id + the partition update.
        Mutation: drop the `if universe_id is not None` branch at L736."""
        proposals = agent._build_proposals(
            npc_id=npc_id,
            relationship_delta="none",
            emotional_state_after="warmer",  # diff vs prior "guarded"
            profile=npc_data["profile"],
            player_entity_id=player_id,
            universe_id=universe_id,
        )
        state = next(p for p in proposals if p["change_type"] == "state_change")
        assert state["content"]["universe_id"] == str(universe_id)
        assert (
            state["content"]["profile_updates"]["current_emotional_state_by_universe"]
            == {str(universe_id): "warmer"}
        )

    def test_state_change_no_universe_stamps_neither(
        self, agent, npc_data, npc_id, player_id
    ):
        """No universe → no universe_id stamped on the proposal.
        Mutation: always stamp universe_id unconditionally."""
        proposals = agent._build_proposals(
            npc_id=npc_id,
            relationship_delta="none",
            emotional_state_after="something-new",
            profile=npc_data["profile"],
            player_entity_id=player_id,
            universe_id=None,
        )
        state = next((p for p in proposals if p["change_type"] == "state_change"), None)
        if state:
            assert "universe_id" not in state["content"]
            assert (
                "current_emotional_state_by_universe"
                not in state["content"]["profile_updates"]
            )

    def test_prior_emotion_reads_per_universe_first(
        self, agent, npc_data, universe_id, npc_id, player_id
    ):
        """Per-universe prior emotion "guarded" + pass "guarded" → NO state_change.
        Mutation: read prior from legacy, which says "neutral" → would emit diff."""
        proposals = agent._build_proposals(
            npc_id=npc_id,
            relationship_delta="none",
            emotional_state_after="guarded",
            profile=npc_data["profile"],
            player_entity_id=player_id,
            universe_id=universe_id,
        )
        assert not any(p["change_type"] == "state_change" for p in proposals)

    def test_emotion_unchanged_gate(self, agent, npc_data, universe_id, npc_id, player_id):
        """Mutation: `!=` flipped to `==` → would always emit state_change.
        With no diff, no state_change proposal."""
        proposals = agent._build_proposals(
            npc_id=npc_id,
            relationship_delta="none",
            emotional_state_after="guarded",
            profile=npc_data["profile"],
            player_entity_id=player_id,
            universe_id=universe_id,
        )
        assert not any(p["change_type"] == "state_change" for p in proposals)

    def test_player_id_equals_npc_id_skips_relationship_proposal(
        self, agent, npc_data, npc_id
    ):
        """A self-loop must NOT emit a relationship proposal.
        Mutation: drop the `player_entity_id != npc_id` guard."""
        proposals = agent._build_proposals(
            npc_id=npc_id,
            relationship_delta="trust:+0.3",
            emotional_state_after="guarded",
            profile=npc_data["profile"],
            player_entity_id=npc_id,
            universe_id=None,
        )
        assert not any(p["change_type"] == "relationship" for p in proposals)


# ---------------------------------------------------------------------------
# _build_relationship_snapshot (npc_voice.py:537-634)
# ---------------------------------------------------------------------------


class TestBuildRelationshipSnapshot:
    def test_forwards_universe_id_to_internal_read(
        self, agent, npc_data, universe_id, player_id
    ):
        """trust starts at 0.1 in the partition; +0.3 delta → ~0.4.
        Mutation: drop `universe_id` kwarg → reads legacy 0.0 → result ~0.3."""
        snap = agent._build_relationship_snapshot(
            profile=npc_data["profile"],
            player_entity_id=player_id,
            relationship_delta="trust:+0.3",
            emotional_state_after="guarded",
            universe_id=universe_id,
        )
        assert round(snap["trust"], 2) == 0.4

    def test_last_shift_reason_forwards(self, agent, npc_data, player_id):
        """Mutation: drop or override `reason` on the internal call."""
        snap = agent._build_relationship_snapshot(
            profile=npc_data["profile"],
            player_entity_id=player_id,
            relationship_delta="none",
            emotional_state_after="guarded",
            reason="because-the-barkeep-glared",
            universe_id=None,
        )
        assert snap.get("last_shift_reason") == "because-the-barkeep-glared"


# ---------------------------------------------------------------------------
# _update_working_social_state (npc_voice.py:864-906)
# ---------------------------------------------------------------------------


class TestUpdateWorkingSocialState:
    def test_legacy_fields_always_written(self, agent, npc_id, player_id):
        """No universe → captured params must still include legacy fields.
        Mutation: drop the legacy write when no universe."""
        snap = {"stance": "guarded", "trust": 0.1, "last_delta": {"trust": 0.1}}
        asyncio.run(
            agent._update_working_social_state(
                npc_id=npc_id,
                emotional_state_after="guarded",
                relationship_snapshot=snap,
                player_entity_id=player_id,
                universe_id=None,
            )
        )
        params = _captured["mongodb_update_npc_profile"][-1]
        assert params["current_emotional_state"] == "guarded"
        assert str(player_id) in params["relationship_states"]
        assert "current_emotional_state_by_universe" not in params
        assert "relationship_states_by_universe" not in params

    def test_universe_partition_written_when_provided(
        self, agent, npc_id, player_id, universe_id
    ):
        """With universe → partition map keys appear."""
        snap = {"stance": "guarded", "trust": 0.1}
        asyncio.run(
            agent._update_working_social_state(
                npc_id=npc_id,
                emotional_state_after="guarded",
                relationship_snapshot=snap,
                player_entity_id=player_id,
                universe_id=universe_id,
            )
        )
        params = _captured["mongodb_update_npc_profile"][-1]
        assert params["relationship_states_by_universe"] == {
            str(universe_id): {str(player_id): snap}
        }
        assert params["current_emotional_state_by_universe"] == {
            str(universe_id): "guarded"
        }

    def test_last_delta_stripped_from_snapshot(self, agent, npc_id, player_id):
        """`last_delta` must NOT land in MongoDB. Mutation: keep the key."""
        snap = {"stance": "guarded", "trust": 0.1, "last_delta": {"trust": 0.1}}
        asyncio.run(
            agent._update_working_social_state(
                npc_id=npc_id,
                emotional_state_after="guarded",
                relationship_snapshot=snap,
                player_entity_id=player_id,
                universe_id=None,
            )
        )
        params = _captured["mongodb_update_npc_profile"][-1]
        nested = params["relationship_states"][str(player_id)]
        assert "last_delta" not in nested

    def test_no_player_id_skips_relationship_block(self, agent, npc_data, npc_id, universe_id):
        """player_entity_id=None must NOT add relationship_states to the write.
        Mutation: drop the `player_entity_id is not None` guard.
        (The emotional_state update is always wanted, so the call itself
        still happens — just without the relationship payload.)"""
        asyncio.run(
            agent._update_working_social_state(
                npc_id=npc_id,
                emotional_state_after="guarded",
                relationship_snapshot={"stance": "warm"},
                player_entity_id=None,
                universe_id=universe_id,
            )
        )
        params = _captured["mongodb_update_npc_profile"][-1]
        assert "relationship_states" not in params
        assert "relationship_states_by_universe" not in params


# ---------------------------------------------------------------------------
# _write_npc_memory (npc_voice.py:931-996)
# ---------------------------------------------------------------------------


class TestWriteNpcMemory:
    def test_caller_universe_id_used_directly(self, agent, npc_id, conv_id):
        """Caller passes universe_id → no neo4j lookup, written as-is."""
        asyncio.run(
            agent._write_npc_memory(
                npc_id=npc_id,
                player_said="hi",
                npc_said="hello",
                conversation_id=conv_id,
                universe_id=uuid4(),
            )
        )
        assert "neo4j_get_entity" not in _captured
        call = _captured["mongodb_create_memory"][-1]
        assert "universe_id" in call and call["universe_id"] is not None

    def test_neo4j_lookup_failure_does_not_propagate(self, npc_id, conv_id):
        """If neo4j_get_entity raises, the write proceeds via the conversatory fallback."""
        a = NPCVoice()
        _patch_dspy_forward(a, _prediction())

        async def fake_call(name: str, params: Dict[str, Any]) -> Any:
            if name == "neo4j_get_entity":
                raise RuntimeError("neo4j down")
            inner = params.get("params", params) if isinstance(params, dict) else params
            _captured.setdefault(name, []).append(inner)
            return None

        a.call_tool = fake_call  # type: ignore[method-assign]
        # Patch asyncio.run directly so the conversatory fallback returns a
        # deterministic id without entering a nested loop.
        import asyncio
        conversatory_universe = uuid4()
        with _patch_mongo_character_lookup(npc_id, conversatory_universe):
            asyncio.run(
                a._write_npc_memory(
                    npc_id=npc_id,
                    player_said="hi",
                    npc_said="hello",
                    conversation_id=conv_id,
                    universe_id=None,
                )
            )
        call = _captured["mongodb_create_memory"][-1]
        # Neo4j raised → entity lookup failed → conversatory fallback wins.
        assert call["universe_id"] == str(conversatory_universe)

    def test_nested_properties_universe_id_resolved(self, npc_id, conv_id):
        """Entity shape is {id, properties: {universe_id: 'X'}}, no top-level field."""
        a = NPCVoice()
        _patch_dspy_forward(a, _prediction())

        async def fake_call(name: str, params: Dict[str, Any]) -> Any:
            if name == "neo4j_get_entity":
                return {"id": str(npc_id), "properties": {"universe_id": "nested-uni"}}
            inner = params.get("params", params) if isinstance(params, dict) else params
            _captured.setdefault(name, []).append(inner)
            return None

        a.call_tool = fake_call  # type: ignore[method-assign]
        with _patch_mongo_character_lookup(npc_id, uuid4()):
            asyncio.run(
                a._write_npc_memory(
                    npc_id=npc_id,
                    player_said="hi",
                    npc_said="hello",
                    conversation_id=conv_id,
                    universe_id=None,
                )
            )
        call = _captured["mongodb_create_memory"][-1]
        # Nested shape wins over conversatory fallback.
        assert call["universe_id"] == "nested-uni"


# ---------------------------------------------------------------------------
# _recall_memories (npc_voice.py:387-414)
# ---------------------------------------------------------------------------


class TestRecallMemoriesMutation:
    def test_top_k_forwarded(self, agent, npc_id):
        """Mutation: hardcode top_k=5 instead of using the param."""
        asyncio.run(agent._recall_memories(npc_id, "q", top_k=7))
        assert _captured["qdrant_search_memories"][-1]["top_k"] == 7

    def test_universe_id_forwarded_to_qdrant_kwargs(self, agent, npc_id, universe_id):
        """Mutation: drop `if universe_id is not None` guard.

        Independent of the existing test file's assertion — duplicates the
        contract so a fixture-pollution regression here is still caught.
        """
        asyncio.run(agent._recall_memories(npc_id, "q", universe_id=universe_id))
        call = _captured["qdrant_search_memories"][-1]
        assert call["universe_id"] == str(universe_id)
        assert call["entity_id"] == str(npc_id)

    def test_non_list_result_returns_empty(self, agent, npc_id):
        """Mutation: drop the `isinstance(result, list)` guard → returns a dict."""

        async def fake_call(name: str, params: Dict[str, Any]) -> Any:
            inner = params.get("params", params) if isinstance(params, dict) else params
            _captured.setdefault(name, []).append(inner)
            return {"unexpected": "shape"}

        agent.call_tool = fake_call  # type: ignore[method-assign]
        result = asyncio.run(agent._recall_memories(npc_id, "q"))
        assert result == []

    def test_cross_incarnation_without_universe_id(self, agent, npc_id):
        """Cross-incarnation flag alone (no universe_id) must be sent through.
        Mutation: gate the flag on `universe_id is not None`."""
        asyncio.run(
            agent._recall_memories(npc_id, "q", include_cross_incarnation=True)
        )
        call = _captured["qdrant_search_memories"][-1]
        assert call.get("include_cross_incarnation") is True
        assert "universe_id" not in call


# ---------------------------------------------------------------------------
# respond_direct — top-level wiring (npc_voice.py:104-273)
# ---------------------------------------------------------------------------


class TestRespondDirectThreadingMutations:
    def test_cross_incarnation_without_universe_threads_flag(
        self, agent, npc_data, npc_id, player_id, conv_id
    ):
        """`include_cross_incarnation=True` alone (no universe_id) must still
        be threaded into the recall kwargs.
        Mutation: only forward the flag when universe_id is also set."""
        conversatory_universe = uuid4()
        # The production code does `import asyncio as _aio` and `_aio.run(...)`.
        # `_patch_conversatory_fallback` only intercepts coroutine-typed calls
        # so the test's outer asyncio.run() still works.
        conversatory_universe = uuid4()
        with _patch_mongo_character_lookup(npc_id, conversatory_universe):
            asyncio.run(
                agent.respond_direct(
                    conversation_id=conv_id,
                    npc_id=npc_id,
                    player_said="hi",
                    npc_data=npc_data,
                    player_entity_id=player_id,
                    universe_id=None,
                    include_cross_incarnation=True,
                )
            )
        recall = _captured.get("qdrant_search_memories", [{}])[-1]
        assert recall.get("include_cross_incarnation") is True
        # universe_id is omitted when include_cross_incarnation=True so the
        # recall spans all universes for this NPC (not scoped to one).
        assert "universe_id" not in recall

    def test_explicit_include_cross_incarnation_false_not_in_kwargs(
        self, agent, npc_data, npc_id, player_id, conv_id
    ):
        """Sanity: explicit False must NOT land in the qdrant kwargs."""
        with patch(
            "monitor_ui.routers.character_conversation.ensure_conversatory_universe",
            new=AsyncMock(return_value=None),
        ), patch("monitor_data.db.mongodb.get_mongodb_client"):
            asyncio.run(
                agent.respond_direct(
                    conversation_id=conv_id,
                    npc_id=npc_id,
                    player_said="hi",
                    npc_data=npc_data,
                    player_entity_id=player_id,
                    universe_id=uuid4(),
                    include_cross_incarnation=False,
                )
            )
        recall = _captured["qdrant_search_memories"][-1]
        assert "include_cross_incarnation" not in recall

    def test_legacy_memory_write_when_no_universe(
        self, agent, npc_data, npc_id, player_id, conv_id
    ):
        """respond_direct without universe_id falls back through conversatory.

        When the conversatory universe is available, the memory write proceeds
        with that universe_id stamped — legacy callers no longer have a
        'no universe' code path. Mutation: drop the conversatory fallback.
        """
        conversatory_universe = uuid4()
        with _patch_mongo_character_lookup(npc_id, conversatory_universe):
            asyncio.run(
                agent.respond_direct(
                    conversation_id=conv_id,
                    npc_id=npc_id,
                    player_said="hi",
                    npc_data=npc_data,
                    player_entity_id=player_id,
                    universe_id=None,
                )
            )
        assert "mongodb_create_memory" in _captured
        assert _captured["mongodb_create_memory"][-1]["universe_id"] == str(
            conversatory_universe
        )