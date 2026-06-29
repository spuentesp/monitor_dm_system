"""
Tests for the unified GMAwareness → Resolver flow.

The resolver is now a thin shell that consumes GMAwareness verdicts. These
tests mock `monitor_agents.resolver.check_gm_awareness` to control routing
and verify each branch dispatches correctly.

Coverage:
- Trivial / propose_roll / contested routing
- Forced narrative accept / push_back / clarification
- Narrative (god) mode → no dice, advance fiction
- Auto-roll mode → system rolls for the player
- Oracle route for world-truth questions
- Pending roll interception
- LLM fallback (verdict returns permissive default)
- Mode-flag fast paths skip the LLM entirely
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.gm_awareness import (
    ActionType,
    CausalityAction,
    GMAwareness,
    IntentType,
    RollNecessity,
    Severity,
)
from monitor_agents.resolver import Resolver

from _gm_helpers import (
    contested_attack,
    contested_shoot,
    contested_spell,
    deus_ex_machina,
    forced_narrative_accept,
    forced_narrative_pushback,
    make_verdict,
    propose_persuasion,
    propose_stealth,
    query_intent,
    trivial_attempt,
    trivial_dialogue,
)


# ===========================================================================
# Helpers
# ===========================================================================


def _make_context(body: int = 0, dex: int = 0, savvy: int = 0) -> Dict[str, Any]:
    """Build a minimal scene context dict matching what SceneLoop passes."""
    return {
        "entities": [
            {
                "properties": {
                    "attributes": {
                        "Strength": 12,
                        "Dexterity": dex or 14,
                        "Wisdom": 10,
                        "Charisma": 8,
                        "Intelligence": 13,
                        "body": body or 1,
                        "savvy": savvy or 0,
                    }
                }
            }
        ],
        "turns": [],
        "source_profile": {
            "character_name": "Test Hero",
            "established_facts": [],
        },
    }


def _patch_gm(verdict: GMAwareness):
    """Patch check_gm_awareness at the resolver's import site."""
    return patch(
        "monitor_agents.resolver.check_gm_awareness",
        new_callable=AsyncMock,
        return_value=verdict,
    )


# ===========================================================================
# Trivial branch — no roll, automatic success
# ===========================================================================


class TestTrivialRouting:
    @pytest.mark.asyncio
    async def test_look_around_is_trivial(self):
        with _patch_gm(trivial_attempt()):
            resolver = Resolver()
            result = await resolver.resolve_turn("s1", "I look around", _make_context())
        assert result["resolution_type"] == "trivial"
        assert result["roll_total"] is None
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_simple_speech_is_trivial(self):
        with _patch_gm(trivial_dialogue()):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", 'I say "Hello"', _make_context()
            )
        assert result["resolution_type"] == "trivial"

    @pytest.mark.asyncio
    async def test_walking_is_trivial(self):
        verdict = make_verdict(
            intent=IntentType.ACTION,
            action=ActionType.MOVEMENT,
            roll_necessity=RollNecessity.TRIVIAL,
            suggested_stat="Dexterity",
            suggested_dc=10,
        )
        with _patch_gm(verdict):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I walk to the bridge", _make_context()
            )
        assert result["resolution_type"] == "trivial"

    @pytest.mark.asyncio
    async def test_trivial_has_risk_preview(self):
        with _patch_gm(trivial_attempt()):
            resolver = Resolver()
            result = await resolver.resolve_turn("s1", "I look around", _make_context())
        assert "risk_preview" in result
        assert result["risk_preview"] != ""


# ===========================================================================
# Propose-roll branch — offer the player a roll
# ===========================================================================


class TestProposeRollRouting:
    @pytest.mark.asyncio
    async def test_persuasion_is_propose_roll(self):
        with _patch_gm(propose_persuasion()):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I try to persuade the guard", _make_context()
            )
        assert result["resolution_type"] == "propose_roll"
        assert result["roll_total"] is None
        assert result["success"] is None
        assert result["success_level"] == "pending"
        assert result["requires_player_choice"] is True
        assert "roll_invitation" in result
        assert result["roll_necessity"] == "propose_roll"

    @pytest.mark.asyncio
    async def test_threaten_is_propose_roll(self):
        verdict = make_verdict(
            intent=IntentType.DIALOGUE,
            action=ActionType.DIALOGUE,
            roll_necessity=RollNecessity.PROPOSE_ROLL,
            suggested_stat="Charisma",
            suggested_dc=12,
        )
        with _patch_gm(verdict):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I threaten the merchant", _make_context()
            )
        assert result["resolution_type"] == "propose_roll"

    @pytest.mark.asyncio
    async def test_sneak_past_danger_is_propose_roll(self):
        with _patch_gm(propose_stealth()):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I sneak past the guard", _make_context()
            )
        assert result["resolution_type"] == "propose_roll"

    @pytest.mark.asyncio
    async def test_investigate_suspicious_area_is_propose_roll(self):
        verdict = make_verdict(
            intent=IntentType.ACTION,
            action=ActionType.EXPLORATION,
            roll_necessity=RollNecessity.PROPOSE_ROLL,
            suggested_stat="Intelligence",
            suggested_dc=13,
        )
        with _patch_gm(verdict):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I examine the trap carefully", _make_context()
            )
        assert result["resolution_type"] == "propose_roll"

    @pytest.mark.asyncio
    async def test_propose_roll_has_stat_and_dc(self):
        with _patch_gm(propose_stealth()):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I try to pick the lock", _make_context()
            )
        assert result["stat"] is not None
        assert result["difficulty_class"] is not None


# ===========================================================================
# Contested branch — roll dice now
# ===========================================================================


class TestContestedRouting:
    @pytest.mark.asyncio
    async def test_attack_is_contested(self):
        with _patch_gm(contested_attack()):
            resolver = Resolver()
            with patch("monitor_data.utils.dice.random.randint", return_value=15):
                result = await resolver.resolve_turn(
                    "s1", "I attack the orc", _make_context()
                )
        assert result["resolution_type"] == "dice"
        assert result["roll_necessity"] == "contested"
        assert result["roll_total"] is not None

    @pytest.mark.asyncio
    async def test_shoot_is_contested(self):
        with _patch_gm(contested_shoot()):
            resolver = Resolver()
            with patch("monitor_data.utils.dice.random.randint", return_value=10):
                result = await resolver.resolve_turn(
                    "s1", "I shoot at the target", _make_context()
                )
        assert result["resolution_type"] == "dice"

    @pytest.mark.asyncio
    async def test_cast_spell_is_contested(self):
        with _patch_gm(contested_spell()):
            resolver = Resolver()
            with patch("monitor_data.utils.dice.random.randint", return_value=12):
                result = await resolver.resolve_turn(
                    "s1", "I cast fireball", _make_context()
                )
        assert result["resolution_type"] == "dice"


# ===========================================================================
# Forced narrative branch
# ===========================================================================


class TestForcedNarrative:
    @pytest.mark.asyncio
    async def test_low_stakes_declaration_accepted(self):
        """Player declares 'I enter the room' (low stakes) — accept, no roll."""
        with _patch_gm(forced_narrative_accept()):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I successfully enter the room", _make_context()
            )
        assert result["resolution_type"] == "forced_narrative"
        assert result["forced_narrative"] is True
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_high_stakes_declaration_pushback(self):
        """Player declares 'I kill the boss' — push back with roll."""
        with _patch_gm(forced_narrative_pushback(stat="Strength", dc=15)):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I kill the boss", _make_context()
            )
        assert result["resolution_type"] == "forced_narrative_pushback"
        assert result["forced_narrative"] is True
        assert result["requires_player_choice"] is True
        assert "pushback_prompt" in result
        assert "Roll Strength (DC 15)" in result["pushback_prompt"]
        assert result["causality_reasons"] == ["Killing without a roll requires a check."]
        assert result["causality_severity"] == "major"

    @pytest.mark.asyncio
    async def test_deus_ex_machina_clarification(self):
        """Player invents an object — ask where it came from."""
        with _patch_gm(deus_ex_machina()):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "I find the key in my pocket", _make_context()
            )
        assert result["resolution_type"] == "forced_narrative_clarification"
        assert result["requires_clarification"] is True
        assert result["causality_severity"] == "deus_ex_machina"


# ===========================================================================
# Mode flags: narrative (god) and auto-roll
# ===========================================================================


class TestModeFlags:
    @pytest.mark.asyncio
    async def test_narrative_mode_skips_llm(self):
        """In narrative mode the resolver must NOT call check_gm_awareness.

        The LLM is bypassed entirely — fiction advances, no dice.
        """
        resolver = Resolver()
        with patch(
            "monitor_agents.resolver.check_gm_awareness",
            new_callable=AsyncMock,
        ) as mock_gm:
            result = await resolver.resolve_turn(
                "s1",
                "I kill the boss and take the crown",
                _make_context(),
                play_mode="narrative",
            )
        mock_gm.assert_not_called()
        assert result["resolution_type"] == "narrative"
        assert result["roll_total"] is None
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_narrative_mode_attack_still_works(self):
        """Combat in narrative mode doesn't roll — god mode accepts everything."""
        resolver = Resolver()
        with patch(
            "monitor_agents.resolver.check_gm_awareness",
            new_callable=AsyncMock,
        ) as mock_gm:
            result = await resolver.resolve_turn(
                "s1", "I attack the orc", _make_context(), play_mode="narrative"
            )
        mock_gm.assert_not_called()
        assert result["resolution_type"] == "narrative"
        assert result["roll_total"] is None

    @pytest.mark.asyncio
    async def test_narrative_mode_declaration_advances_fiction(self):
        resolver = Resolver()
        with patch(
            "monitor_agents.resolver.check_gm_awareness",
            new_callable=AsyncMock,
        ) as mock_gm:
            result = await resolver.resolve_turn(
                "s1",
                "I convince the duke to give me the castle",
                _make_context(),
                play_mode="narrative",
            )
        mock_gm.assert_not_called()
        assert result["resolution_type"] == "narrative"
        assert result["forced_narrative"] is False  # god mode isn't "forced"


class TestAutoRoll:
    @pytest.mark.asyncio
    async def test_auto_roll_skips_llm_and_rolls(self):
        """Auto-roll mode bypasses the LLM and rolls dice immediately.

        check_gm_awareness IS still called (it short-circuits internally),
        but the underlying LLM call is skipped.
        """
        resolver = Resolver()
        # The agent's LLM call must NOT be made — auto-roll short-circuits
        # inside check_gm_awareness before reaching the LLM provider.
        with patch.object(
            resolver,
            "call_llm_structured",
            new_callable=AsyncMock,
            side_effect=AssertionError("LLM must not be called in auto-roll mode"),
        ):
            with patch("monitor_data.utils.dice.random.randint", return_value=15):
                result = await resolver.resolve_turn(
                    "s1",
                    "I attack the orc",
                    _make_context(),
                    roll_mode="auto",
                )
        # Auto-roll → contested path → resolution_type is "dice"
        assert result["resolution_type"] == "dice"
        assert result["roll_total"] is not None


# ===========================================================================
# Oracle route — world-truth questions
# ===========================================================================


class TestOracleRoute:
    @pytest.mark.asyncio
    async def test_world_truth_question_routes_to_oracle(self):
        """A query intent routes to the Oracle (no dice)."""
        with _patch_gm(query_intent()):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "Is the door locked?", _make_context()
            )
        assert result["resolution_type"] == "oracle"
        assert result["action_type"] == "query"
        assert result["intent_type"] == "query"
        assert "oracle_result" in result
        assert result["success"] is not None

    @pytest.mark.asyncio
    async def test_query_picks_up_ooc_likelihood_marker(self):
        """((Likely)) marker in a query is passed to Oracle."""
        with _patch_gm(query_intent()):
            resolver = Resolver()
            result = await resolver.resolve_turn(
                "s1", "Is the guard still there? ((Likely))", _make_context()
            )
        assert result["resolution_type"] == "oracle"


# ===========================================================================
# LLM fallback — graceful degradation when LLM is unavailable
# ===========================================================================


class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_llm_failure_returns_safe_propose_roll(self):
        """If the LLM raises, the resolver falls back to propose-roll.

        This is the safe default — the player gets to choose.
        """
        resolver = Resolver()
        with patch(
            "monitor_agents.resolver.check_gm_awareness",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM unreachable"),
        ):
            result = await resolver.resolve_turn(
                "s1", "I try to open the door", _make_context()
            )
        # Should not crash; should return a structured verdict
        assert "resolution_type" in result
        # Fallback proposes a roll — never roll automatically
        assert result["resolution_type"] in ("propose_roll", "trivial")

    @pytest.mark.asyncio
    async def test_llm_unavailable_does_not_crash_narrative_mode(self):
        """Narrative mode never reaches the LLM even if it would fail."""
        resolver = Resolver()
        result = await resolver.resolve_turn(
            "s1", "anything", _make_context(), play_mode="narrative"
        )
        assert result["resolution_type"] == "narrative"


# ===========================================================================
# Pending roll interception — push back if player skips a pending roll
# ===========================================================================


class TestPendingRollInterception:
    @pytest.mark.asyncio
    async def test_pending_roll_pushed_back_when_player_skips(self):
        """If the previous turn left a pending roll, the next turn must
        either roll the dice or push back. We push back unless the
        player typed /roll or 'I roll d20'."""
        # Even with a permissive GM verdict, the pending-roll guard
        # should intercept because the player didn't type a roll.
        with _patch_gm(trivial_attempt()):
            resolver = Resolver()
            ctx = _make_context()
            ctx["pending_roll"] = {
                "stat": "Strength",
                "dc": 12,
                "action": "force the door open",
            }
            result = await resolver.resolve_turn(
                "s1", "I push the door open.", ctx
            )
        assert result["resolution_type"] == "forced_narrative_pushback"
        assert result["forced_narrative"] is True
        assert "Strength" in result["pushback_prompt"]

    @pytest.mark.asyncio
    async def test_pending_roll_passes_through_when_player_rolls(self):
        """If the player explicitly types 'I roll', the pending roll is consumed."""
        with _patch_gm(trivial_attempt()):
            resolver = Resolver()
            ctx = _make_context()
            ctx["pending_roll"] = {
                "stat": "Strength",
                "dc": 12,
                "action": "force the door open",
                "modifier": 2,
            }
            with patch("monitor_data.utils.dice.random.randint", return_value=10):
                result = await resolver.resolve_turn(
                    "s1", "I roll Strength (DC 12)", ctx
                )
        # Roll happens — not a pushback
        assert result["resolution_type"] != "forced_narrative_pushback"


# ===========================================================================
# GMAwareness structure validation
# ===========================================================================


class TestGMAwarenessStructure:
    def test_intent_enum_values(self):
        """IntentType must include the five canonical values."""
        assert IntentType.META.value == "meta"
        assert IntentType.OOC.value == "ooc"
        assert IntentType.QUERY.value == "query"
        assert IntentType.DIALOGUE.value == "dialogue"
        assert IntentType.ACTION.value == "action"

    def test_action_enum_values(self):
        assert ActionType.NONE.value == "none"
        assert ActionType.COMBAT.value == "combat"
        assert ActionType.STEALTH.value == "stealth"
        assert ActionType.EXPLORATION.value == "exploration"

    def test_roll_necessity_enum_values(self):
        assert RollNecessity.TRIVIAL.value == "trivial"
        assert RollNecessity.PROPOSE_ROLL.value == "propose_roll"
        assert RollNecessity.CONTESTED.value == "contested"

    def test_causality_action_enum_values(self):
        assert CausalityAction.ACCEPT.value == "accept"
        assert CausalityAction.PUSH_BACK.value == "push_back"
        assert CausalityAction.REQUEST_CLARIFICATION.value == "request_clarification"
        assert CausalityAction.NARRATIVE_OVERRIDE.value == "narrative_override"

    def test_severity_enum_values(self):
        assert Severity.NONE.value == "none"
        assert Severity.MINOR.value == "minor"
        assert Severity.MAJOR.value == "major"
        assert Severity.DEUS_EX_MACHINA.value == "deus_ex_machina"

    def test_verdict_construction_minimal(self):
        """A verdict with required fields only is valid."""
        v = GMAwareness(
            intent_type=IntentType.ACTION,
            action_type=ActionType.COMBAT,
            roll_necessity=RollNecessity.CONTESTED,
            declares_outcome=False,
            violates_causality=False,
            action=CausalityAction.ACCEPT,
        )
        assert v.intent_type == IntentType.ACTION
        assert v.roll_necessity == RollNecessity.CONTESTED

    def test_verdict_rejects_invalid_severity_string(self):
        """Pydantic must reject arbitrary strings for severity."""
        with pytest.raises(Exception):
            GMAwareness(
                intent_type=IntentType.ACTION,
                action_type=ActionType.NONE,
                roll_necessity=RollNecessity.TRIVIAL,
                declares_outcome=False,
                violates_causality=False,
                severity="banana",  # invalid
                action=CausalityAction.ACCEPT,
            )

    def test_verdict_target_can_be_none(self):
        """Target is Optional[str] — None means 'no target named'."""
        v = GMAwareness(
            intent_type=IntentType.ACTION,
            action_type=ActionType.MOVEMENT,
            roll_necessity=RollNecessity.TRIVIAL,
            declares_outcome=False,
            violates_causality=False,
            action=CausalityAction.ACCEPT,
            target=None,
        )
        assert v.target is None


# ===========================================================================
# GMAwareness entry-point: check_gm_awareness itself
# ===========================================================================


class TestCheckGMAwareness:
    @pytest.mark.asyncio
    async def test_narrative_mode_skips_llm(self):
        from monitor_agents.gm_awareness import check_gm_awareness

        class FakeAgent:
            async def call_llm_structured(self, *args, **kwargs):
                raise AssertionError("LLM should not be called in narrative mode")

        verdict = await check_gm_awareness(
            agent=FakeAgent(),
            user_input="anything",
            scene_context={},
            play_mode="narrative",
            established_facts=[],
        )
        assert verdict.action == CausalityAction.NARRATIVE_OVERRIDE
        assert verdict.declares_outcome is True

    @pytest.mark.asyncio
    async def test_auto_roll_skips_llm(self):
        from monitor_agents.gm_awareness import check_gm_awareness

        class FakeAgent:
            async def call_llm_structured(self, *args, **kwargs):
                raise AssertionError("LLM should not be called in auto-roll mode")

        verdict = await check_gm_awareness(
            agent=FakeAgent(),
            user_input="I attack",
            scene_context={},
            play_mode="dice_game_system",
            established_facts=[],
            roll_mode="auto",
        )
        assert verdict.action == CausalityAction.ACCEPT
        assert verdict.roll_necessity == RollNecessity.CONTESTED

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_permissive(self):
        """If the LLM raises (or is blocked), the function returns a safe fallback."""
        from monitor_agents.gm_awareness import check_gm_awareness

        # Patch the internal DSPy predict call to raise
        with patch(
            "monitor_agents.gm_awareness._run_dspy_predict",
            new_callable=AsyncMock,
            side_effect=RuntimeError("provider down"),
        ):
            verdict = await check_gm_awareness(
                agent=None,  # not used when _run_dspy_predict is patched
                user_input="I try to pick the lock",
                scene_context={"entities": [], "turns": []},
                play_mode="dice_game_system",
                established_facts=[],
            )
        # Default fallback: declare-outcome=False, action=ACCEPT, propose_roll
        assert verdict.declares_outcome is False
        assert verdict.action == CausalityAction.ACCEPT
        assert verdict.roll_necessity == RollNecessity.PROPOSE_ROLL
        # Reasoning should mention the failure (exact wording may vary)
        assert "unavailable" in verdict.reasoning.lower() or "fallback" in verdict.reasoning.lower()
