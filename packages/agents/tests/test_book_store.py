"""The MongoDB backends must behave like the file logs: resume, reuse, and refuse a second run."""

import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import mongomock
import pytest
from monitor_agents.book_decomposition.extractor import ExtractorResult
from monitor_agents.book_decomposition.ledger import LogBusy
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_agents.book_decomposition.pipeline import WindowOutcome
from monitor_agents.book_decomposition.review import CoverageLog, ReviewResult
from monitor_agents.book_decomposition.runner import IngestStatus, run_until_settled
from monitor_agents.book_decomposition.store import (
    MongoCheckLog,
    MongoCoverageLog,
    MongoExtractionLog,
    load_tree,
    save_review,
    save_tree,
)
from monitor_agents.book_decomposition.windows import build_windows
from monitor_data.schemas.book_graph import (
    BookNode,
    BookNodeKind,
    BookRecordType,
    BookTree,
    ClaimCheck,
    ClaimStatus,
    AtomKind,
    ClaimVerdict,
    DecompositionReport,
    LedgerEntry,
    ParagraphGap,
    ReviewedClaim,
    UnitSkip,
    SkipReason,
    WindowExtraction,
)
from monitor_data.tools.mongodb_tools import book_decomposition as tools


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
    with patch.object(tools, "get_mongodb_client", return_value=client):
        yield database


def _tree(count: int = 12) -> BookTree:
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    for i in range(count):
        text = "Word " * 300
        nodes.append(BookNode(id=f"p{i}", doc_id="d", kind=BookNodeKind.PARAGRAPH, parent_id="root", seq=len(nodes), text=text, page_start=i, page_end=i))
        nodes.append(BookNode(id=f"s{i}", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id=f"p{i}", seq=len(nodes), text=text, page_start=i, page_end=i))
    return BookTree(doc_id="d", title="T", decomposer_version="4", content_hash="x", nodes=nodes, report=DecompositionReport())


class _Extractor:
    """Skips every unit, and can stop the run after a number of calls."""

    def __init__(self, stop_after: int | None = None) -> None:
        self.stop_after = stop_after
        self.units_sent: list[str] = []

    async def __call__(self, window):
        if self.stop_after is not None and len(self.units_sent) >= self.stop_after:
            raise RunStopped("stopped")
        self.units_sent.extend(unit.node_id for unit in window.units)
        return ExtractorResult(
            WindowExtraction(skips=[UnitSkip(label=u.label, reason=SkipReason.FLAVOR) for u in window.units]),
            input_tokens=1,
            output_tokens=1,
        )


@pytest.mark.unit
def test_outcomes_round_trip(mongo):
    log = MongoExtractionLog("d")
    log.append(WindowOutcome(window_id="w", skipped={"s1": "flavor"}))
    assert log.read()[0].skipped == {"s1": "flavor"}


@pytest.mark.unit
def test_retried_window_keeps_both_outcomes(mongo):
    log = MongoExtractionLog("d")
    log.append(WindowOutcome(window_id="w", uncovered=["s1"]))
    log.append(WindowOutcome(window_id="w", skipped={"s1": "flavor"}))
    assert len(log.read()) == 2


@pytest.mark.unit
async def test_interrupted_run_resumes_without_resending_finished_units(mongo):
    windows = build_windows(_tree(), max_words=600)
    assert len(windows) > 2
    log = MongoExtractionLog("d")
    first = _Extractor(stop_after=2)
    result = await run_until_settled(windows, first, log, RunGuard(), concurrency=1, run_key="r")
    assert result.status == IngestStatus.PAUSED or result.states.pending

    second = _Extractor()
    final = await run_until_settled(windows, second, MongoExtractionLog("d"), RunGuard(), concurrency=1, run_key="r")
    assert final.status == IngestStatus.COMPLETE
    assert set(first.units_sent).isdisjoint(second.units_sent)
    assert len(set(first.units_sent) | set(second.units_sent)) == 12


@pytest.mark.unit
async def test_finished_book_sends_nothing_on_a_rerun(mongo):
    windows = build_windows(_tree(), max_words=600)
    await run_until_settled(windows, _Extractor(), MongoExtractionLog("d"), RunGuard(), run_key="r")
    again = _Extractor()
    result = await run_until_settled(windows, again, MongoExtractionLog("d"), RunGuard(), run_key="r")
    assert result.status == IngestStatus.COMPLETE and again.units_sent == []


@pytest.mark.unit
def test_two_workers_cannot_run_one_document(mongo):
    with MongoExtractionLog("d").exclusive():
        with pytest.raises(LogBusy):
            with MongoExtractionLog("d").exclusive():
                pass
    with MongoExtractionLog("d").exclusive():
        pass


@pytest.mark.unit
def test_lease_from_a_dead_worker_expires(mongo):
    now = [datetime(2026, 11, 4, tzinfo=UTC)]
    crashed = MongoExtractionLog("d", lease_seconds=60, clock=lambda: now[0])
    tools.mongodb_acquire_book_lease("d", crashed._owner, 60, now=now[0])  # Held, then the process dies.
    other = MongoExtractionLog("d", lease_seconds=60, clock=lambda: now[0])
    with pytest.raises(LogBusy):
        with other.exclusive():
            pass
    now[0] += timedelta(seconds=61)
    with other.exclusive():
        pass


@pytest.mark.unit
def test_lease_keeps_renewing_during_long_work(mongo):
    now = [datetime(2026, 11, 4, tzinfo=UTC)]
    worker = MongoExtractionLog("d", lease_seconds=0.15, clock=lambda: now[0])
    renewed = threading.Event()
    original = tools.mongodb_acquire_book_lease
    calls = []

    def counting(*args, **kwargs):
        calls.append(args)
        if len(calls) >= 2:
            renewed.set()
        return original(*args, **kwargs)

    with patch("monitor_agents.book_decomposition.store.mongodb_acquire_book_lease", counting):
        with worker.exclusive():
            assert renewed.wait(timeout=3)


@pytest.mark.unit
def test_checks_are_scoped_to_their_prompt_fingerprint(mongo):
    check = ClaimCheck(label="C1", verdict=ClaimVerdict.SUPPORTED)
    MongoCheckLog("d", "old").append({"claim": check})
    assert MongoCheckLog("d", "new").read() == {}
    assert MongoCheckLog("d", "old").read()["claim"].verdict == ClaimVerdict.SUPPORTED


@pytest.mark.unit
def test_coverage_keeps_paragraphs_with_no_gaps(mongo):
    gap = ParagraphGap(paragraph_id="p", page=0, missing="M", quote="q")
    MongoCoverageLog("d", "f").append({"a": [gap], "b": []})
    saved = MongoCoverageLog("d", "f").read()
    assert saved["a"][0].missing == "M" and saved["b"] == []
    assert isinstance(CoverageLog.key(_tree().nodes[1], ["x"]), str)


@pytest.mark.unit
def test_tree_round_trips_in_reading_order(mongo):
    tree = _tree(3)
    save_tree(tree)
    loaded = load_tree("d")
    assert loaded is not None and [n.id for n in loaded.nodes] == [n.id for n in tree.nodes]
    assert loaded.content_hash == "x"


@pytest.mark.unit
def test_partially_saved_tree_counts_as_missing(mongo):
    tools.mongodb_upsert_book_records("d", BookRecordType.NODE, [])
    assert load_tree("d") is None


@pytest.mark.unit
def test_review_results_are_stored(mongo):
    claim = ReviewedClaim(id="c", kind=AtomKind.RULE, statement="S", source_node_ids=["s"], pages=[0], merged_from=[])
    entry = LedgerEntry(claim_id="c", kind=AtomKind.RULE, original_statement="S", status=ClaimStatus.ACCEPTED)
    save_review("d", ReviewResult(claims=[claim], ledger=[entry]))
    assert tools.mongodb_list_book_records("d", BookRecordType.CLAIM)[0].key == "c"
    assert tools.mongodb_list_book_records("d", BookRecordType.LEDGER)[0].data["status"] == "accepted"
    assert tools.mongodb_list_book_records("d", BookRecordType.REPORT)[0].key == "review"
