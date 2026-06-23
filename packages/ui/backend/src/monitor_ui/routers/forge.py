"""
Forge router — high-level world-building entry points beyond raw ingestion.

Currently hosts the **quick-world** path: a one-line seed → a small, playable
universe committed as canon, optionally with a bound chat session ready to
narrate turn one. The Emochi/SillyTavern-style on-ramp to the World Forge.

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: monitor_agents (Layer 2)
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class QuickWorldRequest(BaseModel):
    """Body for POST /forge/quick-world."""

    seed: str = Field(min_length=3, max_length=2000, description="The world seed idea.")
    genre: str = Field(default="", max_length=80)
    tone: str = Field(default="", max_length=80)
    name: str | None = Field(default=None, max_length=120)
    start_playing: bool = Field(
        default=False,
        description="When true, also create a chat session bound to the new universe.",
    )


class QuickWorldResponse(BaseModel):
    """Result of a quick-world build."""

    multiverse_id: str
    universe_id: str
    world_name: str
    world_description: str
    axiom: str
    opening_scene: str
    pc_concept: str
    entities: list[dict]
    lore_facts: list[str]
    committed: int
    errors: list[str]
    session_id: str | None = None


# Curated, deterministic demo world (no LLM) — instant "try it" on-ramp.
_DEMO_NAME = "Millhaven"
_DEMO_DESCRIPTION = "A fog-bound village where people disappear after dark."
_DEMO_GENRE = "dark fantasy"
_DEMO_AXIOM = "After dusk, an unnatural mist rises in Millhaven and the missing are never found whole."
_DEMO_ENTITIES = [
    (
        "Barnaby the Innkeeper",
        "character",
        "A nervous innkeeper who locks his doors at sundown and knows more than he says.",
        "to survive the night without being noticed",
    ),
    (
        "Elder Magda",
        "character",
        "The missing village elder; her silver amulet has not been seen since she vanished.",
        "to be found — or avenged",
    ),
    (
        "Millhaven Inn",
        "location",
        "Warm light, thin walls, and the only safe beds in the village.",
        "",
    ),
    (
        "Millhaven Cemetery",
        "location",
        "Fog-bound graves at the village edge; a freshly disturbed plot lies near the crypt.",
        "",
    ),
    (
        "The Shadow Cabal",
        "faction",
        "A whispered conspiracy said to trade in stolen villagers and darker things.",
        "to harvest the village quietly, one night at a time",
    ),
]
_DEMO_LORE = [
    "Villagers have been disappearing for three nights running.",
    "Elder Magda vanished first; her body was never found.",
    "Fresh drag marks lead from the town square toward the old cemetery.",
]
# A pregen PC with a sheet so the demo exercises the mechanical layer
# (HP/resources show in the HUD), not just narrative prose (T-092).
_DEMO_PC_NAME = "The Lantern-Bearer"
_DEMO_PC_DESC = "A wandering investigator who took the last room at the Millhaven Inn — lantern in one hand, knife in the other."
# Chosen attribute *values* are per-character data and stay here. Resources
# (Health/Nerve) are *derived* from the bound game system's formulas at create
# time — never hardcoded — so they track the system (e.g. Mistlands Core
# Health = "10 + Grit_modifier" → 11 for Grit 12). See _demo_pc_properties.
_DEMO_PC_ATTRIBUTES = {"Grit": 12, "Wits": 13, "Resolve": 11}


def _demo_pc_properties(system_id: "UUID | None") -> dict:
    """Build the demo PC properties, deriving resources from the bound system.

    Attribute values are data; resources come from the game system's resource
    ``calculation`` formulas via ``GameSystemRuntime`` (no literal resource dict).
    If the system can't be loaded, the PC is created with attributes only rather
    than falling back to hardcoded resources.
    """
    props: dict = {"attributes": dict(_DEMO_PC_ATTRIBUTES)}
    if system_id is None:
        return props
    try:
        from monitor_agents.game_system import GameSystemRuntime
        from monitor_data.tools.mongodb_tools import mongodb_get_game_system

        sys_resp = mongodb_get_game_system(system_id)
        doc = sys_resp.model_dump(mode="json") if sys_resp else None
        if not doc:
            return props
        gsr = GameSystemRuntime(doc)
        stats = {name.upper(): val for name, val in _DEMO_PC_ATTRIBUTES.items()}
        derived = gsr.derive_resources(stats)
        if derived:
            props["resources"] = {
                name: {"current": val, "max": val} for name, val in derived.items()
            }
    except Exception as exc:  # noqa: BLE001 — resources are a nice-to-have, never literal
        logger.warning("Demo PC resource derivation failed: %s", exc)
    return props


def _ensure_demo_pc(universe_id: "UUID", system_id: "UUID | None" = None) -> str | None:
    """Create (or reuse) the pregen demo PC entity with a stat sheet.

    Idempotent by name so repeated demo launches don't duplicate the PC.
    Resources are derived from ``system_id``'s formulas, not hardcoded.
    """
    from monitor_data.schemas.entities import EntityCreate, EntityFilter
    from monitor_data.tools.neo4j_tools.entities import (
        neo4j_create_entity,
        neo4j_list_entities,
    )

    try:
        existing = neo4j_list_entities(
            EntityFilter(universe_id=universe_id, name=_DEMO_PC_NAME, limit=10)
        )
        rows = getattr(existing, "entities", existing) or []
        for e in rows:
            if getattr(e, "name", None) == _DEMO_PC_NAME:
                return str(e.id)
    except Exception:  # noqa: BLE001 — fall through to creation
        pass

    pc = neo4j_create_entity(
        EntityCreate(
            universe_id=universe_id,
            name=_DEMO_PC_NAME,
            entity_type="character",
            description=_DEMO_PC_DESC,
            properties=_demo_pc_properties(system_id),
        )
    )
    return str(pc.id)


class DemoWorldResponse(QuickWorldResponse):
    """Quick-world response plus whether the demo already existed."""

    reused: bool = False


@router.post("/demo-world", response_model=DemoWorldResponse)
async def demo_world(start_playing: bool = True) -> DemoWorldResponse:
    """Create (or reuse) the curated Millhaven demo world and a bound session.

    Deterministic and LLM-free so the 'Try the demo' button is instant and
    always works, even with no provider configured.
    """
    import anyio

    from monitor_agents.quick_world import QuickWorldResult

    def _ensure_demo() -> tuple[QuickWorldResult, bool]:
        from uuid import UUID

        from monitor_data.schemas.universe import (
            MultiverseCreate as DLMultiverseCreate,
            UniverseCreate as DLUniverseCreate,
            UniverseFilter,
        )
        from monitor_data.tools.neo4j_tools import (
            neo4j_create_multiverse,
            neo4j_create_universe,
            neo4j_ensure_omniverse,
            neo4j_list_universes,
        )
        from monitor_data.tools.mongodb_tools import mongodb_list_game_systems

        # Query MongoDB for "Mistlands Core" system ID
        systems_res = mongodb_list_game_systems(include_builtin=True, limit=50)
        mistlands_id = None
        for sys in getattr(systems_res, "systems", systems_res):
            if sys.name == "Mistlands Core":
                mistlands_id = sys.id
                break

        # Idempotent: reuse an existing Millhaven demo if present.
        existing = [
            u
            for u in neo4j_list_universes(UniverseFilter(limit=500))
            if u.name == _DEMO_NAME
        ]
        entities_payload = [
            {"name": n, "type": t, "description": d, "want": w, "tags": []}
            for (n, t, d, w) in _DEMO_ENTITIES
        ]
        if existing:
            u = existing[0]
            return (
                QuickWorldResult(
                    multiverse_id=u.multiverse_id,
                    universe_id=u.id,
                    world_name=_DEMO_NAME,
                    world_description=_DEMO_DESCRIPTION,
                    axiom=_DEMO_AXIOM,
                    opening_scene=(
                        "Dusk settles over Millhaven as you arrive. The innkeeper Barnaby "
                        "is already barring his shutters. Somewhere past the square, the fog "
                        "is thickening toward the old cemetery."
                    ),
                    pc_concept="A traveler who took the last room at the Millhaven Inn — and noticed the drag marks.",
                    entities=entities_payload,
                    lore_facts=list(_DEMO_LORE),
                    committed=len(_DEMO_ENTITIES) + len(_DEMO_LORE) + 1,
                    errors=[],
                ),
                True,
            )

        omni = neo4j_ensure_omniverse()
        mv = neo4j_create_multiverse(
            DLMultiverseCreate(
                omniverse_id=UUID(omni["omniverse_id"]),
                name="The Mistlands",
                system_name="Mistlands Core",
                description="Demo setting (Millhaven).",
                is_template=False,
                source_document_id=None,
                parent_multiverse_id=None,
            )
        )
        universe = neo4j_create_universe(
            DLUniverseCreate(
                multiverse_id=mv.id,
                name=_DEMO_NAME,
                description=_DEMO_DESCRIPTION,
                genre=_DEMO_GENRE,
                tone=None,
                tech_level=None,
                parent_universe_id=None,
                is_template=False,
                default_game_system_id=mistlands_id,
                default_system_source_type="generic_library" if mistlands_id else None,
                default_system_source_id=str(mistlands_id) if mistlands_id else None,
                default_system_name="Mistlands Core" if mistlands_id else None,
            )
        )
        return (
            QuickWorldResult(
                multiverse_id=mv.id,
                universe_id=universe.id,
                world_name=_DEMO_NAME,
                world_description=_DEMO_DESCRIPTION,
                axiom=_DEMO_AXIOM,
                opening_scene=(
                    "Dusk settles over Millhaven as you arrive. The innkeeper Barnaby is "
                    "already barring his shutters. Somewhere past the square, the fog is "
                    "thickening toward the old cemetery."
                ),
                pc_concept="A traveler who took the last room at the Millhaven Inn — and noticed the drag marks.",
                entities=entities_payload,
                lore_facts=list(_DEMO_LORE),
                committed=0,
                errors=[],
            ),
            False,
        )

    try:
        result, reused = await anyio.to_thread.run_sync(_ensure_demo)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        raise HTTPException(502, f"Could not create demo world: {exc}") from exc

    # Commit the curated content to canon on first creation.
    if not reused:
        from monitor_agents.quick_world import QuickWorldBuilder

        builder = QuickWorldBuilder()
        committed, errors = await builder._canonize(  # noqa: SLF001 — reuse commit path
            mv_id=result.multiverse_id,
            universe_id=result.universe_id,
            world_name=result.world_name,
            axiom=result.axiom,
            entities=result.entities,
            lore_facts=result.lore_facts,
        )
        result.committed = committed
        result.errors = errors

    # Query MongoDB for "Mistlands Core" system ID
    from monitor_data.tools.mongodb_tools import mongodb_list_game_systems

    systems_res = await anyio.to_thread.run_sync(mongodb_list_game_systems, True, 50)
    mistlands_id = None
    for sys in getattr(systems_res, "systems", systems_res):
        if sys.name == "Mistlands Core":
            mistlands_id = sys.id
            break

    payload = result.summary()
    session_id: str | None = None
    if start_playing:
        try:
            from .chat import create_session
            from .chat_schemas import SessionCreate

            # Bootstrap a pregen PC with a sheet so the demo exercises the
            # mechanical layer (HP/resources in the HUD), not just prose (T-092).
            pc_id: str | None = None
            try:
                pc_id = await anyio.to_thread.run_sync(
                    _ensure_demo_pc, result.universe_id, mistlands_id
                )
            except Exception as exc:  # noqa: BLE001 — PC is a nice-to-have
                payload.setdefault("errors", []).append(
                    f"Demo PC bootstrap failed: {exc}"
                )

            session = await create_session(
                SessionCreate(
                    title="The Millhaven Disappearances",
                    mode="autonomous_gm",
                    multiverse_id=str(result.multiverse_id),
                    universe_id=str(result.universe_id),
                    universe_label=_DEMO_NAME,
                    tone="mystery",
                    # Auto-roll so the mechanical HUD populates without the
                    # manual WS dice protocol; the bound PC carries the sheet.
                    play_mode="dice_game_system",
                    system_id=str(mistlands_id) if mistlands_id else None,
                    character_id=pc_id,
                    speaker_character_id=pc_id,
                    controlled_character_ids=[pc_id] if pc_id else [],
                )
            )
            session_id = session.id
        except Exception as exc:  # noqa: BLE001
            payload.setdefault("errors", []).append(f"Session bootstrap failed: {exc}")

    return DemoWorldResponse(session_id=session_id, reused=reused, **payload)


@router.post("/quick-world", response_model=QuickWorldResponse)
async def quick_world(body: QuickWorldRequest) -> QuickWorldResponse:
    """Expand a seed into a small playable universe and commit it as canon."""
    try:
        from monitor_agents.quick_world import QuickWorldBuilder
    except Exception as exc:  # noqa: BLE001 — agents layer unavailable
        raise HTTPException(503, f"World builder unavailable: {exc}") from exc

    builder = QuickWorldBuilder()
    try:
        result = await builder.build(
            seed=body.seed.strip(),
            genre=body.genre.strip(),
            tone=body.tone.strip(),
            name=(body.name or "").strip() or None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("quick-world build failed: %s", exc)
        raise HTTPException(502, f"World generation failed: {exc}") from exc

    # Query MongoDB for "Mistlands Core" system ID
    from monitor_data.tools.mongodb_tools import mongodb_list_game_systems
    import anyio

    try:
        systems_res = await anyio.to_thread.run_sync(
            mongodb_list_game_systems, True, 50
        )
        mistlands_id = None
        for sys in getattr(systems_res, "systems", systems_res):
            if sys.name == "Mistlands Core":
                mistlands_id = sys.id
                break
    except Exception:
        mistlands_id = None

    payload = result.summary()
    session_id: str | None = None

    if body.start_playing:
        try:
            from .chat import create_session
            from .chat_schemas import SessionCreate

            pc_id: str | None = None
            try:
                pc_id = await anyio.to_thread.run_sync(
                    _ensure_demo_pc, result.universe_id, mistlands_id
                )
            except Exception as exc:  # noqa: BLE001
                payload.setdefault("errors", []).append(
                    f"Quick-world PC bootstrap failed: {exc}"
                )

            session = await create_session(
                SessionCreate(
                    title=f"{result.world_name}",
                    mode="autonomous_gm",
                    multiverse_id=str(result.multiverse_id),
                    universe_id=str(result.universe_id),
                    universe_label=result.world_name,
                    tone=(body.tone.strip() or "dramatic"),
                    play_mode="dice_game_system",
                    system_id=str(mistlands_id) if mistlands_id else None,
                    character_id=pc_id,
                    speaker_character_id=pc_id,
                    controlled_character_ids=[pc_id] if pc_id else [],
                )
            )
            session_id = session.id
        except Exception as exc:  # noqa: BLE001 — world still made; play link optional
            logger.warning("quick-world session bootstrap failed: %s", exc)
            payload.setdefault("errors", []).append(f"Session bootstrap failed: {exc}")

    return QuickWorldResponse(session_id=session_id, **payload)
