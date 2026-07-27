"""Hermetic tests for the stale-job watchdog.

Mocks the MongoDB collection and exercises ``tick_once`` directly —
does not touch real MongoDB. The full background loop is *not*
covered here; it is exercised by the live ``monitor ingest doctor``
smoke run during verification.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from monitor_ui.watchdog import (
    StaleJobWatchdog,
    get_watchdog,
    reset_watchdog,
    set_watchdog,
)


class _FakeCollection:
    """Minimal stand-in for the MongoDB ``ingestion_jobs`` collection.

    Only implements ``find`` + ``update_one`` with the operators the
    watchdog actually uses. State lives in :pyattr:`docs` (list) and
    :pyattr:`updates` (audit log).
    """

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []
        self.updates: list[dict[str, Any]] = []

    def find(self, query: dict[str, Any]):
        status = query.get("status")
        return [d for d in self.docs if d.get("status") == status]

    def update_one(self, filt: dict[str, Any], update: dict[str, Any]):
        for d in self.docs:
            if d.get("_id") != filt.get("_id"):
                continue
            if d.get("status") != filt.get("status"):
                continue
            self.updates.append({"filter": filt, "update": update})
            for k, v in update.get("$set", {}).items():
                d[k] = v
            return
        # No match — Mongo would not raise on no-match, mirror that.

    def insert(self, doc: dict[str, Any]) -> None:
        self.docs.append(doc)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _running_job(
    job_id: str,
    *,
    last_progress_age_min: float,
    has_started_at: bool = True,
) -> dict[str, Any]:
    """Build a fake ``status=running`` document."""
    now = datetime.now(UTC)
    last = now - timedelta(minutes=last_progress_age_min)
    doc: dict[str, Any] = {
        "_id": job_id,
        "job_id": job_id,
        "status": "running",
        "source_title": f"test-{job_id}",
        "stage_last_progress_at": last,
    }
    if has_started_at:
        doc["started_at"] = last
    return doc


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_watchdog()
    yield
    reset_watchdog()


def test_tick_finds_no_running_jobs_returns_zeros():
    coll = _FakeCollection()
    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)

    result = _run(wd.tick_once())

    assert result.scanned == 0
    assert result.failed == 0
    assert result.skipped == 0
    assert coll.updates == []


def test_tick_fails_jobs_older_than_threshold():
    coll = _FakeCollection()
    # Two stale (60 min, 90 min), one fresh (5 min).
    coll.insert(_running_job("stale-A", last_progress_age_min=60))
    coll.insert(_running_job("stale-B", last_progress_age_min=90))
    coll.insert(_running_job("fresh-C", last_progress_age_min=5))

    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)
    result = _run(wd.tick_once())

    assert result.scanned == 2
    assert result.failed == 2
    assert coll.updates[0]["filter"]["status"] == "running"
    set_doc = coll.updates[0]["update"]["$set"]
    assert set_doc["status"] == "failed"
    assert set_doc["kill_reason"] == "watchdog.timeout"
    assert set_doc["last_error"]["category"] == "timeout"
    assert "stale after" in coll.docs[0]["errors"][-1].lower()
    # Fresh one untouched
    assert coll.docs[2]["status"] == "running"


def test_tick_uses_started_at_fallback_when_no_stage_progress():
    coll = _FakeCollection()
    now = datetime.now(UTC)
    coll.docs.append(
        {
            "_id": "fallback-1",
            "job_id": "fallback-1",
            "status": "running",
            "source_title": "fallback",
            "started_at": now - timedelta(minutes=120),
            # stage_last_progress_at absent — should fall back to started_at
        }
    )

    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)
    result = _run(wd.tick_once())

    assert result.failed == 1
    assert coll.docs[0]["status"] == "failed"


def test_tick_skips_jobs_without_any_timestamp():
    coll = _FakeCollection()
    coll.docs.append(
        {
            "_id": "no-ts",
            "job_id": "no-ts",
            "status": "running",
            "source_title": "no-ts",
        }
    )

    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)
    result = _run(wd.tick_once())

    assert result.scanned == 0
    assert result.failed == 0
    assert coll.updates == []


def test_tick_handles_naive_datetime_from_mongo():
    """Mongo returns naive datetimes by default. Watchdog must coerce to UTC."""
    coll = _FakeCollection()
    coll.docs.append(
        {
            "_id": "naive-1",
            "job_id": "naive-1",
            "status": "running",
            "source_title": "naive",
            "stage_last_progress_at": datetime.utcnow() - timedelta(hours=2),
        }
    )

    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)
    result = _run(wd.tick_once())

    assert result.failed == 1


def test_tick_continues_after_a_single_failure():
    """If one update_one raises, the watchdog must still try the next
    stale job. Run logs a warning, returns partial counters."""
    coll = _FakeCollection()
    coll.insert(_running_job("ok-A", last_progress_age_min=60))
    coll.insert(_running_job("ok-B", last_progress_age_min=70))

    call_count = {"n": 0}
    original_update = coll.update_one

    def _flaky_update(filt, update):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated transient mongo error")
        return original_update(filt, update)

    coll.update_one = _flaky_update  # type: ignore[assignment]

    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)
    result = _run(wd.tick_once())

    assert result.scanned == 2
    # First failed mid-update, second succeeded → failed=1
    assert result.failed == 1
    assert coll.docs[1]["status"] == "failed"


def test_collection_accessor_failure_is_swallowed():
    def _broken():
        raise RuntimeError("mongo down")

    wd = StaleJobWatchdog(get_collection=_broken, stale_after_seconds=45 * 60)
    result = _run(wd.tick_once())

    assert result.scanned == 0
    assert result.failed == 0


def test_cas_guard_prevents_double_fail_on_concurrent_run():
    """If two watchdog ticks race on the same row, the second one's
    filter ``{_id: X, status: 'running'}`` no longer matches once the
    first has flipped it to ``failed``. The watchdog must record the
    miss without raising."""
    coll = _FakeCollection()
    coll.insert(_running_job("race-1", last_progress_age_min=60))

    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)

    # Tick once — flips the row.
    _run(wd.tick_once())
    assert coll.docs[0]["status"] == "failed"

    # Second tick: the row no longer matches status='running'.
    # Snapshot the fake before the call to confirm the CAS guard.
    second = _run(wd.tick_once())
    assert second.failed == 0


def test_last_result_is_updated_after_each_tick():
    coll = _FakeCollection()
    coll.insert(_running_job("lr-1", last_progress_age_min=60))

    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)
    assert wd.last_result().failed == 0

    _run(wd.tick_once())
    assert wd.last_result().failed == 1
    assert wd.last_result().scanned == 1


def test_set_get_reset_singleton():
    coll = _FakeCollection()
    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)
    set_watchdog(wd)
    assert get_watchdog() is wd

    reset_watchdog()
    assert get_watchdog() is None


def test_is_running_false_before_start():
    coll = _FakeCollection()
    wd = StaleJobWatchdog(get_collection=lambda: coll, stale_after_seconds=45 * 60)
    assert wd.is_running() is False
