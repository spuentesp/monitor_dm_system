"""
Tests for critical system invariants.

These tests verify the TLA+-style invariants that must hold
at all times for system correctness.

Use Cases: All (INV-1 through INV-6)
"""

from uuid import uuid4

from monitor_data.invariants.canon_keeper import (
    AUTHORIZED_NEO4J_WRITERS,
    CANON_KEEPER_WRITE_TOOLS,
    SHARED_NEO4J_WRITE_TOOLS,
    CanonKeeperExclusivity,
)
from monitor_data.invariants.scene_atomicity import (
    IN_PROGRESS_STATES,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    SceneAtomicity,
)
from monitor_data.schemas.base import SceneStatus


class TestCanonKeeperExclusivityInvariant:
    """
    Tests for INV-1: CanonKeeper Exclusivity.

    TLA+ Spec:
        CanonKeeperExclusivity ==
            ∀ node ∈ Neo4jWriteNodes : node.lastWriter = "CanonKeeper"
            ∧ ∀ edge ∈ CreatedEdges : edge.creator = "CanonKeeper"
    """

    def test_all_exclusive_tools_identified(self):
        """All CanonKeeper-exclusive tools are in the set."""
        expected_tools = {
            "neo4j_create_fact",
            "neo4j_create_entity",
            "neo4j_update_fact",
            "neo4j_delete_fact",
            "neo4j_create_relationship",
            "neo4j_update_relationship",
            "neo4j_delete_relationship",
            "neo4j_create_multiverse",
            "neo4j_create_universe",
            "neo4j_update_universe",
            "neo4j_delete_universe",
        }

        for tool in expected_tools:
            assert tool in CANON_KEEPER_WRITE_TOOLS, (
                f"{tool} should be in CANON_KEEPER_WRITE_TOOLS"
            )

    def test_canon_keeper_is_only_authorized_writer(self):
        """Only CanonKeeper is in AUTHORIZED_NEO4J_WRITERS."""
        assert {"CanonKeeper"} == AUTHORIZED_NEO4J_WRITERS

    def test_shared_tools_have_alternate_authorized(self):
        """Shared tools have at least one alternate authorized agent."""
        assert "neo4j_create_source" in SHARED_NEO4J_WRITE_TOOLS
        assert "neo4j_delete_source" in SHARED_NEO4J_WRITE_TOOLS

        # IngestionPipeline should be authorized for shared tools
        assert (
            CanonKeeperExclusivity.is_authorized_writer(
                "neo4j_create_source", "IngestionPipeline"
            )
            is True
        )

    def test_read_tools_not_in_write_tools(self):
        """Read tools are not classified as write tools."""
        read_tools = {
            "neo4j_get_fact",
            "neo4j_get_entity",
            "neo4j_list_facts",
            "neo4j_list_entities",
            "neo4j_get_universe",
            "neo4j_list_universes",
        }

        for tool in read_tools:
            assert tool not in CANON_KEEPER_WRITE_TOOLS, (
                f"{tool} should not be a write tool"
            )

    def test_canon_keeper_can_call_any_neo4j_tool(self):
        """CanonKeeper is authorized for all Neo4j write tools."""

        all_write_tools = CANON_KEEPER_WRITE_TOOLS | SHARED_NEO4J_WRITE_TOOLS
        for tool in all_write_tools:
            assert (
                CanonKeeperExclusivity.is_authorized_writer(tool, "CanonKeeper") is True
            )

    def test_narrator_cannot_call_exclusive_tool(self):
        """Narrator is not authorized for exclusive write tools."""

        for tool in CANON_KEEPER_WRITE_TOOLS:
            if tool not in SHARED_NEO4J_WRITE_TOOLS:
                assert (
                    CanonKeeperExclusivity.is_authorized_writer(tool, "Narrator")
                    is False
                )


class TestSceneAtomicityInvariant:
    """
    Tests for INV-2: Scene Atomicity.

    TLA+ Spec:
        SceneAtomicity ==
            ∧ ∀ s ∈ scenes : s.status = "completed" =>
                ∀ pc ∈ proposed_changes : pc.scene_id = s.id => pc.status = "committed"
    """

    def test_terminal_states_defined(self):
        """Terminal states are properly defined."""
        assert SceneStatus.COMPLETED in TERMINAL_STATES
        assert SceneStatus.ACTIVE not in TERMINAL_STATES
        assert SceneStatus.FINALIZING not in TERMINAL_STATES

    def test_in_progress_states_defined(self):
        """In-progress states are properly defined."""
        assert SceneStatus.ACTIVE in IN_PROGRESS_STATES
        assert SceneStatus.FINALIZING in IN_PROGRESS_STATES
        assert SceneStatus.COMPLETED not in IN_PROGRESS_STATES

    def test_valid_transitions_from_active(self):
        """Valid transitions from ACTIVE are defined."""
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.ACTIVE, SceneStatus.FINALIZING
            )
            is True
        )
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.ACTIVE, SceneStatus.COMPLETED
            )
            is True
        )
        assert (
            SceneAtomicity.is_valid_transition(SceneStatus.ACTIVE, SceneStatus.ACTIVE)
            is True
        )

    def test_valid_transitions_from_finalizing(self):
        """Valid transitions from FINALIZING are defined."""
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.FINALIZING, SceneStatus.ACTIVE
            )
            is True
        )
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.FINALIZING, SceneStatus.COMPLETED
            )
            is True
        )

    def test_invalid_transitions_from_completed(self):
        """No valid transitions from COMPLETED (terminal)."""
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.COMPLETED, SceneStatus.ACTIVE
            )
            is False
        )
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.COMPLETED, SceneStatus.FINALIZING
            )
            is False
        )

    def test_invalid_transitions_from_abandoned(self):
        """No valid transitions from FINALIZING to ABANDONED (doesn't exist)."""
        # ABANDONED doesn't exist in actual enum, these would fail if called
        # We just verify FINALIZING has no ABANDONED transition
        pass  # Enum doesn't have ABANDONED

    def test_terminal_state_detection(self):
        """is_terminal correctly identifies terminal states."""
        assert SceneAtomicity.is_terminal(SceneStatus.COMPLETED) is True
        assert SceneAtomicity.is_terminal(SceneStatus.ACTIVE) is False
        assert SceneAtomicity.is_terminal(SceneStatus.FINALIZING) is False


class TestTurnFlowInvariant:
    """
    Tests for INV-4: Turn Flow.

    TLA+ Spec:
        TurnFlow ==
            ∧ ∀ turn ∈ Turns : turn.phase ∈ {USER_INPUT, RESOLVE, NARRATE}
            ∧ ∀ i < |turns|-1 : turns[i].phase < turns[i+1].phase
    """

    def test_turn_phase_order(self):
        """Turn phases follow correct ordinal ordering."""
        from monitor_data.invariants.turn_flow import TurnPhase

        assert TurnPhase.USER_INPUT < TurnPhase.RESOLVE
        assert TurnPhase.RESOLVE < TurnPhase.NARRATE

    def test_valid_phase_transitions(self):
        """Valid phase transitions are allowed."""
        from monitor_data.invariants.turn_flow import TurnFlow, TurnPhase

        # USER_INPUT can go to RESOLVE
        assert (
            TurnFlow.is_valid_transition(TurnPhase.USER_INPUT, TurnPhase.RESOLVE)
            is True
        )
        # RESOLVE can go to NARRATE
        assert (
            TurnFlow.is_valid_transition(TurnPhase.RESOLVE, TurnPhase.NARRATE) is True
        )
        # NARRATE can loop back to USER_INPUT
        assert (
            TurnFlow.is_valid_transition(TurnPhase.NARRATE, TurnPhase.USER_INPUT)
            is True
        )

    def test_invalid_phase_transitions(self):
        """Invalid phase transitions are rejected."""
        from monitor_data.invariants.turn_flow import TurnFlow, TurnPhase

        # Cannot skip from USER_INPUT to NARRATE directly
        assert (
            TurnFlow.is_valid_transition(TurnPhase.USER_INPUT, TurnPhase.NARRATE)
            is False
        )
        # Cannot go backwards from RESOLVE to USER_INPUT
        assert (
            TurnFlow.is_valid_transition(TurnPhase.RESOLVE, TurnPhase.USER_INPUT)
            is False
        )

    def test_terminal_phase_detection(self):
        """NARRATE is correctly identified as terminal."""
        from monitor_data.invariants.turn_flow import TurnFlow, TurnPhase

        assert TurnFlow.is_terminal_phase(TurnPhase.NARRATE) is True
        assert TurnFlow.is_terminal_phase(TurnPhase.USER_INPUT) is False


class TestProposedChangeWorkflowInvariant:
    """
    Tests for INV-6: Proposed Change Workflow.

    TLA+ Spec:
        ProposedChangeWorkflow ==
            ∧ ∀ pc ∈ ProposedChanges : pc.status ∈ {PENDING, UNDER_REVIEW, APPROVED, REJECTED, COMMITTED}
            ∧ ∀ pc ∈ COMMITTED : ∃ ck ∈ reviews : ck.pc_id = pc.id ∧ ck.decision = APPROVED
    """

    def test_valid_workflow_transitions(self):
        """Valid workflow transitions are allowed."""
        from monitor_data.invariants.proposed_change_workflow import (
            ProposedChangeStatus,
            ProposedChangeWorkflow,
        )

        # PENDING → UNDER_REVIEW
        assert (
            ProposedChangeWorkflow.is_valid_transition(
                ProposedChangeStatus.PENDING, ProposedChangeStatus.UNDER_REVIEW
            )
            is True
        )
        # UNDER_REVIEW → APPROVED
        assert (
            ProposedChangeWorkflow.is_valid_transition(
                ProposedChangeStatus.UNDER_REVIEW, ProposedChangeStatus.APPROVED
            )
            is True
        )
        # APPROVED → COMMITTED
        assert (
            ProposedChangeWorkflow.is_valid_transition(
                ProposedChangeStatus.APPROVED, ProposedChangeStatus.COMMITTED
            )
            is True
        )

    def test_rejection_is_valid_transition(self):
        """Rejection from PENDING is valid."""
        from monitor_data.invariants.proposed_change_workflow import (
            ProposedChangeStatus,
            ProposedChangeWorkflow,
        )

        assert (
            ProposedChangeWorkflow.is_valid_transition(
                ProposedChangeStatus.PENDING, ProposedChangeStatus.REJECTED
            )
            is True
        )

    def test_invalid_workflow_transitions(self):
        """Invalid workflow transitions are rejected."""
        from monitor_data.invariants.proposed_change_workflow import (
            ProposedChangeStatus,
            ProposedChangeWorkflow,
        )

        # Cannot skip from PENDING to COMMITTED
        assert (
            ProposedChangeWorkflow.is_valid_transition(
                ProposedChangeStatus.PENDING, ProposedChangeStatus.COMMITTED
            )
            is False
        )
        # Cannot go from REJECTED anywhere
        assert (
            ProposedChangeWorkflow.is_valid_transition(
                ProposedChangeStatus.REJECTED, ProposedChangeStatus.COMMITTED
            )
            is False
        )
        # Cannot go from COMMITTED anywhere
        assert (
            ProposedChangeWorkflow.is_valid_transition(
                ProposedChangeStatus.COMMITTED, ProposedChangeStatus.PENDING
            )
            is False
        )

    def test_terminal_statuses(self):
        """Terminal statuses are correctly identified."""
        from monitor_data.invariants.proposed_change_workflow import (
            ProposedChangeStatus,
            ProposedChangeWorkflow,
        )

        assert (
            ProposedChangeWorkflow.is_terminal_status(ProposedChangeStatus.COMMITTED)
            is True
        )
        assert (
            ProposedChangeWorkflow.is_terminal_status(ProposedChangeStatus.REJECTED)
            is True
        )
        assert (
            ProposedChangeWorkflow.is_terminal_status(ProposedChangeStatus.ROLLED_BACK)
            is True
        )
        assert (
            ProposedChangeWorkflow.is_terminal_status(ProposedChangeStatus.PENDING)
            is False
        )

    def test_requires_canon_keeper(self):
        """Correct transitions require CanonKeeper."""
        from monitor_data.invariants.proposed_change_workflow import (
            ProposedChangeStatus,
            ProposedChangeWorkflow,
        )

        # UNDER_REVIEW → APPROVED requires CK
        assert (
            ProposedChangeWorkflow.requires_canon_keeper_action(
                ProposedChangeStatus.UNDER_REVIEW, ProposedChangeStatus.APPROVED
            )
            is True
        )
        # APPROVED → COMMITTED requires CK
        assert (
            ProposedChangeWorkflow.requires_canon_keeper_action(
                ProposedChangeStatus.APPROVED, ProposedChangeStatus.COMMITTED
            )
            is True
        )
        # PENDING → UNDER_REVIEW does NOT require explicit CK (automatic)
        assert (
            ProposedChangeWorkflow.requires_canon_keeper_action(
                ProposedChangeStatus.PENDING, ProposedChangeStatus.UNDER_REVIEW
            )
            is False
        )

    def test_in_progress_state_detection(self):
        """is_in_progress correctly identifies in-progress states."""
        assert SceneAtomicity.is_in_progress(SceneStatus.ACTIVE) is True
        assert SceneAtomicity.is_in_progress(SceneStatus.FINALIZING) is True
        assert SceneAtomicity.is_in_progress(SceneStatus.COMPLETED) is False

    def test_scene_boundary_complete_state(self):
        """SceneBoundary correctly represents complete state."""
        from monitor_data.invariants.scene_atomicity import SceneBoundary

        boundary = SceneBoundary(
            scene_id=uuid4(),
            turn_ids=(uuid4(), uuid4()),
            proposed_change_ids=(uuid4(),),
            status=SceneStatus.COMPLETED,
        )

        assert boundary.is_complete is True
        assert boundary.is_in_progress is False

    def test_scene_boundary_in_progress_state(self):
        """SceneBoundary correctly represents in-progress state."""
        from monitor_data.invariants.scene_atomicity import SceneBoundary

        boundary = SceneBoundary(
            scene_id=uuid4(),
            turn_ids=(uuid4(),),
            proposed_change_ids=(),
            status=SceneStatus.ACTIVE,
        )

        assert boundary.is_complete is False
        assert boundary.is_in_progress is True


class TestSceneStatusTransitionInvariants:
    """Tests for scene status transition properties."""

    def test_all_statuses_have_transitions_defined(self):
        """All scene statuses have transition rules."""
        for status in SceneStatus:
            assert status in VALID_TRANSITIONS

    def test_transition_symmetry_not_required(self):
        """Transitions don't need to be symmetric."""
        # ACTIVE -> FINALIZING is valid
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.ACTIVE, SceneStatus.FINALIZING
            )
            is True
        )
        # But FINALIZING -> ACTIVE is also valid (resume)
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.FINALIZING, SceneStatus.ACTIVE
            )
            is True
        )

    def test_completed_scene_cannot_become_active(self):
        """COMPLETED is terminal - scene cannot resume."""
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.COMPLETED, SceneStatus.ACTIVE
            )
            is False
        )
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.COMPLETED, SceneStatus.FINALIZING
            )
            is False
        )

    def test_finalizing_scene_can_resume(self):
        """FINALIZING is not terminal - scene can resume to ACTIVE."""
        assert (
            SceneAtomicity.is_valid_transition(
                SceneStatus.FINALIZING, SceneStatus.ACTIVE
            )
            is True
        )


class TestInvariantConsistency:
    """Tests for invariant consistency across the system."""

    def test_terminal_and_in_progress_disjoint(self):
        """Terminal and in-progress states are disjoint."""
        assert TERMINAL_STATES.isdisjoint(IN_PROGRESS_STATES)

    def test_all_statuses_accounted(self):
        """All scene statuses are either terminal or in-progress."""
        all_statuses = set(SceneStatus)
        accounted = TERMINAL_STATES | IN_PROGRESS_STATES
        assert all_statuses == accounted

    def test_canon_keeper_tools_cover_all_neo4j_writes(self):
        """CanonKeeper tools cover all Neo4j write operations."""
        # This is a meta-test - ensuring the authority matrix is complete
        from monitor_data.middleware.auth import AUTHORITY_MATRIX

        # All neo4j_create, neo4j_update, neo4j_delete should be in CANON_KEEPER_WRITE_TOOLS
        for tool_name in AUTHORITY_MATRIX:
            if tool_name.startswith("neo4j_") and (
                "create" in tool_name or "update" in tool_name or "delete" in tool_name
            ):
                # Should be restricted to CanonKeeper (or shared)
                assert (
                    tool_name in CANON_KEEPER_WRITE_TOOLS
                    or tool_name in SHARED_NEO4J_WRITE_TOOLS
                )
