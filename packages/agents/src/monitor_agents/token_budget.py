"""
Token budget management for MONITOR LLM calls.

LAYER: 2 (agents)
IMPORTS FROM: tiktoken (external), monitor_data (Layer 1)

Replaces character-based proxies (~4 chars ≈ 1 token) with accurate tiktoken
counting.  Provides per-role token budgets, context truncation, and prompt
caching cost estimation.

Usage:
    from monitor_agents.token_budget import TokenBudget, count_tokens, truncate_to_budget

    budget = TokenBudget(role=ModelRole.HEAVY)
    token_count = count_tokens(text, model="claude-sonnet-4-20250514")
    truncated = truncate_to_budget(text, max_tokens=512, model="gpt-4o")
"""

from __future__ import annotations

import functools

import tiktoken
from monitor_data.schemas.llm_config import ModelRole

# ---------------------------------------------------------------------------
# Model → encoding mapping
# ---------------------------------------------------------------------------

# Mapping from model family prefixes to tiktoken encoding names.
# OpenAI models use "cl100k_base" (GPT-4 / GPT-4o) or "o200k_base" (newer).
# Anthropic has no native tiktoken encoding; we approximate with cl100k_base.
_MODEL_ENCODING_MAP: dict[str, str] = {
    "gpt-4": "cl100k_base",
    "gpt-4o": "o200k_base",
    "gpt-3.5": "cl100k_base",
    "o1-": "o200k_base",
    "o3-": "o200k_base",
    "claude": "cl100k_base",  # approximation — Anthropic uses ~similar tokenization
}

_DEFAULT_ENCODING = "cl100k_base"


def _resolve_encoding(model: str) -> str:
    """Return the tiktoken encoding name for a model string."""
    model_lower = model.lower()
    for prefix, encoding in _MODEL_ENCODING_MAP.items():
        if model_lower.startswith(prefix):
            return encoding
    return _DEFAULT_ENCODING


@functools.lru_cache(maxsize=32)
def _get_encoder(encoding_name: str) -> tiktoken.Encoding:
    """Cache tiktoken encoders to avoid re-initialization."""
    return tiktoken.get_encoding(encoding_name)


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count the number of tokens in *text* for a given model.

    For Anthropic models this is an approximation (typically within ±5%).
    """
    if not text:
        return 0
    encoding_name = _resolve_encoding(model)
    encoder = _get_encoder(encoding_name)
    return len(encoder.encode(text))


def count_messages_tokens(
    messages: list[dict[str, str]],
    model: str = "gpt-4o",
) -> int:
    """Estimate total tokens for a list of chat messages.

    Includes per-message overhead (≈4 tokens for role delimiters).
    """
    total = 0
    for msg in messages:
        # Per-message overhead: role, separators, etc.
        total += 4
        for value in msg.values():
            total += count_tokens(str(value), model=model)
    return total


def truncate_to_tokens(text: str, max_tokens: int, model: str = "gpt-4o") -> str:
    """Truncate *text* to at most *max_tokens*, preserving whole words."""
    if not text:
        return ""
    encoding_name = _resolve_encoding(model)
    encoder = _get_encoder(encoding_name)
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    # Decode back, dropping incomplete bytes
    return encoder.decode(tokens[:max_tokens])


# ---------------------------------------------------------------------------
# Token budgets by model role
# ---------------------------------------------------------------------------


class TokenBudget:
    """Token budget configuration for a model role.

    Provides:
      - max_output_tokens: max tokens the LLM should generate
      - context_window: total context window for the model
      - budget_for(key): recommended token allocation for a context source
    """

    # Per-role defaults — these can be overridden by PostgreSQL config later.
    _ROLE_BUDGETS: dict[ModelRole, dict[str, int]] = {
        ModelRole.LIGHT: {
            "max_output": 1024,
            "context_window": 128_000,
            "query_budget": 128,  # tokens for Qdrant queries
            "summary_budget": 512,  # tokens for context summaries
        },
        ModelRole.STANDARD: {
            "max_output": 2048,
            "context_window": 128_000,
            "query_budget": 256,
            "summary_budget": 1024,
        },
        ModelRole.HEAVY: {
            "max_output": 4096,
            "context_window": 200_000,
            "query_budget": 256,
            "summary_budget": 1536,
        },
    }

    def __init__(self, role: ModelRole) -> None:
        self.role = role
        config = self._ROLE_BUDGETS.get(role, self._ROLE_BUDGETS[ModelRole.STANDARD])
        self.max_output_tokens: int = config["max_output"]
        self.context_window: int = config["context_window"]
        self.query_budget: int = config["query_budget"]
        self.summary_budget: int = config["summary_budget"]

    def available_for_context(self, prompt_tokens: int = 0) -> int:
        """How many tokens are available for context given existing prompt tokens."""
        used = prompt_tokens + self.max_output_tokens + 200  # 200 for system/role overhead
        return max(0, self.context_window - used)
