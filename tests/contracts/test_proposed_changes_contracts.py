"""
Contract tests for ProposedChange schemas (CanonKeeper).

Covers:
- Evidence: supporting evidence for a proposal
- DecisionMetadata: CanonKeeper's decision
- ProposedChangeCreate: create proposal
- ProposedChangeUpdate: update with decision
- ProposedChangeResponse: full response
- ProposalStatus enum
- ProposalType enum

Use Cases: SYS-3 (CanonKeeper authority)
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.base import Authority, ProposalStatus, ProposalType
from monitor_data.schemas.proposed_changes import (
    DecisionMetadata,
    Evidence,
    ProposedChangeCreate,
    ProposedChangeFilter,
    ProposedChangeResponse,
    ProposedChangeUpdate,
)

# =============================================================================
# Enums
# =============================================================================


class TestProposalStatusEnum:
    def test_all_values(self):
        assert ProposalStatus.PENDING.value == "pending"
        assert ProposalStatus.ACCEPTED.value == "accepted"
        assert ProposalStatus.REJECTED.value == "rejected"


class TestProposalTypeEnum:
    def test_all_values(self):
        assert ProposalType.FACT.value == "fact"
        assert ProposalType.ENTITY.value == "entity"
        assert ProposalType.RELATIONSHIP.value == "relationship"
        assert ProposalType.STATE_CHANGE.value == "state_change"
        assert ProposalType.EVENT.value == "event"
        assert ProposalType.MECHANIC.value == "mechanic"


# =============================================================================
# Evidence
# =============================================================================


class TestEvidence:
    def test_turn(self):
        e = Evidence(type="turn", ref_id=uuid4())
        assert e.type == "turn"

    def test_snippet(self):
        e = Evidence(type="snippet", ref_id=uuid4())
        assert e.type == "snippet"

    def test_source(self):
        e = Evidence(type="source", ref_id=uuid4())
        assert e.type == "source"

    def test_rule(self):
        e = Evidence(type="rule", ref_id=uuid4())
        assert e.type == "rule"

    def test_invalid_type_fails(self):
        with pytest.raises(Exception):
            Evidence(type="invalid", ref_id=uuid4())


# =============================================================================
# DecisionMetadata
# =============================================================================


class TestDecisionMetadata:
    def test_minimal(self):
        m = DecisionMetadata(
            decided_by="CanonKeeper",
            decided_at=datetime.now(UTC),
            reason="Consistent with prior canon",
        )
        assert m.decided_by == "CanonKeeper"
        assert m.canonical_ref is None  # default

    def test_with_canonical_ref(self):
        m = DecisionMetadata(
            decided_by="CanonKeeper",
            decided_at=datetime.now(UTC),
            reason="Accepted",
            canonical_ref=uuid4(),
        )
        assert m.canonical_ref is not None


# =============================================================================
# ProposedChangeCreate
# =============================================================================


class TestProposedChangeCreate:
    def test_with_scene(self):
        req = ProposedChangeCreate(
            scene_id=uuid4(),
            change_type=ProposalType.FACT,
            content={"statement": "Arthur is king"},
        )
        assert req.scene_id is not None
        assert req.story_id is None
        assert req.confidence == 1.0  # default
        assert req.authority == Authority.SYSTEM  # default
        assert req.proposer == "Unknown"  # default

    def test_with_story(self):
        req = ProposedChangeCreate(
            story_id=uuid4(),
            change_type=ProposalType.ENTITY,
            content={"name": "Bob", "entity_type": "character"},
        )
        assert req.story_id is not None
        assert req.scene_id is None

    def test_requires_scene_or_story(self):
        with pytest.raises(Exception):
            ProposedChangeCreate(
                change_type=ProposalType.FACT,
                content={"x": 1},
            )

    def test_with_evidence(self):
        eid = uuid4()
        req = ProposedChangeCreate(
            scene_id=uuid4(),
            change_type=ProposalType.FACT,
            content={"statement": "x"},
            evidence=[Evidence(type="turn", ref_id=eid)],
        )
        assert len(req.evidence) == 1

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            ProposedChangeCreate(
                scene_id=uuid4(),
                change_type=ProposalType.FACT,
                content={"x": 1},
                confidence=1.5,
            )

    def test_authority(self):
        req = ProposedChangeCreate(
            scene_id=uuid4(),
            change_type=ProposalType.FACT,
            content={"x": 1},
            authority=Authority.GM,
            proposer="Narrator",
        )
        assert req.authority == Authority.GM
        assert req.proposer == "Narrator"


# =============================================================================
# ProposedChangeUpdate
# =============================================================================


class TestProposedChangeUpdate:
    def test_accept(self):
        meta = DecisionMetadata(
            decided_by="CanonKeeper",
            decided_at=datetime.now(UTC),
            reason="OK",
        )
        upd = ProposedChangeUpdate(
            status=ProposalStatus.ACCEPTED,
            decision_metadata=meta,
        )
        assert upd.status == ProposalStatus.ACCEPTED
        assert upd.decision_metadata.reason == "OK"

    def test_reject(self):
        meta = DecisionMetadata(
            decided_by="CanonKeeper",
            decided_at=datetime.now(UTC),
            reason="Contradicts established canon",
        )
        upd = ProposedChangeUpdate(
            status=ProposalStatus.REJECTED,
            decision_metadata=meta,
        )
        assert upd.status == ProposalStatus.REJECTED


# =============================================================================
# ProposedChangeResponse
# =============================================================================


class TestProposedChangeResponse:
    def test_minimal(self):
        resp = ProposedChangeResponse(
            proposal_id=uuid4(),
            scene_id=uuid4(),
            change_type=ProposalType.FACT,
            content={"x": 1},
            confidence=0.9,
            authority=Authority.SYSTEM,
            proposer="Narrator",
            status=ProposalStatus.PENDING,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert resp.proposal_id
        assert resp.decision_metadata is None  # default
        assert resp.evidence == []  # default


# =============================================================================
# ProposedChangeFilter
# =============================================================================


class TestProposedChangeFilter:
    def test_empty(self):
        f = ProposedChangeFilter()
        assert f.scene_id is None
        assert f.status is None

    def test_with_filters(self):
        f = ProposedChangeFilter(
            scene_id=uuid4(),
            status=ProposalStatus.PENDING,
        )
        assert f.scene_id is not None
        assert f.status == ProposalStatus.PENDING
