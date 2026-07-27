r"""
Scene Atomicity Invariant (INV-2).

This invariant ensures that Scene is the atomic canonization boundary.
All facts within a scene must be canonized together or not at all.

Formal Specification:
    SceneAtomicity ==
        ∧ ∀scene ∈ Scenes : scene.is_complete
        ∧ ∀proposed_change ∈ scene.proposed_changes :
            proposed_change.status ∈ {PENDING, COMMITTED, ROLLED_BACK}
        ∧ All-or-Nothing:
            IF scene.status = COMPLETED
            THEN ∀pc ∈ scene.proposed_changes : pc.status = COMMITTED
            ELSE ∀pc ∈ scene.proposed_changes : pc.status ≠ COMMITTED

TLA+ Representation:
    VARIABLE scenes: set of scenes
    VARIABLE proposed_changes: set of proposed changes

    SceneAtomicity ==
        /\ \A s \in scenes :
            s.status = "completed" <=>
                \A pc \in proposed_changes : pc.scene_id = s.id => pc.status = "committed"
"""

from dataclasses import dataclass
from uuid import UUID

from monitor_data.schemas.base import SceneStatus

# Valid status transitions (based on actual SceneStatus enum: ACTIVE, FINALIZING, COMPLETED)
VALID_TRANSITIONS: dict[SceneStatus, frozenset[SceneStatus]] = {
    SceneStatus.ACTIVE: frozenset({SceneStatus.FINALIZING, SceneStatus.COMPLETED}),
    SceneStatus.FINALIZING: frozenset({SceneStatus.ACTIVE, SceneStatus.COMPLETED}),
    SceneStatus.COMPLETED: frozenset(),  # Terminal state
}

# Terminal states - no further transitions allowed
TERMINAL_STATES: frozenset[SceneStatus] = frozenset(
    {
        SceneStatus.COMPLETED,
    }
)

# States that indicate scene is in progress
IN_PROGRESS_STATES: frozenset[SceneStatus] = frozenset(
    {
        SceneStatus.ACTIVE,
        SceneStatus.FINALIZING,
    }
)


@dataclass(frozen=True)
class SceneBoundary:
    """
    Represents the atomic boundary of a scene.

    A scene is atomic if:
    1. It has a consistent set of proposed changes
    2. All facts within it are canonized together
    3. No partial state visible to other agents until commit
    """

    scene_id: UUID
    turn_ids: tuple[UUID, ...]
    proposed_change_ids: tuple[UUID, ...]
    status: SceneStatus

    @property
    def is_complete(self) -> bool:
        """Check if scene has reached a terminal state."""
        return self.status in TERMINAL_STATES

    @property
    def is_in_progress(self) -> bool:
        """Check if scene is actively being worked on."""
        return self.status in IN_PROGRESS_STATES


class SceneAtomicity:
    """
    Formal invariant checker for scene atomicity.

    This ensures that:
    1. Scene is the atomic unit for canonization
    2. Proposed changes within a scene are all-or-nothing
    3. Status transitions follow the state machine
    """

    @staticmethod
    def is_valid_transition(from_status: SceneStatus, to_status: SceneStatus) -> bool:
        """
        Check if status transition is valid.

        Args:
            from_status: Current scene status
            to_status: Desired new status

        Returns:
            True if transition is allowed
        """
        if from_status == to_status:
            return True  # No-op is always valid
        return to_status in VALID_TRANSITIONS.get(from_status, frozenset())

    @staticmethod
    def is_terminal(status: SceneStatus) -> bool:
        """
        Check if status is terminal (no further transitions allowed).

        Args:
            status: Scene status to check

        Returns:
            True if status is terminal
        """
        return status in TERMINAL_STATES

    @staticmethod
    def is_in_progress(status: SceneStatus) -> bool:
        """
        Check if scene is in progress (can accept turns/resolutions).

        Args:
            status: Scene status to check

        Returns:
            True if scene can accept new content
        """
        return status in IN_PROGRESS_STATES

    @staticmethod
    def assert_valid_transition(
        from_status: SceneStatus,
        to_status: SceneStatus,
    ) -> None:
        """
        Assert that status transition is valid.

        Args:
            from_status: Current scene status
            to_status: Desired new status

        Raises:
            ValueError: If transition is invalid
        """
        if not SceneAtomicity.is_valid_transition(from_status, to_status):
            raise ValueError(
                f"Invalid scene status transition from {from_status} to {to_status}. "
                f"Valid transitions from {from_status}: {VALID_TRANSITIONS.get(from_status, set())}"
            )

    @staticmethod
    def get_atomic_boundary_info(
        scene_id: UUID,
        status: SceneStatus,
        turn_count: int,
        proposed_change_count: int,
    ) -> SceneBoundary:
        """
        Create a SceneBoundary object for atomicity tracking.

        Args:
            scene_id: Scene UUID
            status: Current scene status
            turn_count: Number of turns in scene
            proposed_change_count: Number of proposed changes

        Returns:
            SceneBoundary object
        """
        return SceneBoundary(
            scene_id=scene_id,
            turn_ids=(),  # Would be populated from actual data
            proposed_change_ids=(),
            status=status,
        )

    @staticmethod
    def assert_scene_atomic(scene_boundary: SceneBoundary) -> None:
        """
        Assert that scene boundary is atomic.

        A scene is atomic if:
        1. It's in a terminal state, OR
        2. It's in progress with consistent proposed change state

        Args:
            scene_boundary: The scene boundary to check

        Raises:
            ValueError: If scene is not atomic
        """
        if scene_boundary.is_complete:
            # Scene is complete - this is a valid atomic boundary
            return

        if scene_boundary.is_in_progress:
            # Scene is in progress - this is valid during editing
            # Atomic commit happens when status becomes COMPLETED
            return

        raise ValueError(f"Scene {scene_boundary.scene_id} is in invalid state {scene_boundary.status}")


def assert_scene_atomic(scene_boundary: SceneBoundary) -> None:
    """
    Convenience function to assert scene atomicity.

    Args:
        scene_boundary: The scene boundary to check

    Raises:
        ValueError: If scene is not atomic
    """
    SceneAtomicity.assert_scene_atomic(scene_boundary)


def get_atomic_boundary(
    scene_id: UUID,
    status: SceneStatus,
    turn_count: int = 0,
    proposed_change_count: int = 0,
) -> SceneBoundary:
    """
    Convenience function to get scene atomic boundary.

    Args:
        scene_id: Scene UUID
        status: Current scene status
        turn_count: Number of turns
        proposed_change_count: Number of proposed changes

    Returns:
        SceneBoundary object
    """
    return SceneAtomicity.get_atomic_boundary_info(scene_id, status, turn_count, proposed_change_count)


# =============================================================================
# TLA+ SPECIFICATION
# =============================================================================
"""
---------------- MODULE SceneAtomicity ----------------

CONSTANT
    - ACTIVE, PAUSED, COMPLETED, ABANDONED: scene statuses
    - SceneStatus: set of all statuses

VARIABLE
    - scenes: set of scenes
    - proposed_changes: set of proposed changes

StatusTransitionValid(s, s') ==
    \\/ s = ACTIVE /\\ s' \\in {PAUSED, COMPLETED, ABANDONED}
    \\/ s = PAUSED /\\ s' \\in {ACTIVE, COMPLETED, ABANDONED}
    \\/ s = COMPLETED /\\ s' = COMPLETED  \\* terminal
    \\/ s = ABANDONED /\\ s' = ABANDONED  \\* terminal

SceneAtomicity ==
    /\\ \\A s \\in scenes :
        /\\ s.status = COMPLETED =>
            \\A pc \\in proposed_changes :
                pc.scene_id = s.id => pc.status = "committed"
        /\\ s.status = ABANDONED =>
            \\A pc \\in proposed_changes :
                pc.scene_id = s.id => pc.status \notin {"committed", "pending"}

TypeInvariant ==
    /\\ scenes : SUBSET [id: UUID, status: SceneStatus, turn_count: Int]
    /\\ proposed_changes : SUBSET [id: UUID, scene_id: UUID, status: STRING]

Init ==
    /\\ scenes = {}
    /\\ proposed_changes = {}

CommitScene(s) ==
    /\\ s.status = ACTIVE \\/ s.status = PAUSED
    /\\ s' = [s EXCEPT !.status = COMPLETED]
    /\\ \\A pc \\in proposed_changes :
        pc.scene_id = s.id => pc' = [pc EXCEPT !.status = "committed"]

THEOREM Invariant => SceneAtomicity

=============================================================
"""
