"""Tests for the entity-promotion gate in canonkeeper_support.py.

Covers:
- find_topologically_bound_entity_names: relationship/state_change/event
  proposals in the same batch pin an ENTITY proposal for auto-promotion.
- gate_entity_proposals: the full three-gate split (topology, anchor,
  flavor-threshold) that lets CanonKeeper.evaluate_proposals skip the LLM
  pipeline for proposals with an unambiguous verdict.

See docs/2_architecture/data_model_workflow.md for the full lifecycle.
"""

from __future__ import annotations

from monitor_data.schemas.agent_responses import CanonKeeperDecision

from monitor_agents.canonkeeper.canonkeeper_support import (
    FLAVOR_INTERACTION_THRESHOLD,
    find_topologically_bound_entity_names,
    gate_entity_proposals,
)


def _entity(name: str, **overrides) -> dict:
    base = {
        "proposal_type": "ENTITY",
        "content": {"name": name, "entity_type": "CHARACTER", "description": ""},
    }
    base.update(overrides)
    return base


def _relationship(summary: str = "", content: dict | None = None) -> dict:
    return {
        "proposal_type": "RELATIONSHIP",
        "content": content or {},
        "summary": summary,
    }


# ============================================================================
# find_topologically_bound_entity_names
# ============================================================================


def test_topology_finds_entity_named_in_relationship_summary() -> None:
    proposals = [
        _entity("Kira Shadowdancer"),
        _relationship(summary="Kira Shadowdancer now owes a debt to the Prince."),
    ]
    assert find_topologically_bound_entity_names(proposals) == {"kira shadowdancer"}


def test_topology_finds_entity_named_in_relationship_content() -> None:
    proposals = [
        _entity("Droop"),
        _relationship(content={"source": "Droop", "target": "Player", "kind": "ally_of"}),
    ]
    assert find_topologically_bound_entity_names(proposals) == {"droop"}


def test_topology_ignores_entities_not_mentioned_elsewhere() -> None:
    proposals = [
        _entity("Unmentioned Bartender"),
        _relationship(summary="Something unrelated happened."),
    ]
    assert find_topologically_bound_entity_names(proposals) == set()


def test_topology_no_relationship_proposals_returns_empty() -> None:
    proposals = [_entity("Kira Shadowdancer")]
    assert find_topologically_bound_entity_names(proposals) == set()


def test_topology_state_change_and_event_kinds_also_count() -> None:
    proposals = [
        _entity("Guard Captain"),
        {
            "proposal_type": "STATE_CHANGE",
            "content": {},
            "summary": "Guard Captain's morale drops.",
        },
        {"proposal_type": "EVENT", "content": {}, "summary": "Guard Captain flees the scene."},
    ]
    assert find_topologically_bound_entity_names(proposals) == {"guard captain"}


def test_topology_handles_missing_proposal_type_key_gracefully() -> None:
    proposals = [{"content": {}}, {"content": {}, "summary": "no crash"}]
    assert find_topologically_bound_entity_names(proposals) == set()


# ============================================================================
# gate_entity_proposals — topology gate
# ============================================================================


def test_gate_topologically_bound_entity_is_auto_accepted() -> None:
    entity = _entity("Kira Shadowdancer")
    rel = _relationship(summary="Kira Shadowdancer allies with the player.")

    decided, remaining = gate_entity_proposals([entity, rel])

    assert remaining == [rel]
    assert len(decided) == 1
    proposal, verdict = decided[0]
    assert proposal is entity
    assert verdict.decision == CanonKeeperDecision.ACCEPTED
    assert "graph integrity" in verdict.reasoning


# ============================================================================
# gate_entity_proposals — anchor gate
# ============================================================================


def test_gate_anchor_tagged_entity_is_auto_accepted() -> None:
    entity = _entity("General Puentes", promotion_intent="anchor")

    decided, remaining = gate_entity_proposals([entity])

    assert remaining == []
    proposal, verdict = decided[0]
    assert verdict.decision == CanonKeeperDecision.ACCEPTED
    assert "anchor" in verdict.reasoning


# ============================================================================
# gate_entity_proposals — flavor threshold
# ============================================================================


def test_gate_flavor_entity_below_threshold_is_rejected() -> None:
    entity = _entity("Bartender", promotion_intent="flavor", interaction_count=1)

    decided, remaining = gate_entity_proposals([entity])

    assert remaining == []
    _, verdict = decided[0]
    assert verdict.decision == CanonKeeperDecision.REJECTED
    assert "Garbage collected" in verdict.reasoning


def test_gate_flavor_entity_at_threshold_is_still_rejected() -> None:
    """interaction_count == threshold does not qualify — must exceed it."""
    entity = _entity("Bartender", promotion_intent="flavor", interaction_count=FLAVOR_INTERACTION_THRESHOLD)

    decided, _ = gate_entity_proposals([entity])

    _, verdict = decided[0]
    assert verdict.decision == CanonKeeperDecision.REJECTED


def test_gate_flavor_entity_past_threshold_is_accepted() -> None:
    entity = _entity("Bartender", promotion_intent="flavor", interaction_count=FLAVOR_INTERACTION_THRESHOLD + 1)

    decided, _ = gate_entity_proposals([entity])

    _, verdict = decided[0]
    assert verdict.decision == CanonKeeperDecision.ACCEPTED
    assert "interaction threshold" in verdict.reasoning


def test_gate_untagged_entity_defaults_to_flavor_gc_rules() -> None:
    """No promotion_intent at all -- treated like flavor (untagged default)."""
    entity = _entity("Random Passerby", interaction_count=1)

    decided, _ = gate_entity_proposals([entity])

    _, verdict = decided[0]
    assert verdict.decision == CanonKeeperDecision.REJECTED


def test_gate_untagged_entity_past_threshold_is_accepted() -> None:
    entity = _entity("Recurring Passerby", interaction_count=FLAVOR_INTERACTION_THRESHOLD + 1)

    decided, _ = gate_entity_proposals([entity])

    _, verdict = decided[0]
    assert verdict.decision == CanonKeeperDecision.ACCEPTED


# ============================================================================
# gate_entity_proposals — non-entity passthrough & mixed batches
# ============================================================================


def test_gate_non_entity_proposals_pass_through_untouched() -> None:
    fact = {"proposal_type": "FACT", "content": {"statement": "The war ended."}}

    decided, remaining = gate_entity_proposals([fact])

    assert decided == []
    assert remaining == [fact]


def test_gate_topology_takes_priority_over_flavor_threshold() -> None:
    """Even a low-interaction-count flavor entity gets promoted immediately
    if topology already demands it -- topology gate runs first."""
    entity = _entity("Bartender", promotion_intent="flavor", interaction_count=1)
    rel = _relationship(summary="Bartender hands over the ledger.")

    decided, remaining = gate_entity_proposals([entity, rel])

    assert remaining == [rel]
    _, verdict = decided[0]
    assert verdict.decision == CanonKeeperDecision.ACCEPTED
    assert "graph integrity" in verdict.reasoning


def test_gate_mixed_batch_each_entity_decided_independently() -> None:
    anchor = _entity("Anchor NPC", promotion_intent="anchor")
    low_flavor = _entity("Throwaway NPC", promotion_intent="flavor", interaction_count=1)
    fact = {"proposal_type": "FACT", "content": {"statement": "unrelated"}}

    decided, remaining = gate_entity_proposals([anchor, low_flavor, fact])

    assert remaining == [fact]
    decisions = {p["content"]["name"]: v.decision for p, v in decided}
    assert decisions["Anchor NPC"] == CanonKeeperDecision.ACCEPTED
    assert decisions["Throwaway NPC"] == CanonKeeperDecision.REJECTED


def test_gate_verdict_proposal_id_generated_when_missing() -> None:
    entity = _entity("No ID Entity", promotion_intent="anchor")
    decided, _ = gate_entity_proposals([entity])
    _, verdict = decided[0]
    assert verdict.proposal_id is not None


def test_gate_verdict_proposal_id_preserved_when_present() -> None:
    import uuid

    pid = uuid.uuid4()
    entity = _entity("Has ID Entity", promotion_intent="anchor", proposal_id=str(pid))
    decided, _ = gate_entity_proposals([entity])
    _, verdict = decided[0]
    assert verdict.proposal_id == pid
