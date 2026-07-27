"""Regression tests: startup job recovery must not kill jobs that are
still genuinely in flight.

Live bug (2026-07-22): starting the UI backend server while a completely
independent `monitor ingest file` CLI process was seconds into a real run
immediately marked that job "failed" -- _recover_stale_jobs() treated
status=running at boot as sufficient evidence of an orphan, but the CLI's
ingest process has no relationship to this backend's in-memory queue or
lifecycle at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from monitor_ui import main as main_module


class _FakeUpdateResult:
    def __init__(self, modified_count: int) -> None:
        self.modified_count = modified_count


class _FakeCollection:
    """Minimal update_many-only stand-in, mirroring test_watchdog.py's style."""

    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def _matches(self, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        if doc.get("status") not in query["status"]["$in"]:
            return False
        for clause in query["$or"]:
            if "stage_last_progress_at" in clause and "$lt" in clause.get("stage_last_progress_at", {}):
                val = doc.get("stage_last_progress_at")
                if val is not None and val < clause["stage_last_progress_at"]["$lt"]:
                    return True
            elif clause.get("stage_last_progress_at", {}).get("$exists") is False:
                if "stage_last_progress_at" not in doc:
                    started = doc.get("started_at")
                    if started is not None and started < clause["started_at"]["$lt"]:
                        return True
        return False

    def update_many(self, query: dict[str, Any], update: dict[str, Any]):
        modified = 0
        for doc in self.docs:
            if self._matches(doc, query):
                doc.update(update["$set"])
                modified += 1
        return _FakeUpdateResult(modified)


class _FakeMongoClient:
    def __init__(self, coll: _FakeCollection) -> None:
        self._coll = coll

    def get_collection(self, _name: str) -> _FakeCollection:
        return self._coll


def _patch_mongo(monkeypatch: pytest.MonkeyPatch, coll: _FakeCollection) -> None:
    import monitor_data.db.mongodb as mongodb_module

    monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: _FakeMongoClient(coll))


def test_freshly_started_job_from_an_independent_process_is_left_alone(monkeypatch):
    """The exact live bug: a job that started seconds ago (e.g. via the CLI,
    a completely separate process from this backend) must NOT be failed."""
    now = datetime.now(UTC)
    job = {
        "job_id": "fresh-1",
        "status": "running",
        "started_at": now - timedelta(seconds=10),
    }
    coll = _FakeCollection([job])
    _patch_mongo(monkeypatch, coll)

    main_module._recover_stale_jobs()

    assert job["status"] == "running"


def test_genuinely_orphaned_job_is_still_recovered(monkeypatch):
    """A job whose started_at long predates any plausible restart gap
    (matching the periodic watchdog's own default threshold) is still
    correctly recovered."""
    now = datetime.now(UTC)
    job = {
        "job_id": "orphan-1",
        "status": "running",
        "started_at": now - timedelta(hours=2),
    }
    coll = _FakeCollection([job])
    _patch_mongo(monkeypatch, coll)

    main_module._recover_stale_jobs()

    assert job["status"] == "failed"
    assert "errors" in job
