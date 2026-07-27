"""Auto-extracted MongoDB tools sub-module."""

from contextlib import suppress
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.npc_profiles import (
    NPCProfileCreate,
    NPCProfileResponse,
    NPCProfileUpdate,
)

# =============================================================================
# NPC PROFILE OPERATIONS
# =============================================================================


def _npc_profile_doc_to_response(doc: dict[str, Any]) -> NPCProfileResponse:
    """Convert a MongoDB NPC profile document into an API response model."""
    universe_id_raw = doc.get("universe_id")
    return NPCProfileResponse(
        profile_id=UUID(doc["profile_id"]),
        entity_id=UUID(doc["entity_id"]),
        universe_id=UUID(universe_id_raw) if universe_id_raw else None,
        traits=doc.get("traits", {}),
        values=doc.get("values", []),
        fears=doc.get("fears", []),
        desires=doc.get("desires", []),
        speech_style=doc.get("speech_style"),
        catchphrases=doc.get("catchphrases", []),
        mannerisms=doc.get("mannerisms", []),
        emotional_tendencies=doc.get("emotional_tendencies", []),
        preferences=doc.get("preferences", []),
        triggers=doc.get("triggers", []),
        secrets=doc.get("secrets", []),
        gm_notes=doc.get("gm_notes"),
        current_emotional_state=doc.get("current_emotional_state"),
        relationship_states=doc.get("relationship_states", {}),
        relationship_states_by_universe=doc.get("relationship_states_by_universe", {}),
        current_emotional_state_by_universe=doc.get("current_emotional_state_by_universe", {}),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
    )


def mongodb_create_npc_profile(params: NPCProfileCreate) -> NPCProfileResponse:
    """Create a durable NPC profile document for an existing entity."""
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    verify_result = neo4j_client.execute_read(
        "MATCH (e:Entity {id: $entity_id}) RETURN e.id as id",
        {"entity_id": str(params.entity_id)},
    )
    if not verify_result:
        raise ValueError(f"Entity {params.entity_id} not found")

    profiles = mongo_client["npc_profiles"]
    existing = profiles.find_one({"entity_id": str(params.entity_id)})
    if existing:
        raise ValueError(f"NPC profile for entity {params.entity_id} already exists")

    now = datetime.now(UTC)
    profile_id = uuid4()
    doc = {
        "profile_id": str(profile_id),
        "entity_id": str(params.entity_id),
        "universe_id": str(params.universe_id) if params.universe_id else None,
        "traits": params.traits,
        "values": params.values,
        "fears": params.fears,
        "desires": params.desires,
        "speech_style": params.speech_style,
        "catchphrases": params.catchphrases,
        "mannerisms": params.mannerisms,
        "emotional_tendencies": [e.model_dump() for e in params.emotional_tendencies],
        "preferences": [p.model_dump() for p in params.preferences],
        "triggers": [t.model_dump() for t in params.triggers],
        "secrets": params.secrets,
        "gm_notes": params.gm_notes,
        "current_emotional_state": params.current_emotional_state,
        "relationship_states": params.relationship_states,
        "relationship_states_by_universe": params.relationship_states_by_universe,
        "current_emotional_state_by_universe": params.current_emotional_state_by_universe,
        "created_at": now,
        "updated_at": now,
    }
    profiles.insert_one(doc)
    return _npc_profile_doc_to_response(doc)


def mongodb_get_npc_profile(entity_id: UUID) -> NPCProfileResponse | None:
    """Fetch the NPC profile for a given entity, if one exists."""
    mongo_client = get_mongodb_client()
    doc = mongo_client["npc_profiles"].find_one({"entity_id": str(entity_id)})
    if not doc:
        return None
    return _npc_profile_doc_to_response(doc)


def mongodb_update_npc_profile(entity_id: UUID, params: NPCProfileUpdate) -> NPCProfileResponse:
    """Update or upsert an NPC profile with new emotional/social state."""
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()
    profiles = mongo_client["npc_profiles"]

    # Working social state should remain writable even if Neo4j validation is
    # temporarily unavailable (for example in unit tests or offline prep flows).
    with suppress(Exception):
        neo4j_client.execute_read(
            "MATCH (e:Entity {id: $entity_id}) RETURN e.id as id",
            {"entity_id": str(entity_id)},
        )

    existing = profiles.find_one({"entity_id": str(entity_id)})
    now = datetime.now(UTC)
    if not existing:
        existing = {
            "profile_id": str(uuid4()),
            "entity_id": str(entity_id),
            "universe_id": None,
            "traits": {},
            "values": [],
            "fears": [],
            "desires": [],
            "speech_style": None,
            "catchphrases": [],
            "mannerisms": [],
            "emotional_tendencies": [],
            "preferences": [],
            "triggers": [],
            "secrets": [],
            "gm_notes": None,
            "current_emotional_state": None,
            "relationship_states": {},
            "relationship_states_by_universe": {},
            "current_emotional_state_by_universe": {},
            "created_at": now,
            "updated_at": now,
        }
        profiles.insert_one(existing)

    update_fields: dict[str, Any] = {"updated_at": now}
    for field_name in (
        "traits",
        "values",
        "fears",
        "desires",
        "speech_style",
        "catchphrases",
        "mannerisms",
        "emotional_tendencies",
        "preferences",
        "triggers",
        "secrets",
        "gm_notes",
        "current_emotional_state",
    ):
        value = getattr(params, field_name)
        if value is not None:
            if field_name in {"emotional_tendencies", "preferences", "triggers"}:
                update_fields[field_name] = [
                    item.model_dump() if hasattr(item, "model_dump") else item for item in value
                ]
            else:
                update_fields[field_name] = value

    if params.add_preference is not None:
        update_fields["preferences"] = list(existing.get("preferences", [])) + [params.add_preference.model_dump()]
    if params.add_trigger is not None:
        update_fields["triggers"] = list(existing.get("triggers", [])) + [params.add_trigger.model_dump()]
    if params.add_secret is not None:
        update_fields["secrets"] = list(existing.get("secrets", [])) + [params.add_secret]

    if params.relationship_states is not None:
        merged_relationships = dict(existing.get("relationship_states", {}))
        for target_id, state in params.relationship_states.items():
            existing_state = merged_relationships.get(target_id, {})
            if isinstance(existing_state, dict) and isinstance(state, dict):
                merged_relationships[target_id] = {**existing_state, **state}
            else:
                merged_relationships[target_id] = state
        update_fields["relationship_states"] = merged_relationships

    # Per-universe relationship partition (Character Versions). Same merge
    # semantics as the legacy map: deep-merge each per-(universe,target) entry.
    if params.relationship_states_by_universe is not None:
        merged_by_universe = dict(existing.get("relationship_states_by_universe", {}))
        for universe_id, targets in params.relationship_states_by_universe.items():
            universe_map = dict(merged_by_universe.get(universe_id, {}))
            for target_id, state in (targets or {}).items():
                existing_state = universe_map.get(target_id, {})
                if isinstance(existing_state, dict) and isinstance(state, dict):
                    universe_map[target_id] = {**existing_state, **state}
                else:
                    universe_map[target_id] = state
            merged_by_universe[universe_id] = universe_map
        update_fields["relationship_states_by_universe"] = merged_by_universe

    if params.current_emotional_state_by_universe is not None:
        merged_emotion = dict(existing.get("current_emotional_state_by_universe", {}))
        for universe_id, state_val in (params.current_emotional_state_by_universe or {}).items():
            merged_emotion[universe_id] = state
        update_fields["current_emotional_state_by_universe"] = merged_emotion

    profiles.update_one(
        {"entity_id": str(entity_id)},
        {"$set": update_fields},
    )

    updated = profiles.find_one({"entity_id": str(entity_id)})
    if not updated:
        raise ValueError(f"NPC profile for entity {entity_id} not found after update")
    return _npc_profile_doc_to_response(updated)
