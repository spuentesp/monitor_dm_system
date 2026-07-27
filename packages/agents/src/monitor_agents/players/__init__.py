"""Test-player drivers — single abstraction for the e2e harness.

Public surface is ``InstructablePlayer``; strategies live in this module
and are picked via ``InstructablePlayer(spec=...)``. The harness speaks
to the player through ``InstructablePlayer.next() -> tuple[str, str]``
only.
"""

from .instructable_player import (
    InstructablePlayer,
    InstructedSpec,
    MockSpec,
    PlayerContext,
    PlayerSpec,
    ScriptedSpec,
    TurnObservation,
    classify_player_intent,
    coherence_count,
)

__all__ = [
    "InstructablePlayer",
    "InstructedSpec",
    "MockSpec",
    "PlayerContext",
    "PlayerSpec",
    "ScriptedSpec",
    "TurnObservation",
    "classify_player_intent",
    "coherence_count",
]
