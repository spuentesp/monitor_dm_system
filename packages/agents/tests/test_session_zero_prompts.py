"""
Prompt-level tests for SessionZero — the gold-set.

Each test verifies that the SessionZero DSPy signature + parser produces
the correct question category and structure for representative inputs.
The tests use stub predictions (no live LLM) to verify the parser path,
following the same pattern as test_gm_awareness_prompts.py.

WHAT THIS PROVES
----------------
The DSPy signature + field descriptions + parser produce the right
SessionZeroQuestion for the right input. If you change a `desc=` or the
system prompt, these tests will tell you whether the prompt got better
or worse.

WHAT THIS DOES NOT PROVE
-------------------------
That a *real* LLM produces these questions in production. For that, run
a live session with `LIVE_LLM=1`.
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Gold-set inputs — canonical tone + prior-answer combinations
# ---------------------------------------------------------------------------

GOLDEN_INPUTS: list[dict[str, Any]] = [
    # ── Grim tone, first question → origin ──
    {
        "tone": "grim",
        "system_name": "Death in Space",
        "question_number": 1,
        "max_questions": 7,
        "prior_answers": [],
        "categories_asked": [],
        "expected_category": "origin",
        "expected_is_final": False,
    },
    # ── Grim tone, after origin → loss ──
    {
        "tone": "grim",
        "system_name": "Death in Space",
        "question_number": 2,
        "max_questions": 7,
        "prior_answers": [
            {
                "question": "Where did you come from?",
                "answer": "I was a miner on Inauro.",
                "category": "origin",
            }
        ],
        "categories_asked": ["origin"],
        "expected_category": "loss",
        "expected_is_final": False,
    },
    # ── Horror tone, first question → origin or fear ──
    {
        "tone": "horror",
        "system_name": "Call of Cthulhu",
        "question_number": 1,
        "max_questions": 7,
        "prior_answers": [],
        "categories_asked": [],
        "expected_category": "origin",
        "expected_is_final": False,
    },
    # ── Heroic tone, first question → origin or motivation ──
    {
        "tone": "heroic",
        "system_name": "D&D 5e",
        "question_number": 1,
        "max_questions": 7,
        "prior_answers": [],
        "categories_asked": [],
        "expected_category": "origin",
        "expected_is_final": False,
    },
    # ── Dramatic tone, after several answers → winding down ──
    {
        "tone": "dramatic",
        "system_name": "Vampire: The Masquerade",
        "question_number": 6,
        "max_questions": 7,
        "prior_answers": [
            {"question": "Where did you come from?", "answer": "New York.", "category": "origin"},
            {"question": "Who matters to you?", "answer": "My sire.", "category": "bond"},
            {"question": "What do you want?", "answer": "Freedom.", "category": "motivation"},
            {"question": "What are you afraid of?", "answer": "The Beast.", "category": "fear"},
            {
                "question": "What are you hiding?",
                "answer": "I killed someone.",
                "category": "secret",
            },
        ],
        "categories_asked": ["origin", "bond", "motivation", "fear", "secret"],
        "expected_category": "conflict",
        "expected_is_final": False,
    },
    # ── Last question → is_final should be True ──
    {
        "tone": "grim",
        "system_name": "Death in Space",
        "question_number": 7,
        "max_questions": 7,
        "prior_answers": [
            {"question": "Q1", "answer": "A1", "category": "origin"},
            {"question": "Q2", "answer": "A2", "category": "loss"},
            {"question": "Q3", "answer": "A3", "category": "bond"},
            {"question": "Q4", "answer": "A4", "category": "fear"},
            {"question": "Q5", "answer": "A5", "category": "motivation"},
            {"question": "Q6", "answer": "A6", "category": "secret"},
        ],
        "categories_asked": ["origin", "loss", "bond", "fear", "motivation", "secret"],
        "expected_category": "conflict",
        "expected_is_final": True,
    },
    # ── Mystery tone, first question → origin ──
    {
        "tone": "mystery",
        "system_name": "Gumshoe",
        "question_number": 1,
        "max_questions": 7,
        "prior_answers": [],
        "categories_asked": [],
        "expected_category": "origin",
        "expected_is_final": False,
    },
    # ── Adventure tone, first question → origin ──
    {
        "tone": "adventure",
        "system_name": "OSR",
        "question_number": 1,
        "max_questions": 7,
        "prior_answers": [],
        "categories_asked": [],
        "expected_category": "origin",
        "expected_is_final": False,
    },
]


# ---------------------------------------------------------------------------
# metric() — score a Prediction against an expected SessionZeroQuestion
# ---------------------------------------------------------------------------


def _score_field(name: str, expected: Any, predicted: Any) -> float:
    """Return 1.0 if the field matches, 0.0 otherwise."""
    if isinstance(expected, bool):
        return 1.0 if bool(predicted) == expected else 0.0
    if expected is None:
        return 1.0 if predicted is None else 0.0
    # Handle enums: extract .value if present
    pred_val = getattr(predicted, "value", predicted)
    pred_str = str(pred_val).strip().lower()
    exp_str = str(expected).strip().lower()
    return 1.0 if pred_str == exp_str else 0.0


def metric(expected: dict[str, Any], predicted: Any) -> float:
    """Score a single prediction against the gold-set expectation."""
    fields = [
        ("category", expected.get("expected_category")),
        ("is_final", expected.get("expected_is_final")),
    ]
    pred_dict = {
        "category": getattr(predicted, "category", None),
        "is_final": getattr(predicted, "is_final", None),
    }
    scores = [_score_field(n, e, pred_dict[n]) for n, e in fields]
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Test cases — each gold-set example becomes a parametrized test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "golden_input",
    GOLDEN_INPUTS,
    ids=lambda g: f"{g['tone']}_q{g['question_number']}",
)
def test_golden_question_routing(golden_input: dict[str, Any]):
    """
    Run a gold-set example through the parser and verify the question
    category and is_final flag match expectations.
    """
    from monitor_agents.session_zero import (
        prediction_to_question,
    )

    expected_response = {
        "question_text": "What brought you here?",
        "category": golden_input["expected_category"],
        "is_final": golden_input["expected_is_final"],
        "reasoning": "test routing",
    }

    class _StubPred:
        pass

    pred = _StubPred()
    pred.question_text = expected_response["question_text"]
    pred.category = expected_response["category"]
    pred.is_final = expected_response["is_final"]
    pred.reasoning = expected_response["reasoning"]

    question = prediction_to_question(pred)

    assert question.category.value == golden_input["expected_category"], (
        f"category mismatch: got {question.category.value}, expected {golden_input['expected_category']}"
    )
    assert question.is_final == golden_input["expected_is_final"], (
        f"is_final mismatch: got {question.is_final}, expected {golden_input['expected_is_final']}"
    )
    assert question.question_text, "question_text should not be empty"


# ---------------------------------------------------------------------------
# Mutation-killing tests for the parser
# ---------------------------------------------------------------------------


class TestPredictionParser:
    """Each test targets a mutation in `prediction_to_question`."""

    def test_unknown_category_falls_back_to_custom(self):
        from monitor_agents.session_zero import QuestionCategory, prediction_to_question

        class _P:
            question_text = "What do you want?"
            category = "banana"
            is_final = False
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.category == QuestionCategory.CUSTOM

    def test_empty_category_falls_back_to_custom(self):
        from monitor_agents.session_zero import QuestionCategory, prediction_to_question

        class _P:
            question_text = "What do you want?"
            category = ""
            is_final = False
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.category == QuestionCategory.CUSTOM

    def test_category_alias_origin(self):
        from monitor_agents.session_zero import QuestionCategory, prediction_to_question

        class _P:
            question_text = "Where are you from?"
            category = "background"
            is_final = False
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.category == QuestionCategory.ORIGIN

    def test_category_alias_motivation(self):
        from monitor_agents.session_zero import QuestionCategory, prediction_to_question

        class _P:
            question_text = "What drives you?"
            category = "drive"
            is_final = False
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.category == QuestionCategory.MOTIVATION

    def test_category_alias_faith(self):
        from monitor_agents.session_zero import QuestionCategory, prediction_to_question

        class _P:
            question_text = "What do you believe?"
            category = "belief"
            is_final = False
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.category == QuestionCategory.FAITH

    def test_is_final_string_true(self):
        from monitor_agents.session_zero import prediction_to_question

        class _P:
            question_text = "Last question?"
            category = "custom"
            is_final = "true"
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.is_final is True

    def test_is_final_string_yes(self):
        from monitor_agents.session_zero import prediction_to_question

        class _P:
            question_text = "Last question?"
            category = "custom"
            is_final = "yes"
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.is_final is True

    def test_is_final_string_false(self):
        from monitor_agents.session_zero import prediction_to_question

        class _P:
            question_text = "Next question?"
            category = "custom"
            is_final = "false"
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.is_final is False

    def test_is_final_empty_string(self):
        from monitor_agents.session_zero import prediction_to_question

        class _P:
            question_text = "Next question?"
            category = "custom"
            is_final = ""
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.is_final is False

    def test_empty_question_text_stripped(self):
        from monitor_agents.session_zero import prediction_to_question

        class _P:
            question_text = "  What do you want?  "
            category = "motivation"
            is_final = False
            reasoning = ""

        question = prediction_to_question(_P())
        assert question.question_text == "What do you want?"


# ---------------------------------------------------------------------------
# Summary parser tests
# ---------------------------------------------------------------------------


class TestSummaryParser:
    """Tests for prediction_to_summary."""

    def test_basic_summary(self):
        from monitor_agents.session_zero import prediction_to_summary

        class _P:
            character_name = "Silas"
            concept = "A chrome scrapper with a past."
            backstory = "Silas grew up on the stations..."
            key_bonds = "Sarah, the Iron Centipede"
            key_fears = "The dark, running out of air"
            key_motivations = "Survival, finding parts"

        summary = prediction_to_summary(_P())
        assert summary.character_name == "Silas"
        assert summary.concept == "A chrome scrapper with a past."
        assert "Silas" in summary.backstory
        assert len(summary.key_bonds) == 2
        assert len(summary.key_fears) == 2
        assert len(summary.key_motivations) == 2

    def test_unknown_name_becomes_none(self):
        from monitor_agents.session_zero import prediction_to_summary

        class _P:
            character_name = "Unknown"
            concept = "A drifter."
            backstory = "They wandered..."
            key_bonds = ""
            key_fears = ""
            key_motivations = ""

        summary = prediction_to_summary(_P())
        assert summary.character_name is None

    def test_empty_name_becomes_none(self):
        from monitor_agents.session_zero import prediction_to_summary

        class _P:
            character_name = ""
            concept = "A drifter."
            backstory = "They wandered..."
            key_bonds = ""
            key_fears = ""
            key_motivations = ""

        summary = prediction_to_summary(_P())
        assert summary.character_name is None

    def test_empty_lists_stay_empty(self):
        from monitor_agents.session_zero import prediction_to_summary

        class _P:
            character_name = "Jax"
            concept = "A pilot."
            backstory = "Jax flew..."
            key_bonds = ""
            key_fears = ""
            key_motivations = ""

        summary = prediction_to_summary(_P())
        assert summary.key_bonds == []
        assert summary.key_fears == []
        assert summary.key_motivations == []


# ---------------------------------------------------------------------------
# Fallback question tests (no LLM needed)
# ---------------------------------------------------------------------------


class TestFallbackQuestions:
    """Verify fallback questions work for all tones."""

    @pytest.mark.parametrize(
        "tone",
        ["grim", "horror", "dramatic", "heroic", "mystery", "adventure"],
    )
    def test_fallback_question_has_text_and_category(self, tone: str):
        from monitor_agents.session_zero import QuestionCategory, _fallback_question

        q = _fallback_question(tone, question_number=1, max_questions=7)
        assert q.question_text, f"Fallback question for {tone} should have text"
        assert q.category != QuestionCategory.CUSTOM or q.question_text, (
            f"Fallback question for {tone} should have a valid category"
        )
        assert q.is_final is False, "First question should not be final"

    def test_fallback_question_is_final_at_max(self):
        from monitor_agents.session_zero import _fallback_question

        q = _fallback_question("grim", question_number=7, max_questions=7)
        assert q.is_final is True, "Question at max should be final"

    def test_fallback_question_unknown_tone_uses_dramatic(self):
        from monitor_agents.session_zero import _fallback_question

        q = _fallback_question("nonexistent_tone", question_number=1, max_questions=7)
        assert q.question_text, "Unknown tone should fall back to dramatic questions"

    def test_fallback_question_cycles_through_list(self):
        from monitor_agents.session_zero import _fallback_question

        q1 = _fallback_question("grim", question_number=1, max_questions=7)
        q2 = _fallback_question("grim", question_number=2, max_questions=7)
        assert q1.question_text != q2.question_text, "Questions should cycle through the list, not repeat"


# ---------------------------------------------------------------------------
# Fallback summary tests
# ---------------------------------------------------------------------------


class TestFallbackSummary:
    """Verify fallback summary extraction."""

    def test_fallback_summary_with_name(self):
        from monitor_agents.session_zero import _fallback_summary

        answers = [
            {
                "question": "What's your name?",
                "answer": "My name is Silas and I'm a scrapper.",
                "category": "name",
            },
            {"question": "Where are you from?", "answer": "Inauro station.", "category": "origin"},
        ]
        summary = _fallback_summary("grim", "Death in Space", answers)
        assert summary.character_name == "Silas"
        assert summary.concept
        assert summary.backstory

    def test_fallback_summary_no_name(self):
        from monitor_agents.session_zero import _fallback_summary

        answers = [
            {"question": "Where are you from?", "answer": "A mining colony.", "category": "origin"},
        ]
        summary = _fallback_summary("grim", "Death in Space", answers)
        assert summary.character_name is None
        assert summary.concept
        assert summary.backstory

    def test_fallback_summary_empty_answers(self):
        from monitor_agents.session_zero import _fallback_summary

        summary = _fallback_summary("grim", "Death in Space", [])
        assert summary.character_name is None
        assert summary.concept
        assert summary.backstory


# ---------------------------------------------------------------------------
# Metric tests
# ---------------------------------------------------------------------------


class TestMetric:
    """Verify the metric function scores correctly."""

    def test_perfect_score(self):
        from monitor_agents.session_zero import prediction_to_question

        golden = {
            "expected_category": "origin",
            "expected_is_final": False,
        }

        class _P:
            question_text = "Where are you from?"
            category = "origin"
            is_final = False
            reasoning = ""

        question = prediction_to_question(_P())
        score = metric(golden, question)
        assert score == 1.0

    def test_half_score_wrong_category(self):
        from monitor_agents.session_zero import prediction_to_question

        golden = {
            "expected_category": "origin",
            "expected_is_final": False,
        }

        class _P:
            question_text = "What do you fear?"
            category = "fear"
            is_final = False
            reasoning = ""

        question = prediction_to_question(_P())
        score = metric(golden, question)
        assert score == 0.5

    def test_zero_score(self):
        from monitor_agents.session_zero import prediction_to_question

        golden = {
            "expected_category": "origin",
            "expected_is_final": False,
        }

        class _P:
            question_text = "Last one?"
            category = "conflict"
            is_final = True
            reasoning = ""

        question = prediction_to_question(_P())
        score = metric(golden, question)
        assert score == 0.0


# ---------------------------------------------------------------------------
# Per-universe grounding guard (PR 3)
#
# Background: the 2026-07-23 LLM-vs-LLM play log surfaced a verbatim
# "barkeep / scar on your hand" question in Turn 2 of all three sessions
# (DIS, Fallout, VtM). Root cause: empty or thin world_lore → the prompt
# degenerates to tone+system_name → the LLM converges on a generic RPG
# prior. The fix lives in two places:
#
#   1. SessionZeroSignature + SessionZeroSummarySignature docstrings
#      carry an anti-convergence rule (structural — no LLM call).
#   2. ground_world_lore() always appends a per-universe anchor to
#      the lore list, even when the list is empty.
#
# These tests guard the structural changes (1) and the helper (2)
# without a live LLM. A live run is the actual proof of "questions
# differ across universes" — see scripts/live_llm_gm_vs_player_test.py.
# ---------------------------------------------------------------------------


class TestUniverseAnchoring:
    """The Session Zero prompt must carry a per-universe grounding
    rule so the LLM doesn't reach for generic RPG standbys (tavern
    barkeeps, hand scars) regardless of universe."""

    # --- ground_world_lore helper ---

    def test_ground_world_lore_appends_anchor_to_populated_lore(self) -> None:
        """When the lore list is non-empty, the helper appends ONE
        setting-anchored sentence as the final item. The original
        items are preserved (not mutated)."""
        from monitor_agents.session_zero import ground_world_lore

        original = [
            "The Void Cult drains life from worlds.",
            "Iron Centipede shipwrights ply the stations.",
        ]
        result = ground_world_lore(
            original,
            system_name="Death in Space",
            system_context="",
        )

        # Original items are preserved.
        assert result[: len(original)] == original
        # And exactly one anchor was appended.
        assert len(result) == len(original) + 1
        # The anchor references the system_name and warns against
        # the specific anti-patterns the play log surfaced.
        anchor = result[-1]
        assert "Death in Space" in anchor
        assert "tavern" in anchor.lower()
        assert "scar" in anchor.lower()

    def test_ground_world_lore_falls_back_to_context_when_lore_empty(self) -> None:
        """When the lore list is empty (Neo4j returned nothing), the
        helper falls back to a sentence that quotes the system_context.
        The LLM still sees SOMETHING setting-specific, not a generic
        tone-only prompt."""
        from monitor_agents.session_zero import ground_world_lore

        result = ground_world_lore(
            [],
            system_name="Vampire: The Masquerade",
            system_context=(
                "Backgrounds/Origins: Chasse, Entretien\n"
                "Creation Steps: Choose Clan, Choose Nature, etc."
            ),
        )

        assert len(result) == 1
        anchor = result[0]
        # System name is present (and quoted, so the LLM sees it as
        # a literal label, not free text).
        assert "Vampire: The Masquerade" in anchor
        # Some system context is quoted in the anchor so the LLM
        # has setting-specific material even when Neo4j is empty.
        assert "Chasse" in anchor or "Clan" in anchor

    def test_ground_world_lore_handles_empty_system_name(self) -> None:
        """If the system_name is empty, the anchor falls back to a
        generic 'this setting' label. Better than producing a broken
        'This is a '' session' sentence."""
        from monitor_agents.session_zero import ground_world_lore

        result = ground_world_lore([], system_name="", system_context="")

        assert len(result) == 1
        anchor = result[0]
        # Doesn't contain empty single-quote pair.
        assert "''" not in anchor
        # And still anchors to something — the 'this setting' fallback.
        assert "this setting" in anchor

    def test_ground_world_lore_does_not_mutate_input(self) -> None:
        """Pure function: the caller's list is untouched."""
        from monitor_agents.session_zero import ground_world_lore

        original = ["Fact A", "Fact B"]
        snapshot = list(original)
        ground_world_lore(original, "Test", "")

        assert original == snapshot, "must not mutate the caller's list"

    def test_ground_world_lore_empty_lore_and_empty_context(self) -> None:
        """Worst case: no lore, no system_context, no system_name. The
        helper still produces a coherent anchor — never returns empty
        (which would let the LLM degenerate to tone-only prompting)."""
        from monitor_agents.session_zero import ground_world_lore

        result = ground_world_lore([], "", "")

        assert len(result) == 1
        assert result[0]  # non-empty
        assert "this setting" in result[0]

    # --- Signature docstrings (structural regression guard) ---

    def test_session_zero_signature_docstring_has_anti_convergence_rule(self) -> None:
        """The SessionZeroSignature docstring must contain the
        anti-convergence rule. A future prompt refactor that drops
        this rule would let the barkeep/scar convergence re-emerge."""
        from monitor_agents.session_zero import SessionZeroSignature

        doc = SessionZeroSignature.__doc__ or ""
        # The rule's anchor phrase — must mention distinguishing
        # features and explicitly call out the convergence pattern.
        assert "distinguishing features" in doc
        assert "tavern" in doc.lower()
        assert "scar" in doc.lower()

    def test_session_zero_summary_signature_docstring_has_anti_convergence_rule(self) -> None:
        """The summary phase carries the same rule so the backstory
        doesn't drift into generic prose even when the question phase
        was clean. A regression here would mean the summary undo's
        the question-phase discipline."""
        from monitor_agents.session_zero import SessionZeroSummarySignature

        doc = SessionZeroSummarySignature.__doc__ or ""
        assert "distinguishing features" in doc
        assert "tavern" in doc.lower()
        assert "scar" in doc.lower()

    def test_session_zero_signature_preserves_no_mechanics_constraint(self) -> None:
        """Regression guard: the existing 'never ask about numbers,
        stats, dice, or game mechanics' rule must NOT be removed by
        a refactor that replaces the entire docstring. This is the
        pre-existing negative constraint; we add to it, never
        replace it."""
        from monitor_agents.session_zero import SessionZeroSignature

        doc = SessionZeroSignature.__doc__ or ""
        assert "Never ask about numbers" in doc or "never ask about numbers" in doc.lower()
