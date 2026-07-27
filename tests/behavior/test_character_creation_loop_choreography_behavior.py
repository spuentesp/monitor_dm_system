"""Behavior tests for CharacterCreationLoop choreography (Phase 2-3).

Exercises pure helpers and node functions. LLM-based answer extraction
(attribute/resource assignment, skill selection, option matching) is
mocked at the DSPy module boundary -- these were regex/substring-matching
before (brittle: "put 2 into Perception" didn't match "2 Perception"-only
patterns, and option matching hardcoded VtM-specific "Physical"/"Social"/
"Mental" categories into supposedly system-agnostic code) and are now
genuine LLM extraction. See the `no-brittle-patches` project rule.

Covers:
- _extract_attribute_and_resource_assignments (LLM-mocked, + "roll" command)
- _parse_skill_choices (LLM-mocked)
- _match_option (LLM-mocked)
- _format_current_attrs (string building)
- _build_completion_message (final summary)
- _route_after_present / _route_after_process
- present_step (with various step types)
- process_input (with various step types, LLM-mocked where relevant)
- CharacterCreationState defaults
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.unit


def _make_state(**overrides) -> Any:
    from monitor_agents.loops.character_creation_loop import CharacterCreationState

    base: dict[str, Any] = {}
    base.update(overrides)
    return CharacterCreationState(**base)


def _mock_attribute_module(
    attribute_assignments: str = "{}", resource_assignments: str = "{}"
):
    """Patch AttributeAssignmentModule at its source (character_creation_loop.py
    imports it lazily inside the function, so patch where it's defined)."""
    return patch(
        "monitor_agents.character_creator.character_creation.AttributeAssignmentModule",
        return_value=lambda **_kwargs: SimpleNamespace(
            attribute_assignments=attribute_assignments,
            resource_assignments=resource_assignments,
        ),
    )


def _mock_option_module(matched_option: str):
    return patch(
        "monitor_agents.character_creator.text_matching.OptionMatchModule",
        return_value=lambda **_kwargs: SimpleNamespace(matched_option=matched_option),
    )


def _mock_skill_module(skill_selections: str):
    return patch(
        "monitor_agents.character_creator.character_creation.SkillSelectionModule",
        return_value=lambda **_kwargs: SimpleNamespace(
            skill_selections=skill_selections
        ),
    )


# =============================================================================
# _extract_attribute_and_resource_assignments
# =============================================================================


class TestExtractAttributeAndResourceAssignments:
    @pytest.mark.asyncio
    async def test_llm_extraction_updates_mentioned_attributes(self):
        from monitor_agents.loops.character_creation_loop import (
            _extract_attribute_and_resource_assignments,
        )

        current = {"STR": 10, "DEX": 10, "CON": 10}
        game_context = {"attributes": [{"name": "Strength", "abbreviation": "STR"}]}

        with _mock_attribute_module(attribute_assignments='{"STR": 16, "DEX": 14}'):
            attrs, resources = await _extract_attribute_and_resource_assignments(
                "put 2 into Strength and 4 into Dexterity", current, {}, game_context
            )

        assert attrs["STR"] == 16
        assert attrs["DEX"] == 14
        assert attrs["CON"] == 10  # unmentioned -> unchanged

    @pytest.mark.asyncio
    async def test_llm_extraction_ignores_keys_not_in_current(self):
        from monitor_agents.loops.character_creation_loop import (
            _extract_attribute_and_resource_assignments,
        )

        current = {"STR": 10}
        with _mock_attribute_module(attribute_assignments='{"XYZ": 99}'):
            attrs, _ = await _extract_attribute_and_resource_assignments(
                "XYZ=99", current, {}, {}
            )
        assert attrs == current  # XYZ isn't a real attribute -> ignored

    @pytest.mark.asyncio
    async def test_empty_input_leaves_values_unchanged(self):
        from monitor_agents.loops.character_creation_loop import (
            _extract_attribute_and_resource_assignments,
        )

        current = {"STR": 14, "DEX": 12}
        attrs, resources = await _extract_attribute_and_resource_assignments(
            "", current, {}, {}
        )
        assert attrs == current
        assert resources == {}

    @pytest.mark.asyncio
    async def test_roll_keyword_falls_back_to_random_without_llm_call(
        self, monkeypatch
    ):
        """ "roll"/"random" are fixed player commands, not free text needing
        interpretation -- handled directly, no LLM round-trip needed."""
        from monitor_agents.loops.character_creation_loop import (
            _extract_attribute_and_resource_assignments,
        )

        class FakeRuntime:
            def __init__(self, ctx):
                pass

            def roll_character(self):
                return {"attributes": {"STR": 18, "DEX": 14}}

        monkeypatch.setattr("monitor_agents.game_system.GameSystemRuntime", FakeRuntime)

        with patch(
            "monitor_agents.character_creator.character_creation.AttributeAssignmentModule"
        ) as MockModule:
            current = {"STR": 10, "DEX": 10}
            attrs, _ = await _extract_attribute_and_resource_assignments(
                "roll", current, {}, {}
            )
            MockModule.assert_not_called()

        assert attrs["STR"] == 18
        assert attrs["DEX"] == 14

    @pytest.mark.asyncio
    async def test_resource_mentions_extracted_alongside_attributes(self):
        """Storyteller-style resources (e.g. Willpower) mentioned in the
        same breath as attribute dots must not be dropped."""
        from monitor_agents.loops.character_creation_loop import (
            _extract_attribute_and_resource_assignments,
        )

        game_context = {"resources": [{"name": "Willpower"}]}
        with _mock_attribute_module(resource_assignments='{"Willpower": 5}'):
            _, resources = await _extract_attribute_and_resource_assignments(
                "5 Willpower", {}, {}, game_context
            )
        assert resources["Willpower"] == {"current": 5, "max": 5}

    @pytest.mark.asyncio
    async def test_llm_failure_leaves_values_unchanged(self):
        from monitor_agents.loops.character_creation_loop import (
            _extract_attribute_and_resource_assignments,
        )

        current = {"STR": 10}
        with patch(
            "monitor_agents.character_creator.character_creation.AttributeAssignmentModule",
            side_effect=RuntimeError("boom"),
        ):
            attrs, resources = await _extract_attribute_and_resource_assignments(
                "put 5 into Strength", current, {}, {}
            )
        assert attrs == current
        assert resources == {}


# =============================================================================
# _parse_skill_choices
# =============================================================================


class TestParseSkillChoices:
    @pytest.mark.asyncio
    async def test_extracts_mentioned_skills(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        game_context = {
            "skills": [
                {"name": "Stealth"},
                {"name": "Perception"},
                {"name": "Athletics"},
            ]
        }
        with _mock_skill_module(
            '{"Stealth": true, "Perception": true, "Athletics": true}'
        ):
            result = await _parse_skill_choices(
                "I want to focus on Stealth, Perception, and Athletics", game_context
            )
        assert result == {"Stealth": True, "Perception": True, "Athletics": True}

    @pytest.mark.asyncio
    async def test_extracts_ranked_skills(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        game_context = {"skills": [{"name": "Empathy"}, {"name": "Persuasion"}]}
        with _mock_skill_module('{"Empathy": 4, "Persuasion": 2}'):
            result = await _parse_skill_choices("Empathy 4, Persuasion 2", game_context)
        assert result == {"Empathy": 4, "Persuasion": 2}

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        result = await _parse_skill_choices("", {"skills": [{"name": "Stealth"}]})
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_skills_in_schema_returns_empty_without_llm_call(self):
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        with patch(
            "monitor_agents.character_creator.character_creation.SkillSelectionModule"
        ) as MockModule:
            result = await _parse_skill_choices("stealth, perception", {"skills": []})
            MockModule.assert_not_called()
        assert result == {}

    @pytest.mark.asyncio
    async def test_filters_out_skills_not_in_schema(self):
        """The LLM must not be trusted blindly -- only skills actually
        present in the schema's own list survive."""
        from monitor_agents.loops.character_creation_loop import _parse_skill_choices

        game_context = {"skills": [{"name": "Stealth"}]}
        with _mock_skill_module('{"Stealth": true, "MadeUpSkill": true}'):
            result = await _parse_skill_choices(
                "stealth and something else", game_context
            )
        assert result == {"Stealth": True}
        assert "MadeUpSkill" not in result


# =============================================================================
# _match_option
# =============================================================================


class TestMatchOption:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        with _mock_option_module("Fighter"):
            result = await _match_option("Fighter", ["Wizard", "Fighter", "Rogue"])
        assert result == "Fighter"

    @pytest.mark.asyncio
    async def test_paraphrased_answer_matches_via_llm(self):
        """The whole point of the LLM replacement: full-sentence,
        paraphrased answers that plain substring matching couldn't handle."""
        from monitor_agents.loops.character_creation_loop import _match_option

        with _mock_option_module("Rad Resistant"):
            result = await _match_option(
                "Take the Rad Resistant perk",
                ["Rad Resistant", "Bloody Mess", "Gunslinger"],
            )
        assert result == "Rad Resistant"

    @pytest.mark.asyncio
    async def test_no_match_returns_none(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        with _mock_option_module(""):
            result = await _match_option("xyz", ["Fighter", "Wizard"])
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_options_returns_none_without_llm_call(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        with patch(
            "monitor_agents.character_creator.text_matching.OptionMatchModule"
        ) as MockModule:
            result = await _match_option("Fighter", [])
            MockModule.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_input_returns_none_without_llm_call(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        with patch(
            "monitor_agents.character_creator.text_matching.OptionMatchModule"
        ) as MockModule:
            result = await _match_option("", ["Fighter", "Wizard"])
            MockModule.assert_not_called()
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self):
        from monitor_agents.loops.character_creation_loop import _match_option

        with patch(
            "monitor_agents.character_creator.text_matching.OptionMatchModule",
            side_effect=RuntimeError("boom"),
        ):
            result = await _match_option("Fighter", ["Fighter", "Wizard"])
        assert result is None


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
        from monitor_agents.loops.character_creation_loop import (
            _build_completion_message,
        )

        state = _make_state(character_name="Aragorn", attributes={"STR": 14})
        msg = _build_completion_message(state)
        assert "Aragorn" in msg
        assert "Complete" in msg

    def test_unnamed_character(self):
        from monitor_agents.loops.character_creation_loop import (
            _build_completion_message,
        )

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
                {
                    "step_type": "choose_name",
                    "title": "Name",
                    "instructions": "What is your name?",
                }
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
    @pytest.mark.asyncio
    async def test_empty_input_stays_awaiting(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(player_input=None)
        result = await process_input(state)
        assert result.get("awaiting_input") is True

    @pytest.mark.asyncio
    async def test_choose_name_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_name", "title": "Name"}],
            current_step_index=0,
            player_input="Aragorn",
        )
        result = await process_input(state)
        assert result["character_name"] == "Aragorn"
        assert result["current_step_index"] == 1
        assert "name" in result["character_data"]

    @pytest.mark.asyncio
    async def test_choose_concept_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_concept", "title": "Concept"}],
            player_input="A wandering ranger",
        )
        result = await process_input(state)
        assert result["concept"] == "A wandering ranger"
        assert result["character_data"]["concept"] == "A wandering ranger"

    @pytest.mark.asyncio
    async def test_choose_class_matches_option(self):
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
        with _mock_option_module("Fighter"):
            result = await process_input(state)
        assert result["choices"]["class"] == "Fighter"
        assert result["current_step_index"] == 1

    @pytest.mark.asyncio
    async def test_choose_species_advances(self):
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
        with _mock_option_module("Human"):
            result = await process_input(state)
        assert result["choices"]["species"] == "Human"

    @pytest.mark.asyncio
    async def test_choose_background_advances(self):
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
        with _mock_option_module("Noble"):
            result = await process_input(state)
        assert result["background"] == "Noble"
        assert "background" in result["choices"]

    @pytest.mark.asyncio
    async def test_choose_skills_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[
                {
                    "step_type": "choose_skills",
                    "title": "Skills",
                    "game_context": {},
                }
            ],
            skills={"existing_skill": 1},
            game_context={"skills": [{"name": "Stealth"}, {"name": "Perception"}]},
            player_input="stealth, perception",
        )
        with _mock_skill_module('{"Stealth": true, "Perception": true}'):
            result = await process_input(state)
        assert "Stealth" in result["skills"]
        assert result["skills"]["existing_skill"] == 1

    @pytest.mark.asyncio
    async def test_choose_equipment_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_equipment", "title": "Equipment"}],
            player_input="sword and shield",
        )
        result = await process_input(state)
        assert result["choices"]["equipment"] == "sword and shield"
        assert result["character_data"]["equipment"] == "sword and shield"

    @pytest.mark.asyncio
    async def test_choose_feats_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[
                {
                    "step_type": "choose_feats",
                    "title": "Feats",
                    "options": ["Alert", "Lucky"],
                }
            ],
            player_input="Alert",
        )
        with _mock_option_module("Alert"):
            result = await process_input(state)
        assert result["choices"]["feats"] == "Alert"

    @pytest.mark.asyncio
    async def test_choose_feats_without_options_stores_raw_text(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_feats", "title": "Feats"}],
            player_input="Alert",
        )
        with patch(
            "monitor_agents.character_creator.text_matching.OptionMatchModule"
        ) as MockModule:
            result = await process_input(state)
            MockModule.assert_not_called()
        assert result["choices"]["feats"] == "Alert"

    @pytest.mark.asyncio
    async def test_choose_spells_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "choose_spells", "title": "Spells"}],
            player_input="Fireball",
        )
        result = await process_input(state)
        assert "spells" in result["choices"]

    @pytest.mark.asyncio
    async def test_write_backstory_advances(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "write_backstory", "title": "Backstory"}],
            player_input="A tale of woe",
        )
        result = await process_input(state)
        assert "backstory" in result["choices"]

    @pytest.mark.asyncio
    async def test_custom_step_without_options_stores_raw_text_no_llm_call(self):
        """No options on the step -> no schema to match against -> raw
        text stored directly, no LLM round-trip."""
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[{"step_type": "weird_custom_thing", "title": "Custom"}],
            player_input="my answer",
        )
        with patch(
            "monitor_agents.character_creator.text_matching.OptionMatchModule"
        ) as MockModule:
            result = await process_input(state)
            MockModule.assert_not_called()
        assert result["choices"]["Custom"] == "my answer"
        assert result["current_step_index"] == 1

    @pytest.mark.asyncio
    async def test_custom_step_with_options_matches_via_llm(self):
        """The generic/custom branch is where perk selection lands (no
        dedicated step_type in most ingested schemas) -- when the step
        does supply options, match against them like named steps do."""
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[
                {
                    "step_type": "custom",
                    "title": "Choose Your First Perk",
                    "options": ["Rad Resistant", "Bloody Mess"],
                }
            ],
            player_input="Take the Rad Resistant perk",
        )
        with _mock_option_module("Rad Resistant"):
            result = await process_input(state)
        assert result["choices"]["Choose Your First Perk"] == "Rad Resistant"
        assert result["current_step_index"] == 1

    @pytest.mark.asyncio
    async def test_optional_step_skip(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[
                {"step_type": "custom", "title": "Opt", "is_optional": True}
            ],
            player_input="skip",
        )
        result = await process_input(state)
        assert result["current_step_index"] == 1
        assert result["choices"]["Opt"] == "skipped"

    @pytest.mark.asyncio
    async def test_index_past_end_completes(self):
        from monitor_agents.loops.character_creation_loop import process_input

        state = _make_state(
            creation_steps=[],
            current_step_index=5,
            player_input="anything",
        )
        result = await process_input(state)
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
