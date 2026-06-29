"""
Tests for Session 0 (character creation + opening brief) and the new
LLM-driven causality check (replacing the old regex-based forced narrative
detection).

Session 0 covers the contract that, when a user starts a game:
  1. They go through a conversational character creation flow
  2. The GM gives a brief opening scene (where, what, why)

The causality check replaces the old `_FORCED_NARRATIVE_RE` regex with a
proper LLM-driven judgment call. The contract here is that:
  - The check returns a structured CausalityVerdict
  - In narrative (god) mode, the check always accepts
  - In auto-roll mode, the check accepts (the system rolls)
  - In dice mode, the LLM evaluates whether the player declared an outcome
    and whether it violates causality
  - The verdict includes useful pushback prompts when violations are found

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_session0_and_forced_narrative.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ===========================================================================
# SESSION 0 — Character Creation Flow
# ===========================================================================


class TestSession0CharacterCreationFlow:
    """The character creation loop must be a guided conversation, not just
    a one-shot accept. It should ask questions, offer options, and let
    the player pick or random-roll."""

    def test_character_creation_loop_asks_for_name(self):
        """The first creation step must ask for the character's name."""
        from monitor_agents.loops.character_creation_loop import (
            CharacterCreationState,
            load_system,
        )

        state = CharacterCreationState(
            story_id=uuid4(),
            game_context={
                "_id": "test-system",
                "name": "Test System",
                "character_creation": {
                    "steps": [
                        {"step_number": 2, "step_type": "roll_stats", "title": "Stats"},
                    ],
                },
                "attributes": [
                    {"abbreviation": "STR", "name": "Strength", "default_value": 10},
                ],
                "resources": [
                    {"name": "HP", "max_value": 10, "track_type": "resource"},
                ],
            },
        )
        result = load_system(state)
        steps = result.get("creation_steps", [])

        assert steps, "load_system must produce creation steps"
        first_step = steps[0]
        assert first_step.get("step_type") in ("choose_name", "name"), (
            f"First step must be 'choose_name', got '{first_step.get('step_type')}'"
        )

    def test_character_creation_provides_stat_rolling_options(self):
        """The character creation must offer a way to roll stats."""
        from monitor_agents.loops.character_creation_loop import (
            CharacterCreationState,
            load_system,
        )

        state = CharacterCreationState(
            story_id=uuid4(),
            game_context={
                "_id": "test-system",
                "name": "Test System",
                "character_creation": {
                    "steps": [
                        {"step_number": 1, "step_type": "choose_name"},
                        {"step_number": 2, "step_type": "roll_stats", "title": "Roll Stats"},
                    ],
                },
                "attributes": [
                    {"abbreviation": "STR", "default_value": 10},
                    {"abbreviation": "DEX", "default_value": 10},
                ],
                "resources": [],
            },
        )
        result = load_system(state)
        steps = result.get("creation_steps", [])
        stats_step = next(
            (s for s in steps if "roll" in (s.get("step_type") or "").lower()
             or "stat" in (s.get("title") or "").lower()),
            None,
        )
        assert stats_step is not None, "Character creation must include a stat rolling step"

    def test_character_creation_includes_backstory_question(self):
        """The character creation must include at least one open-ended
        backstory/motivation question."""
        from monitor_agents.loops.character_creation_loop import (
            CharacterCreationState,
            load_system,
        )

        state = CharacterCreationState(
            story_id=uuid4(),
            game_context={
                "_id": "test-system",
                "name": "Test System",
                "character_creation": {
                    "steps": [
                        {"step_number": 1, "step_type": "choose_name"},
                        {"step_number": 2, "step_type": "roll_stats", "title": "Stats"},
                        {
                            "step_number": 3,
                            "step_type": "free_text",
                            "title": "Why do you salvage?",
                            "instructions": "Tell me why your character risks their life on derelicts.",
                        },
                    ],
                },
                "attributes": [{"abbreviation": "STR", "default_value": 10}],
                "resources": [],
            },
        )
        result = load_system(state)
        steps = result.get("creation_steps", [])

        free_text_steps = [
            s for s in steps
            if s.get("step_type") in ("free_text", "backstory", "motivation")
            or "why" in (s.get("instructions") or "").lower()
            or "tell me" in (s.get("instructions") or "").lower()
        ]
        assert free_text_steps, (
            "Character creation must include at least one open-ended "
            "backstory/motivation question."
        )


# ===========================================================================
# SESSION 0 — GM Opening Brief
# ===========================================================================


class TestSession0OpeningBrief:
    """When the character is finalized, the GM must give a brief opening."""

    def test_scene_state_tracks_session_zero(self):
        """SceneState must track whether Session 0 (opening brief) has happened."""
        from monitor_agents.loops.scene_loop import SceneState

        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        # We need a way to know if this is the first turn after char creation.
        # Either an `opening_brief_done` flag, or use turns_count == 0.
        # Use turns_count as the implicit signal for now.
        assert state.turns_count == 0, (
            "A fresh SceneState must have turns_count == 0, which the narrator "
            "can use to detect Session 0 and produce an opening brief."
        )

    def test_opening_brief_prompt_template_exists(self):
        """The narrator prompt template must have a Session 0 / opening brief
        instruction that activates on the first turn."""
        from monitor_agents.prompts.narrator import NarratorSignature

        sig_doc = NarratorSignature.__doc__ or ""
        # The signature should instruct the narrator about opening briefs.
        # We accept any of these phrasings.
        triggers = ["opening", "brief", "session 0", "first turn", "where you are",
                    "situation", "stakes"]
        found = any(t in sig_doc.lower() for t in triggers)
        assert found, (
            "Narrator signature docstring should reference opening brief / "
            "session 0 / where you are / situation / stakes."
        )


# ===========================================================================
# CAUSALITY CHECK — The new LLM-driven replacement for forced narrative
# ===========================================================================


class TestCausalityCheckStructure:
    """The causality check is an LLM-driven judgment call, not a regex.
    It returns a structured CausalityVerdict."""

    def test_causality_verdict_has_required_fields(self):
        """CausalityVerdict must have all the fields needed for the resolver."""
        from monitor_agents.causality_check import CausalityVerdict, CausalityAction

        verdict = CausalityVerdict(
            declares_outcome=True,
            violates_causality=True,
            severity="major",
            reasons=["Killing without a roll"],
            action=CausalityAction.PUSH_BACK,
            suggested_stat="Strength",
            suggested_dc=12,
            reasoning="Player declared a kill outcome without attempting.",
            pushback_prompt="You need to roll Strength (DC 12) to attempt the kill.",
        )

        assert verdict.declares_outcome is True
        assert verdict.violates_causality is True
        assert verdict.severity == "major"
        assert len(verdict.reasons) == 1
        assert verdict.action == CausalityAction.PUSH_BACK
        assert verdict.suggested_stat == "Strength"
        assert verdict.suggested_dc == 12
        assert verdict.pushback_prompt

    def test_causality_action_enum_has_four_actions(self):
        """The action enum must include accept, push_back, request_clarification,
        and narrative_override."""
        from monitor_agents.causality_check import CausalityAction

        actions = {a.value for a in CausalityAction}
        assert "accept" in actions
        assert "push_back" in actions
        assert "request_clarification" in actions
        assert "narrative_override" in actions


class TestCausalityCheckBehavior:
    """The check_causality function must:
    - Always accept in narrative (god) mode
    - Always accept in auto-roll mode
    - Call the LLM in dice mode
    - Return a permissive verdict on LLM failure
    """

    @pytest.mark.asyncio
    async def test_narrative_mode_always_accepts(self):
        """In narrative (god) mode, the causality check must accept without calling LLM."""
        from monitor_agents.causality_check import check_causality, CausalityAction

        agent = MagicMock()
        agent.call_llm_structured = AsyncMock()

        verdict = await check_causality(
            agent=agent,
            user_input="I kill the dragon with my bare hands.",
            scene_context={"entities": [], "turns": []},
            play_mode="narrative",
            established_facts=[],
            roll_mode="normal",
        )

        assert verdict.action == CausalityAction.NARRATIVE_OVERRIDE
        assert verdict.violates_causality is False
        # LLM should NOT have been called
        agent.call_llm_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_roll_mode_accepts(self):
        """In auto-roll mode, the system rolls for the player — causality check accepts."""
        from monitor_agents.causality_check import check_causality, CausalityAction

        agent = MagicMock()
        agent.call_llm_structured = AsyncMock()

        verdict = await check_causality(
            agent=agent,
            user_input="I shoot him dead.",
            scene_context={"entities": [], "turns": []},
            play_mode="dice_game_system",
            established_facts=[],
            roll_mode="auto",
        )

        assert verdict.action == CausalityAction.ACCEPT
        agent.call_llm_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_dice_mode_calls_llm(self):
        """In dice mode, the causality check must call the LLM."""
        from monitor_agents.causality_check import check_causality, CausalityAction, CausalityVerdict

        # Mock LLM to return a verdict
        mock_verdict = CausalityVerdict(
            declares_outcome=True,
            violates_causality=True,
            severity="major",
            reasons=["Killing without a roll"],
            action=CausalityAction.PUSH_BACK,
            suggested_stat="Strength",
            suggested_dc=12,
            reasoning="Test",
            pushback_prompt="Roll Strength (DC 12).",
        )

        agent = MagicMock()
        agent.call_llm_structured = AsyncMock(return_value=mock_verdict)

        verdict = await check_causality(
            agent=agent,
            user_input="I kill the guard.",
            scene_context={"entities": [], "turns": []},
            play_mode="dice_game_system",
            established_facts=[],
            roll_mode="normal",
        )

        # LLM should have been called
        agent.call_llm_structured.assert_called_once()
        assert verdict.action == CausalityAction.PUSH_BACK
        assert verdict.pushback_prompt == "Roll Strength (DC 12)."

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_permissive(self):
        """When the LLM call fails, the causality check must fall back to permissive
        acceptance (let the standard roll resolver handle it)."""
        from monitor_agents.causality_check import check_causality, CausalityAction

        agent = MagicMock()
        agent.call_llm_structured = AsyncMock(side_effect=Exception("LLM down"))

        verdict = await check_causality(
            agent=agent,
            user_input="I kill the guard.",
            scene_context={"entities": [], "turns": []},
            play_mode="dice_game_system",
            established_facts=[],
            roll_mode="normal",
        )

        # Should NOT push back on LLM failure — that's worse than the original problem
        assert verdict.action == CausalityAction.ACCEPT
        assert "unavailable" in verdict.reasoning.lower() or "fall" in verdict.reasoning.lower()


# ===========================================================================
# INTEGRATION — Resolver uses causality check
# ===========================================================================


class TestResolverUsesCausalityCheck:
    """The resolver must call the GM-awareness check (not the old regex) and
    respect its verdict."""

    @pytest.mark.asyncio
    async def test_resolver_calls_causality_check(self):
        """resolve_turn must call check_gm_awareness with the user_input and context."""
        from monitor_agents.gm_awareness import (
            ActionType, IntentType, RollNecessity, Severity, CausalityAction, GMAwareness,
        )
        from monitor_agents.resolver import Resolver

        mock_verdict = GMAwareness(
            intent_type=IntentType.ACTION,
            action_type=ActionType.COMBAT,
            roll_necessity=RollNecessity.PROPOSE_ROLL,
            declares_outcome=True,
            violates_causality=True,
            severity=Severity.MAJOR,
            reasons=["Test reason"],
            action=CausalityAction.PUSH_BACK,
            suggested_stat="Strength",
            suggested_dc=12,
            reasoning="Test",
            pushback_prompt="Roll Strength.",
        )

        # Patch check_gm_awareness at the resolver's import site
        with patch(
            "monitor_agents.resolver.check_gm_awareness",
            new_callable=AsyncMock,
            return_value=mock_verdict,
        ) as mock_check:
            resolver = Resolver.__new__(Resolver)
            resolver.agent_type = "Resolver"
            resolver.agent_id = "test-resolver"
            resolver._llm_registry = MagicMock()
            resolver.call_llm_structured = AsyncMock(return_value=None)

            result = await resolver.resolve_turn(
                scene_id=str(uuid4()),
                user_input="I kill the guard.",
                context={"entities": [], "turns": [], "source_profile": {}},
                game_context={"name": "Test System"},
                play_mode="dice_game_system",
                roll_mode="normal",
            )

            mock_check.assert_called_once()
            assert result["resolution_type"] == "forced_narrative_pushback"
            assert result["pushback_prompt"] == "Roll Strength."

    @pytest.mark.asyncio
    async def test_resolver_narrative_mode_skips_causality_check(self):
        """In narrative mode, the resolver must not call check_gm_awareness."""
        from monitor_agents.resolver import Resolver

        with patch(
            "monitor_agents.resolver.check_gm_awareness",
            new_callable=AsyncMock,
        ) as mock_check:
            resolver = Resolver.__new__(Resolver)
            resolver.agent_type = "Resolver"
            resolver.agent_id = "test-resolver"
            resolver._llm_registry = MagicMock()
            resolver.call_llm_structured = AsyncMock(return_value=None)

            result = await resolver.resolve_turn(
                scene_id=str(uuid4()),
                user_input="I kill the guard.",
                context={"entities": [], "turns": [], "source_profile": {}},
                game_context={"name": "Test System"},
                play_mode="narrative",
                roll_mode="normal",
            )

            mock_check.assert_not_called()
            assert result["resolution_type"] in ("narrative", "forced_narrative")