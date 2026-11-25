"""Acting-owner context and tool-boundary ownership assertions (multi-tenancy).

LAYER: 1 (data-layer)
IMPORTS FROM: monitor_data.db, external libraries only
CALLED BY: UI backend (binds the owner per request/WS turn), agents loops
    (bind the session owner around a turn), and the write tools (assert it).

Phase 6 left ownership enforced at the HTTP layer only. This module carries
the acting owner from the UI into the agent and data layers and gives the
write tools a fail-closed assertion against the Postgres ownership registry
(``worlds.owner_id`` / ``multiverses.owner_id``, plan D3).

Rules:
- The owner lives in a ``contextvars.ContextVar`` so all three layers can
  read it without breaking the layer rules. ``asyncio.to_thread`` /
  ``anyio.to_thread`` copy the context, and LangGraph runs nodes under
  ``copy_context()``, so the value reaches the tools called from loop nodes.
  Where the context does not cross (``run_coroutine_threadsafe`` background
  loops, plain threads), callers capture the owner first and pass it
  explicitly as ``expected_owner_id``.
- No owner in context (auth-disabled local mode, scripts, ingestion workers,
  tests) means NO assertion: existing behavior is unchanged there.
- With an owner bound, a write whose target universe does not resolve to
  that owner is refused with :class:`OwnerViolationError` (fail closed —
  a missed HTTP guard cannot leak a foreign write).
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

_owner_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("monitor_owner_id", default=None)


class OwnerViolationError(PermissionError):
    """Typed refusal: the write targets a universe the acting owner does not own.

    The HTTP layer maps this to the generic 404 (plan D4: never reveal the
    existence of a foreign resource).
    """


def get_owner_id() -> str | None:
    """The acting owner's user id (string form), or ``None`` when unbound."""
    return _owner_id_var.get()


def set_owner_id(owner_id: str | UUID | None) -> contextvars.Token[str | None]:
    """Bind (or with ``None``, unbind) the acting owner for this context."""
    return _owner_id_var.set(str(owner_id) if owner_id is not None else None)


@contextmanager
def bind_owner(owner_id: str | UUID | None) -> Iterator[None]:
    """Bind the acting owner for the duration of the block, then restore."""
    token = set_owner_id(owner_id)
    try:
        yield
    finally:
        _owner_id_var.reset(token)


@contextmanager
def owner_scope(owner_id: str | UUID | None) -> Iterator[None]:
    """Bind ``owner_id`` when one is given; leave the context untouched when None.

    Loop entry points wrap a turn with their stored session owner so tool
    assertions see it even outside an authenticated request, while a loop
    without an explicit owner keeps whatever the UI already bound.
    """
    if owner_id is None:
        yield
        return
    with bind_owner(owner_id):
        yield


def owner_scoped(fn: Any) -> Any:
    """Decorator: run the method under :func:`owner_scope` of ``self.owner_id``.

    A ``None`` owner (local mode, scripts, tests) leaves the context as-is,
    so unowned callers behave exactly as before.
    """
    import functools
    import inspect

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def _awrap(self: Any, *args: Any, **kwargs: Any) -> Any:
            with owner_scope(getattr(self, "owner_id", None)):
                return await fn(self, *args, **kwargs)

        return _awrap

    @functools.wraps(fn)
    def _wrap(self: Any, *args: Any, **kwargs: Any) -> Any:
        with owner_scope(getattr(self, "owner_id", None)):
            return fn(self, *args, **kwargs)

    return _wrap


def acting_owner(expected_owner_id: str | UUID | None = None) -> str | None:
    """The owner an assertion should check: explicit argument wins over context.

    ``None`` means "no assertion" (local mode, scripts, workers, tests).
    """
    if expected_owner_id is not None:
        return str(expected_owner_id)
    return get_owner_id()


# ---------------------------------------------------------------------------
# Universe resolution (sync — tool functions are sync and run in threads)
# ---------------------------------------------------------------------------


def universe_of_story(story_id: str | UUID) -> str | None:
    """Resolve a Story node's ``universe_id`` from Neo4j (``None`` if missing)."""
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (s:Story {id: $id}) RETURN s.universe_id AS uid",
        {"id": str(story_id)},
    )
    return rows[0]["uid"] if rows else None


def universe_of_entity(entity_id: str | UUID) -> str | None:
    """Resolve an Entity node's ``universe_id`` from Neo4j (``None`` if missing)."""
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (e:Entity {id: $id}) RETURN e.universe_id AS uid",
        {"id": str(entity_id)},
    )
    return rows[0]["uid"] if rows else None


def universe_of_scene(scene_id: str | UUID) -> str | None:
    """Resolve a scene's universe: the Mongo scene doc first, Neo4j as fallback."""
    from monitor_data.db.mongodb import get_mongodb_client

    doc = (
        get_mongodb_client()
        .get_collection("scenes")
        .find_one(
            {"scene_id": str(scene_id)},
            {"universe_id": 1},
        )
    )
    if isinstance(doc, dict) and doc.get("universe_id"):
        return str(doc["universe_id"])
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (sc:Scene {id: $id}) RETURN sc.universe_id AS uid",
        {"id": str(scene_id)},
    )
    return rows[0]["uid"] if rows else None


def universe_of_memory(memory_id: str | UUID) -> str | None:
    """Resolve a memory document's universe (``None`` if missing)."""
    from monitor_data.db.mongodb import get_mongodb_client

    doc = (
        get_mongodb_client()
        .get_collection("character_memories")
        .find_one(
            {"memory_id": str(memory_id)},
            {"universe_id": 1},
        )
    )
    return str(doc["universe_id"]) if isinstance(doc, dict) and doc.get("universe_id") else None


# ---------------------------------------------------------------------------
# Registry assertion
# ---------------------------------------------------------------------------


def _registry_owns_universe(universe_id: str, owner_id: str) -> bool:
    """True iff the Postgres ownership registry assigns the universe to the owner."""
    from monitor_data.db._utils import run_sync
    from monitor_data.db.postgres import get_postgres_client

    row = run_sync(get_postgres_client().world_get_for_owner(str(universe_id), UUID(owner_id)))
    return row is not None


def _refuse(resource: str, reason: str) -> OwnerViolationError:
    return OwnerViolationError(f"refusing {resource} write: {reason}")


def assert_owner_match(
    *,
    resource: str,
    universe_id: str | UUID | None = None,
    direct_owner_id: str | UUID | None = None,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert the acting owner owns the target; no-op when no owner is bound.

    ``universe_id`` is checked against the Postgres registry;
    ``direct_owner_id`` is an owner recorded on the resource itself (rootless
    Mongo docs such as knowledge packs). At least one target must resolve to
    the owner, else the write is refused.
    """
    owner = acting_owner(expected_owner_id)
    if owner is None:
        return
    try:
        UUID(owner)
    except ValueError:
        raise _refuse(resource, "acting owner id is not a valid UUID") from None
    if direct_owner_id is not None and str(direct_owner_id) == owner:
        return
    if universe_id is not None and _registry_owns_universe(str(universe_id), owner):
        return
    raise _refuse(resource, f"target is not owned by the acting owner ({owner})")


def assert_universe_write(
    universe_id: str | UUID | None,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a universe directly (e.g. ``MemoryCreate.universe_id``)."""
    if acting_owner(expected_owner_id) is None:
        return
    if universe_id is None:
        raise _refuse(resource, "write names no universe to verify")
    assert_owner_match(resource=resource, universe_id=universe_id, expected_owner_id=expected_owner_id)


def assert_story_write(
    story_id: str | UUID,
    *,
    resource: str,
    universe_id: str | UUID | None = None,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a story: resolve its universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_id if universe_id is not None else universe_of_story(story_id)
    if resolved is None:
        raise _refuse(resource, f"story {story_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def assert_scene_write(
    scene_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a scene: resolve its universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_of_scene(scene_id)
    if resolved is None:
        raise _refuse(resource, f"scene {scene_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def assert_entity_write(
    entity_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a world entity (character sheet, NPC profile)."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_of_entity(entity_id)
    if resolved is None:
        raise _refuse(resource, f"entity {entity_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def assert_memory_write(
    memory_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming an existing memory: resolve its universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_of_memory(memory_id)
    if resolved is None:
        raise _refuse(resource, f"memory {memory_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def assert_proposal_target_write(
    *,
    resource: str,
    scene_id: str | UUID | None = None,
    story_id: str | UUID | None = None,
    universe_id: str | UUID | None = None,
    content: dict[str, Any] | None = None,
    source: str | None = None,
    proposer: str | None = None,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a proposed-change write against its target (mirror of the UI's
    ``require_proposal_owner`` chain: scene → story → universe (direct or
    stamped on ``content``) → ingest job → knowledge pack → promoted
    character; anything else fails closed).
    """
    if acting_owner(expected_owner_id) is None:
        return
    if scene_id is not None:
        assert_scene_write(scene_id, resource=resource, expected_owner_id=expected_owner_id)
        return
    if story_id is not None:
        assert_story_write(story_id, resource=resource, expected_owner_id=expected_owner_id)
        return
    content_universe = (content or {}).get("universe_id") if isinstance(content, dict) else None
    target_universe = universe_id if universe_id is not None else content_universe
    if target_universe is not None:
        assert_universe_write(target_universe, resource=resource, expected_owner_id=expected_owner_id)
        return
    if source and source.startswith("ingestion_job:"):
        from monitor_data.tools.mongodb_tools import mongodb_get_ingestion_job

        job = mongodb_get_ingestion_job(UUID(source.split(":", 1)[1]))
        if job is None:
            raise _refuse(resource, "ingestion job not found")
        assert_universe_write(job.universe_id, resource=resource, expected_owner_id=expected_owner_id)
        return
    if source and source.startswith("knowledge_pack:"):
        from monitor_data.tools.mongodb_tools import mongodb_get_knowledge_pack

        pack = mongodb_get_knowledge_pack(UUID(source.split(":", 1)[1]))
        if pack is None:
            raise _refuse(resource, "knowledge pack not found")
        assert_owner_match(
            resource=resource,
            direct_owner_id=pack.owner_id,
            expected_owner_id=expected_owner_id,
        )
        return
    if proposer and proposer.startswith("character_promotion:"):
        from monitor_data.db.mongodb import get_mongodb_client

        card = (
            get_mongodb_client()
            .get_collection("characters")
            .find_one(
                {"id": proposer.split(":", 1)[1]},
                {"owner_id": 1},
            )
        )
        if not isinstance(card, dict) or not card.get("owner_id"):
            raise _refuse(resource, "promoted character not found")
        assert_owner_match(
            resource=resource,
            direct_owner_id=card["owner_id"],
            expected_owner_id=expected_owner_id,
        )
        return
    raise _refuse(resource, "write names no owned target to verify")


def assert_proposal_write(
    proposal_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming an existing proposal: resolve its target, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    from monitor_data.tools.mongodb_tools import mongodb_get_proposed_change

    proposal = mongodb_get_proposed_change(UUID(str(proposal_id)))
    if proposal is None:
        raise _refuse(resource, f"proposal {proposal_id} not found")
    assert_proposal_target_write(
        resource=resource,
        scene_id=proposal.scene_id,
        story_id=proposal.story_id,
        content=proposal.content,
        source=proposal.source,
        proposer=proposal.proposer,
        expected_owner_id=expected_owner_id,
    )


# ---------------------------------------------------------------------------
# Additional resource resolvers and assertions (UX-1 write-tool gaps)
# ---------------------------------------------------------------------------


def universe_of_play_session(session_id: str | UUID) -> str | None:
    """Resolve a PlaySession's ``universe_id`` from Mongo (``None`` if missing)."""
    from monitor_data.db.mongodb import get_mongodb_client

    doc = (
        get_mongodb_client()
        .get_collection("play_sessions")
        .find_one(
            {"session_id": str(session_id)},
            {"universe_id": 1},
        )
    )
    if isinstance(doc, dict) and doc.get("universe_id"):
        return str(doc["universe_id"])
    return None


def assert_play_session_write(
    session_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a play session: resolve its universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_of_play_session(session_id)
    if resolved is None:
        raise _refuse(resource, f"play session {session_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def universe_of_combat(encounter_id: str | UUID) -> str | None:
    """Resolve a combat encounter's universe through its scene (``None`` if missing)."""
    from monitor_data.db.mongodb import get_mongodb_client

    doc = (
        get_mongodb_client()
        .get_collection("combat_encounters")
        .find_one(
            {"encounter_id": str(encounter_id)},
            {"scene_id": 1},
        )
    )
    if not isinstance(doc, dict) or not doc.get("scene_id"):
        return None
    return universe_of_scene(doc["scene_id"])


def assert_combat_write(
    encounter_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a combat encounter: resolve scene → universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_of_combat(encounter_id)
    if resolved is None:
        raise _refuse(resource, f"combat encounter {encounter_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def assert_character_scope_write(
    character_id: str | UUID | None,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write scoped to a character, mirroring the HTTP
    ``require_playable_character`` chain: ``universe:<id>`` pseudo-characters
    resolve through the registry, standalone Mongo cards through their
    recorded ``owner_id``, and world entities through their universe.
    Anything else fails closed.
    """
    if acting_owner(expected_owner_id) is None:
        return
    if character_id is None or not str(character_id):
        raise _refuse(resource, "write names no character scope to verify")
    cid = str(character_id)
    if cid.startswith("universe:"):
        assert_universe_write(cid[len("universe:") :], resource=resource, expected_owner_id=expected_owner_id)
        return
    from monitor_data.db.mongodb import get_mongodb_client

    card = get_mongodb_client().get_collection("characters").find_one({"id": cid}, {"owner_id": 1})
    if isinstance(card, dict):
        card_owner = card.get("owner_id")
        if not card_owner:
            raise _refuse(resource, f"character card {cid} records no owner to verify")
        assert_owner_match(resource=resource, direct_owner_id=card_owner, expected_owner_id=expected_owner_id)
        return
    resolved = universe_of_entity(cid)
    if resolved is None:
        raise _refuse(resource, f"character {cid} resolves to no owner")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def assert_game_system_write(
    system_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a game system.

    - Missing system → refused (fail closed).
    - ``is_builtin`` seed systems → no assertion (shared, and the data layer
      already refuses modify/delete of them).
    - Systems stamped with ``owner_id`` (hand-authored via HTTP) → that owner
      must be the acting owner.
    - Ownerless systems (ingestion-created, pre-tenancy legacy) → no
      assertion; they stay shared until an owner stamps them.
    """
    if acting_owner(expected_owner_id) is None:
        return
    from monitor_data.db.mongodb import get_mongodb_client

    doc = (
        get_mongodb_client()
        .get_collection("game_systems")
        .find_one(
            {"system_id": str(system_id)},
            {"owner_id": 1, "is_builtin": 1},
        )
    )
    if not isinstance(doc, dict):
        raise _refuse(resource, f"game system {system_id} not found")
    if doc.get("is_builtin"):
        return
    system_owner = doc.get("owner_id")
    if not system_owner:
        return
    assert_owner_match(resource=resource, direct_owner_id=system_owner, expected_owner_id=expected_owner_id)


def universe_of_conversation(conversation_id: str | UUID) -> str | None:
    """Resolve a conversation transcript's ``universe_id`` (``None`` if missing)."""
    from monitor_data.db.mongodb import get_mongodb_client

    doc = (
        get_mongodb_client()
        .get_collection("conversations")
        .find_one(
            {"conversation_id": str(conversation_id)},
            {"universe_id": 1},
        )
    )
    if isinstance(doc, dict) and doc.get("universe_id"):
        return str(doc["universe_id"])
    return None


def assert_conversation_write(
    conversation_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a conversation: resolve its universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_of_conversation(conversation_id)
    if resolved is None:
        raise _refuse(resource, f"conversation {conversation_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def assert_session_entry_write(
    entry_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a Session Recorder entry write: the entry's chat session owner
    must be the acting owner (mirror of the HTTP
    ``require_session_log_entry_owner`` chain: entry → session → ``owner_id``).
    Missing entry, missing session, or an ownerless legacy session fails
    closed when an owner is bound.
    """
    if acting_owner(expected_owner_id) is None:
        return
    from monitor_data.db.mongodb import get_mongodb_client

    mongo = get_mongodb_client()
    entry = mongo.get_collection("chat_messages").find_one({"id": str(entry_id)}, {"session_id": 1})
    if not isinstance(entry, dict) or not entry.get("session_id"):
        raise _refuse(resource, f"session entry {entry_id} records no session to verify")
    session = mongo.get_collection("chat_sessions").find_one({"id": str(entry["session_id"])}, {"owner_id": 1})
    if not isinstance(session, dict) or not session.get("owner_id"):
        raise _refuse(resource, f"chat session {entry['session_id']} records no owner to verify")
    assert_owner_match(
        resource=resource,
        direct_owner_id=session["owner_id"],
        expected_owner_id=expected_owner_id,
    )


def assert_resolution_write(
    resolution_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a resolution: resolve its scene's universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    from monitor_data.db.mongodb import get_mongodb_client

    doc = (
        get_mongodb_client()
        .get_collection("resolutions")
        .find_one(
            {"resolution_id": str(resolution_id)},
            {"scene_id": 1},
        )
    )
    if not isinstance(doc, dict) or not doc.get("scene_id"):
        raise _refuse(resource, f"resolution {resolution_id} resolves to no scene")
    assert_scene_write(doc["scene_id"], resource=resource, expected_owner_id=expected_owner_id)


def assert_visual_identity_target_write(
    *,
    universe_id: str | UUID | None = None,
    entity_id: str | UUID | None = None,
    character_id: str | None = None,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a visual-identity write against its anchor (first present wins:
    universe → entity → character card/world entity); no anchor fails closed."""
    if acting_owner(expected_owner_id) is None:
        return
    if universe_id is not None:
        assert_universe_write(universe_id, resource=resource, expected_owner_id=expected_owner_id)
        return
    if entity_id is not None:
        assert_entity_write(entity_id, resource=resource, expected_owner_id=expected_owner_id)
        return
    if character_id is not None:
        assert_character_scope_write(character_id, resource=resource, expected_owner_id=expected_owner_id)
        return
    raise _refuse(resource, "write names no visual-identity anchor to verify")


def universe_of_party(party_id: str | UUID) -> str | None:
    """Resolve a Party node's universe through its story (``None`` if missing)."""
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (p:Party {id: $id}) RETURN p.story_id AS sid",
        {"id": str(party_id)},
    )
    if not rows or not rows[0].get("sid"):
        return None
    return universe_of_story(rows[0]["sid"])


def assert_party_write(
    party_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a party: resolve party → story → universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_of_party(party_id)
    if resolved is None:
        raise _refuse(resource, f"party {party_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)


def assert_rule_override_write(
    override_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a rule override: resolve its scope target, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    from monitor_data.db.mongodb import get_mongodb_client

    doc = (
        get_mongodb_client()
        .get_collection("rule_overrides")
        .find_one(
            {"override_id": str(override_id)},
            {"scope": 1, "scope_id": 1},
        )
    )
    if not isinstance(doc, dict):
        raise _refuse(resource, f"rule override {override_id} not found")
    scope = str(doc.get("scope") or "")
    scope_id = doc.get("scope_id")
    if not scope_id:
        raise _refuse(resource, f"rule override {override_id} names no scope target")
    if scope == "scene":
        assert_scene_write(scope_id, resource=resource, expected_owner_id=expected_owner_id)
        return
    # STORY scope (the default) and any unknown scope fall through to story.
    assert_story_write(scope_id, resource=resource, expected_owner_id=expected_owner_id)


def assert_multiverse_write(
    multiverse_id: str | UUID | None,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming a multiverse (``multiverses.owner_id`` registry).

    Mirrors the HTTP ``require_multiverse_owner`` chain: the multiverse is a
    Postgres registry root of its own (plan D3), not a Story node.
    """
    if acting_owner(expected_owner_id) is None:
        return
    if multiverse_id is None:
        raise _refuse(resource, "write names no multiverse to verify")
    owner = acting_owner(expected_owner_id)
    try:
        UUID(owner)
    except ValueError:
        raise _refuse(resource, "acting owner id is not a valid UUID") from None
    from monitor_data.db._utils import run_sync
    from monitor_data.db.postgres import get_postgres_client

    row = run_sync(get_postgres_client().multiverse_get_for_owner(str(multiverse_id), UUID(owner)))
    if row is None:
        raise _refuse(resource, f"multiverse {multiverse_id} is not owned by the acting owner ({owner})")


def universe_of_agenda(agenda_id: str | UUID) -> str | None:
    """Resolve an Agenda node's universe through its ``IN_UNIVERSE`` link."""
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (a:Agenda {id: $id})-[:IN_UNIVERSE]->(u) RETURN u.id AS uid",
        {"id": str(agenda_id)},
    )
    return rows[0]["uid"] if rows else None


def assert_agenda_write(
    agenda_id: str | UUID,
    *,
    resource: str,
    expected_owner_id: str | UUID | None = None,
) -> None:
    """Assert a write naming an agenda: resolve agenda → universe, then assert."""
    if acting_owner(expected_owner_id) is None:
        return
    resolved = universe_of_agenda(agenda_id)
    if resolved is None:
        raise _refuse(resource, f"agenda {agenda_id} resolves to no universe")
    assert_owner_match(resource=resource, universe_id=resolved, expected_owner_id=expected_owner_id)
