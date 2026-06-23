from uuid import uuid4

import pytest

from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.ingestion_jobs import (
    IngestionJobCreate,
    IngestionJobFilter,
    IngestionJobUpdate,
    IngestionStage,
)
from monitor_data.tools.mongodb_tools.ingestion_jobs import (
    mongodb_create_ingestion_job,
    mongodb_delete_ingestion_job,
    mongodb_get_ingestion_job,
    mongodb_list_ingestion_jobs,
    mongodb_update_ingestion_job,
)


class _FakeJobsCollection:
    def __init__(self):
        self.jobs = {}
        self._insert_called = False

    def insert_one(self, doc):
        self._insert_called = True
        self.jobs[doc["job_id"]] = doc

    def find_one(self, query):
        if "job_id" in query:
            return self.jobs.get(query["job_id"])
        return None

    def find_one_and_update(self, query, update, return_document=True):
        if "job_id" not in query:
            return None
        job_id = query["job_id"]
        if job_id not in self.jobs:
            return None

        job_doc = self.jobs[job_id].copy()

        # Apply $set operations
        for key, value in update.get("$set", {}).items():
            job_doc[key] = value

        # Apply $push operations
        for key, spec in update.get("$push", {}).items():
            existing = list(job_doc.get(key, []))
            existing.extend(spec.get("$each", []))
            slice_limit = spec.get("$slice")
            if isinstance(slice_limit, int) and slice_limit < 0:
                existing = existing[slice_limit:]
            job_doc[key] = existing

        self.jobs[job_id] = job_doc
        return job_doc.copy()

    def count_documents(self, query):
        count = 0
        for job in self.jobs.values():
            match = True
            if "universe_id" in query and job.get("universe_id") != query["universe_id"]:
                match = False
            if "source_id" in query and job.get("source_id") != query["source_id"]:
                match = False
            if "status" in query and job.get("status") != query["status"]:
                match = False
            if match:
                count += 1
        return count

    def find(self, query):
        results = []
        for job in self.jobs.values():
            match = True
            if "universe_id" in query and job.get("universe_id") != query["universe_id"]:
                match = False
            if "source_id" in query and job.get("source_id") != query["source_id"]:
                match = False
            if "status" in query and job.get("status") != query["status"]:
                match = False
            if match:
                results.append(job)
        return _FakeCursor(results)

    def delete_one(self, query):
        if "job_id" in query and query["job_id"] in self.jobs:
            del self.jobs[query["job_id"]]
            return 1
        return 0


class _FakeCursor:
    def __init__(self, results):
        self.results = results

    def sort(self, key, direction):
        # Sort by started_at
        if direction == -1:  # desc
            self.results = sorted(self.results, key=lambda x: x.get("started_at", ""), reverse=True)
        else:  # asc
            self.results = sorted(self.results, key=lambda x: x.get("started_at", ""))
        return self

    def skip(self, offset):
        self.results = self.results[offset:]
        return self

    def limit(self, limit):
        self.results = self.results[:limit]
        return self

    def __iter__(self):
        return iter(self.results)


class _FakeMongo:
    def __init__(self):
        self.collection = _FakeJobsCollection()

    def get_collection(self, name):
        assert name == "ingestion_jobs"
        return self.collection


# =============================================================================
# TESTS FOR mongodb_create_ingestion_job
# =============================================================================


def test_create_ingestion_job_basic(monkeypatch):
    """Test basic job creation with required fields."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    job = mongodb_create_ingestion_job(create_params)

    assert job.universe_id == universe_id
    assert job.source_id == source_id
    assert job.doc_id == doc_id
    assert job.source_title == "Test Source"
    assert job.status == IngestionStatus.PENDING
    assert job.current_stage is None
    assert job.progress == 0.0
    assert job.snippet_count == 0
    assert job.entities_extracted == 0
    assert job.axioms_extracted == 0
    assert fake_mongo.collection._insert_called


def test_create_ingestion_job_with_explicit_job_id(monkeypatch):
    """Test job creation with explicit job_id."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()
    job_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
        job_id=job_id,
    )

    job = mongodb_create_ingestion_job(create_params)

    assert job.job_id == job_id


def test_create_ingestion_job_with_pipeline_stages(monkeypatch):
    """Test job creation with custom pipeline stages."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
        pipeline_stages=[
            IngestionStage.EXTRACT,
            IngestionStage.EMBED,
            IngestionStage.ANALYZE,
        ],
    )

    job = mongodb_create_ingestion_job(create_params)

    assert len(job.pipeline_stages) == 3
    assert IngestionStage.EXTRACT in job.pipeline_stages
    assert IngestionStage.EMBED in job.pipeline_stages
    assert IngestionStage.ANALYZE in job.pipeline_stages


def test_create_ingestion_job_with_processing_checklist(monkeypatch):
    """Test job creation with processing checklist."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
        processing_checklist=["extract_entities", "detect_game_system"],
    )

    job = mongodb_create_ingestion_job(create_params)

    assert "extract_entities" in job.processing_checklist
    assert "detect_game_system" in job.processing_checklist


# =============================================================================
# TESTS FOR mongodb_get_ingestion_job
# =============================================================================


def test_get_ingestion_job_existing(monkeypatch):
    """Test getting an existing ingestion job."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)
    retrieved_job = mongodb_get_ingestion_job(created_job.job_id)

    assert retrieved_job is not None
    assert retrieved_job.job_id == created_job.job_id
    assert retrieved_job.universe_id == universe_id
    assert retrieved_job.source_title == "Test Source"


def test_get_ingestion_job_not_found(monkeypatch):
    """Test getting a non-existent ingestion job returns None."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    job_id = uuid4()
    result = mongodb_get_ingestion_job(job_id)

    assert result is None


# =============================================================================
# TESTS FOR mongodb_update_ingestion_job
# =============================================================================


def test_update_ingestion_job_status(monkeypatch):
    """Test updating job status."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    updated_job = mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(status=IngestionStatus.RUNNING),
    )

    assert updated_job.status == IngestionStatus.RUNNING


def test_update_ingestion_job_progress(monkeypatch):
    """Test updating job progress."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    updated_job = mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(progress=0.75),
    )

    assert updated_job.progress == 0.75


def test_update_ingestion_job_extraction_counters(monkeypatch):
    """Test updating extraction counters."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    updated_job = mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(
            snippet_count=150,
            entities_extracted=25,
            axioms_extracted=10,
        ),
    )

    assert updated_job.snippet_count == 150
    assert updated_job.entities_extracted == 25
    assert updated_job.axioms_extracted == 10


def test_update_ingestion_job_not_found_raises_error(monkeypatch):
    """Test that updating a non-existent job raises ValueError."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    job_id = uuid4()

    with pytest.raises(ValueError, match="IngestionJob .* not found"):
        mongodb_update_ingestion_job(
            job_id,
            IngestionJobUpdate(status=IngestionStatus.RUNNING),
        )


# =============================================================================
# TESTS FOR mongodb_list_ingestion_jobs
# =============================================================================


def test_list_ingestion_jobs_all(monkeypatch):
    """Test listing all ingestion jobs without filters."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    # Create 3 jobs
    for i in range(3):
        create_params = IngestionJobCreate(
            universe_id=uuid4(),
            source_id=uuid4(),
            doc_id=uuid4(),
            source_title=f"Test Source {i}",
        )
        mongodb_create_ingestion_job(create_params)

    result = mongodb_list_ingestion_jobs(IngestionJobFilter())

    assert len(result.jobs) == 3
    assert result.total == 3


def test_list_ingestion_jobs_by_universe(monkeypatch):
    """Test listing jobs filtered by universe_id."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id_1 = uuid4()
    universe_id_2 = uuid4()

    # Create 2 jobs for universe_1, 1 for universe_2
    for i in range(2):
        create_params = IngestionJobCreate(
            universe_id=universe_id_1,
            source_id=uuid4(),
            doc_id=uuid4(),
            source_title=f"Test Source 1-{i}",
        )
        mongodb_create_ingestion_job(create_params)

    create_params = IngestionJobCreate(
        universe_id=universe_id_2,
        source_id=uuid4(),
        doc_id=uuid4(),
        source_title="Test Source 2",
    )
    mongodb_create_ingestion_job(create_params)

    result = mongodb_list_ingestion_jobs(IngestionJobFilter(universe_id=universe_id_1))

    assert len(result.jobs) == 2
    assert result.total == 2
    assert all(job.universe_id == universe_id_1 for job in result.jobs)


def test_list_ingestion_jobs_by_status(monkeypatch):
    """Test listing jobs filtered by status."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()

    # Create 2 pending jobs
    for i in range(2):
        create_params = IngestionJobCreate(
            universe_id=universe_id,
            source_id=uuid4(),
            doc_id=uuid4(),
            source_title=f"Test Source {i}",
        )
        created_job = mongodb_create_ingestion_job(create_params)
        # Update first job to running
        if i == 0:
            mongodb_update_ingestion_job(
                created_job.job_id,
                IngestionJobUpdate(status=IngestionStatus.RUNNING),
            )

    result = mongodb_list_ingestion_jobs(IngestionJobFilter(status=IngestionStatus.PENDING))

    assert len(result.jobs) == 1
    assert result.total == 1
    assert all(job.status == IngestionStatus.PENDING for job in result.jobs)


# =============================================================================
# TESTS FOR mongodb_delete_ingestion_job
# =============================================================================


def test_delete_ingestion_job_terminal(monkeypatch):
    """Test deleting a terminal job."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    # Update to terminal state
    mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(status=IngestionStatus.COMPLETED),
    )

    # Verify job exists
    assert mongodb_get_ingestion_job(created_job.job_id) is not None

    # Delete job
    result = mongodb_delete_ingestion_job(created_job.job_id)

    assert result is True
    assert mongodb_get_ingestion_job(created_job.job_id) is None


def test_delete_ingestion_job_not_found(monkeypatch):
    """Test deleting a non-existent job returns False."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    job_id = uuid4()
    result = mongodb_delete_ingestion_job(job_id)

    assert result is False


def test_delete_ingestion_job_non_terminal_raises_error(monkeypatch):
    """Test that deleting a non-terminal job raises ValueError."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    with pytest.raises(ValueError, match="Job .* is in 'pending' state"):
        mongodb_delete_ingestion_job(created_job.job_id)


# =============================================================================
# ADDITIONAL TESTS FOR mongodb_update_ingestion_job
# =============================================================================


def test_update_ingestion_job_current_stage_and_stages_completed(monkeypatch):
    """Test updating current_stage and stages_completed."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    updated_job = mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(
            current_stage=IngestionStage.ANALYZE,
            stages_completed=[IngestionStage.EXTRACT, IngestionStage.EMBED],
        ),
    )

    assert updated_job.current_stage == IngestionStage.ANALYZE
    assert len(updated_job.stages_completed) == 2
    assert IngestionStage.EXTRACT in updated_job.stages_completed
    assert IngestionStage.EMBED in updated_job.stages_completed


def test_update_ingestion_job_batch_counters(monkeypatch):
    """Test updating batch counters for reliability tracking."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    updated_job = mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(
            total_batches=100,
            succeeded_batches=90,
            failed_batches=8,
            retried_batches=2,
        ),
    )

    assert updated_job.total_batches == 100
    assert updated_job.succeeded_batches == 90
    assert updated_job.failed_batches == 8
    assert updated_job.retried_batches == 2


def test_update_ingestion_job_proposal_counters(monkeypatch):
    """Test updating proposal counters for canonization tracking."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    updated_job = mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(
            proposals_generated=25,
            proposals_accepted=20,
            proposals_rejected=3,
        ),
    )

    assert updated_job.proposals_generated == 25
    assert updated_job.proposals_accepted == 20
    assert updated_job.proposals_rejected == 3


def test_update_ingestion_job_append_errors_warnings_activity_log(monkeypatch):
    """Test appending errors, warnings, and activity log."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id = uuid4()
    doc_id = uuid4()

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id,
        doc_id=doc_id,
        source_title="Test Source",
    )

    created_job = mongodb_create_ingestion_job(create_params)

    # First update - append initial logs
    updated_job = mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
            activity_log=["Activity 1"],
        ),
    )

    assert len(updated_job.errors) == 2
    assert "Error 1" in updated_job.errors
    assert "Error 2" in updated_job.errors
    assert len(updated_job.warnings) == 1  # 0 initial + 1 new
    assert "Warning 1" in updated_job.warnings
    assert len(updated_job.activity_log) == 3  # 2 initial + 1 new
    assert "Activity 1" in updated_job.activity_log

    # Second update - append more logs (should preserve previous logs)
    updated_job = mongodb_update_ingestion_job(
        created_job.job_id,
        IngestionJobUpdate(
            errors=["Error 3"],
            warnings=["Warning 2"],
            activity_log=["Activity 2"],
        ),
    )

    assert len(updated_job.errors) == 3
    assert "Error 1" in updated_job.errors
    assert "Error 2" in updated_job.errors
    assert "Error 3" in updated_job.errors
    assert len(updated_job.warnings) == 2
    assert "Warning 1" in updated_job.warnings
    assert "Warning 2" in updated_job.warnings
    assert len(updated_job.activity_log) == 4
    assert "Activity 2" in updated_job.activity_log


# =============================================================================
# ADDITIONAL TESTS FOR mongodb_list_ingestion_jobs
# =============================================================================


def test_list_ingestion_jobs_by_source_id(monkeypatch):
    """Test listing jobs filtered by source_id."""
    fake_mongo = _FakeMongo()
    monkeypatch.setattr(
        "monitor_data.tools.mongodb_tools.ingestion_jobs.get_mongodb_client",
        lambda: fake_mongo,
    )

    universe_id = uuid4()
    source_id_1 = uuid4()
    source_id_2 = uuid4()

    # Create 2 jobs for source_id_1, 1 for source_id_2
    for i in range(2):
        create_params = IngestionJobCreate(
            universe_id=universe_id,
            source_id=source_id_1,
            doc_id=uuid4(),
            source_title=f"Test Source 1-{i}",
        )
        mongodb_create_ingestion_job(create_params)

    create_params = IngestionJobCreate(
        universe_id=universe_id,
        source_id=source_id_2,
        doc_id=uuid4(),
        source_title="Test Source 2",
    )
    mongodb_create_ingestion_job(create_params)

    result = mongodb_list_ingestion_jobs(IngestionJobFilter(source_id=source_id_1))

    assert len(result.jobs) == 2
    assert result.total == 2
    assert all(job.source_id == source_id_1 for job in result.jobs)
