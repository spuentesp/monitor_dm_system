"""Shared LLM execution layer for retry-safe, auditable DSPy calls.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents runtime helpers
CALLED BY: analyzer and other LLM-driven agent paths

This module centralizes timeout, retry/backoff, and attempt metadata so agent
code can use one consistent execution policy instead of scattered ad-hoc logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar
from uuid import UUID, uuid4

from monitor_agents.dspy_runtime import default_role_for_node, describe_dspy_target
from monitor_agents.llm_errors import LLMErrorInfo, classify_llm_error
from monitor_data.config import settings
from monitor_data.db.postgres import get_postgres_client
from monitor_data.schemas.llm_config import ModelRole

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LLMAttemptStatus(str, Enum):
    """Execution outcome for a single LLM attempt."""

    SUCCEEDED = "succeeded"
    BACKING_OFF = "backing_off"
    FAILED = "failed"
    FAILED_NON_RETRYABLE = "failed_non_retryable"
    CANCELLED = "cancelled"


@dataclass(slots=True, frozen=True)
class LLMExecutionContext:
    """Durable context envelope for one logical LLM task."""

    job_id: Optional[UUID] = None
    source_id: Optional[UUID] = None
    stage: str = "unspecified"
    batch_id: Optional[str] = None
    node_name: str = "analyzer"
    role: Optional[ModelRole] = None


@dataclass(slots=True, frozen=True)
class LLMAttemptRecord:
    """Attempt-level audit record for one provider call."""

    job_id: Optional[UUID]
    source_id: Optional[UUID]
    stage: str
    batch_id: Optional[str]
    provider_id: Optional[str]
    model: Optional[str]
    role: Optional[str]
    attempt_no: int
    max_attempts: int
    started_at: datetime
    ended_at: datetime
    status: LLMAttemptStatus
    retryable: bool
    error_class: Optional[str]
    error_message: Optional[str]
    request_id: str
    prompt_hash: Optional[str] = None
    input_size: Optional[int] = None
    output_size: Optional[int] = None
    backoff_ms: Optional[int] = None


@dataclass(slots=True)
class LLMExecutionResult(Generic[T]):
    """Successful result plus all recorded attempts."""

    value: T
    attempts: list[LLMAttemptRecord] = field(default_factory=list)

    @property
    def retried_count(self) -> int:
        return max(0, len(self.attempts) - 1)


class LLMTaskRunner:
    """Run a blocking DSPy/LLM task with consistent timeout and retry policy."""

    def __init__(
        self,
        *,
        agent_name: str,
        max_attempts: Optional[int] = None,
        base_delay_s: Optional[float] = None,
        max_delay_s: Optional[float] = None,
        timeout_s: Optional[float] = None,
    ) -> None:
        self.agent_name = agent_name
        self.max_attempts = max_attempts or settings.llm_retry_attempts
        self.base_delay_s = float(base_delay_s or settings.llm_retry_min_wait)
        self.max_delay_s = float(max_delay_s or settings.llm_retry_max_wait)
        self.timeout_s = float(timeout_s or 120.0)

    async def run_blocking(
        self,
        operation: Callable[..., T],
        *,
        kwargs: dict[str, Any],
        context: LLMExecutionContext,
        timeout: Optional[float] = None,
        on_attempt: Optional[Callable[[LLMAttemptRecord], Any]] = None,
    ) -> LLMExecutionResult[T]:
        """Execute a blocking LLM task in a thread with retry/backoff policy."""
        timeout_s = float(timeout or self.timeout_s)
        resolved_role = context.role or default_role_for_node(context.node_name)
        target = describe_dspy_target(context.node_name, resolved_role)
        attempts: list[LLMAttemptRecord] = []
        prompt_hash = self._hash_payload(kwargs)
        input_size = self._estimate_size(kwargs)

        for attempt_no in range(1, self.max_attempts + 1):
            started_at = datetime.now(timezone.utc)
            try:
                value = await asyncio.wait_for(
                    asyncio.to_thread(operation, **kwargs),
                    timeout=timeout_s,
                )
                record = LLMAttemptRecord(
                    job_id=context.job_id,
                    source_id=context.source_id,
                    stage=context.stage,
                    batch_id=context.batch_id,
                    provider_id=target.get("provider"),
                    model=target.get("model"),
                    role=(resolved_role.value if resolved_role else None),
                    attempt_no=attempt_no,
                    max_attempts=self.max_attempts,
                    started_at=started_at,
                    ended_at=datetime.now(timezone.utc),
                    status=LLMAttemptStatus.SUCCEEDED,
                    retryable=False,
                    error_class=None,
                    error_message=None,
                    request_id=str(uuid4()),
                    prompt_hash=prompt_hash,
                    input_size=input_size,
                    output_size=self._estimate_size(value),
                    backoff_ms=None,
                )
                attempts.append(record)
                await self._emit_attempt(on_attempt, record)
                return LLMExecutionResult(value=value, attempts=attempts)
            except BaseException as exc:  # noqa: BLE001
                error_info = classify_llm_error(exc)
                should_retry = error_info.retryable and attempt_no < self.max_attempts
                backoff_ms = None
                backoff_s = 0.0
                if should_retry:
                    backoff_s = self._compute_backoff(attempt_no=attempt_no, error_info=error_info)
                    backoff_ms = int(backoff_s * 1000)
                    status = LLMAttemptStatus.BACKING_OFF
                elif error_info.error_class.value == "cancelled":
                    status = LLMAttemptStatus.CANCELLED
                elif error_info.retryable:
                    status = LLMAttemptStatus.FAILED
                else:
                    status = LLMAttemptStatus.FAILED_NON_RETRYABLE

                record = LLMAttemptRecord(
                    job_id=context.job_id,
                    source_id=context.source_id,
                    stage=context.stage,
                    batch_id=context.batch_id,
                    provider_id=target.get("provider"),
                    model=target.get("model"),
                    role=(resolved_role.value if resolved_role else None),
                    attempt_no=attempt_no,
                    max_attempts=self.max_attempts,
                    started_at=started_at,
                    ended_at=datetime.now(timezone.utc),
                    status=status,
                    retryable=error_info.retryable,
                    error_class=error_info.error_class.value,
                    error_message=error_info.message,
                    request_id=str(uuid4()),
                    prompt_hash=prompt_hash,
                    input_size=input_size,
                    output_size=None,
                    backoff_ms=backoff_ms,
                )
                attempts.append(record)
                await self._emit_attempt(on_attempt, record)

                if not should_retry:
                    raise

                logger.warning(
                    "%s LLM task backing off after %s (%s, batch=%s, attempt=%d/%d, delay_ms=%s)",
                    self.agent_name,
                    error_info.error_class.value,
                    context.stage,
                    context.batch_id,
                    attempt_no,
                    self.max_attempts,
                    backoff_ms,
                )
                await asyncio.sleep(backoff_s)

        raise RuntimeError("LLMTaskRunner exhausted attempts without returning or raising")

    def _compute_backoff(self, *, attempt_no: int, error_info: LLMErrorInfo) -> float:
        """Exponential backoff with full jitter and Retry-After support."""
        if error_info.retry_after_s is not None and error_info.retry_after_s > 0:
            return min(self.max_delay_s, float(error_info.retry_after_s))

        exponential = min(self.max_delay_s, self.base_delay_s * (2 ** max(0, attempt_no - 1)))
        return random.uniform(0.0, exponential)

    async def _emit_attempt(
        self,
        callback: Optional[Callable[[LLMAttemptRecord], Any]],
        record: LLMAttemptRecord,
    ) -> None:
        await self._persist_attempt(record)
        if callback is None:
            return
        try:
            result = callback(record)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "LLM attempt callback failed for %s/%s: %s", record.stage, record.batch_id, exc
            )

    async def _persist_attempt(self, record: LLMAttemptRecord) -> None:
        """Best-effort durable attempt write to PostgreSQL for later audit/replay."""
        try:
            postgres = get_postgres_client()
            await postgres.llm_task_attempt_record(
                {
                    "job_id": str(record.job_id) if record.job_id else None,
                    "source_id": str(record.source_id) if record.source_id else None,
                    "stage": record.stage,
                    "batch_id": record.batch_id,
                    "provider_id": record.provider_id,
                    "model": record.model,
                    "role": record.role,
                    "attempt_no": record.attempt_no,
                    "max_attempts": record.max_attempts,
                    "status": record.status.value,
                    "retryable": record.retryable,
                    "error_class": record.error_class,
                    "error_message": record.error_message,
                    "backoff_ms": record.backoff_ms,
                    "started_at": record.started_at,
                    "ended_at": record.ended_at,
                    "request_id": record.request_id,
                    "prompt_hash": record.prompt_hash,
                    "input_size": record.input_size,
                    "output_size": record.output_size,
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "Could not persist LLM attempt for %s/%s to PostgreSQL: %s",
                record.stage,
                record.batch_id,
                exc,
            )

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        try:
            encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        except TypeError:
            encoded = repr(payload).encode("utf-8", errors="replace")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _estimate_size(payload: Any) -> int:
        if isinstance(payload, str):
            return len(payload)
        try:
            return len(json.dumps(payload, sort_keys=True, default=str))
        except TypeError:
            return len(repr(payload))
