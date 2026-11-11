"""Held batches, the call estimate and the actual count land on the job (I-17, tasks 10 and held items).

The job API response already exposes `failed_sections`, `total_batches` and
`activity_log`; these tests prove a decomposition run fills them in through the
real `mongodb_update_ingestion_job` call.
"""

from __future__ import annotations

import re
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import mongomock
import pytest
from monitor_agents.book_decomposition.extractor import ExtractorResult
from monitor_agents.ingestion import book_stage
from monitor_agents.ingestion.book_stage import (
    create_decomposition_job,
    run_decomposition_job,
)
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookRecordType,
    ClaimCheck,
    ClaimVerdict,
    CoverageAudit,
    ExtractedAtom,
    SkipAudit,
    StackDecision,
    VerificationBatch,
    WindowExtraction,
)
from monitor_data.schemas.ingestion_jobs import IngestionJobCreate
from monitor_data.schemas.knowledge_packs import KnowledgePackType
from monitor_data.tools.mongodb_tools import book_decomposition as storage
from monitor_data.tools.mongodb_tools import ingestion_jobs, knowledge_packs

LIVE_REFUSAL = "The request was rejected because it was considered high risk"


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


def _pdf_with_front_matter() -> bytes:
    """One un-bookmarked page before the sections: the decomposer parents it to the book root."""
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Credits and legal notice.")
    for i in range(2):
        doc.new_page().insert_text((72, 100), f"Rule number {i} says spending Momentum is allowed.")
    doc.set_toc([[1, f"Section {i}", i + 2] for i in range(2)])
    return doc.tobytes()


class _Extractor:
    async def __call__(self, window):
        atoms = [ExtractedAtom(kind=AtomKind.RULE, statement=u.text, cites=[u.label]) for u in window.units]
        return ExtractorResult(WindowExtraction(atoms=atoms), input_tokens=1, output_tokens=1)


class _Review:
    async def verify(self, prompt):
        checks = [
            ClaimCheck(label=b.split("]")[0].strip("["), verdict=ClaimVerdict.SUPPORTED) for b in prompt.split("\n\n")
        ]
        return VerificationBatch(checks=checks)

    async def stack(self, prompt):
        return StackDecision()

    async def audit_skips(self, prompt):
        return SkipAudit()

    async def find_gaps(self, prompt):
        return CoverageAudit()


class _RefusingReview(_Review):
    """The provider refuses every verification request, in its own wording."""

    async def verify(self, prompt):
        raise RuntimeError(LIVE_REFUSAL)


def _source_job():
    return ingestion_jobs.mongodb_create_ingestion_job(
        IngestionJobCreate(universe_id=uuid.uuid4(), source_id=uuid.uuid4(), doc_id=uuid.uuid4(), source_title="Book")
    )


async def _run_job(job, pdf, review, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.delenv("MONITOR_BOOK_COVERAGE", raising=False)
        monkeypatch.delenv("MONITOR_BOOK_GRAPH", raising=False)
    await run_decomposition_job(
        job.job_id,
        pdf,
        doc_id=job.doc_id,
        title="Book",
        pack_type=KnowledgePackType.RULEBOOK,
        make_extractor=lambda _: _Extractor(),
        make_review_model=lambda _, __: review,
    )
    return ingestion_jobs.mongodb_get_ingestion_job(job.job_id)


@pytest.mark.unit
async def test_refused_verification_reaches_the_job_as_held_sections(mongo, monkeypatch):
    job = create_decomposition_job(_source_job(), KnowledgePackType.RULEBOOK)
    final = await _run_job(job, _pdf(), _RefusingReview(), monkeypatch)
    assert final.status.value == "completed"
    # Visible through the existing job API response, with ids and reasons.
    assert final.failed_sections, "a refused batch must not disappear without a record"
    stages = {entry["stage"] for entry in final.failed_sections}
    assert stages == {"verification"}
    assert all(LIVE_REFUSAL in entry["reason"] for entry in final.failed_sections)
    assert all(entry["section_path"] for entry in final.failed_sections)
    assert len(final.failed_sections) == 3  # One held entry per claim of this three-page book.


@pytest.mark.unit
async def test_estimate_and_actual_calls_are_stored_side_by_side(mongo, monkeypatch):
    job = create_decomposition_job(_source_job(), KnowledgePackType.RULEBOOK)
    final = await _run_job(job, _pdf(), _Review(), monkeypatch)
    estimated = next((line for line in final.activity_log if line.startswith("Calls estimated: total=")), None)
    made = next((line for line in final.activity_log if line.startswith("Calls made: total=")), None)
    assert estimated is not None and made is not None
    estimate_total = int(re.search(r"total=(\d+)", estimated).group(1))
    made_total = int(re.search(r"total=(\d+)", made).group(1))
    assert estimate_total > 0 and made_total > 0
    assert final.total_batches == made_total  # The structured count matches the log line.
    assert "extraction=" in estimated and "verification=" in estimated
    assert "extraction=" in made and "verification=" in made


@pytest.mark.unit
async def test_non_content_is_skipped_and_reported_on_the_job(mongo, monkeypatch):
    job = create_decomposition_job(_source_job(), KnowledgePackType.RULEBOOK)
    final = await _run_job(job, _pdf_with_front_matter(), _Review(), monkeypatch)
    # The front-matter sentence never went to the model...
    assert final.decomposition.sentences_total == 2
    # ...and the job says what was skipped.
    skipped_line = next((line for line in final.activity_log if line.startswith("Skipped as non-content: ")), None)
    assert skipped_line is not None and "front_matter=" in skipped_line
    records = storage.mongodb_list_book_records(str(job.doc_id), BookRecordType.REPORT)
    saved = next(record for record in records if record.key == "skipped-non-content")
    assert saved.data["counts"]["front_matter"] >= 1
    assert set(saved.data["reasons"].values()) == {"front_matter"}  # Nothing else was skipped here.


@pytest.mark.unit
async def test_the_job_update_receives_held_sections_and_the_call_counts(mongo, monkeypatch):
    """Cross-component: book_stage passes held ids and counts to the real job update."""
    monkeypatch.delenv("MONITOR_BOOK_COVERAGE", raising=False)
    monkeypatch.delenv("MONITOR_BOOK_GRAPH", raising=False)
    updates = []
    real = book_stage.mongodb_update_ingestion_job

    def spy(job_id, params):
        updates.append(params)
        return real(job_id, params)

    monkeypatch.setattr(book_stage, "mongodb_update_ingestion_job", spy)
    job = create_decomposition_job(_source_job(), KnowledgePackType.RULEBOOK)
    await run_decomposition_job(
        job.job_id,
        _pdf(),
        doc_id=job.doc_id,
        title="Book",
        make_extractor=lambda _: _Extractor(),
        make_review_model=lambda _, __: _RefusingReview(),
    )

    held_update = next(update for update in updates if update.failed_sections is not None)
    assert len(held_update.failed_sections) == 3
    for entry in held_update.failed_sections:
        assert set(entry) == {"section_path", "stage", "reason"}
        assert entry["stage"] == "verification"
    estimate_update = next(
        update
        for update in updates
        if update.activity_log and any(line.startswith("Calls estimated: total=") for line in update.activity_log)
    )
    assert estimate_update.activity_log[0].startswith("Calls estimated: total=")
    final_update = next(update for update in updates if update.total_batches is not None)
    assert final_update.total_batches >= 1
