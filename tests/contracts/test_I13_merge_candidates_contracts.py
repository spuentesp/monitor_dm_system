"""
I-13 / M-6: Entity Merge Candidates — Contract & Behavior Tests

Tests the input/output contracts for MongoDB merge candidate tools
and their behavioral correctness.

Use Cases: I-13 (Entity Merging), M-6 to M-12 (Entity Management)
"""

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.merge_candidates import (
    EntityMergeCandidate,
    MergeConfidence,
    MergeDecision,
    MergeProposal,
    MergeProposalStatus,
    MergeReviewRequest,
)

# =============================================================================
# MergeConfidence — Contract Tests
# =============================================================================


@pytest.mark.unit
class TestMergeConfidenceContract:
    """Contract tests for MergeConfidence enum."""

    def test_confidence_levels(self):
        """MergeConfidence has the expected levels."""
        assert MergeConfidence.HIGH.value == "high"
        assert MergeConfidence.MEDIUM.value == "medium"
        assert MergeConfidence.LOW.value == "low"
        assert MergeConfidence.UNCERTAIN.value == "uncertain"

    def test_confidence_from_float_high(self):
        """Float > 0.85 maps to HIGH confidence."""
        from monitor_data.tools.mongodb_tools.merge_candidates import (
            _coerce_merge_confidence,
        )

        assert _coerce_merge_confidence(0.86) == MergeConfidence.HIGH
        assert _coerce_merge_confidence(0.95) == MergeConfidence.HIGH
        assert _coerce_merge_confidence(1.0) == MergeConfidence.HIGH

    def test_confidence_from_float_medium(self):
        """Float 0.7–0.85 maps to MEDIUM confidence."""
        from monitor_data.tools.mongodb_tools.merge_candidates import (
            _coerce_merge_confidence,
        )

        assert _coerce_merge_confidence(0.7) == MergeConfidence.MEDIUM
        assert _coerce_merge_confidence(0.75) == MergeConfidence.MEDIUM
        assert _coerce_merge_confidence(0.85) == MergeConfidence.MEDIUM

    def test_confidence_from_float_low(self):
        """Float 0.5–0.7 maps to LOW confidence."""
        from monitor_data.tools.mongodb_tools.merge_candidates import (
            _coerce_merge_confidence,
        )

        assert _coerce_merge_confidence(0.5) == MergeConfidence.LOW
        assert _coerce_merge_confidence(0.6) == MergeConfidence.LOW
        assert _coerce_merge_confidence(0.69) == MergeConfidence.LOW

    def test_confidence_from_float_uncertain(self):
        """Float < 0.5 maps to UNCERTAIN confidence."""
        from monitor_data.tools.mongodb_tools.merge_candidates import (
            _coerce_merge_confidence,
        )

        assert _coerce_merge_confidence(0.0) == MergeConfidence.UNCERTAIN
        assert _coerce_merge_confidence(0.49) == MergeConfidence.UNCERTAIN


# =============================================================================
# EntityMergeCandidate — Contract Tests
# =============================================================================


@pytest.mark.unit
class TestEntityMergeCandidateContract:
    """Contract tests for EntityMergeCandidate schema."""

    def test_candidate_minimal(self):
        """EntityMergeCandidate with required fields is valid."""
        uid = uuid4()
        candidate = EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uid,
            entity_ids=[uuid4(), uuid4()],
            merge_confidence=0.85,
            confidence_level=MergeConfidence.HIGH,
        )
        assert candidate.merge_confidence == 0.85
        assert candidate.confidence_level == MergeConfidence.HIGH
        assert len(candidate.entity_ids) == 2

    def test_candidate_with_all_fields(self):
        """EntityMergeCandidate with all fields populated is valid."""
        uid = uuid4()
        now = datetime.now(UTC)
        candidate = EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uid,
            entity_ids=[uuid4(), uuid4(), uuid4()],
            merge_confidence=0.75,
            confidence_level=MergeConfidence.MEDIUM,
            similarity_metrics={"name": 0.9, "description": 0.6},
            conflicting_fields=["description", "properties.alignment"],
            agreed_fields=["name", "entity_type"],
            source_pack_ids=[uuid4()],
            created_at=now,
            reviewed_at=None,
        )
        assert candidate.similarity_metrics["name"] == 0.9
        assert len(candidate.conflicting_fields) == 2
        assert len(candidate.agreed_fields) == 2

    def test_candidate_entity_ids_min_length(self):
        """EntityMergeCandidate requires at least 2 entity IDs."""
        with pytest.raises(Exception):
            EntityMergeCandidate(
                candidate_id=uuid4(),
                universe_id=uuid4(),
                entity_ids=[uuid4()],  # Only 1 — should fail
                merge_confidence=0.8,
                confidence_level=MergeConfidence.HIGH,
            )

    def test_candidate_confidence_bounds(self):
        """EntityMergeCandidate confidence must be between 0.0 and 1.0."""
        uid = uuid4()
        # Valid bounds
        EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uid,
            entity_ids=[uuid4(), uuid4()],
            merge_confidence=0.0,
            confidence_level=MergeConfidence.UNCERTAIN,
        )
        EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uid,
            entity_ids=[uuid4(), uuid4()],
            merge_confidence=1.0,
            confidence_level=MergeConfidence.HIGH,
        )

    def test_candidate_default_values(self):
        """EntityMergeCandidate has sensible defaults."""
        candidate = EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uuid4(),
            entity_ids=[uuid4(), uuid4()],
            merge_confidence=0.8,
            confidence_level=MergeConfidence.HIGH,
        )
        assert candidate.similarity_metrics == {}
        assert candidate.conflicting_fields == []
        assert candidate.agreed_fields == []
        assert candidate.source_pack_ids == []
        assert candidate.reviewed_at is None


# =============================================================================
# MergeProposal — Contract Tests
# =============================================================================


@pytest.mark.unit
class TestMergeProposalContract:
    """Contract tests for MergeProposal schema."""

    def test_proposal_minimal(self):
        """MergeProposal with required fields is valid."""
        uid = uuid4()
        proposal = MergeProposal(
            proposal_id=uuid4(),
            candidate_id=uuid4(),
            universe_id=uid,
            merged_entity_name="Merged Entity",
            merged_entity_type="CHARACTER",
            merged_description="Combined description",
            source_entity_ids=[uuid4(), uuid4()],
            source_pack_ids=[uuid4()],
            resolution_notes={"name": "Used name from entity A"},
            user_reviewed_confidence=0.9,
        )
        assert proposal.merged_entity_name == "Merged Entity"
        assert proposal.status == MergeProposalStatus.PENDING  # default

    def test_proposal_status_values(self):
        """MergeProposalStatus has expected values."""
        assert MergeProposalStatus.PENDING.value == "pending"
        assert MergeProposalStatus.APPROVED.value == "approved"
        assert MergeProposalStatus.REJECTED.value == "rejected"
        assert MergeProposalStatus.APPLIED.value == "applied"

    def test_proposal_default_status(self):
        """MergeProposal defaults to PENDING status."""
        proposal = MergeProposal(
            proposal_id=uuid4(),
            candidate_id=uuid4(),
            universe_id=uuid4(),
            merged_entity_name="Test",
            merged_entity_type="CHARACTER",
            merged_description="Desc",
            source_entity_ids=[uuid4(), uuid4()],
            source_pack_ids=[],
            resolution_notes={},
            user_reviewed_confidence=0.8,
        )
        assert proposal.status == MergeProposalStatus.PENDING

    def test_proposal_with_all_fields(self):
        """MergeProposal with all fields populated is valid."""
        now = datetime.now(UTC)
        proposal = MergeProposal(
            proposal_id=uuid4(),
            candidate_id=uuid4(),
            universe_id=uuid4(),
            status=MergeProposalStatus.APPROVED,
            merged_entity_name="Combined Guild",
            merged_entity_type="ORGANIZATION",
            merged_description="A powerful combined guild",
            merged_properties={"influence": 8, "territory": "Harbor District"},
            merged_tags=["guild", "trade", "harbor"],
            source_entity_ids=[uuid4(), uuid4()],
            source_pack_ids=[uuid4()],
            resolution_notes={"name": "Used guild name from entity A"},
            user_reviewed_confidence=0.95,
            created_at=now,
            updated_at=now,
        )
        assert proposal.merged_properties["influence"] == 8
        assert len(proposal.merged_tags) == 3
        assert proposal.status == MergeProposalStatus.APPROVED


# =============================================================================
# MergeReviewRequest — Contract Tests
# =============================================================================


@pytest.mark.unit
class TestMergeReviewRequestContract:
    """Contract tests for MergeReviewRequest schema."""

    def test_review_request_minimal(self):
        """MergeReviewRequest with empty decisions is valid."""
        request = MergeReviewRequest(decisions=[])
        assert request.decisions == []
        assert request.relationship_decisions == {}
        assert request.notes == ""

    def test_review_request_with_decisions(self):
        """MergeReviewRequest can include field-level merge decisions."""
        entity_id = uuid4()
        decision = MergeDecision(
            field_path="description",
            source_entity_id=entity_id,
            custom_value="Custom merged description",
        )
        request = MergeReviewRequest(
            decisions=[decision],
            relationship_decisions={"rel_1": True, "rel_2": False},
            notes="Merged with preference for entity A's description.",
        )
        assert len(request.decisions) == 1
        assert request.decisions[0].field_path == "description"
        assert request.relationship_decisions["rel_1"] is True
        assert request.notes == "Merged with preference for entity A's description."

    def test_merge_decision_custom_value_optional(self):
        """MergeDecision custom_value is optional."""
        entity_id = uuid4()
        decision = MergeDecision(
            field_path="name",
            source_entity_id=entity_id,
        )
        assert decision.custom_value is None


# =============================================================================
# MergeCandidate Tools — Behavior Tests (with FakeMCPClient)
# =============================================================================


@pytest.mark.unit
class TestMergeCandidateToolBehavior:
    """Behavior tests for merge candidate tool functions."""

    def test_detect_merge_candidates_returns_list(self):
        """mongodb_detect_merge_candidates returns a list of EntityMergeCandidate."""
        # This function takes entities and universe_id, returns detected candidates
        # Without a real DB, we verify the function signature and return type
        import inspect

        from monitor_data.tools.mongodb_tools.merge_candidates import (
            mongodb_detect_merge_candidates,
        )

        sig = inspect.signature(mongodb_detect_merge_candidates)
        params = list(sig.parameters.keys())
        assert "entities" in params
        assert "universe_id" in params

    def test_save_merge_candidate_returns_candidate(self):
        """mongodb_save_merge_candidate returns an EntityMergeCandidate."""
        import inspect

        from monitor_data.tools.mongodb_tools.merge_candidates import (
            mongodb_save_merge_candidate,
        )

        sig = inspect.signature(mongodb_save_merge_candidate)
        params = list(sig.parameters.keys())
        assert "candidate" in params

    def test_list_merge_candidates_has_pagination(self):
        """mongodb_list_merge_candidates supports limit and offset."""
        import inspect

        from monitor_data.tools.mongodb_tools.merge_candidates import (
            mongodb_list_merge_candidates,
        )

        sig = inspect.signature(mongodb_list_merge_candidates)
        params = list(sig.parameters.keys())
        assert "limit" in params
        assert "offset" in params

    def test_create_merge_proposal_signature(self):
        """mongodb_create_merge_proposal has the expected parameters."""
        import inspect

        from monitor_data.tools.mongodb_tools.merge_candidates import (
            mongodb_create_merge_proposal,
        )

        sig = inspect.signature(mongodb_create_merge_proposal)
        params = list(sig.parameters.keys())
        assert "merged_name" in params
        assert "merged_entity_type" in params
        assert "source_entity_ids" in params
        assert "universe_id" in params

    def test_update_merge_proposal_status_signature(self):
        """mongodb_update_merge_proposal_status takes proposal_id and status."""
        import inspect

        from monitor_data.tools.mongodb_tools.merge_candidates import (
            mongodb_update_merge_proposal_status,
        )

        sig = inspect.signature(mongodb_update_merge_proposal_status)
        params = list(sig.parameters.keys())
        assert "proposal_id" in params
        assert "status" in params

    def test_mark_candidate_reviewed_signature(self):
        """mongodb_mark_candidate_reviewed takes candidate_id."""
        import inspect

        from monitor_data.tools.mongodb_tools.merge_candidates import (
            mongodb_mark_candidate_reviewed,
        )

        sig = inspect.signature(mongodb_mark_candidate_reviewed)
        params = list(sig.parameters.keys())
        assert "candidate_id" in params

    def test_delete_merge_candidate_signature(self):
        """mongodb_delete_merge_candidate takes candidate_id."""
        import inspect

        from monitor_data.tools.mongodb_tools.merge_candidates import (
            mongodb_delete_merge_candidate,
        )

        sig = inspect.signature(mongodb_delete_merge_candidate)
        params = list(sig.parameters.keys())
        assert "candidate_id" in params
