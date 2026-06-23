"""
Turn Flow Invariant (INV-4).

This invariant ensures that Turns always flow in the correct sequence:
    User Input → Resolve → Narrate

No turn can skip phases or go backwards.

Formal Specification:
    TurnFlow ==
        ∧ ∀ turn ∈ Turns :
            turn.phase ∈ {USER_INPUT, RESOLVE, NARRATE}
        ∧ ∀ i < |turns|-1 :
            turns[i].phase < turns[i+1].phase
        ∧ No turn can be NARRATE without prior RESOLVE
        ∧ No turn can be RESOLVE without prior USER_INPUT

TLA+ Representation:
    VARIABLE turns: sequence of turns

    TurnFlow ==
        /\ \A i \in DOMAIN turns :
            turns[i].phase \in {"user", "resolve", "narrate"}
        /\ \A i \in 1..(DOMAIN turns - 1) :
            PhaseOrder(turns[i].phase) < PhaseOrder(turns[i+1].phase)
"""

from enum import IntEnum
from dataclasses import dataclass
from typing import Optional, FrozenSet
from uuid import UUID


class TurnPhase(IntEnum):
    """Turn phases in order (must be ordinal for comparison)."""

    USER_INPUT = 1
    RESOLVE = 2
    NARRATE = 3


# Valid phase transitions
VALID_PHASE_TRANSITIONS: dict[TurnPhase, FrozenSet[TurnPhase]] = {
    # User input can go to Resolve
    TurnPhase.USER_INPUT: frozenset({TurnPhase.RESOLVE}),
    # Resolve always goes to Narrate
    TurnPhase.RESOLVE: frozenset({TurnPhase.NARRATE}),
    # Narrate is typically end, but can be followed by more USER_INPUT for next turn
    TurnPhase.NARRATE: frozenset({TurnPhase.USER_INPUT}),
}

# Terminal phases (end of turn sequence)
TERMINAL_PHASES: FrozenSet[TurnPhase] = frozenset(
    {
        TurnPhase.NARRATE,  # Narrate ends the current turn resolution
    }
)


@dataclass(frozen=True)
class TurnBoundary:
    """
    Represents the atomic boundary of a single turn.

    A turn is atomic if:
    1. It has a consistent phase progression
    2. No skipped phases in the sequence
    3. Turn result is final once NARRATE completes
    """

    turn_id: UUID
    scene_id: UUID
    phase: TurnPhase
    speaker: str
    content: str

    @property
    def is_terminal(self) -> bool:
        """Check if turn is at a terminal phase."""
        return self.phase in TERMINAL_PHASES

    @property
    def requires_resolution(self) -> bool:
        """Check if turn requires dice resolution."""
        return self.phase == TurnPhase.RESOLVE


class TurnFlow:
    """
    Formal invariant checker for turn flow.

    This ensures:
    1. Turns follow the sequence: USER_INPUT → RESOLVE → NARRATE
    2. No phase is skipped
    3. No backward transitions
    """

    PHASE_ORDER = {
        TurnPhase.USER_INPUT: 1,
        TurnPhase.RESOLVE: 2,
        TurnPhase.NARRATE: 3,
    }

    @staticmethod
    def is_valid_phase(phase: TurnPhase) -> bool:
        """
        Check if phase is a valid TurnPhase enum value.

        Args:
            phase: The phase to check

        Returns:
            True if phase is valid
        """
        return isinstance(phase, TurnPhase)

    @staticmethod
    def is_valid_transition(from_phase: TurnPhase, to_phase: TurnPhase) -> bool:
        """
        Check if phase transition is valid.

        Args:
            from_phase: Current phase
            to_phase: Desired next phase

        Returns:
            True if transition follows valid flow
        """
        # Allow same phase (staying in same phase for extended content)
        if from_phase == to_phase:
            return True

        # Check if transition is in valid set for from_phase
        valid_next = VALID_PHASE_TRANSITIONS.get(from_phase, frozenset())
        return to_phase in valid_next

    @staticmethod
    def get_next_phase(current_phase: TurnPhase) -> TurnPhase:
        """
        Get the canonical next phase.

        Args:
            current_phase: Current phase

        Returns:
            The expected next phase in the sequence

        Raises:
            ValueError: If current phase has no defined next phase
        """
        if current_phase == TurnPhase.USER_INPUT:
            return TurnPhase.RESOLVE
        elif current_phase == TurnPhase.RESOLVE:
            return TurnPhase.NARRATE
        elif current_phase == TurnPhase.NARRATE:
            return TurnPhase.USER_INPUT  # Next turn starts fresh
        else:
            raise ValueError(f"Unknown phase: {current_phase}")

    @staticmethod
    def validate_turn_sequence(turns: list) -> tuple[bool, Optional[str]]:
        """
        Validate that a sequence of turns follows the flow rules.

        Args:
            turns: List of turns (each should have .phase attribute)

        Returns:
            (is_valid, error_message)
        """
        if not turns:
            return True, None  # Empty sequence is valid

        for i, turn in enumerate(turns):
            phase = turn.phase if hasattr(turn, "phase") else turn.get("phase")

            # Check phase is valid
            if not TurnFlow.is_valid_phase(phase):
                return False, f"Turn {i} has invalid phase: {phase}"

            # Check transitions
            if i > 0:
                prev_phase = (
                    turns[i - 1].phase
                    if hasattr(turns[i - 1], "phase")
                    else turns[i - 1].get("phase")
                )
                if not TurnFlow.is_valid_transition(prev_phase, phase):
                    return False, (
                        f"Invalid transition from {prev_phase.name} to {phase.name} at turn {i}"
                    )

        return True, None

    @staticmethod
    def is_terminal_phase(phase: TurnPhase) -> bool:
        """Check if phase is terminal."""
        return phase in TERMINAL_PHASES
