"""
Embeddings client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (litellm, tenacity) + monitor_data internals
CALLED BY: qdrant_tools.py, ingest_tools.py (via MCP tools)

Provider-agnostic embedding generation via LiteLLM.  The embedding provider is
resolved from PostgreSQL (``role = 'embedding'`` in ``llm_providers``), falling
back to the ``EMBEDDING_MODEL`` env var and then ``text-embedding-3-small``.

Usage:
    from monitor_data.db.embeddings import embed_text, embed_batch

    vector = await embed_text("The hero enters the tavern.")
    vectors = await embed_batch(["text a", "text b"])
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Any, List, Optional

import litellm
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from monitor_data.config import settings

logger = logging.getLogger(__name__)
_LOCAL_EMBEDDING_DIMENSION = settings.embedding_dimension


# ---------------------------------------------------------------------------
# Embedding provider resolution from PostgreSQL
# ---------------------------------------------------------------------------


@dataclass
class _EmbeddingConfig:
    """Cached embedding provider config resolved from the DB."""

    model: str
    api_key: str = ""
    provider_type: str = ""
    base_url: str = ""


_cached_config: Optional[_EmbeddingConfig] = None


async def _resolve_embedding_config() -> _EmbeddingConfig:
    """
    Resolve the embedding model + API key from PostgreSQL ``llm_providers``
    where ``role = 'embedding'``.

    Falls back to ``EMBEDDING_MODEL`` env var / settings when no DB provider
    is configured.  The result is cached for the process lifetime — restart
    the backend to pick up changes (same behaviour as the LLM registry).
    """
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    # Try PostgreSQL first
    try:
        from monitor_data.db.postgres import PostgresClient

        pg = PostgresClient()
        await pg.connect()
        row = await pg.provider_get_by_role("embedding")
        if row and row.get("model"):
            api_key = row.get("api_key", "")
            # Resolve API key from env fallbacks when DB key is empty
            if not api_key:
                provider = row.get("provider", "")
                env_maps = {
                    "openai": ["OPENAI_API_KEY"],
                    "google_ai_studio": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
                    "github_models": ["GITHUB_MODELS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"],
                    "groq": ["GROQ_API_KEY"],
                    "openrouter": ["OPENROUTER_API_KEY"],
                }
                for env_var in env_maps.get(provider, []):
                    api_key = os.getenv(env_var, "").strip()
                    if api_key:
                        break

            from monitor_data.config import normalize_local_base_url

            _cached_config = _EmbeddingConfig(
                model=row["model"],
                api_key=api_key,
                provider_type=row.get("provider", ""),
                base_url=normalize_local_base_url(row.get("base_url", "") or "") or "",
            )
            logger.info(
                "Embedding provider resolved from DB: model=%s provider=%s",
                _cached_config.model,
                _cached_config.provider_type,
            )
            return _cached_config
    except Exception as exc:
        logger.debug("Could not resolve embedding provider from DB: %s", exc)

    # Fallback to env-var / settings default
    _cached_config = _EmbeddingConfig(
        model=settings.embedding_model,
        api_key=settings.openai_api_key or "",
    )
    return _cached_config


def clear_embedding_cache() -> None:
    """Reset the cached embedding config — forces re-resolution on next call."""
    global _cached_config
    _cached_config = None


def _should_skip_remote(config: _EmbeddingConfig) -> bool:
    """Return True when the resolved config clearly cannot reach a remote API."""
    if config.api_key:
        return False
    model = config.model.strip().lower()
    # OpenAI embedding models need an API key
    if model.startswith(("text-embedding-", "openai/", "azure/")):
        return True
    return False


def _local_embed_text(text: str, dimensions: int = _LOCAL_EMBEDDING_DIMENSION) -> List[float]:
    """Create a deterministic local fallback embedding with the Qdrant-sized shape."""
    normalized = text.strip().lower()
    tokens = re.findall(r"[\w']+", normalized) or [normalized or "<empty>"]

    vector = [0.0] * dimensions
    for token_index, token in enumerate(tokens):
        digest = hashlib.sha256(f"{token_index}:{token}".encode("utf-8")).digest()
        for offset in range(0, len(digest), 4):
            chunk = digest[offset : offset + 4]
            bucket = int.from_bytes(chunk, "big", signed=False) % dimensions
            sign = 1.0 if chunk[0] % 2 == 0 else -1.0
            weight = 1.0 + (min(len(token), 32) / 32.0)
            vector[bucket] += sign * weight

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        vector[0] = 1.0
        magnitude = 1.0

    return [value / magnitude for value in vector]


def _local_embed_batch(texts: List[str]) -> List[List[float]]:
    """Create fallback embeddings for a batch of texts."""
    return [_local_embed_text(text) for text in texts]


def _ensure_vectors(texts: List[str], vectors: List[List[float]], model: str) -> List[List[float]]:
    """Guarantee one non-empty vector per input text (T-054).

    Remote providers occasionally return fewer/empty entries; Qdrant rejects
    zero-dimension vectors and the whole ingestion dies. Any hole is filled
    with the deterministic local embedding for that text.
    """
    repaired: List[List[float]] = []
    holes = 0
    for i, text in enumerate(texts):
        vec = vectors[i] if i < len(vectors) else None
        if not vec:
            vec = _local_embed_text(text)
            holes += 1
        repaired.append(vec)
    if holes:
        logger.warning(
            "Embedding model '%s' returned %d empty/missing vector(s); filled with local fallback.",
            model,
            holes,
        )
    return repaired


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

_LLM_RETRY: dict[str, Any] = dict(
    stop=stop_after_attempt(settings.llm_retry_attempts),
    wait=wait_exponential(
        multiplier=1,
        min=settings.llm_retry_min_wait,
        max=settings.llm_retry_max_wait,
    ),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)


@retry(**_LLM_RETRY)
async def embed_text(text: str, model: str | None = None) -> List[float]:
    """
    Generate a single embedding vector for ``text``.

    Resolves the embedding model and API key from the PostgreSQL
    ``llm_providers`` table (role='embedding'), falling back to the
    ``EMBEDDING_MODEL`` env var.

    Falls back to a deterministic local embedding when the configured remote
    provider is unavailable, which keeps ingestion and search operational in
    offline or partially configured dev environments.
    """
    config = await _resolve_embedding_config()
    effective_model = model or config.model

    if _should_skip_remote(config) and model is None:
        logger.warning(
            "Remote embedding model '%s' is configured without a usable API key; using local fallback.",
            effective_model,
        )
        return _local_embed_text(text)

    try:
        kwargs: dict[str, Any] = {"model": effective_model, "input": [text]}
        if model is None:
            if config.api_key:
                kwargs["api_key"] = config.api_key
            if config.base_url:
                kwargs["api_base"] = config.base_url
        response = await litellm.aembedding(**kwargs)
        vector: List[float] = response.data[0].get("embedding") or []
        if not vector:
            logger.warning(
                "Embedding model '%s' returned an empty vector; using local fallback.",
                effective_model,
            )
            return _local_embed_text(text)
        return vector
    except Exception as exc:
        logger.warning(
            "Embedding request failed for model '%s' (%s); using local fallback.",
            effective_model,
            exc,
        )
        return _local_embed_text(text)


@retry(**_LLM_RETRY)
async def embed_batch(texts: List[str], model: str | None = None) -> List[List[float]]:
    """
    Generate embedding vectors for a batch of texts in a single API call.

    Batching is cheaper and faster than calling ``embed_text`` in a loop.
    If the remote provider is unavailable, the batch is embedded locally with a
    deterministic fallback so ingest can continue.
    """
    if not texts:
        return []

    config = await _resolve_embedding_config()
    effective_model = model or config.model

    if _should_skip_remote(config) and model is None:
        logger.warning(
            "Remote embedding model '%s' is configured without a usable API key; using local fallback batch embeddings.",
            effective_model,
        )
        return _local_embed_batch(texts)

    try:
        kwargs: dict[str, Any] = {"model": effective_model, "input": texts}
        if model is None:
            if config.api_key:
                kwargs["api_key"] = config.api_key
            if config.base_url:
                kwargs["api_base"] = config.base_url
        response = await litellm.aembedding(**kwargs)
        # LiteLLM guarantees ordering matches input
        return _ensure_vectors(
            texts, [item.get("embedding") for item in response.data], effective_model
        )
    except Exception as exc:
        logger.warning(
            "Batch embedding request failed for model '%s' (%s); using local fallback.",
            effective_model,
            exc,
        )
        return _local_embed_batch(texts)
