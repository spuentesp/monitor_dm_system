"""Tests for recovery: crashes, outages and bad text can't lose or repeat work (I-17)."""

import asyncio
import random

import pytest
from dspy.utils.exceptions import AdapterParseError
from monitor_agents.book_decomposition import (
    ExtractionLog,
    IngestStatus,
    LogBusy,
    RunGuard,
    WindowOutcome,
    build_windows,
    plan_windows,
    reconcile,
    run_until_settled,
)
from monitor_agents.book_decomposition.extractor import ExtractorResult, WindowExtractionSignature
from monitor_agents.book_decomposition.pacing import StopKind
from monitor_agents.book_decomposition.windows import Window
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
    ExtractedAtom,
    WindowExtraction,
)

PLAN_LIMIT = RuntimeError('{"error":{"message":"Token Plan usage limit reached (2056)"}}')


def _parse_error() -> AdapterParseError:
    return AdapterParseError("ChatAdapter", WindowExtractionSignature, "bad output")


def _book(paragraphs: int = 20, sentences: int = 3) -> list[Window]:
    nodes = [
        BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0),
    ]
    for p in range(paragraphs):
        text = " ".join(f"Sentence {p}x{s} here." for s in range(sentences))
        nodes.append(BookNode(id=f"p{p}", doc_id="d", kind=BookNodeKind.PARAGRAPH, parent_id="root", seq=len(nodes), text=text, page_start=p, page_end=p))
        for s in range(sentences):
            nodes.append(BookNode(id=f"p{p}s{s}", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id=f"p{p}", seq=len(nodes), text=f"Sentence {p}x{s} here.", page_start=p, page_end=p))
    tree = BookTree(doc_id="d", title="T", decomposer_version="2", content_hash="x", nodes=nodes, report=DecompositionReport())
    return build_windows(tree, max_words=30)


def _unit_ids(windows: list[Window]) -> set[str]:
    return {u.node_id for w in windows for u in w.units}


def _answer(window: Window) -> ExtractorResult:
    atoms = [ExtractedAtom(kind=AtomKind.RULE, statement=f"Claim about {u.node_id}.", cites=[u.label]) for u in window.units]
    return ExtractorResult(WindowExtraction(atoms=atoms), 10, 10)


class _Recorder:
    """Records which units were sent to the model, and lets a test inject failures."""

    def __init__(self, fail=None):
        self.sent: list[str] = []
        self.fail = fail

    async def __call__(self, window: Window) -> ExtractorResult:
        self.sent.extend(u.node_id for u in window.units)
        if self.fail:
            error = self.fail(window)
            if error:
                raise error
        return _answer(window)


async def _no_sleep(_: float) -> None:
    return None


def _guard(**kwargs) -> RunGuard:
    async def sleep(_):
        return None

    return RunGuard(sleep=sleep, **kwargs)


async def _run(windows, extractor, log, guard=None, **kwargs):
    return await run_until_settled(windows, extractor, log, guard or _guard(), sleep=_no_sleep, concurrency=2, **kwargs)


@pytest.fixture
def log(tmp_path) -> ExtractionLog:
    return ExtractionLog(tmp_path / "log.jsonl")


@pytest.mark.unit
async def test_clean_run_completes_and_a_second_run_sends_nothing(log):
    windows = _book()
    first = _Recorder()
    result = await _run(windows, first, log)
    assert result.status == IngestStatus.COMPLETE
    assert sorted(first.sent) == sorted(_unit_ids(windows))
    second = _Recorder()
    result = await _run(windows, second, log)
    assert result.status == IngestStatus.COMPLETE
    assert second.sent == []


@pytest.mark.unit
async def test_book_can_be_ingested_in_parts_in_any_order_including_overlaps(log):
    windows = _book()
    recorder = _Recorder()
    middle, end, start = windows[3:6], windows[5:], windows[:4]
    assert (await _run(middle, recorder, log)).status == IngestStatus.COMPLETE
    await _run(end, recorder, log)
    await _run(start, recorder, log)
    assert sorted(recorder.sent) == sorted(_unit_ids(windows))  # Nothing sent twice.
    assert reconcile(_unit_ids(windows), log.read()).is_settled


@pytest.mark.unit
async def test_torn_last_line_from_a_crash_is_ignored_and_that_work_is_redone(log):
    windows = _book()
    await _run(windows[:2], _Recorder(), log)
    text = log.path.read_text()
    last = text.splitlines()[-1]
    log.path.write_text(text[: -len(last) // 2 - 1])  # Cut the last record in half.
    assert len(log.read()) == 1
    recorder = _Recorder()
    result = await _run(windows, recorder, log)
    assert result.status == IngestStatus.COMPLETE
    assert reconcile(_unit_ids(windows), log.read()).is_settled
    # Only the torn window and the never-started ones were sent.
    assert not set(recorder.sent) & {u.node_id for u in windows[0].units}


@pytest.mark.unit
async def test_a_killed_run_resumes_from_the_log_without_repeating_work(log):
    windows = _book()
    sent_before_kill: list[str] = []

    class _DiesAfterThree:
        calls = 0

        async def __call__(self, window: Window) -> ExtractorResult:
            self.calls += 1
            if self.calls > 3:
                raise asyncio.CancelledError  # Same effect as the process being killed.
            sent_before_kill.extend(u.node_id for u in window.units)
            return _answer(window)

    with pytest.raises(asyncio.CancelledError):
        await run_until_settled(windows, _DiesAfterThree(), log, _guard(), sleep=_no_sleep, concurrency=1)
    recorder = _Recorder()
    result = await _run(windows, recorder, log)
    assert result.status == IngestStatus.COMPLETE
    assert not set(sent_before_kill) & set(recorder.sent)
    assert sorted(sent_before_kill + recorder.sent) == sorted(_unit_ids(windows))


@pytest.mark.unit
async def test_quota_pauses_the_run_and_rerunning_finishes_only_the_rest(log):
    windows = _book()
    calls = {"n": 0}

    def fail(_):
        calls["n"] += 1
        return PLAN_LIMIT if calls["n"] > 3 else None

    first = _Recorder(fail)
    result = await _run(windows, first, log)
    assert result.status == IngestStatus.PAUSED
    assert "usage limit" in result.pause_reason
    done = result.states.done
    assert done
    second = _Recorder()
    result = await _run(windows, second, log)
    assert result.status == IngestStatus.COMPLETE
    assert not done & set(second.sent)


@pytest.mark.unit
async def test_waiting_for_quota_recovers_by_itself_in_one_run(log):
    windows = _book()
    calls = {"n": 0}
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)

    def fail(_):
        calls["n"] += 1
        return PLAN_LIMIT if calls["n"] in (2, 3) else None

    result = await run_until_settled(windows, _Recorder(fail), log, _guard(), sleep=sleep, concurrency=1, wait_for_quota_seconds=7200)
    assert result.status == IngestStatus.COMPLETE
    assert slept[:2] == [300.0, 600.0]


@pytest.mark.unit
async def test_quota_wait_gives_up_after_the_allowed_time(log):
    windows = _book()
    result = await run_until_settled(windows, _Recorder(lambda _: PLAN_LIMIT), log, _guard(), sleep=_no_sleep, concurrency=1, wait_for_quota_seconds=600)
    assert result.status == IngestStatus.PAUSED


@pytest.mark.unit
async def test_budget_stop_never_auto_resumes_even_when_waiting_for_quota_is_on(log):
    windows = _book()
    recorder = _Recorder()
    guard = _guard(max_output_tokens=10)
    result = await run_until_settled(windows, recorder, log, guard, sleep=_no_sleep, concurrency=1, wait_for_quota_seconds=7200)
    assert result.status == IngestStatus.PAUSED
    assert guard.stop_kind == StopKind.BUDGET
    assert "budget" in result.pause_reason


@pytest.mark.unit
async def test_sentence_that_never_parses_is_quarantined_and_the_rest_finish(log):
    windows = _book()
    poison = windows[2].units[1].node_id

    def fail(window):
        return _parse_error() if any(u.node_id == poison for u in window.units) else None

    result = await _run(windows, _Recorder(fail), log)
    assert result.status == IngestStatus.COMPLETE_WITH_QUARANTINE
    assert result.states.quarantined == {poison}
    assert len(result.states.done) == len(_unit_ids(windows)) - 1


@pytest.mark.unit
async def test_quarantined_sentence_is_left_alone_until_asked_then_retried_once(log):
    windows = _book()
    poison = windows[2].units[1].node_id

    def fail(window):
        return _parse_error() if any(u.node_id == poison for u in window.units) else None

    await _run(windows, _Recorder(fail), log)
    untouched = _Recorder()
    assert (await _run(windows, untouched, log)).status == IngestStatus.COMPLETE_WITH_QUARANTINE
    assert untouched.sent == []
    healed = _Recorder()
    result = await _run(windows, healed, log, retry_quarantined=True)
    assert healed.sent == [poison]
    assert result.status == IngestStatus.COMPLETE


@pytest.mark.unit
async def test_a_provider_outage_never_quarantines_anything(log):
    windows = _book(paragraphs=4)
    result = await _run(windows, _Recorder(lambda _: RuntimeError("connection reset")), log)
    assert result.status == IngestStatus.PAUSED
    assert result.states.quarantined == frozenset()
    assert len(result.states.pending) == len(_unit_ids(windows))
    assert (await _run(windows, _Recorder(), log)).status == IngestStatus.COMPLETE


@pytest.mark.unit
async def test_partially_finished_window_keeps_its_finished_sentences(log):
    windows = _book(paragraphs=1, sentences=6)
    unit_labels = [u.label for u in windows[0].units]
    calls = {"n": 0}

    class _HalfThenLimit:
        async def __call__(self, window: Window) -> ExtractorResult:
            calls["n"] += 1
            if calls["n"] == 1:
                atoms = [ExtractedAtom(kind=AtomKind.RULE, statement="Half.", cites=unit_labels[:3])]
                return ExtractorResult(WindowExtraction(atoms=atoms), 1, 1)
            raise PLAN_LIMIT

    result = await _run(windows, _HalfThenLimit(), log)
    assert result.status == IngestStatus.PAUSED
    assert len(result.states.done) == 3
    recorder = _Recorder()
    await _run(windows, recorder, log)
    assert len(recorder.sent) == 3


@pytest.mark.unit
@pytest.mark.parametrize("seed", range(5))
async def test_random_failures_of_every_kind_still_end_with_every_sentence_done_once(log, seed):
    """Chaos test: whatever fails, and in whatever order, the book ends up fully accounted for."""
    rng = random.Random(seed)
    windows = _book(paragraphs=30)
    errors = [RuntimeError("connection reset"), RuntimeError("429 Too Many Requests"), _parse_error(), PLAN_LIMIT]

    def fail(_):
        return rng.choice(errors) if rng.random() < 0.4 else None

    for _ in range(15):
        result = await _run(windows, _Recorder(fail), log, retry_quarantined=True)
        if result.status == IngestStatus.COMPLETE:
            break
    assert result.status == IngestStatus.COMPLETE
    per_unit: dict[str, int] = {}
    for outcome in log.read():
        for node_id in set(outcome.cited) | set(outcome.skipped):
            per_unit[node_id] = per_unit.get(node_id, 0) + 1
    assert set(per_unit) == _unit_ids(windows)
    assert max(per_unit.values()) == 1


@pytest.mark.unit
def test_prompt_filter_decides_which_older_work_counts(tmp_path):
    log = ExtractionLog(tmp_path / "log.jsonl")
    log.append(WindowOutcome(window_id="a", run_key="m-old", cited=["u1"]))
    assert reconcile({"u1"}, log.read()).is_settled
    current = [o for o in log.read() if o.run_key == "m-new"]
    assert reconcile({"u1"}, current).pending == {"u1"}


@pytest.mark.unit
def test_plan_keeps_only_pending_units_with_their_context_and_labels():
    windows = _book(paragraphs=2)
    pending = {windows[0].units[1].node_id}
    [planned] = plan_windows(windows, pending)
    assert [u.node_id for u in planned.units] == list(pending)
    assert planned.units[0].label == windows[0].units[1].label
    assert planned.heading_path == windows[0].heading_path
    assert planned.id != windows[0].id


@pytest.mark.unit
def test_second_process_cannot_work_on_the_same_book(tmp_path):
    log = ExtractionLog(tmp_path / "log.jsonl")
    with log.exclusive():
        # flock is per open file, so a separate open here behaves like a separate process.
        with pytest.raises(LogBusy):
            with log.exclusive():
                pass
    with log.exclusive():
        pass  # Released afterward, as it would be after a crash.
