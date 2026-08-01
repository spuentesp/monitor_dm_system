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
from typing import Any

import structlog

from .character_storage import (
    add_version,
    delete_version,
    get_character,
    get_version,
    list_versions,
    touch_version,
)

log = structlog.get_logger()

# Sentinel names for the hidden host universe.
_CONVERSATORY_MULTIVERSE_NAME = "__MONITOR_CONVERSATORY__"
_CONVERSATORY_UNIVERSE_NAME = "Conversatory"

# Stable sentinel "player" entity so NPCVoice keys relationship_states and
# accumulates trust/fear/affinity deltas across conversatory sessions. Without
# a player_entity_id, NPCVoice skips relationship tracking entirely.
_CONVERSATORY_PLAYER_ID = uuid.UUID("c0a7e7a7-0000-4000-8000-000000000001")

# Cached host-universe id (resolved once per process).
_conversatory_universe_id: str | None = None

# Live ConversationLoop cache, keyed by conversation_id (string).
_LOOPS: OrderedDict[str, Any] = OrderedDict()
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
        universes = await asyncio.to_thread(neo4j_list_universes, UniverseFilter(limit=1000))
        for u in universes:
            if getattr(u, "name", None) == _CONVERSATORY_UNIVERSE_NAME:
                _conversatory_universe_id = str(u.id)
                return _conversatory_universe_id
    except Exception as exc:
        log.warning("conversatory_universe_lookup_failed", error=str(exc))

    # Not found — create the multiverse → universe chain via CanonKeeper.
    from monitor_agents.canonkeeper.agent import CanonKeeper

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

    u = await keeper.create_universe(    # type: ignore
        {
            "multiverse_id": str(mv["id"]),
            "name": _CONVERSATORY_UNIVERSE_NAME,
            "genre": "Freeform",
            "description": "Standalone roleplay characters live here.",
            "tone": "neutral",
        }
    )
    if "id" not in u:    # type: ignore
        raise RuntimeError(f"Failed to create conversatory universe: {u}")

    _conversatory_universe_id = str(u["id"])    # type: ignore
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
    from monitor_agents.character_creator.card_draft import CardDrafter

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


def _provision_entity_and_profile(universe_id: str, char: dict[str, Any], fields: dict[str, Any]) -> str:
    """Create the EntityInstance + NPCProfile. Returns the new entity id (str).

    Mirrors entities._persist_generated_entity. Routes the Entity write
    through CanonKeeper.create_entity (the layer-2 authority path —
    INV-1: only CanonKeeper writes Neo4j entity nodes). The NPCProfile
    is stamped with universe_id so its working state can be partitioned
    by Character Version (per-universe recall + state).
    """
    import asyncio

    from monitor_agents.canonkeeper.agent import CanonKeeper
    from monitor_data.schemas.base import Authority, CanonLevel, EntityType
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.npc_profiles import BehavioralTrigger, NPCProfileCreate
    from monitor_data.tools.mongodb_tools import mongodb_create_npc_profile

    entity_create = EntityCreate(
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

    # INV-1: route the Entity write through CanonKeeper rather than
    # calling neo4j_create_entity directly. The keeper owns the Neo4j
    # authority layer and runs the canonical-side bookkeeping.
    keeper = CanonKeeper()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # We're inside another async context — run the keeper call in a
        # worker thread so we don't block the request loop.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            created = pool.submit(lambda: asyncio.run(keeper.create_entity(entity_create))).result()
    else:
        created = asyncio.run(keeper.create_entity(entity_create))

    entity_id = created["id"] if isinstance(created, dict) else str(created)

    triggers = [BehavioralTrigger(**t) for t in fields.get("triggers", [])]
    mongodb_create_npc_profile(
        NPCProfileCreate(
            entity_id=uuid.UUID(entity_id),
            universe_id=uuid.UUID(universe_id),
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
    return entity_id    # type: ignore


async def ensure_character_backed(character_id: str, universe_id: str | None = None) -> dict[str, Any]:
    """Ensure the character has an incarnation in the requested universe.

    Resolution:
      1. If a version already exists for (character_id, universe_id), return it.
      2. Otherwise resolve the target universe (caller → card default →
         hidden Conversatory), then provision a new EntityInstance +
         NPCProfile in that universe and append a version entry.

    The returned dict carries the legacy {entity_id, universe_id} shape AND a
    version_id so callers can render the incarnation (Character Versions UI).
    """
    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")

    # Resolve the target universe for this incarnation.
    if universe_id is None:
        universe_id = (
            char.get("default_universe_id") or char.get("source_universe_id") or await ensure_conversatory_universe()
        )
    universe_id = str(universe_id)

    # 1. Idempotent: existing version returns immediately. Check the
    #    already-loaded doc to avoid an extra Mongo round-trip (and so this
    #    function is fully driven by the patched get_character in tests).
    existing_version = next(
        (v for v in (char.get("versions") or []) if v.get("universe_id") == universe_id),
        None,
    )
    if existing_version:
        return {
            "entity_id": str(existing_version["entity_id"]),
            "universe_id": universe_id,
            "version_id": str(existing_version["version_id"]),
            "npc_profile_id": existing_version.get("npc_profile_id"),
        }

    # 2. Legacy fast-path: character was backed before versions existed.
    #    Treat the legacy top-level fields as a (default) incarnation only
    #    if the resolved universe matches the card's stored default. This
    #    keeps old clients working while we route new ones through versions.
    if (
        char.get("entity_id")
        and char.get("source_universe_id")
        and str(char.get("source_universe_id")) == universe_id
        and not char.get("versions")
    ):
        legacy_entity_id = str(char["entity_id"])
        added = add_version(
            character_id,
            universe_id,
            legacy_entity_id,
            npc_profile_id=None,  # populated lazily; not required
        )
        return {
            "entity_id": legacy_entity_id,
            "universe_id": universe_id,
            "version_id": added["version_id"],
            "npc_profile_id": added.get("npc_profile_id"),
        }

    # 3. New incarnation — generate the profile from the card and provision.
    from monitor_agents.character_creator.npc_profile_gen import NPCProfileGenerator

    generator = NPCProfileGenerator()
    fields = await asyncio.to_thread(
        generator.forward,
        char["name"],
        char.get("description", "") or "",
        char.get("personality", "") or "",
        char.get("gm_notes", "") or "",
    )

    entity_id = await asyncio.to_thread(_provision_entity_and_profile, universe_id, char, fields)
    added = add_version(character_id, universe_id, entity_id)
    log.info(
        "character_expanded",
        character_id=character_id,
        entity_id=entity_id,
        universe_id=universe_id,
        version_id=added["version_id"],
    )
    return {
        "entity_id": entity_id,
        "universe_id": universe_id,
        "version_id": added["version_id"],
        "npc_profile_id": added.get("npc_profile_id"),
    }


async def delete_incarnation(character_id: str, universe_id: str) -> bool:
    """Tear down a Character Version: drop Neo4j entity + Mongo NPCProfile.

    Only deletes the EntityInstance / NPCProfile if no other characters'
    incarnations still reference it (safety against shared ids — a real
    possibility if a card was imported from an existing universe NPC).
    """
    version = get_version(character_id, universe_id)
    if not version:
        return False
    entity_id = str(version["entity_id"])

    # Best-effort cleanup of the Neo4j entity + NPCProfile doc. We don't
    # raise — the Mongo versions[] entry is the source of truth for "this
    # incarnation no longer exists."
    try:
        from monitor_data.tools.neo4j_tools.entities import neo4j_delete_entity

        await asyncio.to_thread(neo4j_delete_entity, uuid.UUID(entity_id))
    except Exception as exc:
        log.warning("incarnation_delete_neo4j_failed", error=str(exc))
    try:
        # No mongodb_delete_npc_profile tool exists; drop the doc directly.
        from monitor_data.db.mongodb import get_mongodb_client

        def _drop_profile_doc() -> None:
            get_mongodb_client().get_collection("npc_profiles").delete_one({"entity_id": entity_id})

        await asyncio.to_thread(_drop_profile_doc)
    except Exception as exc:
        log.warning("incarnation_delete_mongo_failed", error=str(exc))

    delete_version(character_id, universe_id)
    log.info(
        "incarnation_deleted",
        character_id=character_id,
        universe_id=universe_id,
        entity_id=entity_id,
    )
    return True


def list_incarnations(character_id: str) -> list[dict[str, Any]]:
    """Public wrapper: list a character's incarnations (newest first)."""
    return list_versions(character_id)


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


async def start_conversation(character_id: str, universe_id: str | None = None) -> dict[str, Any]:
    """Expand-if-needed, open a DIRECT ConversationLoop, return opening + id.

    universe_id picks the incarnation (Character Version). If omitted, the
    character's default incarnation is used. Pass a new universe_id to
    create an additional incarnation for that universe on the fly.
    """
    from monitor_agents.loops.conversation_loop import (
        ConversationLoop,
        ConversationMode,
    )

    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")

    backing = await ensure_character_backed(character_id, universe_id=universe_id)

    loop = await ConversationLoop.start(
        universe_id=uuid.UUID(backing["universe_id"]),
        mode=ConversationMode.DIRECT,
        npc_ids=[uuid.UUID(backing["entity_id"])],
        story_id=None,
        scene_id=None,
        player_entity_id=_CONVERSATORY_PLAYER_ID,
        # Enables per-turn lorebook scanning (imported character_book entries)
        # for this conversation.
        lorebook_character_ids=[character_id],
    )
    conversation_id = str(loop.state.conversation_id)
    _cache_loop(conversation_id, loop)
    # Stamp last_chatted_at on the incarnation so the roster can surface
    # "recently used" versions.
    try:
        touch_version(character_id, str(backing["universe_id"]))
    except Exception:
        pass

    opening = char.get("first_message") or f"{char['name']} turns to face you."
    return {
        "conversation_id": conversation_id,
        "character_id": character_id,
        "entity_id": backing["entity_id"],
        "universe_id": str(backing["universe_id"]),
        "version_id": str(backing["version_id"]),
        "opening": opening,
    }


async def resume_conversation(character_id: str, conversation_id: str) -> Any | None:
    """Rebuild an in-memory DIRECT loop from its persisted MongoDB transcript.

    Light-RP loops are process-local; a backend restart orphans active
    sessions. The ``conversations`` doc has everything needed to continue:
    universe/npc/player ids plus the full turn list. Returns None when the
    conversation is unknown, not active, or belongs to another incarnation.
    """
    from monitor_agents.loops.conversation_loop import (
        ConversationLoop,
        ConversationMode,
        load_npc_context,
    )
    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("conversations")
    doc = coll.find_one({"conversation_id": conversation_id})
    if not doc or doc.get("status") != "active":
        return None

    backing = await ensure_character_backed(character_id, universe_id=doc.get("universe_id"))
    if backing["entity_id"] not in [str(n) for n in (doc.get("npc_ids") or [])]:
        return None

    player_id = doc.get("player_entity_id")
    loop = ConversationLoop(
        conversation_id=uuid.UUID(conversation_id),
        universe_id=uuid.UUID(backing["universe_id"]),
        mode=ConversationMode.DIRECT,
        npc_ids=[uuid.UUID(backing["entity_id"])],
        story_id=None,
        scene_id=None,
        player_entity_id=uuid.UUID(player_id) if player_id else _CONVERSATORY_PLAYER_ID,
        lorebook_character_ids=[character_id],
    )
    loop._apply(await load_npc_context(loop.state))
    loop.state.turns = [
        {
            "turn_index": t.get("turn_index", i),
            "speaker_role": t.get("speaker_role"),
            "entity_name": t.get("entity_name"),
            "text": t.get("text", ""),
        }
        for i, t in enumerate(doc.get("turns", []))
    ]
    loop.state.turns_count = len(loop.state.turns)
    # Restore the durable proposal outbox written after each turn (crash-safe).
    loop.state.pending_proposals = list(doc.get("pending_proposals") or [])
    _cache_loop(conversation_id, loop)
    return loop


async def send_message(
    conversation_id: str,
    text: str,
    include_cross_incarnation: bool = False,
    character_id: str | None = None,
) -> dict[str, Any]:
    """Step the loop once; return the NPC reply + emotional/relationship read.

    include_cross_incarnation is propagated to NPCVoice so the Qdrant recall
    can broaden to other universes when the caller explicitly opts in.

    Loops are process-local, so a backend restart orphans active sessions.
    When the loop is missing and character_id is provided, the loop is
    rebuilt from the persisted MongoDB transcript (resume) before giving up.
    """
    loop = get_loop(conversation_id)
    if loop is None and character_id:
        loop = await resume_conversation(character_id, conversation_id)
    if loop is None:
        raise KeyError(conversation_id)

    # The loop's state.universe_id is the incarnation's universe; we forward
    # the cross-incarnation flag by setting a transient attribute on the
    # loop state (read by NPCVoice via the conversation_loop wrapper).
    if include_cross_incarnation and getattr(loop, "state", None) is not None:
        loop.state.include_cross_incarnation = True

    responses = await loop.step(text)

    # Durable outbox: persist accumulated proposals onto the conversation doc
    # after every turn so a mid-session crash doesn't lose them (they used to
    # live only in loop memory until close). Restored on resume.
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        get_mongodb_client().get_collection("conversations").update_one(
            {"conversation_id": conversation_id},
            {"$set": {"pending_proposals": list(getattr(loop.state, "pending_proposals", []) or [])}},
        )
    except Exception as exc:
        log.warning("conversation_proposals_persist_failed", conversation_id=conversation_id, exc_info=True)
        from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
        from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource

        await RoleplayErrorRecorder.record(
            source=RoleplayErrorSource.CHARACTER_CONVERSATION,
            category=RoleplayErrorCategory.UNKNOWN,
            message=str(exc),
            fatal=False,
            conversation_id=conversation_id,
        )

    # Reset the transient flag so subsequent steps default to strict scope.
    if include_cross_incarnation and getattr(loop, "state", None) is not None:
        loop.state.include_cross_incarnation = False

    reply = responses[0] if responses else {}
    return {
        "text": reply.get("text", ""),
        "emotional_state": reply.get("emotional_state"),
        "relationship_snapshot": reply.get("relationship_snapshot", {}),
    }


async def redistill_conversation(
    character_id: str, conversation_id: str, *, force: bool = False
) -> dict[str, Any]:
    """Rebuild episodic event proposals for a persisted conversation.

    Episodic proposals are derived from the durable transcript, so they can
    always be regenerated — e.g. after a close-time LLM failure. Idempotent
    by default: if episodic proposals already exist for this conversation,
    they are returned unless force=True.
    """
    from monitor_agents.loops.conversation_loop import redistill_episodic_proposals
    from monitor_data.db.mongodb import get_mongodb_client

    client = get_mongodb_client()
    doc = client.get_collection("conversations").find_one({"conversation_id": conversation_id})
    if not doc:
        raise KeyError(conversation_id)

    backing = await ensure_character_backed(character_id, universe_id=doc.get("universe_id"))
    if backing["entity_id"] not in [str(n) for n in (doc.get("npc_ids") or [])]:
        raise KeyError(conversation_id)

    existing = list(
        client.get_collection("proposed_changes").find(
            {"evidence.ref_id": conversation_id, "content.source": "episodic_extraction"},
            {"content.description": 1, "status": 1},
        )
    )
    if existing and not force:
        return {
            "staged": 0,
            "existing": len(existing),
            "descriptions": [e.get("content", {}).get("description", "") for e in existing],
        }

    staged = await redistill_episodic_proposals(doc)
    return {
        "staged": len(staged),
        "existing": len(existing),
        "descriptions": [p.get("content", {}).get("description", "") for p in staged],
    }


async def end_conversation(conversation_id: str, character_id: str | None = None) -> dict[str, Any]:
    """Finish the loop (persist + stage). Drops it from the cache.

    Always evicts the loop from the cache, even when finish() raises — leaving
    a dead loop in the cache would silently block the same conversation_id
    from being restarted. When the loop was lost to a restart, it is rebuilt
    from the persisted transcript first so the accumulated proposal outbox
    still gets staged.
    """
    loop = get_loop(conversation_id)
    if loop is None and character_id:
        loop = await resume_conversation(character_id, conversation_id)
    if loop is None:
        return {"ended": True, "proposals": 0}
    proposals: list[Any] = []
    try:
        proposals = await loop.finish()
        return {"ended": True, "proposals": len(proposals or [])}
    except Exception as exc:
        log.warning("conversation_finish_failed", conversation_id=conversation_id, exc_info=True)
        from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
        from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource

        await RoleplayErrorRecorder.record(
            source=RoleplayErrorSource.CHARACTER_CONVERSATION,
            category=RoleplayErrorCategory.UNKNOWN,
            message=str(exc),
            fatal=True,
            conversation_id=conversation_id,
        )
        return {"ended": False, "proposals": len(proposals or [])}
    finally:
        pop_loop(conversation_id)


def list_conversations(entity_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Past ConversationSessions for this character's entity, newest first.

    Returns [] when entity_id is missing (no backing entity yet).
    """
    if not entity_id:
        return []
    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("conversations")
    cursor = coll.find({"npc_ids": entity_id}).sort("updated_at", -1).limit(max(1, min(int(limit), 100)))
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
