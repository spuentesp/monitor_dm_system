"""Tests for run pacing and stopping (book decomposition prototype, I-17)."""

import pytest
from dspy.utils.exceptions import AdapterParseError
from monitor_agents.book_decomposition import (
    RunGuard,
    RunStopped,
    build_coverage_report,
    extract_windows,
)
from monitor_agents.book_decomposition.extractor import (
    ExtractorResult,
    TruncatedOutput,
    WindowExtractionSignature,
)
from monitor_agents.book_decomposition.pacing import ends_the_run
from monitor_agents.book_decomposition.review import DspyReviewModel, review_claims
from monitor_agents.book_decomposition.windows import Unit, Window
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
    ExtractedAtom,
    WindowExtraction,
)

PLAN_LIMIT = RuntimeError(
    'AnthropicException - {"error":{"type":"rate_limit_error",'
    '"message":"Token Plan usage limit reached: Upgrade your Token Plan (2056)"}}'
)
NO_BALANCE = RuntimeError('{"error":{"type":"insufficient_balance_error","message":"insufficient balance (1008)"}}')
TEMPORARY_LIMIT = RuntimeError("429 Too Many Requests")


class _Clock:
    """A fake clock, so timing tests don't wait in real time."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(round(seconds, 3))
        self.now += seconds


def _guard(clock: _Clock | None = None, **kwargs) -> RunGuard:
    clock = clock or _Clock()
    return RunGuard(clock=clock, sleep=clock.sleep, **kwargs)


def _windows(count: int) -> list[Window]:
    return [
        Window(id=f"w{i}", division_id="d", heading_path=("C",), context="", units=(Unit(f"n{i}", "S1", BookNodeKind.SENTENCE, "Text.", 0),))
        for i in range(count)
    ]


def _complete(window: Window, output_tokens: int = 100) -> ExtractorResult:
    atoms = [ExtractedAtom(kind=AtomKind.RULE, statement="A claim.", cites=[u.label for u in window.units])]
    return ExtractorResult(WindowExtraction(atoms=atoms), input_tokens=10, output_tokens=output_tokens)


class _Extractor:
    """Fails with a scripted error from call `fail_from` onward."""

    def __init__(self, fail_from: int | None = None, error: Exception = PLAN_LIMIT, output_tokens: int = 100):
        self.calls = 0
        self.fail_from = fail_from
        self.error = error
        self.output_tokens = output_tokens

    async def __call__(self, window: Window) -> ExtractorResult:
        self.calls += 1
        if self.fail_from is not None and self.calls > self.fail_from:
            raise self.error
        return _complete(window, self.output_tokens)


@pytest.mark.unit
@pytest.mark.parametrize("error", [PLAN_LIMIT, NO_BALANCE, RuntimeError("401 invalid api key")])
def test_plan_and_key_errors_end_the_run(error):
    assert ends_the_run(error)


@pytest.mark.unit
@pytest.mark.parametrize(
    "message",
    [
        "usage limit exceeded (2056)",  # The wording in MiniMax's error table.
        "something new about your plan (2056)",
        "usage limit reached and credit auto consumption is off (2067)",
        '{"base_resp":{"status_code":2056,"status_msg":"x"}}',
    ],
)
def test_plan_limit_is_recognized_by_code_whatever_the_wording(message):
    assert ends_the_run(RuntimeError(message))


@pytest.mark.unit
@pytest.mark.parametrize(
    "error",
    [
        TEMPORARY_LIMIT,
        RuntimeError("connection reset"),
        ValueError("oops"),
        RuntimeError("timed out after 2056 ms"),
        RuntimeError('{"request_id":"0738a61df2056b556c"}'),
        RuntimeError("M Plan rate limit reached (2062)"),
    ],
)
def test_temporary_errors_do_not_end_the_run(error):
    assert not ends_the_run(error)


@pytest.mark.unit
def test_truncated_output_says_nothing_about_the_provider():
    error = TruncatedOutput("usage limit reached")
    assert not ends_the_run(error)
    guard = _guard()
    guard.on_error(error)
    assert not guard.stopped
    assert guard.rate_limit_pauses == 0


def _failed_call(error: Exception, output_tokens: int) -> Exception:
    error.book_call_usage = (10, output_tokens)
    return error


@pytest.mark.unit
async def test_failed_calls_count_against_the_budget():
    """Cut-off answers are the most expensive calls, so the budget must see them."""
    guard = _guard(max_output_tokens=20_000)

    async def fail():
        raise _failed_call(TruncatedOutput("cut off"), 16_384)

    with pytest.raises(TruncatedOutput):
        await guard.call(fail)
    assert (guard.input_tokens, guard.output_tokens) == (10, 16_384)
    assert not guard.stopped
    with pytest.raises(RunStopped, match="budget"):
        await guard.call(fail)
    assert guard.output_tokens == 32_768


@pytest.mark.unit
async def test_a_failed_call_does_not_reset_rate_limit_backoff():
    clock = _Clock()
    guard = _guard(clock)

    async def fail():
        raise _failed_call(TruncatedOutput("cut off"), 100)

    guard.on_error(TEMPORARY_LIMIT)
    await guard.acquire()
    with pytest.raises(TruncatedOutput):
        await guard.call(fail)
    guard.on_error(TEMPORARY_LIMIT)
    await guard.acquire()
    assert clock.sleeps == [15.0, 30.0]


@pytest.mark.unit
async def test_outcome_includes_tokens_from_failed_calls_and_a_truncated_window_splits():
    calls: list[int] = []

    async def extractor(window: Window) -> ExtractorResult:
        calls.append(len(window.units))
        if len(window.units) > 1:
            raise _failed_call(TruncatedOutput("cut off"), 16_384)
        return _complete(window, 100)

    units = tuple(Unit(f"n{i}", f"S{i}", BookNodeKind.SENTENCE, "Text.", 0) for i in range(2))
    window = Window(id="w", division_id="d", heading_path=("C",), context="", units=units)
    [outcome] = await extract_windows([window], extractor, concurrency=1)
    assert calls == [2, 1, 1]
    assert outcome.uncovered == []
    assert outcome.output_tokens == 16_384 + 200
    assert outcome.errors[0].startswith("TruncatedOutput")


@pytest.mark.unit
async def test_the_failed_call_that_stops_a_run_is_still_on_the_outcome():
    async def extractor(window: Window) -> ExtractorResult:
        raise _failed_call(TruncatedOutput("cut off"), 500)

    guard = _guard(max_output_tokens=100)
    [outcome] = await extract_windows(_windows(1), extractor, concurrency=1, guard=guard)
    assert guard.stopped
    assert outcome.output_tokens == 500


@pytest.mark.unit
def test_book_text_in_a_parse_error_cannot_end_the_run():
    """A rulebook sentence about a 'usage limit reached' must not look like a provider error."""
    error = AdapterParseError("ChatAdapter", WindowExtractionSignature, "usage limit reached")
    assert not ends_the_run(error)
    guard = _guard()
    guard.on_error(error)
    assert not guard.stopped


@pytest.mark.unit
async def test_plan_limit_stops_the_run_after_one_call_instead_of_trying_every_window():
    extractor = _Extractor(fail_from=0)
    guard = _guard()
    windows = _windows(20)
    outcomes = await extract_windows(windows, extractor, concurrency=1, guard=guard)
    assert extractor.calls == 1
    assert "usage limit" in guard.stopped_reason
    report = build_coverage_report(windows, outcomes)
    assert report.units_uncovered == 20


@pytest.mark.unit
async def test_token_budget_stops_the_run():
    extractor = _Extractor(output_tokens=100)
    guard = _guard(max_output_tokens=250)
    await extract_windows(_windows(10), extractor, concurrency=1, guard=guard)
    assert extractor.calls == 3
    assert "budget" in guard.stopped_reason
    assert guard.output_tokens == 300


@pytest.mark.unit
async def test_requests_are_spaced_to_the_rate():
    clock = _Clock()
    guard = _guard(clock, requests_per_minute=30)
    for _ in range(3):
        await guard.acquire()
    assert clock.sleeps == [2.0, 2.0]
    assert guard.requests == 3


@pytest.mark.unit
async def test_temporary_rate_limit_pauses_callers_with_growing_backoff_and_resets():
    clock = _Clock()
    guard = _guard(clock)
    await guard.acquire()
    guard.on_error(TEMPORARY_LIMIT)
    await guard.acquire()
    guard.on_error(TEMPORARY_LIMIT)
    await guard.acquire()
    assert clock.sleeps == [15.0, 30.0]
    assert guard.rate_limit_pauses == 2
    assert not guard.stopped
    guard.record(1, 1)
    guard.on_error(TEMPORARY_LIMIT)
    await guard.acquire()
    assert clock.sleeps[-1] == 15.0


@pytest.mark.unit
async def test_acquire_after_stop_raises():
    guard = _guard()
    guard.stop("done")
    with pytest.raises(RunStopped, match="done"):
        await guard.acquire()


@pytest.mark.unit
async def test_no_guard_keeps_the_old_behavior():
    windows = _windows(2)
    outcomes = await extract_windows(windows, _Extractor(), concurrency=1)
    assert build_coverage_report(windows, outcomes).coverage == 1.0


class _Module:
    """Stands in for a DSPy Predict that always fails."""

    def __init__(self, error: Exception):
        self.error = error
        self.calls = 0

    def __call__(self, **_):
        self.calls += 1
        raise self.error


@pytest.mark.unit
async def test_review_stops_on_plan_limit_instead_of_marking_claims_for_a_person():
    """Running out of quota says nothing about a claim, so it must not fill the human queue."""
    from monitor_agents.book_decomposition.pipeline import ProvenancedAtom, WindowOutcome

    nodes = [
        BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0),
        BookNode(id="p", doc_id="d", kind=BookNodeKind.PARAGRAPH, parent_id="root", seq=1, text="T.", page_start=0, page_end=0),
        BookNode(id="s", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id="p", seq=2, text="T.", page_start=0, page_end=0),
    ]
    tree = BookTree(doc_id="d", title="T", decomposer_version="1", content_hash="x", nodes=nodes, report=DecompositionReport())
    atom = ExtractedAtom(kind=AtomKind.RULE, statement="A claim.", cites=["S1"])
    outcome = WindowOutcome(window_id="w", atoms=[ProvenancedAtom(atom=atom, source_node_ids=["s"], page=0)])
    model = DspyReviewModel(lm=object(), guard=_guard())
    model._verify = _Module(PLAN_LIMIT)
    with pytest.raises(RunStopped):
        await review_claims(tree, [outcome], model)
    assert model._verify.calls == 1
