"""A book runs end to end through real storage code and real schemas, with scripted models (I-17)."""

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import mongomock
import pytest
from monitor_agents.book_decomposition.extractor import ExtractorResult
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_agents.book_decomposition.review import _heading_path  # noqa: F401
from monitor_agents.book_decomposition.service import DecomposeStatus, decompose_book
from monitor_agents.ingestion.book_stage import (
    book_decomposition_enabled,
    create_decomposition_job,
    is_decomposition_job,
    run_decomposition_job,
    stored_pack_type,
)
from monitor_data.schemas.base import IngestionStatus
from monitor_data.schemas.book_graph import (
    AtomKind,
    ClaimCheck,
    ClaimVerdict,
    CoverageAudit,
    ExtractedAtom,
    SkipAudit,
    StackDecision,
    VerificationBatch,
    WindowExtraction,
)
from monitor_data.schemas.ingestion_jobs import IngestionJobCreate, IngestionJobUpdate, IngestionStage
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_data.tools.mongodb_tools import book_decomposition as storage
from monitor_data.tools.mongodb_tools import ingestion_jobs, knowledge_packs


class _Collection:
    """mongomock's bulk_write rejects this pymongo version's ReplaceOne, so apply them one by one."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def bulk_write(self, operations, ordered=True):
        for op in operations:
            self._inner.replace_one(op._filter, op._doc, upsert=op._upsert)


@pytest.fixture
def mongo():
    database = mongomock.MongoClient().db
    client = SimpleNamespace(get_collection=lambda name: _Collection(database[name]))
    with (
        patch.object(storage, "get_mongodb_client", return_value=client),
        patch.object(ingestion_jobs, "get_mongodb_client", return_value=client),
        patch.object(knowledge_packs, "get_mongodb_client", return_value=client),
    ):
        yield database


def _pdf(pages: int = 3) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 100), f"Rule number {i} says spending Momentum is allowed.")
    doc.set_toc([[1, f"Section {i}", i + 1] for i in range(pages)])
    return doc.tobytes()


class _Extractor:
    def __init__(self, stop_after: int | None = None) -> None:
        self.stop_after = stop_after
        self.guard: RunGuard | None = None
        self.units: list[str] = []

    async def __call__(self, window):
        if self.stop_after is not None and len(self.units) >= self.stop_after:
            self.guard.stop("Output token budget reached")  # As a real guard does before raising.
            raise RunStopped("Output token budget reached")
        self.units.extend(u.node_id for u in window.units)
        atoms = [ExtractedAtom(kind=AtomKind.RULE, statement=u.text, cites=[u.label]) for u in window.units]
        return ExtractorResult(WindowExtraction(atoms=atoms), input_tokens=1, output_tokens=1)


class _Review:
    def __init__(self, stop: bool = False) -> None:
        self.stop = stop
        self.verified = 0

    async def verify(self, prompt):
        if self.stop:
            raise RunStopped("quota")
        checks = [ClaimCheck(label=b.split("]")[0].strip("["), verdict=ClaimVerdict.SUPPORTED) for b in prompt.split("\n\n")]
        self.verified += len(checks)
        return VerificationBatch(checks=checks)

    async def stack(self, prompt):
        return StackDecision()

    async def audit_skips(self, prompt):
        return SkipAudit()

    async def find_gaps(self, prompt):
        return CoverageAudit()


def _run(pdf, doc, job, extractor, review, progress=None):
    extractor.guard = RunGuard()
    return decompose_book(
        pdf,
        doc_id=doc,
        job_id=job,
        title="Book",
        pack_type=KnowledgePackType.RULEBOOK,
        extractor=extractor,
        review_model=review,
        guard=extractor.guard,
        run_key="m-1",
        accept_run=lambda key: key.startswith("m-"),
        concurrency=1,
        on_progress=progress,
    )


@pytest.mark.unit
async def test_whole_book_ends_in_a_stored_review_ready_pack(mongo):
    doc, job = uuid.uuid4(), uuid.uuid4()
    seen = []
    result = await _run(_pdf(), doc, job, _Extractor(), _Review(), seen.append)
    assert result.status == DecomposeStatus.COMPLETE
    assert result.progress.sentences_done == result.progress.sentences_total == 3
    assert result.progress.claims_kept == 3
    pack = knowledge_packs.mongodb_get_knowledge_pack(result.pack_id)
    assert pack is not None and pack.ingestion_job_id == job
    rules = pack.game_system_data.rules
    assert len(rules) == 3 and all(r.evidence_refs for r in rules)
    assert seen[-1].claims_kept == 3


@pytest.mark.unit
async def test_a_paused_extraction_resumes_without_repeating_work(mongo):
    doc, job = uuid.uuid4(), uuid.uuid4()
    first = _Extractor(stop_after=1)
    paused = await _run(_pdf(5), doc, job, first, _Review())
    assert paused.status == DecomposeStatus.PAUSED and paused.pack_id is None
    second = _Extractor()
    done = await _run(_pdf(5), doc, job, second, _Review())
    assert done.status == DecomposeStatus.COMPLETE
    assert set(first.units).isdisjoint(second.units)


@pytest.mark.unit
async def test_a_stopped_review_pauses_and_a_rerun_finishes(mongo):
    doc, job = uuid.uuid4(), uuid.uuid4()
    paused = await _run(_pdf(), doc, job, _Extractor(), _Review(stop=True))
    assert paused.status == DecomposeStatus.PAUSED and "quota" in paused.progress.pause_reason
    extractor = _Extractor()
    done = await _run(_pdf(), doc, job, extractor, _Review())
    assert done.status == DecomposeStatus.COMPLETE and extractor.units == []


@pytest.mark.unit
async def test_running_twice_creates_one_pack_and_spends_nothing_more(mongo):
    doc, job = uuid.uuid4(), uuid.uuid4()
    first = await _run(_pdf(), doc, job, _Extractor(), _Review())
    extractor, review = _Extractor(), _Review()
    second = await _run(_pdf(), doc, job, extractor, review)
    assert first.pack_id == second.pack_id
    assert extractor.units == [] and review.verified == 0
    assert mongo["knowledge_packs"].count_documents({}) == 1


def _source_job():
    job = ingestion_jobs.mongodb_create_ingestion_job(
        IngestionJobCreate(universe_id=uuid.uuid4(), source_id=uuid.uuid4(), doc_id=uuid.uuid4(), source_title="Book")
    )
    return job


@pytest.mark.unit
def test_normal_jobs_do_not_list_the_decompose_stage(mongo):
    job = _source_job()
    assert IngestionStage.DECOMPOSE not in job.pipeline_stages
    assert not is_decomposition_job(job)


@pytest.mark.unit
def test_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("MONITOR_BOOK_DECOMPOSITION", raising=False)
    assert not book_decomposition_enabled()
    monkeypatch.setenv("MONITOR_BOOK_DECOMPOSITION", "1")
    assert book_decomposition_enabled()


async def _run_job(job, pdf, extractor, review):
    await run_decomposition_job(
        job.job_id,
        pdf,
        doc_id=job.doc_id,
        title="Book",
        pack_type=KnowledgePackType.RULEBOOK,
        make_extractor=lambda _: extractor,
        make_review_model=lambda _, __: review,
    )
    return ingestion_jobs.mongodb_get_ingestion_job(job.job_id)


@pytest.mark.unit
async def test_job_records_completion_coverage_and_pack(mongo):
    job = create_decomposition_job(_source_job(), KnowledgePackType.RULEBOOK)
    assert is_decomposition_job(job) and job.status == IngestionStatus.RUNNING
    assert job.source_title == "Book (decomposition)"
    assert stored_pack_type(job.doc_id) == KnowledgePackType.RULEBOOK
    final = await _run_job(job, _pdf(), _Extractor(), _Review())
    assert final.status == IngestionStatus.COMPLETED and final.progress == 1.0
    assert final.decomposition.claims_kept == 3 and final.pack_id is not None
    assert IngestionStage.DECOMPOSE in final.stages_completed


@pytest.mark.unit
async def test_job_pauses_with_a_reason_and_resumes_to_completion(mongo):
    job = create_decomposition_job(_source_job())
    paused = await _run_job(job, _pdf(), _Extractor(), _Review(stop=True))
    assert paused.status == IngestionStatus.PAUSED
    assert "quota" in paused.decomposition.pause_reason
    final = await _run_job(job, _pdf(), _Extractor(), _Review())
    assert final.status == IngestionStatus.COMPLETED


@pytest.mark.unit
async def test_cancelled_job_stays_cancelled(mongo):
    job = create_decomposition_job(_source_job())
    ingestion_jobs.mongodb_update_ingestion_job(job.job_id, IngestionJobUpdate(status=IngestionStatus.CANCELLED))

    class _Cancelling(_Extractor):
        async def __call__(self, window):
            ingestion_jobs.mongodb_update_ingestion_job(job.job_id, IngestionJobUpdate(status=IngestionStatus.CANCELLED))
            return await super().__call__(window)

    final = await _run_job(job, _pdf(), _Cancelling(), _Review())
    assert final.status == IngestionStatus.CANCELLED


@pytest.mark.unit
async def test_unexpected_failure_marks_the_job_failed_with_the_reason(mongo):
    job = create_decomposition_job(_source_job())
    final = await _run_job(job, b"this is not a pdf", _Extractor(), _Review())
    assert final.status == IngestionStatus.FAILED
    assert final.errors and final.last_error is not None
