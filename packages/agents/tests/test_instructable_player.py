"""Hermetic tests for ``InstructablePlayer``.

These tests verify the player *shape* — scripted fallback, LLM fallback,
observation buffer cap, intent classification, coherence overlap. They
mock litellm so no model is contacted.
"""

from __future__ import annotations

from typing import Any

import pytest

from monitor_agents.players import (
    InstructablePlayer,
    InstructedSpec,
    MockSpec,
    PlayerContext,
    ScriptedSpec,
    classify_player_intent,
    coherence_count,
)

# ============================================================================
# ScriptedSpec + base shape
# ============================================================================


@pytest.mark.asyncio
async def test_scripted_replays_arc_then_falls_back() -> None:
    player = InstructablePlayer(
        spec=ScriptedSpec(arc=[("I open the door.", "explore")]),
        context=PlayerContext(concept="Rook", seed=""),
    )
    # First call returns the scripted line.
    a1, i1 = await player.next()
    assert a1 == "I open the door."
    assert i1 == "explore"
    # Second call is the fallback.
    a2, i2 = await player.next()
    assert a2 == "I take stock of the situation."
    assert i2 == "fallback observation"


@pytest.mark.asyncio
async def test_observe_caps_recent_turns() -> None:
    player = InstructablePlayer(
        spec=MockSpec(lines=[("a", "x")]),
        context=PlayerContext(concept="x", seed=""),
        recent_turns_max=3,
    )
    for i in range(20):
        player.observe(gm_text=f"gm {i}", player_text=f"pl {i}", intent="x")
    # Trim is `recent_turns_max * 2 = 6`.
    assert len(player._recent_turns) <= 6


# ============================================================================
# InstructedSpec — scripted_opens + LLM path + error fallback
# ============================================================================


@pytest.mark.asyncio
async def test_instructed_spec_uses_scripted_opens_first() -> None:
    spec = InstructedSpec(
        model="ollama/qwen2.5:latest",
        scripted_opens=[("I lean in.", "social")],
    )
    player = InstructablePlayer(
        spec=spec,
        context=PlayerContext(concept="x", seed=""),
    )
    a, i = await player.next()
    assert a == "I lean in."
    assert i == "social"


@pytest.mark.asyncio
async def test_instructed_spec_falls_back_on_raised_error() -> None:
    def boom(**kwargs):
        raise RuntimeError("litellm-down")

    spec = InstructedSpec(model="ollama/x", _llm_call=boom)
    player = InstructablePlayer(
        spec=spec,
        context=PlayerContext(concept="x", seed=""),
    )
    a, i = await player.next()
    assert a == "I take stock of the situation."
    assert i.startswith("fallback")


@pytest.mark.asyncio
async def test_instructed_spec_falls_back_on_empty_string() -> None:
    spec = InstructedSpec(model="ollama/x", _llm_call=lambda **k: "   \n")
    player = InstructablePlayer(
        spec=spec,
        context=PlayerContext(concept="x", seed=""),
    )
    a, i = await player.next()
    assert i == "fallback (empty player output)"


@pytest.mark.asyncio
async def test_instructed_spec_classifies_intent() -> None:
    spec = InstructedSpec(model="ollama/x", _llm_call=lambda **k: "I swing my sword.")
    player = InstructablePlayer(
        spec=spec,
        context=PlayerContext(concept="x", seed=""),
    )
    action, intent = await player.next()
    assert "physical" in intent
    assert action == "I swing my sword."


# ============================================================================
# system_prompt override (char-creation mode)
# ============================================================================


@pytest.mark.asyncio
async def test_system_prompt_override_replaces_default() -> None:
    """When PlayerContext.system_prompt is set, that text is used as the
    system message instead of the default PLAYER_SYSTEM_PROMPT_TEMPLATE.
    Used by ``--character-driver llm`` to keep the LLM in structured-answer
    mode during char creation instead of in-character reaction mode.
    """
    captured: dict[str, Any] = {}

    def fake_llm(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return ""

    spec = InstructedSpec(model="ollama/x", _llm_call=fake_llm)
    ctx = PlayerContext(
        concept="vtm_pc",
        seed="Victorian horror",
        system_prompt="You are answering mechanical questions. Reply with just the data.",
    )
    player = InstructablePlayer(spec=spec, context=ctx)
    await player.next()
    assert captured, "fake LLM was not invoked"
    system_msg = captured["messages"][0]
    assert system_msg["role"] == "system"
    assert system_msg["content"].startswith("You are answering mechanical questions.")
    # And the default template must NOT leak in.
    assert "You are a tabletop RPG player" not in system_msg["content"]


@pytest.mark.asyncio
async def test_default_system_prompt_is_template() -> None:
    """Without an override, the default PLAYER_SYSTEM_PROMPT_TEMPLATE is
    still emitted (regression guard on the override branch).
    """
    captured: dict[str, Any] = {}

    def fake_llm(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return ""

    spec = InstructedSpec(model="ollama/x", _llm_call=fake_llm)
    ctx = PlayerContext(concept="vtm_pc", seed="Victorian horror")  # no override
    player = InstructablePlayer(spec=spec, context=ctx)
    await player.next()
    system_msg = captured["messages"][0]
    assert "You are a tabletop RPG player" in system_msg["content"]
    assert "vtm_pc" in system_msg["content"]
    assert "Victorian horror" in system_msg["content"]


# ============================================================================
# Language constraint — default English, opt-out for non-English sessions.
# Regression guards for the qwen2.5 → Chinese drift observed in the
# 2026-07-23 LLM-vs-LLM play log (VtM Turn 5). The constraint is part of
# the default system prompt (single source of truth: _LANGUAGE_CLAUSES)
# and is NOT appended on top of caller-supplied overrides.
# ============================================================================


@pytest.mark.asyncio
async def test_default_system_prompt_appends_english_language_clause() -> None:
    """The default template path appends the English language clause.

    This is the regression guard for the qwen2.5 Chinese drift: with no
    override and the default language, the player LLM must see an
    explicit "Respond only in English." instruction. Lives at the END
    of the system message so the LLM (which attends more to recent
    instructions) honors it."""
    captured: dict[str, Any] = {}

    def fake_llm(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return ""

    spec = InstructedSpec(model="ollama/x", _llm_call=fake_llm)
    ctx = PlayerContext(concept="vtm_pc", seed="Victorian horror")
    player = InstructablePlayer(spec=spec, context=ctx)
    await player.next()

    assert captured, "fake LLM was not invoked"
    system_msg = captured["messages"][0]
    assert system_msg["role"] == "system"
    content = system_msg["content"]
    # The clause is present.
    assert "Respond only in English." in content
    # And it's the LAST line (so it sits at the end of the prompt).
    assert content.rstrip().endswith("Respond only in English.")


@pytest.mark.asyncio
async def test_system_prompt_override_does_not_get_language_clause_appended() -> None:
    """When a caller provides ``system_prompt``, they own the prompt —
    the language clause is NOT appended on top. This is the
    documented contract: overrides are caller's responsibility.

    Regression guard: an earlier draft of the language fix did append
    on top of overrides, which double-stacked the clause and surprised
    callers passing their own system_prompt for char-creation dialog."""
    captured: dict[str, Any] = {}

    def fake_llm(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return ""

    spec = InstructedSpec(model="ollama/x", _llm_call=fake_llm)
    override = "You are answering mechanical questions. Reply with just the data."
    ctx = PlayerContext(
        concept="vtm_pc",
        seed="Victorian horror",
        system_prompt=override,
    )
    player = InstructablePlayer(spec=spec, context=ctx)
    await player.next()

    system_msg = captured["messages"][0]
    content = system_msg["content"]
    # Exactly the override, no extras.
    assert content == override
    # Specifically: the default-template language clause did NOT bleed in.
    assert "Respond only in English." not in content
    assert "vtm_pc" not in content
    assert "Victorian horror" not in content


@pytest.mark.asyncio
async def test_language_field_overrides_default_clause() -> None:
    """Setting PlayerContext.language to a non-default code swaps the
    appended clause. The default English clause is replaced (not
    appended-on-top) — so a Japanese-language session sends the LLM
    one clear language instruction, not two conflicting ones.

    This is the path that lets future tests / harnesses drive a
    non-English player LLM (e.g. a Japanese persona in a J-RPG
    scenario) without hardcoding the language in the system prompt."""
    captured: dict[str, Any] = {}

    def fake_llm(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return ""

    spec = InstructedSpec(model="ollama/x", _llm_call=fake_llm)
    ctx = PlayerContext(
        concept="fallout_scavenger",
        seed="post-nuclear wasteland",
        language="ja",
    )
    player = InstructablePlayer(spec=spec, context=ctx)
    await player.next()

    system_msg = captured["messages"][0]
    content = system_msg["content"]
    # The Japanese clause is present and is the LAST line.
    assert "日本語のみで応答してください。" in content
    assert content.rstrip().endswith("日本語のみで応答してください。")
    # The English clause does NOT appear.
    assert "Respond only in English." not in content


@pytest.mark.asyncio
async def test_unknown_language_falls_back_to_english_with_warning() -> None:
    """If a caller passes an unsupported language code, the player
    emits the English clause and logs a warning. This keeps a
    misconfigured harness from emitting NO language clause (which
    was the original bug — qwen2.5 drifted to Chinese)."""
    captured: dict[str, Any] = {}

    def fake_llm(**kwargs):
        captured["messages"] = kwargs.get("messages", [])
        return ""

    spec = InstructedSpec(model="ollama/x", _llm_call=fake_llm)
    ctx = PlayerContext(
        concept="vtm_pc",
        seed="Victorian horror",
        language="klingon",  # intentionally unsupported
    )
    player = InstructablePlayer(spec=spec, context=ctx)
    await player.next()

    system_msg = captured["messages"][0]
    content = system_msg["content"]
    # Fallback to English so the LLM always has a language instruction.
    assert "Respond only in English." in content
    assert content.rstrip().endswith("Respond only in English.")


# ============================================================================
# Cheap helpers
# ============================================================================


# ============================================================================
# MockSpec — deterministic test-only driver
# ============================================================================


@pytest.mark.asyncio
async def test_mock_spec_uses_callable_when_provided() -> None:
    spec = MockSpec(
        lines=[],
        provider=lambda scripted_left: (
            f"custom at {scripted_left}",
            "test",
        ),
    )
    player = InstructablePlayer(
        spec=spec,
        context=PlayerContext(concept="x", seed=""),
    )
    assert await player.next() == ("custom at 0", "test")


# ============================================================================
# Cheap helpers
# ============================================================================


def test_classify_intent_categories() -> None:
    assert classify_player_intent("I ask the barkeep about the stranger.") == "social / dialogue"
    assert classify_player_intent("I search the room.") == "observe / investigate"
    assert classify_player_intent("I wonder if it's a trap.") == "reflection"
    assert "physical" in classify_player_intent("I attack the guard.")


def test_coherence_count_counts_only_overlap() -> None:
    # No overlap.
    assert coherence_count("apple banana", "cherry date") == 0
    # Two common content words.
    assert coherence_count("the corridor collapses loudly", "corridor leaks loudly") >= 1
    # Stopwords excluded.
    assert coherence_count("the and with", "the and with") == 0
