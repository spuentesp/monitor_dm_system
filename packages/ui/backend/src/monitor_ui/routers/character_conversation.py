"""
Character conversatory — story-less MONITOR-backed chat with a roster character.

LAYER: 3 (UI backend)

A standalone "character" (see character_storage) is, by default, a light card
(name + free-text personality). To talk to it through the MONITOR engine
(NPCVoice: memory, triggers, emotional state, relationship deltas) it must be
backed by a real EntityInstance (Neo4j) + NPCProfile (Mongo).

This module:
  * find-or-creates a hidden "Conversatory" universe to host standalone
    characters' entities (so ConversationLoop, which requires a universe_id,
    works without any story);
  * expands a light card into a full NPCProfile via NPCProfileGenerator and
    provisions the backing entity (ensure_character_backed) — idempotent;
  * starts / steps / ends story-less ConversationLoop DIRECT sessions and
    caches the live loops, mirroring chat_loops._CONVERSATION_LOOPS.

Reuses the provisioning pattern from entities._persist_generated_entity.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import OrderedDict
from typing import Any, Optional

import structlog

from .character_storage import get_character, update_character

log = structlog.get_logger()

# Sentinel names for the hidden host universe.
_CONVERSATORY_MULTIVERSE_NAME = "__MONITOR_CONVERSATORY__"
_CONVERSATORY_UNIVERSE_NAME = "Conversatory"

# Stable sentinel "player" entity so NPCVoice keys relationship_states and
# accumulates trust/fear/affinity deltas across conversatory sessions. Without
# a player_entity_id, NPCVoice skips relationship tracking entirely.
_CONVERSATORY_PLAYER_ID = uuid.UUID("c0a7e7a7-0000-4000-8000-000000000001")

# Cached host-universe id (resolved once per process).
_conversatory_universe_id: Optional[str] = None

# Live ConversationLoop cache, keyed by conversation_id (string).
_LOOPS: "OrderedDict[str, Any]" = OrderedDict()
_LOOPS_MAX = 64


# ---------------------------------------------------------------------------
# Conversatory host universe
# ---------------------------------------------------------------------------


async def ensure_conversatory_universe() -> str:
    """Find-or-create the hidden universe that hosts standalone characters."""
    global _conversatory_universe_id
    if _conversatory_universe_id:
        return _conversatory_universe_id

    from monitor_data.schemas.universe import UniverseFilter
    from monitor_data.tools.neo4j_tools.core import neo4j_list_universes

    try:
        universes = await asyncio.to_thread(
            neo4j_list_universes, UniverseFilter(limit=1000)
        )
        for u in universes:
            if getattr(u, "name", None) == _CONVERSATORY_UNIVERSE_NAME:
                _conversatory_universe_id = str(u.id)
                return _conversatory_universe_id
    except Exception as exc:  # noqa: BLE001
        log.warning("conversatory_universe_lookup_failed", error=str(exc))

    # Not found — create the multiverse → universe chain via CanonKeeper.
    from monitor_agents.canonkeeper import CanonKeeper

    keeper = CanonKeeper()
    mv = await keeper.create_multiverse(
        {
            "name": _CONVERSATORY_MULTIVERSE_NAME,
            "system_name": "Freeform",
            "description": "Hidden host for standalone roleplay characters.",
        }
    )
    if "id" not in mv:
        raise RuntimeError(f"Failed to create conversatory multiverse: {mv}")

    u = await keeper.create_universe(
        {
            "multiverse_id": str(mv["id"]),
            "name": _CONVERSATORY_UNIVERSE_NAME,
            "genre": "Freeform",
            "description": "Standalone roleplay characters live here.",
            "tone": "neutral",
        }
    )
    if "id" not in u:
        raise RuntimeError(f"Failed to create conversatory universe: {u}")

    _conversatory_universe_id = str(u["id"])
    log.info("conversatory_universe_created", universe_id=_conversatory_universe_id)
    return _conversatory_universe_id


# ---------------------------------------------------------------------------
# LLM-assisted card drafting ("fill the card for me")
# ---------------------------------------------------------------------------


async def draft_card(
    concept: str,
    name: str = "",
    description: str = "",
    personality: str = "",
) -> dict[str, Any]:
    """Draft the light-card fields from a concept. Does not persist anything."""
    from monitor_agents.prompts.card_draft import CardDrafter

    drafter = CardDrafter()
    return await asyncio.to_thread(
        drafter.forward,
        concept,
        name,
        description,
        personality,
    )


# ---------------------------------------------------------------------------
# Expansion: light card → MONITOR-backed entity + NPCProfile
# ---------------------------------------------------------------------------


def _provision_entity_and_profile(
    universe_id: str, char: dict[str, Any], fields: dict[str, Any]
) -> str:
    """Create the EntityInstance + NPCProfile. Returns the new entity id (str).

    Mirrors entities._persist_generated_entity; synchronous (Neo4j/Mongo tools).
    """
    from monitor_data.schemas.base import Authority, CanonLevel, EntityType
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.npc_profiles import BehavioralTrigger, NPCProfileCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_npc_profile
    from monitor_data.tools.neo4j_tools.entities import neo4j_create_entity

    entity = neo4j_create_entity(
        EntityCreate(
            universe_id=uuid.UUID(universe_id),
            name=char["name"],
            entity_type=EntityType.CHARACTER,
            sub_type="npc",
            is_archetype=False,
            description=char.get("description", "") or "",
            properties={
                "role": "character",
                "standalone_character_id": char["id"],
                "generation_source": "character_card_expansion",
            },
            authority=Authority.SYSTEM,
            canon_level=CanonLevel.CANON,
            confidence=1.0,
        )
    )

    triggers = [BehavioralTrigger(**t) for t in fields.get("triggers", [])]
    mongodb_create_npc_profile(
        NPCProfileCreate(
            entity_id=entity.id,
            traits=fields.get("traits", {}),
            values=fields.get("values", []),
            fears=fields.get("fears", []),
            desires=fields.get("desires", []),
            speech_style=fields.get("speech_style"),
            catchphrases=fields.get("catchphrases", []),
            triggers=triggers,
            gm_notes=char.get("gm_notes") or "",
            current_emotional_state=fields.get("current_emotional_state", "neutral"),
        )
    )
    return str(entity.id)


async def ensure_character_backed(character_id: str) -> dict[str, Any]:
    """Ensure the character has an EntityInstance + NPCProfile.

    Idempotent: returns immediately if already backed. Otherwise generates a
    profile from the card and provisions the backing entity in the character's
    own universe (if universe-linked) or the hidden Conversatory universe.

    Returns {"entity_id": str, "universe_id": str}.
    """
    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")

    universe_id = char.get("source_universe_id") or await ensure_conversatory_universe()

    if char.get("entity_id"):
        return {"entity_id": str(char["entity_id"]), "universe_id": str(universe_id)}

    # Generate a structured profile from the light card.
    from monitor_agents.prompts.npc_profile_gen import NPCProfileGenerator

    generator = NPCProfileGenerator()
    fields = await asyncio.to_thread(
        generator.forward,
        char["name"],
        char.get("description", "") or "",
        char.get("personality", "") or "",
        char.get("gm_notes", "") or "",
    )

    entity_id = await asyncio.to_thread(
        _provision_entity_and_profile, str(universe_id), char, fields
    )
    update_character(
        character_id, {"entity_id": entity_id, "source_universe_id": str(universe_id)}
    )
    log.info(
        "character_expanded",
        character_id=character_id,
        entity_id=entity_id,
        universe_id=str(universe_id),
    )
    return {"entity_id": entity_id, "universe_id": str(universe_id)}


# ---------------------------------------------------------------------------
# Conversation lifecycle
# ---------------------------------------------------------------------------


def _cache_loop(conversation_id: str, loop: Any) -> None:
    _LOOPS[conversation_id] = loop
    _LOOPS.move_to_end(conversation_id)
    while len(_LOOPS) > _LOOPS_MAX:
        _LOOPS.popitem(last=False)


def get_loop(conversation_id: str) -> Any | None:
    return _LOOPS.get(conversation_id)


def pop_loop(conversation_id: str) -> None:
    _LOOPS.pop(conversation_id, None)


async def start_conversation(character_id: str) -> dict[str, Any]:
    """Expand-if-needed, open a DIRECT ConversationLoop, return opening + id."""
    from monitor_agents.loops.conversation_loop import ConversationLoop, ConversationMode

    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")

    backing = await ensure_character_backed(character_id)

    loop = await ConversationLoop.start(
        universe_id=uuid.UUID(backing["universe_id"]),
        mode=ConversationMode.DIRECT,
        npc_ids=[uuid.UUID(backing["entity_id"])],
        story_id=None,
        scene_id=None,
        player_entity_id=_CONVERSATORY_PLAYER_ID,
    )
    conversation_id = str(loop.state.conversation_id)
    _cache_loop(conversation_id, loop)

    opening = char.get("first_message") or f"{char['name']} turns to face you."
    return {
        "conversation_id": conversation_id,
        "character_id": character_id,
        "entity_id": backing["entity_id"],
        "opening": opening,
    }


async def send_message(conversation_id: str, text: str) -> dict[str, Any]:
    """Step the loop once; return the NPC reply + emotional/relationship read."""
    loop = get_loop(conversation_id)
    if loop is None:
        raise KeyError(conversation_id)

    responses = await loop.step(text)
    reply = responses[0] if responses else {}
    return {
        "text": reply.get("text", ""),
        "emotional_state": reply.get("emotional_state"),
        "relationship_snapshot": reply.get("relationship_snapshot", {}),
    }


async def end_conversation(conversation_id: str) -> dict[str, Any]:
    """Finish the loop (persist + stage). Drops it from the cache."""
    loop = get_loop(conversation_id)
    if loop is None:
        return {"ended": True, "proposals": 0}
    try:
        proposals = await loop.finish()
    finally:
        pop_loop(conversation_id)
    return {"ended": True, "proposals": len(proposals or [])}


def list_conversations(entity_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Past ConversationSessions for this character's entity, newest first."""
    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("conversations")
    cursor = (
        coll.find({"npc_ids": entity_id})
        .sort("updated_at", -1)
        .limit(max(1, min(int(limit), 100)))
    )
    out: list[dict[str, Any]] = []
    for doc in cursor:
        out.append(
            {
                "conversation_id": doc.get("conversation_id"),
                "status": doc.get("status"),
                "turn_count": len(doc.get("turns", [])),
                "created_at": doc["created_at"].isoformat()
                if hasattr(doc.get("created_at"), "isoformat")
                else str(doc.get("created_at", "")),
                "updated_at": doc["updated_at"].isoformat()
                if hasattr(doc.get("updated_at"), "isoformat")
                else str(doc.get("updated_at", "")),
            }
        )
    return out
