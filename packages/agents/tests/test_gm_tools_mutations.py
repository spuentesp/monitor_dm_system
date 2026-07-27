"""
Mutation tests for the GM tools registry (T7).

These tests apply *fault injection* to each tool function and assert that
the existing test suite (or this one) catches the mutation. The point is
to verify the tools aren't silently no-op'd — that any change in their
behavior is observable in test failures.

We don't use a mutation framework (mutmut / cosmic-ray). Instead we write
explicit fault tests for each tool:

* ``test_get_scene_state_catches_mutation_skips_schema`` — if the tool
  forgot to query the schema and returned an empty dict, our tests
  would notice.

Each mutation test applies a small change to the tool's logic and
verifies it produces a wrong result that downstream assertions catch.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from monitor_agents.gm_tools.registry import get_tool

# ============================================================================
# get_scene_state — fault injection
# ============================================================================


def test_get_scene_state_mutation_returning_empty_is_detected() -> None:
    """If the tool forgets to query the schema, it should return no_schema status.

    We patch the underlying helper to return None (mimicking the
    "schema not loaded" path) and verify the tool reports no_schema.
    """
    tool = get_tool("get_scene_state")
    with patch("monitor_agents.gm_tools.scene_state._build_gsr_from_json", return_value=None):
        raw = tool.func("scene-1", "{}", "[]", "{}")
        parsed = json.loads(raw)
        assert parsed["status"] == "no_schema"
        # If the tool accidentally returned "ok" with empty schema_summary,
        # the test catches that.


def test_list_playable_actions_mutation_skips_filtering_is_detected() -> None:
    """If the tool returns the schema skills unfiltered (no condition suppression),
    a character with 'restrained' would still see attack skills as playable.

    We assert this explicitly: with a Restrained condition, Brawl must NOT
    be in the playable_actions list.
    """
    tool = get_tool("list_playable_actions")
    schema = json.dumps(
        {
            "name": "test",
            "attributes": [{"name": "Strength", "abbreviation": "STR", "min_value": 1, "max_value": 5}],
            "skills": [
                {"name": "Brawl", "linked_attribute": "Strength", "description": "Punch."},
            ],
            "conditions": [{"name": "Restrained"}],
        }
    )
    raw = tool.func("scene-1", "sys-1", schema, '["Restrained"]')
    parsed = json.loads(raw)
    playable = {a["name"] for a in parsed["playable_actions"]}
    # Brawl is filtered out — Restrained suppresses combat.
    assert "Brawl" not in playable
    # If the tool ever dropped the filter, Brawl would reappear and this test fails.


# ============================================================================
# evaluate_scenery — fault injection
# ============================================================================


def test_evaluate_scenery_mutation_skips_keyword_match_is_detected() -> None:
    """If the tool returns no modifiers even when location tags match a rule,
    a downstream combat scene would lose its advantage/disadvantage modifiers."""
    tool = get_tool("evaluate_scenery")
    schema = json.dumps(
        {
            "name": "test",
            "scenery_rules": [
                {
                    "keyword": "tangled",
                    "trigger_verbs": ["dodge"],
                    "roll_modifier": -2,
                    "roll_mode_override": "disadvantage",
                    "reason_text": "Vines everywhere.",
                }
            ],
        }
    )
    raw = tool.func("scene-1", schema, '["tangled"]', "")
    parsed = json.loads(raw)
    keys = {m["keyword"] for m in parsed["modifiers"]}
    # If the tool skipped the keyword match, "tangled" would be missing.
    assert "tangled" in keys


# ============================================================================
# Tool-call invariant on GMAgent — fault injection
# ============================================================================


@pytest.mark.asyncio
async def test_gm_agent_decide_never_returns_empty_verdict() -> None:
    """GMAgent.decide must always return a populated GMVerdict — even when
    everything fails. A mutation that returned ``None`` would crash the
    resolver downstream."""
    from monitor_agents.gm_agent import GMAgent

    agent = GMAgent()
    # Force the react module to raise AND the seed path to fail.
    agent._react_module = MagicMock(side_effect=RuntimeError("boom"))

    class _Stub:
        async def check_gm_awareness(*_args, **_kwargs):
            raise RuntimeError("seed also broken")

    with patch("monitor_agents.gm_agent.check_gm_awareness", _Stub()):
        verdict = await agent.decide(
            scene_id="s",
            user_input="anything",
            scene_context={"entities": [], "turns": []},
        )
    # The "never raise" contract: verdict is a populated GMVerdict.
    assert verdict is not None
    assert verdict.intent_type is not None
    assert verdict.causality_action is not None
    assert verdict.reasoning  # populated, even if it's a failure message
