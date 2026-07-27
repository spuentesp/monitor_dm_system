"""
Tests for the Narrator agent.

Covers:
- _format_resolution: pure logic, converts resolution dict to summary string
- _parse_proposed_changes: JSON string parsing from DSPy output
- narrate_turn: full pipeline with mocked DSPy module (single LLM call)
- _persist_turn: MongoDB tool calls, JSON parsing, fallback UUID

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_narrator.py -v
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from monitor_agents.loops.story_loop import StoryState
from monitor_agents.narrator.agent import Narrator

# ===========================================================================
# _format_resolution
# ===========================================================================


class TestFormatResolution:
    def setup_method(self):
        self.narrator = Narrator.__new__(Narrator)

    def test_none_resolution_returns_narrative(self):
        assert self.narrator._format_resolution(None) == "narrative"

    def test_empty_dict_returns_narrative(self):
        # Empty dict is falsy, so treated the same as None → "narrative"
        result = self.narrator._format_resolution({})
        assert result == "narrative"

    def test_success_level_only(self):
        result = self.narrator._format_resolution({"success_level": "success"})
        assert result == "success"

    def test_critical_success_level(self):
        result = self.narrator._format_resolution({"success_level": "critical_success"})
        assert result == "critical_success"

    def test_critical_failure_level(self):
        result = self.narrator._format_resolution({"success_level": "critical_failure"})
        assert result == "critical_failure"

    def test_with_roll_total_and_stat(self):
        result = self.narrator._format_resolution({"success_level": "success", "roll_total": 17, "stat": "STR"})
        assert "success" in result
        assert "Roll: 17 (STR)" in result

    def test_roll_without_stat_is_omitted(self):
        result = self.narrator._format_resolution({"success_level": "failure", "roll_total": 5})
        assert result == "failure"
        assert "Roll" not in result

    def test_with_zero_roll_and_stat(self):
        result = self.narrator._format_resolution({"success_level": "failure", "roll_total": 0, "stat": "DEX"})
        assert "Roll: 0 (DEX)" in result

    def test_with_effects_list(self):
        effects = [{"description": "goblin takes 6 damage"}, {"description": "goblin stunned"}]
        result = self.narrator._format_resolution({"success_level": "success", "effects": effects})
        assert "Effects:" in result
        # Both effects should appear as str() representations
        assert "goblin takes 6 damage" in result or "description" in result

    def test_empty_effects_list_omitted(self):
        result = self.narrator._format_resolution({"success_level": "failure", "effects": []})
        assert "Effects" not in result

    def test_full_resolution_all_parts(self):
        result = self.narrator._format_resolution(
            {
                "success_level": "partial_success",
                "roll_total": 12,
                "stat": "WIS",
                "effects": [{"description": "avoided most damage"}],
            }
        )
        assert "partial_success" in result
        assert "Roll: 12 (WIS)" in result
        assert "Effects:" in result

    def test_return_type_is_string(self):
        result = self.narrator._format_resolution({"success_level": "success"})
        assert isinstance(result, str)

    def test_parts_joined_by_period_space(self):
        """Parts are joined with '. '."""
        result = self.narrator._format_resolution({"success_level": "success", "roll_total": 10, "stat": "CHA"})
        assert ". " in result

    def test_propose_roll(self):
        result = self.narrator._format_resolution(
            {"resolution_type": "propose_roll", "stat": "DEX", "difficulty_class": 15}
        )
        assert result == "propose_roll:DEX (DC 15)"

    def test_propose_roll_no_dc(self):
        result = self.narrator._format_resolution({"resolution_type": "propose_roll", "stat": "STR"})
        assert result == "propose_roll:STR"

    def test_narrative_resolution_type(self):
        result = self.narrator._format_resolution({"resolution_type": "narrative", "success_level": "success"})
        assert result == "narrative"

    def test_trivial_resolution_type(self):
        result = self.narrator._format_resolution({"resolution_type": "trivial"})
        assert result == "narrative"


# ===========================================================================
# _persist_turn
# ===========================================================================


class TestPersistTurn:
    @pytest.mark.asyncio
    async def test_persist_writes_user_turn_when_input_given(self):
        """When user_input is provided, two tool calls happen (user + gm)."""
        narrator = Narrator.__new__(Narrator)
        narrator.call_tool = AsyncMock(return_value=json.dumps({"turn_id": "turn-xyz"}))
        scene_id = uuid4()

        await narrator._persist_turn(
            scene_id=scene_id,
            user_input="I climb the wall",
            narrative_text="With a grunt you haul yourself up.",
            resolution=None,
        )

        assert narrator.call_tool.call_count == 2
        first_call = narrator.call_tool.call_args_list[0][0]
        assert first_call[0] == "mongodb_append_turn"

    @pytest.mark.asyncio
    async def test_persist_skips_user_turn_when_no_input(self):
        """When user_input is None, only the GM turn is written."""
        narrator = Narrator.__new__(Narrator)
        narrator.call_tool = AsyncMock(return_value=json.dumps({"turn_id": "turn-abc"}))

        await narrator._persist_turn(
            scene_id=uuid4(),
            user_input=None,
            narrative_text="The scene opens in darkness.",
            resolution=None,
        )

        assert narrator.call_tool.call_count == 1

    @pytest.mark.asyncio
    async def test_persist_returns_turn_id_from_response(self):
        """turn_id is parsed from the last tool call's JSON response."""
        narrator = Narrator.__new__(Narrator)
        expected_id = "turn-expected-123"
        narrator.call_tool = AsyncMock(return_value=json.dumps({"turn_id": expected_id}))

        result = await narrator._persist_turn(
            scene_id=uuid4(),
            user_input=None,
            narrative_text="...",
            resolution=None,
        )

        assert result == expected_id

    @pytest.mark.asyncio
    async def test_persist_accepts_dict_response(self):
        """When the Mongo tool already returns a dict, _persist_turn should accept it."""
        narrator = Narrator.__new__(Narrator)
        narrator.call_tool = AsyncMock(return_value={"turn_id": "turn-dict-123"})

        result = await narrator._persist_turn(
            scene_id=uuid4(),
            user_input=None,
            narrative_text="...",
            resolution=None,
        )

        assert result == "turn-dict-123"

    @pytest.mark.asyncio
    async def test_persist_falls_back_to_uuid_on_invalid_json(self):
        """When tool returns invalid JSON, _persist_turn generates a UUID fallback."""
        narrator = Narrator.__new__(Narrator)
        narrator.call_tool = AsyncMock(return_value="not valid json{{{{")

        result = await narrator._persist_turn(
            scene_id=uuid4(),
            user_input=None,
            narrative_text="...",
            resolution=None,
        )

        # Should be a valid UUID string
        UUID(result)

    @pytest.mark.asyncio
    async def test_persist_falls_back_to_uuid_on_empty_response(self):
        """When tool returns None/empty, falls back to a generated UUID string."""
        narrator = Narrator.__new__(Narrator)
        narrator.call_tool = AsyncMock(return_value=None)

        result = await narrator._persist_turn(
            scene_id=uuid4(),
            user_input=None,
            narrative_text="...",
            resolution=None,
        )

        UUID(result)

    @pytest.mark.asyncio
    async def test_persist_falls_back_to_uuid_when_no_turn_id_key(self):
        """When JSON has no turn_id key, falls back to a UUID."""
        narrator = Narrator.__new__(Narrator)
        narrator.call_tool = AsyncMock(return_value=json.dumps({"status": "ok"}))

        result = await narrator._persist_turn(
            scene_id=uuid4(),
            user_input=None,
            narrative_text="...",
            resolution=None,
        )

        UUID(result)


# ===========================================================================
# narrate_turn (single-phase: DSPy generates prose + proposals in one call)
# ===========================================================================


class TestNarrateTurn:
    """Tests for narrate_turn — single LLM call via DSPy NarratorModule.

    The NarratorModule returns a Prediction with:
      - narrative_text: str  (the GM prose)
      - proposed_changes: str  (JSON array string of world-state changes)

    narrate_turn parses proposed_changes via _parse_proposed_changes and
    returns them as dicts.  No second LLM call (no instructor/structured output).
    """

    @staticmethod
    def _make_prediction(
        narrative_text: str = "The GM speaks.",
        proposed_changes: str = "[]",
    ) -> MagicMock:
        pred = MagicMock()
        pred.narrative_text = narrative_text
        pred.proposed_changes = proposed_changes
        return pred

    @staticmethod
    def _make_narrator(prediction: MagicMock) -> Narrator:
        narrator = Narrator.__new__(Narrator)
        narrator.agent_type = "Narrator"
        narrator.agent_id = "narrator-1"
        narrator._narrator_module = MagicMock(return_value=prediction)
        narrator._persist_turn = AsyncMock(return_value="turn-001")

        # Mock ToneResolver
        narrator._tone_resolver = MagicMock()

        async def mock_resolve(gm_profile=None, fallback_tone="dramatic"):
            # Simple simulation of BUILTIN_TONE_PROFILES for tests
            builtins = {
                "dramatic": "Baroque, weighty.",
                "grim": "Terse, industrial.",
            }
            return builtins.get(fallback_tone, "Dramatic.")

        narrator._tone_resolver.resolve_from_profile = AsyncMock(side_effect=mock_resolve)

        return narrator

    @pytest.mark.asyncio
    async def test_narrate_turn_returns_expected_keys(self):
        """narrate_turn returns narrative_text, proposals, and turn_id."""
        pred = self._make_prediction("You slay the dragon.", "[]")
        narrator = self._make_narrator(pred)

        result = await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input="I attack the dragon",
            resolution={"success_level": "critical_success", "roll_total": 20},
            context={"entities": [], "memories": [], "turns": []},
        )

        assert "narrative_text" in result
        assert "proposals" in result
        assert "turn_id" in result
        assert result["narrative_text"] == "You slay the dragon."
        assert result["turn_id"] == "turn-001"

    @pytest.mark.asyncio
    async def test_narrate_turn_calls_narrator_module(self):
        """narrate_turn invokes the DSPy NarratorModule with correct args."""
        pred = self._make_prediction("You discover a hidden passage.", "[]")
        narrator = self._make_narrator(pred)

        entities = [{"id": "e1"}]
        turns = [{"role": "user", "text": "look around"}]

        await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input="search the wall",
            resolution=None,
            context={"entities": entities, "turns": turns, "memories": []},
        )

        narrator._narrator_module.assert_called_once()
        call_kwargs = narrator._narrator_module.call_args[1]
        assert "player_action" in call_kwargs
        assert call_kwargs["player_action"] == "search the wall"
        assert "resolution_summary" in call_kwargs
        assert call_kwargs["resolution_summary"] == "narrative"  # None → "narrative"

    @pytest.mark.asyncio
    async def test_narrate_turn_injects_profile_context_and_tone_hints(self):
        """High-confidence source profile data should shape narrator context and tone."""
        pred = self._make_prediction("The prince regards you over the rim of a crystal goblet.", "[]")
        narrator = self._make_narrator(pred)

        await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input="I ask the prince about the embrace",
            resolution={"success_level": "success"},
            context={
                "source_profile": {
                    "system_name": "V20",
                    "genre_tone": ["personal horror", "political intrigue"],
                    "narrative_frame": ["tragic", "investigative"],
                    "institution_model": ["sect allegiance", "prince-led domains"],
                    "canon_signal_terms": ["Prince", "Primogen"],
                    "term_lexicon": {"Embrace": ["Siring"], "Kindred": ["Cainites"]},
                    "confidence_by_field": {
                        "system_name": 0.97,
                        "genre_tone": 0.94,
                        "narrative_frame": 0.91,
                        "institution_model": 0.89,
                        "canon_signal_terms": 0.9,
                        "term_lexicon": 0.93,
                    },
                }
            },
            session_tone="dramatic",
        )

        call_kwargs = narrator._narrator_module.call_args[1]
        assert "profile_context" in call_kwargs
        assert "Genre tone: personal horror, political intrigue" in call_kwargs["profile_context"]
        assert "Institution model: sect allegiance, prince-led domains" in call_kwargs["profile_context"]
        assert "personal horror" in call_kwargs["tone_context"]
        assert "political intrigue" in call_kwargs["tone_context"]

    @pytest.mark.asyncio
    async def test_narrate_turn_uses_scene_description_when_no_user_input(self):
        """narrate_turn substitutes '(scene description)' for None user_input."""
        pred = self._make_prediction("The scene unfolds...", "[]")
        narrator = self._make_narrator(pred)

        await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input=None,
            resolution=None,
            context={},
        )

        call_kwargs = narrator._narrator_module.call_args[1]
        assert call_kwargs["player_action"] == "(scene description)"

    @pytest.mark.asyncio
    async def test_narrate_turn_proposals_parsed_from_dspy_output(self):
        """narrate_turn parses proposals from the DSPy proposed_changes JSON string."""
        proposals_json = json.dumps(
            [
                {
                    "change_type": "entity_state_change",
                    "summary": "Door opened",
                    "content": {"entity_id": "door-1", "state": "open"},
                }
            ]
        )
        pred = self._make_prediction("The door swings open.", proposals_json)
        narrator = self._make_narrator(pred)

        result = await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input="open the door",
            resolution=None,
            context={},
        )

        assert len(result["proposals"]) == 1
        assert isinstance(result["proposals"][0], dict)
        assert result["proposals"][0]["change_type"] == "entity_state_change"
        assert result["proposals"][0]["summary"] == "Door opened"

    @pytest.mark.asyncio
    async def test_narrate_turn_empty_proposals(self):
        """narrate_turn handles empty proposed_changes gracefully."""
        pred = self._make_prediction("The wind howls.", "[]")
        narrator = self._make_narrator(pred)

        result = await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input="listen",
            resolution=None,
            context={},
        )

        assert result["proposals"] == []

    @pytest.mark.asyncio
    async def test_narrate_turn_persist_called_with_correct_args(self):
        """narrate_turn calls _persist_turn with the DSPy narrative_text directly."""
        pred = self._make_prediction("Arrows rain down on you.", "[]")
        narrator = self._make_narrator(pred)

        scene_id = uuid4()
        resolution = {"success_level": "failure"}

        await narrator.narrate_turn(
            scene_id=scene_id,
            user_input="dodge",
            resolution=resolution,
            context={},
        )

        narrator._persist_turn.assert_called_once_with(
            scene_id=scene_id,
            user_input="dodge",
            narrative_text="Arrows rain down on you.",
            resolution=resolution,
        )

    @pytest.mark.asyncio
    async def test_narrate_turn_no_second_llm_call(self):
        """Verify narrate_turn does NOT call call_llm_structured (single-phase)."""
        pred = self._make_prediction("The torch flickers.", "[]")
        narrator = self._make_narrator(pred)

        # If call_llm_structured exists, it should NOT be called
        narrator.call_llm_structured = AsyncMock(side_effect=AssertionError("Should not be called"))

        await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input="look around",
            resolution=None,
            context={},
        )

        # If we got here, call_llm_structured was not invoked — pass

    @pytest.mark.asyncio
    async def test_narrate_turn_with_gm_profile(self):
        """narrate_turn should call resolve_from_profile with the GM profile."""
        pred = self._make_prediction("Prose.", "[]")
        narrator = self._make_narrator(pred)

        gm_profile = {"name": "Test Profile", "tone_tags": ["grim"]}

        await narrator.narrate_turn(
            scene_id=uuid4(),
            user_input="...",
            resolution=None,
            context={},
            gm_profile=gm_profile,
            session_tone="grim",
        )

        narrator._tone_resolver.resolve_from_profile.assert_called_once_with(gm_profile, fallback_tone="grim")

    @pytest.mark.asyncio
    async def test_narrate_turn_injects_story_state(self):
        """story_state should be formatted and appended to profile_context."""
        pred = self._make_prediction("Prose.", "[]")
        narrator = self._make_narrator(pred)

        story_state = StoryState(
            story_id=uuid4(),
            universe_id=uuid4(),
            arc_label="The Rising Storm",
            tension_score=0.8,
            active_threads=["Finding the lost sword", "The traitor among us"],
        )

        await narrator.narrate_turn(
            scene_id=uuid4(), user_input="...", resolution=None, context={}, story_state=story_state
        )

        call_kwargs = narrator._narrator_module.call_args[1]
        assert "profile_context" in call_kwargs
        assert "STORY ARC CONTEXT:" in call_kwargs["profile_context"]
        assert "- Phase: The Rising Storm" in call_kwargs["profile_context"]
        assert "- Tension: 0.8/1.0" in call_kwargs["profile_context"]
        assert "- Active Threads: Finding the lost sword, The traitor among us" in call_kwargs["profile_context"]


# ===========================================================================
# _parse_proposed_changes
# ===========================================================================


class TestParseProposedChanges:
    """Tests for Narrator._parse_proposed_changes — JSON string → list[dict]."""

    def test_valid_json_array(self):
        raw = json.dumps(
            [
                {
                    "change_type": "entity_state_change",
                    "summary": "Door opened",
                    "content": {"state": "open"},
                },
                {"change_type": "relationship_change", "summary": "NPC angered", "content": {}},
            ]
        )
        result = Narrator._parse_proposed_changes(raw)
        assert len(result) == 2
        assert result[0]["change_type"] == "entity_state_change"

    def test_empty_string(self):
        assert Narrator._parse_proposed_changes("") == []

    def test_none_like_empty(self):
        assert Narrator._parse_proposed_changes("  ") == []

    def test_empty_json_array(self):
        assert Narrator._parse_proposed_changes("[]") == []

    def test_invalid_json(self):
        assert Narrator._parse_proposed_changes("not json at all") == []

    def test_partial_json_with_embedded_array(self):
        """DSPy sometimes wraps JSON in prose — extract the array."""
        raw = 'Here are the changes: [{"change_type": "npc_reaction", "summary": "Guard suspicious", "content": {}}]. End.'
        result = Narrator._parse_proposed_changes(raw)
        assert len(result) == 1
        assert result[0]["change_type"] == "npc_reaction"

    def test_markdown_code_fence_stripped(self):
        """LLM sometimes wraps JSON in ```json ... ``` fences."""
        raw = '```json\n[{"change_type": "weather", "summary": "Storm starts", "content": {}}]\n```'
        result = Narrator._parse_proposed_changes(raw)
        assert len(result) == 1
        assert result[0]["change_type"] == "weather"

    def test_non_list_json_returns_empty(self):
        """A JSON object (not array) should return empty list."""
        assert Narrator._parse_proposed_changes('{"key": "value"}') == []

    def test_dict_items_without_change_type_get_default(self):
        """Items missing change_type get 'narrative_implication' as default."""
        raw = json.dumps([{"summary": "Something happened", "content": {}}])
        result = Narrator._parse_proposed_changes(raw)
        assert len(result) == 1
        assert result[0]["change_type"] == "narrative_implication"

    def test_non_dict_items_filtered_out(self):
        """Non-dict items in the array are silently skipped."""
        raw = json.dumps(["string_item", 42, {"change_type": "valid", "summary": "ok", "content": {}}])
        result = Narrator._parse_proposed_changes(raw)
        assert len(result) == 1
        assert result[0]["change_type"] == "valid"

    def test_multiple_proposals_preserved(self):
        proposals = [{"change_type": "entity_state_change", "summary": f"Change {i}", "content": {}} for i in range(5)]
        result = Narrator._parse_proposed_changes(json.dumps(proposals))
        assert len(result) == 5
