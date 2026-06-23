"""Tests for WorldArchitect profile-aware world-building guidance."""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, Mock

import pytest

from monitor_agents.world_architect import WorldArchitect


@pytest.mark.asyncio
async def test_process_turn_includes_world_profile_guidance() -> None:
    """WorldArchitect should build and pass structured profile guidance into the prompt."""
    agent = WorldArchitect()
    universe_id = uuid4()
    world_summary = {
        "entities": [
            {"name": "House Morvain", "type": "faction", "description": "Ancient noble house"}
        ],
        "axioms": [{"statement": "Blood binds the old oaths.", "domain": "society"}],
        "facts": [{"statement": "The city is ruled by a nocturnal court.", "type": "state"}],
        "entity_count": 1,
        "axiom_count": 1,
        "fact_count": 1,
    }

    agent._load_world_state = AsyncMock(return_value=world_summary)
    agent._commit_proposals = AsyncMock(return_value=(0, [], {}))
    agent._architect_module = Mock(
        return_value=SimpleNamespace(
            response="That gives us a strong foundation.",
            extracted_proposals="[]",
        )
    )

    result = await agent.process_turn(
        user_message="A vampire prince rules the city through feuding noble houses.",
        universe_id=universe_id,
        conversation_history=[{"role": "user", "content": "I want gothic court politics."}],
    )

    kwargs = agent._architect_module.call_args.kwargs
    assert "world_profile_context" in kwargs
    assert "coverage_summary" in kwargs
    assert "known_open_questions" in kwargs
    assert "court" in kwargs["world_profile_context"].lower()
    assert result["coverage_summary"]
    assert result["known_open_questions"]
    assert result["world_profile"]["profile_type"] == "world"


@pytest.mark.asyncio
async def test_suggest_next_uses_profile_guidance() -> None:
    """Gap analysis should receive profile context and open questions, not just raw counts."""
    agent = WorldArchitect()
    universe_id = uuid4()
    world_summary = {
        "entities": [],
        "axioms": [],
        "facts": [],
        "entity_count": 0,
        "axiom_count": 0,
        "fact_count": 0,
    }

    agent._load_world_state = AsyncMock(return_value=world_summary)
    agent._gap_module = Mock(
        return_value=SimpleNamespace(
            gaps=json.dumps(
                [
                    {
                        "area": "Core identity",
                        "priority": 1,
                        "suggestion": "Name the world and define its tone.",
                        "example_prompt": "This world is called...",
                    }
                ]
            )
        )
    )

    response = await agent.suggest_next(universe_id)

    kwargs = agent._gap_module.call_args.kwargs
    assert "coverage_summary" in kwargs
    assert "known_open_questions" in kwargs
    assert "world_profile_context" in kwargs
    assert "Core identity" in response


class TestWorldArchitectProfileTypes:
    @pytest.mark.asyncio
    async def test_process_turn_handles_empty_history(self) -> None:
        """WorldArchitect should handle empty conversation history."""
        agent = WorldArchitect()
        universe_id = uuid4()

        agent._load_world_state = AsyncMock(
            return_value={
                "entities": [],
                "axioms": [],
                "facts": [],
                "entity_count": 0,
                "axiom_count": 0,
                "fact_count": 0,
            }
        )
        agent._commit_proposals = AsyncMock(return_value=(0, [], {}))
        agent._architect_module = Mock(
            return_value=SimpleNamespace(
                response="Let's start building.",
                extracted_proposals="[]",
            )
        )

        result = await agent.process_turn(
            user_message="I want to create a new world.",
            universe_id=universe_id,
            conversation_history=[],
        )

        assert result["coverage_summary"] is not None
        assert result["world_profile"]["profile_type"] == "world"

    @pytest.mark.asyncio
    async def test_suggest_next_with_no_gaps(self) -> None:
        """suggest_next should handle world with no gaps."""
        agent = WorldArchitect()
        universe_id = uuid4()

        agent._load_world_state = AsyncMock(
            return_value={
                "entities": [{"name": "World", "type": "setting"}],
                "axioms": [{"statement": "Default axiom.", "domain": "general"}],
                "facts": [],
                "entity_count": 1,
                "axiom_count": 1,
                "fact_count": 0,
            }
        )
        agent._gap_module = Mock(return_value=SimpleNamespace(gaps=json.dumps([])))

        response = await agent.suggest_next(universe_id)

        assert response is not None

    def test_world_architect_has_process_turn_method(self) -> None:
        """WorldArchitect should have process_turn method."""
        agent = WorldArchitect()
        assert hasattr(agent, "process_turn")

    def test_world_architect_has_suggest_next_method(self) -> None:
        """WorldArchitect should have suggest_next method."""
        agent = WorldArchitect()
        assert hasattr(agent, "suggest_next")

    def test_world_architect_initialization(self) -> None:
        """WorldArchitect can be initialized."""
        agent = WorldArchitect()
        assert agent is not None


# ---------------------------------------------------------------------------
# T-096: deterministic fallback entity proposal for explicit create requests
# ---------------------------------------------------------------------------


class TestFallbackEntityProposal:
    def _agent(self):
        return WorldArchitect.__new__(WorldArchitect)

    @pytest.mark.parametrize(
        "msg,expected_name,expected_type",
        [
            (
                "Create a new NPC: Sister Wrenna, a haunted gravekeeper.",
                "Sister Wrenna",
                "character",
            ),
            (
                "Add a new canon NPC named Gareth the lamplighter who walks at dusk.",
                "Gareth",
                "character",
            ),
            (
                "Create and commit a new character entity named Mirella Vane.",
                "Mirella Vane",
                "character",
            ),
            (
                "Please add a faction called The Ash Wardens to the world.",
                "The Ash Wardens",
                "faction",
            ),
            ("Create a location named Hollowmere on the map.", "Hollowmere", "location"),
        ],
    )
    def test_synthesizes_for_explicit_create(self, msg, expected_name, expected_type):
        uid = uuid4()
        prop = self._agent()._fallback_entity_proposal(msg, uid)
        assert prop is not None
        assert prop["change_type"] == "entity"
        assert prop["payload"]["name"] == expected_name
        assert prop["payload"]["entity_type"] == expected_type
        assert prop["universe_id"] == str(uid)

    @pytest.mark.parametrize(
        "msg",
        [
            "What do you think about the political situation in the world?",
            "Tell me more about the lamplighter.",
            "How many factions are there?",
            "create something interesting",  # no entity kind / no name
        ],
    )
    def test_no_proposal_without_explicit_named_create(self, msg):
        assert self._agent()._fallback_entity_proposal(msg, uuid4()) is None

    def test_none_without_universe(self):
        assert self._agent()._fallback_entity_proposal("Create an NPC named Bob", None) is None
