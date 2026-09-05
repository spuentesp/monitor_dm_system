"""
Modes router — system operation mode management.

Exposes the three MONITOR modes (World Architect, Autonomous GM, GM Assistant)
plus their per-session context configuration.
"""

from __future__ import annotations

from fastapi import APIRouter

from .modes_schemas import ActiveMode, ModeConfig, SetActiveMode

router = APIRouter()

# ---------------------------------------------------------------------------
# Static mode definitions
# ---------------------------------------------------------------------------

MODES = [
    {
        "id": "world_architect",
        "label": "World Architect",
        "tagline": "Build the Omniverse",
        "description": (
            "Define worlds, universes, and multiverses. Ingest lore books, "
            "session summaries, and player notes. Maintain facts, factions, "
            "geography, and the rules of reality. Fork timelines."
        ),
        "capabilities": [
            "Ingest and extract structured lore from documents",
            "Manage entities, factions, locations, and events",
            "Query and cross-reference canonical facts",
            "Fork alternate timelines and compare canons",
            "Define world axioms (magic, physics, tech level)",
        ],
        "color": "purple",
        "icon": "Globe",
    },
    {
        "id": "autonomous_gm",
        "label": "Autonomous GM",
        "tagline": "Solo Play — Full Narrative Control",
        "description": (
            "The system acts as your Game Master: narrating scenes, adjudicating "
            "rules, voicing NPCs with memory, and evolving the world based on "
            "your choices — all without a human GM at the table."
        ),
        "capabilities": [
            "Scene-by-scene GM narration with full context",
            "Rules adjudication for any RPG system",
            "Persistent NPC memory and personality",
            "Dynamic world-state evolution from player choices",
            "Canon commitment — decisions persist across sessions",
        ],
        "color": "cyan",
        "icon": "Bot",
    },
    {
        "id": "gm_assistant",
        "label": "GM Assistant",
        "tagline": "Co-Pilot for Human GMs",
        "description": (
            "Support human-led campaigns by recording what happens, tracking "
            "consequences, surfacing relevant lore, and suggesting what comes "
            "next — without replacing the GM's creative control."
        ),
        "capabilities": [
            "Live session recording and summarisation",
            "Automatic entity extraction from session notes",
            "Lore recall: 'What did we establish about X?'",
            "Consequence tracking and continuity alerts",
            "Plot thread and NPC relationship mapping",
        ],
        "color": "emerald",
        "icon": "Headphones",
    },
]

# In-memory active mode (replace with MongoDB persistence)
# reason: bare-typed module-level mutable singleton — entries are str | None | list; narrow to a typed ActiveMode TypedDict in a follow-up
_ACTIVE: dict = {  # type: ignore
    "mode_id": "autonomous_gm",
    "world_id": None,
    "character_id": None,
    "tone": "dramatic",
    "context_depth": "standard",
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ModeConfig])
async def list_modes() -> list[ModeConfig]:
    return [ModeConfig(**m) for m in MODES]


@router.get("/active", response_model=ActiveMode)
async def get_active_mode() -> ActiveMode:
    return ActiveMode(**_ACTIVE)


@router.post("/active", response_model=ActiveMode)
async def set_active_mode(body: SetActiveMode) -> ActiveMode:
    _ACTIVE.update(body.model_dump())
    return ActiveMode(**_ACTIVE)
