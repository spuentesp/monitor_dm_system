"""Knowledge audit tool — what the system believes a character knows (CF-15).

Read-only aggregation over the stores that already hold the answer:

- **Facts** the character witnessed (Neo4j; a fact with no witness record
  is common knowledge, so it counts as known by everyone).
- **Memories** the character owns (Mongo), each with its scene, importance
  and certainty.
- **Proposals** that would change what is attributed to the character
  (Mongo), so the GM can see pending canon before accepting it.

Nothing here writes to Neo4j — the tool only reads. The challenge action
stages a ``ProposedChange`` through the CF-8 queue, where CanonKeeper
decides.

LAYER: 1 (data-layer)
IMPORTS FROM: external libraries + data-layer db modules only
CALLED BY: agents (Layer 2) via MCP, UI backend (Layer 3)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.base import ProposalStatus
from monitor_data.schemas.facts import FactFilter
from monitor_data.schemas.knowledge_audit import (
    KnowledgeAudit,
    KnowledgeAuditFilter,
    KnowledgeItem,
)

# A memory the character is unsure of is worth a second look.
_LOW_CERTAINTY = 0.5

# A memory that matters a lot but the character is unsure of is the worst
# case: it will be recalled loudly and believed wrongly.
_MATERIAL_IMPORTANCE = 0.6


def _witnessed_facts(entity_id: UUID, universe_id: UUID | None, limit: int) -> list[dict[str, Any]]:
    """The canon facts this character witnessed (plus common knowledge)."""
    try:
        from monitor_data.tools.neo4j_tools.facts import neo4j_list_facts

        filters = FactFilter(
            universe_id=universe_id,
            entity_id=entity_id,
            limit=min(limit, 100),
        )
        facts = neo4j_list_facts(filters)
    except Exception:  # noqa: BLE001  # reason: an unreadable graph means "no facts here", not a failure
        return []

    rows: list[dict[str, Any]] = []
    for fact in facts:
        witnesses = [str(w) for w in (fact.witnesses or [])]
        if not witnesses:
            source = "common"
        elif str(entity_id) in witnesses:
            source = "witnessed"
        else:
            # The fact involves the character but they were not there.
            continue
        rows.append(
            {
                "id": str(fact.id),
                "statement": fact.statement,
                "source": source,
                "canon_level": str(fact.canon_level.value)
                if hasattr(fact.canon_level, "value")
                else str(fact.canon_level),
                "confidence": float(fact.confidence),
            }
        )
    return rows


def _owned_memories(entity_id: UUID, universe_id: UUID | None, limit: int) -> list[dict[str, Any]]:
    """The character's own memories."""
    client = get_mongodb_client()
    collection = client.get_collection("character_memories")
    query: dict[str, Any] = {"entity_id": str(entity_id)}
    if universe_id is not None:
        query["universe_id"] = str(universe_id)
    cursor = collection.find(query).sort("importance", -1).limit(limit)
    rows: list[dict[str, Any]] = []
    for doc in cursor:
        rows.append(
            {
                "id": str(doc.get("memory_id") or doc.get("id") or ""),
                "statement": str(doc.get("text") or ""),
                "source": "memory",
                "scene_id": doc.get("scene_id"),
                "importance": float(doc.get("importance") or 0.0),
                "certainty": float(doc.get("certainty") if doc.get("certainty") is not None else 1.0),
                "linked_fact_id": doc.get("linked_fact_id"),
                "witnesses": doc.get("witnesses") or [],
            }
        )
    return rows


def _pending_proposals(entity_id: UUID, universe_id: UUID | None, limit: int) -> list[dict[str, Any]]:
    """Proposals that would change what is attributed to the character."""
    client = get_mongodb_client()
    collection = client.get_collection("proposed_changes")
    query: dict[str, Any] = {"status": ProposalStatus.PENDING.value}
    if universe_id is not None:
        query["universe_id"] = str(universe_id)
    cursor = collection.find(query).limit(limit)
    rows: list[dict[str, Any]] = []
    for doc in cursor:
        content = doc.get("content") or {}
        if not isinstance(content, dict):
            content = {}
        participants = content.get("participants") or []
        mentioned = str(entity_id) in {str(p) for p in participants}
        if not mentioned and str(doc.get("entity_id") or "") != str(entity_id):
            continue
        statement = (
            content.get("statement")
            or content.get("description")
            or content.get("summary")
            or content.get("name")
            or ""
        )
        rows.append(
            {
                "id": str(doc.get("proposal_id") or ""),
                "statement": str(statement),
                "source": "proposal",
                "confidence": float(doc.get("confidence") or 1.0),
            }
        )
    return rows


def _suspicion(memory: dict[str, Any]) -> tuple[bool, str]:
    """Whether an attribution looks doubtful — the v1 heuristic.

    Three signals, all explicit:

    1. The character is unsure of it (``certainty`` below half).
    2. It matters to them and they are unsure of it (the worst case: it
       will be recalled loudly and believed wrongly).
    3. It is anchored to a canon fact they did not witness.
    """
    certainty = float(memory.get("certainty") or 1.0)
    importance = float(memory.get("importance") or 0.0)
    if certainty < _LOW_CERTAINTY and importance >= _MATERIAL_IMPORTANCE:
        return True, (f"Important to them ({importance:.2f}) but they are not sure of it ({certainty:.2f}).")
    if certainty < _LOW_CERTAINTY:
        return True, f"They are not sure of this ({certainty:.2f})."
    linked = memory.get("linked_fact_id")
    witnesses = [str(w) for w in (memory.get("witnesses") or [])]
    if linked and witnesses and str(memory.get("entity_id") or "") not in witnesses:
        return True, "Anchored to a canon fact this character did not witness."
    return False, ""


def mongodb_list_knowledge_audit(params: KnowledgeAuditFilter) -> KnowledgeAudit:
    """Everything the system attributes to one character.

    Authority: * (read-only)
    Use Case: CF-15
    """
    entity_id = params.entity_id
    universe_id = params.universe_id
    limit = params.limit

    items: list[KnowledgeItem] = []

    for fact in _witnessed_facts(entity_id, universe_id, limit):
        items.append(
            KnowledgeItem(
                id=fact["id"],
                kind="fact",
                statement=fact["statement"],
                source=fact["source"],
                confidence=fact["confidence"],
                canon_level=fact.get("canon_level", ""),
            )
        )

    suspicious_count = 0
    for memory in _owned_memories(entity_id, universe_id, limit):
        suspicious, reason = _suspicion({**memory, "entity_id": str(entity_id)})
        if suspicious:
            suspicious_count += 1
        items.append(
            KnowledgeItem(
                id=memory["id"],
                kind="memory",
                statement=memory["statement"],
                source="memory",
                scene_id=UUID(str(memory["scene_id"])) if memory.get("scene_id") else None,
                importance=memory["importance"],
                certainty=memory["certainty"],
                suspicious=suspicious,
                suspicion_reason=reason,
            )
        )

    for proposal in _pending_proposals(entity_id, universe_id, limit):
        items.append(
            KnowledgeItem(
                id=proposal["id"],
                kind="proposal",
                statement=proposal["statement"],
                source="proposal",
                confidence=proposal["confidence"],
            )
        )

    return KnowledgeAudit(
        entity_id=entity_id,
        universe_id=universe_id,
        items=items,
        fact_count=sum(1 for item in items if item.kind == "fact"),
        memory_count=sum(1 for item in items if item.kind == "memory"),
        proposal_count=sum(1 for item in items if item.kind == "proposal"),
        suspicious_count=suspicious_count,
    )


__all__ = ["mongodb_list_knowledge_audit"]
