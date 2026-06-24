"""
Unit tests for the NPCProfileGenerator (card → structured profile).

No live LM/DB — the DSPy context and the predictor are mocked so we exercise
the parsing + coercion + fallback logic only.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import patch

from monitor_agents.prompts import npc_profile_gen as gen
from monitor_agents.prompts.npc_profile_gen import (
    NPCProfileGenerator,
    _coerce_profile,
    _neutral_profile,
)


# ---------------------------------------------------------------------------
# Pure coercion helpers
# ---------------------------------------------------------------------------


class TestCoerceProfile:
    def test_clamps_traits_and_drops_bad_values(self):
        out = _coerce_profile({"traits": {"a": 2.0, "b": -5.0, "c": "nope"}})
        assert out["traits"] == {"a": 1.0, "b": -1.0, "c": 0.0}

    def test_filters_empty_list_items_and_caps(self):
        out = _coerce_profile({"values": ["honor", "", "  ", "family"]})
        assert out["values"] == ["honor", "family"]

    def test_triggers_require_condition_and_reaction(self):
        out = _coerce_profile(
            {
                "triggers": [
                    {"condition": "asked about X", "reaction": "deflects", "intensity": 9},
                    {"condition": "", "reaction": "noop"},  # dropped
                    {"reaction": "noop"},  # dropped
                ]
            }
        )
        assert len(out["triggers"]) == 1
        t = out["triggers"][0]
        assert t["condition"] == "asked about X"
        assert t["intensity"] == 1.0  # clamped
        assert t["is_hidden"] is True  # default

    def test_speech_style_empty_becomes_none(self):
        assert _coerce_profile({"speech_style": "  "})["speech_style"] is None

    def test_emotional_state_defaults_to_neutral(self):
        assert _coerce_profile({})["current_emotional_state"] == "neutral"

    def test_neutral_profile_is_valid_shape(self):
        n = _neutral_profile("Anyone")
        assert set(n) >= {"traits", "values", "fears", "desires", "triggers"}
        assert n["current_emotional_state"] == "neutral"


# ---------------------------------------------------------------------------
# forward() parsing — predictor + context mocked
# ---------------------------------------------------------------------------


def _run_forward_with_output(profile_json: str) -> dict:
    generator = NPCProfileGenerator()

    def fake_generate(**_kwargs):
        return SimpleNamespace(profile_json=profile_json)

    with (
        patch.object(gen, "dspy_context_for", return_value=contextlib.nullcontext()),
        patch.object(generator, "generate", side_effect=fake_generate),
    ):
        return generator.forward(name="Maeve", description="a wary tavern keeper")


class TestForwardParsing:
    def test_parses_clean_json(self):
        out = _run_forward_with_output(
            '{"traits": {"wariness": 0.8}, "values": ["self-preservation"], '
            '"current_emotional_state": "guarded"}'
        )
        assert out["traits"] == {"wariness": 0.8}
        assert out["values"] == ["self-preservation"]
        assert out["current_emotional_state"] == "guarded"

    def test_parses_json_in_code_fence(self):
        out = _run_forward_with_output('```json\n{"values": ["honor"]}\n```')
        assert out["values"] == ["honor"]

    def test_parses_json_with_surrounding_prose(self):
        out = _run_forward_with_output(
            'Here is the profile you asked for:\n{"fears": ["betrayal"]}\nHope that helps!'
        )
        assert out["fears"] == ["betrayal"]

    def test_falls_back_to_neutral_on_garbage(self):
        out = _run_forward_with_output("not json at all")
        assert out == _neutral_profile("Maeve")
