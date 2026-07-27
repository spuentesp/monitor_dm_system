"""The single Embedder.

This module is the *only* place in the system that calls
``litellm.aembedding``. The pair registry pins the model + provider;
this class reads the api_key + base_url from the live ``llm_providers``
row whose role is 'embedding' and calls litellm.

Fail-loud: a provider error or empty response raises
:class:`EmbedderProviderError` — never fakes a vector. The only paths
that can recover are the caller's (decide to not embed, surface an
operational alert).
"""

from __future__ import annotations

import logging
from typing import Any

import litellm

from monitor_data.config import settings
from monitor_data.db.postgres import PostgresClient
from monitor_data.llm.provider_semaphore import get_provider_semaphore_registry

from .embedding_health import EmbeddingHealthChecker
from .errors import EmbedderProviderError
from .pairs import ModelPair

logger = logging.getLogger(__name__)


# Module-level cache: a process always uses one (pair, pg) combination —
# we avoid re-probing on every embed call. ``None`` until the first
# checker is built lazily from the resolved pair + live creds.
_health_checker: EmbeddingHealthChecker | None = None


def _get_health_checker(pair: ModelPair, base_url: str) -> EmbeddingHealthChecker:
    """Return a process-cached EmbeddingHealthChecker for the active pair.

    The checker is built lazily on first use and reused across calls so
    the per-process probe cost is one Ollama ``/api/show`` request plus
    one ``litellm.aembedding`` probe per ``cache_ttl_seconds`` window.
    """
    global _health_checker
    if _health_checker is None:
        _health_checker = EmbeddingHealthChecker(
            model=pair.embedding_model,
            provider=pair.embedding_provider,
            base_url=base_url,
            expected_dim=settings.embedding_dimension,
        )
    return _health_checker


def reset_embedding_health_checker() -> None:
    """Drop the cached checker (test seams; pair flips)."""
    global _health_checker
    _health_checker = None


class Embedder:
    """The single embedding client for the retrieval layer.

    The constructor takes the active ``ModelPair`` + a Postgres client;
    the pair pins ``embedding_model`` + ``embedding_provider``, and the
    live ``llm_providers`` row for role='embedding' provides the
    ``api_key`` and ``base_url`` (which the pair deliberately does not
    store — credentials are env-managed).
    """

    def __init__(
        self,
        pair: ModelPair,
        pg: PostgresClient | None = None,
        *,
        preflight_enabled: bool = True,
    ) -> None:
        self._pair = pair
        self._pg = pg
        # ``preflight_enabled`` lets hermetic unit tests bypass the live
        # Ollama registry probe. Production paths leave it True — the
        # whole point of this class is fail-loud at the 0th embed call.
        self._preflight_enabled = preflight_enabled

    async def _client(self) -> PostgresClient:
        if self._pg is not None:
            return self._pg
        return PostgresClient()

    async def _live_creds(self) -> tuple[str, str]:
        """Read the api_key + base_url for the pair's embedding role
        from the live ``llm_providers`` row.

        The pair contract ensures this row exists; if it doesn't, we
        fail loud with a clear message.
        """
        client = await self._client()
        try:
            row = await client.provider_get_by_role("embedding")
        finally:
            if self._pg is None:
                await client.close()
        if row is None:
            raise EmbedderProviderError(
                f"no llm_providers row for role='embedding' — the pair "
                f"requires one (pair.embedding_model={self._pair.embedding_model!r}, "
                f"pair.embedding_provider={self._pair.embedding_provider!r})."
            )
        if row.get("model") != self._pair.embedding_model:
            raise EmbedderProviderError(
                f"live llm_providers role='embedding' model={row.get('model')!r} "
                f"does not match active pair.embedding_model="
                f"{self._pair.embedding_model!r}. The pair contract "
                f"was broken — the live row was changed without "
                f"updating the pair."
            )
        if row.get("provider") != self._pair.embedding_provider:
            raise EmbedderProviderError(
                f"live llm_providers role='embedding' provider="
                f"{row.get('provider')!r} does not match active pair."
                f"embedding_provider={self._pair.embedding_provider!r}."
            )
        return row.get("api_key", "") or "", row.get("base_url", "") or ""

    async def _build_kwargs(self, inputs: list[str]) -> dict[str, Any]:
        api_key, base_url = await self._live_creds()
        # litellm needs a `<provider>/<model>` qualified model name when the
        # endpoint is not OpenAI/Anthropic.  The pair only stores the bare
        # model, so prepend the ollama prefix here when the live provider
        # is ollama.
        model_name = self._pair.embedding_model
        if self._pair.embedding_provider == "ollama" and "/" not in model_name:
            model_name = f"ollama/{model_name}"
        kwargs: dict[str, Any] = {
            "model": model_name,
            "input": inputs,
        }
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["api_base"] = base_url
        return kwargs

    async def embed(self, text: str) -> list[float]:
        """Embed a single text. Fail-loud on provider error or empty response."""
        await self._preflight()
        kwargs = await self._build_kwargs([text])
        sem = get_provider_semaphore_registry().get(self._pair.embedding_provider)
        async with sem:
            try:
                resp = await litellm.aembedding(**kwargs)
            except Exception as exc:
                raise EmbedderProviderError(
                    f"litellm.aembedding failed for {self._pair.embedding_model!r}: {exc}"
                ) from exc
        data = resp.data or []
        if not data or not (data[0].get("embedding") or []):
            raise EmbedderProviderError(f"embedding model {self._pair.embedding_model!r} returned an empty vector.")
        return list(data[0]["embedding"])

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Fail-loud on provider error or empty response."""
        if not texts:
            return []
        await self._preflight()
        kwargs = await self._build_kwargs(texts)
        sem = get_provider_semaphore_registry().get(self._pair.embedding_provider)
        async with sem:
            try:
                resp = await litellm.aembedding(**kwargs)
            except Exception as exc:
                raise EmbedderProviderError(
                    f"litellm.aembedding failed for {self._pair.embedding_model!r}: {exc}"
                ) from exc
        out: list[list[float]] = []
        for i, item in enumerate(resp.data or []):
            vec = item.get("embedding") or []
            if not vec:
                raise EmbedderProviderError(
                    f"embedding model {self._pair.embedding_model!r} returned an empty vector at index {i}."
                )
            out.append(list(vec))
        return out

    async def _preflight(self) -> None:
        """Verify the embedding model is live before the real call.

        Runs once per process (cached at module level). On miss, raises
        :class:`EmbeddingModelMissingError` so the ingest pipeline can
        mark the job ``failed`` with ``last_error.category=
        embedding_preflight_failed`` at the 0th embed instead of timing
        out at chunk 120.
        """
        if not self._preflight_enabled:
            return
        try:
            api_key, base_url = await self._live_creds()
        except EmbedderProviderError:
            # Pair/credential drift is already specific — don't mask it.
            raise
        checker = _get_health_checker(self._pair, base_url)
        await checker.assert_live()


__all__ = ["Embedder"]
