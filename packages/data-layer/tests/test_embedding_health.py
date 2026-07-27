"""Embedding health-check pre-flight tests.

Verify :class:`EmbeddingHealthChecker` catches the failure modes that
bit the 2026-07-22 Fallout ingest:
  - Ollama registry 404 (model not pulled)
  - vector_dim mismatch vs. settings.embedding_dimension
  - provider unreachable

Run hermetically: every external surface is mocked.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor_data.retrieval.embedding_health import (
    EmbeddingHealthChecker,
    EmbeddingModelMissingError,
)


def _run(coro):
    """Drive the coroutine on a fresh loop so each test is isolated."""
    return asyncio.new_event_loop().run_until_complete(coro)


def _ok_show():
    """A 200 response from Ollama /api/show."""
    resp = MagicMock()
    resp.status_code = 200
    return resp


def _missing_show():
    """Ollama 404 — the model is not in the local registry."""
    resp = MagicMock()
    resp.status_code = 404
    resp.text = 'model "nomic-embed-text:latest" not found'
    return resp


def test_raises_embedding_model_missing_error_when_ollama_404s():
    """The most common production failure: operator pointed at a model
    they forgot to ``ollama pull``."""
    checker = EmbeddingHealthChecker(
        model="nomic-embed-text:latest",
        provider="ollama",
        base_url="http://localhost:11434",
        expected_dim=768,
    )

    async def _go():
        with patch.object(checker, "_probe_embed", return_value=(768, "ok")):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=_missing_show())
                with pytest.raises(EmbeddingModelMissingError) as excinfo:
                    await checker.assert_live()
                msg = str(excinfo.value)
                # Either phrase tells the operator the model is missing.
                assert ("ollama pull" in msg) or ("not found" in msg), msg

    _run(_go())


def test_marks_unhealthy_when_dim_mismatch():
    """A provider that loaded a model with a different vector dim is
    just as broken — the existing Qdrant collections would be poisoned
    with the wrong-shape vectors."""
    checker = EmbeddingHealthChecker(
        model="nomic-embed-text:latest",
        provider="ollama",
        base_url="http://localhost:11434",
        expected_dim=768,
    )

    async def _go():
        with patch.object(checker, "_probe_embed", return_value=(384, "wrong dim")):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=_ok_show())
                status = await checker.verify()
        assert status.healthy is False
        assert "768" in status.detail and "384" in status.detail

    _run(_go())


def test_marks_healthy_when_probe_succeeds():
    checker = EmbeddingHealthChecker(
        model="nomic-embed-text:latest",
        provider="ollama",
        base_url="http://localhost:11434",
        expected_dim=768,
    )

    async def _go():
        with patch.object(checker, "_probe_embed", return_value=(768, "embed ok")):
            with patch("httpx.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=_ok_show())
                status = await checker.verify()
        assert status.healthy is True
        assert status.vector_dim == 768

    _run(_go())


def test_invalidate_cache_forces_reprobe():
    """Used by the operator flow: ``ollama pull`` runs while the
    backend is up — the next probe must bypass the cache."""
    checker = EmbeddingHealthChecker(
        model="nomic-embed-text:latest",
        provider="ollama",
        base_url="http://localhost:11434",
        expected_dim=768,
        cache_ttl_seconds=999_999.0,  # effectively never expires
    )
    # Pre-populate cache with a successful probe.
    checker._cached = checker._cached or MagicMock(checked_at=10**12, healthy=True)

    # After invalidate, the very next verify() must probe again.
    checker.invalidate_cache()
    assert checker._force_next is True
    assert checker._cached is None


def test_unknown_provider_reported_as_unhealthy():
    checker = EmbeddingHealthChecker(
        model="anything",
        provider="gibberish-provider",
        base_url="",
        expected_dim=768,
    )

    async def _go():
        status = await checker.verify()
        assert status.healthy is False
        assert "gibberish-provider" in status.detail

    _run(_go())


def test_embedding_model_missing_error_independent_of_embedder_provider():
    """EmbeddingModelMissingError is NOT a subclass of EmbedderProviderError
    — a model-missing failure is operator-correctable and must surface as
    a different category from a transient provider outage. Callers that
    want both must catch them explicitly."""
    from monitor_data.retrieval.errors import EmbedderProviderError

    assert not issubclass(EmbeddingModelMissingError, EmbedderProviderError), (
        "EmbeddingModelMissingError must be independent — see Error class docstring."
    )
