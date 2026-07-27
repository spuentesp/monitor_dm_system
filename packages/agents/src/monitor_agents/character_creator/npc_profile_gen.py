"""
DSPy Signature + Module for generating a rich NPCProfile from a light card.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_agents, monitor_data schemas

Turns a character.ai / SillyTavern-style "card" (name + free-text description +
personality notes) into the structured MONITOR psychological backbone:
traits, values, fears, desires, speech style, catchphrases, and behavioral
triggers. This is what lets an imported light card be *expanded* into a true
MONITOR-backed character that NPCVoice can drive with memory and deltas.

Parsing mirrors prompts/memory_extraction.py: tolerate prose-wrapped JSON and
fall back to a neutral-but-valid profile so character expansion never hard-fails.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for

logger = logging.getLogger(__name__)


# =============================================================================
# SIGNATURE
# =============================================================================


class NPCProfileGenSignature(dspy.Signature):  # type: ignore[misc]
    """
    Expand a character card into a structured psychological profile.

    You are a character designer. Given a character's name and free-text
    description / personality notes, infer a consistent psychological profile.
    Stay faithful to the source text — do not invent a different character.
    Keep every field grounded in what the card implies.
    """

    name: str = dspy.InputField(desc="Character's name")
    description: str = dspy.InputField(desc="Free-text description / backstory of the character")
    personality: str = dspy.InputField(desc="Personality notes (may be empty)")
    gm_notes: str = dspy.InputField(desc="Author/GM notes — hidden intent, secrets (may be empty)")

    profile_json: str = dspy.OutputField(
        desc=(
            "A single JSON object (no prose) with keys: "
            "'traits' (object mapping 4-6 trait names to floats -1.0..1.0), "
            "'values' (array of short strings), "
            "'fears' (array of short strings), "
            "'desires' (array of short strings), "
            "'speech_style' (one short string), "
            "'catchphrases' (array of 0-3 short strings), "
            "'current_emotional_state' (one short word/phrase), "
            "'triggers' (array of objects each with "
            "'condition', 'reaction', 'intensity' (0.0..1.0), 'is_hidden' (bool))."
        )
    )


# =============================================================================
# MODULE
# =============================================================================


def _clamp(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return round(max(lo, min(hi, float(value))), 3)
    except (TypeError, ValueError):
        return default


def _neutral_profile(name: str) -> dict[str, Any]:
    """A valid, bland profile used when generation/parsing fails."""
    return {
        "traits": {"openness": 0.0, "warmth": 0.0, "confidence": 0.0},
        "values": [],
        "fears": [],
        "desires": [],
        "speech_style": "",
        "catchphrases": [],
        "current_emotional_state": "neutral",
        "triggers": [],
    }


def _coerce_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize an LLM-produced profile dict into NPCProfileCreate-compatible fields."""
    traits_raw = raw.get("traits") or {}
    traits: dict[str, float] = {}
    if isinstance(traits_raw, dict):
        for key, val in list(traits_raw.items())[:8]:
            traits[str(key)] = _clamp(val, -1.0, 1.0, 0.0)

    def _str_list(key: str, cap: int) -> list[str]:
        items = raw.get(key) or []
        if not isinstance(items, list):
            return []
        return [str(x).strip() for x in items if str(x).strip()][:cap]

    triggers: list[dict[str, Any]] = []
    for t in (raw.get("triggers") or [])[:6]:
        if not isinstance(t, dict):
            continue
        condition = str(t.get("condition", "")).strip()
        reaction = str(t.get("reaction", "")).strip()
        if not condition or not reaction:
            continue
        triggers.append(
            {
                "condition": condition[:500],
                "reaction": reaction[:500],
                "intensity": _clamp(t.get("intensity", 0.7), 0.0, 1.0, 0.7),
                "is_hidden": bool(t.get("is_hidden", True)),
            }
        )

    return {
        "traits": traits,
        "values": _str_list("values", 6),
        "fears": _str_list("fears", 6),
        "desires": _str_list("desires", 6),
        "speech_style": (str(raw.get("speech_style", "")).strip() or None),
        "catchphrases": _str_list("catchphrases", 3),
        "current_emotional_state": (str(raw.get("current_emotional_state", "")).strip() or "neutral"),
        "triggers": triggers,
    }


class NPCProfileGenerator(dspy.Module):  # type: ignore[misc]
    """
    ChainOfThought generator — reasons about character psychology before
    emitting the structured profile. Run under ModelRole.STANDARD.
    """

    def __init__(self) -> None:
        super().__init__()
        self.generate = dspy.ChainOfThought(NPCProfileGenSignature)

    def forward(
        self,
        name: str,
        description: str = "",
        personality: str = "",
        gm_notes: str = "",
        role: ModelRole | None = None,
    ) -> dict[str, Any]:
        with dspy_context_for("npc_profile_gen", role or ModelRole.STANDARD):
            prediction = self.generate(
                name=name,
                description=description or "",
                personality=personality or "",
                gm_notes=gm_notes or "",
            )

        raw_text = prediction.profile_json or ""
        try:
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            # Some models prepend prose — grab the outermost JSON object.
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if start != -1 and end != -1 and end > start:
                raw_text = raw_text[start : end + 1]
            parsed = json.loads(raw_text)
            if not isinstance(parsed, dict):
                raise ValueError("profile_json was not a JSON object")
            return _coerce_profile(parsed)
        except (json.JSONDecodeError, IndexError, ValueError) as exc:
            logger.warning("NPCProfileGenerator parse failed (%s); using neutral profile", exc)
            return _neutral_profile(name)
