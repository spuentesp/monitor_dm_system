"""
Property-based tests for the GM tools registry (T7 contract surface).

These tests use ``hypothesis`` to fuzz the tool inputs and assert
*invariants* — properties the tools must satisfy regardless of input.
Properties are stronger than example-based tests because they assert
behavior across the whole input space, not just hand-picked cases.

Properties verified:
- ``get_scene_state`` always returns a dict with ``scene_id``, ``status``.
- ``list_playable_actions`` always returns a dict with ``scene_id`` and
  ``playable_actions`` list — never raises on weird schemas.
- ``evaluate_scenery`` always returns a dict with ``scene_id`` and
  ``modifiers`` list.
- ``roll_dice`` always returns a dict with ``formula`` and either
  ``total`` or ``error``.
- ``resolve_oracle`` always returns a dict with ``question`` key.

These are invariant-style tests; they're meant to catch "the tool
silently changed shape" regressions.
"""

from __future__ import annotations

import json
import string

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from monitor_agents.gm_tools.registry import get_tool

# ============================================================================
# Strategies
# ============================================================================

_safe_text = st.text(
    alphabet=string.ascii_letters + string.digits + " .,!?'\"",
    min_size=0,
    max_size=120,
)
_safe_int = st.integers(min_value=-50, max_value=200)


# ============================================================================
# get_scene_state — always returns a dict with the right shape
# ============================================================================


@given(
    scene_id=_safe_text,
    game_context_json=st.one_of(st.just(""), st.just("not json"), st.just("{}"), st.just('{"x": 1}')),
    active_conditions_json=st.one_of(st.just("[]"), st.just("not json"), st.just('["A","B"]')),
    working_resources_json=st.one_of(st.just("{}"), st.just("not json"), st.just('{"HP": 5}')),
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_get_scene_state_never_raises_and_has_required_keys(
    scene_id: str,
    game_context_json: str,
    active_conditions_json: str,
    working_resources_json: str,
) -> None:
    tool = get_tool("get_scene_state")
    raw = tool.func(scene_id, game_context_json, active_conditions_json, working_resources_json)
    parsed = json.loads(raw)
    assert "scene_id" in parsed
    assert "status" in parsed
    assert parsed["scene_id"] == scene_id
    assert parsed["status"] in {"ok", "no_schema"}


# ============================================================================
# list_playable_actions — always returns a dict with playable_actions list
# ============================================================================


@given(
    scene_id=_safe_text,
    system_id=_safe_text,
    game_context_json=st.one_of(st.just(""), st.just("not json"), st.just("{}"), st.just('{"x":1}')),
    active_conditions_json=st.one_of(st.just("[]"), st.just("not json"), st.just('["restrained"]')),
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_list_playable_actions_never_raises_and_has_list(
    scene_id: str,
    system_id: str,
    game_context_json: str,
    active_conditions_json: str,
) -> None:
    tool = get_tool("list_playable_actions")
    raw = tool.func(scene_id, system_id, game_context_json, active_conditions_json)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    assert parsed["scene_id"] == scene_id
    assert isinstance(parsed["playable_actions"], list)
    assert isinstance(parsed["unavailable_actions"], list)
    # Every playable action has at minimum a name.
    for a in parsed["playable_actions"]:
        assert "name" in a


# ============================================================================
# evaluate_scenery — always returns a dict with modifiers list
# ============================================================================


@given(
    scene_id=_safe_text,
    game_context_json=st.one_of(st.just(""), st.just("not json"), st.just("{}")),
    location_tags_json=st.one_of(st.just("[]"), st.just("not json"), st.just('["tangled"]')),
    location_description=_safe_text,
)
@settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_evaluate_scenery_never_raises_and_has_modifiers_list(
    scene_id: str,
    game_context_json: str,
    location_tags_json: str,
    location_description: str,
) -> None:
    tool = get_tool("evaluate_scenery")
    raw = tool.func(scene_id, game_context_json, location_tags_json, location_description)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    assert parsed["scene_id"] == scene_id
    assert isinstance(parsed["modifiers"], list)


# ============================================================================
# roll_dice — returns a dict, formula is preserved
# ============================================================================


@given(formula=st.sampled_from(["1d20", "3d6", "1d20+5", "2d20kh1", "d6"]), modifier=_safe_int)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_roll_dice_returns_dict_with_formula_or_error(formula: str, modifier: int) -> None:
    tool = get_tool("roll_dice")
    raw = tool.func(formula, modifier)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    assert parsed["formula"] == formula
    assert parsed["modifier"] == modifier
    # Either total (success) or error (failure) — always one of the two.
    assert "total" in parsed or "error" in parsed


# ============================================================================
# resolve_oracle — returns dict with question
# ============================================================================


@given(
    question=_safe_text,
    likelihood=st.sampled_from(
        [
            "nearly_certain",
            "very_likely",
            "likely",
            "fifty_fifty",
            "unlikely",
            "very_unlikely",
            "nearly_impossible",
            "certain",
            "impossible",
            "bogus_value",
        ]
    ),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_resolve_oracle_never_raises_and_has_question(
    question: str,
    likelihood: str,
) -> None:
    tool = get_tool("resolve_oracle")
    raw = tool.func(question, likelihood, 0.5)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    assert parsed["question"] == question
