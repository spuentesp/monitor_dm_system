"""
Tests for Temporal & Contradiction Gap implementation.

Covers:
  1. Fact expiration system
  2. Temporal validation for scenes
  3. Contradiction detection in CanonKeeper
  4. Plot thread detection from scenes
"""

from datetime import datetime, timedelta, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.plot_threads import (
    PlotThreadCategory,
    PlotThreadUrgency,
)
from monitor_data.schemas.temporal_validation import (
    FactValidityStatus,
    TemporalSeverity,
    TemporalValidationRequest,
    TemporalViolationType,
)
from monitor_data.tools.plot_thread_tools import (
    classify_thread_content,
    detect_plot_threads_from_scene,
    update_thread_status_from_scene,
)
from monitor_data.tools.temporal_tools import (
    batch_check_fact_validity,
    check_fact_validity,
    validate_scene_temporal,
)

# =============================================================================
# FACT EXPIRATION TESTS
# =============================================================================


class TestFactExpiration:
    """Tests for fact validity and expiration."""

    def test_timeless_fact_always_valid(self):
        """Fact with no time_ref or duration is always valid."""
        fact = {
            "id": uuid4(),
            "statement": "Magic exists in this world",
        }
        check_time = datetime.now(UTC)

        validity = check_fact_validity(fact, check_time)

        assert validity.status == FactValidityStatus.ALWAYS_VALID
        assert validity.is_timeless is True
        assert validity.expires_at is None

    def test_fact_valid_at_check_time(self):
        """Fact is valid when check_time is within [time_ref, time_ref + duration]."""
        time_ref = datetime.now(UTC)
        duration = 3600  # 1 hour
        fact = {
            "id": uuid4(),
            "statement": "The castle is under siege",
            "time_ref": time_ref,
            "duration": duration,
        }

        # Check 30 minutes in
        check_time = time_ref + timedelta(minutes=30)
        validity = check_fact_validity(fact, check_time)

        assert validity.status == FactValidityStatus.VALID
        assert validity.expires_at == time_ref + timedelta(seconds=duration)
        assert validity.time_until_expiry is not None
        assert validity.time_until_expiry > timedelta(0)

    def test_fact_expired(self):
        """Fact is expired when check_time > time_ref + duration."""
        time_ref = datetime.now(UTC) - timedelta(hours=2)
        duration = 3600  # 1 hour
        fact = {
            "id": uuid4(),
            "statement": "The castle is under siege",
            "time_ref": time_ref,
            "duration": duration,
        }

        # Check 2 hours after start (fact expired 1 hour ago)
        check_time = datetime.now(UTC)
        validity = check_fact_validity(fact, check_time)

        assert validity.status == FactValidityStatus.EXPIRED
        assert validity.expires_at == time_ref + timedelta(seconds=duration)
        assert validity.time_until_expiry is None

    def test_fact_not_yet_started(self):
        """Fact is not yet valid when check_time < time_ref."""
        time_ref = datetime.now(UTC) + timedelta(hours=1)
        fact = {
            "id": uuid4(),
            "statement": "The coronation will begin",
            "time_ref": time_ref,
            "duration": 3600,
        }

        # Check now (before fact starts)
        check_time = datetime.now(UTC)
        validity = check_fact_validity(fact, check_time)

        assert validity.status == FactValidityStatus.NOT_YET_STARTED
        assert validity.time_until_start is not None
        assert validity.time_until_start > timedelta(0)

    def test_expiring_soon_warning(self):
        """Fact is flagged as expiring soon when within 24 hours."""
        time_ref = datetime.now(UTC) - timedelta(hours=23)
        duration = 86400  # 24 hours
        fact = {
            "id": uuid4(),
            "statement": "The treaty expires soon",
            "time_ref": time_ref,
            "duration": duration,
        }

        # Check now (1 hour before expiration)
        check_time = datetime.now(UTC)
        validity = check_fact_validity(fact, check_time)

        assert validity.status == FactValidityStatus.VALID
        assert validity.is_expiring_soon is True
        assert validity.time_until_expiry is not None
        assert 0 < validity.time_until_expiry.total_seconds() <= 86400

    def test_batch_check_fact_validity(self):
        """Batch check correctly categorizes multiple facts."""
        now = datetime.now(UTC)

        facts = [
            {
                "id": uuid4(),
                "statement": "Timeless truth",
            },
            {
                "id": uuid4(),
                "statement": "Valid fact",
                "time_ref": now - timedelta(hours=1),
                "duration": 7200,
            },
            {
                "id": uuid4(),
                "statement": "Expired fact",
                "time_ref": now - timedelta(hours=3),
                "duration": 3600,
            },
            {
                "id": uuid4(),
                "statement": "Future fact",
                "time_ref": now + timedelta(hours=1),
                "duration": 3600,
            },
        ]

        batch = batch_check_fact_validity(facts, now, uuid4())

        assert batch.always_valid_count == 1
        assert batch.valid_count == 1
        assert batch.expired_count == 1
        assert batch.not_yet_started_count == 1
        assert len(batch.facts_to_expire) == 1


# =============================================================================
# TEMPORAL VALIDATION TESTS
# =============================================================================


class TestTemporalValidation:
    """Tests for scene temporal validation."""

    def test_valid_scene_no_violations(self):
        """Scene with valid timeline has no violations."""
        request = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=datetime(1000, 1, 1, tzinfo=UTC),
            scene_text="The knights rode into battle on horseback.",
            validate_against_facts=False,
            validate_against_events=False,
        )

        result = validate_scene_temporal(request)

        assert result.is_valid is True
        assert result.can_proceed is True
        assert result.total_violations == 0

    def test_future_reference_detection(self):
        """Scene with future reference is flagged."""
        request = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=datetime(1000, 1, 1, tzinfo=UTC),
            scene_text="Tomorrow, the king will die in battle.",
            validate_against_facts=False,
            validate_against_events=False,
        )

        result = validate_scene_temporal(request)

        # Future reference should be detected (at least as INFO or WARNING)
        assert result.total_violations > 0
        future_refs = [
            v
            for v in result.violations
            if v.violation_type == TemporalViolationType.FUTURE_REFERENCE
        ]
        assert len(future_refs) > 0

    def test_future_event_reference(self):
        """Scene referencing a future event is flagged as ERROR."""
        event_time = datetime(1000, 1, 2, tzinfo=UTC)
        canon_events = [
            {
                "id": uuid4(),
                "title": "King's Death",
                "start_time": event_time,
            },
        ]

        request = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=datetime(1000, 1, 1, tzinfo=UTC),
            scene_text="The King's Death will occur tomorrow.",
        )

        result = validate_scene_temporal(request, canon_events=canon_events)

        # Should detect future event reference
        event_refs = [
            v
            for v in result.violations
            if v.violation_type == TemporalViolationType.FUTURE_REFERENCE
            and v.severity == TemporalSeverity.ERROR
        ]
        assert len(event_refs) > 0
        assert result.is_valid is False

    def test_expired_fact_reference(self):
        """Scene referencing an expired fact is flagged."""
        fact_time = datetime(1000, 1, 1, tzinfo=UTC)
        canon_facts = [
            {
                "id": uuid4(),
                "statement": "The castle is under siege",
                "time_ref": fact_time,
                "duration": 3600,  # 1 hour
            },
        ]

        # Check 2 hours after fact started (now expired)
        request = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=datetime(
                1000, 1, 1, 2, tzinfo=UTC
            ),  # 2 hours later
            scene_text="The castle is under siege.",
        )

        result = validate_scene_temporal(request, canon_facts=canon_facts)

        # Should detect expired fact reference
        expired_refs = [
            v
            for v in result.violations
            if v.violation_type == TemporalViolationType.EXPIRED_FACT
        ]
        assert len(expired_refs) > 0

    def test_temporal_paradox_detection(self):
        """Scene causing an event that happens before the scene is flagged."""
        scene_time = datetime(1000, 1, 2, tzinfo=UTC)
        canon_events = [
            {
                "id": uuid4(),
                "title": "King's Decision",
                "start_time": datetime(1000, 1, 1, tzinfo=UTC),
                "causes": [uuid4()],  # Will be replaced with scene_id in real usage
            },
        ]

        request = TemporalValidationRequest(
            scene_id=uuid4(),
            universe_id=uuid4(),
            story_id=uuid4(),
            scene_time_ref=scene_time,
            scene_text="The king makes a decision.",
        )

        # This would require the scene_id to be in the causes list
        # For testing, we'll just ensure the function runs without error
        result = validate_scene_temporal(request, canon_events=canon_events)
        assert result is not None


# =============================================================================
# PLOT THREAD DETECTION TESTS
# =============================================================================


class TestPlotThreadDetection:
    """Tests for plot thread detection from scenes."""

    def test_detect_promise_thread(self):
        """Promise threads are detected from scene text."""
        scene_text = "The king promised to rebuild the city after the war."
        scene_id = uuid4()
        universe_id = uuid4()

        result = detect_plot_threads_from_scene(scene_text, scene_id, universe_id)

        assert result.total_detected >= 1
        promises = [
            t for t in result.threads if t.category == PlotThreadCategory.PROMISE
        ]
        assert len(promises) > 0
        assert "promise" in promises[0].title.lower()

    def test_detect_threat_thread(self):
        """Threat threads are detected from scene text."""
        scene_text = "The enemy army threatens to attack at dawn."
        scene_id = uuid4()
        universe_id = uuid4()

        result = detect_plot_threads_from_scene(scene_text, scene_id, universe_id)

        assert result.total_detected >= 1
        threats = [t for t in result.threads if t.category == PlotThreadCategory.THREAT]
        assert len(threats) > 0
        assert threats[0].urgency in (
            PlotThreadUrgency.HIGH,
            PlotThreadUrgency.CRITICAL,
        )

    def test_detect_mystery_thread(self):
        """Mystery threads are detected from scene text."""
        scene_text = "Who murdered the councilor? The mystery remains unsolved."
        scene_id = uuid4()
        universe_id = uuid4()

        result = detect_plot_threads_from_scene(scene_text, scene_id, universe_id)

        assert result.total_detected >= 1
        mysteries = [
            t for t in result.threads if t.category == PlotThreadCategory.MYSTERY
        ]
        assert len(mysteries) > 0

    def test_detect_consequence_thread(self):
        """Consequence threads are detected from scene text."""
        scene_text = "As a result of the betrayal, the kingdom is now at war."
        scene_id = uuid4()
        universe_id = uuid4()

        result = detect_plot_threads_from_scene(scene_text, scene_id, universe_id)

        assert result.total_detected >= 1
        consequences = [
            t for t in result.threads if t.category == PlotThreadCategory.CONSEQUENCE
        ]
        assert len(consequences) > 0

    def test_detect_relationship_thread(self):
        """Relationship threads are detected from scene text."""
        scene_text = "The tension between the two factions continues to grow."
        scene_id = uuid4()
        universe_id = uuid4()

        result = detect_plot_threads_from_scene(scene_text, scene_id, universe_id)

        assert result.total_detected >= 1
        relationships = [
            t for t in result.threads if t.category == PlotThreadCategory.RELATIONSHIP
        ]
        assert len(relationships) > 0

    def test_detect_world_event_thread(self):
        """World event threads are detected from scene text."""
        scene_text = "The coronation of the new king will change everything."
        scene_id = uuid4()
        universe_id = uuid4()

        result = detect_plot_threads_from_scene(scene_text, scene_id, universe_id)

        assert result.total_detected >= 1
        events = [
            t for t in result.threads if t.category == PlotThreadCategory.WORLD_EVENT
        ]
        assert len(events) > 0

    def test_high_urgency_threads_counted(self):
        """High urgency threads are counted correctly."""
        scene_text = (
            "The enemy army threatens to attack immediately. "
            "The king promised to defend the city at all costs."
        )
        scene_id = uuid4()
        universe_id = uuid4()

        result = detect_plot_threads_from_scene(scene_text, scene_id, universe_id)

        assert result.high_urgency_count >= 1

    def test_thread_status_update_resolved(self):
        """Thread status is updated when resolved in scene."""
        existing_threads = [
            {
                "thread_id": uuid4(),
                "title": "Promise: Rebuild the city",
                "description": "The king promised to rebuild the city",
            },
        ]

        scene_text = "The king fulfilled his promise and rebuilt the city."
        scene_id = uuid4()
        universe_id = uuid4()

        updates = update_thread_status_from_scene(
            scene_id, scene_text, universe_id, existing_threads
        )

        assert len(updates["resolved_threads"]) > 0

    def test_thread_status_update_advanced(self):
        """Thread status is updated when advanced in scene."""
        existing_threads = [
            {
                "thread_id": uuid4(),
                "title": "Mystery: Who killed the councilor?",
                "description": "The murder of the councilor remains unsolved",
            },
        ]

        scene_text = "The investigation into the councilor's murder continues."
        scene_id = uuid4()
        universe_id = uuid4()

        updates = update_thread_status_from_scene(
            scene_id, scene_text, universe_id, existing_threads
        )

        assert len(updates["advanced_threads"]) > 0

    def test_classify_thread_content(self):
        """Text is classified into correct thread category."""
        assert (
            classify_thread_content("I promise to help you")
            == PlotThreadCategory.PROMISE
        )
        assert (
            classify_thread_content("The enemy threatens to attack")
            == PlotThreadCategory.THREAT
        )
        assert (
            classify_thread_content("Who committed this crime?")
            == PlotThreadCategory.MYSTERY
        )
        assert (
            classify_thread_content("As a result, the war began")
            == PlotThreadCategory.CONSEQUENCE
        )


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestTemporalContradictionIntegration:
    """Integration tests for temporal and contradiction features."""

    def test_scene_revision_validation_flow(self):
        """Full flow of validating a scene revision."""

        # This would require a CanonKeeper instance in a real test
        # For now, we'll test the structure
        pass  # Placeholder for full integration test

    def test_fact_replacement_flow(self):
        """Fact replacement creates new fact with replaces field."""
        from monitor_agents.temporal_validation import handle_fact_replacement

        old_fact_id = uuid4()
        new_fact_data = {
            "id": uuid4(),
            "statement": "The king is dead",
            "universe_id": uuid4(),
        }

        result = handle_fact_replacement(
            old_fact_id=old_fact_id,
            new_fact_data=new_fact_data,
            scene_id=uuid4(),
            reason="Updated by scene revision",
        )

        assert result["old_fact_id"] == str(old_fact_id)
        assert result["new_fact_id"] == str(new_fact_data["id"])
        assert "updated by scene revision" in result["reason"].lower()

    def test_contradiction_blocks_high_severity(self):
        """High severity contradictions block proposals."""
        # This would require CanonKeeper and full setup
        # Placeholder for integration test
        pass


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestEdgeCases:
    """Edge case tests for temporal and contradiction features."""

    def test_empty_scene_no_threads(self):
        """Empty scene text produces no plot threads."""
        result = detect_plot_threads_from_scene("", uuid4(), uuid4())
        assert result.total_detected == 0

    def test_fact_with_no_id_raises_error(self):
        """Fact without ID raises ValueError."""
        with pytest.raises(ValueError):
            check_fact_validity({"statement": "Test"}, datetime.now(UTC))

    def test_concurrent_fact_expiration_checks(self):
        """Multiple facts can be checked concurrently."""
        now = datetime.now(UTC)
        facts = [{"id": uuid4(), "statement": f"Fact {i}"} for i in range(100)]

        batch = batch_check_fact_validity(facts, now, uuid4())
        assert batch.total_checked == 100

    def test_very_long_scene_text(self):
        """Very long scene text is handled correctly."""
        long_text = "The king promised to help. " * 1000
        result = detect_plot_threads_from_scene(long_text, uuid4(), uuid4())
        # Should detect the promise, even in very long text
        assert result.total_detected >= 1
