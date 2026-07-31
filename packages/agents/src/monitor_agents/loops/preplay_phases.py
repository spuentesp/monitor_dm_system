"""Canonical phase vocabulary for the autonomous-GM pre-play flow."""

from __future__ import annotations

from enum import StrEnum


class PreplayPhase(StrEnum):
    """Persisted phases before the first in-fiction turn."""

    CHARACTER_INTERVIEW = "character_interview"
    CHARACTER_CREATION = "char_creation"
    SESSION_ZERO = "session_zero"


PREPLAY_PHASES = frozenset(phase.value for phase in PreplayPhase)

# Existing sessions may still carry these values. They are accepted on read,
# while new transitions write the canonical phases above.
LEGACY_PREPLAY_PHASES = frozenset({"awaiting_character"})
ALL_PREPLAY_PHASES = PREPLAY_PHASES | LEGACY_PREPLAY_PHASES


def normalize_preplay_phase(value: str | None) -> str:
    """Return the canonical phase for a persisted legacy value."""
    if value == "awaiting_character":
        return PreplayPhase.CHARACTER_INTERVIEW.value
    return value or PreplayPhase.CHARACTER_INTERVIEW.value
