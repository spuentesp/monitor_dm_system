"""CanonKeeper Support — pure helpers extracted from canonkeeper.py.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), stdlib
CALLED BY: canonkeeper.py

Entity-promotion gate: decides which pending ENTITY proposals can skip
the full LLM evaluation pipeline (policy check + contradiction check +
reasoning + instructor verdict) and be auto-decided instead, based on:

1. Topology  — referenced by a relationship/state_change/event proposal
               in the SAME batch. Graph integrity requires the entity
               exist for the relationship to attach to.
2. Anchor    — tagged [Name](entity:anchor) by the Narrator at generation
               time (see NarratorSignature's docstring). Structural weight
               declared explicitly; auto-promote.
3. Flavor / untagged — auto-promote only once interaction_count exceeds
               the GC threshold; otherwise discarded (REJECTED) without
               spending an LLM call on it.

See docs/2_architecture/data_model_workflow.md for the full lifecycle.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from monitor_data.schemas.agent_responses import CanonKeeperDecision, CanonKeeperVerdict

# A flavor entity mentioned more than this many times earns permanent
# placement anyway — sustained presence is itself a promotion signal.
FLAVOR_INTERACTION_THRESHOLD = 3

_TOPOLOGY_KINDS = {"RELATIONSHIP", "STATE_CHANGE", "EVENT"}


def _proposal_kind(proposal: dict[str, Any]) -> str:
    """Normalize the proposal-type key across proposers.

    Proposers disagree on both the key name (``proposal_type`` vs
    ``change_type``) and casing (``"ENTITY"`` vs ``"entity"``) — this
    predates entity promotion and isn't something this module can fix
    without touching every proposer, so it normalizes defensively instead.
    """
    raw = proposal.get("proposal_type") or proposal.get("change_type") or ""
    return str(raw).strip().upper()


def _entity_name(proposal: dict[str, Any]) -> str:
    content = proposal.get("content") or {}
    return str(content.get("name", "")).strip()


def find_topologically_bound_entity_names(proposals: list[dict[str, Any]]) -> set[str]:
    """Entity names referenced by a non-ENTITY proposal in the same batch.

    A relationship/state-change/event proposal that mentions an entity by
    name (substring match against its serialized content + summary) means
    that entity must be promoted too, or the relationship has nothing to
    attach to in Neo4j. Names are returned lower-cased for
    case-insensitive matching by the caller.
    """
    entity_names = [n for n in (_entity_name(p) for p in proposals if _proposal_kind(p) == "ENTITY") if n]
    if not entity_names:
        return set()

    bound: set[str] = set()
    for proposal in proposals:
        if _proposal_kind(proposal) not in _TOPOLOGY_KINDS:
            continue
        haystack = (
            json.dumps(proposal.get("content", {}), default=str) + " " + str(proposal.get("summary", ""))
        ).lower()
        for name in entity_names:
            if name.lower() in haystack:
                bound.add(name.lower())

    return bound


def _accept_verdict(proposal: dict[str, Any], *, reason: str) -> CanonKeeperVerdict:
    content = proposal.get("content") or {}
    proposal_id = proposal.get("proposal_id") or str(uuid4())
    return CanonKeeperVerdict(
        proposal_id=proposal_id,
        decision=CanonKeeperDecision.ACCEPTED,
        reasoning=reason,
        canon_node_type=str(content.get("entity_type") or "concept"),
        canon_properties=content,
        decided_at=datetime.now(UTC),
    )


def _reject_verdict(proposal: dict[str, Any], *, reason: str) -> CanonKeeperVerdict:
    proposal_id = proposal.get("proposal_id") or str(uuid4())
    return CanonKeeperVerdict(
        proposal_id=proposal_id,
        decision=CanonKeeperDecision.REJECTED,
        reasoning=reason,
        canon_node_type=None,
        canon_properties=None,
        decided_at=datetime.now(UTC),
    )


def gate_entity_proposals(
    proposals: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], CanonKeeperVerdict]], list[dict[str, Any]]]:
    """Split proposals into (pre-decided (proposal, verdict) pairs, proposals
    still needing the full LLM evaluation pipeline).

    Only PENDING ENTITY proposals are subject to the three gates (topology,
    anchor, flavor-threshold); every other proposal type passes through to
    ``remaining`` untouched, preserving today's behavior for facts,
    mechanics, and any proposal type this gate doesn't understand.
    """
    bound_names = find_topologically_bound_entity_names(proposals)
    decided: list[tuple[dict[str, Any], CanonKeeperVerdict]] = []
    remaining: list[dict[str, Any]] = []

    for proposal in proposals:
        if _proposal_kind(proposal) != "ENTITY":
            remaining.append(proposal)
            continue

        # UI-staged visual-identity canonization targets an EXISTING canonical
        # entity — it is not an entity-promotion candidate, so the topology /
        # anchor / flavor-threshold gates must not pre-decide it (the flavor
        # gate would garbage-collect it). Route it to the full LLM pipeline.
        content = proposal.get("content") or {}
        if isinstance(content, dict) and content.get("operation") == "set_visual_identity":
            remaining.append(proposal)
            continue

        name = _entity_name(proposal)
        intent = proposal.get("promotion_intent")
        interaction_count = int(proposal.get("interaction_count", 1) or 1)

        if name and name.lower() in bound_names:
            decided.append(
                (
                    proposal,
                    _accept_verdict(
                        proposal,
                        reason=(
                            "Auto-promoted to satisfy graph integrity: referenced by a "
                            "relationship/state-change/event proposal in this same batch."
                        ),
                    ),
                )
            )
            continue

        if intent == "anchor":
            decided.append(
                (
                    proposal,
                    _accept_verdict(
                        proposal,
                        reason="Auto-promoted: tagged as a structural anchor by the Narrator.",
                    ),
                )
            )
            continue

        # Flavor (explicit tag or untagged-default) — threshold or GC.
        if interaction_count > FLAVOR_INTERACTION_THRESHOLD:
            decided.append(
                (
                    proposal,
                    _accept_verdict(
                        proposal,
                        reason=(
                            f"Auto-promoted: flavor entity mentioned {interaction_count} times, "
                            f"past the interaction threshold ({FLAVOR_INTERACTION_THRESHOLD})."
                        ),
                    ),
                )
            )
        else:
            decided.append(
                (
                    proposal,
                    _reject_verdict(
                        proposal,
                        reason=(
                            f"Garbage collected: flavor entity mentioned only "
                            f"{interaction_count} time(s), below the interaction "
                            f"threshold ({FLAVOR_INTERACTION_THRESHOLD})."
                        ),
                    ),
                )
            )

    return decided, remaining
