"""
Image generation provider adapters for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (httpx, base64) + monitor_data.schemas
CALLED BY: UI backend image_gen router (Layer 2/3 boundary)

One interface — ``generate_image(prompt, *, aspect_ratio) -> bytes`` — with
implementations for MiniMax (``image-01``) and Google Gemini's image-capable
"nano-banana" models (``gemini-2.5-flash-image``). Provider selection reuses
the LLM registry tables: any ``llm_providers`` row with ``role='image'`` is a
candidate; ``resolve_image_adapter`` picks the default/connected one.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import httpx

from monitor_data.schemas.llm_config import LLMProviderType, ModelRole

_MINIMAX_DEFAULT_BASE = "https://api.minimaxi.com"
_GEMINI_DEFAULT_BASE = "https://generativelanguage.googleapis.com"
_GEMINI_DEFAULT_MODEL = "gemini-2.5-flash-image"
_TIMEOUT = 90.0  # image generation is slow; chat timeouts don't apply


class ImageProviderError(RuntimeError):
    """Raised for provider misconfiguration or unusable provider responses."""


@runtime_checkable
class ImageProviderAdapter(Protocol):
    """One method: prompt (+ aspect ratio) in, image bytes out."""

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes: ...


def _minimax_base(base_url: str | None) -> str:
    """Normalise a MiniMax base URL for the image endpoint.

    Chat providers store the Anthropic-compatible base (``.../anthropic``);
    image generation lives at the host root (``/v1/image_generation``).
    """
    base = (base_url or "").strip().rstrip("/") or _MINIMAX_DEFAULT_BASE
    if base.endswith("/anthropic"):
        base = base[: -len("/anthropic")]
    return base


@dataclass
class MiniMaxImageAdapter:
    """MiniMax ``POST /v1/image_generation`` (model ``image-01``)."""

    api_key: str
    base_url: str = _MINIMAX_DEFAULT_BASE
    model: str = "image-01"

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        base = _minimax_base(self.base_url)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{base}/v1/image_generation",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "aspect_ratio": aspect_ratio,
                    "response_format": "url",
                },
            )
            resp.raise_for_status()
            data = (resp.json() or {}).get("data") or {}

            # Base64 payloads arrive inline regardless of requested format.
            b64_list = data.get("image_base64") or []
            if b64_list:
                return base64.b64decode(b64_list[0])

            # URL payloads are temporary — download immediately.
            urls = data.get("image_urls") or []
            if urls:
                dl = await client.get(urls[0])
                dl.raise_for_status()
                return bytes(dl.content)

        raise ImageProviderError("MiniMax image response contained no image data")


@dataclass
class GeminiImageAdapter:
    """Gemini ``:generateContent`` with IMAGE response modality (nano-banana)."""

    api_key: str
    model: str = _GEMINI_DEFAULT_MODEL
    base_url: str = _GEMINI_DEFAULT_BASE

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        # aspect_ratio is accepted for interface parity; Gemini infers framing
        # from the prompt text, so the router bakes it into the prompt.
        url = f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
                },
            )
            resp.raise_for_status()
            payload = resp.json() or {}

        for candidate in payload.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                if inline.get("data"):
                    return base64.b64decode(inline["data"])
        raise ImageProviderError("Gemini response contained no inline image part")


def _env_key_for(provider: LLMProviderType) -> str:
    """Fallback credential lookup, mirroring llm_mgmt's env seeding."""
    if provider is LLMProviderType.MINIMAX:
        return os.getenv("MINIMAX_TOKEN", "").strip() or os.getenv("MINIMAX_API_KEY", "").strip()
    if provider is LLMProviderType.GOOGLE_AI_STUDIO:
        return os.getenv("GOOGLE_API_KEY", "").strip()
    return ""


def adapter_for_provider_row(row: dict[str, Any]) -> ImageProviderAdapter:
    """Build the image adapter for one ``llm_providers`` row.

    Raises ``ImageProviderError`` when the provider type has no image support
    or no credential is available (row key first, then env fallback).
    """
    provider = LLMProviderType(str(row.get("provider") or ""))
    api_key = (row.get("api_key") or "").strip() or _env_key_for(provider)
    if not api_key:
        raise ImageProviderError(f"No API key configured for image provider '{row.get('id')}'")

    if provider is LLMProviderType.MINIMAX:
        return MiniMaxImageAdapter(
            api_key=api_key,
            base_url=_minimax_base(row.get("base_url")),
            model=(row.get("model") or "").strip() or "image-01",
        )
    if provider is LLMProviderType.GOOGLE_AI_STUDIO:
        return GeminiImageAdapter(
            api_key=api_key,
            model=(row.get("model") or "").strip() or _GEMINI_DEFAULT_MODEL,
            base_url=(row.get("base_url") or "").strip().rstrip("/") or _GEMINI_DEFAULT_BASE,
        )
    raise ImageProviderError(f"Provider '{provider.value}' does not support image generation")


async def resolve_image_adapter(postgres: Any) -> ImageProviderAdapter | None:
    """Pick the configured image provider from the LLM registry tables.

    Preference: is_default image row → connected image row → any image row.
    Returns None when no row carries ``role='image'`` (router maps to 400).
    """
    rows = await postgres.providers_list()
    image_rows = [r for r in rows if (r.get("role") or "").strip().lower() == ModelRole.IMAGE.value]
    if not image_rows:
        return None
    image_rows.sort(
        key=lambda r: (
            not r.get("is_default"),
            (r.get("status") or "").lower() != "connected",
        )
    )
    return adapter_for_provider_row(image_rows[0])
