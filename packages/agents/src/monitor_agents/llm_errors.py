"""Normalized LLM error taxonomy and retryability helpers.

LAYER: 2 (agents)
IMPORTS FROM: external libraries only
CALLED BY: BaseAgent, llm_execution, analyzer

This module keeps retry policy classification in one place so MONITOR does not
scatter provider-specific string matching across the ingestion pipeline.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class LLMErrorClass(str, Enum):
    """Normalized categories for provider/runtime failures."""

    RATE_LIMIT = "rate_limit"
    UPSTREAM = "upstream"
    NETWORK = "network"
    TIMEOUT = "timeout"
    QUOTA = "quota"
    AUTH = "auth"
    MISCONFIGURATION = "misconfiguration"
    VALIDATION = "validation"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class LLMErrorInfo:
    """Normalized failure record used by retry and audit code."""

    error_class: LLMErrorClass
    retryable: bool
    message: str
    retry_after_s: Optional[float] = None


_RETRY_AFTER_RE = re.compile(r"retry(?:[- ]after)?[^0-9]{0,8}(\d+(?:\.\d+)?)", re.IGNORECASE)


def _message(exc: BaseException) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text[:600]


def _retry_after_seconds(message: str) -> Optional[float]:
    match = _RETRY_AFTER_RE.search(message)
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def classify_llm_error(exc: BaseException) -> LLMErrorInfo:
    """Classify an LLM/provider error into retryable and non-retryable groups."""
    if isinstance(exc, asyncio.CancelledError):
        return LLMErrorInfo(LLMErrorClass.CANCELLED, retryable=False, message=_message(exc))
    if isinstance(exc, TimeoutError | asyncio.TimeoutError):
        return LLMErrorInfo(LLMErrorClass.TIMEOUT, retryable=True, message=_message(exc))

    message = _message(exc)
    lowered = message.lower()
    type_name = exc.__class__.__name__.lower()

    if any(token in lowered for token in ("429", "rate limit", "too many requests", "ratelimit")):
        return LLMErrorInfo(
            LLMErrorClass.RATE_LIMIT,
            retryable=True,
            message=message,
            retry_after_s=_retry_after_seconds(message),
        )

    if any(
        token in lowered for token in ("quota", "insufficient_quota", "budget exhausted", "billing")
    ):
        return LLMErrorInfo(LLMErrorClass.QUOTA, retryable=False, message=message)

    if any(
        token in lowered
        for token in (
            "401",
            "403",
            "invalid api key",
            "authentication",
            "unauthorized",
            "forbidden",
        )
    ):
        return LLMErrorInfo(LLMErrorClass.AUTH, retryable=False, message=message)

    if any(
        token in lowered
        for token in (
            "unsupported model",
            "unknown model",
            "not found",
            "misconfig",
            "deployment does not exist",
        )
    ):
        return LLMErrorInfo(LLMErrorClass.MISCONFIGURATION, retryable=False, message=message)

    if any(
        token in lowered
        for token in ("schema", "validation", "invalid_request_error", "malformed", "bad request")
    ):
        return LLMErrorInfo(LLMErrorClass.VALIDATION, retryable=False, message=message)

    if any(
        token in lowered
        for token in (
            "500",
            "502",
            "503",
            "504",
            "server error",
            "service unavailable",
            "overloaded",
        )
    ):
        return LLMErrorInfo(LLMErrorClass.UPSTREAM, retryable=True, message=message)

    if any(token in lowered for token in ("timeout", "timed out", "deadline exceeded")):
        return LLMErrorInfo(LLMErrorClass.TIMEOUT, retryable=True, message=message)

    if any(
        token in lowered
        for token in (
            "connection reset",
            "connection aborted",
            "connection refused",
            "temporarily unavailable",
            "temporary failure",
            "dns",
            "socket",
            "network",
        )
    ) or any(token in type_name for token in ("connection", "network", "transport")):
        return LLMErrorInfo(LLMErrorClass.NETWORK, retryable=True, message=message)

    return LLMErrorInfo(LLMErrorClass.UNKNOWN, retryable=False, message=message)


def is_retryable_exception(exc: BaseException) -> bool:
    """Return True only for transient, retry-safe LLM failures."""
    return classify_llm_error(exc).retryable
