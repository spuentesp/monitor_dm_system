"""Tests for LLMProviderUnavailable — the player-facing quota/rate-limit
error surfaced when the Narrator's LLM call fails for a provider-level
reason (not a transient parse hiccup).
"""

from __future__ import annotations

from monitor_agents.llm_errors import (
    LLMErrorClass,
    LLMErrorInfo,
    LLMProviderUnavailable,
    classify_llm_error,
)


def test_rate_limit_message_mentions_usage_limit() -> None:
    exc = LLMProviderUnavailable(
        LLMErrorInfo(LLMErrorClass.RATE_LIMIT, retryable=True, message="429 too many requests")
    )
    assert "usage limit" in exc.user_message.lower()
    assert "try again" in exc.user_message.lower()


def test_quota_message_mentions_usage_limit() -> None:
    exc = LLMProviderUnavailable(LLMErrorInfo(LLMErrorClass.QUOTA, retryable=False, message="quota exceeded"))
    assert "usage limit" in exc.user_message.lower()


def test_auth_message_is_distinct() -> None:
    exc = LLMProviderUnavailable(LLMErrorInfo(LLMErrorClass.AUTH, retryable=False, message="invalid api key"))
    assert "authentication" in exc.user_message.lower()


def test_misconfiguration_message_is_distinct() -> None:
    exc = LLMProviderUnavailable(LLMErrorInfo(LLMErrorClass.MISCONFIGURATION, retryable=False, message="unknown model"))
    assert "misconfigured" in exc.user_message.lower()


def test_unknown_class_gets_generic_message() -> None:
    exc = LLMProviderUnavailable(LLMErrorInfo(LLMErrorClass.UNKNOWN, retryable=False, message="???"))
    assert "temporarily unavailable" in exc.user_message.lower()


def test_str_of_exception_is_the_raw_message() -> None:
    exc = LLMProviderUnavailable(LLMErrorInfo(LLMErrorClass.RATE_LIMIT, retryable=True, message="raw provider text"))
    assert str(exc) == "raw provider text"


def test_classify_minimax_anthropic_shaped_rate_limit() -> None:
    """MiniMax's Anthropic-compatible endpoint reports rate limits with an
    'AnthropicException' wrapper and a 'Token Plan usage limit reached'
    message — confirm this classifies as RATE_LIMIT, not UNKNOWN, so the
    Narrator's retry loop treats it as a hard failure to surface, not a
    transient DSPy parse hiccup to silently retry."""
    exc = RuntimeError(
        'AnthropicException - {"type":"error","error":{"type":"rate_limit_error",'
        '"message":"Token Plan usage limit reached: Upgrade your Token Plan '
        'or purchase Credits for more usage. (2056)"}}'
    )
    info = classify_llm_error(exc)
    assert info.error_class == LLMErrorClass.RATE_LIMIT
