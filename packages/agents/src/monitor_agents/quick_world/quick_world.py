"""
DSPy signature + module for one-shot "quick world" generation.

Turns a one-line seed ("a rain-soaked noir city where memories are currency")
into a small, immediately playable world: a premise, an axiom, a handful of
entities with wants, a few lore facts, an opening scene, and a suggested PC.

This is the Emochi/SillyTavern-style on-ramp — most roleplay worlds start from
a vibe, not a 300-page rulebook. The heavy lorebook-ingestion path lives in the
Indexer/Analyzer pipeline; this is deliberately a single structured LLM call.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_agents.dspy_runtime
"""

from __future__ import annotations

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for


class QuickWorldSignature(dspy.Signature):  # type: ignore[misc]
    """
    You are a tabletop RPG world designer. From a short seed idea, design a
    compact, vivid, *immediately playable* setting — the kind a solo player
    could drop into within a minute.

    Design rules:
    - Keep it small and sharp: one striking premise, not an encyclopedia.
    - Every entity must have a clear WANT that can drive a scene — an ally with
      an agenda, an antagonist with a plan, a place with a pull, optionally a
      faction with leverage.
    - The axiom is one load-bearing truth about how this world works (magic,
      tech, society, the dead — whatever the seed implies).
    - Lore facts are concrete and specific (events, relationships, secrets),
      never generic flavor.
    - The opening scene drops the PC into a charged situation with an immediate
      hook — a question, a threat, or a choice. Address the player as "you".
    - Match the requested genre and tone precisely. Honor the seed's specifics.
    - Output strict JSON for the list fields; no markdown, no commentary.
    """

    seed: str = dspy.InputField(desc="The player's seed idea for the world (one or two sentences).")
    genre: str = dspy.InputField(
        desc="Genre hint, e.g. 'dark fantasy', 'cyberpunk noir', 'cosmic horror'. May be empty."
    )
    tone: str = dspy.InputField(desc="Narrative tone, e.g. 'grim', 'heroic', 'mysterious'. May be empty.")

    world_name: str = dspy.OutputField(desc="A short, evocative name for the world/setting.")
    world_description: str = dspy.OutputField(desc="2-4 sentences establishing the setting's premise and feel.")
    axiom: str = dspy.OutputField(desc="One load-bearing world truth (a single sentence).")
    entities_json: str = dspy.OutputField(
        desc=(
            "JSON array of 3-4 entities. Each object: "
            '{"name": str, "type": "character"|"location"|"faction"|"object", '
            '"description": str (1-2 sentences), "want": str (what it pursues), '
            '"tags": [str, ...]}. Include at least one ally character, one '
            "antagonist character, and one location."
        )
    )
    lore_json: str = dspy.OutputField(
        desc="JSON array of 2-3 concrete lore-fact strings (events, secrets, relationships)."
    )
    opening_scene: str = dspy.OutputField(
        desc="2-3 sentences dropping the PC into an opening situation with an immediate hook. Second person."
    )
    pc_concept: str = dspy.OutputField(
        desc="A one-line suggested player-character concept that fits this world (name + hook)."
    )


class QuickWorldModule(dspy.Module):  # type: ignore[misc]
    """One-shot seed → playable-world blueprint."""

    def __init__(self) -> None:
        super().__init__()
        self.generate = dspy.ChainOfThought(QuickWorldSignature)

    def forward(self, seed: str, genre: str = "", tone: str = "") -> dspy.Prediction:
        # STANDARD role: this is a creative generation, worth a capable model.
        with dspy_context_for("quick_world", ModelRole.STANDARD):
            return self.generate(seed=seed, genre=genre, tone=tone)
