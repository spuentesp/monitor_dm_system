"""
Tests for NPCVoice agent — direct dialogue and actor-mode reflection.

Covers:
- respond_direct: correct DSPy module invoked, turn persisted, memory written
- respond_actor: actor module invoked, canon_insight parsed into proposals
- _evaluate_triggers: trigger matching logic
- _format_personality: compact personality string
- _build_proposals: relationship delta and emotional state proposals
- _build_insight_proposals: profile update and new_fact proposals
"""

from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from monitor_agents.npc_voice.agent import NPCVoice

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def npc_id() -> UUID:
    return uuid4()


@pytest.fixture
def conversation_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_profile() -> dict[str, Any]:
    return {
        "traits": {"openness": 0.3, "conscientiousness": 0.8, "agreeableness": -0.4},
        "values": ["loyalty", "honor"],
        "fears": ["betrayal"],
        "desires": ["recognition"],
        "speech_style": "terse military clipped",
        "catchphrases": ["Stand your ground.", "Weakness invites death."],
        "current_emotional_state": "guarded",
        "triggers": [
            {
                "condition": "mention the thieves guild",
                "reaction": "becomes hostile",
                "intensity": 0.9,
                "is_hidden": False,
            }
        ],
        "secrets": ["Was a spy", "Owes debt to guild"],
    }


@pytest.fixture
def sample_npc_data(sample_profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "Commander Aldric",
        "role": "city guard captain",
        "profile": sample_profile,
        "facts": [
            "Commander Aldric leads the East Gate garrison",
            "He lost two fingers at the Battle of Ashford",
        ],
    }


# =============================================================================
# _evaluate_triggers TESTS
# =============================================================================


def test_evaluate_triggers_matches_keyword() -> None:
    """Trigger fires when player input contains a keyword from condition."""
    agent = NPCVoice()
    triggers = [
        {
            "condition": "mention the thieves guild",
            "reaction": "hostile",
            "intensity": 0.9,
            "is_hidden": False,
        }
    ]
    active = agent._evaluate_triggers(triggers, "I need help from the guild")
    assert len(active) == 1
    assert active[0]["reaction"] == "hostile"


def test_evaluate_triggers_no_match() -> None:
    """Trigger does not fire if no keywords match."""
    agent = NPCVoice()
    triggers = [{"condition": "assassination attempt", "reaction": "draws sword", "intensity": 1.0}]
    active = agent._evaluate_triggers(triggers, "What is the weather today?")
    assert active == []


def test_evaluate_triggers_caps_at_three() -> None:
    """At most 3 triggers are returned regardless of how many match."""
    agent = NPCVoice()
    # All keywords are long enough to be checked — force match by using single word conditions
    triggers2 = [{"condition": f"trigger{i}", "reaction": f"r{i}", "intensity": 0.5} for i in range(6)]
    # Player mentions all trigger words
    player_input = " ".join(f"trigger{i}" for i in range(6))
    active = agent._evaluate_triggers(triggers2, player_input)
    assert len(active) <= 3


# =============================================================================
# _format_personality TESTS
# =============================================================================


def test_format_personality_includes_speech_style(sample_profile: dict[str, Any]) -> None:
    agent = NPCVoice()
    result = agent._format_personality(sample_profile)
    assert "terse military clipped" in result


def test_format_personality_includes_top_traits(sample_profile: dict[str, Any]) -> None:
    agent = NPCVoice()
    result = agent._format_personality(sample_profile)
    assert "conscientiousness" in result  # highest abs value


def test_format_personality_empty_profile() -> None:
    agent = NPCVoice()
    result = agent._format_personality({})
    assert "No personality profile defined" in result


# =============================================================================
# _build_proposals TESTS
# =============================================================================


def test_build_proposals_emotional_state_change(npc_id: UUID, sample_profile: dict[str, Any]) -> None:
    """Emotional shifts are normalized into a canonical state_change proposal."""
    agent = NPCVoice()
    proposals = agent._build_proposals(
        npc_id=npc_id,
        relationship_delta="none",
        emotional_state_after="hostile",  # different from profile's "guarded"
        profile=sample_profile,
    )
    assert any(p["change_type"] == "state_change" for p in proposals)
    state_proposal = next(p for p in proposals if p["change_type"] == "state_change")
    assert state_proposal["content"]["current_emotional_state"] == "hostile"
    assert "hostile" in state_proposal["content"]["add_tags"]


def test_build_proposals_no_emotional_change(npc_id: UUID, sample_profile: dict[str, Any]) -> None:
    """No state_change proposal is created when the mood is unchanged."""
    agent = NPCVoice()
    proposals = agent._build_proposals(
        npc_id=npc_id,
        relationship_delta="none",
        emotional_state_after="guarded",  # same as profile
        profile=sample_profile,
    )
    assert not any(p["change_type"] == "state_change" for p in proposals)


def test_build_proposals_relationship_delta_positive(npc_id: UUID, sample_profile: dict[str, Any]) -> None:
    """Relationship shifts are normalized into canonical relationship proposals."""
    agent = NPCVoice()
    player_id = uuid4()
    proposals = agent._build_proposals(
        npc_id=npc_id,
        relationship_delta="trust:+0.15",
        emotional_state_after="guarded",
        profile=sample_profile,
        player_entity_id=player_id,
    )
    rel = next((p for p in proposals if p["change_type"] == "relationship"), None)
    assert rel is not None
    assert rel["content"]["from_entity_id"] == str(npc_id)
    assert rel["content"]["to_entity_id"] == str(player_id)
    assert rel["content"]["rel_type"] in {"KNOWS", "ALLIED_WITH"}
    assert rel["content"]["properties"]["sentiment"] == "trust"
    assert rel["content"]["properties"]["delta"] == pytest.approx(0.15)


def test_build_proposals_malformed_delta_ignored(npc_id: UUID, sample_profile: dict[str, Any]) -> None:
    """Malformed relationship deltas do not create canonical proposals."""
    agent = NPCVoice()
    proposals = agent._build_proposals(
        npc_id=npc_id,
        relationship_delta="not_valid_format",
        emotional_state_after="guarded",
        profile=sample_profile,
        player_entity_id=uuid4(),
    )
    assert not any(p["change_type"] == "relationship" for p in proposals)


# =============================================================================
# _build_insight_proposals TESTS
# =============================================================================


def test_build_insight_proposals_update_profile(npc_id: UUID) -> None:
    agent = NPCVoice()
    proposals = agent._build_insight_proposals(npc_id, "update_profile:speech_style=slow and deliberate")
    assert len(proposals) == 1
    assert proposals[0]["change_type"] == "entity"
    assert proposals[0]["content"]["entity_id"] == str(npc_id)
    assert proposals[0]["content"]["profile_updates"]["speech_style"] == "slow and deliberate"


def test_build_insight_proposals_new_fact(npc_id: UUID) -> None:
    agent = NPCVoice()
    proposals = agent._build_insight_proposals(npc_id, "new_fact:Aldric secretly admires the PC's courage")
    assert len(proposals) == 1
    assert proposals[0]["change_type"] == "fact"
    assert "Aldric" in proposals[0]["content"]["statement"]


def test_build_insight_proposals_none(npc_id: UUID) -> None:
    agent = NPCVoice()
    assert agent._build_insight_proposals(npc_id, "none") == []
    assert agent._build_insight_proposals(npc_id, "") == []
    assert agent._build_insight_proposals(npc_id, "NONE") == []


# =============================================================================
# respond_direct INTEGRATION TEST (mocked LLM + tools)
# =============================================================================


@pytest.mark.asyncio
async def test_respond_direct_full_flow(
    npc_id: UUID,
    conversation_id: UUID,
    sample_npc_data: dict[str, Any],
) -> None:
    """
    respond_direct loads NPC data, calls DSPy module, persists turn and memory.
    """
    agent = NPCVoice()
    recorded_memory_args: dict[str, Any] = {}

    # Mock tool calls
    async def mock_call_tool(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "neo4j_get_entity":
            return {
                "name": sample_npc_data["name"],
                "universe_id": "uni-test",  # used by _write_npc_memory fallback
                "properties": {"role": sample_npc_data["role"]},
            }
        if tool_name == "mongodb_get_npc_profile":
            return sample_npc_data["profile"]
        if tool_name == "neo4j_list_facts":
            return [{"statement": f} for f in sample_npc_data["facts"]]
        if tool_name == "qdrant_search_memories":
            # Live fix wraps in {"params": ...}; unwrap to read fields.
            inner = args.get("params", args) if isinstance(args, dict) else args
            recorded_memory_args.update(inner)
            return [{"text": "I saw you defend the market from bandits"}]
        if tool_name in ("mongodb_append_conversation_turn", "mongodb_create_memory"):
            return {}
        return None

    agent.call_tool = mock_call_tool

    # Mock DSPy module prediction
    mock_prediction = Mock()
    mock_prediction.npc_response = "I remember you. You have guts, I'll grant you that."
    mock_prediction.emotional_state_after = "cautiously respectful"
    mock_prediction.relationship_delta = "trust:+0.1"
    agent._direct_module = Mock(return_value=mock_prediction)

    result = await agent.respond_direct(
        conversation_id=conversation_id,
        npc_id=npc_id,
        player_said="Commander, I need your help.",
        conversation_history=[],
        player_entity_id=uuid4(),
        scene_id=uuid4(),
        story_id=uuid4(),
        universe_id=uuid4(),  # legacy callers may omit; we pass it explicitly
    )

    assert result["npc_response"] == "I remember you. You have guts, I'll grant you that."
    assert result["emotional_state_after"] == "cautiously respectful"
    assert result["relationship_delta"] == "trust:+0.1"
    assert any(p["change_type"] == "state_change" for p in result["proposals"])
    assert any(p["change_type"] == "relationship" for p in result["proposals"])
    assert recorded_memory_args["query_text"] == "Commander, I need your help."
    assert recorded_memory_args["top_k"] == 5


@pytest.mark.asyncio
async def test_respond_direct_passes_profile_context_to_voice_module(
    npc_id: UUID,
    conversation_id: UUID,
    sample_npc_data: dict[str, Any],
) -> None:
    """High-confidence source-profile hints are forwarded into the direct voice prompt."""
    agent = NPCVoice()
    source_profile = {
        "genre_tone": ["courtly intrigue", "gothic horror"],
        "institution_model": ["princes", "courts", "clans"],
        "canon_signal_terms": ["Prince", "Primogen", "Embrace"],
        "term_lexicon": {"Embrace": ["the Embrace", "siring"]},
        "confidence_by_field": {
            "genre_tone": 0.9,
            "institution_model": 0.92,
            "canon_signal_terms": 0.95,
            "term_lexicon": 0.9,
        },
    }

    async def mock_call_tool(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "neo4j_get_entity":
            return {
                "name": sample_npc_data["name"],
                "universe_id": "uni-test",
                "properties": {"role": sample_npc_data["role"]},
            }
        if tool_name == "mongodb_get_npc_profile":
            return sample_npc_data["profile"]
        if tool_name == "neo4j_list_facts":
            return [{"statement": f} for f in sample_npc_data["facts"]]
        if tool_name == "qdrant_search_memories":
            return [{"text": "The Prince owes me a debt."}]
        if tool_name in ("mongodb_append_conversation_turn", "mongodb_create_memory"):
            return {}
        return None

    agent.call_tool = mock_call_tool

    mock_prediction = Mock()
    mock_prediction.npc_response = "Mind your tone in this court."
    mock_prediction.emotional_state_after = "guarded"
    mock_prediction.relationship_delta = "none"
    agent._direct_module = Mock(return_value=mock_prediction)

    await agent.respond_direct(
        conversation_id=conversation_id,
        npc_id=npc_id,
        player_said="Tell me about the Embrace.",
        conversation_history=[],
        source_profile=source_profile,
        universe_id=uuid4(),
    )

    kwargs = agent._direct_module.call_args.kwargs
    assert "Prince" in kwargs["profile_context"]
    assert "Embrace" in kwargs["profile_context"]


@pytest.mark.asyncio
async def test_respond_direct_unknown_npc_raises(
    conversation_id: UUID,
) -> None:
    """respond_direct raises ValueError when NPC entity not found."""
    agent = NPCVoice()

    async def mock_call_tool(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "neo4j_get_entity":
            return None  # not found
        return {}

    agent.call_tool = mock_call_tool

    with pytest.raises(ValueError, match="not found"):
        await agent.respond_direct(
            conversation_id=conversation_id,
            npc_id=uuid4(),
            player_said="Hello?",
        )


# =============================================================================
# respond_actor INTEGRATION TEST
# =============================================================================


@pytest.mark.asyncio
async def test_respond_actor_full_flow(
    npc_id: UUID,
    conversation_id: UUID,
    sample_npc_data: dict[str, Any],
) -> None:
    """respond_actor calls actor module and parses canon_insight."""
    agent = NPCVoice()

    async def mock_call_tool(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "neo4j_get_entity":
            return {
                "name": sample_npc_data["name"],
                "properties": {"role": sample_npc_data["role"]},
            }
        if tool_name == "mongodb_get_npc_profile":
            return sample_npc_data["profile"]
        if tool_name == "neo4j_list_facts":
            return [{"statement": f} for f in sample_npc_data["facts"]]
        if tool_name in ("mongodb_append_conversation_turn",):
            return {}
        return None

    agent.call_tool = mock_call_tool

    mock_prediction = Mock()
    mock_prediction.actor_response = "As Aldric, I would feel deeply betrayed. My loyalty is my identity."
    mock_prediction.canon_insight = "update_profile:motivation=protect the city at any cost"
    agent._actor_module = Mock(return_value=mock_prediction)

    result = await agent.respond_actor(
        conversation_id=conversation_id,
        npc_id=npc_id,
        gm_question="What would you do if the PC betrayed you?",
    )

    assert "betrayed" in result["actor_response"]
    assert result["canon_insight"].startswith("update_profile:")
    assert len(result["proposals"]) == 1
    assert result["proposals"][0]["change_type"] == "entity"


@pytest.mark.asyncio
async def test_respond_actor_no_insight_no_proposals(
    npc_id: UUID,
    conversation_id: UUID,
    sample_npc_data: dict[str, Any],
) -> None:
    """Actor response with canon_insight='none' produces no proposals."""
    agent = NPCVoice()

    async def mock_call_tool(tool_name: str, args: dict[str, Any]) -> Any:
        if tool_name == "neo4j_get_entity":
            return {"name": sample_npc_data["name"], "properties": {}}
        if tool_name in ("mongodb_get_npc_profile", "neo4j_list_facts"):
            return {} if "profile" in tool_name else []
        return {}

    agent.call_tool = mock_call_tool

    mock_prediction = Mock()
    mock_prediction.actor_response = "Interesting question. Let me think..."
    mock_prediction.canon_insight = "none"
    agent._actor_module = Mock(return_value=mock_prediction)

    result = await agent.respond_actor(
        conversation_id=conversation_id,
        npc_id=npc_id,
        gm_question="How do you feel about your work?",
    )

    assert result["proposals"] == []
