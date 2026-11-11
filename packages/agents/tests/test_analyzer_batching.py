"""Word-budget batches, coverage splitting, and cancellation between batches (I-17, I-2).

The fake models here are scripted: one truncates (parse failure), one returns a
reply that covers only part of what it was sent, one refuses. Nothing calls a
real model.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dspy.utils.exceptions import AdapterParseError
from monitor_agents.analyzer import AnalysisCancelledError, Analyzer
from monitor_agents.analyzer._batching import plan_word_batches, run_covered_batch
from monitor_agents.analyzer._models import LLMExecutionSummary
from monitor_agents.analyzer.analyzer import BatchedExtractionSignature
from monitor_agents.utils.analyzer_support import SectionDigest

LIVE_REFUSAL = "The request was rejected because it was considered high risk"


def _section(path: str, text: str) -> SectionDigest:
    return SectionDigest(section_path=path, text=text, min_page=0, min_chunk_index=0)


class _ScriptedRun:
    """Records each call's unit ids and returns or raises what the script says."""

    def __init__(self, script: dict[tuple[str, ...], object]) -> None:
        self.script = script
        self.calls: list[tuple[str, ...]] = []

    async def __call__(self, items) -> object:
        ids = tuple(item.section_path for item in items)
        self.calls.append(ids)
        outcome = self.script[ids]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _covered(*paths: str) -> SimpleNamespace:
    return SimpleNamespace(sections_covered=list(paths))


# ---------------------------------------------------------------------------
# Word-budget planning
# ---------------------------------------------------------------------------


def test_word_batches_fill_to_the_budget() -> None:
    sections = [_section("a", "one two"), _section("b", "three four"), _section("c", "five six seven")]

    batches = plan_word_batches(sections, words_of=lambda s: len(s.text.split()), max_words=4, max_sections=16)

    assert [[s.section_path for s in batch] for batch in batches] == [["a", "b"], ["c"]]


def test_word_batches_keep_the_old_two_section_behaviour_with_old_settings() -> None:
    sections = [_section(str(i), "x y") for i in range(5)]

    # Pre-phase settings: no word cap, two sections per call.
    batches = plan_word_batches(sections, words_of=lambda s: len(s.text.split()), max_words=1_000_000, max_sections=2)

    assert [len(batch) for batch in batches] == [2, 2, 1]


def test_a_section_longer_than_the_budget_travels_alone() -> None:
    long_one = _section("long", " ".join(["word"] * 50))
    batches = plan_word_batches([long_one], words_of=lambda s: len(s.text.split()), max_words=10, max_sections=16)

    assert [[s.section_path for s in batch] for batch in batches] == [["long"]]


# ---------------------------------------------------------------------------
# Coverage-verified runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_truncated_reply_splits_and_the_uncovered_part_is_retried() -> None:
    """Cut off at the output cap → parse failure → split; every unit still lands."""
    sections = [_section("a", "t"), _section("b", "t"), _section("c", "t"), _section("d", "t")]
    run = _ScriptedRun(
        {
            ("a", "b", "c", "d"): AdapterParseError("ChatAdapter", BatchedExtractionSignature, "output cut off"),
            ("a", "b"): _covered("a", "b"),
            ("c", "d"): _covered("c", "d"),
        }
    )

    outcome = await run_covered_batch(sections, run, id_of=lambda s: s.section_path)

    assert run.calls == [("a", "b", "c", "d"), ("a", "b"), ("c", "d")]
    assert len(outcome.results) == 2
    assert outcome.held == []
    assert outcome.calls == 3


@pytest.mark.asyncio
async def test_a_partially_covered_reply_retries_only_the_uncovered_units() -> None:
    sections = [_section("a", "t"), _section("b", "t"), _section("c", "t"), _section("d", "t")]
    run = _ScriptedRun(
        {
            ("a", "b", "c", "d"): _covered("a", "b"),  # model dropped c and d
            ("c", "d"): _covered("c", "d"),
        }
    )

    outcome = await run_covered_batch(sections, run, id_of=lambda s: s.section_path)

    # The partial reply is kept for the units it covered; only the missing ones
    # are retried, and the batch is not accepted until they are covered.
    assert run.calls == [("a", "b", "c", "d"), ("c", "d")]
    assert len(outcome.results) == 2
    assert outcome.held == []


@pytest.mark.asyncio
async def test_a_unit_whose_reply_never_covers_it_is_held_with_its_id() -> None:
    sections = [_section("Chapter > Alpha", "t"), _section("Chapter > Beta", "t")]
    run = _ScriptedRun(
        {
            ("Chapter > Alpha", "Chapter > Beta"): _covered("Chapter > Alpha"),
            ("Chapter > Beta",): SimpleNamespace(sections_covered=[]),  # still not covered
        }
    )

    outcome = await run_covered_batch(sections, run, id_of=lambda s: s.section_path)

    assert [held.id for held in outcome.held] == ["Chapter > Beta"]
    assert "did not cover" in outcome.held[0].reason
    assert len(outcome.results) == 1  # Alpha's reply was kept


@pytest.mark.asyncio
async def test_a_refusal_still_splits_through_the_shared_part_c_helper() -> None:
    sections = [_section("a", "t"), _section("b", "t")]
    run = _ScriptedRun(
        {
            ("a", "b"): AdapterParseError("ChatAdapter", BatchedExtractionSignature, LIVE_REFUSAL),
            ("a",): _covered("a"),
            ("b",): _covered("b"),
        }
    )

    outcome = await run_covered_batch(sections, run, id_of=lambda s: s.section_path)

    assert run.calls == [("a", "b"), ("a",), ("b",)]
    assert len(outcome.results) == 2
    assert outcome.held == []


@pytest.mark.asyncio
async def test_a_one_unit_batch_that_refuses_is_held_not_retried() -> None:
    sections = [_section("solo", "t")]
    run = _ScriptedRun({("solo",): AdapterParseError("ChatAdapter", BatchedExtractionSignature, LIVE_REFUSAL)})

    outcome = await run_covered_batch(sections, run, id_of=lambda s: s.section_path)

    assert run.calls == [("solo",)]
    assert [held.id for held in outcome.held] == ["solo"]
    assert LIVE_REFUSAL in outcome.held[0].reason


@pytest.mark.asyncio
async def test_an_empty_batch_is_never_run() -> None:
    run = _ScriptedRun({})

    outcome = await run_covered_batch([], run, id_of=lambda s: s.section_path)

    assert run.calls == []
    assert outcome.results == [] and outcome.held == []


# ---------------------------------------------------------------------------
# _batched_extract_all: budgets, held items on the job, cancellation
# ---------------------------------------------------------------------------


def _fake_extraction_call(module, *, stage=None, batch_id=None, **kwargs):
    """A complete reply: every section echoed back in sections_covered."""
    context = kwargs["sections_context"]
    covered = [
        line.removeprefix("# Section: ").strip() for line in context.splitlines() if line.startswith("# Section: ")
    ]
    return SimpleNamespace(
        axioms=[],
        entities=[],
        lore_facts=[],
        sections_covered=covered,
    )


@pytest.mark.asyncio
async def test_batched_extraction_packs_small_sections_into_word_budget_calls(monkeypatch) -> None:
    analyzer = Analyzer()
    monkeypatch.setenv("MONITOR_ANALYZER_BATCH_WORDS", "10")
    monkeypatch.setenv("MONITOR_ANALYZER_BATCH_SECTIONS", "16")
    contexts: list[str] = []

    async def fake_call_module(module, **kwargs):
        contexts.append(kwargs["sections_context"])
        return _fake_extraction_call(module, **kwargs)

    monkeypatch.setattr(analyzer, "_call_module", fake_call_module)
    sections = [_section(f"s{i}", "one two three") for i in range(4)]  # 3 words each → 3 per 10-word batch

    await analyzer._batched_extract_all(sections, "Source", True, True, True)

    assert len(contexts) == 2
    assert contexts[0].count("# Section: ") == 3
    assert contexts[1].count("# Section: ") == 1


@pytest.mark.asyncio
async def test_batched_extraction_old_settings_batch_two_sections_per_call(monkeypatch) -> None:
    analyzer = Analyzer()
    monkeypatch.setenv("MONITOR_ANALYZER_BATCH_WORDS", "1000000")
    monkeypatch.setenv("MONITOR_ANALYZER_BATCH_SECTIONS", "2")
    contexts: list[str] = []

    async def fake_call_module(module, **kwargs):
        contexts.append(kwargs["sections_context"])
        return _fake_extraction_call(module, **kwargs)

    monkeypatch.setattr(analyzer, "_call_module", fake_call_module)
    sections = [_section(f"s{i}", "x y z z z z z z z z z") for i in range(5)]  # long text, old cap

    await analyzer._batched_extract_all(sections, "Source", True, True, True)

    assert [c.count("# Section: ") for c in contexts] == [2, 2, 1]


@pytest.mark.asyncio
async def test_held_and_failed_sections_reach_the_job_result(monkeypatch) -> None:
    analyzer = Analyzer()
    analyzer._active_execution_summary = LLMExecutionSummary()
    sections = [_section("Alpha", "t"), _section("Beta", "t")]

    async def always_refuses(module, **kwargs):
        raise AdapterParseError("ChatAdapter", BatchedExtractionSignature, LIVE_REFUSAL)

    monkeypatch.setattr(analyzer, "_call_module", always_refuses)

    axioms, entities, lore = await analyzer._batched_extract_all(sections, "Source", True, True, True)

    assert axioms == [] and entities == [] and lore == []
    failed = analyzer._active_execution_summary.failed_sections
    assert sorted(entry["section_path"] for entry in failed) == ["Alpha", "Beta"]
    assert all(LIVE_REFUSAL in entry["reason"] for entry in failed)
    assert all(entry["stage"] == "batched_extraction" for entry in failed)


@pytest.mark.asyncio
async def test_an_unrecoverable_batch_failure_records_every_section(monkeypatch) -> None:
    analyzer = Analyzer()
    analyzer._active_execution_summary = LLMExecutionSummary()
    sections = [_section("Alpha", "t"), _section("Beta", "t")]

    async def explodes(module, **kwargs):
        raise RuntimeError("provider gone")

    monkeypatch.setattr(analyzer, "_call_module", explodes)

    await analyzer._batched_extract_all(sections, "Source", True, True, True)

    failed = analyzer._active_execution_summary.failed_sections
    assert sorted(entry["section_path"] for entry in failed) == ["Alpha", "Beta"]
    assert all("provider gone" in entry["reason"] for entry in failed)


@pytest.mark.asyncio
async def test_cancellation_stops_before_the_next_model_call(monkeypatch) -> None:
    analyzer = Analyzer()
    analyzer._active_job_id = uuid4()
    runner = AsyncMock()
    monkeypatch.setattr(analyzer._llm_runner, "run_blocking", runner)
    cancel_check = AsyncMock(return_value=True)
    monkeypatch.setattr("monitor_agents.analyzer._core.job_is_cancelled", cancel_check)

    with pytest.raises(AnalysisCancelledError):
        await analyzer._call_module(object(), stage="batched_extraction", sections_context="x")
    runner.assert_not_awaited()

    # Once seen, the stop short-circuits without another job read.
    with pytest.raises(AnalysisCancelledError):
        await analyzer._call_module(object(), stage="batched_extraction", sections_context="x")
    cancel_check.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancellation_propagates_out_of_batched_extraction(monkeypatch) -> None:
    analyzer = Analyzer()
    analyzer._active_execution_summary = LLMExecutionSummary()
    sections = [_section("Alpha", "t"), _section("Beta", "t")]

    async def cancelled(module, **kwargs):
        raise AnalysisCancelledError("job cancelled")

    monkeypatch.setattr(analyzer, "_call_module", cancelled)

    with pytest.raises(AnalysisCancelledError):
        await analyzer._batched_extract_all(sections, "Source", True, True, True)

    # A cancelled run records no fake failures — the cancel endpoint owns the record.
    assert analyzer._active_execution_summary.failed_sections == []


def test_cancellation_is_not_swallowed_by_except_exception() -> None:
    """The stop signal must pass through every existing ``except Exception``."""
    with pytest.raises(AnalysisCancelledError):
        try:
            raise AnalysisCancelledError("stop")
        except Exception:  # noqa: BLE001  # reason: proving it does NOT catch the stop signal
            pytest.fail("except Exception caught AnalysisCancelledError")


# ---------------------------------------------------------------------------
# Job status stays truthful while the run is still working (fact d, I-17)
# ---------------------------------------------------------------------------


def test_backing_off_and_partial_never_become_the_job_status(monkeypatch) -> None:
    from datetime import UTC, datetime

    from monitor_agents.llm_execution import LLMAttemptRecord, LLMAttemptStatus

    analyzer = Analyzer()
    job_id = uuid4()
    updates: list[dict] = []
    monkeypatch.setattr(analyzer, "_update_job", lambda _job_id, **kwargs: updates.append(kwargs))

    def _record(summary: LLMExecutionSummary, status: LLMAttemptStatus) -> None:
        analyzer._record_llm_attempt(
            job_id,
            summary,
            LLMAttemptRecord(
                job_id=job_id,
                source_id=None,
                stage="batched_extraction",
                batch_id="1/2",
                provider_id="prov",
                model="model",
                role="heavy",
                attempt_no=1,
                max_attempts=3,
                started_at=datetime.now(UTC),
                ended_at=datetime.now(UTC),
                status=status,
                retryable=status is not LLMAttemptStatus.FAILED_NON_RETRYABLE,
                error_class="rate_limit" if status is LLMAttemptStatus.BACKING_OFF else "validation",
                error_message="something happened",
                request_id="req",
                backoff_ms=1500 if status is LLMAttemptStatus.BACKING_OFF else None,
            ),
        )

    backing_off = LLMExecutionSummary()
    _record(backing_off, LLMAttemptStatus.BACKING_OFF)
    partial_mid_run = LLMExecutionSummary(failed_batches=1, succeeded_batches=3)
    _record(partial_mid_run, LLMAttemptStatus.FAILED_NON_RETRYABLE)

    # Work is still in progress: no status write at all for these two.
    assert updates, "telemetry must still reach the job"
    assert all(kwargs.get("status") is None for kwargs in updates)
    # The retry signal and the error detail still flow.
    assert any(kwargs.get("next_retry_at") is not None for kwargs in updates)
    assert any(kwargs.get("errors") for kwargs in updates)
    # partial is a flag on the job, not a status.
    assert all("partial" in kwargs for kwargs in updates)

    # A cancelled attempt is the one case where the status must change.
    _record(LLMExecutionSummary(), LLMAttemptStatus.CANCELLED)
    assert updates[-1].get("status") is not None
    assert updates[-1]["status"].value == "cancelled"
