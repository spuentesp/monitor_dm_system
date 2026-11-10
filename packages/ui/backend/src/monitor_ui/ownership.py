"""Ownership authorization helpers (multi-tenancy Phase 3).

Postgres is the authoritative ownership registry for Neo4j roots
(plan D3): ``multiverses.owner_id`` owns a Multiverse, ``worlds.owner_id``
owns a Universe, and all world-descendant data inherits through the
validated ``universe_id`` chain.

Rules (plan D4):
- A missing, unregistered, or foreign private ID returns the same generic
  404 as a nonexistent ID — private existence is never revealed.
- Ownership filters are applied in the storage query (ID predicate in
  Cypher / WHERE clause in SQL) BEFORE pagination; an empty owned-ID set
  yields an empty list, never an unscoped fallback.
- In ``MONITOR_AUTH_DISABLED`` local mode the fixed local account is admin
  and legacy data is backfilled to it, so checks pass (``via == "local"``).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID


from collections.abc import Awaitable, Callable, Iterable

from fastapi import Depends, HTTPException, Request, status

from monitor_data.db.postgres import PostgresClient

from monitor_ui.auth import Principal, get_current_user, get_postgres

_NOT_FOUND = "Not found"


def _is_local_mode(principal: Principal) -> bool:
    """Auth-disabled local development: the local admin retains full access.

    Fail closed: a principal without a ``via`` attribute raises
    AttributeError rather than being treated as local mode.
    """
    return principal.via == "local"


async def require_multiverse_owner(
    db: PostgresClient,
    principal: Principal,
    multiverse_id: str | UUID,
) -> dict[str, Any]:
    """Return the registry row iff the principal owns the multiverse, else 404."""
    if _is_local_mode(principal):
        return {"id": str(multiverse_id), "owner_id": principal.user_id}
    row = await db.multiverse_get_for_owner(_uuid_or_404(multiverse_id), principal.user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return row


async def require_universe_owner(
    db: PostgresClient,
    principal: Principal,
    universe_id: str | UUID | None,
) -> dict[str, Any]:
    """Return the registry row iff the principal owns the universe, else 404."""
    if universe_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if _is_local_mode(principal):
        return {"id": str(universe_id), "owner_id": principal.user_id}
    row = await db.world_get_for_owner(str(universe_id), principal.user_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return row


async def owned_multiverse_ids(db: PostgresClient, principal: Principal) -> list[str] | None:
    """IDs of multiverses the principal owns, for owner-scoped Neo4j lists.

    Returns ``None`` in auth-disabled local mode (unscoped). Otherwise a
    possibly-empty list: empty means the caller owns nothing and must get
    an empty result, NEVER an unscoped fallback.
    """
    if _is_local_mode(principal):
        return None
    rows = await db.multiverses_list(principal.user_id)
    return [str(r["id"]) for r in rows]


async def owned_world_ids(db: PostgresClient, principal: Principal) -> list[str] | None:
    """IDs of universes the principal owns, for owner-scoped Neo4j lists.

    Returns ``None`` in auth-disabled local mode (unscoped). Otherwise a
    possibly-empty list: empty means the caller owns nothing and must get
    an empty result, NEVER an unscoped fallback.
    """
    if _is_local_mode(principal):
        return None
    rows = await db.worlds_list(principal.user_id)
    return [str(r["id"]) for r in rows]


def _characters_collection() -> Any:
    """Mongo ``characters`` collection (standalone cards; rootless)."""
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client().get_collection("characters")


def character_owner_predicate(principal: Principal) -> dict[str, Any]:
    """Mongo predicate fragment scoping queries to the principal's cards.

    Empty in auth-disabled local mode (legacy cards belong to the local
    account). Never omit the predicate silently in enforced mode.
    """
    if _is_local_mode(principal):
        return {}
    return {"owner_id": str(principal.user_id)}


async def require_character_owner(principal: Principal, character_id: str) -> dict[str, Any]:
    """Return the character doc iff the principal owns it, else 404.

    The owner predicate is part of the Mongo query; foreign and missing IDs
    return the identical generic 404. Auth-disabled local mode: the local
    account owns all legacy cards.
    """
    if _is_local_mode(principal):
        return {"id": character_id, "owner_id": principal.user_id}
    query: dict[str, Any] = {"id": character_id, **character_owner_predicate(principal)}
    doc = _characters_collection().find_one(query)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return dict(doc)


async def _universe_of_story(story_id: str | UUID) -> str | None:
    """Resolve a Story node's universe_id from Neo4j (None if missing)."""
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (s:Story {id: $id}) RETURN s.universe_id AS uid",
        {"id": str(story_id)},
    )
    return rows[0]["uid"] if rows else None


async def _universe_of_scene(scene_id: str | UUID) -> str | None:
    """Resolve a Scene node's universe_id from Neo4j (None if missing)."""
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (sc:Scene {id: $id}) RETURN sc.universe_id AS uid",
        {"id": str(scene_id)},
    )
    return rows[0]["uid"] if rows else None


async def require_story_owner(db: PostgresClient, principal: Principal, story_id: str | UUID) -> None:
    """Stories inherit ownership through their universe chain (plan D3)."""
    if _is_local_mode(principal):
        return
    uid = await _universe_of_story(story_id)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_universe_owner(db, principal, uid)


async def require_scene_owner(db: PostgresClient, principal: Principal, scene_id: str | UUID) -> None:
    """Scenes inherit ownership through their universe (plan D3)."""
    if _is_local_mode(principal):
        return
    uid = await _universe_of_scene(scene_id)
    if uid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_universe_owner(db, principal, uid)


async def require_play_session_owner(db: PostgresClient, principal: Principal, session_id: str | UUID) -> None:
    """PlaySessions (Mongo) inherit ownership via their universe_id."""
    if _is_local_mode(principal):
        return
    from monitor_data.tools.mongodb_tools.play_sessions import mongodb_get_play_session

    session = mongodb_get_play_session(UUID(str(session_id)))
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_universe_owner(db, principal, session.universe_id)


async def require_asset_owner(db: PostgresClient, principal: Principal, asset: Any) -> None:
    """Generated assets authorize through their owning universe or character.

    An asset with neither linkage fails closed (404) — object-key knowledge
    is never sufficient (plan: authorize downloads via owning resource).
    """
    if _is_local_mode(principal):
        return
    uid = getattr(asset, "universe_id", None)
    if uid:
        await require_universe_owner(db, principal, uid)
        return
    cid = getattr(asset, "character_id", None)
    if cid:
        await require_character_owner(principal, str(cid))
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


def _chat_sessions_collection() -> Any:
    """Mongo ``chat_sessions`` collection (source of truth for session docs)."""
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client().get_collection("chat_sessions")


async def require_chat_session_owner(principal: Principal, session_id: str) -> dict[str, Any]:
    """Return the chat-session doc iff the principal owns it, else 404.

    The owner predicate is applied in the Mongo query itself — the Redis
    index is never trusted as proof of ownership. In auth-disabled local
    mode legacy sessions without ``owner_id`` belong to the local account.
    """
    col = _chat_sessions_collection()
    if _is_local_mode(principal):
        doc = col.find_one({"id": session_id})
    else:
        doc = col.find_one({"id": session_id, "owner_id": str(principal.user_id)})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return dict(doc)


# ---------------------------------------------------------------------------
# Common resource-ownership resolvers (single implementation, shared by all
# routers — see ``resource_route_guard`` below). Each resolver maps one
# path/query parameter name to the ownership check for that resource kind.
# Every resolver fails closed with the generic 404 for foreign/missing IDs.
# ---------------------------------------------------------------------------


async def require_character_scope(db: PostgresClient, principal: Principal, character_id: str) -> None:
    """Character scope, including ``universe:<id>`` pseudo-characters."""
    if character_id.startswith("universe:"):
        await require_universe_owner(db, principal, character_id[len("universe:") :])
    else:
        await require_character_owner(principal, character_id)


async def require_ingestion_job_owner(db: PostgresClient, principal: Principal, job_id: str) -> None:
    """Ingestion jobs are tenancy-checked by creator or owning universe.

    Fail closed: the job must exist and either ``owner_id`` is the caller or
    the job's universe resolves to a universe the caller owns. A foreign or
    missing job gets the generic 404.
    """
    if _is_local_mode(principal):
        return
    from monitor_data.tools.mongodb_tools import mongodb_get_ingestion_job

    job = mongodb_get_ingestion_job(UUID(str(job_id)))
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if getattr(job, "owner_id", None) == str(principal.user_id):
        return
    await require_universe_owner(db, principal, job.universe_id)


async def require_ingest_source_owner(db: PostgresClient, principal: Principal, source_id: str) -> None:
    """Ingest sources are job-backed or doc-backed and must belong to the caller.

    Mirrors the strict creator check ``ingest._require_source_owner`` uses.
    """
    if _is_local_mode(principal):
        return
    from monitor_data.schemas.ingestion_jobs import IngestionJobFilter
    from monitor_data.tools.mongodb_tools import mongodb_list_documents, mongodb_list_ingestion_jobs

    uid = _uuid_or_404(source_id)
    res = await asyncio.to_thread(
        mongodb_list_ingestion_jobs,
        IngestionJobFilter(source_id=UUID(uid), limit=1, sort_order="desc"),
    )
    if res.jobs:
        if getattr(res.jobs[0], "owner_id", None) != str(principal.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
        return
    docs = await asyncio.to_thread(mongodb_list_documents)
    doc = next((d for d in docs if str(getattr(d, "source_id", None)) == uid), None)
    if doc is None or getattr(doc, "owner_id", None) != str(principal.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


async def require_pack_owner(db: PostgresClient, principal: Principal, pack_id: str) -> None:
    """Knowledge packs are rootless Mongo docs carrying ``owner_id``."""
    if _is_local_mode(principal):
        return
    from monitor_data.tools.mongodb_tools import mongodb_get_knowledge_pack

    pack = mongodb_get_knowledge_pack(UUID(str(pack_id)))
    if pack is None or pack.owner_id != str(principal.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


async def require_party_owner(db: PostgresClient, principal: Principal, party_id: str) -> None:
    """Parties inherit ownership through their story's universe."""
    if _is_local_mode(principal):
        return
    from monitor_data.schemas.parties import PartyFilter
    from monitor_data.tools.neo4j_tools.parties import neo4j_list_parties

    rows = neo4j_list_parties(PartyFilter(party_id=UUID(str(party_id)), limit=1))
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_story_owner(db, principal, rows[0].story_id)


async def require_proposal_owner(db: PostgresClient, principal: Principal, proposal_id: str | UUID) -> None:
    """A proposal is owned through its scene/story, ingestion job, pack, or
    promoted character. Anything else fails closed (404)."""
    if _is_local_mode(principal):
        return
    from monitor_data.tools.mongodb_tools import (
        mongodb_get_ingestion_job,
        mongodb_get_knowledge_pack,
        mongodb_get_proposed_change,
    )

    proposal = mongodb_get_proposed_change(UUID(str(proposal_id)))
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if proposal.scene_id is not None:
        await require_scene_owner(db, principal, proposal.scene_id)
        return
    if proposal.story_id is not None:
        await require_story_owner(db, principal, proposal.story_id)
        return
    source = proposal.source or ""
    if source.startswith("ingestion_job:"):
        job = mongodb_get_ingestion_job(UUID(source.split(":", 1)[1]))
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
        await require_universe_owner(db, principal, job.universe_id)
        return
    if source.startswith("knowledge_pack:"):
        pack = mongodb_get_knowledge_pack(UUID(source.split(":", 1)[1]))
        if pack is None or pack.owner_id != str(principal.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
        return
    proposer = proposal.proposer or ""
    if proposer.startswith("character_promotion:"):
        await require_character_owner(principal, proposer.split(":", 1)[1])
        return
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


async def require_lorebook_entry_owner(db: PostgresClient, principal: Principal, entry_id: str) -> None:
    """Lorebook entries are scoped by their owning character/universe."""
    if _is_local_mode(principal):
        return
    from monitor_data.tools.mongodb_tools.lorebook_tools import mongodb_get_lorebook_entry

    entry = mongodb_get_lorebook_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_character_scope(db, principal, entry.character_id)


async def require_template_owner(db: PostgresClient, principal: Principal, template_id: str | UUID) -> Any:
    """Templates: entity templates belong to their universe; character
    templates (G-6, ``character_templates`` collection) are owner-predicated
    rootless docs. Returns the template in enforced mode, None in local mode
    (caller falls back to a direct load). Foreign/missing -> 404.
    """
    if _is_local_mode(principal):
        return None
    from monitor_data.tools.mongodb_tools.templates import mongodb_get_entity_template

    try:
        template = mongodb_get_entity_template(UUID(str(template_id)))
    except (ValueError, TypeError):
        template = None
    if template is not None:
        await require_universe_owner(db, principal, template.universe_id)
        return template
    from monitor_data.tools.mongodb_tools.character_templates import mongodb_get_character_template

    character_template = mongodb_get_character_template(str(template_id), owner_id=str(principal.user_id))
    if character_template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return character_template


async def require_asset_id_owner(db: PostgresClient, principal: Principal, asset_id: str) -> None:
    """Generated assets authorize through their owning universe or character."""
    if _is_local_mode(principal):
        return
    from monitor_data.tools.mongodb_tools.generated_assets import mongodb_get_generated_asset

    asset = mongodb_get_generated_asset(UUID(str(asset_id)))
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_asset_owner(db, principal, asset)


async def require_collection_owner(
    db: PostgresClient, principal: Principal, collection_id: str | UUID, *, write: bool = False
) -> Any:
    """Prompt collections: universe-bound -> universe owner; global/builtin
    -> readable by all, writable by admins only. Returns the collection in
    enforced mode, None in local mode."""
    if _is_local_mode(principal):
        return None
    from monitor_data.tools.mongodb_tools.prompt_collections import mongodb_get_prompt_collection
    from monitor_ui.auth import require_admin

    collection = mongodb_get_prompt_collection(UUID(str(collection_id)))
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    uid = getattr(collection, "universe_id", None)
    if uid is not None:
        await require_universe_owner(db, principal, uid)
    elif write or getattr(collection, "is_builtin", False):
        await require_admin(principal)
    return collection


async def require_random_table_owner(
    db: PostgresClient, principal: Principal, table: Any, *, write: bool = False
) -> None:
    """Random tables: universe-scoped -> universe owner; global tables are
    shared for reads, admin-only for writes."""
    if _is_local_mode(principal):
        return
    from monitor_ui.auth import require_admin

    uid = getattr(table, "universe_id", None)
    if uid is not None:
        await require_universe_owner(db, principal, uid)
    elif write:
        await require_admin(principal)


async def require_tone_library_owner(
    db: PostgresClient, principal: Principal, library: Any, *, write: bool = False
) -> None:
    """Tone libraries: universe-bound -> universe owner; global/builtin ->
    readable by all, writable by admins only."""
    if _is_local_mode(principal):
        return
    from monitor_ui.auth import require_admin

    uid = getattr(library, "universe_id", None)
    if uid is not None:
        await require_universe_owner(db, principal, uid)
    elif write:
        await require_admin(principal)


# Parameter name -> ownership resolver. ``resource_route_guard`` consults this
# table for every path/query parameter present on the incoming request, so a
# router opts into ownership enforcement simply by mounting with the guard —
# no per-router guard code.


def _uuid_or_404(value: str | UUID) -> str:
    """Canonical UUID string, or the generic 404 for a malformed ID."""
    try:
        return str(UUID(str(value)))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from None


def _universes_of_entities(entity_ids: list[str]) -> dict[str, str | None]:
    """Map Neo4j Entity ids to their universe_id (absent ids are omitted)."""
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (e:Entity) WHERE e.id IN $ids RETURN e.id AS id, e.universe_id AS uid",
        {"ids": entity_ids},
    )
    return {str(r["id"]): r["uid"] for r in rows}


async def require_entities_owner(db: PostgresClient, principal: Principal, entity_ids: Iterable[str | UUID]) -> None:
    """Every entity must exist and live in a universe the caller owns, else 404.

    All-or-nothing, so a mixed batch cannot act on (or probe for) foreign IDs.
    """
    if _is_local_mode(principal):
        return
    ids = sorted({_uuid_or_404(entity_id) for entity_id in entity_ids})
    if not ids:
        return
    universes = _universes_of_entities(ids)
    if any(universes.get(entity_id) is None for entity_id in ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    for universe_id in {str(uid) for uid in universes.values()}:
        await require_universe_owner(db, principal, universe_id)


async def require_entity_owner(db: PostgresClient, principal: Principal, entity_id: str | UUID) -> None:
    """World entities inherit ownership through their universe (plan D3)."""
    await require_entities_owner(db, principal, [entity_id])


async def _require_graph_node_owner(db: PostgresClient, principal: Principal, label: str, node_id: str) -> None:
    """Owner check for a universe-scoped Neo4j node (Fact/Axiom/Event/...).

    ``label`` is a code constant, never client input. Nodes without a
    universe_id, and missing nodes, get the generic 404.
    """
    if _is_local_mode(principal):
        return
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        f"MATCH (n:{label} {{id: $id}}) RETURN n.universe_id AS uid",
        {"id": _uuid_or_404(node_id)},
    )
    uid = rows[0]["uid"] if rows else None
    if uid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_universe_owner(db, principal, uid)


async def require_fact_owner(db: PostgresClient, principal: Principal, fact_id: str) -> None:
    await _require_graph_node_owner(db, principal, "Fact", fact_id)


async def require_axiom_owner(db: PostgresClient, principal: Principal, axiom_id: str) -> None:
    await _require_graph_node_owner(db, principal, "Axiom", axiom_id)


async def require_event_owner(db: PostgresClient, principal: Principal, event_id: str) -> None:
    await _require_graph_node_owner(db, principal, "Event", event_id)


async def require_relationship_owner(db: PostgresClient, principal: Principal, relationship_id: str) -> None:
    """Relationships inherit ownership through either endpoint entity."""
    if _is_local_mode(principal):
        return
    from monitor_data.db.neo4j import get_neo4j_client

    rows = get_neo4j_client().execute_read(
        "MATCH (r:Relationship {id: $id}) RETURN r.from_entity_id AS fid, r.to_entity_id AS tid",
        {"id": _uuid_or_404(relationship_id)},
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_entities_owner(db, principal, [rows[0]["fid"], rows[0]["tid"]])


async def require_sheet_owner(db: PostgresClient, principal: Principal, sheet_id: str) -> None:
    """Character sheets resolve through their Neo4j entity's universe."""
    if _is_local_mode(principal):
        return
    from monitor_data.db.mongodb import get_mongodb_client

    doc = get_mongodb_client().get_collection("character_sheets").find_one({"id": _uuid_or_404(sheet_id)})
    if doc is None or not doc.get("entity_id"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    await require_entity_owner(db, principal, doc["entity_id"])


async def require_playable_character(db: PostgresClient, principal: Principal, character_id: str) -> None:
    """A playable character is either a standalone Mongo card the caller owns
    OR a Neo4j world entity living in a universe the caller owns (Play setup,
    downtime, level-up all address characters this way). Foreign/missing -> 404.
    """
    if _is_local_mode(principal):
        return
    if character_id.startswith("universe:"):
        await require_universe_owner(db, principal, character_id[len("universe:") :])
        return
    try:
        await require_character_owner(principal, character_id)
        return
    except HTTPException:
        pass
    # Not a Mongo card — try as a Neo4j entity in an owned universe.
    await require_entity_owner(db, principal, character_id)


_SCOPE_RESOLVERS: dict[str, Callable[..., Awaitable[Any]]] = {
    "universe_id": require_universe_owner,
    "entity_id": require_entity_owner,
    "fact_id": require_fact_owner,
    "axiom_id": require_axiom_owner,
    "event_id": require_event_owner,
    "relationship_id": require_relationship_owner,
    "sheet_id": require_sheet_owner,
    "multiverse_id": require_multiverse_owner,
    "scene_id": require_scene_owner,
    "story_id": require_story_owner,
    "character_id": require_playable_character,
    "ingestion_job_id": require_ingestion_job_owner,
    "job_id": require_ingestion_job_owner,
    "source_id": require_ingest_source_owner,
    "proposal_id": require_proposal_owner,
    "pack_id": require_pack_owner,
    "party_id": require_party_owner,
    "entry_id": require_lorebook_entry_owner,
    "template_id": require_template_owner,
    "asset_id": require_asset_id_owner,
    "collection_id": require_collection_owner,
    "mv_id": require_multiverse_owner,
}


async def resource_route_guard(
    request: Request,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> None:
    """Common router-level guard: every route requires authentication, and any
    path/query parameter that names an ownable resource is owner-checked via
    the shared resolver table. Foreign or missing IDs get the same generic
    404. Auth-disabled local mode bypasses (the local admin owns legacy data).

    Usage: ``router = APIRouter(dependencies=[Depends(resource_route_guard)])``.
    """
    if _is_local_mode(principal):
        return
    params: dict[str, str] = dict(request.query_params)
    params.update(request.path_params)  # path params win over query params
    for name, resolve in _SCOPE_RESOLVERS.items():
        raw = params.get(name)
        if raw is not None:
            await resolve(db, principal, raw)
