"""Tests for monitor_data.llm.image_policy (Task 10, Layer 1).

The policy module is a pure function. It decides whether a candidate prompt
should be allowed to reach the provider, based on:

- ``moderation_mode`` — "provider_default" passes everything through;
  "lines_and_veils" blocks prompts that directly violate an active campaign
  line or veil.
- The SceneState's ``agreements_lines`` (hard "no" — must never appear on
  paper) and ``agreements_veils`` (fade-to-black — must never be depicted
  on screen).

Lines are checked directly against the prompt. Veils are checked against
prompt evidence of the veiled act (the same set of phrases the resolver
uses when warning about a veil in the per-turn guardrails). An empty
agreements list means the campaign has declared no restrictions: the
policy must NOT invent any — Light RP with no agreements uses the provider
policy verbatim.

The check is intentionally cheap, deterministic, and provider-agnostic:
the provider's own safety filter still applies on top of whatever
MONITOR does here.
"""

from __future__ import annotations

import pytest
from monitor_data.llm.image_policy import (
    ImageModerationMode,
    ImagePolicyDecision,
    check_image_policy,
)


def test_provider_default_mode_passes_line_violation_through() -> None:
    """provider_default does not block — the provider's safety rules apply."""
    decision = check_image_policy(
        prompt="A clear, violent murder scene in graphic detail.",
        mode=ImageModerationMode.PROVIDER_DEFAULT,
        agreements_lines=("no graphic violence",),
        agreements_veils=(),
    )
    assert decision.allowed is True
    assert decision.reason == "provider_default"
    assert decision.violated_agreement is None


def test_provider_default_mode_passes_even_with_no_agreements() -> None:
    """Light RP with no agreements => provider policy only, no inventions."""
    decision = check_image_policy(
        prompt="A cozy scene in a tavern.",
        mode=ImageModerationMode.PROVIDER_DEFAULT,
        agreements_lines=(),
        agreements_veils=(),
    )
    assert decision.allowed is True
    assert decision.reason == "provider_default"
    assert decision.violated_agreement is None


def test_lines_and_veils_blocks_when_prompt_contains_line_phrase() -> None:
    """A line is a "must never appear on paper" — the prompt must not contain it."""
    decision = check_image_policy(
        prompt="A tavern brawl that ends with graphic dismemberment.",
        mode=ImageModerationMode.LINES_AND_VEILS,
        agreements_lines=("dismemberment",),
        agreements_veils=(),
    )
    assert decision.allowed is False
    assert decision.reason == "lines_and_veils"
    assert decision.violated_agreement == "dismemberment"


def test_lines_and_veils_blocks_when_prompt_contains_veil_phrase() -> None:
    """A veil is "fade-to-black" — the prompt must not depict the veiled act."""
    decision = check_image_policy(
        prompt="An explicit depiction of torture on the prisoner.",
        mode=ImageModerationMode.LINES_AND_VEILS,
        agreements_lines=(),
        agreements_veils=("torture",),
    )
    assert decision.allowed is False
    assert decision.reason == "lines_and_veils"
    assert decision.violated_agreement == "torture"


def test_lines_and_veils_passes_when_no_agreement_matches() -> None:
    """Clean prompts pass even when agreements are configured."""
    decision = check_image_policy(
        prompt="A warm sunset over the rooftops.",
        mode=ImageModerationMode.LINES_AND_VEILS,
        agreements_lines=("dismemberment",),
        agreements_veils=("torture",),
    )
    assert decision.allowed is True
    assert decision.reason == "lines_and_veils"
    assert decision.violated_agreement is None


def test_lines_and_veils_with_empty_agreements_uses_provider_policy() -> None:
    """Light RP with no agreements never invents restrictions."""
    decision = check_image_policy(
        prompt="A scene that mentions anything at all.",
        mode=ImageModerationMode.LINES_AND_VEILS,
        agreements_lines=(),
        agreements_veils=(),
    )
    assert decision.allowed is True
    assert decision.reason == "lines_and_veils_no_agreements"
    assert decision.violated_agreement is None


def test_lines_and_veils_match_is_case_insensitive() -> None:
    """Agreement phrases are matched case-insensitively against the prompt."""
    decision = check_image_policy(
        prompt="An explicit DISMEMBERMENT of the enemy.",
        mode=ImageModerationMode.LINES_AND_VEILS,
        agreements_lines=("dismemberment",),
        agreements_veils=(),
    )
    assert decision.allowed is False
    assert decision.violated_agreement == "dismemberment"


def test_lines_and_veils_match_is_substring() -> None:
    """A line phrase embedded in a longer prompt is still a violation."""
    decision = check_image_policy(
        prompt="A quiet forest after a small dismemberment attempt.",
        mode=ImageModerationMode.LINES_AND_VEILS,
        agreements_lines=("dismemberment",),
        agreements_veils=(),
    )
    assert decision.allowed is False
    assert decision.violated_agreement == "dismemberment"


def test_lines_and_veils_priority_line_wins_over_veil() -> None:
    """When both fire, the first match (line) is reported for clarity."""
    decision = check_image_policy(
        prompt="A scene of torture ending in dismemberment.",
        mode=ImageModerationMode.LINES_AND_VEILS,
        agreements_lines=("dismemberment",),
        agreements_veils=("torture",),
    )
    assert decision.allowed is False
    # Lines are checked first; the violating phrase we report is the one
    # that the caller can surface ("dismemberment is a line").
    assert decision.violated_agreement == "dismemberment"


def test_provider_default_does_not_consider_agreements_at_all() -> None:
    """provider_default literally ignores agreements — provider-only filter."""
    decision = check_image_policy(
        prompt="A scene that mentions dismemberment and torture.",
        mode=ImageModerationMode.PROVIDER_DEFAULT,
        agreements_lines=("dismemberment",),
        agreements_veils=("torture",),
    )
    assert decision.allowed is True
    assert decision.reason == "provider_default"


def test_lines_and_veils_ignores_blank_agreement_phrases() -> None:
    """Empty/whitespace-only agreement entries do not cause false positives."""
    decision = check_image_policy(
        prompt="A prompt with no restricted content.",
        mode=ImageModerationMode.LINES_AND_VEILS,
        agreements_lines=("", "   "),
        agreements_veils=(),
    )
    assert decision.allowed is True
    assert decision.violated_agreement is None


@pytest.mark.parametrize(
    "mode",
    [
        ImageModerationMode.PROVIDER_DEFAULT,
        ImageModerationMode.LINES_AND_VEILS,
    ],
)
def test_returns_decision_dataclass(mode: ImageModerationMode) -> None:
    """The result is always an ImagePolicyDecision (typed, not a tuple)."""
    decision = check_image_policy(
        prompt="A cozy scene.",
        mode=mode,
        agreements_lines=(),
        agreements_veils=(),
    )
    assert isinstance(decision, ImagePolicyDecision)
    assert isinstance(decision.allowed, bool)
    assert isinstance(decision.reason, str)
    assert decision.violated_agreement is None or isinstance(decision.violated_agreement, str)
