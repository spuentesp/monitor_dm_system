"""
Contract tests for Temporal Validation schemas (P-14 flashback mode).

Covers:
- TemporalViolationType enum (6 types: future ref, paradox, anachronism, etc.)
- TemporalSeverity enum (info, warning, error)
- FactValidityStatus enum (valid, expired, not_yet_started, always_valid)
- TemporalViolation: a detected inconsistency
- TemporalValidationRequest: scene validation request
- TemporalValidationResult: validation summary
- FactValidity: per-fact validity check
- SceneTemporalContext: scene's temporal context (P-14)

Use Cases: P-14 (Flashback Mode), Phase 4.6
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

from monitor_data.schemas.temporal_validation import (
    FactExpirationBatch,
    FactValidity,
    FactValidityStatus,
    SceneTemporalContext,
    TemporalSeverity,
    TemporalValidationRequest,
    TemporalValidationResult,
    TemporalViolation,
    TemporalViolationType,
)


def _ts() -> datetime:
    return datetime.now(UTC)


# =============================================================================
# Enums
# =============================================================================


class TestTemporalViolationTypeEnum:
    def test_all_values(self):
        assert TemporalViolationType.FUTURE_REFERENCE.value == "future_reference"
        assert TemporalViolationType.TEMPORAL_PARADOX.value == "temporal_paradox"
        assert TemporalViolationType.ANACHRONISM.value == "anachronism"
        assert TemporalViolationType.DURATION_MISMATCH.value == "duration_mismatch"
        assert TemporalViolationType.EXPIRED_FACT.value == "expired_fact"
        assert TemporalViolationType.PREMATURE_FACT.value == "premature_fact"


class TestTemporalSeverityEnum:
    def test_all_values(self):
        assert TemporalSeverity.INFO.value == "info"
        assert TemporalSeverity.WARNING.value == "warning"
        assert TemporalSeverity.ERROR.value == "error"


class TestFactValidityStatusEnum:
    def test_all_values(self):
        assert FactValidityStatus.VALID.value == "valid"
        assert FactValidityStatus.EXPIRED.value == "expired"
        assert FactValidityStatus.NOT_YET_STARTED.value == "not_yet_started"
        assert FactValidityStatus.ALWAYS_VALID.value == "always_valid"


# =============================================================================
# TemporalViolation
# =============================================================================


class TestTemporalViolation:
    def test_minimal(self):
        v = TemporalViolation(
            violation_id="v-001",
            violation_type=TemporalViolationType.ANACHRONISM,
            severity=TemporalSeverity.WARNING,
            description="A gun appears in a medieval setting",
        )
        assert v.violation_id == "v-001"
        assert v.violation_type == TemporalViolationType.ANACHRONISM
        assert v.severity == TemporalSeverity.WARNING

    def test_with_scene_ref(self):
        v = TemporalViolation(
            violation_id="v-002",
            violation_type=TemporalViolationType.EXPIRED_FACT,
            severity=TemporalSeverity.ERROR,
            description="King is dead but referenced as alive",
            scene_id=uuid4(),
        )
        assert v.scene_id is not None
        assert v.fact_id is None  # default

    def test_with_fact_ref(self):
        v = TemporalViolation(
            violation_id="v-003",
            violation_type=TemporalViolationType.PREMATURE_FACT,
            severity=TemporalSeverity.WARNING,
            description="Fact is from the future",
            fact_id=uuid4(),
        )
        assert v.fact_id is not None

    def test_with_timestamps(self):
        v = TemporalViolation(
            violation_id="v-004",
            violation_type=TemporalViolationType.TEMPORAL_PARADOX,
            severity=TemporalSeverity.ERROR,
            description="Circular timeline detected",
            scene_time_ref=_ts(),
            canon_time_ref=_ts(),
        )
        assert v.scene_time_ref is not None
        assert v.canon_time_ref is not None

    def test_with_context(self):
        v = TemporalViolation(
            violation_id="v-005",
            violation_type=TemporalViolationType.DURATION_MISMATCH,
            severity=TemporalSeverity.INFO,
            description="Duration mismatch",
            context={"expected": 60, "actual": 30},
        )
        assert v.context["expected"] == 60


# =============================================================================
# TemporalValidationRequest
# =============================================================================


class TestTemporalValidationRequest:
    def test_minimal(self):
        req = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=_ts(),
            scene_text="The king walks into the room.",
        )
        assert req.scene_id
        assert req.scene_text == "The king walks into the room."
        assert req.validate_against_facts is True  # default
        assert req.validate_against_events is True  # default

    def test_with_entity_ids(self):
        eid = uuid4()
        req = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=_ts(),
            scene_text="The wizard casts a spell.",
            entity_ids=[eid],
        )
        assert eid in req.entity_ids

    def test_with_location(self):
        req = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=_ts(),
            scene_text="The party enters the dungeon.",
            location_ref=uuid4(),
        )
        assert req.location_ref is not None

    def test_with_validation_flags(self):
        req = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=_ts(),
            scene_text="...",
            validate_against_facts=False,
            validate_against_events=False,
        )
        assert req.validate_against_facts is False
        assert req.validate_against_events is False


# =============================================================================
# TemporalValidationResult
# =============================================================================


class TestTemporalValidationResult:
    def test_minimal(self):
        result = TemporalValidationResult(
            scene_id=uuid4(),
            universe_id=uuid4(),
            scene_time_ref=_ts(),
        )
        assert result.total_violations == 0
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.violations == []

    def test_with_violations(self):
        v = TemporalViolation(
            violation_id="v-006",
            violation_type=TemporalViolationType.ANACHRONISM,
            severity=TemporalSeverity.WARNING,
            description="test",
        )
        result = TemporalValidationResult(
            scene_id=uuid4(),
            universe_id=uuid4(),
            scene_time_ref=_ts(),
            violations=[v],
            total_violations=1,
            warning_count=1,
        )
        assert result.total_violations == 1
        assert result.warning_count == 1
        assert len(result.violations) == 1


# =============================================================================
# FactValidity
# =============================================================================


class TestFactValidity:
    def test_valid_fact(self):
        v = FactValidity(
            fact_id=uuid4(),
            statement="The king is alive",
            status=FactValidityStatus.VALID,
            check_time=_ts(),
        )
        assert v.status == FactValidityStatus.VALID

    def test_expired_fact(self):
        v = FactValidity(
            fact_id=uuid4(),
            statement="The king is alive",
            status=FactValidityStatus.EXPIRED,
            check_time=_ts(),
        )
        assert v.status == FactValidityStatus.EXPIRED

    def test_always_valid_fact(self):
        v = FactValidity(
            fact_id=uuid4(),
            statement="The world is round",
            status=FactValidityStatus.ALWAYS_VALID,
            check_time=_ts(),
            is_timeless=True,
        )
        assert v.status == FactValidityStatus.ALWAYS_VALID
        assert v.is_timeless is True


# =============================================================================
# SceneTemporalContext (P-14)
# =============================================================================


class TestSceneTemporalContext:
    def test_no_time_shift(self):
        t = _ts()
        ctx = SceneTemporalContext(
            scene_id=uuid4(),
            old_time_ref=t,
            new_time_ref=t,
        )
        assert ctx.time_shifted is False
        assert ctx.can_revise is True
        assert ctx.timeline_conflicts == []

    def test_time_shifted(self):
        ctx = SceneTemporalContext(
            scene_id=uuid4(),
            old_time_ref=_ts(),
            new_time_ref=_ts(),
            time_shifted=True,
        )
        assert ctx.time_shifted is True

    def test_with_conflicts(self):
        v = TemporalViolation(
            violation_id="v-c-001",
            violation_type=TemporalViolationType.FUTURE_REFERENCE,
            severity=TemporalSeverity.WARNING,
            description="Timeline conflict",
        )
        ctx = SceneTemporalContext(
            scene_id=uuid4(),
            new_time_ref=_ts(),
            timeline_conflicts=[v],
            can_revise=False,
        )
        assert len(ctx.timeline_conflicts) == 1
        assert ctx.can_revise is False


# =============================================================================
# FactExpirationBatch
# =============================================================================


class TestFactExpirationBatch:
    def test_minimal(self):
        batch = FactExpirationBatch(
            universe_id=uuid4(),
            check_time=_ts(),
        )
        assert batch.universe_id
        assert batch.total_checked == 0
        assert batch.expired_count == 0

    def test_with_expired(self):
        v = FactValidity(
            fact_id=uuid4(),
            statement="The wizard knew fireball",
            status=FactValidityStatus.EXPIRED,
            check_time=_ts(),
        )
        batch = FactExpirationBatch(
            universe_id=uuid4(),
            check_time=_ts(),
            expired_facts=[v],
        )
        batch.compute_totals()
        assert batch.expired_count == 1
        assert batch.facts_to_expire == [v.fact_id]
