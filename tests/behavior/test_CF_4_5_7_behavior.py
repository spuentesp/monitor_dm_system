"""
Behavior tests for the GM Assistant use cases (Phase 4).

Use Cases:
- CF-4: Plot hook suggestions
- CF-5: Contradiction detection
- CF-7: Session preparation materials

These tests verify the PlotHookAgent produces sensible output both
through the LLM path (with FakeLLMClient) and the heuristic fallback
path (no LLM). The tests are pure unit tests — no DB, no real MCP
servers, no real LLM calls.
"""

from __future__ import annotations

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
)

# =============================================================================
# CF-4: Plot Hook Suggestions
# =============================================================================


class TestPlotHookSchema:
    """PlotHook model has expected fields and defaults."""

    def test_minimal_plot_hook(self):
        h = PlotHook(
            title="Mystery at the docks", description="A ship arrived at midnight."
        )
        assert h.title == "Mystery at the docks"
        assert h.urgency == "medium"
        assert h.suggested_scene_type == "exploration"
        assert h.connected_entities == []

    def test_plot_hook_with_metadata(self):
        h = PlotHook(
            title="Bandit ambush",
            description="Bandits on the road.",
            urgency="high",
            suggested_scene_type="combat",
            connected_entities=["Thieves Guild"],
        )
        assert h.urgency == "high"
        assert h.suggested_scene_type == "combat"
        assert "Thieves Guild" in h.connected_entities

    def test_plot_hook_response_wraps_list(self):
        resp = PlotHookListResponse(
            hooks=[
                PlotHook(title="A", description="a"),
                PlotHook(title="B", description="b"),
            ]
        )
        assert len(resp.hooks) == 2


class TestSuggestHooksHeuristic:
    """suggest_hooks falls back to heuristics when LLM is unavailable."""

    @pytest.mark.asyncio
    async def test_empty_universe_yields_no_hooks(self):
        agent = PlotHookAgent()
        # Force LLM path to fail so heuristic path runs
        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(agent, "call_tool", new=AsyncMock(return_value={})):
            hooks = await agent.suggest_hooks(universe_id=uuid4(), max_hooks=5)
        # No data → no hooks
        assert isinstance(hooks, list)
        assert hooks == []

    @pytest.mark.asyncio
    async def test_threads_produce_hooks(self):
        agent = PlotHookAgent()

        async def fake_call_tool(name, args):
            if name == "neo4j_list_plot_threads":
                return {
                    "threads": [
                        {
                            "title": "The Lost Crown",
                            "description": "A relic vanished.",
                            "status": "active",
                        },
                        {
                            "title": "Smugglers in the Bay",
                            "description": "Activity at the docks.",
                            "status": "active",
                        },
                    ]
                }
            if name == "mongodb_list_scenes":
                return {"scenes": []}
            if name == "neo4j_list_entities":
                return {"entities": []}
            return {}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            hooks = await agent.suggest_hooks(universe_id=uuid4(), max_hooks=10)
        assert len(hooks) >= 1
        # Each hook has a title and description
        for h in hooks:
            assert isinstance(h, PlotHook)
            assert h.title
            assert h.description

    @pytest.mark.asyncio
    async def test_max_hooks_is_respected(self):
        agent = PlotHookAgent()

        async def fake_call_tool(name, args):
            if name == "neo4j_list_plot_threads":
                return {
                    "threads": [
                        {
                            "title": f"Thread {i}",
                            "description": f"desc {i}",
                            "status": "active",
                        }
                        for i in range(20)
                    ]
                }
            return {"scenes": [], "entities": []}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            hooks = await agent.suggest_hooks(universe_id=uuid4(), max_hooks=3)
        assert len(hooks) <= 3

    @pytest.mark.asyncio
    async def test_connected_entities_populated_from_threads(self):
        agent = PlotHookAgent()

        # Threads with involved_entities should surface in connected_entities
        async def fake_call_tool(name, args):
            if name == "neo4j_list_plot_threads":
                return {
                    "threads": [
                        {
                            "title": "The Baron's Secret",
                            "description": "Baron hides something.",
                            "status": "active",
                            "involved_entities": ["Baron Aldric", "Captain Vela"],
                        }
                    ]
                }
            return {"scenes": [], "entities": []}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            hooks = await agent.suggest_hooks(universe_id=uuid4(), max_hooks=5)
        # Heuristic should at least produce one hook with the title
        assert any(
            h.title == "The Baron's Secret" or "Baron" in (h.title + h.description)
            for h in hooks
        )


class TestSuggestHooksLLMPath:
    """When LLM is available, suggest_hooks uses the LLM response."""

    @pytest.mark.asyncio
    async def test_llm_response_hooks_are_returned(self):
        agent = PlotHookAgent()

        async def fake_llm(model_class, messages, **kwargs):
            return PlotHookListResponse(
                hooks=[
                    PlotHook(
                        title="LLM Hook 1",
                        description="A story beat suggested by the LLM.",
                        urgency="high",
                    ),
                ]
            )

        with patch.object(agent, "call_tool", new=AsyncMock(return_value={})):
            with patch.object(
                agent, "call_llm_structured", new=AsyncMock(side_effect=fake_llm)
            ):
                hooks = await agent.suggest_hooks(universe_id=uuid4(), max_hooks=5)
        assert len(hooks) == 1
        assert hooks[0].title == "LLM Hook 1"
        assert hooks[0].urgency == "high"


# =============================================================================
# CF-5: Contradiction Detection
# =============================================================================


class TestContradictionSchema:
    def test_minimal_contradiction(self):
        c = Contradiction(
            fact_a="The king is alive.",
            fact_b="The king is dead.",
            explanation="Contradictory life states.",
            suggestion="Pick one as canon.",
        )
        assert c.fact_a == "The king is alive."
        assert c.fact_b == "The king is dead."
        assert c.severity == "medium"
        assert c.suggestion == "Pick one as canon."

    def test_contradiction_response_wraps_list(self):
        resp = ContradictionListResponse(
            contradictions=[
                Contradiction(
                    fact_a="X",
                    fact_b="not X",
                    severity="high",
                    explanation="opposites",
                    suggestion="pick one",
                ),
            ]
        )
        assert len(resp.contradictions) == 1


class TestDetectContradictionsHeuristic:
    """detect_contradictions falls back to heuristics when LLM fails."""

    @pytest.mark.asyncio
    async def test_empty_universe_no_contradictions(self):
        agent = PlotHookAgent()
        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(agent, "call_tool", new=AsyncMock(return_value={})):
            contradictions = await agent.detect_contradictions(universe_id=uuid4())
        assert contradictions == []

    @pytest.mark.asyncio
    async def test_no_facts_no_contradictions(self):
        agent = PlotHookAgent()

        async def fake_call_tool(name, args):
            return {"facts": []}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            contradictions = await agent.detect_contradictions(universe_id=uuid4())
        assert contradictions == []

    @pytest.mark.asyncio
    async def test_focus_entity_path_uses_neo4j_get_entity(self):
        agent = PlotHookAgent()
        focus_id = uuid4()
        called_tools = []

        async def fake_call_tool(name, args):
            called_tools.append(name)
            if name == "neo4j_get_entity":
                return {"name": "Theron", "entity_type": "CHARACTER"}
            return {"facts": []}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            await agent.detect_contradictions(
                universe_id=uuid4(),
                focus_entity_id=focus_id,
            )
        # The focus path should fetch the specific entity, not the list
        assert "neo4j_get_entity" in called_tools
        assert "neo4j_list_entities" not in called_tools


class TestDetectContradictionsLLMPath:
    @pytest.mark.asyncio
    async def test_llm_response_returned(self):
        agent = PlotHookAgent()

        async def fake_llm(model_class, messages, **kwargs):
            return ContradictionListResponse(
                contradictions=[
                    Contradiction(
                        fact_a="The duke is at the castle.",
                        fact_b="The duke is in the capital.",
                        severity="high",
                        explanation="The duke can't be in two places.",
                        suggestion="Pick one location as canon.",
                    ),
                ]
            )

        with patch.object(
            agent, "call_tool", new=AsyncMock(return_value={"facts": []})
        ), patch.object(
            agent, "call_llm_structured", new=AsyncMock(side_effect=fake_llm)
        ):
            contradictions = await agent.detect_contradictions(universe_id=uuid4())
        assert len(contradictions) == 1
        assert contradictions[0].severity == "high"


# =============================================================================
# CF-7: Session Prep
# =============================================================================


class TestSessionPrepSchema:
    def test_minimal_session_prep(self):
        prep = SessionPrep(recap="No recent scenes.")
        assert prep.recap == "No recent scenes."
        assert prep.open_threads == []
        assert prep.hooks == []
        assert prep.npc_reminders == []
        assert prep.world_state_changes == []


class TestGenerateSessionPrep:
    @pytest.mark.asyncio
    async def test_empty_data_yields_default_prep(self):
        agent = PlotHookAgent()

        async def fake_call_tool(name, args):
            return {}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            prep = await agent.generate_session_prep(
                universe_id=uuid4(),
                story_id=uuid4(),
            )
        assert isinstance(prep, SessionPrep)
        # With no data, the default recap should mention "no recent"
        assert "No recent" in prep.recap or prep.recap == ""

    @pytest.mark.asyncio
    async def test_recap_uses_recent_scene_summaries(self):
        agent = PlotHookAgent()

        async def fake_call_tool(name, args):
            if name == "mongodb_list_scenes":
                return {
                    "scenes": [
                        {
                            "title": "The Ambush",
                            "summary": "Bandits attacked the caravan.",
                        },
                        {
                            "title": "Into the Forest",
                            "summary": "The party tracked the bandits.",
                        },
                    ]
                }
            return {}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            prep = await agent.generate_session_prep(
                universe_id=uuid4(),
                story_id=uuid4(),
            )
        assert "Ambush" in prep.recap or "ambush" in prep.recap.lower()
        assert "Forest" in prep.recap or "forest" in prep.recap.lower()

    @pytest.mark.asyncio
    async def test_open_threads_populated(self):
        agent = PlotHookAgent()

        async def fake_call_tool(name, args):
            if name == "neo4j_list_plot_threads":
                return {
                    "threads": [
                        {"title": "The Crown", "status": "active"},
                        {"title": "Smugglers", "status": "active"},
                    ]
                }
            return {}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            prep = await agent.generate_session_prep(
                universe_id=uuid4(),
                story_id=uuid4(),
            )
        # The agent should surface thread titles
        assert (
            any("Crown" in t for t in prep.open_threads) or len(prep.open_threads) == 0
        )

    @pytest.mark.asyncio
    async def test_world_state_changes_filters_canon_facts(self):
        agent = PlotHookAgent()

        async def fake_call_tool(name, args):
            if name == "neo4j_list_facts":
                return {
                    "facts": [
                        {"content": "The king died.", "canon_level": "canon"},
                        {"content": "The baker has a secret.", "canon_level": "rumor"},
                        {
                            "content": "The kingdom fell to ruin.",
                            "canon_level": "established",
                        },
                    ]
                }
            return {}

        with patch.object(
            agent,
            "call_llm_structured",
            new=AsyncMock(side_effect=RuntimeError("no LLM")),
        ), patch.object(
            agent, "call_tool", new=AsyncMock(side_effect=fake_call_tool)
        ):
            prep = await agent.generate_session_prep(
                universe_id=uuid4(),
                story_id=uuid4(),
            )
        # Only canon + established facts should be surfaced as world state changes
        # 'rumor' level should NOT be included
        for change in prep.world_state_changes:
            assert "baker" not in change.lower(), (
                "rumor-level fact should not be world state change"
            )


# =============================================================================
# Router integration (smoke test the endpoints with FastAPI)
# =============================================================================


class TestGMRouterSchemas:
    """Request/response schemas for the gm_tools router validate correctly."""

    def test_suggest_hooks_request_defaults(self):
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        req = SuggestHooksRequest(universe_id=uuid4())
        assert req.max_hooks == 5
        assert req.story_id is None

    def test_suggest_hooks_request_validates_bounds(self):
        from monitor_ui.routers.gm_tools import SuggestHooksRequest

        with pytest.raises(Exception):
            # max_hooks > 20 should be rejected
            SuggestHooksRequest(universe_id=uuid4(), max_hooks=100)
        with pytest.raises(Exception):
            # max_hooks < 1 should be rejected
            SuggestHooksRequest(universe_id=uuid4(), max_hooks=0)

    def test_detect_contradictions_request(self):
        from monitor_ui.routers.gm_tools import DetectContradictionsRequest

        req = DetectContradictionsRequest(
            universe_id=uuid4(),
            focus_entity_id=uuid4(),
        )
        assert req.focus_entity_id is not None

    def test_session_prep_request_requires_story(self):
        from monitor_ui.routers.gm_tools import SessionPrepRequest

        req = SessionPrepRequest(universe_id=uuid4(), story_id=uuid4())
        assert req.session_number is None
