"""Contract tests for the AgentResponse schemas.

Verifies that agent_responses Pydantic models:
- instantiate with valid data,
- enforce required fields and min/max length constraints,
- enforce enum membership for success levels and decisions.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from monitor_data.schemas.agent_responses import (
    CanonKeeperDecision,
    CanonKeeperVerdict,
    NarratorResponse,
    ProposedChangeRef,
    ResolverOutcome,
    ResolverSuccessLevel,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


# =============================================================================
# ProposedChangeRef
# =============================================================================


class TestProposedChangeRef:
    def test_minimal(self):
        ref = ProposedChangeRef(change_type="entity_create", summary="new NPC")
        assert ref.change_type == "entity_create"
        assert ref.summary == "new NPC"
        assert ref.content == {}
        # proposal_id is auto-generated
        assert ref.proposal_id is not None

    def test_with_id(self):
        pid = uuid4()
        ref = ProposedChangeRef(
            proposal_id=pid,
            change_type="fact_add",
            summary="a fact",
            content={"key": "v"},
        )
        assert ref.proposal_id == pid
        assert ref.content == {"key": "v"}

    def test_summary_too_long(self):
        with pytest.raises(ValidationError):
            ProposedChangeRef(change_type="x", summary="y" * 501)

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ProposedChangeRef(change_type="x")  # type: ignore[call-arg]


# =============================================================================
# NarratorResponse
# =============================================================================


class TestNarratorResponse:
    def test_minimal(self):
        r = NarratorResponse(narrative_text="The party enters the tavern.")
        assert r.narrative_text == "The party enters the tavern."
        assert r.proposals == []
        assert r.mood is None

    def test_with_proposals(self):
        r = NarratorResponse(
            narrative_text="Bartender introduces himself.",
            proposals=[
                ProposedChangeRef(change_type="entity_create", summary="new bartender")
            ],
            mood="whimsical",
        )
        assert len(r.proposals) == 1
        assert r.mood == "whimsical"

    def test_mood_too_long(self):
        with pytest.raises(ValidationError):
            NarratorResponse(narrative_text="x", mood="y" * 51)

    def test_empty_narrative_rejected(self):
        with pytest.raises(ValidationError):
            NarratorResponse(narrative_text="")

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            NarratorResponse()  # type: ignore[call-arg]


# =============================================================================
# ResolverSuccessLevel
# =============================================================================


class TestResolverSuccessLevel:
    def test_values(self):
        assert ResolverSuccessLevel.CRITICAL_SUCCESS.value == "critical_success"
        assert ResolverSuccessLevel.SUCCESS.value == "success"
        assert ResolverSuccessLevel.PARTIAL_SUCCESS.value == "partial_success"
        assert ResolverSuccessLevel.FAILURE.value == "failure"
        assert ResolverSuccessLevel.CRITICAL_FAILURE.value == "critical_failure"


# =============================================================================
# ResolverOutcome
# =============================================================================


class TestResolverOutcome:
    def test_minimal(self):
        o = ResolverOutcome(
            success_level=ResolverSuccessLevel.SUCCESS,
            narration_hint="The attack lands solidly.",
        )
        assert o.success_level == ResolverSuccessLevel.SUCCESS
        assert o.roll_total is None
        assert o.roll_breakdown is None
        assert o.effects == []
        assert o.proposals == []

    def test_with_roll(self):
        o = ResolverOutcome(
            success_level=ResolverSuccessLevel.CRITICAL_SUCCESS,
            roll_total=18,
            roll_breakdown="2d6+3 = 6+6+3 = 15",
            effects=["12 damage", "knockdown"],
            narration_hint="A devastating blow.",
        )
        assert o.roll_total == 18
        assert "knockdown" in o.effects

    def test_roll_breakdown_too_long(self):
        with pytest.raises(ValidationError):
            ResolverOutcome(
                success_level=ResolverSuccessLevel.SUCCESS,
                narration_hint="x",
                roll_breakdown="y" * 201,
            )

    def test_narration_hint_too_long(self):
        with pytest.raises(ValidationError):
            ResolverOutcome(
                success_level=ResolverSuccessLevel.SUCCESS,
                narration_hint="x" * 501,
            )

    def test_invalid_success_level(self):
        with pytest.raises(ValidationError):
            ResolverOutcome(
                success_level="bogus",  # type: ignore[arg-type]
                narration_hint="x",
            )

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            ResolverOutcome()  # type: ignore[call-arg]


# =============================================================================
# CanonKeeperDecision
# =============================================================================


class TestCanonKeeperDecision:
    def test_values(self):
        assert CanonKeeperDecision.ACCEPTED.value == "accepted"
        assert CanonKeeperDecision.REJECTED.value == "rejected"
        assert CanonKeeperDecision.DEFERRED.value == "deferred"


# =============================================================================
# CanonKeeperVerdict
# =============================================================================


class TestCanonKeeperVerdict:
    def test_minimal(self):
        pid = uuid4()
        v = CanonKeeperVerdict(
            proposal_id=pid,
            decision=CanonKeeperDecision.ACCEPTED,
            reasoning="This is a complete and consistent proposal.",
        )
        assert v.proposal_id == pid
        assert v.decision == CanonKeeperDecision.ACCEPTED
        assert v.canon_node_type is None
        assert v.canon_properties is None
        assert isinstance(v.decided_at, datetime)

    def test_with_canon(self):
        v = CanonKeeperVerdict(
            proposal_id=uuid4(),
            decision=CanonKeeperDecision.ACCEPTED,
            reasoning="Accepting to canonise this NPC.",
            canon_node_type="EntityInstance",
            canon_properties={"name": "Bob", "role": "innkeeper"},
        )
        assert v.canon_node_type == "EntityInstance"
        assert v.canon_properties == {"name": "Bob", "role": "innkeeper"}

    def test_reasoning_too_short(self):
        with pytest.raises(ValidationError):
            CanonKeeperVerdict(
                proposal_id=uuid4(),
                decision=CanonKeeperDecision.REJECTED,
                reasoning="too short",  # < 10 chars
            )

    def test_reasoning_too_long(self):
        with pytest.raises(ValidationError):
            CanonKeeperVerdict(
                proposal_id=uuid4(),
                decision=CanonKeeperDecision.REJECTED,
                reasoning="x" * 2001,
            )

    def test_invalid_decision(self):
        with pytest.raises(ValidationError):
            CanonKeeperVerdict(
                proposal_id=uuid4(),
                decision="bogus",  # type: ignore[arg-type]
                reasoning="this is a long enough reasoning",
            )

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            CanonKeeperVerdict()  # type: ignore[call-arg]
