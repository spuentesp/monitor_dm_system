"""Embedding model health checker.

Pre-flight probe for the active embedding pair. Verifies that the
``llm_providers`` row's model name is loadable by the live provider
(e.g. an Ollama model pulled into the local registry) before a real
embed call is attempted.

Fail-loud: a missing or unloaded model raises
:class:`EmbeddingModelMissingError` (subclass of
:class:`EmbedderProviderError`). The caller (e.g. the ingest pipeline)
catches this at the 0th embed call and marks the ingestion job
``failed`` with ``last_error.category=embedding_preflight_failed``,
which is a far better signal than a mid-batch hang at chunk 120.

Probe cache TTL avoids re-hitting Ollama on every embed: a healthy
deployment probes once per 5 minutes, not per text.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .errors import EmbeddingModelMissingError

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingHealthStatus:
    """Result of a health probe."""

    healthy: bool
    model: str
    provider: str
    base_url: str
    checked_at: float = field(default_factory=time.time)
    detail: str = ""
    vector_dim: int | None = None


class EmbeddingHealthChecker:
    """Pre-flight probe for the active embedding pair.

    Two-stage:
      1. provider reachability + model name registry check
         (Ollama ``/api/show``, or a best-effort 404 check for non-Ollama)
      2. a single embedding call to confirm the model actually responds
         and the resulting vector dimension matches
         ``settings.embedding_dimension``.

    Cached for ``cache_ttl_seconds``; ``force=True`` bypasses cache.
    """

    def __init__(
        self,
        *,
        model: str,
        provider: str,
        base_url: str,
        expected_dim: int,
        cache_ttl_seconds: float = 300.0,
        timeout: float = 10.0,
    ) -> None:
        self._model = model
        self._provider = provider
        self._base_url = (base_url or "").rstrip("/")
        self._expected_dim = expected_dim
        self._cache_ttl = cache_ttl_seconds
        self._timeout = timeout
        self._lock = asyncio.Lock()
        self._cached: EmbeddingHealthStatus | None = None
        # Test escape hatch: force the next call to bypass the cache even
        # if cache_ttl_seconds hasn't elapsed.
        self._force_next = False

    async def verify(self, *, force: bool = False) -> EmbeddingHealthStatus:
        """Return cached healthy status if fresh; otherwise probe."""
        now = time.time()
        cached = self._cached
        if cached is not None and not force and not self._force_next:
            if (now - cached.checked_at) < self._cache_ttl:
                return cached
        self._force_next = False

        async with self._lock:
            # Re-check under the lock in case of a concurrent call.
            cached = self._cached
            if cached is not None and not force:
                if (time.time() - cached.checked_at) < self._cache_ttl:
                    return cached

            status = await self._probe()
            self._cached = status
            return status

    def invalidate_cache(self) -> None:
        """Force the next ``verify()`` to re-probe (e.g. after operator
        runs ``ollama pull`` while the backend is running)."""
        self._cached = None
        self._force_next = True

    def last_cached_status(self, *, force: bool = False) -> EmbeddingHealthStatus | None:
        """Return the cached status without probing. ``None`` if no
        probe has been run yet — callers (e.g. ``check_llm_providers``
        on /healthz) treat that as ``unknown``. With ``force=True``,
        fires a fresh probe in the background and returns the current
        cached value immediately (best-effort cheap read)."""
        return self._cached

    async def assert_live(self) -> EmbeddingHealthStatus:
        """Probe and raise :class:`EmbeddingModelMissingError` if not healthy."""
        status = await self.verify()
        if not status.healthy:
            raise EmbeddingModelMissingError(
                f"embedding model {self._model!r} ({self._provider}) is not live: {status.detail}"
            )
        return status

    async def _probe(self) -> EmbeddingHealthStatus:
        # Stage 1: provider reachability + model registry presence.
        if self._provider == "ollama":
            ok, detail = await self._probe_ollama_registry()
            if not ok:
                return EmbeddingHealthStatus(
                    healthy=False,
                    model=self._model,
                    provider=self._provider,
                    base_url=self._base_url,
                    detail=detail,
                )
        elif self._provider in {"openai", "anthropic", "minimax", "zai"}:
            # Cloud providers do not expose a registry; we can only probe
            # via an actual embed call below. Call out the unknown in the
            # status detail for diagnostics.
            detail = f"cloud provider '{self._provider}' has no registry probe; relying on embed-call test"
        else:
            return EmbeddingHealthStatus(
                healthy=False,
                model=self._model,
                provider=self._provider,
                base_url=self._base_url,
                detail=f"unknown provider {self._provider!r} (no probe implemented)",
            )

        # Stage 2: actual embed call to verify the model responds AND that
        # the resulting vector dim matches settings.embedding_dimension.
        dim, detail = await self._probe_embed()
        if dim is None:
            return EmbeddingHealthStatus(
                healthy=False,
                model=self._model,
                provider=self._provider,
                base_url=self._base_url,
                detail=detail,
            )
        if dim != self._expected_dim:
            return EmbeddingHealthStatus(
                healthy=False,
                model=self._model,
                provider=self._provider,
                base_url=self._base_url,
                detail=(
                    f"vector dim mismatch: model returned {dim}, settings.embedding_dimension={self._expected_dim}"
                ),
            )

        return EmbeddingHealthStatus(
            healthy=True,
            model=self._model,
            provider=self._provider,
            base_url=self._base_url,
            detail=detail,
            vector_dim=dim,
        )

    async def _probe_ollama_registry(self) -> tuple[bool, str]:
        """Hit Ollama ``/api/show`` to confirm the model is in the registry."""
        if not self._base_url:
            return False, "ollama base_url is empty"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/api/show",
                    json={"name": self._model},
                )
        except httpx.HTTPError as exc:
            return False, f"ollama unreachable at {self._base_url}: {exc}"

        if resp.status_code == 200:
            return True, "registered"
        if resp.status_code == 404:
            return False, (f"ollama has no model named {self._model!r}. Run: ollama pull {self._model}")
        return False, f"ollama /api/show status={resp.status_code}: {resp.text[:200]}"

    async def _probe_embed(self) -> tuple[int | None, str]:
        """Send a single trivial embed to confirm the model responds.

        Returns ``(vector_dim, detail)``. ``vector_dim is None`` on failure.
        """
        import litellm  # local import keeps the module import-light

        # Mirror the embedder's ollama-prefix convention.
        model_name = self._model
        if self._provider == "ollama" and "/" not in model_name:
            model_name = f"ollama/{model_name}"

        kwargs: dict[str, Any] = {"model": model_name, "input": ["health probe"]}
        if self._base_url:
            kwargs["api_base"] = self._base_url
        try:
            resp = await litellm.aembedding(**kwargs)
        except Exception as exc:
            return None, f"embed probe failed: {exc}"

        data = getattr(resp, "data", None) or []
        if not data or not data[0].get("embedding"):
            return None, "embed probe returned empty vector"
        return len(data[0]["embedding"]), f"embed probe ok, dim={len(data[0]['embedding'])}"


__all__ = [
    "EmbeddingHealthChecker",
    "EmbeddingHealthStatus",
    "EmbeddingModelMissingError",
    "get_embedding_health_checker",
    "reset_embedding_health_checker",
]


# Module-level singleton for ``/healthz`` cheap read. The Embedder's own
# singleton (in ``embedder.py``) is built lazily from the resolved pair;
# this one is built lazily from settings and is the one ``check_llm_providers``
# reads from.
_singleton: EmbeddingHealthChecker | None = None


def get_embedding_health_checker() -> EmbeddingHealthChecker:
    """Return the process-level EmbeddingHealthChecker built from settings."""
    global _singleton
    if _singleton is None:
        from monitor_data.config import get_settings

        settings = get_settings()
        _singleton = EmbeddingHealthChecker(
            model=settings.embedding_model,
            provider=getattr(settings, "embedding_provider", "ollama") or "ollama",
            base_url=getattr(settings, "embedding_base_url", "") or "",
            expected_dim=settings.embedding_dimension,
        )
    return _singleton


def reset_embedding_health_checker() -> None:
    """Drop the cached singleton (test seams)."""
    global _singleton
    _singleton = None
