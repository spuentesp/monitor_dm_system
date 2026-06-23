"""
P-21: Downtime & Character Progression - Behavior Tests

This package contains comprehensive behavior tests for the Downtime & Character Progression use case,
verifying that the implementation matches the behavior specifications in:
docs/use-cases/behaviors/P-21-behaviors.md

Behavior tests verify:
- System flow matches step-by-step actions
- All preconditions and postconditions are enforced
- Error cases are handled correctly
- Success criteria are met
"""

from tests.unit.P_21.test_downtime_character_progression import (
    UpgradeType,
    UpgradeOption,
    CharacterProgression,
    ProgressionRules,
    ValidationResult,
    ProposedChange,
    CanonResult,
    TurnType,
    TurnCreate,
    Turn,
    Scene,
    Story,
    ProgressionLoop,
    CanonKeeper,
    NarratorAgent,
)

__all__ = [
    # Schema classes
    "UpgradeType",
    "UpgradeOption",
    "CharacterProgression",
    "ProgressionRules",
    "ValidationResult",
    "ProposedChange",
    "CanonResult",
    "TurnType",
    "TurnCreate",
    "Turn",
    "Scene",
    "Story",
    # Agent classes
    "ProgressionLoop",
    "CanonKeeper",
    "NarratorAgent",
]