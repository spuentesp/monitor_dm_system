"""Turn a chosen start option into canon state — and back into a situation brief.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents (same layer).

Everything here writes through CanonKeeper: each change is staged as a
``ProposedChange`` and committed by ``CanonKeeper.bulk_commit_proposals``
("proposals accepted for the opening"). MongoDB-only artifacts (NPC
profiles) use the data-layer tools directly.

Public surface:

    result = await materialize_chosen_start(session)         # pre-play finish
    result = await prepare_starting_situation(universe_id)   # pack apply path
    brief = situation_brief(session)                         # opening narration
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_agents.world_seed.models import StartOption, WorldSeedResult
from monitor_agents.world_seed.seed import WorldSeed

logger = logging.getLogger(__name__)

OPENING_SOURCE_PREFIX = "world_seed:opening"


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _slug(value: str) -> str:
    return (value or "").strip()


def resolve_chosen_start(session: dict[str, Any]) -> StartOption | None:
    """Return the session's chosen start option, defaulting to the first one.

    The skip path ("Skip to play") never makes an explicit choice — picking
    the first option is its documented contract.
    """
    raw_options = session.get("start_options") or []
    if not raw_options:
        return None
    options = [StartOption.model_validate(item) for item in raw_options if isinstance(item, dict)]
    if not options:
        return None
    chosen_id = session.get("chosen_start_option_id")
    for option in options:
        if option.option_id == chosen_id:
            return option
    # No explicit choice (or a stale one) — the first option is the contract
    # for the skip path and for a player who never answered the start question.
    session["chosen_start_option_id"] = options[0].option_id
    return options[0]


def situation_brief(session: dict[str, Any]) -> str:
    """Text brief of the materialized situation, for the opening narration.

    Names the place, who is present, and what is happening, so the opening
    GM message can end on a prompt to act without inventing new content.
    """
    raw = session.get("materialized_start") or session.get("start_option")
    if not isinstance(raw, dict):
        return ""
    lines: list[str] = []
    location = _slug(str(raw.get("location") or ""))
    location_description = _slug(str(raw.get("location_description") or ""))
    if location:
        lines.append(f"PLACE: {location}" + (f" — {location_description}" if location_description else ""))
    npcs = raw.get("npcs") or []
    npc_lines = []
    for npc in npcs[:6]:
        if not isinstance(npc, dict):
            continue
        name = _slug(str(npc.get("name") or ""))
        if not name:
            continue
        want = _slug(str(npc.get("want") or ""))
        npc_lines.append(f"- {name}" + (f" (wants: {want})" if want else ""))
    if npc_lines:
        lines.append("PRESENT:\n" + "\n".join(npc_lines))
    hook = _slug(str(raw.get("hook") or ""))
    if hook:
        lines.append(f"AT STAKE: {hook}")
    role = _slug(str(raw.get("player_role") or ""))
    if role:
        lines.append(f"PLAYER'S SUGGESTED ROLE: {role}")
    return "\n".join(lines)


def situation_prompt_block(session: dict[str, Any]) -> str:
    """The starting situation as one prompt block, or ``""``.

    Single renderer for every opening prompt (join task 12): the pre-play
    finalize and the cold-open path used to hand-build this block with
    drifting wording.
    """
    brief = situation_brief(session)
    if not brief:
        return ""
    return "STARTING SITUATION (established state — narrate this, invent nothing that contradicts it):\n" + brief


# ─── proposal staging ────────────────────────────────────────────────────────


def _stage_proposal(
    *,
    universe_id: str,
    payload: dict[str, Any],
    proposal_type: str,
    change_type: str,
    story_id: str | None,
    source: str,
) -> dict[str, Any]:
    """Stage one ProposedChange and return the dict CanonKeeper commits.

    With a ``story_id`` the proposal is persisted through the canonical
    ``mongodb_create_proposed_change`` tool (DL-5) first. Without one (the
    pack prepare path runs before any story exists) the proposal exists
    only for the commit pass — same shape, same dispatcher.
    """
    proposal_id = uuid4()
    persisted: dict[str, Any] = {}
    if story_id:
        try:
            from monitor_data.schemas.base import ProposalType
            from monitor_data.schemas.proposed_changes import ProposedChangeCreate
            from monitor_data.tools.mongodb_tools import mongodb_create_proposed_change

            response = mongodb_create_proposed_change(
                ProposedChangeCreate(
                    story_id=_uuid(story_id),
                    change_type=ProposalType(change_type),
                    content=payload,
                    confidence=1.0,
                    proposer="WorldSeed",
                    source=source,
                    proposal_type=proposal_type,
                )
            )
            proposal_id = response.proposal_id
            persisted = {"proposal_id": str(proposal_id)}
        except Exception as exc:  # noqa: BLE001  # reason: a failed stage must not lose the opening; the commit dict is still returned (in _stage_proposal)
            logger.warning("world_seed: proposal staging failed (%s); committing un-persisted", exc)
    now = datetime.now(UTC).isoformat()
    return {
        "proposal_id": str(proposal_id),
        "universe_id": str(universe_id),
        "story_id": str(story_id) if story_id else None,
        "proposer": "WorldSeed",
        "change_type": change_type,
        "proposal_type": proposal_type,
        "content": payload,
        "payload": payload,
        "confidence": 1.0,
        "authority": "system",
        "status": "pending",
        "source": source,
        "created_at": now,
        "updated_at": None,
        **persisted,
    }


async def _commit_via_keeper(proposals: list[dict[str, Any]], *, universe_id: str) -> dict[str, Any]:
    """Commit staged proposals through CanonKeeper (the only Neo4j writer)."""
    if not proposals:
        return {"committed": 0, "errors": []}
    from monitor_agents.canonkeeper.agent import CanonKeeper

    keeper = CanonKeeper()
    return await keeper.bulk_commit_proposals(
        proposals,
        universe_id=_uuid(universe_id),
        source_ids=None,
        contradiction_check=False,
    )


# ─── materialization ─────────────────────────────────────────────────────────


def _option_proposals(
    option: StartOption,
    *,
    universe_id: str,
    story_id: str | None,
    pc_name: str | None,
    source: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build entity / agenda / thread+placement proposals for one option.

    Returns ``(entity_proposals, agenda_payloads, followup_proposals)`` —
    agenda owner ids are filled in after the entities are committed.
    """
    entity_proposals: list[dict[str, Any]] = []
    agenda_payloads: list[dict[str, Any]] = []
    followups: list[dict[str, Any]] = []

    location_payload = {
        "name": option.location,
        "entity_type": "location",
        "is_archetype": False,
        "description": option.location_description or option.summary,
        "properties": {"role": "start_location", "hook": option.hook},
        "canon_level": "canon",
    }
    entity_proposals.append(
        _stage_proposal(
            universe_id=universe_id,
            payload=location_payload,
            proposal_type="entity",
            change_type="entity",
            story_id=story_id,
            source=source,
        )
    )
    for npc in option.npcs:
        entity_proposals.append(
            _stage_proposal(
                universe_id=universe_id,
                payload={
                    "name": npc.name,
                    "entity_type": "character",
                    "is_archetype": False,
                    "description": npc.description,
                    "properties": {"role": "NPC", "want": npc.want},
                    "canon_level": "canon",
                },
                proposal_type="entity",
                change_type="entity",
                story_id=story_id,
                source=source,
            )
        )
        if npc.want:
            agenda_payloads.append(
                {
                    "npc_name": npc.name,
                    "title": f"{npc.name}'s drive",
                    "description": npc.want,
                    "agenda_type": "faction_goal",
                    "status": "active",
                    "total_segments": 6,
                    "current_segments": 0,
                }
            )

    for thread in option.threads:
        followups.append(
            _stage_proposal(
                universe_id=universe_id,
                payload={
                    "title": thread.title,
                    "description": thread.description,
                    "category": thread.category,
                    "urgency": thread.urgency,
                    "priority": "main" if thread.urgency in {"high", "critical"} else "minor",
                    "entity_names": [npc.name for npc in option.npcs] + [option.location],
                    "source_hint": source,
                },
                proposal_type="create_plot_thread",
                change_type="fact",
                story_id=story_id,
                source=source,
            )
        )

    if pc_name and option.location:
        followups.append(
            _stage_proposal(
                universe_id=universe_id,
                payload={
                    "from_entity": pc_name,
                    "rel_type": "located_in",
                    "to_entity": option.location,
                    "description": f"{pc_name} begins at {option.location}.",
                    "confidence": 1.0,
                },
                proposal_type="entity_relationship",
                change_type="relationship",
                story_id=story_id,
                source=source,
            )
        )
    return entity_proposals, agenda_payloads, followups


async def _entity_name_to_id(universe_id: str, name: str) -> str | None:
    from monitor_data.schemas.entities import EntityFilter
    from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities

    def _lookup() -> str | None:
        listing = neo4j_list_entities(EntityFilter(universe_id=_uuid(universe_id), limit=200))
        for entity in getattr(listing, "entities", []) or []:
            if (entity.name or "").strip().lower() == name.strip().lower():
                return str(entity.id)
        return None

    return await asyncio.to_thread(_lookup)


async def _persist_npc_profiles(
    option: StartOption,
    *,
    universe_id: str,
    source: str,
) -> list[dict[str, Any]]:
    """NPC profiles in MongoDB, keyed to the committed entity instances."""
    profiles: list[dict[str, Any]] = []
    try:
        from monitor_data.schemas.npc_profiles import NPCProfileCreate
        from monitor_data.tools.mongodb_tools import mongodb_create_npc_profile
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _persist_npc_profiles)
        logger.warning("world_seed: npc profile tools unavailable: %s", exc)
        return profiles

    for npc in option.npcs:
        entity_id = await _entity_name_to_id(universe_id, npc.name)
        if not entity_id:
            continue

        def _create(entity_id: str = entity_id, npc: Any = npc) -> Any:
            return mongodb_create_npc_profile(
                NPCProfileCreate(
                    entity_id=_uuid(entity_id),
                    values=[],
                    desires=[npc.want] if npc.want else [],
                    speech_style=None,
                    gm_notes=(npc.description or "")[:2000],
                    current_emotional_state="neutral",
                )
            )

        try:
            profile = await asyncio.to_thread(_create)
            profiles.append(
                {
                    "npc_name": npc.name,
                    "entity_id": entity_id,
                    "profile_id": str(getattr(profile, "profile_id", "")),
                    "source": source,
                }
            )
        except Exception as exc:  # noqa: BLE001  # reason: one duplicate profile must not lose the opening (in _persist_npc_profiles)
            logger.warning("world_seed: npc profile for %s failed: %s", npc.name, exc)
    return profiles


async def _commit_pack_story_proposals(
    *,
    universe_id: str,
    story_id: str | None,
) -> dict[str, Any]:
    """Commit the pack's agendas and plot threads that apply-time left behind.

    ``create_agenda`` proposals wait in PENDING on the apply/new-world path;
    ``create_plot_thread`` proposals commit as ``unresolved`` there because
    no story exists yet. Once the opening story exists both kinds belong to
    the starting situation, so they are committed here (the plot threads
    with the new story attached). Everything else stays pending review.
    """
    if not story_id:
        return {"committed": 0, "errors": []}
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        mongodb = get_mongodb_client()
        coll = mongodb.get_collection("proposed_changes")
        query = {
            "source": {"$regex": "^knowledge_pack:"},
            "proposal_type": {"$in": ["create_agenda", "create_plot_thread"]},
            "$or": [
                {"status": "pending"},
                {"status": "committed", "runtime_activation_status": "unresolved"},
            ],
        }
        if universe_id:
            query["universe_id"] = str(universe_id)
        docs = list(coll.find(query).limit(50))
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _commit_pack_story_proposals)
        logger.warning("world_seed: pack proposal query failed: %s", exc)
        return {"committed": 0, "errors": [str(exc)]}

    proposals: list[dict[str, Any]] = []
    for doc in docs:
        doc = dict(doc)
        doc.pop("_id", None)
        if doc.get("proposal_type") == "create_plot_thread":
            doc["story_id"] = str(story_id)
        proposals.append(doc)
    return await _commit_via_keeper(proposals, universe_id=universe_id)


async def materialize_chosen_start(
    session: dict[str, Any],
    *,
    story_id: str | None = None,
    universe_id: str | None = None,
) -> dict[str, Any]:
    """Turn the chosen start option into state for the opening.

    Creates the location and NPCs as entity instances (not archetypes) with
    NPC profiles and agendas, 2-3 plot threads, and the PC placed at the
    location — all through CanonKeeper as proposals accepted for the
    opening. Idempotent per session and option.
    """
    option = resolve_chosen_start(session)
    if option is None:
        return {}

    universe_id = str(universe_id or session.get("universe_id") or session.get("world_id") or "")
    story_id = str(story_id or session.get("story_id") or "") or None
    if not universe_id:
        return {"error": "no universe for start materialization"}

    already = session.get("materialized_start")
    if isinstance(already, dict) and already.get("option_id") == option.option_id:
        return already

    source = f"{OPENING_SOURCE_PREFIX}:{session.get('id') or story_id or universe_id}"
    pc_name = await _pc_name(session, universe_id)
    entity_proposals, agenda_payloads, followups = _option_proposals(
        option,
        universe_id=universe_id,
        story_id=story_id,
        pc_name=pc_name,
        source=source,
    )

    entity_result = await _commit_via_keeper(entity_proposals, universe_id=universe_id)
    profiles = await _persist_npc_profiles(option, universe_id=universe_id, source=source)

    agenda_proposals: list[dict[str, Any]] = []
    for agenda in agenda_payloads:
        owner_id = await _entity_name_to_id(universe_id, str(agenda.get("npc_name") or ""))
        payload = {key: value for key, value in agenda.items() if key != "npc_name"}
        payload["owner_id"] = owner_id
        agenda_proposals.append(
            _stage_proposal(
                universe_id=universe_id,
                payload=payload,
                proposal_type="create_agenda",
                change_type="fact",
                story_id=story_id,
                source=source,
            )
        )
    agenda_result = await _commit_via_keeper(agenda_proposals, universe_id=universe_id)
    followup_result = await _commit_via_keeper(followups, universe_id=universe_id)
    pack_result = await _commit_pack_story_proposals(universe_id=universe_id, story_id=story_id)

    result = {
        "option_id": option.option_id,
        "location": option.location,
        "npcs": [npc.model_dump() for npc in option.npcs],
        "hook": option.hook,
        "player_role": option.player_role,
        "generated": option.generated,
        "profiles": profiles,
        "committed": {
            "entities": entity_result.get("committed", 0),
            "agendas": agenda_result.get("committed", 0),
            "threads_and_placement": followup_result.get("committed", 0),
            "pack_story_items": pack_result.get("committed", 0),
        },
        "errors": [
            *entity_result.get("errors", []),
            *agenda_result.get("errors", []),
            *followup_result.get("errors", []),
            *pack_result.get("errors", []),
        ],
    }
    session["materialized_start"] = result
    session["start_option"] = option.model_dump(mode="json")
    return result


async def _pc_name(session: dict[str, Any], universe_id: str) -> str | None:
    """Exact name of the bound PC entity, for the placement relationship."""
    entity_id = session.get("character_id") or session.get("speaker_character_id")
    if not entity_id:
        name = str(session.get("speaker_label") or "").strip()
        return name or None
    try:
        from monitor_data.tools.neo4j_tools.entities import neo4j_get_entity

        entity_uuid = _uuid(entity_id)
        if entity_uuid is None:
            return None
        entity = await asyncio.to_thread(neo4j_get_entity, entity_uuid)
        return (getattr(entity, "name", None) or "").strip() or None
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _pc_name)
        logger.debug("world_seed: pc name resolve failed: %s", exc)
        return str(session.get("speaker_label") or "").strip() or None


# ─── pack apply path (task 6) ────────────────────────────────────────────────


async def prepare_starting_situation(
    universe_id: str | UUID,
    *,
    pack_ids: list[str] | None = None,
    system_name: str | None = None,
    tone: str | None = None,
) -> dict[str, Any]:
    """Run the seed against a universe and materialize its first option.

    Used after ``POST /packs/{id}/apply/new-world``: an ingested book gets
    somewhere to stand before any play session exists. Plot threads attach
    to a story and therefore wait for the first session's bootstrap, which
    also commits the pack's pending agendas and plot threads.
    """
    seed = WorldSeed()
    seed_result: WorldSeedResult = await seed.generate_start_options(
        universe_id=universe_id,
        pack_ids=pack_ids,
        system_name=system_name,
        tone=tone,
    )
    if not seed_result.options:
        return {"universe_id": str(universe_id), "options": [], "materialized": {}}

    first = seed_result.options[0]
    fake_session: dict[str, Any] = {
        "id": f"prepare:{universe_id}",
        "universe_id": str(universe_id),
        "start_options": [option.model_dump(mode="json") for option in seed_result.options],
        "chosen_start_option_id": first.option_id,
    }
    materialized = await materialize_chosen_start(fake_session, universe_id=str(universe_id))
    return {
        "universe_id": str(universe_id),
        "source": seed_result.source,
        "options": seed_result.to_chips(),
        "materialized": materialized,
    }
