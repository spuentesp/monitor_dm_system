"""Typed models for the world-seed starting situation (Phase 2 guided start).

LAYER: 2 (agents)
IMPORTS FROM: pydantic only.

A ``WorldSeedResult`` is the structured answer to "how could this story
begin?": 2-4 concrete start options grounded in what the universe holds,
each with a location, named NPCs present, a hook, and a suggested role for
the player. The same shapes feed the interview question, the UI chips, and
the materialization step that turns the chosen option into canon state.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class StartOptionNPC(BaseModel):
    """One named NPC present at the start of an option."""

    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    want: str = Field(default="", max_length=300, description="What this NPC pursues — becomes their agenda.")


class StartOptionThread(BaseModel):
    """One plot thread the chosen start opens."""

    title: str = Field(max_length=300)
    description: str = Field(default="", max_length=2000)
    category: str = Field(default="mystery", description="PlotThreadCategory value.")
    urgency: str = Field(default="medium", description="PlotThreadUrgency value.")


class StartOption(BaseModel):
    """A concrete way to begin the story in this world."""

    option_id: str = Field(max_length=120, description="Stable slug, unique within the seed result.")
    title: str = Field(max_length=200, description="Short name — shown as a chip and used in the question.")
    summary: str = Field(default="", max_length=500)
    location: str = Field(max_length=200)
    location_description: str = Field(default="", max_length=1000)
    npcs: list[StartOptionNPC] = Field(default_factory=list, description="2-4 named NPCs present.")
    hook: str = Field(default="", max_length=500, description="What pulls the player in — what is at stake.")
    player_role: str = Field(default="", max_length=300, description="Suggested role for the player character.")
    threads: list[StartOptionThread] = Field(default_factory=list, description="2-3 plot threads.")
    generated: bool = Field(
        default=False,
        description="True when this option was invented (sparse universe) rather than drawn from canon.",
    )

    def chip_label(self) -> str:
        return self.title.strip() or self.location.strip() or self.option_id

    def chip_dict(self) -> dict[str, Any]:
        """Structured data for the UI (chips the way suggested actions work)."""
        return {
            "option_id": self.option_id,
            "title": self.chip_label(),
            "summary": self.summary,
            "location": self.location,
            "npc_names": [npc.name for npc in self.npcs],
            "hook": self.hook,
            "player_role": self.player_role,
            "generated": self.generated,
        }


class WorldSeedResult(BaseModel):
    """The starting-situation options for one universe."""

    universe_id: str
    options: list[StartOption] = Field(default_factory=list)
    source: Literal["canon", "generated", "mixed"] = "canon"
    material_digest: str = Field(default="", description="What grounded the options (debug/prompt echo).")

    def by_id(self, option_id: str | None) -> StartOption | None:
        if not option_id:
            return None
        for option in self.options:
            if option.option_id == option_id:
                return option
        return None

    def to_chips(self) -> list[dict[str, Any]]:
        """Structured data for the UI (chips the way suggested actions work)."""
        return [option.chip_dict() for option in self.options]


class UniverseMaterial(BaseModel):
    """What the universe holds, gathered for grounding the start options."""

    universe_id: str
    universe_name: str = ""
    description: str = ""
    genre: str | None = None
    tone: str | None = None
    system_name: str | None = None
    locations: list[dict[str, str]] = Field(default_factory=list)
    characters: list[dict[str, str]] = Field(default_factory=list)
    factions: list[dict[str, str]] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    axioms: list[str] = Field(default_factory=list)
    agendas: list[dict[str, str]] = Field(default_factory=list)
    plot_threads: list[dict[str, str]] = Field(default_factory=list)
    character_profiles: list[dict[str, str]] = Field(default_factory=list)
    topologies: list[dict[str, str]] = Field(default_factory=list)

    def grounding_count(self) -> int:
        return (
            len(self.locations)
            + len(self.characters)
            + len(self.factions)
            + len(self.facts)
            + len(self.axioms)
            + len(self.agendas)
            + len(self.plot_threads)
            + len(self.character_profiles)
            + len(self.topologies)
        )

    def is_sparse(self) -> bool:
        """A universe too thin to ground concrete start options in.

        Sparse means the seed has nothing to anchor a location and NPCs to:
        no location AND no character/faction content to stand in for one.
        """
        has_place = bool(self.locations)
        has_people = bool(self.characters) or bool(self.factions) or bool(self.character_profiles)
        if has_place and has_people:
            return False
        return self.grounding_count() < 4

    def digest(self, limit_per_section: int = 6) -> str:
        """Compact text digest for prompt grounding."""

        def _lines(items: list[dict[str, str]], keys: tuple[str, ...]) -> list[str]:
            out: list[str] = []
            for item in items[:limit_per_section]:
                parts = [str(item.get(key) or "").strip() for key in keys]
                text = " — ".join(part for part in parts if part)
                if text:
                    out.append(text)
            return out

        sections: list[str] = []
        if self.description:
            sections.append("Setting: " + self.description.strip())
        lines = _lines(self.locations, ("name", "description"))
        if lines:
            sections.append("Locations:\n" + "\n".join(f"- {line}" for line in lines))
        lines = _lines(self.characters, ("name", "description", "want"))
        if lines:
            sections.append("Characters:\n" + "\n".join(f"- {line}" for line in lines))
        lines = _lines(self.factions, ("name", "description"))
        if lines:
            sections.append("Factions:\n" + "\n".join(f"- {line}" for line in lines))
        if self.axioms:
            sections.append("World truths:\n" + "\n".join(f"- {a}" for a in self.axioms[:limit_per_section]))
        if self.facts:
            sections.append("Lore facts:\n" + "\n".join(f"- {f}" for f in self.facts[:limit_per_section]))
        lines = _lines(self.agendas, ("title", "description"))
        if lines:
            sections.append("Agendas:\n" + "\n".join(f"- {line}" for line in lines))
        lines = _lines(self.plot_threads, ("title", "description"))
        if lines:
            sections.append("Open plot threads:\n" + "\n".join(f"- {line}" for line in lines))
        lines = _lines(self.character_profiles, ("name", "summary"))
        if lines:
            sections.append("Character profiles:\n" + "\n".join(f"- {line}" for line in lines))
        lines = _lines(self.topologies, ("from_location", "to_location", "description"))
        if lines:
            sections.append("Travel connections:\n" + "\n".join(f"- {line}" for line in lines))
        return "\n\n".join(sections)
