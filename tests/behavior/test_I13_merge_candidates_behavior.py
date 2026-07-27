"""
I-13 / M-6: Entity Merge Candidates — Behavior Tests

Tests the behavioral correctness of merge candidate detection,
proposal creation, and review workflows.

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
# Merge Detection — Behavioral Correctness
# =============================================================================


@pytest.mark.unit
class TestMergeDetectionBehavior:
    """Behavior tests for merge candidate detection logic."""

    def test_confidence_coercion_boundary_values(self):
        """_coerce_merge_confidence handles boundary values correctly."""
        from monitor_data.tools.mongodb_tools.merge_candidates import (
            _coerce_merge_confidence,
        )

        # Exact boundaries (> 0.85 = HIGH, >= 0.7 = MEDIUM, >= 0.5 = LOW)
        assert _coerce_merge_confidence(0.86) == MergeConfidence.HIGH
        assert _coerce_merge_confidence(0.70) == MergeConfidence.MEDIUM
        assert _coerce_merge_confidence(0.50) == MergeConfidence.LOW

        # Just below boundaries
        assert (
            _coerce_merge_confidence(0.85) == MergeConfidence.MEDIUM
        )  # 0.85 is NOT > 0.85
        assert _coerce_merge_confidence(0.69) == MergeConfidence.LOW
        assert _coerce_merge_confidence(0.49) == MergeConfidence.UNCERTAIN

    def test_confidence_coercion_extreme_values(self):
        """_coerce_merge_confidence handles 0.0 and 1.0 correctly."""
        from monitor_data.tools.mongodb_tools.merge_candidates import (
            _coerce_merge_confidence,
        )

        assert _coerce_merge_confidence(0.0) == MergeConfidence.UNCERTAIN
        assert _coerce_merge_confidence(1.0) == MergeConfidence.HIGH

    def test_candidate_requires_two_entities_minimum(self):
        """EntityMergeCandidate requires at least 2 entity IDs for a merge."""
        # Single entity — should fail
        with pytest.raises(Exception):
            EntityMergeCandidate(
                candidate_id=uuid4(),
                universe_id=uuid4(),
                entity_ids=[uuid4()],
                merge_confidence=0.8,
                confidence_level=MergeConfidence.HIGH,
            )

        # Two entities — should succeed
        candidate = EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uuid4(),
            entity_ids=[uuid4(), uuid4()],
            merge_confidence=0.8,
            confidence_level=MergeConfidence.HIGH,
        )
        assert len(candidate.entity_ids) == 2

        # Three entities — should succeed
        candidate = EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uuid4(),
            entity_ids=[uuid4(), uuid4(), uuid4()],
            merge_confidence=0.8,
            confidence_level=MergeConfidence.HIGH,
        )
        assert len(candidate.entity_ids) == 3

    def test_candidate_similarity_metrics_default_empty(self):
        """EntityMergeCandidate similarity_metrics defaults to empty dict."""
        candidate = EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uuid4(),
            entity_ids=[uuid4(), uuid4()],
            merge_confidence=0.8,
            confidence_level=MergeConfidence.HIGH,
        )
        assert candidate.similarity_metrics == {}

    def test_candidate_conflicting_and_agreed_fields(self):
        """EntityMergeCandidate tracks conflicting and agreed fields."""
        candidate = EntityMergeCandidate(
            candidate_id=uuid4(),
            universe_id=uuid4(),
            entity_ids=[uuid4(), uuid4()],
            merge_confidence=0.75,
            confidence_level=MergeConfidence.MEDIUM,
            conflicting_fields=["description", "properties.alignment"],
            agreed_fields=["name", "entity_type"],
        )
        assert "description" in candidate.conflicting_fields
        assert "name" in candidate.agreed_fields


# =============================================================================
# Merge Proposal — Behavioral Correctness
# =============================================================================


@pytest.mark.unit
class TestMergeProposalBehavior:
    """Behavior tests for merge proposal creation and status transitions."""

    def test_proposal_starts_as_pending(self):
        """New MergeProposal defaults to PENDING status."""
        proposal = MergeProposal(
            proposal_id=uuid4(),
            candidate_id=uuid4(),
            universe_id=uuid4(),
            merged_entity_name="Merged Entity",
            merged_entity_type="CHARACTER",
            merged_description="Combined description",
            source_entity_ids=[uuid4(), uuid4()],
            source_pack_ids=[],
            resolution_notes={},
            user_reviewed_confidence=0.9,
        )
        assert proposal.status == MergeProposalStatus.PENDING

    def test_proposal_status_transitions(self):
        """MergeProposalStatus has the expected transition order."""
        # PENDING → APPROVED → APPLIED
        # PENDING → REJECTED
        assert MergeProposalStatus.PENDING.value == "pending"
        assert MergeProposalStatus.APPROVED.value == "approved"
        assert MergeProposalStatus.REJECTED.value == "rejected"
        assert MergeProposalStatus.APPLIED.value == "applied"

    def test_proposal_with_merged_properties(self):
        """MergeProposal can include merged properties from source entities."""
        proposal = MergeProposal(
            proposal_id=uuid4(),
            candidate_id=uuid4(),
            universe_id=uuid4(),
            merged_entity_name="Combined Guild",
            merged_entity_type="ORGANIZATION",
            merged_description="A powerful combined guild",
            merged_properties={"influence": 8, "territory": "Harbor District"},
            merged_tags=["guild", "trade", "harbor"],
            source_entity_ids=[uuid4(), uuid4()],
            source_pack_ids=[uuid4()],
            resolution_notes={"name": "Used guild name from entity A"},
            user_reviewed_confidence=0.95,
        )
        assert proposal.merged_properties["influence"] == 8
        assert "guild" in proposal.merged_tags

    def test_proposal_resolution_notes(self):
        """MergeProposal resolution_notes captures field-level decisions."""
        notes = {
            "name": "Used name from entity A (more specific)",
            "description": "Combined descriptions",
            "alignment": "Kept entity A's alignment (lawful good)",
        }
        proposal = MergeProposal(
            proposal_id=uuid4(),
            candidate_id=uuid4(),
            universe_id=uuid4(),
            merged_entity_name="Test",
            merged_entity_type="CHARACTER",
            merged_description="Desc",
            source_entity_ids=[uuid4(), uuid4()],
            source_pack_ids=[],
            resolution_notes=notes,
            user_reviewed_confidence=0.85,
        )
        assert "name" in proposal.resolution_notes
        assert "alignment" in proposal.resolution_notes


# =============================================================================
# Merge Review — Behavioral Correctness
# =============================================================================


@pytest.mark.unit
class TestMergeReviewBehavior:
    """Behavior tests for merge review request workflow."""

    def test_review_with_field_decisions(self):
        """MergeReviewRequest can specify which source entity to use per field."""
        entity_a = uuid4()
        decision = MergeDecision(
            field_path="description",
            source_entity_id=entity_a,
            custom_value="A detailed description combining both sources.",
        )
        request = MergeReviewRequest(
            decisions=[decision],
            relationship_decisions={"rel_1": True, "rel_2": False},
            notes="Prefer entity A's description for richness.",
        )
        assert len(request.decisions) == 1
        assert request.decisions[0].source_entity_id == entity_a
        assert request.relationship_decisions["rel_1"] is True
        assert request.relationship_decisions["rel_2"] is False

    def test_review_with_no_decisions(self):
        """MergeReviewRequest can be empty (auto-merge with defaults)."""
        request = MergeReviewRequest(decisions=[])
        assert request.decisions == []
        assert request.relationship_decisions == {}
        assert request.notes == ""

    def test_review_with_custom_value(self):
        """MergeDecision can specify a custom value for a field."""
        entity_id = uuid4()
        decision = MergeDecision(
            field_path="name",
            source_entity_id=entity_id,
            custom_value="The Combined Guild of Merchants",
        )
        assert decision.custom_value == "The Combined Guild of Merchants"
        assert decision.field_path == "name"

    def test_review_without_custom_value(self):
        """MergeDecision without custom_value uses source entity's value."""
        entity_id = uuid4()
        decision = MergeDecision(
            field_path="name",
            source_entity_id=entity_id,
        )
        assert decision.custom_value is None
        # The merge logic should use the source entity's value for this field


# =============================================================================
# Merge Candidate Document Conversion — Behavioral Correctness
# =============================================================================


@pytest.mark.unit
class TestMergeCandidateDocConversion:
    """Behavior tests for MongoDB document ↔ model conversion."""

    def test_convert_candidate_doc_to_model(self):
        """_convert_candidate_doc_to_model correctly maps MongoDB doc to model."""
        from monitor_data.tools.mongodb_tools.merge_candidates import (
            _convert_candidate_doc_to_model,
        )

        uid = uuid4()
        eid1 = uuid4()
        eid2 = uuid4()
        cid = uuid4()
        now = datetime.now(UTC)

        doc = {
            "candidate_id": str(cid),
            "universe_id": str(uid),
            "entity_ids": [str(eid1), str(eid2)],
            "merge_confidence": 0.90,  # > 0.85 → HIGH
            "confidence_level": "high",
            "similarity_metrics": {"name": 0.95, "description": 0.7},
            "conflicting_fields": ["description"],
            "agreed_fields": ["name", "entity_type"],
            "source_pack_ids": [],
            "created_at": now,
            "reviewed_at": None,
        }

        result = _convert_candidate_doc_to_model(doc)
        assert result.candidate_id == cid
        assert result.universe_id == uid
        assert len(result.entity_ids) == 2
        assert result.merge_confidence == 0.90
        assert result.confidence_level == MergeConfidence.HIGH
        assert result.similarity_metrics["name"] == 0.95
        assert "description" in result.conflicting_fields
        assert "name" in result.agreed_fields
