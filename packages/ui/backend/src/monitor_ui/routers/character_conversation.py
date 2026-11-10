"""
Character conversatory — story-less MONITOR-backed chat with a roster character.

LAYER: 3 (UI backend)

A standalone "character" (see character_storage) is, by default, a light card
(name + free-text personality). To talk to it through the MONITOR engine
(NPCVoice: memory, triggers, emotional state, relationship deltas) it must be
backed by a real EntityInstance (Neo4j) + NPCProfile (Mongo).

This module:
  * find-or-creates the owner's hidden "Conversatory" universe (one per user,
    via the Postgres ownership registry) to host standalone characters'
    entities (so ConversationLoop, which requires a universe_id, works
    without any story);
  * expands a light card into a full NPCProfile via NPCProfileGenerator and
    provisions the backing entity (ensure_character_backed) — idempotent;
  * starts / steps / ends story-less ConversationLoop DIRECT sessions and
    caches the live loops, mirroring chat_loops._CONVERSATION_LOOPS.

Reuses the provisioning pattern from entities._persist_generated_entity.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import uuid
from asyncio import Lock as _AsyncLock
from collections import OrderedDict
from typing import Any

import structlog

from .character_storage import (
    add_version,
    create_character,
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

# Live ConversationLoop cache, keyed by conversation_id (string).
_LOOPS: OrderedDict[str, Any] = OrderedDict()
_LOOPS_MAX = 64

# Per-conversation mutexes so concurrent send/end calls serialize cleanly.
_LOCKS: OrderedDict[str, _AsyncLock] = OrderedDict()
_LOCKS_MAX = 256

# NPCProfileCreate.gm_notes limit. The full notes stay on the card.
_PROFILE_NOTES_MAX = 5000
_CARD_PROMPT_MAX = 12000

_CLIENT_FINGERPRINT_MESSAGES = 2


# ---------------------------------------------------------------------------
# Conversatory host universe
# ---------------------------------------------------------------------------


async def ensure_conversatory_universe(owner_id: str | uuid.UUID | None = None) -> str:
    """Find-or-create the owner's hidden universe that hosts standalone cards.

    One Conversatory per user, found through the Postgres ownership registry
    (``worlds.kind = 'conversatory'``) — never by name and never cached in a
    process global. ``owner_id=None`` means the auth-disabled local account
    (legacy cards created before ownership existed).
    """
    from monitor_data.db.postgres import get_postgres_client

    if owner_id is None:
        from monitor_ui.auth import LOCAL_USER_ID

        owner = LOCAL_USER_ID
    else:
        owner = uuid.UUID(str(owner_id))

    db = get_postgres_client()
    await db.connect()
    row = await db.world_get_conversatory(owner)
    if row:
        return str(row["id"])

    # Not found — create the multiverse → universe chain via CanonKeeper and
    # register the universe in the ownership registry as this user's host.
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

    # reason: CanonKeeper.create_universe accepts UniverseCreate | dict; passing a bare dict literal here relies on the agent's runtime validation — narrow to UniverseCreate in a follow-up
    u = await keeper.create_universe(
        {
            "multiverse_id": str(mv["id"]),
            "name": _CONVERSATORY_UNIVERSE_NAME,
            "genre": "Freeform",
            "description": "Standalone roleplay characters live here.",
            "tone": "neutral",
        }
    )
    # reason: u: Any (agent-returned universe dict); subscript access `.id` and `"id" in u` are union-attr gaps that mypy can't bridge across the agent boundary
    if "id" not in u:
        raise RuntimeError(f"Failed to create conversatory universe: {u}")

    universe_id = str(u["id"])
    await db.multiverse_upsert(
        {"id": str(mv["id"]), "owner_id": owner, "label": _CONVERSATORY_MULTIVERSE_NAME, "active": True}
    )
    await db.world_upsert(
        {
            "id": universe_id,
            "owner_id": owner,
            "multiverse_id": str(mv["id"]),
            "label": _CONVERSATORY_UNIVERSE_NAME,
            "active": True,
            "kind": "conversatory",
        }
    )
    log.info("conversatory_universe_created", universe_id=universe_id, owner_id=str(owner))
    return universe_id


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
            gm_notes=(char.get("gm_notes") or "")[:_PROFILE_NOTES_MAX],
            current_emotional_state=fields.get("current_emotional_state", "neutral"),
        )
    )
    # reason: entity_id is the keeper's return value from create_entity — typed Any at the agent boundary; narrow to EntityResponse / UUID once the agent publishes its return contract
    return entity_id  # type: ignore


async def ensure_character_backed(
    character_id: str, universe_id: str | None = None, *, user_name: str | None = None
) -> dict[str, Any]:
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
            char.get("default_universe_id")
            or char.get("source_universe_id")
            or await ensure_conversatory_universe(char.get("owner_id"))
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
    from monitor_data.interop.card_macros import substitute_card_macros

    # Resolve {{char}}/{{user}} placeholders at render time — the stored card
    # stays raw so an export round-trip remains faithful. This profile is shared by
    # every conversation with the incarnation, so {{user}} takes the neutral default;
    # the bound persona's name goes into each conversation's character_card.
    char_rendered = {
        **char,
        **{
            field: substitute_card_macros(str(char.get(field) or ""), char_name=char["name"])
            for field in ("description", "personality", "gm_notes")
        },
    }

    generator = NPCProfileGenerator()
    fields = await asyncio.to_thread(
        generator.forward,
        char_rendered["name"],
        char_rendered.get("description", "") or "",
        char_rendered.get("personality", "") or "",
        char_rendered.get("gm_notes", "") or "",
    )

    entity_id = await asyncio.to_thread(_provision_entity_and_profile, universe_id, char_rendered, fields)
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
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in delete_incarnation)
        log.warning("incarnation_delete_neo4j_failed", error=str(exc))
    try:
        # No mongodb_delete_npc_profile tool exists; drop the doc directly.
        from monitor_data.db.mongodb import get_mongodb_client

        def _drop_profile_doc() -> None:
            get_mongodb_client().get_collection("npc_profiles").delete_one({"entity_id": entity_id})

        await asyncio.to_thread(_drop_profile_doc)
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _drop_profile_doc)
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


def _get_conversation_lock(conversation_id: str) -> _AsyncLock:
    lock = _LOCKS.get(conversation_id)
    if lock is None:
        lock = _AsyncLock()
        _LOCKS[conversation_id] = lock
    _LOCKS.move_to_end(conversation_id)
    if len(_LOCKS) > _LOCKS_MAX:
        for key in list(_LOCKS.keys()):
            if len(_LOCKS) <= _LOCKS_MAX:
                break
            if key != conversation_id and not _LOCKS[key].locked():
                _LOCKS.pop(key, None)
    return lock


def player_id_for_persona(persona_character_id: str | None) -> uuid.UUID:
    """Derive a deterministic player entity UUID per bound persona."""
    if not persona_character_id:
        return _CONVERSATORY_PLAYER_ID
    return uuid.uuid5(_CONVERSATORY_PLAYER_ID, f"persona:{persona_character_id}")


def _loop_matches_character(loop: Any, character_id: str | None) -> bool:
    """Return True when the loop has no character constraint or matches character_id."""
    if not character_id:
        return True
    state = getattr(loop, "state", None)
    bound = getattr(state, "lorebook_character_ids", None)
    if isinstance(bound, (list, tuple, set)) and bound:
        return character_id in bound
    return True


def _cache_loop(conversation_id: str, loop: Any) -> None:
    _LOOPS[conversation_id] = loop
    _LOOPS.move_to_end(conversation_id)
    while len(_LOOPS) > _LOOPS_MAX:
        _LOOPS.popitem(last=False)


def get_loop(conversation_id: str, character_id: str | None = None) -> Any | None:
    loop = _LOOPS.get(conversation_id)
    if loop is not None and not _loop_matches_character(loop, character_id):
        return None
    return loop


def pop_loop(conversation_id: str) -> None:
    _LOOPS.pop(conversation_id, None)


def render_character_card(char: dict[str, Any], user_name: str | None) -> str:
    """Render a card's text for one conversation, with that conversation's persona."""
    from monitor_data.interop.card_macros import substitute_card_macros

    sections = (
        ("Description", char.get("description")),
        ("Personality", char.get("personality")),
        ("Scenario and author's notes", char.get("gm_notes")),
    )
    parts = [
        f"{label}: {substitute_card_macros(str(text).strip(), char_name=char['name'], user_name=user_name)}"
        for label, text in sections
        if str(text or "").strip()
    ]
    return "\n\n".join(parts)[:_CARD_PROMPT_MAX]


async def start_conversation(
    character_id: str,
    universe_id: str | None = None,
    *,
    persona_character_id: str | None = None,
    preset: str = "light",
) -> dict[str, Any]:
    """Expand-if-needed, open a DIRECT ConversationLoop, return opening + id.

    universe_id picks the incarnation (Character Version). If omitted, the
    character's default incarnation is used. Pass a new universe_id to
    create an additional incarnation for that universe on the fly.

    persona_character_id binds a persona card (is_ooc_persona=true): its
    name resolves {{user}} in rendered card text and its name + description
    enter the prompt as the player's persona.

    preset names the LightPreset configuration over the loop ("light" by
    default: no dice, no GM verdict, no canonization prompts).
    """
    from monitor_agents.loops.conversation_loop import (
        ConversationLoop,
        ConversationMode,
        get_preset,
    )

    resolved_preset = get_preset(preset)

    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")

    user_name: str | None = None
    persona_text: str | None = None
    if persona_character_id:
        persona = get_character(persona_character_id)
        if not persona:
            raise ValueError(f"Persona {persona_character_id} not found")
        if not persona.get("is_ooc_persona"):
            raise ValueError(f"Character {persona_character_id} is not a persona (is_ooc_persona=false)")
        user_name = str(persona.get("name") or "").strip() or None
        if user_name:
            persona_desc = str(persona.get("description") or "").strip()
            persona_text = f"{user_name} — {persona_desc}" if persona_desc else user_name

    backing = await ensure_character_backed(character_id, universe_id=universe_id, user_name=user_name)

    player_entity_id = player_id_for_persona(persona_character_id)

    loop = await ConversationLoop.start(
        universe_id=uuid.UUID(backing["universe_id"]),
        mode=ConversationMode.DIRECT,
        npc_ids=[uuid.UUID(backing["entity_id"])],
        story_id=None,
        scene_id=None,
        player_entity_id=player_entity_id,
        # Enables per-turn lorebook scanning (imported character_book entries)
        # for this conversation.
        lorebook_character_ids=[character_id],
        player_persona=persona_text,
        character_card=render_character_card(char, user_name),
        player_name=user_name,
        preset=resolved_preset,
    )
    conversation_id = str(loop.state.conversation_id)
    _cache_loop(conversation_id, loop)
    # Persist the bound persona so a resumed loop (backend restart) keeps
    # injecting it into the voice prompt.
    if persona_text:
        try:
            from monitor_data.db.mongodb import get_mongodb_client

            get_mongodb_client().get_collection("conversations").update_one(
                {"conversation_id": conversation_id},
                {"$set": {"player_persona": persona_text, "player_name": user_name or ""}},
            )
        except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in start_conversation)
            log.warning("conversation_persona_persist_failed", exc_info=True)
    # Stamp the preset so a resumed loop keeps the same configuration.
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        get_mongodb_client().get_collection("conversations").update_one(
            {"conversation_id": conversation_id},
            {"$set": {"preset": resolved_preset.name}},
        )
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in start_conversation)
        log.warning("conversation_preset_persist_failed", exc_info=True)
    # Stamp last_chatted_at on the incarnation so the roster can surface
    # "recently used" versions.
    try:
        touch_version(character_id, str(backing["universe_id"]))
    except Exception:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in start_conversation)
        log.debug("last_chatted_at stamp failed", exc_info=True)

    opening_raw = char.get("first_message") or f"{char['name']} turns to face you."
    from monitor_data.interop.card_macros import substitute_card_macros

    opening = substitute_card_macros(opening_raw, char_name=char["name"], user_name=user_name)
    # Only the card's own greeting is the character speaking; the fallback is narration.
    if char.get("first_message"):
        try:
            await loop.add_opening(opening)
        except Exception:  # noqa: BLE001  # reason: the chat works without it; the character just won't recall its greeting
            log.warning("conversation_opening_persist_failed", conversation_id=conversation_id, exc_info=True)
    return {
        "conversation_id": conversation_id,
        "character_id": character_id,
        "entity_id": backing["entity_id"],
        "universe_id": str(backing["universe_id"]),
        "version_id": str(backing["version_id"]),
        "opening": opening,
        "preset": resolved_preset.name,
    }


def client_history_fingerprint(messages: list[tuple[str, str]]) -> str | None:
    """Identify a position in a client-held chat by its last two messages.

    OpenAI-shaped clients resend their history instead of holding a session id.
    Only the tail is used because they also drop old messages to fit their
    context. Returns None until the history contains a player message: every new
    chat with a card starts from the same greeting, so that can't identify one.
    """
    tail = messages[-_CLIENT_FINGERPRINT_MESSAGES:]
    if not any(role == "user" for role, _ in tail):
        return None
    normalized = "\n".join(f"{role}:{' '.join(text.split())}" for role, text in tail)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def find_client_conversation(character_id: str, persona_id: str | None, fingerprint: str) -> str | None:
    """Return the active conversation a client's history continues, if any."""
    from monitor_data.db.mongodb import get_mongodb_client

    def _find() -> dict[str, Any] | None:
        return (
            get_mongodb_client()
            .get_collection("conversations")
            .find_one(
                {
                    "status": "active",
                    "client_session.character_id": character_id,
                    "client_session.persona_character_id": persona_id,
                    "client_session.fingerprints": fingerprint,
                },
                {"conversation_id": 1, "turns": 1},
                sort=[("updated_at", -1)],
            )
        )

    doc = await asyncio.to_thread(_find)
    if not doc:
        return None
    player_turns = sum(1 for t in (doc.get("turns") or []) if isinstance(t, dict) and t.get("speaker_role") == "player")
    if player_turns >= 100:
        return None
    return str(doc["conversation_id"])


async def remember_client_conversation(
    conversation_id: str,
    character_id: str,
    persona_id: str | None,
    fingerprints: list[str | None],
) -> None:
    """Record the history positions that lead back to this conversation.

    fingerprints holds the position before and after the latest exchange. The
    earlier one is what a client sends when it regenerates that reply.
    """
    from monitor_data.db.mongodb import get_mongodb_client

    def _save() -> None:
        get_mongodb_client().get_collection("conversations").update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    "client_session": {
                        "character_id": character_id,
                        "persona_character_id": persona_id,
                        "fingerprints": [f for f in fingerprints if f],
                    }
                }
            },
        )

    await asyncio.to_thread(_save)


async def resume_conversation(
    character_id: str,
    conversation_id: str,
    *,
    allow_at_limit: bool = False,
) -> Any | None:
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
    loop.state.lorebook_character_ids = [character_id]
    restored_turns = [
        {
            "turn_index": t.get("turn_index", i),
            "speaker_role": t.get("speaker_role"),
            "entity_name": t.get("entity_name"),
            "text": t.get("text", ""),
        }
        for i, t in enumerate(doc.get("turns", []))
    ]
    # Drop any trailing unanswered player turns left by a failed/interrupted LLM call.
    had_trailing_player = False
    while restored_turns and restored_turns[-1].get("speaker_role") == "player":
        restored_turns.pop()
        had_trailing_player = True
    if had_trailing_player:
        with contextlib.suppress(Exception):
            coll.update_one({"conversation_id": conversation_id}, {"$set": {"turns": restored_turns}})
    loop.state.turns = restored_turns
    # turns_count tracks completed player exchanges, not individual messages.
    loop.state.turns_count = sum(1 for t in loop.state.turns if t.get("speaker_role") == "player")
    if not allow_at_limit and loop.state.turns_count >= getattr(loop.state, "max_turns", 100):
        return None
    # Restore the durable proposal outbox written after each turn (crash-safe).
    loop.state.pending_proposals = list(doc.get("pending_proposals") or [])
    loop.state.lorebook_overrides = dict(doc.get("lorebook_overrides") or {})
    # Restore the bound persona so the voice prompt keeps using it.
    loop.state.player_persona = str(doc.get("player_persona") or "")
    stored_name = str(doc.get("player_name") or "").strip()
    if stored_name:
        loop.state.player_name = stored_name
    elif loop.state.player_persona:
        loop.state.player_name = loop.state.player_persona.split(" — ", 1)[0].strip()
    # Restore the preset configuration (light RP: tier, canonization policy).
    preset_name = str(doc.get("preset") or "").strip()
    if preset_name:
        try:
            from monitor_agents.loops.conversation_loop import get_preset

            preset = get_preset(preset_name)
        except KeyError:
            log.warning("conversation_resume_unknown_preset", preset=preset_name)
        else:
            loop.state.preset_name = preset.name
            loop.state.model_tier = preset.model_tier
            loop.state.stage_canon_proposals = preset.stage_canon_proposals
    char = get_character(character_id)
    if char:
        # player_persona is "name — description" (or just the name), as start_conversation built it.
        user_name = loop.state.player_persona.split(" — ", 1)[0].strip() or None
        loop.state.character_card = render_character_card(char, user_name)
    _cache_loop(conversation_id, loop)
    return loop


async def _resolve_loop(conversation_id: str, character_id: str | None) -> Any:
    """Return the live loop for this conversation, rebuilding it if needed.

    Loops are process-local, so a backend restart orphans active sessions.
    When the loop is missing and character_id is provided (or derivable from
    the conversation's client_session), the loop is rebuilt from the persisted
    MongoDB transcript (resume). Raises KeyError when no loop can be found.
    """
    cached = _LOOPS.get(conversation_id)
    if cached is not None and not _loop_matches_character(cached, character_id):
        raise KeyError(conversation_id)
    if cached is not None:
        return cached

    resolved_char_id = character_id
    if not resolved_char_id:
        with contextlib.suppress(Exception):
            from monitor_data.db.mongodb import get_mongodb_client

            doc = (
                get_mongodb_client()
                .get_collection("conversations")
                .find_one(
                    {"conversation_id": conversation_id},
                    {"client_session": 1},
                )
            )
            if isinstance(doc, dict):
                cs = doc.get("client_session")
                if isinstance(cs, dict) and cs.get("character_id"):
                    resolved_char_id = str(cs["character_id"])
    if resolved_char_id:
        loop = await resume_conversation(resolved_char_id, conversation_id)
        if loop is not None:
            return loop
    raise KeyError(conversation_id)


async def _persist_outbox(conversation_id: str, loop: Any) -> None:
    """Durable outbox: persist accumulated proposals onto the conversation doc.

    Runs after every turn so a mid-session crash doesn't lose them (they used
    to live only in loop memory until close). Restored on resume.
    """
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        outbox = (
            [] if getattr(loop, "_closed", False) is True else list(getattr(loop.state, "pending_proposals", []) or [])
        )
        get_mongodb_client().get_collection("conversations").update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    "pending_proposals": outbox,
                    # Per-conversation lorebook switches from the character's directives.
                    "lorebook_overrides": dict(getattr(loop.state, "lorebook_overrides", {}) or {}),
                }
            },
        )
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _persist_outbox)
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
    from monitor_agents.loops.conversation_loop import ConversationClosedError

    async with _get_conversation_lock(conversation_id):
        loop = await _resolve_loop(conversation_id, character_id)

        # The loop's state.universe_id is the incarnation's universe; we forward
        # the cross-incarnation flag by setting a transient attribute on the
        # loop state (read by NPCVoice via the conversation_loop wrapper).
        if include_cross_incarnation and getattr(loop, "state", None) is not None:
            loop.state.include_cross_incarnation = True

        try:
            responses = await loop.step(text)
        except ConversationClosedError as exc:
            pop_loop(conversation_id)
            raise KeyError(conversation_id) from exc
        except Exception:
            with contextlib.suppress(Exception):
                from monitor_data.db.mongodb import get_mongodb_client

                get_mongodb_client().get_collection("conversations").update_one(
                    {"conversation_id": conversation_id},
                    {"$set": {"turns": list(getattr(loop.state, "turns", []) or [])}},
                )
            raise
        finally:
            # Always reset the transient flag, even if step() raised.
            if include_cross_incarnation and getattr(loop, "state", None) is not None:
                loop.state.include_cross_incarnation = False

        await _persist_outbox(conversation_id, loop)

        if getattr(loop, "_closed", False) is True:
            pop_loop(conversation_id)

        reply = responses[0] if responses else {}
        return {
            "text": reply.get("text", ""),
            "emotional_state": reply.get("emotional_state"),
            "relationship_snapshot": reply.get("relationship_snapshot", {}),
        }


async def send_message_stream(
    conversation_id: str,
    text: str,
    include_cross_incarnation: bool = False,
    character_id: str | None = None,
) -> Any:
    """Yield the reply to one player line as it streams, then persist.

    Streaming send path (Phase 7): the loop's NPC memory writes for this turn
    are deferred and flushed after the final chunk — "memory writes happen
    after the stream completes". The outbox bookkeeping runs at the end too.

    Yields typed events: ``{"type": "token", "text": ...}`` per chunk of the
    reply, then one ``{"type": "done", ...}`` carrying the emotional /
    relationship read. Always ends by flushing deferred memory writes, even
    when the consumer stops early — the exchange happened, so the character
    must remember it.

    Raises KeyError up front when the conversation is unknown/inactive, and
    propagates generation errors before the first chunk.
    """
    from monitor_agents.loops.conversation_loop import ConversationClosedError

    async def _generator() -> Any:
        async with _get_conversation_lock(conversation_id):
            loop = await _resolve_loop(conversation_id, character_id)

            if include_cross_incarnation and getattr(loop, "state", None) is not None:
                loop.state.include_cross_incarnation = True

            try:
                responses = await loop.step(text, defer_memory_writes=True)
            except ConversationClosedError as exc:
                pop_loop(conversation_id)
                raise KeyError(conversation_id) from exc
            except Exception:
                with contextlib.suppress(Exception):
                    from monitor_data.db.mongodb import get_mongodb_client

                    get_mongodb_client().get_collection("conversations").update_one(
                        {"conversation_id": conversation_id},
                        {"$set": {"turns": list(getattr(loop.state, "turns", []) or [])}},
                    )
                raise
            finally:
                if include_cross_incarnation and getattr(loop, "state", None) is not None:
                    loop.state.include_cross_incarnation = False

            reply = responses[0] if responses else {}
            reply_text = str(reply.get("text") or "")
            try:
                for chunk in _stream_chunks(reply_text):
                    yield {"type": "token", "text": chunk}
                yield {
                    "type": "done",
                    "conversation_id": conversation_id,
                    "text": reply_text,
                    "emotional_state": reply.get("emotional_state"),
                    "relationship_snapshot": reply.get("relationship_snapshot", {}),
                }
            finally:
                # Memory writes happen after the stream completes. A flush
                # failure is recorded — never silently dropped.
                try:
                    await loop.flush_memory_writes()
                except Exception as exc:  # noqa: BLE001  # reason: recorded below, then the stream still finishes
                    log.warning("conversation_memory_flush_failed", conversation_id=conversation_id, exc_info=True)
                    from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
                    from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource

                    await RoleplayErrorRecorder.record(
                        source=RoleplayErrorSource.CHARACTER_CONVERSATION,
                        category=RoleplayErrorCategory.UNKNOWN,
                        message=str(exc),
                        fatal=False,
                        conversation_id=conversation_id,
                    )
                await _persist_outbox(conversation_id, loop)
                if getattr(loop, "_closed", False) is True:
                    pop_loop(conversation_id)

    return _generator()


def _stream_chunks(text: str) -> list[str]:
    """Split a generated reply into small chunks for token-style streaming."""
    if not text:
        return []
    words = text.split(" ")
    chunks: list[str] = []
    for i, word in enumerate(words):
        chunks.append(word if i == len(words) - 1 else word + " ")
    return chunks


async def redistill_conversation(character_id: str, conversation_id: str, *, force: bool = False) -> dict[str, Any]:
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
    async with _get_conversation_lock(conversation_id):
        cached = _LOOPS.get(conversation_id)
        if cached is not None and not _loop_matches_character(cached, character_id):
            return {"ended": False, "proposals": 0}

        loop = cached
        if loop is None and character_id:
            loop = await resume_conversation(character_id, conversation_id, allow_at_limit=True)
        if loop is None:
            return {"ended": True, "proposals": 0}
        proposals: list[Any] = []
        try:
            proposals = await loop.finish()
            return {"ended": True, "proposals": len(proposals or [])}
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in end_conversation)
            log.warning("conversation_finish_failed", conversation_id=conversation_id, exc_info=True)
            try:
                from monitor_data.db.mongodb import get_mongodb_client

                state = getattr(loop, "state", None)
                remaining = getattr(state, "pending_proposals", None)
                if isinstance(remaining, list):
                    get_mongodb_client().get_collection("conversations").update_one(
                        {"conversation_id": conversation_id},
                        {"$set": {"pending_proposals": list(remaining)}},
                    )
            except Exception:  # noqa: BLE001  # reason: best-effort recovery outbox update
                log.debug("conversation_recovery_outbox_update_failed", exc_info=True)
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


# ---------------------------------------------------------------------------
# "What this character remembers about you" (Phase 7, task 5)
# ---------------------------------------------------------------------------


def _character_entity_ids(char: dict[str, Any]) -> list[str]:
    """Every entity id this character has incarnated as (any universe)."""
    ids: list[str] = []
    if char.get("entity_id"):
        ids.append(str(char["entity_id"]))
    for version in char.get("versions") or []:
        eid = str(version.get("entity_id") or "")
        if eid and eid not in ids:
            ids.append(eid)
    return ids


def list_memories_about_you(
    character_id: str,
    *,
    universe_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """What this character remembers about the user, newest first.

    A memory is "about you" when it was written during a conversation with
    the player (``metadata.conversation_id`` is set — the shape
    ``NPCVoice._write_npc_memory`` writes). Scoped to the character's
    incarnations; pass universe_id to narrow to one incarnation.
    """
    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")
    entity_ids = _character_entity_ids(char)
    if not entity_ids:
        return {"memories": [], "total": 0}

    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("character_memories")
    query: dict[str, Any] = {
        "entity_id": {"$in": entity_ids},
        "metadata.conversation_id": {"$exists": True},
    }
    if universe_id:
        query["universe_id"] = str(universe_id)
    total = coll.count_documents(query)
    cursor = coll.find(query).sort("created_at", -1).limit(max(1, min(int(limit), 100)))
    memories = [
        {
            "id": str(m.get("memory_id", "")),
            "text": m.get("text", ""),
            "importance": m.get("importance", 0.0),
            "entity_id": str(m.get("entity_id", "")),
            "universe_id": str(m.get("universe_id", "")),
            "conversation_id": str((m.get("metadata") or {}).get("conversation_id", "")),
            "created_at": m["created_at"].isoformat()
            if hasattr(m.get("created_at"), "isoformat")
            else str(m.get("created_at", "")),
        }
        for m in cursor
    ]
    return {"memories": memories, "total": total}


def delete_character_memory(character_id: str, memory_id: str) -> bool:
    """Delete one memory this character holds (view + recall forget it).

    Verifies the memory belongs to one of the character's incarnations first,
    then deletes the MongoDB document and its Qdrant vector so neither the
    view nor semantic recall can surface it again.
    """
    import uuid as _uuid

    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")
    entity_ids = _character_entity_ids(char)

    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("character_memories")
    doc = coll.find_one({"memory_id": str(memory_id)})
    if not doc or str(doc.get("entity_id", "")) not in entity_ids:
        return False

    from monitor_data.tools.mongodb_tools.memories import mongodb_delete_memory

    deleted = mongodb_delete_memory(_uuid.UUID(str(memory_id)))
    if deleted:
        # Caller-owned vector cleanup (mongodb_delete_memory's contract):
        # without it, semantic recall would keep surfacing a ghost hit.
        try:
            from monitor_data.schemas.vectors import VectorDeleteRequest
            from monitor_data.tools.qdrant_tools import qdrant_delete

            qdrant_delete(VectorDeleteRequest(collection="memories", id=_uuid.UUID(str(memory_id))))
        except Exception:  # noqa: BLE001  # reason: the Mongo doc is gone; recall hydrates from it and skips textless hits
            log.warning("memory_vector_delete_failed", memory_id=memory_id, exc_info=True)
        _increment_memory_count(character_id, delta=-1)
    return deleted


def _increment_memory_count(character_id: str, delta: int) -> None:
    """Keep the character doc's memory_count roughly in sync (display only)."""
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        get_mongodb_client().get_collection("characters").update_one(
            {"id": character_id},
            {"$max": {"memory_count": 0}, "$inc": {"memory_count": delta}},
        )
    except Exception:  # noqa: BLE001  # reason: counter is display-only
        log.debug("memory_count_update_failed", exc_info=True)


# ---------------------------------------------------------------------------
# One-click start with a universe character (Phase 7, task 1)
# ---------------------------------------------------------------------------


async def start_universe_character_chat(
    entity_id: str,
    *,
    persona_character_id: str | None = None,
    owner_id: str | None = None,
) -> dict[str, Any]:
    """One action: open a chat with any character in a universe.

    Finds (or creates) the standalone card linked to this universe NPC and
    opens a DIRECT conversation on the SAME entity — no duplicate
    incarnation, no interview, no mode choice. The card's first_message (when
    the NPC has one) is the opening line.
    """
    import uuid as _uuid

    from monitor_data.tools.neo4j_tools.entities import neo4j_get_entity

    entity = neo4j_get_entity(_uuid.UUID(entity_id))
    if entity is None:
        raise ValueError(f"Character entity {entity_id} not found")
    entity_dict = entity.model_dump() if hasattr(entity, "model_dump") else dict(entity)
    etype = str(entity_dict.get("entity_type", "")).lower()
    if etype not in ("character", "npc", "pc", "monster"):
        raise ValueError(f"Entity {entity_id} is not a character (entity_type={etype!r})")
    universe_id = str(entity_dict.get("universe_id") or "")
    if not universe_id:
        raise ValueError(f"Entity {entity_id} has no universe to chat in")

    from monitor_data.db.mongodb import get_mongodb_client

    coll = get_mongodb_client().get_collection("characters")
    char = coll.find_one({"$or": [{"entity_id": str(entity_id)}, {"versions.entity_id": str(entity_id)}]})
    if char is None:
        name = str(entity_dict.get("name") or "Unknown")
        char = create_character(
            {
                "name": name[:200],
                "description": str(entity_dict.get("description") or ""),
                "personality": str(entity_dict.get("properties", {}).get("personality") or ""),
                "gm_notes": str(entity_dict.get("properties", {}).get("gm_notes") or ""),
                "entity_id": str(entity_id),
                "source_universe_id": universe_id,
                "owner_id": owner_id,
            }
        )
        log.info("universe_character_card_created", entity_id=entity_id, character_id=char["id"])

    result = await start_conversation(
        str(char["id"]),
        universe_id=universe_id,
        persona_character_id=persona_character_id,
        preset="light",
    )
    return result


# ---------------------------------------------------------------------------
# Graduate a light chat into a guided-start campaign (Phase 7, task 6)
# ---------------------------------------------------------------------------

_GRADUATE_MEMORY_CARRY_LIMIT = 50


def carry_memories_to_incarnation(
    character_id: str,
    entity_id: str,
    universe_id: str,
    *,
    limit: int = _GRADUATE_MEMORY_CARRY_LIMIT,
) -> int:
    """Copy the character's conversation memories into one incarnation.

    Graduation hands the character's memories to the campaign: every "about
    you" memory from other incarnations is copied to (entity_id, universe_id)
    so the campaign's incarnation recalls them. Idempotent — each copy is
    stamped ``metadata.graduated_from`` with the source memory id and skipped
    on re-graduation. Returns how many memories were carried.
    """
    import uuid as _uuid

    from monitor_data.db.mongodb import get_mongodb_client
    from monitor_data.schemas.memories import MemoryCreate
    from monitor_data.tools.mongodb_tools.memories import mongodb_create_memory

    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")
    source_ids = [eid for eid in _character_entity_ids(char) if eid != str(entity_id)]
    if not source_ids:
        # Graduating in place (same incarnation): its memories are already
        # bound to this entity — nothing to carry.
        return 0
    coll = get_mongodb_client().get_collection("character_memories")
    query: dict[str, Any] = {
        "entity_id": {"$in": source_ids},
        "metadata.conversation_id": {"$exists": True},
    }
    existing_copies = {
        str(m.get("metadata", {}).get("graduated_from", ""))
        for m in coll.find(
            {"entity_id": str(entity_id), "metadata.graduated_from": {"$exists": True}},
            {"metadata.graduated_from": 1},
        )
    }
    carried = 0
    for mem in coll.find(query).sort("created_at", -1).limit(max(1, limit)):
        source_memory_id = str(mem.get("memory_id", ""))
        if not source_memory_id or source_memory_id in existing_copies:
            continue
        metadata = dict(mem.get("metadata") or {})
        metadata["graduated_from"] = source_memory_id
        metadata["graduated_to_universe"] = str(universe_id)
        try:
            mongodb_create_memory(
                MemoryCreate(
                    universe_id=_uuid.UUID(str(universe_id)),
                    entity_id=_uuid.UUID(str(entity_id)),
                    text=str(mem.get("text") or " ")[:5000] or " ",
                    importance=float(mem.get("importance", 0.5) or 0.5),
                    emotional_valence=float(mem.get("emotional_valence", 0.0) or 0.0),
                    certainty=float(mem.get("certainty", 1.0) or 1.0),
                    metadata=metadata,
                )
            )
            carried += 1
        except Exception:  # noqa: BLE001  # reason: one bad memory must not block the rest
            log.warning("memory_carry_failed", memory_id=source_memory_id, exc_info=True)
    _increment_memory_count(character_id, delta=carried)
    return carried


async def graduate_prepare(
    character_id: str,
    *,
    universe_id: str | None = None,
    tone: str | None = None,
) -> dict[str, Any]:
    """Step 1 of graduation: incarnation + the guided start's opening question.

    Calls the Phase 2 guided-start entry points — ``WorldSeed`` for 2-4
    concrete ways to begin and ``session_zero.ask_start_options_question`` for
    the question that presents them — so the light chat hands off to the same
    guided start a new campaign gets.
    """
    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")
    target_universe = (
        str(universe_id)
        if universe_id
        else str(char.get("default_universe_id") or char.get("source_universe_id") or "")
    ) or None
    backing = await ensure_character_backed(character_id, universe_id=target_universe)

    from monitor_agents.session_zero import ask_start_options_question
    from monitor_agents.world_seed import WorldSeed

    start_options: list[dict[str, Any]] = []
    seed_source = "none"
    try:
        seed_result = await WorldSeed().generate_start_options(
            universe_id=str(backing["universe_id"]),
            system_name=None,
            tone=tone,
        )
        start_options = [option.chip_dict() for option in seed_result.options]
        seed_source = seed_result.source
    except Exception as exc:  # noqa: BLE001  # reason: recorded; the graduate flow continues without options
        log.warning("graduate_start_options_failed", exc_info=True)
        from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
        from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource

        await RoleplayErrorRecorder.record(
            source=RoleplayErrorSource.CHARACTER_CONVERSATION,
            category=RoleplayErrorCategory.LLM,
            message=f"graduate start options failed: {exc}",
            fatal=False,
            conversation_id=None,
        )

    question_text = "How would you like this story to begin?"
    suggested_answers: list[str] = []
    if start_options:
        question = await ask_start_options_question(
            system_name=str(char.get("name") or ""),
            tone=tone or "dramatic",
            start_options=start_options,
            world_material=str(char.get("description") or "")[:2000],
        )
        question_text = str(question.question_text)
        suggested_answers = [str(a) for a in question.suggested_answers]

    return {
        "character_id": character_id,
        "universe_id": str(backing["universe_id"]),
        "entity_id": str(backing["entity_id"]),
        "version_id": str(backing["version_id"]),
        "start_options": start_options,
        "start_options_source": seed_source,
        "question": question_text,
        "suggested_answers": suggested_answers,
    }


async def graduate_to_campaign(
    character_id: str,
    *,
    universe_id: str | None = None,
    persona_character_id: str | None = None,
    start_answer: str = "",
    start_options: list[dict[str, Any]] | None = None,
    question_text: str = "",
    tone: str | None = None,
) -> dict[str, Any]:
    """Step 2 of graduation: carry everything and hand off to the guided start.

    Resolves the player's start choice via ``session_zero.resolve_start_choice``,
    carries the character's memories into the chosen universe's incarnation,
    and returns the exact guided-start session payload (for ``POST /api/chat``)
    with the character, persona and chosen start in hand.
    """
    char = get_character(character_id)
    if not char:
        raise ValueError(f"Character {character_id} not found")
    if persona_character_id:
        persona = get_character(persona_character_id)
        if not persona:
            raise ValueError(f"Persona {persona_character_id} not found")
        if not persona.get("is_ooc_persona"):
            raise ValueError(f"Character {persona_character_id} is not a persona (is_ooc_persona=false)")

    target_universe = (
        str(universe_id)
        if universe_id
        else str(char.get("default_universe_id") or char.get("source_universe_id") or "")
    ) or None
    backing = await ensure_character_backed(character_id, universe_id=target_universe)

    from monitor_agents.session_zero import resolve_start_choice

    options = [o for o in (start_options or []) if isinstance(o, dict)]
    choice = await resolve_start_choice(
        question_text=question_text or "How would you like this story to begin?",
        options=options,
        answer=start_answer or "surprise me",
    )

    memories_carried = await asyncio.to_thread(
        carry_memories_to_incarnation,
        character_id,
        str(backing["entity_id"]),
        str(backing["universe_id"]),
    )

    premise = (choice.free_answer or "").strip()
    if not premise and choice.option_id:
        picked = next((o for o in options if str(o.get("option_id")) == str(choice.option_id)), None)
        if picked:
            premise = str(picked.get("summary") or picked.get("hook") or picked.get("title") or "")
    if not premise:
        premise = f"A campaign with {char['name']}."

    session_create = {
        "title": f"{char['name']} — new campaign",
        "mode": "autonomous_gm",
        "universe_id": str(backing["universe_id"]),
        "selected_character_id": character_id,
        "persona_id": persona_character_id,
        "story_premise": premise,
        "tone": tone or "dramatic",
    }
    return {
        "character_id": character_id,
        "universe_id": str(backing["universe_id"]),
        "entity_id": str(backing["entity_id"]),
        "version_id": str(backing["version_id"]),
        "chosen": choice.model_dump(mode="json"),
        "story_premise": premise,
        "memories_carried": memories_carried,
        "session_create": session_create,
    }
