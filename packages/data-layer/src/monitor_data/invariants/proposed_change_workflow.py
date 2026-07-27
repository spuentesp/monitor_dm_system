# ruff: noqa: E402
from typing import Any

r"""
Proposed Change Workflow Invariant (INV-6).

This invariant ensures that changes follow the workflow:
    Proposed → CanonKeeper Review → Neo4j Commit

No direct Neo4j writes except from CanonKeeper after review.

Formal Specification:
    ProposedChangeWorkflow ==
        ∧ ∀ pc ∈ ProposedChanges :
            pc.status ∈ {PENDING, UNDER_REVIEW, APPROVED, REJECTED, COMMITTED}
        ∧ ∀ pc ∈ Pending :
            ∃ ck ∈ CanonKeeper : ck.reviews(pc)
        ∧ ∀ pc ∈ COMMITTED :
            ∃ op ∈ Neo4jOps : op.source = pc.id
        ∧ All facts go through ProposedChange workflow

TLA+ Representation:
    VARIABLE proposed_changes: set of proposed changes
    VARIABLE canon_keeper_reviews: set of review records

    ProposedChangeWorkflow ==
        /\ \A pc \in proposed_changes :
            pc.status \in {"pending", "under_review", "approved", "rejected", "committed"}
        /\ \A pc \in proposed_changes :
            pc.status = "committed" =>
                \E ck \in canon_keeper_reviews :
                    ck.proposed_change_id = pc.id /\ ck.decision = "approved"
        /\ \A pc \in proposed_changes :
            pc.status = "pending" \/ pc.status = "under_review" =>
                ~ \E op \in Neo4jOps : op.source = pc.id
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class ProposedChangeStatus(Enum):
    """Status values for proposed changes."""

    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


# Status transitions that require CanonKeeper authority
CANONKEEPER_REQUIRED_TRANSITIONS: frozenset[tuple[ProposedChangeStatus, ProposedChangeStatus]] = frozenset(
    {
        # PENDING can go to UNDER_REVIEW without explicit CK action
        # UNDER_REVIEW requires CK action
        (ProposedChangeStatus.UNDER_REVIEW, ProposedChangeStatus.APPROVED),
        (ProposedChangeStatus.UNDER_REVIEW, ProposedChangeStatus.REJECTED),
        # APPROVED to COMMITTED requires CK commit
        (ProposedChangeStatus.APPROVED, ProposedChangeStatus.COMMITTED),
    }
)

# Valid status transitions
VALID_STATUS_TRANSITIONS: dict[ProposedChangeStatus, frozenset[ProposedChangeStatus]] = {
    ProposedChangeStatus.PENDING: frozenset(
        {
            ProposedChangeStatus.UNDER_REVIEW,
            ProposedChangeStatus.REJECTED,  # Can be rejected without review
        }
    ),
    ProposedChangeStatus.UNDER_REVIEW: frozenset(
        {
            ProposedChangeStatus.APPROVED,
            ProposedChangeStatus.REJECTED,
        }
    ),
    ProposedChangeStatus.APPROVED: frozenset(
        {
            ProposedChangeStatus.COMMITTED,
            ProposedChangeStatus.ROLLED_BACK,  # Can be rolled back before commit
        }
    ),
    ProposedChangeStatus.REJECTED: frozenset(),  # Terminal
    ProposedChangeStatus.COMMITTED: frozenset(),  # Terminal
    ProposedChangeStatus.ROLLED_BACK: frozenset(),  # Terminal
}

# Terminal states (no further transitions)
TERMINAL_STATUSES: frozenset[ProposedChangeStatus] = frozenset(
    {
        ProposedChangeStatus.REJECTED,
        ProposedChangeStatus.COMMITTED,
        ProposedChangeStatus.ROLLED_BACK,
    }
)

# States where change is visible in Neo4j
NEO4J_VISIBLE_STATUSES: frozenset[ProposedChangeStatus] = frozenset(
    {
        ProposedChangeStatus.COMMITTED,
    }
)

# States where change is NOT yet in Neo4j
PENDING_NEO4J_STATUSES: frozenset[ProposedChangeStatus] = frozenset(
    {
        ProposedChangeStatus.PENDING,
        ProposedChangeStatus.UNDER_REVIEW,
        ProposedChangeStatus.APPROVED,
        ProposedChangeStatus.REJECTED,
        ProposedChangeStatus.ROLLED_BACK,
    }
)


@dataclass(frozen=True)
class ProposedChangeBoundary:
    """
    Represents the atomic boundary of a proposed change.

    A proposed change must:
    1. Pass through the review workflow
    2. Be approved by CanonKeeper before commit
    3. Be committed atomically to Neo4j
    """

    change_id: UUID
    change_type: str  # "fact", "entity", "relationship", etc.
    status: ProposedChangeStatus
    created_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    committed_at: datetime | None = None

    @property
    def is_terminal(self) -> bool:
        """Check if change is in terminal state."""
        return self.status in TERMINAL_STATUSES

    @property
    def is_committed(self) -> bool:
        """Check if change has been committed to Neo4j."""
        return self.status == ProposedChangeStatus.COMMITTED

    @property
    def requires_canon_keeper(self) -> bool:
        """Check if current status requires CanonKeeper action."""
        return self.status in {
            ProposedChangeStatus.UNDER_REVIEW,
            ProposedChangeStatus.APPROVED,
        }

    @property
    def is_visible_in_neo4j(self) -> bool:
        """Check if change is visible in Neo4j."""
        return self.status in NEO4J_VISIBLE_STATUSES


class ProposedChangeWorkflow:
    """
    Formal invariant checker for proposed change workflow.

    This ensures:
    1. All changes go through PENDING → UNDER_REVIEW → APPROVED/REJECTED → COMMITTED
    2. Only CanonKeeper can approve or commit
    3. Changes are atomic - all-or-nothing in Neo4j
    """

    @staticmethod
    def is_valid_status(status: ProposedChangeStatus) -> bool:
        """
        Check if status is a valid ProposedChangeStatus.

        Args:
            status: The status to check

        Returns:
            True if status is valid
        """
        return isinstance(status, ProposedChangeStatus)

    @staticmethod
    def is_valid_transition(from_status: ProposedChangeStatus, to_status: ProposedChangeStatus) -> bool:
        """
        Check if status transition is valid.

        Args:
            from_status: Current status
            to_status: Desired new status

        Returns:
            True if transition follows valid workflow
        """
        if from_status == to_status:
            return True  # No-op transition is valid

        valid_next = VALID_STATUS_TRANSITIONS.get(from_status, frozenset())
        return to_status in valid_next

    @staticmethod
    def requires_canon_keeper_action(from_status: ProposedChangeStatus, to_status: ProposedChangeStatus) -> bool:
        """
        Check if transition requires CanonKeeper authority.

        Args:
            from_status: Current status
            to_status: Desired new status

        Returns:
            True if CanonKeeper authority is required
        """
        return (from_status, to_status) in CANONKEEPER_REQUIRED_TRANSITIONS

    @staticmethod
    def can_commit_directly(current_status: ProposedChangeStatus) -> bool:
        """
        Check if changes can be committed directly from current status.

        Args:
            current_status: Current status

        Returns:
            True if direct commit is allowed
        """
        # Only APPROVED changes can be committed
        return current_status == ProposedChangeStatus.APPROVED

    @staticmethod
    def validate_workflow_sequence(changes: list[Any]) -> tuple[bool, str | None]:
        """
        Validate that a sequence of changes follows workflow rules.

        Args:
            changes: List of proposed changes (each should have .status attribute)

        Returns:
            (is_valid, error_message)
        """
        if not changes:
            return True, None  # Empty sequence is valid

        for i, change in enumerate(changes):
            status = change.status if hasattr(change, "status") else change.get("status")

            # Check status is valid
            if not ProposedChangeWorkflow.is_valid_status(status):
                return False, f"Change {i} has invalid status: {status}"

            # Check transitions
            if i > 0:
                prev_status = (
                    changes[i - 1].status if hasattr(changes[i - 1], "status") else changes[i - 1].get("status")
                )
                if not ProposedChangeWorkflow.is_valid_transition(prev_status, status):
                    return False, (
                        f"Invalid workflow transition from {prev_status.value} to {status.value} at change {i}"
                    )

                # Check CanonKeeper requirement
                if ProposedChangeWorkflow.requires_canon_keeper_action(prev_status, status):
                    if not change.reviewed_by:
                        return False, (
                            f"Transition from {prev_status.value} to {status.value} at change {i} "
                            f"requires CanonKeeper review but reviewed_by is None"
                        )

        return True, None

    @staticmethod
    def is_terminal_status(status: ProposedChangeStatus) -> bool:
        """Check if status is terminal."""
        return status in TERMINAL_STATUSES

    @staticmethod
    def is_committed(status: ProposedChangeStatus) -> bool:
        """Check if change has been committed."""
        return status == ProposedChangeStatus.COMMITTED
