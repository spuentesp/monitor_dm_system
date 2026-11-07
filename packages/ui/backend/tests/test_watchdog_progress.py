"""The real watchdog must leave a progressing job alone, and still fail a dead one (I-17)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import mongomock
import pytest
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import IngestionJobCreate, IngestionJobUpdate
from monitor_data.tools.mongodb_tools import ingestion_jobs
from monitor_ui.watchdog import StaleJobWatchdog


@pytest.fixture
def collection():
    database = mongomock.MongoClient().db
    client = SimpleNamespace(get_collection=lambda name: database[name])
    with patch.object(ingestion_jobs, "get_mongodb_client", return_value=client):
        yield database["ingestion_jobs"]


def _running_job(collection, age: timedelta):
    job = ingestion_jobs.mongodb_create_ingestion_job(
        IngestionJobCreate(universe_id=uuid.uuid4(), source_id=uuid.uuid4(), doc_id=uuid.uuid4())
    )
    then = datetime.now(UTC) - age
    collection.update_one(
        {"job_id": str(job.job_id)},
        {"$set": {"status": "running", "started_at": then, "stage_last_progress_at": then}},
    )
    return job


@pytest.mark.unit
async def test_old_job_that_reports_progress_survives_and_a_silent_one_fails(collection):
    alive = _running_job(collection, timedelta(hours=5))
    dead = _running_job(collection, timedelta(hours=5))
    ingestion_jobs.mongodb_update_ingestion_job(alive.job_id, IngestionJobUpdate(progress=0.5))

    await StaleJobWatchdog(get_collection=lambda: collection, stale_after_seconds=45 * 60).tick_once()

    assert ingestion_jobs.mongodb_get_ingestion_job(alive.job_id).status == IngestionStatus.RUNNING
    assert ingestion_jobs.mongodb_get_ingestion_job(dead.job_id).status == IngestionStatus.FAILED


@pytest.mark.unit
async def test_an_empty_update_is_enough_to_count_as_a_heartbeat(collection):
    job = _running_job(collection, timedelta(hours=5))
    ingestion_jobs.mongodb_update_ingestion_job(job.job_id, IngestionJobUpdate())
    await StaleJobWatchdog(get_collection=lambda: collection, stale_after_seconds=45 * 60).tick_once()
    assert ingestion_jobs.mongodb_get_ingestion_job(job.job_id).status == IngestionStatus.RUNNING
