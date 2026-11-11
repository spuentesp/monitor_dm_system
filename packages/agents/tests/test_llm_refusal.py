"""CONTENT_REFUSED: refusal text is its own error class, never quota, never retried as-is (I-2).

The live failure: MiMo v2.6 Flash refused 3 of 59 extraction batches with
"The request was rejected because it was considered high risk", which surfaced
as a JSON parse failure. Refusal must not end the run as quota and must not be
retried with the identical request.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from dspy.utils.exceptions import AdapterParseError
from monitor_agents.analyzer import Analyzer
from monitor_agents.book_decomposition.extractor import WindowExtractionSignature
from monitor_agents.book_decomposition.pacing import RunGuard, ends_the_run
from monitor_agents.llm_errors import (
    REFUSAL_PHRASES,
    LLMErrorClass,
    LLMErrorInfo,
    LLMProviderUnavailable,
    classify_llm_error,
    is_retryable_exception,
)
from monitor_agents.llm_execution import LLMExecutionContext, LLMTaskRunner

LIVE_REFUSAL = "The request was rejected because it was considered high risk"


def _refusal_as_parse_error() -> AdapterParseError:
    """How the refusal reached us live: a 200 whose body was the refusal text."""
    return AdapterParseError("ChatAdapter", WindowExtractionSignature, LIVE_REFUSAL)


@pytest.mark.unit
def test_live_refusal_phrase_classifies_as_content_refused() -> None:
    info = classify_llm_error(RuntimeError(LIVE_REFUSAL))
    assert info.error_class == LLMErrorClass.CONTENT_REFUSED
    assert info.retryable is False


@pytest.mark.unit
def test_refusal_phrases_are_kept_in_one_place() -> None:
    assert LIVE_REFUSAL.casefold() in REFUSAL_PHRASES
    assert all(isinstance(phrase, str) and phrase for phrase in REFUSAL_PHRASES)


@pytest.mark.unit
def test_refusal_inside_a_parse_error_classifies_as_content_refused() -> None:
    info = classify_llm_error(_refusal_as_parse_error())
    assert info.error_class == LLMErrorClass.CONTENT_REFUSED
    assert info.retryable is False


@pytest.mark.unit
@pytest.mark.parametrize("reply", ["", "   ", "Sorry, I cannot help with that request."])
def test_empty_or_non_structured_reply_where_structured_output_was_required(reply: str) -> None:
    exc = AdapterParseError("ChatAdapter", WindowExtractionSignature, reply)
    info = classify_llm_error(exc)
    assert info.error_class == LLMErrorClass.CONTENT_REFUSED
    assert info.retryable is False


@pytest.mark.unit
def test_structured_parse_failure_is_not_mistaken_for_a_refusal() -> None:
    exc = AdapterParseError("ChatAdapter", WindowExtractionSignature, '{"atoms": [{"kind": ')
    assert classify_llm_error(exc).error_class != LLMErrorClass.CONTENT_REFUSED


@pytest.mark.unit
def test_refusal_is_not_retried_unchanged() -> None:
    assert is_retryable_exception(_refusal_as_parse_error()) is False
    assert is_retryable_exception(RuntimeError(LIVE_REFUSAL)) is False


@pytest.mark.unit
def test_refusal_is_not_classified_as_quota() -> None:
    """The run-ending path keys off QUOTA/AUTH; refusal must land outside both."""
    for exc in (RuntimeError(LIVE_REFUSAL), _refusal_as_parse_error()):
        assert classify_llm_error(exc).error_class == LLMErrorClass.CONTENT_REFUSED
        assert not ends_the_run(exc)


@pytest.mark.unit
def test_refusal_does_not_stop_a_run_guard() -> None:
    guard = RunGuard()
    guard.on_error(RuntimeError(LIVE_REFUSAL))
    guard.on_error(_refusal_as_parse_error())
    assert not guard.stopped
    assert guard.stop_kind is None
    assert guard.rate_limit_pauses == 0


@pytest.mark.unit
def test_provider_unavailable_message_explains_a_refusal() -> None:
    exc = LLMProviderUnavailable(LLMErrorInfo(LLMErrorClass.CONTENT_REFUSED, retryable=False, message=LIVE_REFUSAL))
    assert "refused" in exc.user_message.lower()
    assert "not help" in exc.user_message.lower()


class _CountingRunner:
    """LLMTaskRunner stand-in that records how many attempts were made."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    async def run_blocking(self, operation, *, kwargs, context, timeout=None, on_attempt=None):
        self.calls += 1
        raise self.error


class _FakePostgres:
    def __init__(self) -> None:
        self.records: list = []

    async def llm_task_attempt_record(self, attempt):
        self.records.append(attempt)
        return attempt


@pytest.mark.unit
async def test_task_runner_does_not_retry_a_refusal(monkeypatch) -> None:
    fake_postgres = _FakePostgres()
    monkeypatch.setattr("monitor_agents.llm_execution.get_postgres_client", lambda: fake_postgres)
    monkeypatch.setattr(
        "monitor_agents.llm_execution.describe_dspy_target",
        lambda *_args, **_kwargs: {"provider": "p", "model": "m"},
    )
    runner = LLMTaskRunner(agent_name="Analyzer", max_attempts=3, base_delay_s=0.001, timeout_s=1)

    def refuse(**_kwargs):
        raise _refusal_as_parse_error()

    with pytest.raises(AdapterParseError):
        await runner.run_blocking(
            refuse,
            kwargs={},
            context=LLMExecutionContext(job_id=uuid4(), stage="batched_extraction"),
        )

    assert len(fake_postgres.records) == 1
    assert fake_postgres.records[0]["status"] == "failed_non_retryable"
    assert fake_postgres.records[0]["error_class"] == "content_refused"


@pytest.mark.unit
async def test_task_runner_still_retries_a_rate_limit_for_contrast(monkeypatch) -> None:
    fake_postgres = _FakePostgres()
    monkeypatch.setattr("monitor_agents.llm_execution.get_postgres_client", lambda: fake_postgres)
    monkeypatch.setattr(
        "monitor_agents.llm_execution.describe_dspy_target",
        lambda *_args, **_kwargs: {"provider": "p", "model": "m"},
    )
    runner = LLMTaskRunner(agent_name="Analyzer", max_attempts=2, base_delay_s=0.001, timeout_s=1)

    def rate_limited(**_kwargs):
        raise RuntimeError("429 too many requests")

    with pytest.raises(RuntimeError):
        await runner.run_blocking(
            rate_limited,
            kwargs={},
            context=LLMExecutionContext(job_id=uuid4(), stage="batched_extraction"),
        )

    assert len(fake_postgres.records) == 2


class _RefusingModule:
    def __init__(self, error: Exception) -> None:
        self.error = error


@pytest.mark.unit
async def test_call_module_does_not_retry_a_refusal_unchanged(monkeypatch) -> None:
    """Cross-component: _call_module must consult classify_llm_error and re-raise."""
    analyzer = Analyzer()

    class _Runner:
        def __init__(self) -> None:
            self.calls = 0

        async def run_blocking(self, operation, *, kwargs, context, timeout=None, on_attempt=None):
            self.calls += 1
            raise _refusal_as_parse_error()

    runner = _Runner()
    monkeypatch.setattr(analyzer, "_llm_runner", runner)

    with pytest.raises(AdapterParseError):
        await analyzer._call_module(_RefusingModule(_refusal_as_parse_error()), sections_context="x")

    assert runner.calls == 1


@pytest.mark.unit
async def test_call_module_still_retries_an_ordinary_parse_failure(monkeypatch) -> None:
    """Control: the existing once-only retry for transient parse failures stays."""
    analyzer = Analyzer()

    class _Runner:
        def __init__(self) -> None:
            self.calls = 0

        async def run_blocking(self, operation, *, kwargs, context, timeout=None, on_attempt=None):
            self.calls += 1
            raise AdapterParseError("ChatAdapter", WindowExtractionSignature, '{"atoms": [{"kind": "rule"')

    runner = _Runner()
    monkeypatch.setattr(analyzer, "_llm_runner", runner)

    with pytest.raises(AdapterParseError):
        await analyzer._call_module(_RefusingModule(_refusal_as_parse_error()), sections_context="x")

    assert runner.calls == 2
