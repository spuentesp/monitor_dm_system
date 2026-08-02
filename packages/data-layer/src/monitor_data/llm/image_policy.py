"""Image moderation policy (Task 10, Layer 1).

The policy runs *before* the image provider is invoked. It is the only
client-side gate MONITOR enforces; the provider's own safety filter still
applies on top of whatever we decide here.

Two modes, both surfaced through :class:`ImageModerationMode`:

- ``provider_default`` — pass everything through. Treats the provider as
  the authoritative filter. This is the right default for Light RP where
  the table has no agreements.

- ``lines_and_veils`` — block prompts that directly violate an active
  campaign line or veil. Lines are "must never appear on paper" topics;
  veils are "fade-to-black" topics. The list of agreements is supplied
  by the caller (the same SceneState that the resolver uses for
  per-turn guardrails).

Lines and veils are matched as case-insensitive substrings against the
candidate prompt. The match is deliberately cheap and deterministic — we
do not parse intent, we do not classify the prompt, and we do not ask the
LLM. The provider API performs the deeper safety classification.

The function never invents restrictions. When ``lines_and_veils`` is
configured but the caller passes empty agreements, the policy reports
"no agreements declared" and lets the prompt through — the brief is
explicit that Light RP must not silently add rules the table did not opt
into.

LAYER: 1 (data-layer)
IMPORTS FROM: stdlib only
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable


class ImageModerationMode(StrEnum):
    """Which moderation policy the image router applies before the provider."""

    PROVIDER_DEFAULT = "provider_default"
    LINES_AND_VEILS = "lines_and_veils"


@dataclass(frozen=True)
class ImagePolicyDecision:
    """Result of an image-policy check.

    ``allowed`` is the actionable bit. ``reason`` is a stable string the
    router can log and surface to the UI; ``violated_agreement`` is the
    matched phrase when the decision is a block, otherwise ``None``.
    """

    allowed: bool
    reason: str
    violated_agreement: str | None = None


def _normalize_agreement(phrase: str) -> str:
    return phrase.strip().lower()


def _normalised_agreements(agreements: Iterable[str]) -> list[str]:
    return [normalised for raw in agreements if (normalised := _normalize_agreement(raw))]


def _first_violation(prompt: str, phrases: list[str]) -> str | None:
    # Substring match is intentional: the brief specifies case-insensitive
    # substring matching for the lines-and-veils check. It does produce
    # false positives (e.g. "blood" matches "bloodstream"), but that is
    # the chosen behavior — adding word boundaries here would silently
    # let through phrases the table explicitly opted out of. If a future
    # review wants stricter matching, the decision belongs in the
    # ImageGenerationSettings schema (e.g. a per-agreement match_mode
    # field), not in a quiet tightening of the matcher.
    haystack = prompt.lower()
    for phrase in phrases:
        if phrase and phrase in haystack:
            return phrase
    return None


def check_image_policy(
    *,
    prompt: str,
    mode: ImageModerationMode,
    agreements_lines: Iterable[str],
    agreements_veils: Iterable[str],
) -> ImagePolicyDecision:
    """Decide whether ``prompt`` may be sent to the image provider.

    Args:
        prompt: Final positive prompt that would be sent to the provider.
        mode: Which moderation policy to apply.
        agreements_lines: "Lines" — things that must never appear on paper.
        agreements_veils: "Veils" — things that must never be depicted.

    Returns:
        An :class:`ImagePolicyDecision` whose ``allowed`` bit is the only
        contract the router depends on. ``reason`` is human-readable.
    """
    if mode is ImageModerationMode.PROVIDER_DEFAULT:
        return ImagePolicyDecision(allowed=True, reason="provider_default")

    # mode == LINES_AND_VEILS
    lines = _normalised_agreements(agreements_lines)
    veils = _normalised_agreements(agreements_veils)
    if not lines and not veils:
        # Light RP with no agreements: do not invent restrictions.
        return ImagePolicyDecision(
            allowed=True,
            reason="lines_and_veils_no_agreements",
        )

    violation = _first_violation(prompt, lines)
    if violation is not None:
        return ImagePolicyDecision(
            allowed=False,
            reason="lines_and_veils",
            violated_agreement=violation,
        )
    violation = _first_violation(prompt, veils)
    if violation is not None:
        return ImagePolicyDecision(
            allowed=False,
            reason="lines_and_veils",
            violated_agreement=violation,
        )
    return ImagePolicyDecision(allowed=True, reason="lines_and_veils")


__all__ = [
    "ImageModerationMode",
    "ImagePolicyDecision",
    "check_image_policy",
]
