"""A book runs end to end through real storage code and real schemas, with scripted models (I-17)."""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import fitz
import mongomock
import pytest
from monitor_agents.book_decomposition import held_claims
from monitor_agents.book_decomposition.extractor import ExtractorResult
from monitor_agents.book_decomposition.knowledge_graph import GraphBatch, MergeAnswer
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_agents.book_decomposition.service import DecomposeStatus, decompose_book
from monitor_agents.ingestion.book_stage import (
    book_decomposition_enabled,
    create_decomposition_job,
    decide_held_claim_for_job,
    held_claims_for_job,
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
    BookRecordType,
    ExtractedAtom,
    LedgerEntry,
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
        checks = [
            ClaimCheck(label=b.split("]")[0].strip("["), verdict=ClaimVerdict.SUPPORTED) for b in prompt.split("\n\n")
        ]
        self.verified += len(checks)
        return VerificationBatch(checks=checks)

    async def stack(self, prompt):
        return StackDecision()

    async def audit_skips(self, prompt):
        return SkipAudit()

    async def find_gaps(self, prompt):
        return CoverageAudit()


class _DoubtingReview(_Review):
    """Calls the first claim unsupported. It matches its source, so review sends it to a person."""

    async def verify(self, prompt):
        batch = await super().verify(prompt)
        batch.checks[0].verdict = ClaimVerdict.UNSUPPORTED
        return batch


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
async def test_a_paused_extraction_resumes_without_repeating_work(mongo, monkeypatch):
    # One window per section, so pausing mid-book is possible at all (task 5 packs
    # these five short sections into a single window at the default budget).
    monkeypatch.setenv("MONITOR_BOOK_WINDOW_WORDS", "5")
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
            ingestion_jobs.mongodb_update_ingestion_job(
                job.job_id, IngestionJobUpdate(status=IngestionStatus.CANCELLED)
            )
            return await super().__call__(window)

    final = await _run_job(job, _pdf(), _Cancelling(), _Review())
    assert final.status == IngestionStatus.CANCELLED


@pytest.mark.unit
async def test_unexpected_failure_marks_the_job_failed_with_the_reason(mongo):
    job = create_decomposition_job(_source_job())
    final = await _run_job(job, b"this is not a pdf", _Extractor(), _Review())
    assert final.status == IngestionStatus.FAILED
    assert final.errors and final.last_error is not None


class _Graph:
    async def propose(self, claims):
        return GraphBatch.model_validate(
            {
                "claim_domains": {"C1": "rules"},
                "relationships": [{"subject": "Momentum", "predicate": "used_in", "object": "Rule", "cites": ["C1"]}],
            }
        )

    async def find_duplicates(self, names):
        return MergeAnswer()


@pytest.mark.unit
async def test_domain_trees_and_graphs_are_stored_when_asked_for(mongo):
    doc, job = uuid.uuid4(), uuid.uuid4()
    extractor = _Extractor()
    extractor.guard = RunGuard()
    await decompose_book(
        _pdf(),
        doc_id=doc,
        job_id=job,
        title="Book",
        pack_type=KnowledgePackType.RULEBOOK,
        extractor=extractor,
        review_model=_Review(),
        guard=extractor.guard,
        run_key="m-1",
        accept_run=lambda key: key.startswith("m-"),
        concurrency=1,
        graph_model=_Graph(),
    )
    keys = {r.key for r in storage.mongodb_list_book_records(str(doc), BookRecordType.REPORT)}
    assert {"tree-rules", "tree-lore", "graph-rules", "graph-lore", "claim-domains", "review"} <= keys


@pytest.mark.unit
async def test_domain_trees_are_stored_without_a_graph_model(mongo):
    doc, job = uuid.uuid4(), uuid.uuid4()
    await _run(_pdf(), doc, job, _Extractor(), _Review())
    records = {r.key: r for r in storage.mongodb_list_book_records(str(doc), BookRecordType.REPORT)}
    assert "tree-rules" in records and "graph-rules" not in records
    assert records["tree-rules"].data["children"]
    assert "graph-lore" not in records


@pytest.mark.unit
async def test_book_structure_goes_through_canonkeeper_only_when_chosen(mongo, monkeypatch):
    record = AsyncMock(return_value=3)
    with patch("monitor_agents.canonkeeper.agent.CanonKeeper.record_book_structure", record):
        job = create_decomposition_job(_source_job())
        await _run_job(job, _pdf(), _Extractor(), _Review())
        record.assert_not_awaited()
        monkeypatch.setenv("MONITOR_BOOK_NEO4J", "1")
        await run_decomposition_job(
            job.job_id,
            _pdf(),
            doc_id=job.doc_id,
            title="Book",
            source_id=job.source_id,
            make_extractor=lambda _: _Extractor(),
            make_review_model=lambda _, __: _Review(),
        )
    assert record.await_args.args[1] == job.source_id


@pytest.mark.unit
async def test_failed_structure_write_warns_and_the_book_still_finishes(mongo, monkeypatch):
    monkeypatch.setenv("MONITOR_BOOK_NEO4J", "1")
    record = AsyncMock(side_effect=RuntimeError("neo4j down"))
    job = create_decomposition_job(_source_job())
    with patch("monitor_agents.canonkeeper.agent.CanonKeeper.record_book_structure", record):
        await run_decomposition_job(
            job.job_id,
            _pdf(),
            doc_id=job.doc_id,
            title="Book",
            source_id=job.source_id,
            make_extractor=lambda _: _Extractor(),
            make_review_model=lambda _, __: _Review(),
        )
    final = ingestion_jobs.mongodb_get_ingestion_job(job.job_id)
    assert final.status == IngestionStatus.COMPLETED
    assert any("neo4j down" in warning for warning in final.warnings)


def _raw(mongo, job):
    return mongo["ingestion_jobs"].find_one({"job_id": str(job.job_id)})


@pytest.mark.unit
def test_any_job_update_counts_as_progress(mongo):
    job = _source_job()
    before = _raw(mongo, job).get("stage_last_progress_at")
    ingestion_jobs.mongodb_update_ingestion_job(job.job_id, IngestionJobUpdate(progress=0.5))
    after = _raw(mongo, job)["stage_last_progress_at"]
    assert after is not None and after != before


@pytest.mark.unit
async def test_heartbeat_keeps_a_quiet_stretch_alive_and_stops_afterward(mongo):
    job = create_decomposition_job(_source_job())
    stamps = []

    class _SlowReview(_Review):
        async def verify(self, prompt):
            first = _raw(mongo, job)["stage_last_progress_at"]
            await asyncio.sleep(0.15)  # A long review with no progress updates of its own.
            stamps.append((first, _raw(mongo, job)["stage_last_progress_at"]))
            return await super().verify(prompt)

    await run_decomposition_job(
        job.job_id,
        _pdf(1),
        doc_id=job.doc_id,
        title="Book",
        heartbeat_seconds=0.03,
        make_extractor=lambda _: _Extractor(),
        make_review_model=lambda _, __: _SlowReview(),
    )
    assert stamps and stamps[0][1] > stamps[0][0]
    finished = _raw(mongo, job)["stage_last_progress_at"]
    await asyncio.sleep(0.1)
    assert _raw(mongo, job)["stage_last_progress_at"] == finished


@pytest.mark.unit
async def test_claims_sent_to_a_person_are_counted_on_the_job(mongo):
    result = await _run(_pdf(), uuid.uuid4(), uuid.uuid4(), _Extractor(), _DoubtingReview())
    assert result.progress.claims_for_review == 1
    assert result.progress.claims_kept == 2


# --- Held claims: a person accepts or rejects what review couldn't settle (I-17) ---


async def _held(mongo):
    doc = uuid.uuid4()
    result = await _run(_pdf(), doc, uuid.uuid4(), _Extractor(), _DoubtingReview())
    (claim,) = held_claims.list_held_claims(str(doc))
    return doc, result, claim


def _rules(pack_id):
    return [rule.description for rule in knowledge_packs.mongodb_get_knowledge_pack(pack_id).game_system_data.rules]


@pytest.mark.unit
async def test_a_held_claim_lists_its_source_and_why_it_waits(mongo):
    _, _, claim = await _held(mongo)
    assert claim.kind == "rule" and claim.decision is None
    assert claim.reason.startswith("unsupported")
    assert claim.sources and claim.sources[0].text in claim.statement
    assert claim.page == claim.sources[0].page


@pytest.mark.unit
async def test_accepting_adds_the_claim_to_the_pack_once(mongo):
    doc, result, claim = await _held(mongo)
    assert claim.statement not in _rules(result.pack_id)
    held_claims.decide_held_claim(str(doc), claim.claim_id, accept=True)
    held_claims.decide_held_claim(str(doc), claim.claim_id, accept=True)  # A second click.
    rules = _rules(result.pack_id)
    assert rules.count(claim.statement) == 1 and len(rules) == 3
    assert held_claims.open_review_count(str(doc)) == 0


@pytest.mark.unit
async def test_accepting_with_new_wording_puts_that_wording_in_the_pack(mongo):
    doc, result, claim = await _held(mongo)
    held_claims.decide_held_claim(str(doc), claim.claim_id, accept=True, statement="  Spending Momentum is allowed. ")
    assert "Spending Momentum is allowed." in _rules(result.pack_id)
    assert held_claims.list_held_claims(str(doc))[0].decision.statement == "Spending Momentum is allowed."


@pytest.mark.unit
async def test_rejecting_keeps_the_claim_out_and_cannot_be_flipped(mongo):
    doc, result, claim = await _held(mongo)
    held_claims.decide_held_claim(str(doc), claim.claim_id, accept=False)
    assert claim.statement not in _rules(result.pack_id)
    assert held_claims.open_review_count(str(doc)) == 0
    with pytest.raises(held_claims.HeldClaimConflict, match="other way"):
        held_claims.decide_held_claim(str(doc), claim.claim_id, accept=True)


@pytest.mark.unit
async def test_a_decision_survives_a_rerun_and_a_rebuilt_pack(mongo):
    doc, result, claim = await _held(mongo)
    held_claims.decide_held_claim(str(doc), claim.claim_id, accept=True)
    again = await _run(_pdf(), doc, uuid.uuid4(), _Extractor(), _DoubtingReview())
    assert again.progress.claims_for_review == 0
    assert _rules(result.pack_id).count(claim.statement) == 1
    mongo["knowledge_packs"].delete_many({})
    rebuilt = await _run(_pdf(), doc, uuid.uuid4(), _Extractor(), _DoubtingReview())
    assert claim.statement in _rules(rebuilt.pack_id)


@pytest.mark.unit
async def test_accepting_into_a_pack_without_rules_creates_its_rules(mongo):
    doc, result, claim = await _held(mongo)
    mongo["knowledge_packs"].update_one({"pack_id": str(result.pack_id)}, {"$set": {"game_system_data": None}})
    held_claims.decide_held_claim(str(doc), claim.claim_id, accept=True)
    assert _rules(result.pack_id) == [claim.statement]


@pytest.mark.unit
async def test_an_applied_pack_refuses_new_claims_and_records_nothing(mongo):
    doc, result, claim = await _held(mongo)
    mongo["knowledge_packs"].update_one({"pack_id": str(result.pack_id)}, {"$set": {"status": "applied"}})
    with pytest.raises(held_claims.HeldClaimConflict, match="applied"):
        held_claims.decide_held_claim(str(doc), claim.claim_id, accept=True)
    assert held_claims.open_review_count(str(doc)) == 1


@pytest.mark.unit
async def test_no_decision_while_the_book_is_being_decomposed(mongo):
    doc, _, claim = await _held(mongo)
    assert storage.mongodb_acquire_book_lease(str(doc), "a-run", 300)
    with pytest.raises(held_claims.HeldClaimConflict, match="being decomposed"):
        held_claims.decide_held_claim(str(doc), claim.claim_id, accept=False)


@pytest.mark.unit
async def test_only_held_claims_can_be_decided(mongo):
    doc, _, _ = await _held(mongo)
    kept = next(r.key for r in storage.mongodb_list_book_records(str(doc), BookRecordType.CLAIM))
    with pytest.raises(held_claims.HeldClaimNotFound):
        held_claims.decide_held_claim(str(doc), kept, accept=True)


@pytest.mark.unit
def test_an_older_ledger_entry_falls_back_to_its_original_wording():
    entry = LedgerEntry.model_validate(
        {"claim_id": "c1", "kind": "rule", "original_statement": "Roll two dice.", "status": "needs_human"}
    )
    assert entry.statement is None and entry.conflicts_with == []
    assert held_claims._statement(entry) == "Roll two dice."


@pytest.mark.unit
async def test_a_decision_on_the_job_lowers_its_count(mongo):
    job = create_decomposition_job(_source_job())
    with patch("monitor_agents.canonkeeper.agent.CanonKeeper.record_book_structure", AsyncMock()):
        await run_decomposition_job(
            job.job_id,
            _pdf(),
            doc_id=job.doc_id,
            title="Book",
            make_extractor=lambda _: _Extractor(),
            make_review_model=lambda _, __: _DoubtingReview(),
        )
    assert ingestion_jobs.mongodb_get_ingestion_job(job.job_id).decomposition.claims_for_review == 1
    (claim,) = held_claims_for_job(job.job_id)
    assert decide_held_claim_for_job(job.job_id, claim.claim_id, accept=False) == 0
    assert ingestion_jobs.mongodb_get_ingestion_job(job.job_id).decomposition.claims_for_review == 0
    with pytest.raises(held_claims.HeldClaimNotFound):
        held_claims_for_job(_source_job().job_id)


def _tree_claim_ids(mongo_doc):
    def walk(node):
        yield from node["claim_ids"]
        for child in node["children"]:
            yield from walk(child)

    records = storage.mongodb_list_book_records(mongo_doc, BookRecordType.REPORT)
    return {cid for r in records if r.key == "tree-rules" for cid in walk(r.data)}


@pytest.mark.unit
async def test_an_accepted_claim_joins_the_rules_tree_and_stays_after_a_rerun(mongo):
    doc, _, claim = await _held(mongo)
    assert claim.claim_id not in _tree_claim_ids(str(doc))
    before = len(_tree_claim_ids(str(doc)))
    held_claims.decide_held_claim(str(doc), claim.claim_id, accept=True)
    after = _tree_claim_ids(str(doc))
    assert claim.claim_id in after and len(after) == before + 1
    await _run(_pdf(), doc, uuid.uuid4(), _Extractor(), _DoubtingReview())
    assert _tree_claim_ids(str(doc)) == after


@pytest.mark.unit
async def test_a_rejected_claim_stays_out_of_the_tree(mongo):
    doc, _, claim = await _held(mongo)
    held_claims.decide_held_claim(str(doc), claim.claim_id, accept=False)
    assert claim.claim_id not in _tree_claim_ids(str(doc))
