"""
LLM connections router — manage and test LLM provider configurations.

Provider configs are persisted in the PostgreSQL ``llm_providers`` table.
On the first request the router auto-seeds from environment variables when
the table is empty, so a fresh deployment only needs an .env file.

Provider type values follow the canonical names used by LLMProviderType:
  anthropic | openai | github_models | google_ai_studio | ollama | groq |
  openrouter | z_ai | minimax | custom
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import suppress
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from monitor_data.db.postgres import get_postgres_client
from pydantic import BaseModel


def _invalidate_llm_cache() -> None:
    """Best-effort purge of the background LLM registry cache.

    Called after any provider or node-assignment mutation so the next
    DSPy / agent call re-resolves providers from PostgreSQL.
    """
    with suppress(Exception):
        from monitor_agents.dspy_runtime import clear_bg_registry_cache

        clear_bg_registry_cache()


router = APIRouter()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LLMProvider(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    api_key_masked: str | None = None
    base_url: str | None = None
    status: str = "unconfigured"
    latency_ms: float | None = None
    is_default: bool = False
    role: str = "standard"


class LLMProviderCreate(BaseModel):
    name: str
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    is_default: bool = False
    role: str = "standard"


class LLMProviderUpdate(BaseModel):
    name: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    is_default: bool | None = None
    role: str | None = None


class TestResult(BaseModel):
    ok: bool
    latency_ms: float | None = None
    model_response: str | None = None
    error: str | None = None


class NodeAssignment(BaseModel):
    node_name: str
    provider_id: str
    param_overrides: dict[str, Any] = {}
    notes: str | None = None
    provider_name: str | None = None
    model: str | None = None
    provider: str | None = None


class NodeAssignmentUpdate(BaseModel):
    provider_id: str
    param_overrides: dict[str, Any] = {}
    notes: str | None = None


# Static fallback model lists (used when live discovery fails or no key set)
AVAILABLE_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "claude-opus-4-5",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5",
        "claude-3-7-sonnet-20251022",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "o1-preview",
        "o3-mini",
    ],
    "github_models": [
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "o4-mini",
        "o3",
        "claude-opus-4-5",
        "claude-sonnet-4-20250514",
        "claude-3-7-sonnet",
        "Llama-4-Scout-17B-16E-Instruct",
        "Llama-4-Maverick-17B-128E-Instruct",
        "Llama-3.3-70B-Instruct",
        "Mistral-large-2411",
        "Mistral-small-2503",
        "Phi-4",
        "Phi-4-mini",
        "DeepSeek-V3-0324",
        "DeepSeek-R1",
        "gemini-2.0-flash",
    ],
    "ollama": [
        "llama3.3",
        "mistral",
        "mixtral",
        "codellama",
        "gemma3",
    ],
    "google_ai_studio": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
        "gemini-1.5-pro",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "openrouter": [
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3-opus",
        "openai/gpt-4o",
        "openai/gpt-4-turbo",
        "google/gemini-2.0-flash",
        "meta-llama/llama-3.3-70b-instruct",
        "mistralai/mistral-large-2411",
    ],
    "z_ai": [
        "glm-5.1",
        "glm-5-flash",
        "glm-4-plus",
        "glm-4",
        "glm-4-flash",
        "glm-4-air",
        "glm-3-turbo",
    ],
    "minimax": [
        "MiniMax-M2.7",
        "M2-her",
        "MiniMax-Text-01",
        "abab6.5s-chat",
        "abab6.5g-chat",
        "abab5.5s-chat",
    ],
    "custom": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "claude-opus-4-5",
        "claude-sonnet-4-20250514",
        "gemini-2.0-flash",
    ],
}


def _discover_ollama_model_sync(base_url: str) -> str:
    """Query Ollama /api/tags and return the first installed model name.

    Falls back to ``qwen2.5:latest`` when Ollama is unreachable or empty.
    This is sync so it can be called from anywhere without async context.
    """
    try:
        import json as _json
        import urllib.request as _req

        ol_base = base_url.replace("/v1", "").rstrip("/")
        with _req.urlopen(f"{ol_base}/api/tags", timeout=5) as r:
            models = [
                m["name"]
                for m in _json.loads(r.read()).get("models", [])
                if m.get("name")
            ]
            if models:
                return models[0]
    except Exception:
        pass
    return "qwen2.5:latest"


def _resolve_model(env_var: str, existing: str, fallback: str) -> str:
    """Single source of truth for model name resolution.

    Priority: existing DB value → explicit env var → hardcoded fallback.
    DB wins so that UI edits survive backend restarts. The env var is only
    the bootstrap seed used when no DB row exists yet.
    """
    return existing or os.getenv(env_var, "").strip() or fallback


def _mask_key(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "••••••••"
    return key[:4] + "••••••••" + key[-4:]


def _to_response(p: dict) -> LLMProvider:
    return LLMProvider(
        id=p["id"],
        name=p["name"],
        provider=p["provider"],
        model=p["model"],
        api_key_masked=_mask_key(p.get("api_key")),
        base_url=p.get("base_url"),
        status=p.get("status", "unconfigured"),
        latency_ms=p.get("latency_ms"),
        is_default=p.get("is_default", False),
        role=p.get("role", "standard"),
    )


# ---------------------------------------------------------------------------
# Auto-sync built-in provider profiles from env / pii_chan defaults
# ---------------------------------------------------------------------------

_seeded: bool = False


async def _maybe_seed_from_env() -> None:
    """Ensure the built-in provider profiles exist in PostgreSQL.

    This persists the canonical saved profiles used by the UI. It intentionally
    mirrors the pii_chan setup:
      - GitHub Models
      - Google AI Studio
      - local Ollama / OpenAI-compatible
    plus cloud Anthropic/OpenAI rows when keys are present.
    """
    global _seeded
    if _seeded:
        return

    postgres = get_postgres_client()
    # Default to empty so a transient providers_list() failure can't leave this
    # unbound (the lookups below all depend on it) — seeding then proceeds from
    # env/defaults only instead of 500-ing the whole provider list.
    existing_rows: dict[str, Any] = {}
    with suppress(Exception):
        existing_rows = {row["id"]: row for row in await postgres.providers_list()}
    gh_token = (
        os.getenv("GITHUB_MODELS_TOKEN", "").strip()
        or os.getenv("GITHUB_TOKEN", "").strip()
        or os.getenv("GH_TOKEN", "").strip()
        or existing_rows.get("github-models-default", {}).get("api_key", "")
    )
    google_key = os.getenv("GOOGLE_API_KEY", "").strip() or existing_rows.get(
        "google-ai-studio-default", {}
    ).get("api_key", "")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or existing_rows.get(
        "anthropic-default", {}
    ).get("api_key", "")
    openai_key = os.getenv("OPENAI_API_KEY", "").strip() or existing_rows.get(
        "openai-default", {}
    ).get("api_key", "")

    has_existing_default = any(
        bool(row.get("is_default")) for row in existing_rows.values()
    )

    # Resolve model names: env var wins; existing DB value preserved if no env override;
    # Ollama falls back to live auto-discovery then a safe hardcoded default.
    # This ensures manual DB edits via the UI survive backend restarts.
    ol_base = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434").rstrip("/")
    _gh_model = _resolve_model(
        "GITHUB_MODELS_MODEL",
        existing_rows.get("github-models-default", {}).get("model", ""),
        "openai/gpt-4.1-mini",
    )
    _google_model = _resolve_model(
        "GOOGLE_MODEL",
        existing_rows.get("google-ai-studio-default", {}).get("model", ""),
        "gemini-2.5-flash",
    ).replace("models/", "")
    _ollama_model = _resolve_model(
        "OLLAMA_MODEL",
        existing_rows.get("ollama-local", {}).get("model", ""),
        _discover_ollama_model_sync(ol_base),
    )
    _anthropic_model = _resolve_model(
        "LLM_MODEL",
        existing_rows.get("anthropic-default", {}).get("model", ""),
        "claude-sonnet-4-20250514",
    )

    builtin_profiles: list[dict[str, Any]] = [
        {
            "id": "github-models-default",
            "name": existing_rows.get("github-models-default", {}).get(
                "name", "GitHub Models"
            ),
            "provider": "github_models",
            "model": _gh_model,
            "api_key": gh_token,
            "base_url": os.getenv(
                "GITHUB_MODELS_BASE_URL", "https://models.github.ai/inference"
            ),
            "model_params": {"temperature": 0.7, "max_tokens": 4096},
            "role": existing_rows.get("github-models-default", {}).get(
                "role", "standard"
            ),
            "status": existing_rows.get("github-models-default", {}).get(
                "status", "unconfigured"
            ),
            "latency_ms": existing_rows.get("github-models-default", {}).get(
                "latency_ms"
            ),
            "is_default": existing_rows.get("github-models-default", {}).get(
                "is_default", bool(gh_token) and not has_existing_default
            ),
        },
        {
            "id": "google-ai-studio-default",
            "name": existing_rows.get("google-ai-studio-default", {}).get(
                "name", "Google AI Studio"
            ),
            "provider": "google_ai_studio",
            "model": _google_model,
            "api_key": google_key,
            "base_url": None,
            "model_params": {"temperature": 0.7, "max_tokens": 8192},
            "role": existing_rows.get("google-ai-studio-default", {}).get(
                "role", "heavy"
            ),
            "status": existing_rows.get("google-ai-studio-default", {}).get(
                "status", "unconfigured"
            ),
            "latency_ms": existing_rows.get("google-ai-studio-default", {}).get(
                "latency_ms"
            ),
            "is_default": existing_rows.get("google-ai-studio-default", {}).get(
                "is_default", False
            ),
        },
        {
            "id": "ollama-local",
            "name": existing_rows.get("ollama-local", {}).get("name", "Ollama (local)"),
            "provider": "ollama",
            "model": _ollama_model,
            "api_key": "",
            "base_url": ol_base + "/v1",
            "model_params": {"temperature": 0.7, "max_tokens": 4096},
            "role": existing_rows.get("ollama-local", {}).get("role", "light"),
            "status": existing_rows.get("ollama-local", {}).get(
                "status", "unconfigured"
            ),
            "latency_ms": existing_rows.get("ollama-local", {}).get("latency_ms"),
            "is_default": existing_rows.get("ollama-local", {}).get(
                "is_default",
                not gh_token
                and not anthropic_key
                and not openai_key
                and not has_existing_default,
            ),
        },
    ]

    if anthropic_key or "anthropic-default" in existing_rows:
        builtin_profiles.append(
            {
                "id": "anthropic-default",
                "name": existing_rows.get("anthropic-default", {}).get(
                    "name", "Anthropic (Claude)"
                ),
                "provider": "anthropic",
                "model": _anthropic_model,
                "api_key": anthropic_key,
                "base_url": None,
                "model_params": {"temperature": 0.7, "max_tokens": 4096},
                "role": existing_rows.get("anthropic-default", {}).get("role", "heavy"),
                "status": existing_rows.get("anthropic-default", {}).get(
                    "status", "unconfigured"
                ),
                "latency_ms": existing_rows.get("anthropic-default", {}).get(
                    "latency_ms"
                ),
                "is_default": existing_rows.get("anthropic-default", {}).get(
                    "is_default", False
                ),
            }
        )

    if openai_key or "openai-default" in existing_rows:
        builtin_profiles.append(
            {
                "id": "openai-default",
                "name": existing_rows.get("openai-default", {}).get("name", "OpenAI"),
                "provider": "openai",
                "model": _resolve_model(
                    "OPENAI_MODEL",
                    existing_rows.get("openai-default", {}).get("model", ""),
                    "gpt-4o",
                ),
                "api_key": openai_key,
                "base_url": None,
                "model_params": {"temperature": 0.7, "max_tokens": 4096},
                "role": existing_rows.get("openai-default", {}).get("role", "standard"),
                "status": existing_rows.get("openai-default", {}).get(
                    "status", "unconfigured"
                ),
                "latency_ms": existing_rows.get("openai-default", {}).get("latency_ms"),
                "is_default": existing_rows.get("openai-default", {}).get(
                    "is_default", False
                ),
            }
        )

    minimax_key = (
        os.getenv("MINIMAX_TOKEN", "").strip()
        or os.getenv("MINIMAX_API_KEY", "").strip()
        or existing_rows.get("minimax-default", {}).get("api_key", "")
    )
    minimax_base = (
        os.getenv("MINIMAX_BASE_URL", "").strip()
        or existing_rows.get("minimax-default", {}).get("base_url", "")
        or "https://api.minimax.io/anthropic"
    )
    # ── MiniMax: light / standard / heavy ──
    if minimax_key or any(
        k in existing_rows for k in ("minimax-light", "minimax-her", "minimax-m27")
    ):
        # Light — fast, cheap
        builtin_profiles.append(
            {
                "id": "minimax-light",
                "name": existing_rows.get("minimax-light", {}).get(
                    "name", "MiniMax M2-her (Light)"
                ),
                "provider": "minimax",
                "model": _resolve_model(
                    "MINIMAX_LIGHT_MODEL",
                    existing_rows.get("minimax-light", {}).get("model", ""),
                    "M2-her",
                ),
                "api_key": minimax_key,
                "base_url": minimax_base,
                "model_params": {"temperature": 0.7, "max_tokens": 2048},
                "role": existing_rows.get("minimax-light", {}).get("role", "light"),
                "status": existing_rows.get("minimax-light", {}).get(
                    "status", "unconfigured"
                ),
                "latency_ms": existing_rows.get("minimax-light", {}).get("latency_ms"),
                "is_default": existing_rows.get("minimax-light", {}).get(
                    "is_default", False
                ),
            }
        )
        # Standard — roleplay-optimised, balanced
        builtin_profiles.append(
            {
                "id": "minimax-her",
                "name": existing_rows.get("minimax-her", {}).get(
                    "name", "MiniMax M2.7 (Standard)"
                ),
                "provider": "minimax",
                "model": _resolve_model(
                    "MINIMAX_HER_MODEL",
                    existing_rows.get("minimax-her", {}).get("model", ""),
                    "MiniMax-M2.7",
                ),
                "api_key": minimax_key,
                "base_url": minimax_base,
                "model_params": {"temperature": 1.0, "max_tokens": 4096, "top_p": 0.95},
                "role": existing_rows.get("minimax-her", {}).get("role", "standard"),
                "status": existing_rows.get("minimax-her", {}).get(
                    "status", "unconfigured"
                ),
                "latency_ms": existing_rows.get("minimax-her", {}).get("latency_ms"),
                "is_default": existing_rows.get("minimax-her", {}).get(
                    "is_default", False
                ),
            }
        )
        # Heavy — largest context, best quality
        builtin_profiles.append(
            {
                "id": "minimax-m27",
                "name": existing_rows.get("minimax-m27", {}).get(
                    "name", "MiniMax M2.7 (Heavy)"
                ),
                "provider": "minimax",
                "model": _resolve_model(
                    "MINIMAX_M27_MODEL",
                    existing_rows.get("minimax-m27", {}).get("model", ""),
                    "MiniMax-M2.7",
                ),
                "api_key": minimax_key,
                "base_url": minimax_base,
                "model_params": {"temperature": 0.7, "max_tokens": 8192},
                "role": existing_rows.get("minimax-m27", {}).get("role", "heavy"),
                "status": existing_rows.get("minimax-m27", {}).get(
                    "status", "unconfigured"
                ),
                "latency_ms": existing_rows.get("minimax-m27", {}).get("latency_ms"),
                "is_default": existing_rows.get("minimax-m27", {}).get(
                    "is_default", False
                ),
            }
        )

    # Remove legacy single-provider entry if it exists
    for legacy_id in ("minimax-default",):
        if legacy_id in existing_rows and "minimax-her" not in existing_rows:
            with suppress(Exception):
                await postgres.provider_delete(legacy_id)

    # ── Z.AI (ZhipuAI): light / standard / heavy ──
    zai_key = (
        os.getenv("Z_AI_TOKEN", "").strip()
        or os.getenv("Z_AI_API_KEY", "").strip()
        or existing_rows.get("zai-default", {}).get("api_key", "")
    )
    zai_base = (
        os.getenv("Z_AI_BASE_URL", "").strip()
        or existing_rows.get("zai-default", {}).get("base_url", "")
        or "https://api.z.ai/api/coding/paas/v4"
    )
    if zai_key or any(
        k in existing_rows for k in ("zai-light", "zai-standard", "zai-heavy")
    ):
        # Light — flash model, fastest
        builtin_profiles.append(
            {
                "id": "zai-light",
                "name": existing_rows.get("zai-light", {}).get(
                    "name", "Z.AI glm-z1-flash (Light)"
                ),
                "provider": "z_ai",
                "model": _resolve_model(
                    "Z_AI_LIGHT_MODEL",
                    existing_rows.get("zai-light", {}).get("model", ""),
                    "glm-z1-flash",
                ),
                "api_key": zai_key,
                "base_url": zai_base,
                "model_params": {"temperature": 0.6, "max_tokens": 2048},
                "role": existing_rows.get("zai-light", {}).get("role", "light"),
                "status": existing_rows.get("zai-light", {}).get(
                    "status", "unconfigured"
                ),
                "latency_ms": existing_rows.get("zai-light", {}).get("latency_ms"),
                "is_default": existing_rows.get("zai-light", {}).get(
                    "is_default", False
                ),
            }
        )
        # Standard — balanced
        builtin_profiles.append(
            {
                "id": "zai-standard",
                "name": existing_rows.get("zai-standard", {}).get(
                    "name", "Z.AI glm-4-flash (Standard)"
                ),
                "provider": "z_ai",
                "model": _resolve_model(
                    "Z_AI_STANDARD_MODEL",
                    existing_rows.get("zai-standard", {}).get("model", ""),
                    "glm-4-flash",
                ),
                "api_key": zai_key,
                "base_url": zai_base,
                "model_params": {"temperature": 0.7, "max_tokens": 4096},
                "role": existing_rows.get("zai-standard", {}).get("role", "standard"),
                "status": existing_rows.get("zai-standard", {}).get(
                    "status", "unconfigured"
                ),
                "latency_ms": existing_rows.get("zai-standard", {}).get("latency_ms"),
                "is_default": existing_rows.get("zai-standard", {}).get(
                    "is_default", False
                ),
            }
        )
        # Heavy — most capable
        builtin_profiles.append(
            {
                "id": "zai-heavy",
                "name": existing_rows.get("zai-heavy", {}).get(
                    "name", "Z.AI glm-4-plus (Heavy)"
                ),
                "provider": "z_ai",
                "model": _resolve_model(
                    "Z_AI_HEAVY_MODEL",
                    existing_rows.get("zai-heavy", {}).get("model", ""),
                    "glm-4-plus",
                ),
                "api_key": zai_key,
                "base_url": zai_base,
                "model_params": {"temperature": 0.7, "max_tokens": 8192},
                "role": existing_rows.get("zai-heavy", {}).get("role", "heavy"),
                "status": existing_rows.get("zai-heavy", {}).get(
                    "status", "unconfigured"
                ),
                "latency_ms": existing_rows.get("zai-heavy", {}).get("latency_ms"),
                "is_default": existing_rows.get("zai-heavy", {}).get(
                    "is_default", False
                ),
            }
        )

    # Remove legacy ZAI single-provider entry
    if "zai-default" in existing_rows and "zai-light" not in existing_rows:
        with suppress(Exception):
            await postgres.provider_delete("zai-default")

    for profile in builtin_profiles:
        with suppress(Exception):
            await postgres.provider_upsert(profile)
    # Mirror into the MONITOR settings store (used by legacy callers).
    with suppress(Exception):
        await postgres.config_set(
            "llm_provider", "github_models" if gh_token else "ollama"
        )
        await postgres.config_set(
            "llm_provider_order", "google_ai_studio,github_models,ollama"
        )
        await postgres.config_set("google_model", _google_model)
        await postgres.config_set("github_models_model", _gh_model)
        await postgres.config_set("openai_compatible_model", _ollama_model)
        await postgres.config_set("openai_compatible_base_url", ol_base + "/v1")

    _seeded = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=list[LLMProvider])
async def list_providers() -> list[LLMProvider]:
    await _maybe_seed_from_env()
    postgres = get_postgres_client()
    rows = await postgres.providers_list()
    return [_to_response(r) for r in rows]


@router.post("/providers", response_model=LLMProvider, status_code=201)
async def add_provider(body: LLMProviderCreate) -> LLMProvider:
    postgres = get_postgres_client()
    pid = str(uuid.uuid4())
    if body.is_default:
        # Clear is_default on all existing rows first
        existing = await postgres.providers_list()
        for p in existing:
            if p.get("is_default"):
                await postgres.provider_upsert({**p, "is_default": False})
    new_provider: dict[str, Any] = {
        "id": pid,
        "name": body.name,
        "provider": body.provider,
        "model": body.model,
        "api_key": body.api_key or "",
        "base_url": body.base_url,
        "model_params": {},
        "role": body.role,
        "status": "unconfigured",
        "latency_ms": None,
        "is_default": body.is_default,
    }
    await postgres.provider_upsert(new_provider)
    _invalidate_llm_cache()
    return _to_response(new_provider)


@router.put("/providers/{provider_id}", response_model=LLMProvider)
async def update_provider(provider_id: str, body: LLMProviderUpdate) -> LLMProvider:
    postgres = get_postgres_client()
    existing = await postgres.provider_get(provider_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Provider not found")
    update = body.model_dump(exclude_none=True)
    # An empty api_key from the form means "leave the saved key alone" —
    # merging "" used to silently destroy stored credentials (T-049).
    if not str(update.get("api_key") or "").strip():
        update.pop("api_key", None)
    if update.get("is_default"):
        await postgres.provider_set_default(provider_id)
        existing["is_default"] = True
        update.pop("is_default", None)
    merged = {**existing, **update}
    await postgres.provider_upsert(merged)
    _invalidate_llm_cache()
    return _to_response(merged)


@router.delete("/providers/{provider_id}", status_code=204)
async def delete_provider(provider_id: str) -> None:
    postgres = get_postgres_client()
    await postgres.provider_delete(provider_id)
    _invalidate_llm_cache()


class DuplicateProviderBody(BaseModel):
    """Optional overrides when duplicating an existing provider."""

    name: str | None = None
    model: str | None = None
    role: str | None = None


@router.post(
    "/providers/{provider_id}/duplicate", response_model=LLMProvider, status_code=201
)
async def duplicate_provider(
    provider_id: str, body: DuplicateProviderBody | None = None
) -> LLMProvider:
    """Duplicate an existing provider config, optionally changing name/model/role."""
    postgres = get_postgres_client()
    source = await postgres.provider_get(provider_id)
    if not source:
        raise HTTPException(status_code=404, detail="Provider not found")

    new_id = str(uuid.uuid4())
    role = body.role if body and body.role else source.get("role", "standard")
    model = body.model if body and body.model else source["model"]
    name = body.name if body and body.name else f"{source['name']} ({role})"

    new_provider: dict[str, Any] = {
        "id": new_id,
        "name": name,
        "provider": source["provider"],
        "model": model,
        "api_key": source.get("api_key", ""),
        "base_url": source.get("base_url"),
        "model_params": source.get("model_params", {}),
        "role": role,
        "status": "unconfigured",
        "latency_ms": None,
        "is_default": False,
    }
    await postgres.provider_upsert(new_provider)
    _invalidate_llm_cache()
    return _to_response(new_provider)


@router.get("/assignments", response_model=list[NodeAssignment])
async def list_node_assignments() -> list[NodeAssignment]:
    postgres = get_postgres_client()
    rows = await postgres.node_assignments_list()
    return [NodeAssignment(**row) for row in rows]


@router.put("/assignments/{node_name}", response_model=NodeAssignment)
async def upsert_node_assignment(
    node_name: str, body: NodeAssignmentUpdate
) -> NodeAssignment:
    postgres = get_postgres_client()
    await postgres.node_assignment_set(
        node_name=node_name,
        provider_id=body.provider_id,
        param_overrides=body.param_overrides,
        notes=body.notes,
    )
    row = await postgres.node_assignment_get(node_name)
    if not row:
        raise HTTPException(status_code=404, detail="Assignment not found after update")
    _invalidate_llm_cache()
    return NodeAssignment(**row)


@router.delete("/assignments/{node_name}", status_code=204)
async def delete_node_assignment(node_name: str) -> None:
    postgres = get_postgres_client()
    await postgres.node_assignment_delete(node_name)
    _invalidate_llm_cache()


@router.post("/providers/{provider_id}/test", response_model=TestResult)
async def test_provider(provider_id: str) -> TestResult:
    postgres = get_postgres_client()
    p = await postgres.provider_get(provider_id)
    if not p:
        raise HTTPException(status_code=404, detail="Provider not found")

    api_key = p.get("api_key") or ""
    provider = p["provider"]
    model = p["model"]
    base_url = p.get("base_url") or ""

    t0 = time.monotonic()
    try:
        if provider == "anthropic":
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(
                    ok=True,
                    latency_ms=latency,
                    model_response=resp.json()
                    .get("content", [{}])[0]
                    .get("text", "ok"),
                )

        elif provider == "openai":
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(ok=True, latency_ms=latency)

        elif provider == "github_models":
            inference_base = base_url or "https://models.github.ai/inference"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{inference_base.rstrip('/')}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(ok=True, latency_ms=latency)

        elif provider == "google_ai_studio":
            normalized_model = (
                model if model.startswith("models/") else f"models/{model}"
            )
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/{normalized_model}:generateContent?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json={"contents": [{"parts": [{"text": "ping"}]}]},
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(ok=True, latency_ms=latency)

        elif provider == "ollama":
            ol_base = (base_url or "http://localhost:11434/v1").replace("/v1", "")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{ol_base}/api/tags")
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000

                # Validate configured model exists; auto-correct to first installed model if not
                installed = [m["name"] for m in resp.json().get("models", [])]
                resolved_model = model
                if installed and model not in installed:
                    resolved_model = installed[0]
                    await postgres.provider_upsert(
                        {
                            **p,
                            "model": resolved_model,
                            "status": "connected",
                            "latency_ms": int(latency),
                        }
                    )
                else:
                    await postgres.provider_upsert(
                        {**p, "status": "connected", "latency_ms": int(latency)}
                    )

                return TestResult(
                    ok=True,
                    latency_ms=latency,
                    model_response=f"model={resolved_model}"
                    + (" (auto-corrected)" if resolved_model != model else ""),
                )

        elif provider == "minimax":
            # MiniMax uses Anthropic SDK with OpenAI-compatible endpoint
            minimax_base = (
                base_url
                or os.getenv("MINIMAX_BASE_URL", "").strip()
                or "https://api.minimax.chat/v1"
            )
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{minimax_base.rstrip('/')}/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(
                    ok=True,
                    latency_ms=latency,
                    model_response=resp.json()
                    .get("content", [{}])[0]
                    .get("text", "ok"),
                )

        elif provider == "z_ai":
            # Z.AI (ZhipuAI) uses OpenAI-compatible endpoint
            zai_base = base_url or "https://api.z.ai/api/coding/paas/v4"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{zai_base.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(ok=True, latency_ms=latency)

        elif provider == "groq":
            # Groq uses OpenAI-compatible endpoint
            groq_base = base_url or "https://api.groq.com/openai/v1"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{groq_base.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(ok=True, latency_ms=latency)

        elif provider == "openrouter":
            # OpenRouter uses OpenAI-compatible endpoint
            openrouter_base = base_url or "https://openrouter.ai/api/v1"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{openrouter_base.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(ok=True, latency_ms=latency)

        elif provider == "custom":
            if not base_url:
                return TestResult(
                    ok=False, error="base_url is required for custom provider"
                )
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 10,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )
                resp.raise_for_status()
                latency = (time.monotonic() - t0) * 1000
                await postgres.provider_upsert(
                    {**p, "status": "connected", "latency_ms": int(latency)}
                )
                return TestResult(ok=True, latency_ms=latency)

        else:
            return TestResult(ok=False, error=f"Test not implemented for {provider}")

    except Exception as exc:
        with suppress(Exception):
            await postgres.provider_upsert({**p, "status": "error", "latency_ms": None})
        return TestResult(ok=False, error=str(exc))
    finally:
        _invalidate_llm_cache()


@router.get("/models/{provider}", response_model=list[str])
async def list_models(provider: str) -> list[str]:
    """
    Return available models for a provider.

    Fetches live from the provider API when a key is stored in Postgres.
    Falls back to the static list on error or when no key is available.
    """
    postgres = get_postgres_client()
    # Find the first stored entry for this provider type
    rows = await postgres.providers_list()
    stored = next((r for r in rows if r["provider"] == provider), None)
    api_key = (stored or {}).get("api_key") or ""
    base_url = (stored or {}).get("base_url") or ""

    try:
        if provider == "anthropic" and api_key:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    models = sorted(
                        [m["id"] for m in data if "claude" in m.get("id", "").lower()],
                        reverse=True,
                    )
                    return models or AVAILABLE_MODELS["anthropic"]

        elif provider == "openai" and api_key:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    chat_models = sorted(
                        [
                            m["id"]
                            for m in data
                            if any(
                                k in m["id"] for k in ("gpt-4", "gpt-3.5", "o1", "o3")
                            )
                        ],
                        reverse=True,
                    )
                    return chat_models or AVAILABLE_MODELS["openai"]

        elif provider == "z_ai" and api_key:
            # Z.AI (ZhipuAI) uses OpenAI-compatible endpoint
            zai_base = base_url or "https://api.z.ai/api/coding/paas/v4"
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{zai_base}models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    return sorted(
                        [m["id"] for m in data if "glm" in m.get("id", "").lower()],
                        reverse=True,
                    ) or AVAILABLE_MODELS.get("z_ai", [])

        elif provider == "github_models" and api_key:
            # Use the GitHub Models catalog endpoint (returns richer metadata than /v1/models)
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://models.github.ai/catalog/models",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Accept": "application/json",
                    },
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    items = (
                        payload
                        if isinstance(payload, list)
                        else payload.get("data", [])
                    )
                    models = sorted(
                        {str(m.get("id", "")).strip() for m in items if m.get("id")}
                    )
                    return models or AVAILABLE_MODELS["github_models"]

        elif provider == "ollama":
            ol_base = (base_url or "http://localhost:11434/v1").replace("/v1", "")
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{ol_base}/api/tags")
                if resp.status_code == 200:
                    models_data = resp.json().get("models", [])
                    return [m["name"] for m in models_data] or AVAILABLE_MODELS.get(
                        "ollama", []
                    )

        elif provider == "google_ai_studio" and api_key:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                )
                if resp.status_code == 200:
                    data = resp.json().get("models", [])
                    return [
                        m["name"].split("/")[-1]
                        for m in data
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                    ] or AVAILABLE_MODELS.get("google_ai_studio", [])

        elif provider == "minimax" and api_key:
            # MiniMax uses OpenAI-compatible endpoint
            minimax_base = (
                base_url
                or os.getenv("MINIMAX_BASE_URL", "").strip()
                or "https://api.minimax.chat/v1"
            )
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{minimax_base.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    return sorted(
                        [m["id"] for m in data if m.get("id")],
                        reverse=True,
                    ) or AVAILABLE_MODELS.get("minimax", [])

        elif provider == "groq" and api_key:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    return sorted(
                        [
                            m["id"]
                            for m in data
                            if any(k in m["id"] for k in ("llama", "mixtral", "gemma"))
                        ],
                        reverse=True,
                    ) or AVAILABLE_MODELS.get("groq", [])

        elif provider == "openrouter" and api_key:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    return sorted(
                        [m["id"] for m in data if m.get("id")]
                    ) or AVAILABLE_MODELS.get("openrouter", [])

        elif provider == "custom" and api_key and base_url:
            # Custom OpenAI-compatible endpoint
            custom_base = base_url.rstrip("/")
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{custom_base}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    return sorted([m["id"] for m in data], reverse=True)

    except Exception:
        pass

    return AVAILABLE_MODELS.get(provider, [])
