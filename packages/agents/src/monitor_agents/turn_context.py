"""
Turn Context — structured scene situation for narrative coherence.

LAYER: 2 (agents)
IMPORTS FROM: pydantic, typing

The TurnContext object represents the "ground truth" that a human GM holds in
their head during play: where the player is, what's around them, what can be
interacted with, who else is present, and what facts have been established.

This is NOT a replacement for the canon graph (Neo4j) — it is a lightweight,
per-turn snapshot that the narrator reads to ground its prose in the current
scene state.  It prevents the setting drift, name confusion, and spatial
amnesia documented in tests/e2e/logs/long_form_22turn.md.

Lifecycle:
  1. Built at the start of each turn by ``build_turn_context`` (scene_loop node)
  2. Read by the narrator as part of the context dict
  3. Updated after narration by ``extract_facts`` (established_facts) and
     ``check_consistency`` (consistency_violations)
  4. Carried in SceneState.turn_context between turns
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TurnContext(BaseModel):
    """Structured representation of the current scene situation.

    Every field is designed to answer a question the narrator would otherwise
    have to guess at:
    - ``genre`` / ``setting_summary`` → "What world are we in?"
    - ``location_name`` / ``location_description`` → "Where am I?"
    - ``player_position`` → "Where exactly am I standing?"
    - ``nearby_objects`` / ``interactables`` → "What can I see and touch?"
    - ``exits`` → "Where can I go from here?"
    - ``npcs_present`` → "Who else is here?"
    - ``character_name`` / ``character_role`` → "Who am I?"
    - ``character_stats`` / ``active_conditions`` / ``inventory_notable`` → "What can I do?"
    - ``established_facts`` → "What do we know for sure?"
    - ``recent_summary`` → "What just happened?"
    - ``pending_roll`` → "Am I waiting on a dice roll?"
    """

    # ── Setting Anchor ──
    genre: str = ""
    setting_summary: str = ""
    tone: str = "dramatic"

    # ── Scene Situation ──
    location_name: str = ""
    location_description: str = ""
    scene_goal: str = ""

    # ── Spatial Awareness ──
    player_position: str = ""
    nearby_objects: list[str] = Field(default_factory=list)
    interactables: list[dict[str, Any]] = Field(default_factory=list)
    exits: list[str] = Field(default_factory=list)

    # ── NPCs Present ──
    npcs_present: list[dict[str, Any]] = Field(default_factory=list)

    # ── Character State ──
    character_name: str = ""
    character_role: str = ""
    character_stats: dict[str, int] = Field(default_factory=dict)
    active_conditions: list[str] = Field(default_factory=list)
    inventory_notable: list[str] = Field(default_factory=list)

    # ── Narrative Memory ──
    established_facts: list[str] = Field(default_factory=list)
    recent_summary: str = ""
    pending_roll: dict[str, Any] | None = None

    def to_narrator_prompt(self) -> str:
        """Format as a compact text block for injection into the narrator prompt.

        This is used as a fallback when the narrator DSPy signature doesn't have
        a dedicated turn_context field — it can be appended to profile_context.
        """
        lines: list[str] = []

        if self.genre or self.setting_summary:
            parts = []
            if self.genre:
                parts.append(f"GENRE: {self.genre.upper()}")
            if self.setting_summary:
                parts.append(f"SETTING: {self.setting_summary}")
            lines.append(" | ".join(parts))

        if self.location_name:
            loc_parts = [f"LOCATION: {self.location_name}"]
            if self.player_position:
                loc_parts.append(f"POSITION: {self.player_position}")
            lines.append(" | ".join(loc_parts))
        if self.location_description:
            lines.append(f"  {self.location_description}")

        if self.nearby_objects:
            lines.append(f"NEARBY: {', '.join(self.nearby_objects)}")
        if self.interactables:
            interact_strs = [f"{i.get('name', '?')} ({i.get('state', '?')})" for i in self.interactables]
            lines.append(f"INTERACTABLES: {', '.join(interact_strs)}")
        if self.exits:
            lines.append(f"EXITS: {', '.join(self.exits)}")

        if self.npcs_present:
            npc_strs = [f"{n.get('name', '?')} ({n.get('disposition', '?')})" for n in self.npcs_present]
            lines.append(f"NPCS PRESENT: {', '.join(npc_strs)}")

        if self.character_name:
            char_parts = [f"CHARACTER: {self.character_name}"]
            if self.character_role:
                char_parts.append(f"ROLE: {self.character_role}")
            lines.append(" | ".join(char_parts))
        if self.active_conditions:
            lines.append(f"CONDITIONS: {', '.join(self.active_conditions)}")
        if self.inventory_notable:
            lines.append(f"NOTABLE INVENTORY: {', '.join(self.inventory_notable)}")

        if self.established_facts:
            lines.append("ESTABLISHED FACTS:")
            for fact in self.established_facts:
                lines.append(f"  - {fact}")

        if self.recent_summary:
            lines.append(f"RECENT: {self.recent_summary}")

        if self.pending_roll:
            pr = self.pending_roll
            lines.append(
                f"PENDING ROLL: {pr.get('stat', '?')} DC {pr.get('dc', '?')} (action: {pr.get('action', '?')})"
            )

        return "\n".join(lines) if lines else ""
