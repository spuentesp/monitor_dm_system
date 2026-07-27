"""Regression tests: match_consequence_choice must not fabricate a player
decision from a stray digit in an unrelated sentence, and must not pick
by stopword-blind word overlap.

Previously: `re.search(r"\\b([1-9])\\b", lowered)` matched the FIRST digit
ANYWHERE in the message -- "Wait, give me 2 secs to think" silently
"chose" option 2 before the word-overlap fallback (itself stopword-blind)
even ran, discarding what the player actually said and committing an
irreversible session-state change. See the `no-brittle-patches` project
rule -- this is now genuine LLM matching, with only an *exact* bare-number
message ("2", "#2", "2.") treated as a structured menu pick.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from monitor_ui.routers.chat_support import match_consequence_choice

OPTIONS = [
    "Take 2 stress and expose your position",
    "Lose your grip and drop the case",
]


def _mock_option_module(matched_option: str):
    return patch(
        "monitor_agents.character_creator.text_matching.OptionMatchModule",
        return_value=lambda **_kwargs: SimpleNamespace(matched_option=matched_option),
    )


@pytest.mark.asyncio
async def test_exact_bare_number_is_a_structured_pick_no_llm_call():
    with patch("monitor_agents.character_creator.text_matching.OptionMatchModule") as MockModule:
        result = await match_consequence_choice("2", OPTIONS)
        MockModule.assert_not_called()
    assert result == "Lose your grip and drop the case"

    with patch("monitor_agents.character_creator.text_matching.OptionMatchModule") as MockModule:
        result = await match_consequence_choice("#1", OPTIONS)
        MockModule.assert_not_called()
    assert result == "Take 2 stress and expose your position"


@pytest.mark.asyncio
async def test_digit_embedded_in_an_unrelated_sentence_does_not_fabricate_a_choice():
    """The original bug: "give me 2 secs to think" must NOT silently
    resolve to option 2 -- it isn't a numbered pick, it's the player
    stalling, and must go through real interpretation instead."""
    with _mock_option_module(""):
        result = await match_consequence_choice("Wait, give me 2 secs to think", OPTIONS)
    assert result is None


@pytest.mark.asyncio
async def test_paraphrased_answer_matches_via_llm():
    with _mock_option_module("Lose your grip and drop the case"):
        result = await match_consequence_choice("I guess I'll just drop it rather than risk being seen", OPTIONS)
    assert result == "Lose your grip and drop the case"


@pytest.mark.asyncio
async def test_llm_receives_the_options_verbatim():
    captured = {}

    def fake_module(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(matched_option=OPTIONS[0])

    with patch(
        "monitor_agents.character_creator.text_matching.OptionMatchModule",
        return_value=fake_module,
    ):
        await match_consequence_choice("I'll expose myself", OPTIONS)

    assert captured["player_answer"] == "I'll expose myself"
    assert OPTIONS[0] in captured["available_options"]
    assert OPTIONS[1] in captured["available_options"]


@pytest.mark.asyncio
async def test_no_match_returns_none():
    with _mock_option_module(""):
        result = await match_consequence_choice("I have no idea what you mean", OPTIONS)
    assert result is None


@pytest.mark.asyncio
async def test_llm_hallucinating_an_option_not_in_the_list_is_rejected():
    """Defense in depth: even if the LLM returns something, only an exact
    verbatim match against the real options list is accepted."""
    with _mock_option_module("Some option that was never offered"):
        result = await match_consequence_choice("whatever", OPTIONS)
    assert result is None


@pytest.mark.asyncio
async def test_empty_input_returns_none_without_llm_call():
    with patch("monitor_agents.character_creator.text_matching.OptionMatchModule") as MockModule:
        result = await match_consequence_choice("", OPTIONS)
        MockModule.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_empty_options_returns_none_without_llm_call():
    with patch("monitor_agents.character_creator.text_matching.OptionMatchModule") as MockModule:
        result = await match_consequence_choice("2", [])
        MockModule.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_llm_failure_returns_none():
    with patch(
        "monitor_agents.character_creator.text_matching.OptionMatchModule",
        side_effect=RuntimeError("boom"),
    ):
        result = await match_consequence_choice("I'll take the stress", OPTIONS)
    assert result is None
