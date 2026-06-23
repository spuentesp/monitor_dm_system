"""Behavior tests for ConversationLoop choreography (Phase 2-3).

Exercises pure logic only — no LLM, no DB.

Covers:
- _normalize_conversation_change_type: legacy NPC proposal labels map
  to canonical ProposedChange types
- ConversationState defaults
"""
from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# _normalize_conversation_change_type
# =============================================================================


class TestNormalizeConversationChangeType:
    def test_known_legacy_labels_map_correctly(self):
        from monitor_agents.loops.conversation_loop import (
            _normalize_conversation_change_type,
        )

        assert (
            _normalize_conversation_change_type("npc_emotional_state") == "state_change"
        )
        assert (
            _normalize_conversation_change_type("relationship_delta") == "relationship"
        )
        assert (
            _normalize_conversation_change_type("npc_profile_update") == "entity"
        )
        assert _normalize_conversation_change_type("fact_proposal") == "fact"

    def test_unknown_label_passes_through_normalized(self):
        from monitor_agents.loops.conversation_loop import (
            _normalize_conversation_change_type,
        )

        assert _normalize_conversation_change_type("custom_thing") == "custom_thing"
        assert _normalize_conversation_change_type("ALREADY_CANONICAL") == "already_canonical"

    def test_empty_string_defaults_to_fact(self):
        from monitor_agents.loops.conversation_loop import (
            _normalize_conversation_change_type,
        )

        assert _normalize_conversation_change_type("") == "fact"

    def test_none_defaults_to_fact(self):
        from monitor_agents.loops.conversation_loop import (
            _normalize_conversation_change_type,
        )

        # _normalize_conversation_change_type does `(change_type or "fact").strip().lower()`
        # so None becomes "fact"
        assert _normalize_conversation_change_type(None) == "fact"

    def test_strips_whitespace_and_lowercases(self):
        from monitor_agents.loops.conversation_loop import (
            _normalize_conversation_change_type,
        )

        assert (
            _normalize_conversation_change_type("  NPC_EMOTIONAL_STATE  ")
            == "state_change"
        )

    def test_already_normalized_passes_through(self):
        from monitor_agents.loops.conversation_loop import (
            _normalize_conversation_change_type,
        )

        # Already-canonical values pass through unchanged
        for canonical in ["state_change", "relationship", "entity", "fact"]:
            assert _normalize_conversation_change_type(canonical) == canonical


# =============================================================================
# ConversationState defaults
# =============================================================================


def _make_state(**overrides) -> Any:
    """Build a minimal ConversationState."""
    from monitor_agents.loops.conversation_loop import ConversationState
    from monitor_data.schemas.conversations import ConversationMode

    base: Dict[str, Any] = {
        "conversation_id": uuid4(),
        "universe_id": uuid4(),
        "mode": ConversationMode.DIRECT,
    }
    base.update(overrides)
    return ConversationState(**base)


class TestConversationStateDefaults:
    def test_minimal_construction(self):
        state = _make_state()
        assert state.npc_ids == []
        assert state.scene_id is None
        assert state.story_id is None
        assert state.player_entity_id is None
        assert state.npc_contexts == {}
        assert state.source_profile == {}
        assert state.turns == []
        assert state.current_player_input is None
        assert state.current_npc_responses == []
        assert state.pending_proposals == []
        assert state.is_complete is False
        assert state.turns_count == 0
        assert state.max_turns == 100

    def test_required_fields(self):
        from monitor_data.schemas.conversations import ConversationMode
        from monitor_agents.loops.conversation_loop import ConversationState

        # Missing conversation_id
        with pytest.raises(Exception):
            ConversationState(universe_id=uuid4(), mode=ConversationMode.DIRECT)

        # Missing universe_id
        with pytest.raises(Exception):
            ConversationState(conversation_id=uuid4(), mode=ConversationMode.DIRECT)

        # Missing mode
        with pytest.raises(Exception):
            ConversationState(conversation_id=uuid4(), universe_id=uuid4())

    def test_explicit_overrides(self):
        cid = uuid4()
        sid = uuid4()
        pid = uuid4()
        npc1 = uuid4()
        npc2 = uuid4()
        state = _make_state(
            conversation_id=cid,
            scene_id=sid,
            player_entity_id=pid,
            npc_ids=[npc1, npc2],
            current_player_input="Hello there",
            turns_count=5,
            max_turns=20,
            is_complete=True,
        )
        assert state.conversation_id == cid
        assert state.scene_id == sid
        assert state.player_entity_id == pid
        assert state.npc_ids == [npc1, npc2]
        assert state.current_player_input == "Hello there"
        assert state.turns_count == 5
        assert state.max_turns == 20
        assert state.is_complete is True

    def test_with_npc_contexts(self):
        npc_id = uuid4()
        state = _make_state(
            npc_ids=[npc_id],
            npc_contexts={
                str(npc_id): {
                    "name": "Bartholomew",
                    "role": "innkeeper",
                    "profile": {"speech_style": "formal"},
                    "facts": [{"id": "f1", "statement": "He owns the Prancing Pony"}],
                }
            },
        )
        ctx = state.npc_contexts[str(npc_id)]
        assert ctx["name"] == "Bartholomew"
        assert ctx["facts"][0]["statement"].startswith("He owns")

    def test_with_pending_proposals(self):
        state = _make_state(
            pending_proposals=[
                {
                    "proposal_type": "fact",
                    "payload": {"statement": "Bart has a limp"},
                }
            ]
        )
        assert len(state.pending_proposals) == 1
        assert state.pending_proposals[0]["proposal_type"] == "fact"
