"""
KnowledgeAuditAgent — audit what the system believes a character knows
(CF-15 / G09).

The GM can ask the system what the party knows; this agent answers a
different question: *is that right?* It gathers the facts, memories and
pending proposals attributed to a character, flags the attributions that
look doubtful, and — when the GM disagrees — stages a correction as a
``ProposedChange`` for the CF-8 queue.

The correction goes through the queue, never straight to canon: CanonKeeper
is the only writer, and the GM's own objection is a proposal like any
other, so the review trail shows it.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1 schemas + MCP tools), monitor_agents.base
CALLED BY: UI backend routers (Layer 3)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog
from monitor_agents.base import BaseAgent
from monitor_data.schemas.base import Authority, ProposalType
from monitor_data.schemas.knowledge_audit import (
    KnowledgeAudit,
    KnowledgeChallenge,
)
from monitor_data.schemas.proposed_changes import ProposedChangeCreate

log = structlog.get_logger()


def _as_dict(raw: Any) -> dict[str, Any]:
    """A tool result as a dict (the MCP layer may hand back JSON text)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


class KnowledgeAuditAgent(BaseAgent):
    """Inspects and challenges what a character is believed to know."""

    def __init__(self, agent_id: str | None = None, model: str | None = None) -> None:
        super().__init__(
            agent_type="KnowledgeAuditAgent",
            agent_id=agent_id or "knowledge-audit-agent",
            model=model,
        )

    async def run(self) -> None:
        """Implemented for BaseAgent compliance; routes call the methods below."""

    async def audit(
        self,
        entity_id: UUID,
        universe_id: UUID | None = None,
    ) -> KnowledgeAudit:
        """What the system believes this character knows, with provenance.

        Args:
            entity_id: The character to audit.
            universe_id: The universe to scope the audit to.

        Returns:
            The audit: every attributed fact, memory and pending proposal,
            each with where it came from and whether the attribution looks
            doubtful.
        """
        raw = await self.call_tool(
            "mongodb_list_knowledge_audit",
            {
                "params": {
                    "entity_id": str(entity_id),
                    "universe_id": str(universe_id) if universe_id else None,
                    "limit": 200,
                }
            },
        )
        payload = _as_dict(raw)
        if not payload:
            return KnowledgeAudit(entity_id=entity_id, universe_id=universe_id)
        try:
            return KnowledgeAudit.model_validate(payload)
        except Exception as exc:  # noqa: BLE001  # reason: a malformed audit degrades to an empty one
            log.warning("knowledge audit payload was malformed: %s", exc)
            return KnowledgeAudit(entity_id=entity_id, universe_id=universe_id)

    async def challenge(
        self,
        entity_id: UUID,
        universe_id: UUID | None,
        challenge: KnowledgeChallenge,
        story_id: UUID | None = None,
        scene_id: UUID | None = None,
    ) -> str:
        """Stage a correction for one attribution (CF-8 queue).

        The correction is a proposal, not a write: the GM's objection goes
        through the same review as anything else that would change canon,
        and CanonKeeper decides.

        Args:
            entity_id: The character whose knowledge is being corrected.
            universe_id: The universe the character belongs to.
            challenge: What the GM disputes and why.
            story_id: The story scope for the proposal, when there is one.
            scene_id: The scene scope for the proposal, when there is one.

        Returns:
            The proposal id.

        Raises:
            ValueError: When the proposal cannot be staged (no scope).
        """
        content: dict[str, Any] = {
            "statement": challenge.statement,
            "participants": [str(entity_id)],
            "knowledge_correction": {
                "action": challenge.action,
                "item_id": challenge.item_id,
                "item_kind": challenge.kind,
                "reason": challenge.reason,
            },
        }
        if universe_id is not None:
            content["universe_id"] = str(universe_id)

        raw = await self.call_tool(
            "mongodb_create_proposed_change",
            {
                "params": ProposedChangeCreate(
                    scene_id=scene_id,
                    story_id=story_id,
                    change_type=ProposalType.FACT,
                    content=content,
                    confidence=1.0,
                    authority=Authority.GM,
                    proposer="KnowledgeAuditAgent",
                    source=f"knowledge_challenge:{entity_id}",
                    proposal_type=f"knowledge_{challenge.action}",
                ).model_dump(mode="json")
            },
        )
        payload = _as_dict(raw)
        proposal_id = str(payload.get("proposal_id") or "")
        if not proposal_id:
            raise ValueError("The correction could not be staged.")
        log.info(
            "knowledge_challenge_staged",
            entity_id=str(entity_id),
            action=challenge.action,
            proposal_id=proposal_id,
        )
        return proposal_id


__all__ = ["KnowledgeAuditAgent"]
