"""
LLM Registry — resolves the right LLM client for each agent node or task role.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries (instructor, openai, anthropic)
CALLED BY: BaseAgent, individual agents

Design
------
Most providers expose an OpenAI-compatible REST endpoint; only Anthropic requires
its own SDK.  The registry hides this distinction behind a unified ``LLMClient``
interface so agents never branch on provider type.

Provider resolution order for ``for_node(node_name)``:
  1. Explicit row in ``llm_node_assignments`` for this node
  2. Provider marked ``is_default = TRUE`` in ``llm_providers``

Provider resolution order for ``for_role(role)``:
  1. First provider tagged with the requested role (default-preferred)
  2. Default provider as fallback

Usage::

    registry = LLMRegistry(postgres_client)

    # By agent node name:
    client = await registry.for_node("narrator")

    # By task-complexity tier:
    client = await registry.for_role(ModelRole.LIGHT)

    result = await client.create(MyOutputModel, messages=[...])

Clients are cached per lookup key so PostgreSQL is only hit once per registry
lifetime.  Call ``clear_cache()`` after re-configuring providers.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast

import instructor
from anthropic import AsyncAnthropic
from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.llm_config import (
    PROVIDER_BASE_URLS,
    EffectiveLLMConfig,
    LLMProviderType,
    ModelRole,
)
from openai import AsyncOpenAI
from pydantic import BaseModel

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# LLMClient — unified async interface
# =============================================================================


@dataclass
class LLMClient:
    """
    Unified async LLM client produced by ``LLMRegistry``.

    Wraps either an Anthropic or OpenAI-compatible backend behind a small
    provider-agnostic interface so agents and DSPy helpers can honor the saved
    runtime configuration from PostgreSQL.
    """

    model: str
    provider: LLMProviderType
    params: dict[str, Any]
    api_key: str = ""
    base_url: str | None = None
    prompt_version: str | None = None
    _instructor_client: Any = field(repr=False, default=None)
    _raw_client: Any = field(repr=False, default=None)

    async def create(
        self,
        response_model: type[T],
        messages: list[dict[str, Any]],
        **override_params: Any,
    ) -> T:
        """Call the underlying LLM and return a validated Pydantic instance."""
        params = {**self.params, **override_params}
        if self.provider in (LLMProviderType.ANTHROPIC, LLMProviderType.MINIMAX):
            return cast(
                T,
                await self._instructor_client.messages.create(
                    model=self.model,
                    response_model=response_model,
                    messages=messages,
                    **params,
                ),
            )
        return cast(
            T,
            await self._instructor_client.chat.completions.create(
                model=self.model,
                response_model=response_model,
                messages=messages,
                **params,
            ),
        )

    async def complete_text(
        self,
        messages: list[dict[str, Any]],
        **override_params: Any,
    ) -> str:
        """Run a plain text completion using the configured provider."""
        params = {**self.params, **override_params}
        if self.provider in (LLMProviderType.ANTHROPIC, LLMProviderType.MINIMAX):
            response = await self._raw_client.messages.create(
                model=self.model,
                messages=messages,
                **params,
            )
            content = getattr(response, "content", []) or []
            text_parts = [getattr(part, "text", "") for part in content if getattr(part, "text", "")]
            return "\n".join(text_parts).strip()

        response = await self._raw_client.chat.completions.create(
            model=self.model,
            messages=messages,
            **params,
        )
        message = response.choices[0].message if response.choices else None
        content = getattr(message, "content", "") if message else ""
        if isinstance(content, list):
            return "\n".join(str(part) for part in content).strip()
        return str(content or "").strip()

    async def stream_text(
        self,
        messages: list[dict[str, Any]],
        **override_params: Any,
    ) -> AsyncIterator[str]:
        """Yield text fragments as the provider streams them.

        Provider branching:
          - Anthropic / MiniMax: ``messages.stream(...)`` event stream;
            we yield ``.text`` from every event that carries it.
          - OpenAI and OpenAI-compatible: ``chat.completions.create(stream=True)``;
            we yield ``.choices[0].delta.content`` from each chunk.

        Provider-specific edge cases (tool calls, reasoning tokens, refusal
        events) are ignored — this is a plain-text stream surface.
        """
        params = {**self.params, **override_params}
        if self.provider in (LLMProviderType.ANTHROPIC, LLMProviderType.MINIMAX):

            async def _anthropic_stream() -> AsyncIterator[str]:
                async with self._raw_client.messages.stream(
                    model=self.model,
                    messages=messages,
                    **params,
                ) as event_stream:
                    async for event in event_stream:
                        text = getattr(event, "text", None)
                        if text:
                            yield text

            return _anthropic_stream()

        async def _openai_stream() -> AsyncIterator[str]:
            response = await self._raw_client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                **params,
            )
            async for chunk in response:
                if not getattr(chunk, "choices", None):
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                if piece:
                    yield piece

        return _openai_stream()


# =============================================================================
# LLMRegistry — multi-provider factory
# =============================================================================


class LLMRegistry:
    """
    Loads LLM provider configs from PostgreSQL and hands out ``LLMClient`` instances.

    Supported backends
    ------------------
    OpenAI-compatible (use ``openai.AsyncOpenAI`` with a custom ``base_url``):
      - ``openai``           — api.openai.com
      - ``github_models``    — models.inference.ai.azure.com
      - ``google_ai_studio`` — generativelanguage.googleapis.com (Gemini)
      - ``groq``             — api.groq.com
      - ``openrouter``       — openrouter.ai
      - ``ollama``           — local self-hosted (localhost:11434 by default)
      - ``azure_openai``     — custom base_url per Azure deployment
      - ``custom``           — any OpenAI-compatible endpoint in base_url

    Native SDK:
      - ``anthropic``        — Anthropic AsyncAnthropic SDK

    Configuration is stored in PostgreSQL:
      - ``llm_providers``         — credentials, model, base_url, role, params
      - ``llm_node_assignments``  — node → provider mapping with per-node overrides
    """

    def __init__(self, postgres: PostgresClient) -> None:
        self._postgres = postgres
        self._cache: dict[str, LLMClient] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def for_node(self, node_name: str) -> LLMClient:
        """
        Return the LLM client assigned to *node_name*.

        Falls back to the ``is_default`` provider when no explicit assignment
        exists for this node.

        Raises ``ValueError`` if neither an assignment nor a default exists.
        """
        if node_name not in self._cache:
            row = await self._postgres.effective_llm_for_node(node_name)
            config = self._row_to_config(row, node_name=node_name)
            self._cache[node_name] = self._build_client(config)
        return self._cache[node_name]

    async def for_role(self, role: ModelRole | str) -> LLMClient:
        """
        Return the best configured LLM client for a task-complexity tier.

        Preference order:
          1. connected + usable provider matching the requested role
          2. usable default provider
          3. any other connected usable provider
        """
        coerced = ModelRole.coerce(role)
        if coerced is None:
            raise ValueError(f"Invalid model role: {role!r}")
        role = coerced
        cache_key = f"__role__{role.value}"
        if cache_key not in self._cache:
            rows = await self._postgres.providers_list()
            ranked: list[tuple[int, dict[str, Any]]] = []

            for row in rows:
                row_role = row.get("role", ModelRole.STANDARD.value)
                status = (row.get("status") or "").lower()
                row["effective_params"] = row.get("model_params") or {}
                config = self._row_to_config(row)
                if not self._is_provider_usable(config, status):
                    continue

                if row_role == role.value and row.get("is_default") and status == "connected":
                    priority = 0  # role + default + connected — best possible match
                elif row_role == role.value and status == "connected":
                    priority = 1  # role + connected, not explicitly default
                elif row_role == role.value:
                    priority = 2  # role matches but not connected
                elif row.get("is_default") and status == "connected":
                    priority = 3  # fallback: default provider, not this role
                elif row.get("is_default"):
                    priority = 4
                elif status == "connected":
                    priority = 5
                else:
                    priority = 6
                ranked.append((priority, row))

            if not ranked:
                raise ValueError(f"No usable LLM provider configured for role '{role.value}'")

            ranked.sort(key=lambda item: item[0])
            config = self._row_to_config(ranked[0][1])
            self._cache[cache_key] = self._build_client(config)
        return self._cache[cache_key]

    async def for_node_or_role(self, node_name: str, role: ModelRole) -> LLMClient:
        """Use an explicit node assignment when present, otherwise fall back to the requested role."""
        assignment = await self._postgres.node_assignment_get(node_name)
        if assignment is not None:
            return await self.for_node(node_name)
        return await self.for_role(role)

    async def default_client(self) -> LLMClient | None:
        """Return the client for the is_default provider, or None if unset/unusable."""
        cache_key = "__default__"
        if cache_key not in self._cache:
            rows = await self._postgres.providers_list()
            default_row = next((r for r in rows if r.get("is_default")), None)
            if default_row is None:
                return None
            default_row["effective_params"] = default_row.get("model_params") or {}
            config = self._row_to_config(default_row)
            if not self._is_provider_usable(config, (default_row.get("status") or "").lower()):
                return None
            self._cache[cache_key] = self._build_client(config)
        return self._cache[cache_key]

    def clear_cache(self) -> None:
        """Evict all cached clients."""
        self._cache.clear()

    @staticmethod
    def _is_provider_usable(config: EffectiveLLMConfig, status: str = "") -> bool:
        """Return True when a provider is realistically callable."""
        if status == "error":
            return False
        if config.provider in {LLMProviderType.OLLAMA, LLMProviderType.CUSTOM}:
            return True
        if status == "connected":
            return True
        return bool(config.api_key)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_config(
        row: dict[str, Any],
        node_name: str | None = None,
    ) -> EffectiveLLMConfig:
        params = row.get("effective_params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except Exception:
                params = {}
        if not isinstance(params, dict):
            params = {}

        return EffectiveLLMConfig(
            id=row["id"],
            name=row["name"],
            provider=LLMProviderType(row["provider"]),
            model=row["model"],
            api_key=row.get("api_key", ""),
            base_url=row.get("base_url"),
            role=ModelRole(row.get("role", "standard")),
            effective_params=params,
            node_name=node_name,
            prompt_version=row.get("prompt_version"),
        )

    @staticmethod
    def _resolve_base_url(config: EffectiveLLMConfig) -> str | None:
        """
        Return the base URL to use for this provider.

        Prefers the explicitly stored ``base_url`` (required for Azure OpenAI,
        non-default Ollama ports, and CUSTOM providers).  Falls back to the
        well-known default for the provider type.

        localhost URLs are rewritten via MONITOR_LOCALHOST_REWRITE so rows
        pointing at host-running services (ollama, LM Studio) keep working
        when the backend itself runs inside Docker.
        """
        from monitor_data.config import normalize_local_base_url

        if config.base_url:
            return normalize_local_base_url(config.base_url)
        return PROVIDER_BASE_URLS.get(config.provider)

    @staticmethod
    def _resolve_api_key(config: EffectiveLLMConfig) -> str:
        """
        Resolve the API key for a provider.

        Priority:
          1. Explicit key stored in the DB row (non-empty)
          2. Well-known environment variables per provider type
             - github_models : GITHUB_MODELS_TOKEN → GITHUB_TOKEN → GH_TOKEN
             - google_ai_studio : GOOGLE_API_KEY
             - openai          : OPENAI_API_KEY
             - groq             : GROQ_API_KEY
             - openrouter       : OPENROUTER_API_KEY
             - anthropic        : ANTHROPIC_API_KEY
          3. Empty string / "not-needed" (e.g. local Ollama)

        Follows the same fallback chain as pii_chan's llm/client.py.
        """
        if config.api_key:
            return config.api_key

        env_lookups: dict[LLMProviderType, list[str]] = {
            LLMProviderType.GITHUB_MODELS: [
                "GITHUB_MODELS_TOKEN",
                "GITHUB_TOKEN",
                "GH_TOKEN",
            ],
            LLMProviderType.GOOGLE_AI_STUDIO: ["GOOGLE_API_KEY"],
            LLMProviderType.OPENAI: ["OPENAI_API_KEY"],
            LLMProviderType.GROQ: ["GROQ_API_KEY"],
            LLMProviderType.OPENROUTER: ["OPENROUTER_API_KEY"],
            LLMProviderType.Z_AI: ["Z_AI_API_KEY"],
            LLMProviderType.MINIMAX: ["MINIMAX_API_KEY"],
            LLMProviderType.ANTHROPIC: ["ANTHROPIC_API_KEY"],
            LLMProviderType.AZURE_OPENAI: ["AZURE_OPENAI_API_KEY"],
        }

        # MiniMax also checks for a custom base URL
        if config.provider == LLMProviderType.MINIMAX:
            base_url_override = os.getenv("MINIMAX_BASE_URL", "").strip()
            if base_url_override:
                config.base_url = base_url_override

        for env_var in env_lookups.get(config.provider, []):
            value = os.getenv(env_var, "").strip()
            if value:
                return value

        return ""

    def _build_client(self, config: EffectiveLLMConfig) -> LLMClient:
        """Instantiate and instructor-wrap the correct SDK client."""
        api_key = self._resolve_api_key(config)
        base_url = self._resolve_base_url(config)

        if config.provider == LLMProviderType.ANTHROPIC:
            raw: Any = AsyncAnthropic(api_key=api_key or None)
            instructor_client = instructor.from_anthropic(
                raw,
                mode=instructor.Mode.ANTHROPIC_TOOLS,
            )
        elif config.provider == LLMProviderType.MINIMAX:
            # MiniMax uses Anthropic SDK with a custom base URL (OpenAI-compatible endpoint)
            raw = AsyncAnthropic(api_key=api_key or None, base_url=base_url)
            instructor_client = instructor.from_anthropic(
                raw,
                mode=instructor.Mode.ANTHROPIC_TOOLS,
            )
        else:
            raw = AsyncOpenAI(
                api_key=api_key or "not-needed",
                base_url=base_url,
            )
            instructor_client = instructor.from_openai(raw)

        return LLMClient(
            model=config.model,
            provider=config.provider,
            params=config.effective_params,
            api_key=api_key,
            base_url=base_url,
            prompt_version=config.prompt_version,
            _instructor_client=instructor_client,
            _raw_client=raw,
        )
