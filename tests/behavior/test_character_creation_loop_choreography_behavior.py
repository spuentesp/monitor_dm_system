"""Behavior tests for CharacterCreationLoop choreography (Phase 2-3).

Exercises pure helpers and node functions without LLM or DB.

Covers:
- _parse_attribute_assignment (regex parsing, prefix matching, "roll" command)
- _parse_skill_choices (tokenizer)
- _match_option (fuzzy matching)
- _format_current_attrs (string building)
- _build_completion_message (final summary)
- _route_after_present / _route_after_process
- present_step (with various step types)
- process_input (with various step types)
- CharacterCreationState defaults
"""
from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_state(**overrides) -> Any:
    from monitor_agents.loops.character_creation_loop import CharacterCreationState

    base: Dict[str, Any] = {}
    base.update(overrides)
    return CharacterCreationState(**base)


# =============================================================================
# _parse_attribute_assignment
# =============================================================================


class TestParseAttributeAssignment:
    def test_simple_assignment_with_equals(self):
        from monitor_agents.loops.character_creation_loop import _parse_attribute_assignment

        current = {"STR": 10, "DEX": 10, "CON": 10}
        result = _parse_attribute_assignment("STR=16 DEX=14", current, {})
        assert result["STR"] == 16
        assert result["DEX"] == 14
        assert result["CON"] == 10  # unchanged

    def test_assignment_with_colon(self):
        from monitor_agents.loops.character_creation_loop import _parse_attribute_assignment

        current = {"STR": 10, "INT": 10}
        result = _parse_attribute_assignment("STR:18", current, {})
        assert result["STR"] == 18
        assert result["INT"] == 10

    def test_case_insensitive_keys(self):
        from monitor_agents.loops.character_creation_loop import _parse_attribute_assignment

        current = {"STR": 10, "DEX": 10}
        result = _parse_attribute_assignment("str=15", current, {})
        assert result["STR"] == 15

    def test_unknown_key_no_match(self):
        from monitor_agents.loops.character_creation_loop import _parse_attribute_assignment

        current = {"STR": 10}
        result = _parse_attribute_assignment("XYZ=99", current, {})
        assert result == current  # unchanged

    def test_partial_prefix_match(self):
        from monitor_agents.loops.character_creation_loop import _parse_attribute_assignment

        current = {"STRENGTH": 10, "DEXTERITY": 10}
        # ST is 2-char prefix of STRENGTH
        result = _parse_attribute_assignment("ST=18", current, {})
        assert result["STRENGTH"] == 18

    def test_preserves_existing_values(self):
        from monitor_agents.loops.character_creation_loop import _parse_attribute_assignment

        current = {"STR": 14, "DEX": 12}
        result = _parse_attribute_assignment("", current, {})
        # No structured input, no "roll" keyword -> unchanged
        assert result["STR"] == 14
        assert result["DEX"] == 12

    def test_roll_keyword_falls_back_to_random(self, monkeypatch):
        from monitor_agents.loops.character_creation_loop import _parse_attribute_assignment

        # Force a stub GSR-like object
        class StubGSR:
            def roll_character(self):
                return {"attributes": {"STR": 18, "DEX": 14}}

        # Patch GameSystemRuntime to return our stub
        class FakeRuntime:
            def __init__(self, ctx):
                pass

            def roll_character(self):
                return {"attributes": {"STR": 18, "DEX": 14}}

        import monitor_agents.loops.character_creation_loop as mod
        monkeypatch.setattr("monitor_agents.game_system.GameSystemRuntime", FakeRuntime)

        current = {"STR": 10, "DEX": 10}
        result = _parse_attribute_assignment("roll", current, {})
        assert result["STR"] == 18
        assert result["DEX"] == 14


# =============================================================================
# _parse_skill_choices
# =============================================================================


class TestParseSkillChoices:
    def test_comma_separated(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        result = _parse_skill_choices("stealth, perception, athletics")
        assert result == {"stealth": True, "perception": True, "athletics": True}

    def test_space_separated(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        result = _parse_skill_choices("stealth perception")
        assert "stealth" in result
        assert "perception" in result

    def test_mixed_separators(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        result = _parse_skill_choices("stealth,perception athletics")
        assert "stealth" in result
        assert "perception" in result
        assert "athletics" in result

    def test_empty_input(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        result = _parse_skill_choices("")
        assert result == {}

    def test_skips_empty_tokens(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        result = _parse_skill_choices("stealth,  ,perception")
        assert "stealth" in result
        assert "perception" in result


# =============================================================================
# _match_option
# =============================================================================


class TestMatchOption:
    def test_exact_match(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        result = _match_option("Fighter", ["Wizard", "Fighter", "Rogue"])
        assert result == "Fighter"

    def test_case_insensitive(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        result = _match_option("fighter", ["Fighter", "Wizard"])
        assert result == "Fighter"

    def test_substring_match_input_in_option(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        result = _match_option("Wiz", ["Wizard", "Fighter"])
        assert result == "Wizard"

    def test_substring_match_option_in_input(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        result = _match_option("I want Fighter", ["Fighter", "Wizard"])
        assert result == "Fighter"

    def test_no_match_returns_none(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        result = _match_option("xyz", ["Fighter", "Wizard"])
        assert result is None

    def test_empty_options(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        result = _match_option("Fighter", [])
        assert result is None

    def test_empty_input(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        result = _match_option("", ["Fighter", "Wizard"])
        # Empty string is contained in every string, so first option wins
        assert result == "Fighter"


# =============================================================================
# _format_current_attrs
# =============================================================================


class TestFormatCurrentAttrs:
    def test_empty_attrs(self):
        from monitor_agents.loops.character_creation_loop import _format_current_attrs

        state = _make_state(attributes={})
        assert _format_current_attrs(state) == ""

    def test_single_attr(self):
        from monitor_agents.loops.character_creation_loop import _format_current_attrs

        state = _make_state(attributes={"STR": 14})
        assert _format_current_attrs(state) == "STR=14"

    def test_multiple_attrs(self):
        from monitor_agents.loops.character_creation_loop import _format_current_attrs

        state = _make_state(attributes={"STR": 14, "DEX": 12, "CON": 10})
        result = _format_current_attrs(state)
        assert "STR=14" in result
        assert "DEX=12" in result
        assert "CON=10" in result


# =============================================================================
# _build_completion_message
# =============================================================================


class TestBuildCompletionMessage:
    def test_includes_name(self):
        from monitor_agents.loops.character_creation_loop import _build_completion_message

        state = _make_state(character_name="Aragorn", attributes={"STR": 14})
        msg = _build_completion_message(state)
        assert "Aragorn" in msg
        assert "Complete" in msg

    def test_unnamed_character(self):
        from monitor_agents.loops.character_creation_loop import _build_completion_message

        state = _make_state(attributes={})
        msg = _build_completion_message(state)
        assert "Unnamed" in msg


# =============================================================================
# Routing
# =============================================================================


class TestRouting:
    def test_route_after_present_done(self):
        from monitor_agents.loops.character_creation_loop import _route_after_present

        state = _make_state(creation_complete=True)
        assert _route_after_present(state) == "done"

    def test_route_after_present_await(self):
        from monitor_agents.loops.character_creation_loop import _route_after_present

        state = _make_state(awaiting_input=True)
        assert _route_after_present(state) == "await"

    def test_route_after_present_auto(self):
        from monitor_agents.loops.character_creation_loop import _route_after_present

        state = _make_state(awaiting_input=False, creation_complete=False)
        assert _route_after_present(state) == "auto"

    def test_route_after_process_retry_on_error(self):
        from monitor_agents.loops.character_creation_loop import _route_after_process

        state = _make_state(error="bad input")
        assert _route_after_process(state) == "retry"

    def test_route_after_process_done_at_end(self):
        from monitor_agents.loops.character_creation_loop import _route_after_process

        state = _make_state(creation_complete=True, current_step_index=5, total_steps=5)
        assert _route_after_process(state) == "done"

    def test_route_after_process_done_at_index_past_total(self):
        from monitor_agents.loops.character_creation_loop import _route_after_process

        state = _make_state(current_step_index=10, total_steps=5)
        assert _route_after_process(state) == "done"

    def test_route_after_process_continue(self):
        from monitor_agents.loops.character_creation_loop import _route_after_process

        state = _make_state(current_step_index=2, total_steps=5)
        assert _route_after_process(state) == "continue"


# =============================================================================
# present_step
# =============================================================================


class TestPresentStep:
    def test_no_steps_returns_complete(self):
        from monitor_agents.loops.character_creation_loop import present_step

        state = _make_state(creation_steps=[])
        result = present_step(state)
        assert result.get("creation_complete") is True
        assert result.get("awaiting_input") is False

    def test_index_past_end_returns_complete(self):
        from monitor_agents.loops.character_creation_loop import present_step

        state = _make_state(
            creation_steps=[{"title": "name", "step_type": "choose_name"}],
            current_step_index=5,
        )
        result = present_step(state)
        assert result.get("creation_complete") is True

    def test_choose_name_step(self):
        from monitor_agents.loops.character_creation_loop import present_step

        state = _make_state(
            creation_steps=[
                {"step_type": "choose_name", "title": "Name", "instructions": "What is your name?"}
            ],
            current_step_index=0,
        )
        result = present_step(state)
        assert result.get("awaiting_input") is True
        assert "Name" in result.get("step_prompt", "")

    def test_optional_step_prompts_skip(self):
        from monitor_agents.loops.character_creation_loop import present_step

        state = _make_state(
            creation_steps=[
                {
                    "step_type": "custom",
                    "title": "Optional",
                    "instructions": "Whatever",
                    "is_optional": True,
                }
            ],
        )
        result = present_step(state)
        assert "skip" in result.get("step_prompt", "").lower()

    def test_options_listed(self):
        from monitor_agents.loops.character_creation_loop import present_step

        state = _make_state(
            creation_steps=[
                {
                    "step_type": "choose_class",
                    "title": "Class",
                    "instructions": "Pick a class",
                    "options": ["Fighter", "Wizard", "Rogue"],
                }
            ],
        )
        result = present_step(state)
        prompt = result.get("step_prompt", "")
        assert "Fighter" in prompt
        assert "Wizard" in prompt
        assert "Rogue" in prompt

    def test_already_complete_returns_not_awaiting(self):
        from monitor_agents.loops.character_creation_loop import present_step

        state = _make_state(creation_complete=True, creation_steps=[{"title": "x"}])
        result = present_step(state)
        assert result.get("awaiting_input") is False


# =============================================================================
# process_input
# =============================================================================


class TestProcessInput:
    def test_empty_input_stays_awaiting(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(player_input=None)
        result = process_input(state)
        assert result.get("awaiting_input") is True

    def test_choose_name_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_name", "title": "Name"}],
            current_step_index=0,
            player_input="Aragorn",
        )
        result = process_input(state)
        assert result["character_name"] == "Aragorn"
        assert result["current_step_index"] == 1
        assert "name" in result["character_data"]

    def test_choose_concept_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_concept", "title": "Concept"}],
            player_input="A wandering ranger",
        )
        result = process_input(state)
        assert result["concept"] == "A wandering ranger"
        assert result["character_data"]["concept"] == "A wandering ranger"

    def test_choose_class_matches_option(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[
                {
                    "step_type": "choose_class",
                    "title": "Class",
                    "options": ["Fighter", "Wizard", "Rogue"],
                }
            ],
            player_input="Fighter",
        )
        result = process_input(state)
        assert result["choices"]["class"] == "Fighter"
        assert result["current_step_index"] == 1

    def test_choose_species_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[
                {
                    "step_type": "choose_species",
                    "title": "Species",
                    "options": ["Human", "Elf"],
                }
            ],
            player_input="Human",
        )
        result = process_input(state)
        assert result["choices"]["species"] == "Human"

    def test_choose_background_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[
                {
                    "step_type": "choose_background",
                    "title": "Background",
                    "options": ["Noble", "Soldier"],
                }
            ],
            player_input="Noble",
        )
        result = process_input(state)
        assert result["background"] == "Noble"
        assert "background" in result["choices"]

    def test_choose_skills_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_skills", "title": "Skills"}],
            skills={"existing_skill": 1},
            player_input="stealth, perception",
        )
        result = process_input(state)
        assert "stealth" in result["skills"]
        assert result["skills"]["existing_skill"] == 1

    def test_choose_equipment_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_equipment", "title": "Equipment"}],
            player_input="sword and shield",
        )
        result = process_input(state)
        assert result["choices"]["equipment"] == "sword and shield"
        assert result["character_data"]["equipment"] == "sword and shield"

    def test_choose_feats_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_feats", "title": "Feats"}],
            player_input="Alert",
        )
        result = process_input(state)
        assert "feats" in result["choices"]

    def test_choose_spells_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_spells", "title": "Spells"}],
            player_input="Fireball",
        )
        result = process_input(state)
        assert "spells" in result["choices"]

    def test_write_backstory_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "write_backstory", "title": "Backstory"}],
            player_input="A tale of woe",
        )
        result = process_input(state)
        assert "backstory" in result["choices"]

    def test_custom_step_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "weird_custom_thing", "title": "Custom"}],
            player_input="my answer",
        )
        result = process_input(state)
        assert result["choices"]["Custom"] == "my answer"
        assert result["current_step_index"] == 1

    def test_optional_step_skip(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "custom", "title": "Opt", "is_optional": True}],
            player_input="skip",
        )
        result = process_input(state)
        assert result["current_step_index"] == 1
        assert result["choices"]["Opt"] == "skipped"

    def test_index_past_end_completes(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[],
            current_step_index=5,
            player_input="anything",
        )
        result = process_input(state)
        assert result.get("creation_complete") is True


# =============================================================================
# CharacterCreationState defaults
# =============================================================================


class TestCharacterCreationStateDefaults:
    def test_minimal_construct(self):
        from monitor_agents.loops.character_creation_loop import CharacterCreationState

        state = CharacterCreationState()
        assert state.scene_id is None
        assert state.story_id is None
        assert state.universe_id is None
        assert state.game_context == {}
        assert state.current_step_index == 0
        assert state.total_steps == 0
        assert state.creation_steps == []
        assert state.character_data == {}
        assert state.attributes == {}
        assert state.skills == {}
        assert state.resources == {}
        assert state.choices == {}
        assert state.background is None
        assert state.character_name is None
        assert state.concept is None
        assert state.gm_message is None
        assert state.player_input is None
        assert state.step_prompt is None
        assert state.creation_complete is False
        assert state.awaiting_input is False
        assert state.error is None
