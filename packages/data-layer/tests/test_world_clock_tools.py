"""Tests for the world clock MongoDB tools (CF-11 Advance World Time).

Pins the behaviors the gap plan calls out: advancing, overdue computation,
idempotency (monotonic clock), and the advance audit log — plus deadline
upserts and the off-screen summary attachment.

Run:
    uv run pytest packages/data-layer/tests/test_world_clock_tools.py -q -p no:cacheprovider
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import pytest
from monitor_data.schemas.world_clock import (
    MAX_ADVANCE_RECORDS,
    OffScreenSummaryRecord,
    WorldClockAdvance,
    WorldClockDeadlineUpsert,
    WorldClockQuery,
    deadline_status,
    parse_time_delta,
)
from monitor_data.tools.mongodb_tools.world_clock import (
    mongodb_advance_world_clock,
    mongodb_get_world_clock,
    mongodb_list_due_deadlines,
    mongodb_record_offscreen_summary,
    mongodb_upsert_world_deadline,
)


class _FakeClockCollection:
    """In-memory stand-in for the ``world_clocks`` collection.

    Mirrors the production surface the tools use: ``find_one`` and
    ``update_one(..., upsert=True)`` keyed on (universe_id, story_id).
    """

    def __init__(self) -> None:
        self.docs: dict[tuple[str, str], dict] = {}

    def find_one(self, query: dict) -> dict | None:
        doc = self.docs.get((query["universe_id"], query["story_id"]))
        return dict(doc) if doc else None

    def update_one(self, query: dict, update: dict, upsert: bool = False) -> None:
        key = (query["universe_id"], query["story_id"])
        existing = self.docs.get(key)
        if existing is None:
            if not upsert:
                return  # mirror pymongo's no-op on no-match
            existing = {}
            self.docs[key] = existing
        for field, value in update.get("$set", {}).items():
            existing[field] = value


def _patch_collection(fake: _FakeClockCollection):
    fake_client = type("C", (), {"get_collection": staticmethod(lambda _name: fake)})()
    return patch(
        "monitor_data.tools.mongodb_tools.world_clock.get_mongodb_client",
        return_value=fake_client,
    )


def _advance(story_id, universe_id, **overrides):
    payload = {
        "universe_id": universe_id,
        "story_id": story_id,
        "target_time": datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
    }
    payload.update(overrides)
    return WorldClockAdvance(**payload)


def _query(story_id, universe_id):
    return WorldClockQuery(universe_id=universe_id, story_id=story_id)


# ---------------------------------------------------------------------------
# Delta parsing (pure)
# ---------------------------------------------------------------------------


class TestParseTimeDelta:
    def test_common_deltas(self):
        from datetime import timedelta

        assert parse_time_delta("+3 days") == timedelta(days=3)
        assert parse_time_delta("2 hours") == timedelta(hours=2)
        assert parse_time_delta("+30 minutes") == timedelta(minutes=30)
        assert parse_time_delta("  1 week ") == timedelta(weeks=1)
        assert parse_time_delta("+10 seconds") == timedelta(seconds=10)

    @pytest.mark.parametrize("bad", ["", "-3 days", "+-2 days", "three days", "+0 days", "3 lightyears"])
    def test_rejects_junk_and_backwards(self, bad: str):
        with pytest.raises(ValueError):
            parse_time_delta(bad)


# ---------------------------------------------------------------------------
# Deadline status computation (pure, deterministic)
# ---------------------------------------------------------------------------


class TestDeadlineStatus:
    def test_upcoming_due_overdue_by_date(self):
        due = datetime(1012, 3, 3, 18, 0, tzinfo=UTC)
        assert deadline_status(due, datetime(1012, 3, 2, 9, 0, tzinfo=UTC)) == "upcoming"
        # Due date reached: still "due" all day, even after the due time.
        assert deadline_status(due, datetime(1012, 3, 3, 9, 0, tzinfo=UTC)) == "due"
        assert deadline_status(due, datetime(1012, 3, 3, 23, 59, tzinfo=UTC)) == "due"
        # Date passed: overdue.
        assert deadline_status(due, datetime(1012, 3, 4, 0, 0, tzinfo=UTC)) == "overdue"

    def test_naive_values_treated_as_utc(self):
        assert deadline_status(datetime(1012, 3, 3, 0, 0), datetime(1012, 3, 4, 0, 0)) == "overdue"


# ---------------------------------------------------------------------------
# Advance: initialization, movement, monotonicity, audit log
# ---------------------------------------------------------------------------


class TestAdvanceClock:
    def test_get_miss_returns_none(self):
        fake = _FakeClockCollection()
        with _patch_collection(fake):
            assert mongodb_get_world_clock(_query(uuid4(), uuid4())) is None

    def test_first_set_needs_an_absolute_target(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            with pytest.raises(ValueError, match="absolute world time"):
                mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=None, delta="+3 days"))

    def test_absolute_initialization_records_the_first_audit_entry(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            result = mongodb_advance_world_clock(_advance(story_id, universe_id))
            clock = mongodb_get_world_clock(_query(story_id, universe_id))

        assert result.initialized is True
        assert result.changed is True
        assert clock is not None
        assert clock.current_at == datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        assert clock.display == "1012-03-01T09:00:00+00:00"
        assert len(clock.advances) == 1
        assert clock.advances[0].from_at is None
        assert clock.advances[0].to_at == datetime(1012, 3, 1, 9, 0, tzinfo=UTC)

    def test_relative_advance_moves_time_and_appends_audit(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            result = mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=None, delta="+3 days"))
            clock = mongodb_get_world_clock(_query(story_id, universe_id))

        assert result.changed is True
        assert result.initialized is False
        assert clock is not None
        assert clock.current_at == datetime(1012, 3, 4, 9, 0, tzinfo=UTC)
        # Newest record first, from → to preserved for the CF-2 time line.
        assert len(clock.advances) == 2
        assert clock.advances[0].delta == "+3 days"
        assert clock.advances[0].from_at == datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        assert clock.advances[0].to_at == datetime(1012, 3, 4, 9, 0, tzinfo=UTC)
        # Display follows the new time (no override set).
        assert clock.display == "1012-03-04T09:00:00+00:00"

    def test_repeating_the_same_advance_is_idempotent(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        target = datetime(1012, 3, 5, 18, 0, tzinfo=UTC)
        with _patch_collection(fake):
            first = mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=target))
            second = mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=target))
            clock = mongodb_get_world_clock(_query(story_id, universe_id))

        assert first.changed is True
        assert second.changed is False
        assert clock is not None
        # The no-op added no audit record.
        assert len(clock.advances) == 1

    def test_backwards_moves_are_refused(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=datetime(1012, 3, 5, tzinfo=UTC)))
            with pytest.raises(ValueError, match="backwards"):
                mongodb_advance_world_clock(
                    _advance(story_id, universe_id, target_time=datetime(1012, 3, 1, tzinfo=UTC))
                )
            with pytest.raises(ValueError, match="backwards"):
                mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=None, delta="-2 days"))
            clock = mongodb_get_world_clock(_query(story_id, universe_id))

        assert clock is not None
        assert clock.current_at == datetime(1012, 3, 5, 0, 0, tzinfo=UTC)
        assert len(clock.advances) == 1

    def test_bad_delta_is_refused_and_changes_nothing(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            with pytest.raises(ValueError, match="delta|unit"):
                mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=None, delta="three fortnights"))
            clock = mongodb_get_world_clock(_query(story_id, universe_id))

        assert clock is not None
        assert clock.current_at == datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        assert len(clock.advances) == 1

    def test_display_override_persists_across_advances(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            mongodb_advance_world_clock(
                _advance(
                    story_id,
                    universe_id,
                    target_time=None,
                    delta="+1 day",
                    display="1st of Emberfall",
                )
            )
            clock = mongodb_get_world_clock(_query(story_id, universe_id))

        assert clock is not None
        assert clock.display == "1st of Emberfall"

    def test_audit_log_is_capped(self):
        from datetime import timedelta

        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        base = datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            for day in range(1, MAX_ADVANCE_RECORDS + 5):
                mongodb_advance_world_clock(
                    _advance(
                        story_id,
                        universe_id,
                        target_time=base + timedelta(days=day),
                    )
                )
            clock = mongodb_get_world_clock(_query(story_id, universe_id))

        assert clock is not None
        assert len(clock.advances) == MAX_ADVANCE_RECORDS

    def test_universes_and_stories_have_independent_clocks(self):
        fake = _FakeClockCollection()
        mine, theirs = uuid4(), uuid4()
        story_a, story_b = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_a, mine))
            mongodb_advance_world_clock(_advance(story_a, theirs, target_time=datetime(1012, 6, 1, tzinfo=UTC)))
            mongodb_advance_world_clock(_advance(story_b, mine, target_time=datetime(999, 1, 1, tzinfo=UTC)))

            clock = mongodb_get_world_clock(_query(story_a, mine))
            other_story = mongodb_get_world_clock(_query(story_b, mine))

        assert clock is not None and clock.current_at == datetime(1012, 3, 1, 9, 0, tzinfo=UTC)
        assert other_story is not None and other_story.current_at == datetime(999, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Deadlines: upsert, status flips, crossed detection, list_due_deadlines
# ---------------------------------------------------------------------------


class TestDeadlines:
    def test_upsert_requires_an_existing_clock(self):
        fake = _FakeClockCollection()
        with _patch_collection(fake):
            with pytest.raises(ValueError, match="absolute world time"):
                mongodb_upsert_world_deadline(
                    WorldClockDeadlineUpsert(
                        universe_id=uuid4(),
                        story_id=uuid4(),
                        title="The ransom is due",
                        due_at=datetime(1012, 3, 3, tzinfo=UTC),
                    )
                )

    def test_create_and_replace_roundtrip(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            created = mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="The ransom is due",
                    due_at=datetime(1012, 3, 3, tzinfo=UTC),
                    notes="Baron Vasz demands the silver",
                )
            )
            deadline_id = created.deadlines[0].id
            replaced = mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="Ransom raised",
                    due_at=datetime(1012, 3, 6, tzinfo=UTC),
                    deadline_id=deadline_id,
                )
            )

        assert len(created.deadlines) == 1
        assert created.deadlines[0].status == "upcoming"
        assert len(replaced.deadlines) == 1
        assert replaced.deadlines[0].id == deadline_id
        assert replaced.deadlines[0].title == "Ransom raised"
        assert replaced.deadlines[0].due_at == datetime(1012, 3, 6, tzinfo=UTC)

    def test_unknown_deadline_id_is_refused(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            with pytest.raises(ValueError, match="Unknown deadline id"):
                mongodb_upsert_world_deadline(
                    WorldClockDeadlineUpsert(
                        universe_id=universe_id,
                        story_id=story_id,
                        title="Ghost",
                        due_at=datetime(1012, 3, 3, tzinfo=UTC),
                        deadline_id="nope",
                    )
                )

    def test_status_flips_due_then_overdue_as_time_passes(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="The ritual completes",
                    due_at=datetime(1012, 3, 3, tzinfo=UTC),
                )
            )

            mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=None, delta="+2 days"))
            due_view = mongodb_get_world_clock(_query(story_id, universe_id))
            mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=None, delta="+1 day"))
            overdue_view = mongodb_get_world_clock(_query(story_id, universe_id))

        assert due_view is not None and due_view.deadlines[0].status == "due"
        assert overdue_view is not None and overdue_view.deadlines[0].status == "overdue"

    def test_crossed_reports_newly_flipped_deadlines_only(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            # One deadline inside the advance window, one already behind us.
            mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="Due inside window",
                    due_at=datetime(1012, 3, 3, tzinfo=UTC),
                )
            )
            mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="Already late",
                    due_at=datetime(1012, 2, 20, tzinfo=UTC),
                )
            )
            result = mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=None, delta="+5 days"))
            # Repeating the same window adds nothing to crossed.
            again = mongodb_advance_world_clock(_advance(story_id, universe_id, target_time=None, delta="+5 days"))

        assert [d.title for d in result.crossed] == ["Due inside window"]
        assert result.crossed[0].status == "overdue"
        # The second move crosses nothing new (both were already past).
        assert again.crossed == []

    def test_list_due_deadlines_returns_due_and_overdue_sorted(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            # No clock yet → nothing due.
            assert mongodb_list_due_deadlines(_query(story_id, universe_id)) == []

            mongodb_advance_world_clock(_advance(story_id, universe_id))
            assert mongodb_list_due_deadlines(_query(story_id, universe_id)) == []

            mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="Later",
                    due_at=datetime(1012, 3, 20, tzinfo=UTC),
                )
            )
            mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="Overdue first",
                    due_at=datetime(1012, 2, 20, tzinfo=UTC),
                )
            )
            mongodb_upsert_world_deadline(
                WorldClockDeadlineUpsert(
                    universe_id=universe_id,
                    story_id=story_id,
                    title="Due today",
                    due_at=datetime(1012, 3, 1, 18, 0, tzinfo=UTC),
                )
            )
            due = mongodb_list_due_deadlines(_query(story_id, universe_id))

        assert [d.title for d in due] == ["Overdue first", "Due today"]
        assert [d.status for d in due] == ["overdue", "due"]


# ---------------------------------------------------------------------------
# Off-screen summary attachment
# ---------------------------------------------------------------------------


class TestOffScreenSummary:
    def test_summary_roundtrip(self):
        fake = _FakeClockCollection()
        story_id, universe_id = uuid4(), uuid4()
        with _patch_collection(fake):
            mongodb_advance_world_clock(_advance(story_id, universe_id))
            saved = mongodb_record_offscreen_summary(
                OffScreenSummaryRecord(
                    universe_id=universe_id,
                    story_id=story_id,
                    summary="While the party rested, Mira struck a deal with the guild.",
                    recorded_at=datetime(2026, 11, 10, tzinfo=UTC),
                )
            )
            clock = mongodb_get_world_clock(_query(story_id, universe_id))

        assert saved.offscreen_summary.startswith("While the party rested")
        assert clock is not None
        assert clock.offscreen_summary_at == datetime(2026, 11, 10, tzinfo=UTC)

    def test_summary_requires_an_existing_clock(self):
        fake = _FakeClockCollection()
        with _patch_collection(fake):
            with pytest.raises(ValueError, match="No world clock"):
                mongodb_record_offscreen_summary(
                    OffScreenSummaryRecord(
                        universe_id=uuid4(),
                        story_id=uuid4(),
                        summary="Nothing yet.",
                    )
                )
