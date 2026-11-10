"""DSPy signature + module for composing world-seed start options.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_agents.dspy_runtime.

This is deliberately NOT a second world generator: it composes 2-4 start
options out of material the universe already holds (or that the reused
QuickWorld signature synthesized for sparse universes). Every option must
be anchored to a named location and named NPCs from the material.
"""

from __future__ import annotations

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for


class StartOptionsSignature(dspy.Signature):  # type: ignore[misc]
    """
    You are a tabletop RPG GM preparing concrete ways a story could begin in
    an established setting.

    From the world material below, design 2-4 DISTINCT start options. Each
    option is one charged opening situation the player could step into.

    Rules:
    - Ground every option in the material: use real location names and real
      character names from it wherever they exist. Never rename them. Only
      invent names when the material has none (the output is then marked as
      generated).
    - Each option: one location where the scene happens, 2-4 named NPCs who
      are present (with what each wants), an immediate hook (a question,
      threat, or choice with something at stake), and a suggested role for
      the player character.
    - Each option opens 2-3 plot threads (unresolved promises, threats, or
      mysteries) that reference the option's people and place.
    - Options must differ from one another in place, people, and stakes —
      not just wording.
    - Match the setting's tone. Concrete over epic.
    - Output strict JSON for options_json; no markdown, no commentary.
    """

    world_material: str = dspy.InputField(
        desc="Grounding digest: locations, characters with wants, factions, lore facts, agendas, open plot threads, travel connections."
    )
    system_name: str = dspy.InputField(desc="Setting / system name. May be empty.")
    tone: str = dspy.InputField(desc="Narrative tone, e.g. 'grim', 'heroic'. May be empty.")
    min_options: int = dspy.InputField(desc="Minimum number of start options to produce (2).")
    max_options: int = dspy.InputField(desc="Maximum number of start options to produce (4).")

    options_json: str = dspy.OutputField(
        desc=(
            "JSON array of 2-4 objects. Each object: "
            '{"title": str (short option name), "summary": str (one sentence), '
            '"location": str, "location_description": str, '
            '"npcs": [{"name": str, "description": str, "want": str}, ...] (2-4), '
            '"hook": str, "player_role": str, '
            '"threads": [{"title": str, "description": str, "category": "promise"|"threat"|"mystery"|"consequence"|"relationship"|"world_event", "urgency": "low"|"medium"|"high"|"critical"}, ...] (2-3)}'
        )
    )


class StartOptionsModule(dspy.Module):  # type: ignore[misc]
    """Compose start options from world material."""

    def __init__(self) -> None:
        super().__init__()
        self.predict = dspy.ChainOfThought(StartOptionsSignature)

    def forward(
        self,
        *,
        world_material: str,
        system_name: str,
        tone: str,
        min_options: int,
        max_options: int,
    ) -> dspy.Prediction:
        # STANDARD role: creative composition worth a capable model.
        with dspy_context_for("world_seed", ModelRole.STANDARD):
            return self.predict(
                world_material=world_material,
                system_name=system_name,
                tone=tone,
                min_options=min_options,
                max_options=max_options,
            )
