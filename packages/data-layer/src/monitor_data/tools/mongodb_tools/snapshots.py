"""
MongoDB tools for World Snapshot operations.

LAYER: 1 (data-layer)
Authority: MongoDB
Use Case: DL-23
"""

from typing import Any

import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.world_snapshots import (
    SnapshotCompareResponse,
    SnapshotEntityDiff,
    SnapshotFactDiff,
    SnapshotRelationshipDiff,
    WorldSnapshot,
    WorldSnapshotCreate,
    WorldSnapshotFilter,
    WorldSnapshotListResponse,
    WorldSnapshotResponse,
)
from monitor_data.tools.neo4j_tools.core import neo4j_get_universe_state

logger = logging.getLogger(__name__)

# =============================================================================
# WORLD SNAPSHOT OPERATIONS (DL-23)
# =============================================================================


def mongodb_create_world_snapshot(params: WorldSnapshotCreate) -> WorldSnapshotResponse:
    """
    Capture the current state of a Universe from Neo4j and save it to MongoDB.
    """
    client = get_mongodb_client()
    collection = client.get_collection("world_snapshots")

    # 1. Fetch current state from Neo4j
    state = neo4j_get_universe_state(params.universe_id)

    snapshot_id = uuid4()
    now = datetime.now(UTC)

    # 2. Build full snapshot document
    snapshot_doc = {
        "snapshot_id": str(snapshot_id),
        "universe_id": str(params.universe_id),
        "name": params.name,
        "description": params.description,
        "entities": state["entities"],
        "facts": state["facts"],
        "axioms": state["axioms"],
        "relationships": state["relationships"],
        "created_at": now,
    }

    collection.insert_one(snapshot_doc)

    return WorldSnapshotResponse(
        snapshot_id=snapshot_id,
        universe_id=params.universe_id,
        name=params.name,
        description=params.description,
        entity_count=len(state["entities"]),
        fact_count=len(state["facts"]),
        relationship_count=len(state["relationships"]),
        axiom_count=len(state["axioms"]),
        created_at=now,
    )


def mongodb_get_world_snapshot(snapshot_id: UUID) -> WorldSnapshot | None:
    """Retrieve the full content of a snapshot."""
    client = get_mongodb_client()
    collection = client.get_collection("world_snapshots")

    doc = collection.find_one({"snapshot_id": str(snapshot_id)})
    if not doc:
        return None

    return WorldSnapshot(**doc)


def mongodb_list_world_snapshots(filters: WorldSnapshotFilter) -> WorldSnapshotListResponse:
    """List snapshots for a universe."""
    client = get_mongodb_client()
    collection = client.get_collection("world_snapshots")

    query = {}
    if filters.universe_id:
        query["universe_id"] = str(filters.universe_id)

    total = collection.count_documents(query)
    cursor = (
        collection.find(query, {"entities": 0, "facts": 0, "axioms": 0, "relationships": 0})
        .sort("created_at", -1)
        .skip(filters.offset)
        .limit(filters.limit)
    )

    snapshots = [
        WorldSnapshotResponse(
            snapshot_id=UUID(doc["snapshot_id"]),
            universe_id=UUID(doc["universe_id"]),
            name=doc["name"],
            description=doc.get("description", ""),
            entity_count=doc.get("entity_count", 0),
            fact_count=doc.get("fact_count", 0),
            relationship_count=doc.get("relationship_count", 0),
            axiom_count=doc.get("axiom_count", 0),
            created_at=doc["created_at"],
        )
        for doc in cursor
    ]

    return WorldSnapshotListResponse(snapshots=snapshots, total=total, limit=filters.limit, offset=filters.offset)


def mongodb_delete_world_snapshot(snapshot_id: UUID) -> bool:
    """Delete a snapshot."""
    client = get_mongodb_client()
    collection = client.get_collection("world_snapshots")

    result = collection.delete_one({"snapshot_id": str(snapshot_id)})
    return result.deleted_count > 0


def mongodb_restore_world_snapshot(snapshot_id: UUID) -> dict[str, Any]:
    """
    Restore a universe from a snapshot.

    Reads the snapshot data and creates ProposedChange documents for each
    entity, fact, and relationship. CanonKeeper evaluates and commits these
    proposals to Neo4j, maintaining the write invariant.

    The restore process:
    1. Read snapshot from MongoDB
    2. Create ProposedChange documents for entities, facts, and relationships
    3. CanonKeeper evaluates and commits each proposal
    4. Update snapshot metadata with restore status

    Authority: CanonKeeper, WorldArchitect
    Use Case: M-34

    Args:
        snapshot_id: UUID of the snapshot to restore

    Returns:
        Dict with entities/facts/relationships restored counts and status

    Raises:
        ValueError: If snapshot not found
    """
    from monitor_data.schemas.base import Authority, ProposalType
    from monitor_data.schemas.proposed_changes import ProposedChangeCreate
    from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change

    client = get_mongodb_client()
    collection = client.get_collection("world_snapshots")

    # 1. Get snapshot data
    doc = collection.find_one({"snapshot_id": str(snapshot_id)})
    if not doc:
        raise ValueError(f"Snapshot {snapshot_id} not found")

    universe_id = UUID(doc["universe_id"])
    entities = doc.get("entities", [])
    facts = doc.get("facts", [])
    relationships = doc.get("relationships", [])

    # 2. Create ProposedChange documents for CanonKeeper to evaluate and commit.
    #    This maintains the architecture invariant: only CanonKeeper writes to Neo4j.
    proposals_created = 0
    errors = []

    # 2a. Entity proposals
    for entity_data in entities:
        try:
            entity_name = entity_data.get("name", "Unknown")
            entity_type = entity_data.get("entity_type", "CONCEPT")
            description = entity_data.get("description", "")
            is_archetype = entity_data.get("is_archetype", False)
            properties = entity_data.get("properties", {})
            if isinstance(properties, str):
                try:
                    properties = json.loads(properties)
                except (json.JSONDecodeError, TypeError):
                    properties = {}

            proposal = ProposedChangeCreate(
                scene_id=None,
                story_id=None,
                change_type=ProposalType.ENTITY,
                content={
                    "name": entity_name,
                    "entity_type": entity_type,
                    "description": description,
                    "is_archetype": is_archetype,
                    "properties": properties,
                    "universe_id": str(universe_id),
                    "source_snapshot_id": str(snapshot_id),
                },
                confidence=1.0,
                authority=Authority.SYSTEM,
                proposer="snapshot_restore",
            )
            mongodb_create_proposed_change(proposal)
            proposals_created += 1
        except Exception as exc:
            logger.warning("Failed to create entity proposal for %s: %s", entity_data.get("name"), exc)
            errors.append(f"entity:{entity_data.get('name', 'unknown')}:{exc}")

    # 2b. Fact proposals
    for fact_data in facts:
        try:
            statement = fact_data.get("statement", "")
            if not statement:
                continue

            proposal = ProposedChangeCreate(
                scene_id=None,
                story_id=None,
                change_type=ProposalType.FACT,
                content={
                    "statement": statement,
                    "fact_type": fact_data.get("fact_type", "STATE"),
                    "canon_level": fact_data.get("canon_level", "canon"),
                    "magnitude": fact_data.get("magnitude", 1),
                    "universe_id": str(universe_id),
                    "source_snapshot_id": str(snapshot_id),
                },
                confidence=1.0,
                authority=Authority.SYSTEM,
                proposer="snapshot_restore",
            )
            mongodb_create_proposed_change(proposal)
            proposals_created += 1
        except Exception as exc:
            logger.warning("Failed to create fact proposal: %s", exc)
            errors.append(f"fact:{fact_data.get('id', 'unknown')}:{exc}")

    # 2c. Relationship proposals
    for rel_data in relationships:
        try:
            from_id = rel_data.get("from_id")
            to_id = rel_data.get("to_id")
            rel_type = rel_data.get("type", "RELATED_TO")
            if not from_id or not to_id:
                continue

            proposal = ProposedChangeCreate(
                scene_id=None,
                story_id=None,
                change_type=ProposalType.RELATIONSHIP,
                content={
                    "from_entity_id": from_id,
                    "to_entity_id": to_id,
                    "relationship_type": rel_type,
                    "universe_id": str(universe_id),
                    "source_snapshot_id": str(snapshot_id),
                },
                confidence=1.0,
                authority=Authority.SYSTEM,
                proposer="snapshot_restore",
            )
            mongodb_create_proposed_change(proposal)
            proposals_created += 1
        except Exception as exc:
            logger.warning("Failed to create relationship proposal: %s", exc)
            errors.append(f"relationship:{rel_data.get('from_id', 'unknown')}:{exc}")

    # 3. Update snapshot metadata
    collection.update_one(
        {"snapshot_id": str(snapshot_id)},
        {
            "$set": {
                "restored_at": datetime.now(UTC),
                "restore_status": "proposed",
                "proposals_created": proposals_created,
            }
        },
    )

    return {
        "snapshot_id": str(snapshot_id),
        "universe_id": str(universe_id),
        "entities_proposed": len(entities),
        "facts_proposed": len(facts),
        "relationships_proposed": len(relationships),
        "proposals_created": proposals_created,
        "errors": errors,
        "status": "proposed",
        "note": "Proposals created for CanonKeeper evaluation. Call CanonKeeper.evaluate_proposals() to commit to Neo4j.",
    }


def mongodb_compare_snapshots(snapshot_a_id: UUID, snapshot_b_id: UUID) -> SnapshotCompareResponse:
    """
    Compare two snapshots and return a detailed diff.

    Authority: All agents
    Use Case: M-34

    Args:
        snapshot_a_id: UUID of the earlier snapshot
        snapshot_b_id: UUID of the later snapshot

    Returns:
        SnapshotCompareResponse with entity/fact/relationship diffs

    Raises:
        ValueError: If either snapshot not found or they belong to different universes
    """
    client = get_mongodb_client()
    collection = client.get_collection("world_snapshots")

    doc_a = collection.find_one({"snapshot_id": str(snapshot_a_id)})
    doc_b = collection.find_one({"snapshot_id": str(snapshot_b_id)})

    if not doc_a:
        raise ValueError(f"Snapshot {snapshot_a_id} not found")
    if not doc_b:
        raise ValueError(f"Snapshot {snapshot_b_id} not found")

    # Verify same universe
    if doc_a["universe_id"] != doc_b["universe_id"]:
        raise ValueError("Cannot compare snapshots from different universes")

    universe_id = UUID(doc_a["universe_id"])

    # Build entity lookup maps
    entities_a = {e.get("id") or e.get("entity_id"): e for e in doc_a.get("entities", [])}
    entities_b = {e.get("id") or e.get("entity_id"): e for e in doc_b.get("entities", [])}

    entity_diffs: list[SnapshotEntityDiff] = []
    entities_added = 0
    entities_removed = 0
    entities_modified = 0

    all_entity_ids = set(entities_a.keys()) | set(entities_b.keys())
    for eid in all_entity_ids:
        in_a = eid in entities_a
        in_b = eid in entities_b

        if in_a and not in_b:
            diff = SnapshotEntityDiff(
                entity_id=eid,
                name=entities_a[eid].get("name", "unknown"),
                diff_type="removed",
                snapshot_a_state=entities_a[eid],
                snapshot_b_state=None,
            )
            entity_diffs.append(diff)
            entities_removed += 1
        elif not in_a and in_b:
            diff = SnapshotEntityDiff(
                entity_id=eid,
                name=entities_b[eid].get("name", "unknown"),
                diff_type="added",
                snapshot_a_state=None,
                snapshot_b_state=entities_b[eid],
            )
            entity_diffs.append(diff)
            entities_added += 1
        else:
            # Modified — check which fields changed
            state_a = entities_a[eid]
            state_b = entities_b[eid]
            changed_fields = [k for k in set(state_a.keys()) | set(state_b.keys()) if state_a.get(k) != state_b.get(k)]
            if changed_fields:
                diff = SnapshotEntityDiff(
                    entity_id=eid,
                    name=state_b.get("name", state_a.get("name", "unknown")),
                    diff_type="modified",
                    snapshot_a_state=state_a,
                    snapshot_b_state=state_b,
                    changed_fields=sorted(changed_fields),
                )
                entity_diffs.append(diff)
                entities_modified += 1

    # Build fact lookup maps
    facts_a = {f.get("id") or f.get("fact_id"): f for f in doc_a.get("facts", [])}
    facts_b = {f.get("id") or f.get("fact_id"): f for f in doc_b.get("facts", [])}

    fact_diffs: list[SnapshotFactDiff] = []
    facts_added = 0
    facts_removed = 0
    facts_modified = 0

    all_fact_ids = set(facts_a.keys()) | set(facts_b.keys())
    for fid in all_fact_ids:
        in_a = fid in facts_a
        in_b = fid in facts_b

        if in_a and not in_b:
            diff_fact = SnapshotFactDiff(
                fact_id=fid,
                statement=facts_a[fid].get("statement", ""),
                diff_type="removed",
                snapshot_a_state=facts_a[fid],
                snapshot_b_state=None,
            )
            fact_diffs.append(diff_fact)
            facts_removed += 1
        elif not in_a and in_b:
            diff_fact = SnapshotFactDiff(
                fact_id=fid,
                statement=facts_b[fid].get("statement", ""),
                diff_type="added",
                snapshot_a_state=None,
                snapshot_b_state=facts_b[fid],
            )
            fact_diffs.append(diff_fact)
            facts_added += 1
        else:
            state_a = facts_a[fid]
            state_b = facts_b[fid]
            changed_fields = [k for k in set(state_a.keys()) | set(state_b.keys()) if state_a.get(k) != state_b.get(k)]
            if changed_fields:
                diff_fact = SnapshotFactDiff(
                    fact_id=fid,
                    statement=state_b.get("statement", state_a.get("statement", "")),
                    diff_type="modified",
                    snapshot_a_state=state_a,
                    snapshot_b_state=state_b,
                    changed_fields=sorted(changed_fields),
                )
                fact_diffs.append(diff_fact)
                facts_modified += 1

    # Build relationship diffs
    rels_a = {
        f"{r.get('from_entity_id')}:{r.get('to_entity_id')}:{r.get('relationship_type')}"
        for r in doc_a.get("relationships", [])
    }
    rels_b = {
        f"{r.get('from_entity_id')}:{r.get('to_entity_id')}:{r.get('relationship_type')}"
        for r in doc_b.get("relationships", [])
    }

    relationship_diffs: list[SnapshotRelationshipDiff] = []
    relationships_added = 0
    relationships_removed = 0

    for rel_key in rels_a - rels_b:
        parts = rel_key.split(":")
        diff_rel = SnapshotRelationshipDiff(
            relationship_id=rel_key,
            from_entity_id=parts[0],
            to_entity_id=parts[1],
            relationship_type=parts[2] if len(parts) > 2 else "unknown",
            diff_type="removed",
            snapshot_a_state=None,
            snapshot_b_state=None,
        )
        relationship_diffs.append(diff_rel)
        relationships_removed += 1

    for rel_key in rels_b - rels_a:
        parts = rel_key.split(":")
        diff_rel = SnapshotRelationshipDiff(
            relationship_id=rel_key,
            from_entity_id=parts[0],
            to_entity_id=parts[1],
            relationship_type=parts[2] if len(parts) > 2 else "unknown",
            diff_type="added",
            snapshot_a_state=None,
            snapshot_b_state=None,
        )
        relationship_diffs.append(diff_rel)
        relationships_added += 1

    return SnapshotCompareResponse(
        snapshot_a_id=snapshot_a_id,
        snapshot_b_id=snapshot_b_id,
        universe_id=universe_id,
        entities_added=entities_added,
        entities_removed=entities_removed,
        entities_modified=entities_modified,
        facts_added=facts_added,
        facts_removed=facts_removed,
        facts_modified=facts_modified,
        relationships_added=relationships_added,
        relationships_removed=relationships_removed,
        entity_diffs=entity_diffs,
        fact_diffs=fact_diffs,
        relationship_diffs=relationship_diffs,
        snapshot_a_name=doc_a.get("name", ""),
        snapshot_b_name=doc_b.get("name", ""),
        snapshot_a_created_at=doc_a.get("created_at", datetime.utcnow()),
        snapshot_b_created_at=doc_b.get("created_at", datetime.utcnow()),
    )
