"""
Tests for GMAgent (T3).

Coverage:
- GMVerdict parsing utilities (gmverdict_from_prediction /
  gmverdict_from_awareness) shape correctly across all field types.
- The fallback seed path: when ReAct raises, GMAgent falls back to
  GMAwarenessModule and produces a structured verdict.
- The ReAct loop's tool-call accounting is captured.
- decide() never raises — even on a worst-case failure it returns a
  structured GMVerdict.

The ReAct loop itself needs a real (or _FakeLM) DSPy context to run; we
test it indirectly via the public decide() method with patched internals.
The full ReAct-flow end-to-end test lives in T8 (live sessions).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_agents.gm_agent import (
    GMAgent,
    _trajectory_tool_calls,
    default_gm_agent,
    gmverdict_from_awareness,
    gmverdict_from_prediction,
    reset_gm_agent,
)
from monitor_agents.gm_awareness import (
    ActionType,
    CausalityAction,
    GMAwareness,
    IntentType,
    RollNecessity,
)

# ============================================================================
# Helpers
# ============================================================================


def _fake_trajectory(*tool_calls: tuple[str, str]) -> dict[str, Any]:
    """Build a ReAct trajectory dict from a sequence of (name, observation)."""
    trajectory: dict[str, Any] = {}
    for i, (name, obs) in enumerate(tool_calls):
        trajectory[f"thought_{i}"] = f"calling {name}"
        trajectory[f"tool_name_{i}"] = name
        trajectory[f"tool_args_{i}"] = {}
        trajectory[f"observation_{i}"] = obs
    return trajectory


def _fake_prediction(**fields: Any) -> Any:
    """Build a dspy.Prediction-like object with optional trajectory."""

    class _P:
        def __init__(self):
            self.trajectory = fields.pop("trajectory", None) or {}

    p = _P()
    for k, v in fields.items():
        setattr(p, k, v)
    return p


def _scene_context() -> dict[str, Any]:
    return {
        "entities": [
            {"name": "Barnaby the Innkeeper", "entity_type": "character"},
            {"name": "The Shadow Cabal", "entity_type": "faction"},
        ],
        "turns": [
            {"speaker": "GM", "text": "Welcome to Millhaven."},
            {"speaker": "PLAYER", "text": "I step into the inn."},
        ],
    }


# ============================================================================
# Trajectory parsing
# ============================================================================


def test_trajectory_tool_calls_counts_names_and_failures() -> None:
    trajectory = _fake_trajectory(
        ("get_scene_state", '{"status": "ok"}'),
        ("roll_dice", '{"total": 14}'),
        ("list_playable_actions", "Execution error in list_playable_actions: timeout"),
        ("finish", "Completed."),
    )
    names, count, failures = _trajectory_tool_calls(trajectory)
    assert count == 4
    assert names == ["get_scene_state", "roll_dice", "list_playable_actions", "finish"]
    assert len(failures) == 1
    assert "list_playable_actions" in failures[0]


def test_trajectory_tool_calls_empty_trajectory() -> None:
    names, count, failures = _trajectory_tool_calls({})
    assert count == 0
    assert names == []
    assert failures == []


# ============================================================================
# Verdict construction
# ============================================================================


def test_gmverdict_from_prediction_parses_all_fields() -> None:
    pred = _fake_prediction(
        intent_type="action",
        action_type="combat",
        roll_necessity="contested",
        causality_action="PUSH_BACK",
        suggested_stat="STR",
        suggested_dc=15,
        subsystem_hint="combat",
        declares_outcome=True,
        pushback_prompt="Roll for it.",
        narrative_draft="You swing.",
        reasoning="because",
        trajectory=_fake_trajectory(("roll_dice", '{"total": 14}')),
    )
    v = gmverdict_from_prediction(pred, upstream_action_context={"stat_name": "STR", "subsystem_hint": "combat"})
    assert v.intent_type == IntentType.ACTION
    assert v.action_type == ActionType.COMBAT
    assert v.roll_necessity == RollNecessity.CONTESTED
    assert v.causality_action == CausalityAction.PUSH_BACK
    assert v.suggested_stat == "STR"
    assert v.suggested_dc == 15
    assert v.subsystem_hint == "combat"
    assert v.declares_outcome is True
    assert v.pushback_prompt == "Roll for it."
    assert v.narrative_draft == "You swing."
    assert v.tool_calls_made == ["roll_dice"]
    assert v.tool_call_count == 1
    assert v.action_route == {"stat_name": "STR", "subsystem_hint": "combat"}


def test_gmverdict_falls_back_to_upstream_subsystem_hint() -> None:
    pred = _fake_prediction(
        intent_type="action",
        action_type="exploration",
        roll_necessity="trivial",
        causality_action="ACCEPT",
        subsystem_hint="none",  # LLM returned "none" — fall back to upstream.
        suggested_dc=12,
        suggested_stat="none",
        declares_outcome=False,
        pushback_prompt="",
        narrative_draft="You look.",
        reasoning="",
        trajectory={},
    )
    v = gmverdict_from_prediction(pred, upstream_action_context={"subsystem_hint": "ship"})
    assert v.subsystem_hint == "ship"


def test_gmverdict_invalid_enum_falls_back_to_safe_default() -> None:
    pred = _fake_prediction(
        intent_type="totally-not-an-intent",
        action_type="made-up",
        roll_necessity="nonsense",
        causality_action="WHATEVER",
        suggested_stat="none",
        suggested_dc=0,
        subsystem_hint="none",
        declares_outcome=False,
        pushback_prompt="",
        narrative_draft="",
        reasoning="",
        trajectory={},
    )
    v = gmverdict_from_prediction(pred)
    # Falls back to defaults — safe ACTION / NONE / PROPOSE_ROLL / ACCEPT.
    assert v.intent_type == IntentType.ACTION
    assert v.action_type == ActionType.NONE
    assert v.roll_necessity == RollNecessity.PROPOSE_ROLL
    assert v.causality_action == CausalityAction.ACCEPT


def test_gmverdict_dc_zero_renders_as_none() -> None:
    pred = _fake_prediction(
        intent_type="dialogue",
        action_type="dialogue",
        roll_necessity="trivial",
        causality_action="ACCEPT",
        suggested_stat="CHA",
        suggested_dc=0,  # zero means "no roll"
        subsystem_hint="social",
        declares_outcome=False,
        pushback_prompt="",
        narrative_draft="",
        reasoning="",
        trajectory={},
    )
    v = gmverdict_from_prediction(pred)
    assert v.suggested_dc is None


def test_gmverdict_from_awareness_basic() -> None:
    aw = GMAwareness(
        intent_type=IntentType.ACTION,
        action_type=ActionType.COMBAT,
        roll_necessity=RollNecessity.CONTESTED,
        declares_outcome=False,
        violates_causality=False,
        action=CausalityAction.ACCEPT,
        suggested_stat="DEX",
        suggested_dc=13,
        reasoning="fast reflexes",
    )
    v = gmverdict_from_awareness(aw)
    assert v.intent_type == IntentType.ACTION
    assert v.action_type == ActionType.COMBAT
    assert v.suggested_stat == "DEX"
    assert v.suggested_dc == 13
    assert v.reasoning == "fast reflexes"
    assert v.tool_call_count == 0


# ============================================================================
# GMAgent.decide — never-raise contract
# ============================================================================


@pytest.mark.asyncio
async def test_decide_returns_fallback_on_react_failure() -> None:
    """If ReAct raises, GMAgent falls through to GMAwarenessModule."""
    agent = GMAgent()

    # Stub the ReAct module to raise.
    agent._react_module = MagicMock(side_effect=RuntimeError("dspy fail"))

    # And stub check_gm_awareness to return a deterministic seed verdict.
    seed = GMAwareness(
        intent_type=IntentType.ACTION,
        action_type=ActionType.EXPLORATION,
        roll_necessity=RollNecessity.TRIVIAL,
        declares_outcome=False,
        violates_causality=False,
        action=CausalityAction.ACCEPT,
        suggested_stat="WIT",
        suggested_dc=12,
        reasoning="seed fallback",
    )

    with patch("monitor_agents.gm_agent.check_gm_awareness", AsyncMock(return_value=seed)):
        verdict = await agent.decide(
            scene_id="scene-1",
            user_input="I look around.",
            scene_context=_scene_context(),
            established_facts=["Elder Magda vanished."],
        )
    assert verdict.intent_type == IntentType.ACTION
    assert verdict.action_type == ActionType.EXPLORATION
    assert verdict.roll_necessity == RollNecessity.TRIVIAL
    assert verdict.reasoning == "seed fallback"
    assert verdict.tool_call_count == 0


@pytest.mark.asyncio
async def test_decide_never_raises() -> None:
    """Worst-case: everything blows up. GMAgent returns a structured fallback verdict."""
    agent = GMAgent()
    agent._react_module = MagicMock(side_effect=RuntimeError("boom"))

    async def _also_fail(*_args, **_kwargs):
        raise RuntimeError("seed also failed")

    with patch("monitor_agents.gm_agent.check_gm_awareness", side_effect=_also_fail):
        # The seed-fallback path catches its own errors and returns a
        # structured verdict — the *outer* decide() should still succeed.
        verdict = await agent.decide(
            scene_id="scene-1",
            user_input="anything",
            scene_context={"entities": [], "turns": []},
        )
    assert verdict.intent_type == IntentType.ACTION
    assert verdict.causality_action == CausalityAction.ACCEPT
    # Reasoning mentions the failure — observability.
    assert "failed" in verdict.reasoning.lower() or "unreachable" in verdict.reasoning.lower()


@pytest.mark.asyncio
async def test_decide_propagates_subsystem_hint_from_upstream() -> None:
    """When ReAct returns subsystem_hint='none', fall back to upstream_action_context."""
    agent = GMAgent()

    pred = _fake_prediction(
        intent_type="action",
        action_type="combat",
        roll_necessity="contested",
        causality_action="ACCEPT",
        suggested_stat="STR",
        suggested_dc=13,
        subsystem_hint="none",  # LLM didn't decide
        declares_outcome=False,
        pushback_prompt="",
        narrative_draft="You swing.",
        reasoning="",
        trajectory=_fake_trajectory(),
    )

    def _react(*_args, **_kwargs):
        return pred

    agent._react_module = MagicMock(side_effect=_react)

    verdict = await agent.decide(
        scene_id="scene-1",
        user_input="I attack.",
        scene_context=_scene_context(),
        upstream_action_context={"stat_name": "STR", "subsystem_hint": "combat"},
    )
    assert verdict.subsystem_hint == "combat"


# ============================================================================
# Singleton lifecycle
# ============================================================================


def test_default_gm_agent_singleton() -> None:
    reset_gm_agent()
    a = default_gm_agent()
    b = default_gm_agent()
    assert a is b


def test_reset_gm_agent_drops_singleton() -> None:
    reset_gm_agent()
    a = default_gm_agent()
    reset_gm_agent()
    b = default_gm_agent()
    assert a is not b
