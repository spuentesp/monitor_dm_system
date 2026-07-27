"""
Tests for the PlotHookAgent.

Covers:
- suggest_hooks: LLM-driven hook generation with heuristic fallback
- detect_contradictions: LLM-driven contradiction detection with heuristic fallback
- generate_session_prep: Aggregation of recap, threads, hooks, NPC reminders
- _heuristic_hooks: Fallback hook generation from threads and entities
- _heuristic_contradictions: Simple negation-based contradiction detection
- _parse_result: JSON string and dict parsing

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_plot_hooks.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_agents.plot_hooks import (
    Contradiction,
    ContradictionListResponse,
    PlotHook,
    PlotHookAgent,
    PlotHookListResponse,
    SessionPrep,
    extract_canon_entity_names,
    filter_ungrounded_hooks,
    hook_is_grounded,
)

# ===========================================================================
# FIXTURES
# ===========================================================================


@pytest.fixture
def agent():
    return PlotHookAgent(agent_id="test-plot-hook-agent")


@pytest.fixture
def universe_id():
    return uuid4()


@pytest.fixture
def story_id():
    return uuid4()


# ===========================================================================
# _parse_result
# ===========================================================================


class TestParseResult:
    def setup_method(self):
        self.agent = PlotHookAgent(agent_id="test-parse")

    def test_parse_dict_with_key(self):
        result = self.agent._parse_result({"threads": [{"id": "1"}]}, "threads", [])
        assert result == [{"id": "1"}]

    def test_parse_dict_missing_key_returns_default(self):
        result = self.agent._parse_result({"other": "data"}, "threads", [])
        assert result == []

    def test_parse_json_string(self):
        data = json.dumps({"threads": [{"id": "1"}]})
        result = self.agent._parse_result(data, "threads", [])
        assert result == [{"id": "1"}]

    def test_parse_invalid_json_returns_default(self):
        result = self.agent._parse_result("not json", "threads", [])
        assert result == []

    def test_parse_dict_with_dict_key(self):
        result = self.agent._parse_result({"key": "value"}, {}, {})
        assert result == {"key": "value"}

    def test_parse_non_dict_non_string(self):
        result = self.agent._parse_result([1, 2, 3], "key", None)
        assert result is None


# ===========================================================================
# _heuristic_hooks
# ===========================================================================


class TestHeuristicHooks:
    def setup_method(self):
        self.agent = PlotHookAgent(agent_id="test-heuristic")

    def test_empty_inputs_returns_empty(self):
        hooks = self.agent._heuristic_hooks([], [], [], 5)
        assert hooks == []

    def test_threads_become_hooks(self):
        threads = [
            {"thread_id": "t1", "title": "The Dark Forest", "description": "A mysterious forest"},
            {"thread_id": "t2", "title": "Missing Prince", "description": "The prince is missing"},
        ]
        hooks = self.agent._heuristic_hooks(threads, [], [], 5)
        assert len(hooks) == 2
        assert hooks[0].title == "Thread: The Dark Forest"
        assert hooks[0].urgency == "high"
        assert hooks[0].suggested_scene_type == "revelation"

    def test_entities_with_state_tags_become_hooks(self):
        entities = [
            {"name": "Gandalf", "entity_type": "character", "state_tags": ["wounded", "cursed"]},
        ]
        hooks = self.agent._heuristic_hooks([], [], entities, 5)
        assert len(hooks) == 1
        assert "Gandalf" in hooks[0].title
        assert "wounded" in hooks[0].description

    def test_max_hooks_limit(self):
        threads = [{"thread_id": f"t{i}", "title": f"Thread {i}", "description": f"Desc {i}"} for i in range(10)]
        hooks = self.agent._heuristic_hooks(threads, [], [], 3)
        assert len(hooks) == 3

    def test_entities_without_tags_skipped(self):
        entities = [
            {"name": "Boring NPC", "entity_type": "character", "state_tags": []},
        ]
        hooks = self.agent._heuristic_hooks([], [], entities, 5)
        assert hooks == []


# ===========================================================================
# _heuristic_contradictions
# ===========================================================================


class TestHeuristicContradictions:
    def setup_method(self):
        self.agent = PlotHookAgent(agent_id="test-contradiction")

    def test_no_facts_returns_empty(self):
        contradictions = self.agent._heuristic_contradictions([])
        assert contradictions == []

    def test_single_fact_no_contradiction(self):
        facts = [{"entity_id": "e1", "content": "The sky is blue"}]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert contradictions == []

    def test_same_entity_negation_detected(self):
        facts = [
            {"entity_id": "e1", "content": "The king is not dead"},
            {"entity_id": "e1", "content": "The king is dead and buried"},
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 1
        assert contradictions[0].severity == "medium"

    def test_different_entities_no_contradiction(self):
        facts = [
            {"entity_id": "e1", "content": "The king is wise"},
            {"entity_id": "e2", "content": "The queen is brave"},
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert contradictions == []


# ===========================================================================
# suggest_hooks (with mocked MCP tools and LLM)
# ===========================================================================


class TestSuggestHooks:
    @pytest.mark.asyncio
    async def test_suggest_hooks_with_llm(self, agent, universe_id):
        """Test LLM-driven hook generation."""
        mock_hooks = [
            PlotHook(
                thread_id="t1",
                title="The Dark Forest",
                description="A mysterious forest beckons",
                urgency="high",
                suggested_scene_type="exploration",
                connected_entities=["Forest Spirit"],
            )
        ]

        with (
            patch.object(agent, "call_tool", new_callable=AsyncMock) as mock_tool,
            patch.object(agent, "call_llm_structured", new_callable=AsyncMock) as mock_llm,
        ):
            # Mock MCP tool responses
            mock_tool.side_effect = [
                {"threads": [{"title": "Dark Forest", "description": "Mysterious", "status": "active"}]},
                {"scenes": [{"title": "Scene 1", "summary": "The party entered the forest"}]},
                {
                    "entities": [
                        {
                            "name": "Forest Spirit",
                            "entity_type": "character",
                            "state_tags": ["mysterious"],
                        }
                    ]
                },
            ]
            mock_llm.return_value = PlotHookListResponse(hooks=mock_hooks)

            result = await agent.suggest_hooks(universe_id, max_hooks=3)

            assert len(result) == 1
            assert result[0].title == "The Dark Forest"
            assert result[0].urgency == "high"

    @pytest.mark.asyncio
    async def test_suggest_hooks_fallback_to_heuristics(self, agent, universe_id):
        """Test that heuristic fallback works when LLM fails."""
        with (
            patch.object(agent, "call_tool", new_callable=AsyncMock) as mock_tool,
            patch.object(
                agent,
                "call_llm_structured",
                new_callable=AsyncMock,
                side_effect=Exception("LLM unavailable"),
            ),
        ):
            mock_tool.side_effect = [
                {"threads": [{"title": "Dark Forest", "description": "Mysterious", "status": "active"}]},
                {"scenes": []},
                {"entities": []},
            ]

            result = await agent.suggest_hooks(universe_id, max_hooks=3)

            # Should fall back to heuristic hooks from threads
            assert len(result) >= 1
            assert "Dark Forest" in result[0].title


# ===========================================================================
# detect_contradictions (with mocked MCP tools and LLM)
# ===========================================================================


class TestDetectContradictions:
    @pytest.mark.asyncio
    async def test_detect_contradictions_with_llm(self, agent, universe_id):
        """Test LLM-driven contradiction detection."""
        mock_contradictions = [
            Contradiction(
                fact_a="The king is alive",
                fact_b="The king was killed in battle",
                severity="high",
                explanation="The king cannot be both alive and dead",
                suggestion="Determine if the king faked his death",
            )
        ]

        with (
            patch.object(agent, "call_tool", new_callable=AsyncMock) as mock_tool,
            patch.object(agent, "call_llm_structured", new_callable=AsyncMock) as mock_llm,
        ):
            mock_tool.side_effect = [
                {"facts": [{"content": "The king is alive", "canon_level": "canon"}]},
                {"entities": [{"name": "The King", "entity_type": "character"}]},
            ]
            mock_llm.return_value = ContradictionListResponse(contradictions=mock_contradictions)

            result = await agent.detect_contradictions(universe_id)

            assert len(result) == 1
            assert result[0].severity == "high"

    @pytest.mark.asyncio
    async def test_detect_contradictions_fallback(self, agent, universe_id):
        """Test heuristic fallback when LLM fails."""
        with (
            patch.object(agent, "call_tool", new_callable=AsyncMock) as mock_tool,
            patch.object(
                agent,
                "call_llm_structured",
                new_callable=AsyncMock,
                side_effect=Exception("LLM unavailable"),
            ),
        ):
            mock_tool.side_effect = [
                {
                    "facts": [
                        {"entity_id": "e1", "content": "The king is not dead"},
                        {"entity_id": "e1", "content": "The king is dead"},
                    ]
                },
                {"entities": []},
            ]

            result = await agent.detect_contradictions(universe_id)

            # Should fall back to heuristic contradictions
            assert len(result) >= 1


# ===========================================================================
# generate_session_prep
# ===========================================================================


class TestGenerateSessionPrep:
    @pytest.mark.asyncio
    async def test_generate_session_prep(self, agent, universe_id, story_id):
        """Test full session prep generation."""
        with (
            patch.object(agent, "call_tool", new_callable=AsyncMock) as mock_tool,
            patch.object(agent, "suggest_hooks", new_callable=AsyncMock) as mock_hooks,
        ):
            mock_tool.side_effect = [
                # mongodb_list_scenes
                {
                    "scenes": [
                        {"title": "The Ambush", "summary": "Goblins attacked the party"},
                        {"title": "The Escape", "summary": "The party fled through the forest"},
                    ]
                },
                # neo4j_list_plot_threads
                {
                    "threads": [
                        {
                            "title": "The Dark Forest",
                            "involved_entities": ["Forest Spirit", "Aragorn"],
                        },
                    ]
                },
                # neo4j_list_facts
                {
                    "facts": [
                        {"content": "The forest is cursed", "canon_level": "canon"},
                    ]
                },
            ]
            mock_hooks.return_value = [
                PlotHook(
                    title="Forest Curse",
                    description="Break the curse",
                    urgency="high",
                    suggested_scene_type="exploration",
                    connected_entities=["Forest Spirit"],
                ),
            ]

            result = await agent.generate_session_prep(universe_id, story_id)

            assert isinstance(result, SessionPrep)
            assert "Ambush" in result.recap
            assert len(result.open_threads) >= 1
            assert len(result.hooks) >= 1
            assert "The forest is cursed" in result.world_state_changes

    @pytest.mark.asyncio
    async def test_generate_session_prep_empty(self, agent, universe_id, story_id):
        """Test session prep with no data."""
        with (
            patch.object(agent, "call_tool", new_callable=AsyncMock) as mock_tool,
            patch.object(agent, "suggest_hooks", new_callable=AsyncMock) as mock_hooks,
        ):
            mock_tool.side_effect = [
                {"scenes": []},
                {"threads": []},
                {"facts": []},
            ]
            mock_hooks.return_value = []

            result = await agent.generate_session_prep(universe_id, story_id)

            assert isinstance(result, SessionPrep)
            assert result.recap == "No recent scenes found."
            assert result.open_threads == []
            assert result.hooks == []


# ===========================================================================
# CF-4 HOOK QUALITY GROUNDING (G-6)
# ===========================================================================


class TestHookGrounding:
    """CF-4 enhancement: hooks must be grounded to canon entity names."""

    def test_extract_canon_entity_names_dedupes_and_lowercases(self) -> None:
        entities = [
            {"name": "Aldric the Bold"},
            {"name": "aldric the bold"},
            {"name": "Mira Stonebrook"},
            {"name": ""},
            {"not_a_name": "x"},
        ]
        names = extract_canon_entity_names(entities)
        assert len(names) == 2
        assert any("aldric" in n.lower() for n in names)
        assert any("mira" in n.lower() for n in names)

    def test_hook_is_grounded_by_title(self) -> None:
        canon = ["Aldric the Bold", "Mira Stonebrook"]
        hook = PlotHook(title="Aldric's Last Stand", description="...")
        assert hook_is_grounded(hook, canon) is True

    def test_hook_is_grounded_handles_punctuation(self) -> None:
        """Apostrophes/dashes in title still match canon entity names."""
        canon = ["Aldric the Bold"]
        hook = PlotHook(title="Aldric's Reckoning — Part Two", description="...")
        assert hook_is_grounded(hook, canon) is True

    def test_hook_is_grounded_by_connected_entities(self) -> None:
        canon = ["Aldric the Bold"]
        hook = PlotHook(
            title="Mystery in the Hills",
            description="...",
            connected_entities=["Mira Stonebrook", "Aldric the Bold"],
        )
        assert hook_is_grounded(hook, canon) is True

    def test_hook_is_not_grounded(self) -> None:
        canon = ["Aldric the Bold"]
        hook = PlotHook(title="Something happens in a town", description="...")
        assert hook_is_grounded(hook, canon) is False

    def test_hook_is_grounded_with_empty_canon(self) -> None:
        hook = PlotHook(title="Generic mystery", description="...")
        assert hook_is_grounded(hook, []) is True

    def test_filter_ungrounded_hooks_drops_unrelated(self) -> None:
        canon = ["Aldric the Bold"]
        hooks = [
            PlotHook(title="Aldric's Reckoning", description="..."),
            PlotHook(title="A stranger appears", description="..."),
        ]
        filtered = filter_ungrounded_hooks(hooks, canon, min_grounded=1)
        assert len(filtered) == 1
        assert "aldric" in filtered[0].title.lower()

    def test_filter_ungrounded_keeps_all_if_too_few_grounded(self) -> None:
        canon = ["Aldric the Bold"]
        hooks = [
            PlotHook(title="A stranger appears", description="..."),
            PlotHook(title="Another mystery", description="..."),
        ]
        filtered = filter_ungrounded_hooks(hooks, canon, min_grounded=1)
        assert len(filtered) == 2

    @pytest.mark.asyncio
    async def test_suggest_hooks_filters_ungrounded_hooks(
        self,
        agent: PlotHookAgent,
    ) -> None:
        universe_id = uuid4()
        grounded_hook = PlotHook(title="Aldric's Quest", description="...")
        ungrounded_hook = PlotHook(title="A stranger appears", description="...")
        llm_response = PlotHookListResponse(hooks=[grounded_hook, ungrounded_hook])

        with patch.object(agent, "call_tool", new=AsyncMock()) as mock_tool:
            mock_tool.side_effect = [
                {"threads": []},
                {"scenes": []},
                {
                    "entities": [
                        {"name": "Aldric the Bold"},
                        {"name": "Mira Stonebrook"},
                    ]
                },
            ]
            with patch.object(
                agent,
                "call_llm_structured",
                new=AsyncMock(return_value=llm_response),
            ):
                hooks = await agent.suggest_hooks(universe_id)

        assert len(hooks) == 1
        assert "aldric" in hooks[0].title.lower()


# ===========================================================================
# CF-5 CONTRADICTION DEPTH FIXTURES (G-7)
# ===========================================================================


class TestContradictionDepthFixtures:
    """Deeper contradiction detection beyond simple negation.

    Covers:
    - Status antonyms (alive/dead, married/single, free/captive)
    - Location conflict (entity in two different places)
    - Multiple planted contradictions in same batch
    """

    def setup_method(self):
        self.agent = PlotHookAgent(agent_id="test-contradiction-depth")

    def test_planted_alive_vs_dead(self):
        """Fact: 'The mayor is alive' vs 'The mayor is dead' → detect."""
        facts = [
            {
                "entity_id": "mayor",
                "content": "The mayor is alive and well, ruling the city.",
            },
            {
                "entity_id": "mayor",
                "content": "The mayor is dead, struck down in the night.",
            },
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 1
        # Should detect the alive/dead antonym
        joined = " ".join(c.explanation.lower() for c in contradictions)
        assert "alive" in joined or "dead" in joined

    def test_planted_married_vs_single(self):
        facts = [
            {
                "entity_id": "alice",
                "content": "Alice is married to the blacksmith.",
            },
            {
                "entity_id": "alice",
                "content": "Alice is single and courted by many suitors.",
            },
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 1
        joined = " ".join(c.explanation.lower() for c in contradictions)
        assert "married" in joined or "single" in joined

    def test_planted_free_vs_captive(self):
        facts = [
            {
                "entity_id": "prisoner",
                "content": "The prisoner is free, walking the streets.",
            },
            {
                "entity_id": "prisoner",
                "content": "The prisoner is captive in the dungeon.",
            },
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 1
        joined = " ".join(c.explanation.lower() for c in contradictions)
        assert "free" in joined or "captive" in joined

    def test_planted_ally_vs_enemy(self):
        facts = [
            {
                "entity_id": "knight",
                "content": "The knight is an ally of the crown.",
            },
            {
                "entity_id": "knight",
                "content": "The knight is an enemy of the realm.",
            },
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 1

    def test_planted_location_conflict(self):
        facts = [
            {
                "entity_id": "wizard",
                "content": "The wizard is in Waterdeep planning the assault.",
            },
            {
                "entity_id": "wizard",
                "content": "The wizard is in Neverwinter, gathering scrolls.",
            },
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 1
        joined = " ".join(c.explanation.lower() for c in contradictions)
        assert "location" in joined or "waterdeep" in joined or "neverwinter" in joined

    def test_multiple_contradictions_in_batch(self):
        """Multiple entities with multiple planted contradictions."""
        facts = [
            # Entity 1: alive/dead
            {"entity_id": "e1", "content": "The baron is alive."},
            {"entity_id": "e1", "content": "The baron is dead."},
            # Entity 2: location
            {"entity_id": "e2", "content": "The witch is in Baldur's Gate."},
            {"entity_id": "e2", "content": "The witch is in Candlekeep."},
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 2

    def test_no_contradiction_when_same_status(self):
        facts = [
            {"entity_id": "e1", "content": "The king is alive."},
            {"entity_id": "e1", "content": "The king is well and active."},
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        # Same status, no contradiction expected
        assert contradictions == []

    def test_location_with_overlap_no_contradiction(self):
        """Both facts mention the same location → no conflict."""
        facts = [
            {"entity_id": "e1", "content": "The hero is in Waterdeep."},
            {"entity_id": "e1", "content": "The hero is in Waterdeep resting."},
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        # Same location — no location contradiction
        location_contradictions = [c for c in contradictions if "location" in c.explanation.lower()]
        assert location_contradictions == []

    def test_severity_is_high_for_status_antonyms(self):
        """Status antonym contradictions should be marked high severity."""
        facts = [
            {"entity_id": "e1", "content": "The lord is alive."},
            {"entity_id": "e1", "content": "The lord is dead."},
        ]
        contradictions = self.agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 1
        # At least one should be high severity (status antonym path)
        assert any(c.severity == "high" for c in contradictions)
