"""
LLM Provider and Model Instance Configuration Schemas.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, enum)
CALLED BY: agents (Layer 2), UI backend

Defines the full type hierarchy for LLM configuration:

  LLMProviderType  — which backend (Anthropic, OpenAI, GitHub Models, …)
  ModelRole        — task-complexity tier (light / standard / heavy)
  LLMProviderConfig — one row of ``llm_providers`` (provider + single model)
  LLMNodeAssignment — which provider is assigned to an agent node
  EffectiveLLMConfig — merged config the registry turns into a live client

Design principle
----------------
Most providers expose an OpenAI-compatible REST endpoint; only Anthropic
requires its own SDK.  ``LLMProviderType.is_openai_compatible`` reflects this
so the registry can pick the right client class without extra branching.

Well-known base URLs are collected in ``PROVIDER_BASE_URLS``; providers that
need a custom endpoint (Azure OpenAI, Ollama on a non-default port, any
``CUSTOM`` provider) simply store the URL in ``LLMProviderConfig.base_url``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class LLMProviderType(StrEnum):
    """Supported LLM provider backends."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GITHUB_MODELS = "github_models"  # Azure-hosted, OpenAI-compatible
    GOOGLE_AI_STUDIO = "google_ai_studio"  # Gemini via OpenAI-compatible endpoint
    AZURE_OPENAI = "azure_openai"  # needs custom base_url per deployment
    GROQ = "groq"
    OLLAMA = "ollama"  # local self-hosted
    OPENROUTER = "openrouter"
    Z_AI = "z_ai"  # ZhipuAI (Z.AI) - OpenAI-compatible endpoint
    MINIMAX = "minimax"  # MiniMax AI - Anthropic-compatible endpoint with custom base_url
    CUSTOM = "custom"  # any OpenAI-compatible w/ custom base_url

    @property
    def is_openai_compatible(self) -> bool:
        """Return True for every provider that speaks the OpenAI chat API."""
        return self not in (LLMProviderType.ANTHROPIC, LLMProviderType.MINIMAX)


class ModelRole(StrEnum):
    """
    Task-complexity tier for a model instance.

    Agents pick the cheapest tier that satisfies the need:

    LIGHT    — fast/cheap: classification, summarisation, simple extraction,
               embedding re-ranking, health-checks.
    STANDARD — balanced: most agent tasks (context assembly, resolver,
               memory indexing, proposed-change evaluation).
    HEAVY    — most capable: narrative generation (Narrator), final canon
               evaluation (CanonKeeper), long-form story reasoning.
    EMBEDDING — vector embeddings.
    IMAGE    — image generation (portraits, scene illustrations); resolved
               by monitor_data.llm.image_providers, not by the chat registry.
    """

    LIGHT = "light"
    STANDARD = "standard"
    HEAVY = "heavy"
    EMBEDDING = "embedding"
    IMAGE = "image"

    @classmethod
    def coerce(cls, value: ModelRole | str | None) -> ModelRole | None:
        """Interpret a role that crossed a process boundary (DB row, env
        override, module attribute) as a ModelRole; None when absent or
        unrecognized. Raw strings must never reach ``.value`` call sites.
        """
        if value is None or isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return None


# =============================================================================
# WELL-KNOWN BASE URLS
# =============================================================================

# Default OpenAI-compatible base URLs per provider type.
# Anthropic is not included — it uses its own SDK, not the OpenAI client.
# Azure OpenAI, Ollama (non-default port), and CUSTOM providers must store
# their base URL in LLMProviderConfig.base_url.
PROVIDER_BASE_URLS: dict[str, str] = {
    LLMProviderType.OPENAI: "https://api.openai.com/v1",
    LLMProviderType.GITHUB_MODELS: "https://models.github.ai/inference",
    LLMProviderType.GOOGLE_AI_STUDIO: "https://generativelanguage.googleapis.com/v1beta/openai/",
    LLMProviderType.GROQ: "https://api.groq.com/openai/v1",
    LLMProviderType.OPENROUTER: "https://openrouter.ai/api/v1",
    LLMProviderType.OLLAMA: "http://localhost:11434/v1",
    LLMProviderType.Z_AI: "https://api.z.ai/api/coding/paas/v4",
    LLMProviderType.MINIMAX: "https://api.minimax.io/anthropic",  # Anthropic-compatible endpoint
}


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class ModelParams(BaseModel):
    """
    Sampling / generation parameters; all fields are optional.

    Stored as JSONB in ``llm_providers.model_params`` and
    ``llm_node_assignments.param_overrides``.  The registry merges
    provider-level params with per-node overrides at resolve time.

    Note: ``max_tokens`` is *required* by Anthropic — always include it when
    configuring an Anthropic provider.
    """

    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return only the fields that have been explicitly set."""
        return {k: v for k, v in self.model_dump().items() if v is not None}


class LLMProviderConfig(BaseModel):
    """
    One row from the ``llm_providers`` table.

    A provider config = a specific model on a specific backend backed by a
    single credential.  You can have multiple configs sharing the same
    provider type (e.g. two OpenAI keys for different orgs, or a cheap and
    an expensive Anthropic model on the same key).
    """

    id: str = Field(..., description="Unique slug, e.g. 'claude-haiku-light'")
    name: str = Field(..., description="Human-readable label")
    provider: LLMProviderType
    model: str = Field(..., description="Exact model identifier, e.g. 'gpt-4o-mini'")
    api_key: str = Field(default="", description="Bearer token / API key")
    base_url: str | None = Field(
        default=None,
        description="Override the well-known base URL (required for Azure OpenAI, local Ollama, CUSTOM)",
    )
    model_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Default sampling params (temperature, max_tokens, …)",
    )
    role: ModelRole = Field(
        default=ModelRole.STANDARD,
        description="Task-complexity tier this config is optimised for",
    )
    status: str = Field(default="unconfigured")
    latency_ms: int | None = None
    is_default: bool = False


class LLMNodeAssignment(BaseModel):
    """
    One row from ``llm_node_assignments``, optionally joined with provider data.

    Maps an agent node (``narrator``, ``canonkeeper``, …) to the provider
    profile it should use, with optional per-node parameter overrides.
    """

    node_name: str
    provider_id: str
    param_overrides: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

    # Populated when fetched with a JOIN on llm_providers:
    provider_name: str | None = None
    model: str | None = None
    provider: LLMProviderType | None = None
    role: ModelRole | None = None


class EffectiveLLMConfig(BaseModel):
    """
    Fully resolved LLM configuration for an agent node (or role fallback).

    Built by the registry from a ``postgres.effective_llm_for_node()`` row:
    provider-level ``model_params`` merged with per-node ``param_overrides``.
    This is the object the registry converts into a live client.
    """

    id: str = Field(..., description="provider_id from llm_providers")
    name: str = Field(..., description="Human-readable provider name")
    provider: LLMProviderType
    model: str
    api_key: str = ""
    base_url: str | None = None
    role: ModelRole = ModelRole.STANDARD
    effective_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Merged model_params + param_overrides, ready for the LLM call",
    )
    node_name: str | None = Field(
        default=None,
        description="None when resolved via role fallback rather than explicit assignment",
    )
    prompt_version: str | None = Field(
        default=None,
        description="Optional pinned prompt-template version (e.g. 'narrator-v3'). "
        "Drives cache-busting / A-B comparisons; passes through to the client.",
    )


class LLMTaskAttemptResponse(BaseModel):
    """Durable audit row for one provider call attempt."""

    id: str | None = None
    job_id: str | None = None
    source_id: str | None = None
    stage: str
    batch_id: str | None = None
    provider_id: str | None = None
    model: str | None = None
    role: str | None = None
    attempt_no: int
    max_attempts: int = 1
    status: str
    retryable: bool = False
    error_class: str | None = None
    error_message: str | None = None
    backoff_ms: int | None = None
    started_at: str | None = None
    ended_at: str | None = None
    request_id: str | None = None
    prompt_hash: str | None = None
    input_size: int | None = None
    output_size: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
