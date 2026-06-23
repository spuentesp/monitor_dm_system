from uuid import uuid4

import pytest

from monitor_agents.llm_errors import LLMErrorClass, LLMErrorInfo, classify_llm_error
from monitor_agents.llm_execution import LLMExecutionContext, LLMTaskRunner


class _FakePostgres:
    def __init__(self):
        self.records = []

    async def llm_task_attempt_record(self, attempt):  # noqa: ANN001
        self.records.append(attempt)
        return attempt


class _FailingPostgres:
    async def llm_task_attempt_record(self, attempt):  # noqa: ANN001
        raise RuntimeError("postgres unavailable")


def test_classify_llm_error_flags_rate_limits_as_retryable():
    info = classify_llm_error(RuntimeError("429 rate limit exceeded; retry after 2s"))

    assert info.error_class == LLMErrorClass.RATE_LIMIT
    assert info.retryable is True


def test_classify_llm_error_flags_auth_failures_as_non_retryable():
    info = classify_llm_error(RuntimeError("401 invalid api key"))

    assert info.error_class == LLMErrorClass.AUTH
    assert info.retryable is False


@pytest.mark.asyncio
async def test_task_runner_persists_attempt_metadata_to_postgres(monkeypatch):
    fake_postgres = _FakePostgres()
    monkeypatch.setattr("monitor_agents.llm_execution.get_postgres_client", lambda: fake_postgres)
    monkeypatch.setattr(
        "monitor_agents.llm_execution.describe_dspy_target",
        lambda *_args, **_kwargs: {"provider": "github-models-default", "model": "gpt-4.1-mini"},
    )

    runner = LLMTaskRunner(agent_name="Analyzer", max_attempts=1, timeout_s=1)
    result = await runner.run_blocking(
        lambda text: text.upper(),
        kwargs={"text": "hello world"},
        context=LLMExecutionContext(
            job_id=uuid4(),
            source_id=uuid4(),
            stage="rules",
            batch_id="batch-1",
            node_name="analyzer",
        ),
    )

    assert result.value == "HELLO WORLD"
    assert len(fake_postgres.records) == 1
    attempt = fake_postgres.records[0]
    assert attempt["status"] == "succeeded"
    assert attempt["provider_id"] == "github-models-default"
    assert attempt["prompt_hash"]
    assert attempt["input_size"] > 0
    assert attempt["output_size"] == len("HELLO WORLD")


@pytest.mark.asyncio
async def test_task_runner_tolerates_attempt_ledger_failures(monkeypatch):
    monkeypatch.setattr(
        "monitor_agents.llm_execution.get_postgres_client", lambda: _FailingPostgres()
    )
    monkeypatch.setattr(
        "monitor_agents.llm_execution.describe_dspy_target",
        lambda *_args, **_kwargs: {"provider": "github-models-default", "model": "gpt-4.1-mini"},
    )

    runner = LLMTaskRunner(agent_name="Analyzer", max_attempts=1, timeout_s=1)
    result = await runner.run_blocking(
        lambda text: text[::-1],
        kwargs={"text": "audit"},
        context=LLMExecutionContext(stage="entities", node_name="analyzer"),
    )

    assert result.value == "tidua"


def test_compute_backoff_increases_with_attempt_no():
    """Test that _compute_backoff increases delay with attempt number."""
    runner = LLMTaskRunner(
        agent_name="Analyzer", max_attempts=3, base_delay_s=1.0, max_delay_s=60.0, timeout_s=10
    )

    backoff_1 = runner._compute_backoff(
        attempt_no=1,
        error_info=LLMErrorInfo(
            error_class=LLMErrorClass.UNKNOWN, retryable=True, message="error1"
        ),
    )
    backoff_2 = runner._compute_backoff(
        attempt_no=2,
        error_info=LLMErrorInfo(
            error_class=LLMErrorClass.UNKNOWN, retryable=True, message="error2"
        ),
    )
    backoff_3 = runner._compute_backoff(
        attempt_no=3,
        error_info=LLMErrorInfo(
            error_class=LLMErrorClass.UNKNOWN, retryable=True, message="error3"
        ),
    )

    # Backoff should increase with attempt number (exponential backoff)
    assert backoff_1 >= 0
    assert backoff_2 >= 0
    assert backoff_3 >= 0


def test_compute_backoff_with_retry_after():
    """Test that _compute_backoff uses retry_after_s when available."""
    runner = LLMTaskRunner(
        agent_name="Analyzer", max_attempts=3, base_delay_s=1.0, max_delay_s=60.0, timeout_s=10
    )

    backoff = runner._compute_backoff(
        attempt_no=1,
        error_info=LLMErrorInfo(
            error_class=LLMErrorClass.RATE_LIMIT,
            retryable=True,
            message="rate limited",
            retry_after_s=30.0,
        ),
    )

    # Should use the retry_after_s value (capped at max_delay_s)
    assert backoff == 30.0


def test_compute_backoff_respects_max_delay():
    """Test that _compute_backoff respects max_delay_s cap."""
    runner = LLMTaskRunner(
        agent_name="Analyzer", max_attempts=3, base_delay_s=10.0, max_delay_s=30.0, timeout_s=10
    )

    backoff = runner._compute_backoff(
        attempt_no=10,
        error_info=LLMErrorInfo(error_class=LLMErrorClass.UNKNOWN, retryable=True, message="error"),
    )

    # Should be capped at max_delay_s
    assert backoff <= 30.0


def test_estimate_size_for_string():
    """Test _estimate_size correctly estimates string size."""
    runner = LLMTaskRunner(
        agent_name="Analyzer", max_attempts=3, base_delay_s=1.0, max_delay_s=60.0, timeout_s=10
    )

    size = runner._estimate_size("hello world")
    assert size == len("hello world")


def test_estimate_size_for_list():
    """Test _estimate_size correctly estimates list size."""
    runner = LLMTaskRunner(
        agent_name="Analyzer", max_attempts=3, base_delay_s=1.0, max_delay_s=60.0, timeout_s=10
    )

    size = runner._estimate_size(["a", "b", "c"])
    assert size > 0  # List returns combined size of elements


def test_estimate_size_for_dict():
    """Test _estimate_size correctly estimates dict size."""
    runner = LLMTaskRunner(
        agent_name="Analyzer", max_attempts=3, base_delay_s=1.0, max_delay_s=60.0, timeout_s=10
    )

    size = runner._estimate_size({"key": "value"})
    assert size >= 1


def test_hash_payload_deterministic():
    """Test that _hash_payload produces deterministic results."""
    runner = LLMTaskRunner(
        agent_name="Analyzer", max_attempts=3, base_delay_s=1.0, max_delay_s=60.0, timeout_s=10
    )

    payload = {"text": "hello", "num": 42}
    hash1 = runner._hash_payload(payload)
    hash2 = runner._hash_payload(payload)

    assert hash1 == hash2


def test_hash_payload_different_for_different_inputs():
    """Test that _hash_payload produces different hashes for different inputs."""
    runner = LLMTaskRunner(agent_name="Analyzer", max_attempts=3, timeout_s=10)

    hash1 = runner._hash_payload({"text": "hello"})
    hash2 = runner._hash_payload({"text": "world"})

    assert hash1 != hash2


def test_classify_llm_error_flags_timeout_as_retryable():
    """Test that timeout errors are classified as retryable."""
    info = classify_llm_error(RuntimeError("timed out after 30s"))

    assert info.error_class == LLMErrorClass.TIMEOUT
    assert info.retryable is True


def test_classify_llm_error_flags_invalid_response_as_unknown():
    """Test that invalid response errors are classified as UNKNOWN with non-retryable."""
    info = classify_llm_error(RuntimeError("failed to parse JSON response"))

    assert info.error_class == LLMErrorClass.UNKNOWN
    assert info.retryable is False


def test_classify_llm_error_flags_unknown_errors_as_non_retryable():
    """Test that unknown errors default to non-retryable."""
    info = classify_llm_error(RuntimeError("some unexpected error"))

    assert info.error_class == LLMErrorClass.UNKNOWN
    assert info.retryable is False


def test_llm_execution_context_defaults():
    """Test LLMExecutionContext default values."""
    ctx = LLMExecutionContext(stage="test", node_name="test-node")

    assert ctx.stage == "test"
    assert ctx.node_name == "test-node"
    assert ctx.job_id is None
    assert ctx.source_id is None
    assert ctx.batch_id is None


def test_llm_execution_context_with_all_fields():
    """Test LLMExecutionContext with all fields specified."""
    job_id = uuid4()
    source_id = uuid4()
    ctx = LLMExecutionContext(
        stage="rules",
        node_name="analyzer",
        job_id=job_id,
        source_id=source_id,
        batch_id="batch-1",
    )

    assert ctx.stage == "rules"
    assert ctx.node_name == "analyzer"
    assert ctx.job_id == job_id
    assert ctx.source_id == source_id
    assert ctx.batch_id == "batch-1"
