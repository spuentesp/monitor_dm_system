"""Behavior tests for PlotHookAgent (Phase 4 - GM Assistant).

Exercises pure helper methods and schemas — no LLM, no MCP.

Covers:
- _parse_result (handles JSON strings, dicts, errors)
- _heuristic_hooks (threads → hooks, state tags → hooks)
- _heuristic_contradictions (negation detection)
- Schema defaults and validation
"""
from __future__ import annotations

import json
from typing import Any, Dict, List
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# Test fixtures
# =============================================================================


def _make_agent() -> Any:
    """Create a PlotHookAgent, skipping __init__ for unit testing."""
    from monitor_agents.plot_hooks import PlotHookAgent

    agent = PlotHookAgent.__new__(PlotHookAgent)
    return agent


# =============================================================================
# _parse_result
# =============================================================================


class TestParseResult:
    def test_dict_with_key(self):
        agent = _make_agent()
        result = agent._parse_result({"threads": ["a", "b"]}, "threads", [])
        assert result == ["a", "b"]

    def test_dict_missing_key_returns_default(self):
        agent = _make_agent()
        result = agent._parse_result({}, "missing", ["default"])
        assert result == ["default"]

    def test_json_string_parses(self):
        agent = _make_agent()
        payload = json.dumps({"threads": ["x", "y"]})
        result = agent._parse_result(payload, "threads", [])
        assert result == ["x", "y"]

    def test_invalid_json_returns_default(self):
        agent = _make_agent()
        result = agent._parse_result("not valid json", "key", "fallback")
        assert result == "fallback"

    def test_non_dict_non_str_returns_default(self):
        agent = _make_agent()
        result = agent._parse_result(42, "key", "default")
        assert result == "default"

    def test_dict_with_dict_key_returns_dict(self):
        agent = _make_agent()
        result = agent._parse_result({"a": 1, "b": 2}, {}, "default")
        # Empty dict means "return whole result"
        assert result == {"a": 1, "b": 2}


# =============================================================================
# _heuristic_hooks
# =============================================================================


class TestHeuristicHooks:
    def test_thread_becomes_hook(self):
        agent = _make_agent()
        threads = [
            {
                "thread_id": "t1",
                "title": "Missing artifact",
                "description": "The crown was stolen",
                "involved_entities": ["Bandit King"],
            }
        ]
        hooks = agent._heuristic_hooks(threads, [], [], max_hooks=5)
        assert len(hooks) == 1
        assert hooks[0].thread_id == "t1"
        assert hooks[0].urgency == "high"
        assert hooks[0].suggested_scene_type == "revelation"
        assert "Bandit King" in hooks[0].connected_entities

    def test_entity_with_state_tags_becomes_hook(self):
        agent = _make_agent()
        entities = [
            {
                "name": "Villain",
                "entity_type": "npc",
                "state_tags": ["wounded", "fleeing"],
            }
        ]
        hooks = agent._heuristic_hooks([], [], entities, max_hooks=5)
        assert len(hooks) == 1
        assert "wounded" in hooks[0].description
        assert "fleeing" in hooks[0].description
        assert hooks[0].urgency == "medium"

    def test_entity_without_state_tags_ignored(self):
        agent = _make_agent()
        entities = [{"name": "Bystander", "entity_type": "npc", "state_tags": []}]
        hooks = agent._heuristic_hooks([], [], entities, max_hooks=5)
        assert hooks == []

    def test_max_hooks_respected(self):
        agent = _make_agent()
        threads = [{"thread_id": f"t{i}", "title": f"Thread {i}"} for i in range(10)]
        hooks = agent._heuristic_hooks(threads, [], [], max_hooks=3)
        assert len(hooks) == 3

    def test_threads_then_entities(self):
        agent = _make_agent()
        threads = [{"thread_id": "t1", "title": "T1"}]
        entities = [
            {"name": "E1", "state_tags": ["x"]},
            {"name": "E2", "state_tags": ["y"]},
        ]
        hooks = agent._heuristic_hooks(threads, [], entities, max_hooks=5)
        # 1 thread + 2 entities = 3 hooks
        assert len(hooks) == 3


# =============================================================================
# _heuristic_contradictions
# =============================================================================


class TestHeuristicContradictions:
    def test_no_facts_returns_empty(self):
        agent = _make_agent()
        assert agent._heuristic_contradictions([]) == []

    def test_single_fact_returns_empty(self):
        agent = _make_agent()
        facts = [{"entity_id": "e1", "content": "The door is open"}]
        assert agent._heuristic_contradictions(facts) == []

    def test_negation_contradiction_detected(self):
        # Heuristic: fact_a must contain a negation word ("not ", "never ", etc.)
        # and fact_b must not contain that word (no-space form). It also requires
        # that one of fact_a's first 3 words appear in fact_b.
        agent = _make_agent()
        facts = [
            {"entity_id": "e1", "content": "The bridge is not destroyed in the war"},
            {"entity_id": "e1", "content": "The bridge stands"},
        ]
        contradictions = agent._heuristic_contradictions(facts)
        # "not " in fact_a, "not" not in fact_b (true), and "the"/"bridge"/"is" in fact_b (true)
        assert len(contradictions) >= 1
        assert contradictions[0].severity == "medium"

    def test_no_contradiction_for_different_entities(self):
        agent = _make_agent()
        facts = [
            {"entity_id": "e1", "content": "The door is not locked"},
            {"entity_id": "e2", "content": "The door is locked"},
        ]
        # Different entities, should not flag
        assert agent._heuristic_contradictions(facts) == []

    def test_no_contradiction_for_consistent_facts(self):
        agent = _make_agent()
        facts = [
            {"entity_id": "e1", "content": "The door is locked"},
            {"entity_id": "e1", "content": "The door is also locked"},
        ]
        # No negation in fact_a, no contradiction
        assert agent._heuristic_contradictions(facts) == []

    def test_uses_text_field_fallback(self):
        agent = _make_agent()
        facts = [
            {"entity_id": "e1", "text": "The castle is not ruined by the siege"},
            {"entity_id": "e1", "text": "The castle stands"},
        ]
        contradictions = agent._heuristic_contradictions(facts)
        assert len(contradictions) >= 1


# =============================================================================
# Schemas
# =============================================================================


class TestPlotHookSchema:
    def test_minimal_construct(self):
        from monitor_agents.plot_hooks import PlotHook

        hook = PlotHook(title="Test", description="A test hook")
        assert hook.title == "Test"
        assert hook.description == "A test hook"
        assert hook.urgency == "medium"
        assert hook.suggested_scene_type == "exploration"
        assert hook.connected_entities == []
        assert hook.thread_id is None

    def test_full_construct(self):
        from monitor_agents.plot_hooks import PlotHook

        hook = PlotHook(
            thread_id="t1",
            title="Test",
            description="Desc",
            urgency="critical",
            suggested_scene_type="combat",
            connected_entities=["Goblin", "Troll"],
        )
        assert hook.thread_id == "t1"
        assert hook.urgency == "critical"
        assert "Goblin" in hook.connected_entities


class TestContradictionSchema:
    def test_minimal_construct(self):
        from monitor_agents.plot_hooks import Contradiction

        c = Contradiction(
            fact_a="A is true",
            fact_b="A is false",
            explanation="Contradicts",
            suggestion="Choose one",
        )
        assert c.fact_a == "A is true"
        assert c.fact_b == "A is false"
        assert c.severity == "medium"


class TestSessionPrepSchema:
    def test_minimal_construct(self):
        from monitor_agents.plot_hooks import SessionPrep

        prep = SessionPrep(recap="Last time...")
        assert prep.recap == "Last time..."
        assert prep.open_threads == []
        assert prep.hooks == []
        assert prep.npc_reminders == []
        assert prep.world_state_changes == []

    def test_full_construct(self):
        from monitor_agents.plot_hooks import SessionPrep, PlotHook

        prep = SessionPrep(
            recap="Recap",
            open_threads=["thread1"],
            hooks=[PlotHook(title="H1", description="D1")],
            npc_reminders=["NPC1"],
            world_state_changes=["bridge collapsed"],
        )
        assert len(prep.open_threads) == 1
        assert len(prep.hooks) == 1
        assert prep.hooks[0].title == "H1"


class TestPlotHookListResponse:
    def test_empty(self):
        from monitor_agents.plot_hooks import PlotHookListResponse

        resp = PlotHookListResponse()
        assert resp.hooks == []

    def test_with_hooks(self):
        from monitor_agents.plot_hooks import PlotHookListResponse, PlotHook

        resp = PlotHookListResponse(hooks=[PlotHook(title="H1", description="D1")])
        assert len(resp.hooks) == 1


class TestContradictionListResponse:
    def test_empty(self):
        from monitor_agents.plot_hooks import ContradictionListResponse

        resp = ContradictionListResponse()
        assert resp.contradictions == []
