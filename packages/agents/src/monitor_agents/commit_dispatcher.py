"""
CommitDispatcher mixin for CanonKeeper.

LAYER: 2 (agents)

Separates the commit-dispatch responsibility from the evaluation/reasoning
responsibility (SRP). CanonKeeper inherits from this mixin to gain the
commit dispatch logic.

The actual per-type handler methods (_commit_entity, _commit_axiom, etc.)
remain on CanonKeeper itself since they require BaseAgent.call_tool and
domain-specific normalisation logic. This mixin provides:

1. The _COMMIT_HANDLERS dispatch table
2. The _commit_to_neo4j() entry point that routes proposals to handlers
3. Integration with the global CommitHandlerRegistry (Open/Closed)

This allows:
- New entity types to be added via registry without modifying CanonKeeper
- Commit dispatch logic to be tested independently
- Clear separation between "evaluate" and "commit" concerns
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from monitor_data.schemas.agent_responses import CanonKeeperVerdict

logger = logging.getLogger(__name__)


class CommitDispatcherMixin:
    """
    Mixin providing commit-dispatch logic for CanonKeeper.

    This mixin assumes the host class provides:
    - async call_tool(tool_name, params) -> Any  (from BaseAgent)
    - async _commit_entity(...) and other _commit_* handlers
    """

    # ------------------------------------------------------------------
    # _commit_to_neo4j dispatch table
    # Maps type_key → private handler method name on self
    # ------------------------------------------------------------------
    _COMMIT_HANDLERS: dict[str, str] = {
        "multiverse": "_commit_multiverse",
        "universe": "_commit_universe",
        "entity": "_commit_entity",
        "character": "_commit_entity",
        "location": "_commit_entity",
        "item": "_commit_entity",
        "faction": "_commit_entity",
        "concept": "_commit_entity",
        "create_entity_archetype": "_commit_entity",
        "entity_archetype": "_commit_entity",
        "axiom": "_commit_axiom",
        "create_axiom": "_commit_axiom",
        "world_truth": "_commit_axiom",
        "update_agenda_clock": "_commit_update_agenda_clock",
        "create_agenda": "_commit_create_agenda",
        "spatial_topology": "_commit_spatial_topology",
        "create_random_table": "_commit_random_table",
        "create_tone_profile": "_commit_tone_profile",
        "create_character_profile": "_commit_character_profile",
        "create_generation_template": "_commit_generation_template",
        "relationship": "_commit_relationship",
        "fact": "_commit_fact",
        "event": "_commit_fact",
        "create_lore_fact": "_commit_fact",
        "lore_fact": "_commit_fact",
        "create_plot_thread": "_commit_plot_thread",
        "entity_relationship": "_commit_entity_relationship",
        "state_update": "_commit_state_change",
        "state_change": "_commit_state_change",
    }

    async def _commit_to_neo4j(
        self,
        verdict: CanonKeeperVerdict,
        proposal: dict[str, Any],
        source_ids: list[UUID] | None = None,
    ) -> None:
        """
        Write an accepted proposal to Neo4j.

        Routes to the correct handler via _COMMIT_HANDLERS dispatch table,
        or via the global CommitHandlerRegistry (Open/Closed principle).

        Only CanonKeeper has authority for these tools (enforced by middleware).

        After each successful write the new Neo4j node UUID is stored back on
        the MongoDB proposal document as ``neo4j_id`` so the two databases
        remain bidirectionally linked by UUID.

        Args:
            verdict:    Accepted CanonKeeperVerdict for this proposal.
            proposal:   Raw MongoDB proposal document dict.
            source_ids: Neo4j Source node UUIDs to create SUPPORTED_BY edges.
        """
        from monitor_data.db.mongodb import get_mongodb_client

        from monitor_agents.handlers.registry import get_handler_registry

        mongodb = get_mongodb_client()
        proposals_coll = mongodb.get_collection("proposed_changes")
        proposal_id = str(proposal.get("proposal_id") or "")
        # Reset the per-commit neo4j-id stash used by the audit trail.
        self._last_commit_neo4j_id = None

        # Normalize — KnowledgePack proposals use prefixed types
        proposal_type = proposal.get("proposal_type", "").lower()
        change_type = verdict.canon_node_type.lower() if verdict.canon_node_type else ""
        type_key = proposal_type or change_type

        # Check registry first (allows external handler registration)
        registry = get_handler_registry()
        external_handler = registry.get(type_key)
        if external_handler is not None:
            await external_handler(
                proposals_coll,
                proposal_id,
                proposal,
                [str(sid) for sid in source_ids] if source_ids else None,
                verdict,
                self,
            )
            self._audit_commit(proposals_coll, proposal_id, type_key, proposal, verdict)
            return

        # Fall back to built-in handlers
        handler_name = self._COMMIT_HANDLERS.get(type_key)
        if handler_name is None:
            logger.warning("Unknown type_key '%s' in _commit_to_neo4j", type_key)
            return

        handler = getattr(self, handler_name)
        await handler(
            proposals_coll,
            proposal_id,
            proposal,
            [str(sid) for sid in source_ids] if source_ids else None,
            verdict,
        )
        self._audit_commit(proposals_coll, proposal_id, type_key, proposal, verdict)

    # Neo4j UUID of the most recent committed node — set by handlers via
    # _store_neo4j_id_on_proposal, consumed by _audit_commit.
    _last_commit_neo4j_id: str | None = None

    # Map a proposal/commit type_key to a ChangeLog subject type.
    _AUDIT_SUBJECT: dict[str, str] = {
        "entity": "entity",
        "character": "entity",
        "location": "entity",
        "item": "entity",
        "faction": "entity",
        "concept": "entity",
        "create_entity_archetype": "entity",
        "entity_archetype": "entity",
        "axiom": "axiom",
        "create_axiom": "axiom",
        "world_truth": "axiom",
        "fact": "fact",
        "event": "event",
        "create_lore_fact": "lore_event",
        "lore_fact": "lore_event",
        "relationship": "relationship",
        "entity_relationship": "relationship",
        "create_plot_thread": "story",
        "state_update": "entity",
        "state_change": "entity",
    }

    def _audit_commit(
        self,
        proposals_coll: Any,
        proposal_id: str,
        type_key: str,
        proposal: dict[str, Any],
        verdict: CanonKeeperVerdict,
    ) -> None:
        """Append an append-only ChangeLog entry for a committed proposal.

        Best-effort: auditing must never break a canon commit.
        """
        from uuid import UUID as _UUID

        from monitor_data.schemas.change_log import ChangeSubjectType
        from monitor_data.tools.mongodb_tools import (
            make_change_log_entry,
            mongodb_append_change_log,
        )

        try:
            subject_name = self._AUDIT_SUBJECT.get(type_key)
            if subject_name is None:
                return  # unknown/non-audited type — skip quietly
            # Prefer the in-memory stash (set by the handler), falling back to
            # the persisted proposal doc for scene-loop proposals.
            doc = proposals_coll.find_one({"proposal_id": proposal_id}) if proposal_id else None
            doc = doc or {}
            neo4j_id = getattr(self, "_last_commit_neo4j_id", None) or doc.get("neo4j_id")
            if not neo4j_id:
                return

            def _maybe_uuid(value: Any) -> UUID | None:
                try:
                    return _UUID(str(value)) if value else None
                except (ValueError, TypeError):
                    return None

            entry = make_change_log_entry(
                subject_type=ChangeSubjectType(subject_name),
                subject_id=_UUID(str(neo4j_id)),
                authority=(proposal.get("authority") or "system"),
                evidence_type="proposal",
                evidence_id=_maybe_uuid(proposal_id),
                reason=getattr(verdict, "reasoning", None) or getattr(verdict, "rationale", None),
                transaction_id=_maybe_uuid(doc.get("scene_id")),
            )
            mongodb_append_change_log(entry)
        except Exception:  # pragma: no cover — auditing is non-critical
            logger.debug("change_log audit skipped for %s", proposal_id, exc_info=True)
