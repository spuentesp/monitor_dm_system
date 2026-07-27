"""Shared scenario fixtures for the full-loop harness.

DRY: both ``scripts/e2e_full_loop.py`` and ``tests/e2e/test_e2e_full_loop.py``
import from here so a scenario change lands in both places at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioTurn:
    """One scripted turn: what the player says + an intent label."""

    player_action: str
    intent: str


@dataclass
class Scenario:
    name: str
    world_id: str
    seed: str
    character_concept: str
    arc: list[ScenarioTurn] = field(default_factory=list)
    scripted_opens: list[ScenarioTurn] = field(default_factory=list)
    character_spec: dict[str, Any] = field(default_factory=dict)


VTM_SCENARIOS: list[Scenario] = [
    Scenario(
        name="vtm_embrace",
        world_id="vtm-demo",
        seed=(
            "A nocturnal corner of Los Angeles, 1999. The player was Embraced "
            "last night by an unknown sire, and the sun has just set."
        ),
        character_concept="A new Kindred, freshly Embraced, asking about their sire",
        scripted_opens=[
            ScenarioTurn(
                "I sit up in the alley where I woke. The world feels wrong — everything is too bright. What's happening to me?",
                "establish baseline",
            ),
            ScenarioTurn(
                "The Prince mentions my sire by name. I ask him to repeat it.",
                "probe authority",
            ),
        ],
        character_spec={"name": "Newly Embraced", "concept": "Curious Neonate"},
    ),
    Scenario(
        name="vtm_primogen",
        world_id="vtm-demo",
        seed=(
            "The player has been a Ventrue for six months, now invited to a "
            "Primogen meeting as an observer. The Prince is announcing new "
            "hunting grounds."
        ),
        character_concept="A young Ventrue attending their first Primogen council",
        scripted_opens=[
            ScenarioTurn(
                "I take my seat at the back of the chamber and look around at the other Primogen.",
                "establish baseline",
            ),
            ScenarioTurn(
                "The Prince mentions my sire by name. I ask him to repeat it.",
                "probe authority",
            ),
        ],
        character_spec={"name": "Young Ventrue", "concept": "Political Observer"},
    ),
]


DIS_SCENARIOS: list[Scenario] = [
    Scenario(
        name="dis_salvage",
        world_id="dis-demo",
        seed=(
            "Aboard the dead mining frigate *Ozymandias*. The player is a "
            "desperate scrapper in a deteriorating suit, oxygen ticking down, "
            "with a glowing fusion battery to extract."
        ),
        character_concept="Rook, a Chrome scrapper on the Ozymandias",
        scripted_opens=[
            ScenarioTurn(
                "I mute my comms and unholster my rivet gun. I kick off the bulkhead toward the battery.",
                "navigate zero-G",
            ),
            ScenarioTurn(
                "My magnetic boot clips debris. I spin, slam into a bulkhead. My suit integrity alarm starts blaring.",
                "react to failure",
            ),
        ],
        character_spec={
            "name": "Rook 'Rust' Vane",
            "concept": "A hard-luck salvager and void-scarred mechanic.",
        },
    ),
    Scenario(
        name="dis_void_whisper",
        world_id="dis-demo",
        seed=(
            "The player's comms crackle. Someone is whispering from outside "
            "the airlock, but there is no one outside the airlock."
        ),
        character_concept="Echo, a Savvy salvager who listens before touching",
        scripted_opens=[
            ScenarioTurn(
                "I press my helmet against the airlock and listen.",
                "tune in",
            ),
        ],
        character_spec={"name": "Echo", "concept": "Savvy salvager"},
    ),
]


SCENARIOS: dict[str, Scenario] = {s.name: s for s in VTM_SCENARIOS + DIS_SCENARIOS}


# Seeded game-system IDs — verified by memory entry 2026-07-21.
V5_SYSTEM_ID = "a227676a-edab-4a43-80d9-8f76b74ff289"
DIS_SYSTEM_ID = "04dba354-5211-44a2-8bdd-20fae64c016f"

SYSTEM_ID_BY_WORLD: dict[str, str] = {
    "vtm-demo": V5_SYSTEM_ID,
    "dis-demo": DIS_SYSTEM_ID,
}


def scripted_pairs(scenario: Scenario) -> list[tuple[str, str]]:
    """Return the scripted-opens as (action, intent) pairs."""
    return [(t.player_action, t.intent) for t in scenario.scripted_opens]
