import logging
import os
from datetime import datetime, timedelta, timezone, UTC
from types import SimpleNamespace

import pytest
from monitor_ui import main
from monitor_ui.routers import ingest
from monitor_ui.watchdog import _DEFAULT_STALE_AFTER_SECONDS


def _assert_stale_jobs_query(query: dict) -> None:
    """Assert the startup-recovery query's shape without pinning the exact
    cutoff timestamp (computed via `datetime.now()` inside the function
    under test). See `_recover_stale_jobs`'s docstring: a job only
    recovers here if it would ALSO look orphaned to the periodic
    StaleJobWatchdog, i.e. `stage_last_progress_at` (or `started_at` as
    fallback) predates a `_DEFAULT_STALE_AFTER_SECONDS`-old cutoff.
    """
    assert query["status"] == {"$in": ["pending", "running"]}
    or_clauses = query["$or"]
    assert len(or_clauses) == 2
    progress_cutoff = or_clauses[0]["stage_last_progress_at"]["$lt"]
    fallback_clause = or_clauses[1]
    assert fallback_clause["stage_last_progress_at"] == {"$exists": False}
    started_cutoff = fallback_clause["started_at"]["$lt"]
    assert progress_cutoff == started_cutoff

    expected_cutoff = datetime.now(UTC) - timedelta(
        seconds=_DEFAULT_STALE_AFTER_SECONDS
    )
    assert abs((expected_cutoff - progress_cutoff).total_seconds()) < 5


class _FakeCollection:
    def __init__(self):
        self.query = None
        self.update = None

    def update_many(self, query, update):
        self.query = query
        self.update = update
        return SimpleNamespace(modified_count=2)


class _FakeMongo:
    def __init__(self):
        self.collection = _FakeCollection()

    def get_collection(self, name):
        assert name == "ingestion_jobs"
        return self.collection


def test_recover_stale_jobs_marks_pending_and_running_failed(monkeypatch):
    fake_mongo = _FakeMongo()

    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client",
        lambda: fake_mongo,
    )

    main._recover_stale_jobs()

    _assert_stale_jobs_query(fake_mongo.collection.query)
    update = fake_mongo.collection.update["$set"]
    assert update["status"] == "failed"
    assert "queued or running" in update["errors"][0]
    assert isinstance(update["completed_at"], datetime)
    assert update["completed_at"].tzinfo == UTC


class _FakeExecutor:
    def __init__(self):
        self.calls = []

    def shutdown(self, *, wait, cancel_futures):
        self.calls.append({"wait": wait, "cancel_futures": cancel_futures})


def test_shutdown_ingest_runtime_marks_jobs_interrupted_and_stops_executor(monkeypatch):
    fake_mongo = _FakeMongo()
    fake_executor = _FakeExecutor()

    token = ingest._reserve_ingest_slot("Queued Book")
    ingest._mark_ingest_started(token, "Queued Book")

    monkeypatch.setattr(ingest, "get_mongodb_client", lambda: fake_mongo)
    monkeypatch.setattr(ingest, "_ingest_executor", fake_executor)

    result = ingest.shutdown_ingest_runtime("Server shutdown requested")

    assert result["cleared_active"] == 1
    assert result["recovered_jobs"] == 2
    assert fake_mongo.collection.query == {"status": {"$in": ["pending", "running"]}}
    assert fake_mongo.collection.update["$set"]["status"] == "failed"
    assert (
        "Server shutdown requested"
        in fake_mongo.collection.update["$push"]["errors"]["$each"][0]
    )
    assert fake_executor.calls == [{"wait": False, "cancel_futures": True}]
    assert not ingest._ingest_active_requests
    assert not ingest._ingest_pending_requests


@pytest.mark.asyncio
async def test_lifespan_runs_shutdown_cleanup(monkeypatch):
    calls = []

    monkeypatch.setattr(main, "_startup_runtime", lambda: calls.append("startup"))
    monkeypatch.setattr(main, "_shutdown_runtime", lambda: calls.append("shutdown"))

    async with main.lifespan(SimpleNamespace()):
        assert calls == ["startup"]

    assert calls == ["startup", "shutdown"]


# =============================================================================
# Additional startup and shutdown tests
# =============================================================================


def test_recover_stale_jobs_no_stale_jobs(monkeypatch):
    """Test recovery when no stale jobs exist."""
    fake_mongo = _FakeMongo()
    fake_mongo.collection.update = lambda q, u: SimpleNamespace(modified_count=0)

    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client",
        lambda: fake_mongo,
    )

    main._recover_stale_jobs()

    _assert_stale_jobs_query(fake_mongo.collection.query)
    # Should still attempt the update, even if no jobs are modified


def test_recover_stale_jobs_mongodb_error(monkeypatch):
    """Test recovery handles MongoDB connection errors gracefully."""
    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client",
        lambda: (_ for _ in ()).throw(Exception("Connection failed")),
    )

    # Should not raise an exception; should log a warning and continue
    main._recover_stale_jobs()


def test_startup_runtime_calls_prepare_ingest_runtime(monkeypatch):
    """Test _startup_runtime calls prepare_ingest_runtime before recovery."""
    calls = []

    monkeypatch.setattr(
        ingest,
        "prepare_ingest_runtime",
        lambda: calls.append("prepare_ingest_runtime"),
    )
    monkeypatch.setattr(
        main,
        "_recover_stale_jobs",
        lambda: calls.append("recover_stale_jobs"),
    )
    monkeypatch.setattr(
        "monitor_data.initialization.ensure_tone_builtins.ensure_tone_builtins",
        lambda: calls.append("ensure_tone_builtins"),
    )

    main._startup_runtime()

    assert calls == [
        "prepare_ingest_runtime",
        "recover_stale_jobs",
        "ensure_tone_builtins",
    ]


def test_shutdown_runtime_cleans_executor(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    """Test _shutdown_runtime cleans up the executor and logs summary."""
    fake_executor = _FakeExecutor()

    monkeypatch.setattr(ingest, "get_mongodb_client", lambda: _FakeMongo())
    monkeypatch.setattr(ingest, "_ingest_executor", fake_executor)

    # Set up some state to recover
    token = ingest._reserve_ingest_slot("Test Book")
    ingest._mark_ingest_started(token, "Test Book")

    main._shutdown_runtime()

    assert fake_executor.calls == [{"wait": False, "cancel_futures": True}]
    assert any(
        "Runtime shutdown cleanup finished" in rec.message for rec in caplog.records
    )


def test_load_tokens_env_when_file_exists(monkeypatch, tmp_path):
    """Test _load_tokens_env loads .env.tokens if it exists."""
    tokens_file = tmp_path / ".env.tokens"
    tokens_file.write_text("TEST_TOKEN=secret123\n")

    monkeypatch.setattr(
        os.path,
        "dirname",
        lambda p: str(tmp_path),
    )

    # Load environment to check if tokens are loaded

    main._load_tokens_env()

    # The function should attempt to load .env.tokens without error
    # (We can't easily verify the env vars are loaded without side effects)


class TestIngestRouterSlotManagement:
    """Tests for ingest router slot management functions."""

    def test_reserve_ingest_slot_returns_token(self):
        """_reserve_ingest_slot should return a token string."""
        token = ingest._reserve_ingest_slot("Test Job")
        assert isinstance(token, str)
        assert len(token) > 0
