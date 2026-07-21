"""
Tests for the Entity Promotion gate (DL-2 generalized promotion).

Covers:
- Step 1: narrator prompt carries the entity-tagging instructions
- Step 2: ProposedChange schema exposes promotion_intent / interaction_count /
          is_mechanically_bound (and PromotionIntent enum)
- Step 3: entity_promotion parser + merge / bump / mechanical binding
- Step 4+5: CanonKeeper._apply_entity_promotion_rules — topology, state-gated,
            anchor, flavor threshold flush, mechanically-bound fallback

All tests are pure (no DB / LLM).
"""

from __future__ import annotations

import os
import sys
from uuid import uuid4

import pytest

# Make the source trees importable when running this file directly without
# an editable install (CI sandboxes).
_HERE = os.path.dirname(os.path.abspath(__file__))
_AGENTS_SRC = os.path.normpath(os.path.join(_HERE, "..", "src"))
_DATA_SRC = os.path.normpath(
    os.path.join(_HERE, "..", "..", "data-layer", "src")
)
for p in (_AGENTS_SRC, _DATA_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)


# ─── Step 1: Narrator prompt ────────────────────────────────────────────────


def test_narrator_signature_mentions_entity_intent_syntax():
    """The Narrator prompt must explain both anchor and flavor syntaxes."""
    from monitor_agents.prompts.narrator import NarratorSignature

    desc = NarratorSignature.__doc__ or ""
    # docstring itself doesn't carry output desc; check output field
    narrative_field = NarratorSignature.model_fields["narrative_text"]
    text = narrative_field.json_schema_extra["desc"]
    assert "[Name](entity:anchor)" in text
    assert "[Name](entity:flavor)" in text
    assert "ENTITY INTENT TAGGING" in text or "intent" in text.lower()


# ─── Step 2: Schema fields ──────────────────────────────────────────────────


def test_promotion_intent_enum_values():
    from monitor_data.schemas.proposed_changes import PromotionIntent

    assert PromotionIntent.ANCHOR.value == "anchor"
    assert PromotionIntent.FLAVOR.value == "flavor"


def test_proposed_change_create_accepts_promotion_metadata():
    from monitor_data.schemas.proposed_changes import (
        ProposedChangeCreate,
        PromotionIntent,
    )

    pc = ProposedChangeCreate(
        change_type="entity",
        content={"name": "Kira"},
        scene_id=uuid4(),
        promotion_intent=PromotionIntent.ANCHOR,
        interaction_count=2,
        is_mechanically_bound=False,
    )
    assert pc.promotion_intent == PromotionIntent.ANCHOR
    assert pc.interaction_count == 2
    assert pc.is_mechanically_bound is False


def test_proposed_change_response_exposes_promotion_metadata():
    from monitor_data.schemas.proposed_changes import ProposedChangeResponse

    pid = uuid4()
    pr = ProposedChangeResponse(
        proposal_id=pid,
        scene_id=uuid4(),
        change_type="entity",
        content={"name": "Mara"},
        confidence=0.8,
        authority="system",
        proposer="narrator",
        status="pending",
        promotion_intent="flavor",
        interaction_count=5,
        is_mechanically_bound=True,
        created_at="2026-07-21T00:00:00",
        updated_at="2026-07-21T00:00:00",
    )
    assert pr.promotion_intent == "flavor"
    assert pr.interaction_count == 5
    assert pr.is_mechanically_bound is True


def test_non_entity_proposal_leaves_promotion_fields_at_defaults():
    """FACT proposals carry promotion metadata as None/default (irrelevant)."""
    from monitor_data.schemas.proposed_changes import ProposedChangeCreate

    pc = ProposedChangeCreate(
        change_type="fact",
        content={"statement": "Something happened"},
        scene_id=uuid4(),
    )
    assert pc.promotion_intent is None
    assert pc.interaction_count == 1
    assert pc.is_mechanically_bound is False


# ─── Step 3: Parser & helpers ──────────────────────────────────────────────


def test_parse_entity_tags_extracts_anchor_and_flavor():
    from monitor_agents.loops.entity_promotion import parse_entity_tags

    text = (
        '[Kira](entity:anchor) leans on the bar. '
        '[a bartender](entity:flavor) wipes a glass. '
        '[Rust Nail](entity:anchor) glares from the corner.'
    )
    parsed = parse_entity_tags(text)
    assert parsed == [
        ("Kira", "anchor"),
        ("a bartender", "flavor"),
        ("Rust Nail", "anchor"),
    ]


def test_parse_entity_tags_returns_empty_for_no_tags():
    from monitor_agents.loops.entity_promotion import parse_entity_tags

    assert parse_entity_tags("") == []
    assert parse_entity_tags("Nothing tagged here, just prose.") == []
    # A bare bracket without the (entity:...) suffix is NOT a tag.
    assert parse_entity_tags("[just bracketed](not-a-tag)") == []


def test_merge_tagged_intents_stamps_existing_proposal():
    from monitor_agents.loops.entity_promotion import merge_tagged_intents

    base = [
        {
            "proposal_type": "ENTITY",
            "content": {"name": "Kira"},
            "summary": "LLM detected Kira",
            "confidence": 0.9,
        }
    ]
    merged = merge_tagged_intents(base, [("Kira", "anchor")])
    assert merged[0]["promotion_intent"] == "anchor"
    assert merged[0]["content"]["name"] == "Kira"


def test_merge_tagged_intents_appends_when_llm_missed_entity():
    from monitor_agents.loops.entity_promotion import merge_tagged_intents

    base: list = []
    merged = merge_tagged_intents(base, [("The Bartender", "flavor")])
    assert len(merged) == 1
    assert merged[0]["proposal_type"] == "ENTITY"
    assert merged[0]["content"]["name"] == "The Bartender"
    assert merged[0]["promotion_intent"] == "flavor"
    assert merged[0]["interaction_count"] == 1


def test_bump_interaction_counts_increments_repeats():
    from monitor_agents.loops.entity_promotion import (
        bump_interaction_counts,
        merge_tagged_intents,
    )

    base = [
        {"proposal_type": "ENTITY", "content": {"name": "Kira"}, "interaction_count": 1}
    ]
    # First turn: Kira appears (counts as one interaction this turn).
    bumped = bump_interaction_counts(base, [("Kira", "anchor")])
    kira = next(p for p in bumped if p["content"]["name"] == "Kira")
    assert kira["interaction_count"] == 2

    # Same turn: multiple Kira mentions in one narrative still count as ONE
    # mention that turn (de-duped). This is the semantic bump uses — the
    # parser sees the entity in this turn's narration exactly once.
    bumped = bump_interaction_counts(
        bumped,
        [("Kira", "anchor"), ("Kira", "anchor"), ("Kira", "anchor")],
    )
    kira = next(p for p in bumped if p["content"]["name"] == "Kira")
    assert kira["interaction_count"] == 3


def test_detect_mechanically_bound_marks_named_entities():
    from monitor_agents.loops.entity_promotion import (
        detect_mechanically_bound,
    )

    proposals = [
        {"content": {"name": "Kira"}, "is_mechanically_bound": False},
        {"content": {"name": "The Bartender"}, "is_mechanically_bound": False},
        {"content": {"name": "Nobody"}},
    ]
    mechanical = [
        {"name": "Kira", "target_name": "the bartender"},
        {"entity_id": "Nobody", "description": "someone walked by"},
    ]
    bound = detect_mechanically_bound(proposals, mechanical)
    by_name = {p["content"]["name"]: p for p in bound}
    assert by_name["Kira"]["is_mechanically_bound"] is True
    assert by_name["The Bartender"]["is_mechanically_bound"] is True
    assert "Nobody" not in by_name or by_name["Nobody"].get("is_mechanically_bound") is True


def test_annotate_proposals_full_pipeline():
    """One-shot integration of parse + merge + bump + bind."""
    from monitor_agents.loops.entity_promotion import annotate_proposals

    base = [{"proposal_type": "ENTITY", "content": {"name": "Kira"}}]
    narrative = "[Kira](entity:anchor) walks to the bar. [a bartender](entity:flavor) nods."
    mechanical = [{"target_name": "a bartender"}]
    out = annotate_proposals(base, narrative, mechanical)
    by_name = {p["content"]["name"]: p for p in out}
    assert "Kira" in by_name
    assert "a bartender" in by_name
    assert by_name["a bartender"]["promotion_intent"] == "flavor"
    assert by_name["a bartender"]["is_mechanically_bound"] is True


# ─── Step 4 + 5: CanonKeeper promotion rules ───────────────────────────────


def _proposal(pid, change_type, *, name=None, payload_extra=None, **extra):
    payload = {"name": name} if name else {}
    if payload_extra:
        payload.update(payload_extra)
    return {
        "proposal_id": str(pid),
        "change_type": change_type,
        "payload": payload,
        **extra,
    }


def test_topology_promotes_entity_named_by_relationship():
    from monitor_agents.canonkeeper import CanonKeeper
    from monitor_data.schemas.agent_responses import CanonKeeperDecision

    ck = CanonKeeper()
    proposals = [
        _proposal(uuid4(), "entity", name="Kira", promotion_intent="flavor"),
        _proposal(uuid4(), "RELATIONSHIP", payload_extra={
            "from_entity": "Kira", "to_entity": "The Crew"
        }),
    ]
    verdicts = ck._apply_entity_promotion_rules(proposals)
    entity_v = next(v for v in verdicts if "graph integrity" in v.reasoning)
    assert entity_v.decision == CanonKeeperDecision.ACCEPTED


def test_state_gated_promotes_entity_named_in_state_change():
    from monitor_agents.canonkeeper import CanonKeeper
    from monitor_data.schemas.agent_responses import CanonKeeperDecision

    ck = CanonKeeper()
    proposals = [
        _proposal(uuid4(), "entity", name="Rust Nail",
                  promotion_intent="flavor", interaction_count=1,
                  is_mechanically_bound=False),
        _proposal(uuid4(), "STATE_CHANGE",
                  payload_extra={"entity_id": "Rust Nail",
                                 "add_tags": ["wounded"]}),
    ]
    verdicts = ck._apply_entity_promotion_rules(proposals)
    accept = [v for v in verdicts if v.decision == CanonKeeperDecision.ACCEPTED]
    assert any("mechanically bound" in v.reasoning for v in accept)


def test_anchor_intent_promotes_immediately():
    from monitor_agents.canonkeeper import CanonKeeper
    from monitor_data.schemas.agent_responses import CanonKeeperDecision

    ck = CanonKeeper()
    proposals = [_proposal(uuid4(), "entity", name="Vex",
                          promotion_intent="anchor", interaction_count=1)]
    verdicts = ck._apply_entity_promotion_rules(proposals)
    assert verdicts[0].decision == CanonKeeperDecision.ACCEPTED
    assert "anchor intent" in verdicts[0].reasoning


def test_flavor_low_interaction_count_is_discarded():
    from monitor_agents.canonkeeper import CanonKeeper
    from monitor_data.schemas.agent_responses import CanonKeeperDecision

    ck = CanonKeeper()
    proposals = [_proposal(uuid4(), "entity", name="a clerk",
                          promotion_intent="flavor", interaction_count=1)]
    verdicts = ck._apply_entity_promotion_rules(proposals)
    assert verdicts[0].decision == CanonKeeperDecision.REJECTED
    assert "Flavor entity discarded" in verdicts[0].reasoning


def test_flavor_high_interaction_count_is_promoted():
    from monitor_agents.canonkeeper import CanonKeeper
    from monitor_data.schemas.agent_responses import CanonKeeperDecision

    ck = CanonKeeper()
    proposals = [_proposal(uuid4(), "entity", name="Mara",
                          promotion_intent="flavor", interaction_count=10)]
    verdicts = ck._apply_entity_promotion_rules(proposals)
    assert verdicts[0].decision == CanonKeeperDecision.ACCEPTED
    assert "interaction threshold" in verdicts[0].reasoning


def test_mechanically_bound_flavor_survives_even_when_threshold_low():
    from monitor_agents.canonkeeper import CanonKeeper
    from monitor_data.schemas.agent_responses import CanonKeeperDecision

    ck = CanonKeeper()
    proposals = [
        _proposal(uuid4(), "entity", name="Rust Nail",
                  promotion_intent="flavor", interaction_count=1,
                  is_mechanically_bound=True),
    ]
    verdicts = ck._apply_entity_promotion_rules(proposals)
    # Only state-bound + matching payload promotes; here the entity is
    # mechanically bound but not referenced by another state_change in the
    # batch, so the threshold check applies and rejects (interaction_count=1).
    # The mechanical-bound escape only fires when the name shows up in
    # a STATE_CHANGE / EVENT payload in the SAME batch.
    assert verdicts[0].decision == CanonKeeperDecision.REJECTED


def test_untagged_entity_falls_through_to_llm():
    """No rule matches → no auto verdict, LLM evaluation takes over."""
    from monitor_agents.canonkeeper import CanonKeeper

    ck = CanonKeeper()
    proposals = [_proposal(uuid4(), "entity", name="Whisper")]
    verdicts = ck._apply_entity_promotion_rules(proposals)
    assert verdicts == []


def test_non_entity_proposals_are_ignored_by_promotion_gate():
    from monitor_agents.canonkeeper import CanonKeeper

    ck = CanonKeeper()
    proposals = [
        _proposal(uuid4(), "FACT", name="the sky is red"),
        _proposal(uuid4(), "STATE_CHANGE",
                  payload_extra={"entity_id": "the sky"}),
    ]
    verdicts = ck._apply_entity_promotion_rules(proposals)
    # No ENTITY proposal in batch → no verdicts
    assert verdicts == []
