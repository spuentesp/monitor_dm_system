"""
Pydantic schemas for temporal validation (Temporal & Contradiction Gap).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py, mongodb_tools.py, canonkeeper agent

These schemas define temporal consistency validation for scenes and facts:
- TemporalValidationRequest: Check if scene timeline respects canon chronology
- TemporalViolation: Detected temporal inconsistency
- FactExpiration: Track fact validity over time
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class TemporalViolationType(str, Enum):
    """Type of temporal inconsistency."""

    FUTURE_REFERENCE = "future_reference"  # Scene references event that hasn't happened yet
    TEMPORAL_PARADOX = "temporal_paradox"  # Circular or impossible timeline
    ANACHRONISM = "anachronism"  # Technology/knowledge not available at this time
    DURATION_MISMATCH = "duration_mismatch"  # Fact duration conflicts with scene timeline
    EXPIRED_FACT = "expired_fact"  # Fact is no longer valid at scene time
    PREMATURE_FACT = "premature_fact"  # Fact becomes valid after scene time


class TemporalSeverity(str, Enum):
    """Severity of temporal violation."""

    INFO = "info"  # Informational, doesn't break coherence
    WARNING = "warning"  # Should be reviewed but can proceed
    ERROR = "error"  # Breaks timeline coherence, must resolve


class FactValidityStatus(str, Enum):
    """Whether a fact is valid at a given point in time."""

    VALID = "valid"  # Fact is active and true at this time
    EXPIRED = "expired"  # Fact was true but has ended
    NOT_YET_STARTED = "not_yet_started"  # Fact will become true in the future
    ALWAYS_VALID = "always_valid"  # Fact has no time constraints


# =============================================================================
# TEMPORAL VALIDATION SCHEMAS
# =============================================================================


class TemporalViolation(BaseModel):
    """A detected temporal inconsistency."""

    violation_id: str = Field(
        max_length=100,
        description="Unique identifier for this violation",
    )
    violation_type: TemporalViolationType
    severity: TemporalSeverity
    description: str = Field(max_length=1000, description="Human-readable explanation")
    scene_id: Optional[UUID] = Field(None, description="Scene where violation occurred")
    fact_id: Optional[UUID] = Field(None, description="Related fact if applicable")
    event_id: Optional[UUID] = Field(None, description="Related event if applicable")
    scene_time_ref: Optional[datetime] = Field(None, description="Scene timestamp")
    canon_time_ref: Optional[datetime] = Field(None, description="Canonical event timestamp")
    # Additional context
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for debugging",
    )


class TemporalValidationRequest(BaseModel):
    """Request to validate temporal consistency of a scene."""

    scene_id: UUID
    universe_id: UUID
    story_id: UUID
    scene_time_ref: datetime = Field(description="Scene timestamp")
    scene_text: str = Field(max_length=10000, description="Scene content for analysis")
    entity_ids: List[UUID] = Field(
        default_factory=list,
        description="Entities present in scene",
    )
    location_ref: Optional[UUID] = Field(None, description="Scene location")
    # Optional: facts/events to validate against
    validate_against_facts: bool = Field(
        default=True,
        description="Check scene against canonical facts",
    )
    validate_against_events: bool = Field(
        default=True,
        description="Check scene against canonical events",
    )


class TemporalValidationResult(BaseModel):
    """Result of temporal validation."""

    scene_id: UUID
    universe_id: UUID
    scene_time_ref: datetime
    validation_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Violations
    violations: List[TemporalViolation] = Field(default_factory=list)
    # Summary
    total_violations: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    # Validity check
    is_valid: bool = Field(default=True, description="No ERROR-level violations")
    can_proceed: bool = Field(
        default=True,
        description="Can proceed with scene despite warnings",
    )

    def compute_totals(self) -> None:
        """Recompute summary stats from violations."""
        self.total_violations = len(self.violations)
        self.error_count = sum(1 for v in self.violations if v.severity == TemporalSeverity.ERROR)
        self.warning_count = sum(
            1 for v in self.violations if v.severity == TemporalSeverity.WARNING
        )
        self.info_count = sum(1 for v in self.violations if v.severity == TemporalSeverity.INFO)
        self.is_valid = self.error_count == 0
        self.can_proceed = self.error_count == 0


# =============================================================================
# FACT EXPIRATION SCHEMAS
# =============================================================================


class FactValidity(BaseModel):
    """Validity status of a fact at a specific point in time."""

    fact_id: UUID
    statement: str = Field(max_length=2000)
    time_ref: Optional[datetime] = Field(None, description="When fact became true")
    duration: Optional[int] = Field(None, description="Duration in seconds")
    expires_at: Optional[datetime] = Field(None, description="Calculated expiration time")
    status: FactValidityStatus
    check_time: datetime = Field(description="Time at which validity was checked")
    # Context
    is_timeless: bool = Field(
        default=False,
        description="Fact has no temporal constraints",
    )
    is_expiring_soon: bool = Field(
        default=False,
        description="Fact will expire within next 24 hours",
    )
    time_until_expiry: Optional[timedelta] = Field(
        None,
        description="Time remaining until expiration (None if never expires)",
    )
    time_until_start: Optional[timedelta] = Field(
        None,
        description="Time until fact becomes valid (None if already valid or timeless)",
    )


class FactExpirationBatch(BaseModel):
    """Batch check of multiple facts for validity."""

    universe_id: UUID
    check_time: datetime
    # Results
    valid_facts: List[FactValidity] = Field(default_factory=list)
    expired_facts: List[FactValidity] = Field(default_factory=list)
    not_yet_started_facts: List[FactValidity] = Field(default_factory=list)
    always_valid_facts: List[FactValidity] = Field(default_factory=list)
    # Summary
    total_checked: int = 0
    valid_count: int = 0
    expired_count: int = 0
    not_yet_started_count: int = 0
    always_valid_count: int = 0
    # Actions
    facts_to_expire: List[UUID] = Field(
        default_factory=list,
        description="Fact IDs that should be tombstoned",
    )

    def compute_totals(self) -> None:
        """Recompute summary stats."""
        self.valid_facts = [f for f in self.valid_facts if f.status == FactValidityStatus.VALID]
        self.expired_facts = [
            f for f in self.expired_facts if f.status == FactValidityStatus.EXPIRED
        ]
        self.not_yet_started_facts = [
            f for f in self.not_yet_started_facts if f.status == FactValidityStatus.NOT_YET_STARTED
        ]
        self.always_valid_facts = [
            f for f in self.always_valid_facts if f.status == FactValidityStatus.ALWAYS_VALID
        ]

        self.total_checked = (
            len(self.valid_facts)
            + len(self.expired_facts)
            + len(self.not_yet_started_facts)
            + len(self.always_valid_facts)
        )
        self.valid_count = len(self.valid_facts)
        self.expired_count = len(self.expired_facts)
        self.not_yet_started_count = len(self.not_yet_started_facts)
        self.always_valid_count = len(self.always_valid_facts)

        # Facts that are expired should be tombstoned
        self.facts_to_expire = [f.fact_id for f in self.expired_facts]


# =============================================================================
# SCENE REVISION TEMPORAL SCHEMAS
# =============================================================================


class SceneTemporalContext(BaseModel):
    """Temporal context for a scene revision."""

    scene_id: UUID
    old_time_ref: Optional[datetime] = Field(None, description="Previous scene timestamp")
    new_time_ref: datetime = Field(description="New scene timestamp")
    time_shifted: bool = Field(default=False, description="Whether time changed")
    shift_magnitude: Optional[timedelta] = Field(
        None,
        description="How much time shifted (None if no shift)",
    )
    # Validation results
    old_validity: Optional[TemporalValidationResult] = Field(None)
    new_validity: Optional[TemporalValidationResult] = Field(None)
    # Conflicts
    timeline_conflicts: List[TemporalViolation] = Field(default_factory=list)
    # Recommendation
    can_revise: bool = Field(default=True, description="Whether revision is temporally safe")


class FactReplacement(BaseModel):
    """Record of a fact being replaced by a new version."""

    old_fact_id: UUID
    new_fact_id: UUID
    old_statement: str = Field(max_length=2000)
    new_statement: str = Field(max_length=2000)
    replacement_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scene_id: Optional[UUID] = Field(None, description="Scene that caused replacement")
    reason: str = Field(max_length=500, description="Why replacement occurred")
    # Tracking
    replaced_by_canonkeeper: bool = Field(
        default=False,
        description="Whether CanonKeeper authorized this replacement",
    )
    canon_level: str = Field(default="proposed")
