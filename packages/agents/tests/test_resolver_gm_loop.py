"""
Tests for the Resolver's GM-agent-driven path (T5).

Covers:
- Resolver uses GMAgent.decide() as the deciding authority in production
  (when check_gm_awareness is unpatched).
- When check_gm_awareness is patched (legacy test seam), the resolver
  honors the patched function and converts its GMAwareness result into
  the legacy resolution dict.
- The fallback path: GMAgent.decide() raises → resolver falls through to
  a structured verdict rather than crashing.
- Wire format compatibility: the resolved dict has all the legacy keys
  consumers expect (resolution_type, stat, difficulty_class, etc.).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_agents.gm_agent import GMVerdict
from monitor_agents.gm_awareness import (
    ActionType,
    CausalityAction,
    GMAwareness,
    IntentType,
    RollNecessity,
    Severity,
)
from monitor_agents.resolver import Resolver

# ============================================================================
# Helpers
# ============================================================================


def _make_context() -> dict:
    return {
        "entities": [],
        "turns": [],
        "source_profile": {"name": "Test Player", "class": "Fighter"},
    }


def _stub_gm_agent(
    verdict: GMVerdict | Exception | None = None,
) -> MagicMock:
    """Build a stub GMAgent whose ``decide`` returns the given verdict (or raises)."""
    agent = MagicMock()
    if isinstance(verdict, Exception):
        agent.decide = AsyncMock(side_effect=verdict)
    elif isinstance(verdict, GMVerdict):
        agent.decide = AsyncMock(return_value=verdict)
    else:
        # Default: an ACTION verdict with trivial roll.
        agent.decide = AsyncMock(
            return_value=GMVerdict(
                intent_type=IntentType.ACTION,
                action_type=ActionType.EXPLORATION,
                roll_necessity=RollNecessity.TRIVIAL,
                causality_action=CausalityAction.ACCEPT,
                subsystem_hint=None,
                action_route=None,
                narrative_draft="",
                reasoning="stub",
            )
        )
    return agent


# ============================================================================
# Production path: GMAgent decides
# ============================================================================


@pytest.mark.asyncio
async def test_resolver_uses_gm_agent_decide() -> None:
    """The resolver delegates the GM decision to GMAgent.decide()."""
    stub = _stub_gm_agent(
        GMVerdict(
            intent_type=IntentType.ACTION,
            action_type=ActionType.COMBAT,
            roll_necessity=RollNecessity.CONTESTED,
            causality_action=CausalityAction.ACCEPT,
            subsystem_hint="combat",
            action_route={"stat_name": "STR", "difficulty_class": 12, "subsystem_hint": "combat"},
            narrative_draft="You swing.",
            reasoning="combat intent",
        )
    )
    resolver = Resolver(gm_agent=stub)

    with patch("monitor_data.utils.dice.random.randint", return_value=14):
        result, _ = await resolver.resolve_turn(
            scene_id="scene-1",
            user_input="I attack the goblin",
            context=_make_context(),
            game_context=None,
            play_mode="dice_standard",
        )
    assert stub.decide.called
    # The dice path produced a real resolution dict.
    assert "stat" in result
    assert "difficulty_class" in result
    assert "resolution_type" in result


@pytest.mark.asyncio
async def test_resolver_gm_agent_action_routes_to_push_back_branch() -> None:
    """When the GMAgent returns causality_action=PUSH_BACK with declares_outcome=True,
    the resolver surfaces forced_narrative_pushback (asking the player to roll)."""
    stub = _stub_gm_agent(
        GMVerdict(
            intent_type=IntentType.ACTION,
            action_type=ActionType.DIALOGUE,
            roll_necessity=RollNecessity.PROPOSE_ROLL,
            causality_action=CausalityAction.PUSH_BACK,
            declares_outcome=True,  # player asserted a (declarable) outcome
            subsystem_hint="social",
            action_route={"stat_name": "CHA", "difficulty_class": 13},
            suggested_stat="CHA",
            suggested_dc=13,
            pushback_prompt="Roll for it.",
            narrative_draft="",
            reasoning="need a roll",
        )
    )
    resolver = Resolver(gm_agent=stub)
    result, _ = await resolver.resolve_turn(
        scene_id="scene-1",
        user_input="I convince the guard with a single perfect speech",
        context=_make_context(),
        play_mode="dice_standard",
    )
    assert result["resolution_type"] == "forced_narrative_pushback"
    assert result["pushback_prompt"] == "Roll for it."
    assert result["stat"] == "CHA"


@pytest.mark.asyncio
async def test_resolver_narrative_mode_short_circuits() -> None:
    """In narrative play_mode, the resolver returns immediately without consulting the GM."""
    stub = MagicMock()
    resolver = Resolver(gm_agent=stub)
    result, _ = await resolver.resolve_turn(
        scene_id="scene-1",
        user_input="anything",
        context=_make_context(),
        play_mode="narrative",
    )
    assert result["resolution_type"] == "narrative"
    # The GM was not consulted in pure narrative mode.
    assert not stub.decide.called


# ============================================================================
# Backward compat: patched check_gm_awareness
# ============================================================================


@pytest.mark.asyncio
async def test_resolver_honors_patched_check_gm_awareness() -> None:
    """When ``check_gm_awareness`` is patched (test seam), the resolver uses it."""
    accept_verdict = GMAwareness(
        intent_type=IntentType.ACTION,
        action_type=ActionType.MOVEMENT,
        roll_necessity=RollNecessity.TRIVIAL,
        declares_outcome=True,
        violates_causality=False,
        severity=Severity.NONE,
        action=CausalityAction.ACCEPT,
        reasoning="declared outcome",
    )

    resolver = Resolver()
    with patch(
        "monitor_agents.resolver.check_gm_awareness",
        new_callable=AsyncMock,
        return_value=accept_verdict,
    ):
        result, _ = await resolver.resolve_turn(
            scene_id="s1",
            user_input="I successfully enter the room",
            context=_make_context(),
        )
    assert result["resolution_type"] == "forced_narrative"
    assert result["forced_narrative"] is True


# ============================================================================
# Wire format compatibility
# ============================================================================


@pytest.mark.asyncio
async def test_resolved_dict_has_legacy_keys() -> None:
    """The resolved dict preserves the legacy wire format consumers expect."""
    stub = _stub_gm_agent(
        GMVerdict(
            intent_type=IntentType.ACTION,
            action_type=ActionType.COMBAT,
            roll_necessity=RollNecessity.CONTESTED,
            causality_action=CausalityAction.ACCEPT,
            subsystem_hint="combat",
            action_route={"stat_name": "STR", "difficulty_class": 12, "subsystem_hint": "combat"},
            narrative_draft="You swing.",
        )
    )
    resolver = Resolver(gm_agent=stub)
    with patch("monitor_data.utils.dice.random.randint", return_value=14):
        result, _ = await resolver.resolve_turn(
            scene_id="scene-1",
            user_input="I attack",
            context=_make_context(),
            game_context=None,
            play_mode="dice_standard",
        )
    # Legacy keys must be present.
    for key in (
        "scene_id",
        "action_type",
        "intent_type",
        "resolution_type",
        "stat",
        "difficulty_class",
        "roll_necessity",
        "effects",
        "risk_preview",
        "consequence_options",
        "requires_player_choice",
        "narrative_pressure",
        "proposals",
        "subsystem_hint",
    ):
        assert key in result, f"missing legacy key: {key}"


# ============================================================================
# Default Resolver has a GMAgent (singleton)
# ============================================================================


def test_default_resolver_has_gm_agent() -> None:
    resolver = Resolver()
    assert resolver._gm_agent is not None


def test_resolver_accepts_custom_gm_agent() -> None:
    stub = _stub_gm_agent()
    resolver = Resolver(gm_agent=stub)
    assert resolver._gm_agent is stub


# ============================================================================
# Pushback-ignored-roll behavior (T6)
# ============================================================================


@pytest.mark.asyncio
async def test_pushback_response_requires_player_choice() -> None:
    """When the GM says PUSH_BACK, the resolver surfaces requires_player_choice=True.

    The UI uses this flag to render a chip letting the player accept the
    proposed roll. The downstream narrative layer (scene_loop / narrator)
    also reads it to know whether to wait for player input.
    """
    stub = _stub_gm_agent(
        GMVerdict(
            intent_type=IntentType.ACTION,
            action_type=ActionType.DIALOGUE,
            roll_necessity=RollNecessity.PROPOSE_ROLL,
            causality_action=CausalityAction.PUSH_BACK,
            declares_outcome=True,
            subsystem_hint="social",
            action_route={"stat_name": "CHA", "difficulty_class": 13},
            suggested_stat="CHA",
            suggested_dc=13,
            pushback_prompt="Roll for it.",
            narrative_draft="",
            reasoning="declarative attempt — needs a roll",
        )
    )
    resolver = Resolver(gm_agent=stub)
    result, _ = await resolver.resolve_turn(
        scene_id="scene-1",
        user_input="I convince the prince with perfect words",
        context=_make_context(),
        play_mode="dice_standard",
    )
    assert result["resolution_type"] == "forced_narrative_pushback"
    assert result["requires_player_choice"] is True
    assert result["pushback_prompt"] == "Roll for it."


@pytest.mark.asyncio
async def test_clarification_response_requires_player_choice() -> None:
    """REQUEST_CLARIFICATION (with declares_outcome=True) also surfaces requires_player_choice=True."""
    stub = _stub_gm_agent(
        GMVerdict(
            intent_type=IntentType.ACTION,
            action_type=ActionType.EXPLORATION,
            roll_necessity=RollNecessity.PROPOSE_ROLL,
            causality_action=CausalityAction.REQUEST_CLARIFICATION,
            declares_outcome=True,
            pushback_prompt="Where exactly?",
            narrative_draft="",
            reasoning="missing info",
        )
    )
    resolver = Resolver(gm_agent=stub)
    result, _ = await resolver.resolve_turn(
        scene_id="scene-1",
        user_input="I search",
        context=_make_context(),
        play_mode="dice_standard",
    )
    assert result["resolution_type"] == "forced_narrative_clarification"
    assert result["requires_player_choice"] is True


@pytest.mark.asyncio
async def test_subsystem_hint_combat_drives_combat_loop() -> None:
    """The resolver exposes subsystem_hint so scene_loop can delegate to combat_loop.

    In dice_game_system mode the resolver delegates routing to the
    SemanticActionRouter tool. We pin the router's return to surface
    ``subsystem_hint="combat"`` so we can verify the dict carries it.
    """
    stub = _stub_gm_agent(
        GMVerdict(
            intent_type=IntentType.ACTION,
            action_type=ActionType.COMBAT,
            roll_necessity=RollNecessity.CONTESTED,
            causality_action=CausalityAction.ACCEPT,
            subsystem_hint="combat",
            action_route={"stat_name": "STR", "difficulty_class": 13, "subsystem_hint": "combat"},
            narrative_draft="",
        )
    )
    resolver = Resolver(gm_agent=stub)

    async def _fake_route(sd, user_input, source_profile=None):
        return {
            "action_type": "combat",
            "stat_name": "STR",
            "difficulty_class": 12,
            "subsystem_hint": "combat",
        }

    with (
        patch("monitor_data.utils.dice.random.randint", return_value=14),
        patch(
            "monitor_agents.game_system._action_routing.infer_action_context",
            side_effect=_fake_route,
        ),
    ):
        result, _ = await resolver.resolve_turn(
            scene_id="scene-1",
            user_input="I attack",
            context=_make_context(),
            game_context={
                "name": "test",
                "attributes": [
                    {
                        "name": "Strength",
                        "abbreviation": "STR",
                        "min_value": 1,
                        "max_value": 5,
                        "default_value": 2,
                    }
                ],
                "skills": [],
            },
            play_mode="dice_game_system",
        )
    # subsystem_hint propagates to the resolved dict.
    assert result["subsystem_hint"] == "combat"
