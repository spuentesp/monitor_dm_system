"""The single PairLLM.

This module is the *only* place in the retrieval layer that calls
``litellm.acompletion``. The pair registry pins the chat-side models
(``chat_model`` for the GM, ``hyde_model`` for HyDE rewrites,
``rerank_model`` for the rerank step) + their providers; this class
reads api_key + base_url from the live ``llm_providers`` rows
(role-keyed) and dispatches.

Fail-loud: a provider error raises :class:`PairLLMProviderError`. The
retrieval layer's callers (HyDE / rerank helpers) may choose to
catch and fall back to plain vector order — that's a caller choice,
not a ``PairLLM`` choice.
"""

from __future__ import annotations

import logging
from typing import Any

import litellm

from monitor_data.db.postgres import PostgresClient

from .errors import PairLLMProviderError
from .pairs import ModelPair

logger = logging.getLogger(__name__)


# Which pair field maps to which llm_providers role.
_ROLE_FOR = {
    "chat": "chat",
    "hyde": None,  # uses the pair's hyde_role
    "rerank": None,  # uses the pair's rerank_role
}


def _litellm_model_string(model: str, provider: str) -> str:
    """Build the model string litellm needs to actually route the call.

    ``llm_providers`` rows for chat-side roles store the bare model
    name (e.g. ``qwen2.5:latest``) and rely on ``base_url`` to reach an
    OpenAI-compatible endpoint — litellm needs an explicit provider
    prefix to route correctly, it can't infer one from a bare name.
    Mirrors the convention already used for chat resolution elsewhere
    in the system (``dspy_runtime._model_string_for_dspy``): Anthropic
    and MiniMax (Anthropic-compatible endpoint) get an ``anthropic/``
    prefix; anything already prefixed is passed through; everything
    else is assumed OpenAI-compatible.
    """
    if provider in ("anthropic", "minimax"):
        return model if model.startswith("anthropic/") else f"anthropic/{model}"
    if "/" in model:
        return model
    return f"openai/{model}"


class PairLLM:
    """Single client for the retrieval layer's chat-side calls (HyDE
    rewrite, rerank prompt). The active pair pins which (model,
    provider, role) tuple to use; the live ``llm_providers`` row for
    that role provides the credentials.
    """

    def __init__(self, pair: ModelPair, pg: PostgresClient | None = None) -> None:
        self._pair = pair
        self._pg = pg

    async def _client(self) -> PostgresClient:
        if self._pg is not None:
            return self._pg
        return PostgresClient()

    async def _resolve(self, component: str) -> tuple[str, str, str, str, str]:
        """Return ``(role, model, provider, api_key, base_url)`` for a
        retrieval component (one of 'chat', 'hyde', 'rerank').

        Fails loud with a clear message if the live row is missing or
        doesn't match the pair.
        """
        if component == "chat":
            role = self._pair.chat_role
            want_model = self._pair.chat_model
            want_provider = self._pair.chat_provider
        elif component == "hyde":
            role = self._pair.hyde_role
            want_model = self._pair.hyde_model
            want_provider = self._pair.hyde_provider
        elif component == "rerank":
            role = self._pair.rerank_role
            want_model = self._pair.rerank_model
            want_provider = self._pair.rerank_provider
        else:
            raise PairLLMProviderError(f"unknown PairLLM component: {component!r}")

        client = await self._client()
        try:
            row = await client.provider_get_by_role(role)
        finally:
            if self._pg is None:
                await client.close()
        if row is None:
            raise PairLLMProviderError(
                f"no llm_providers row for role={role!r} — the pair "
                f"requires one (pair.{component}_model={want_model!r}, "
                f"pair.{component}_provider={want_provider!r})."
            )
        if row.get("model") != want_model:
            raise PairLLMProviderError(
                f"live llm_providers role={role!r} model={row.get('model')!r} "
                f"does not match active pair.{component}_model="
                f"{want_model!r}. The pair contract was broken."
            )
        if row.get("provider") != want_provider:
            raise PairLLMProviderError(
                f"live llm_providers role={role!r} provider="
                f"{row.get('provider')!r} does not match active pair."
                f"{component}_provider={want_provider!r}."
            )
        return (
            role,
            want_model,
            want_provider,
            row.get("api_key", "") or "",
            row.get("base_url", "") or "",
        )

    async def acompletion(
        self,
        component: str,
        prompt: str,
        *,
        max_tokens: int = 256,
        temperature: float = 0.0,
    ) -> str:
        """Run an ``acompletion`` using the (model, provider, role) the
        pair pins for ``component``. Returns the response text.
        Fails loud on provider errors.
        """
        _, model, provider, api_key, base_url = await self._resolve(component)
        litellm_model = _litellm_model_string(model, provider)
        kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if api_key:
            kwargs["api_key"] = api_key
        elif provider not in ("anthropic", "minimax"):
            # litellm's OpenAI-compatible path refuses to call without *some*
            # api_key, even against a local/no-auth endpoint. Same convention
            # as dspy_runtime._resolve_client for unauthenticated local models.
            kwargs["api_key"] = "not-needed"
        if base_url:
            kwargs["api_base"] = base_url
        try:
            resp = await litellm.acompletion(**kwargs)
        except Exception as exc:
            raise PairLLMProviderError(
                f"litellm.acompletion failed for {litellm_model!r} (component={component!r}): {exc}"
            ) from exc
        if not resp.choices or not resp.choices[0].message.content:
            raise PairLLMProviderError(f"PairLLM({component!r}) got empty response from {model!r}.")
        return str(resp.choices[0].message.content).strip()


__all__ = ["PairLLM"]
