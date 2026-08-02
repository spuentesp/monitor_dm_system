"""
Image generation provider adapters for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (httpx, base64) + monitor_data.schemas
CALLED BY: UI backend image_gen router (Layer 2/3 boundary)

Two public adapter classes for image generation: MiniMax (``image-01``,
``POST /v1/image_generation``) and Google Gemini's image-capable "nano-banana"
models (``gemini-2.5-flash-image``, ``:generateContent`` with the IMAGE
response modality). Provider selection reuses the LLM registry tables: any
``llm_providers`` row with ``role='image'`` is a candidate;
``resolve_image_adapter`` picks the default/connected one.

Task 3 surface
--------------

- :class:`ImageCapabilities` declares what each provider can do (aspect-ratio
  set, whether the request payload accepts inline reference bytes).
- :class:`ImageGenerationInput` is the structured input contract used by the
  orchestration layer. Both adapters accept it via ``generate_image_structured``.
- :func:`generate_image_compat` is a thin compatibility wrapper so existing
  callers (and the UI backend router) can keep using
  ``adapter.generate_image(prompt, *, aspect_ratio)`` while the rest of the
  system moves to the structured form.
- :func:`filter_references_for_adapter` is the orchestration hook that drops
  reference images when the configured provider reports no support, so the
  adapter never sees bytes it cannot send.

Reference-image support deliberately stays ``False`` for both adapters until a
provider-payload test confirms the actual image-generation model contract.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable

import httpx

from monitor_data.schemas.llm_config import LLMProviderType, ModelRole

_MINIMAX_DEFAULT_BASE = "https://api.minimaxi.com"
_GEMINI_DEFAULT_BASE = "https://generativelanguage.googleapis.com"
_GEMINI_DEFAULT_MODEL = "gemini-2.5-flash-image"
_TIMEOUT = 90.0  # image generation is slow; chat timeouts don't apply

# Provider-advertised aspect ratios. MiniMax accepts these on
# ``POST /v1/image_generation``. Gemini infers framing from the prompt text,
# but the orchestration layer still validates the request side of the contract.
_MINIMAX_SUPPORTED_ASPECT_RATIOS: frozenset[str] = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"})
_GEMINI_SUPPORTED_ASPECT_RATIOS: frozenset[str] = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"})


class ImageProviderError(RuntimeError):
    """Raised for provider misconfiguration or unusable provider responses."""


# ---------------------------------------------------------------------------
# Public dataclasses (Task 3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageCapabilities:
    """Static metadata about what an image provider can do.

    Adapters expose this through :meth:`ImageProviderAdapter.capabilities`.
    The orchestration layer uses it to decide whether to send reference
    images, validate the requested aspect ratio, and pick a provider for
    a given request shape.
    """

    provider_id: str
    model: str
    supports_reference_images: bool
    supported_aspect_ratios: frozenset[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible snapshot of these capabilities.

        ``supported_aspect_ratios`` is normalised to a sorted list so the
        resulting mapping is deterministic and round-trips through
        :func:`json.dumps` / :func:`json.loads` without surprises. The
        orchestration layer persists this shape in audit logs.
        """
        return {
            "provider_id": self.provider_id,
            "model": self.model,
            "supports_reference_images": self.supports_reference_images,
            "supported_aspect_ratios": sorted(self.supported_aspect_ratios),
        }


@dataclass(frozen=True)
class ReferenceImage:
    """An inline reference image plus its MIME content type."""

    content: bytes
    content_type: str = "image/png"


@dataclass(frozen=True)
class ImageGenerationInput:
    """Structured input to an image-generation adapter.

    ``prompt`` is the text prompt. ``aspect_ratio`` must be one of the ratios
    listed in the adapter's :class:`ImageCapabilities`. ``reference_images`` is
    an ordered sequence of inline images that the adapter may attach to the
    request; providers that do not advertise support will silently drop them
    via :func:`filter_references_for_adapter`.
    """

    prompt: str
    aspect_ratio: str = "1:1"
    reference_images: Sequence[ReferenceImage] = field(default_factory=tuple)


@runtime_checkable
class ImageProviderAdapter(Protocol):
    """The image-generation adapter contract (Task 3).

    Two call shapes:

    - ``generate_image(prompt, *, aspect_ratio)`` -- legacy positional form
      preserved so existing router call sites keep working without change.
    - ``generate_image_structured(input)`` -- new structured form used by the
      orchestration layer.

    Both routes share the same per-provider implementation, validate the
    aspect ratio against the adapter's advertised capabilities, and produce
    the same HTTP request body.
    """

    def capabilities(self) -> ImageCapabilities: ...

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes: ...

    async def generate_image_structured(self, input: ImageGenerationInput) -> bytes: ...


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def _minimax_base(base_url: str | None) -> str:
    """Normalise a MiniMax base URL for the image endpoint.

    Chat providers store the Anthropic-compatible base (``.../anthropic``);
    image generation lives at the host root (``/v1/image_generation``).
    """
    base = (base_url or "").strip().rstrip("/") or _MINIMAX_DEFAULT_BASE
    if base.endswith("/anthropic"):
        base = base[: -len("/anthropic")]
    return base


def _validate_aspect_ratio(capabilities: ImageCapabilities, aspect_ratio: str) -> None:
    """Reject an unsupported aspect ratio with an :class:`ImageProviderError`.

    Called by both adapters on every request -- structured-input and legacy
    routes alike -- so callers cannot accidentally send a ratio the provider
    cannot honour.
    """
    if aspect_ratio not in capabilities.supported_aspect_ratios:
        raise ImageProviderError(
            f"aspect_ratio {aspect_ratio!r} is not supported by "
            f"{capabilities.provider_id}/{capabilities.model}; "
            f"supported ratios: {sorted(capabilities.supported_aspect_ratios)}"
        )


@dataclass
class MiniMaxImageAdapter:
    """MiniMax ``POST /v1/image_generation`` (model ``image-01``).

    Text-only contract: the request body carries ``model``, ``prompt``,
    ``aspect_ratio``, and ``response_format``; reference images are not
    part of the MiniMax image-generation surface, so
    :attr:`ImageCapabilities.supports_reference_images` is ``False``.
    """

    api_key: str
    base_url: str = _MINIMAX_DEFAULT_BASE
    model: str = "image-01"

    def capabilities(self) -> ImageCapabilities:
        return ImageCapabilities(
            provider_id="minimax",
            model=self.model,
            supports_reference_images=False,
            supported_aspect_ratios=_MINIMAX_SUPPORTED_ASPECT_RATIOS,
        )

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        # Route the legacy form through the structured-input path so the
        # payload contract has exactly one source of truth.
        return await self.generate_image_structured(ImageGenerationInput(prompt=prompt, aspect_ratio=aspect_ratio))

    async def generate_image_structured(self, input: ImageGenerationInput) -> bytes:
        caps = self.capabilities()
        _validate_aspect_ratio(caps, input.aspect_ratio)
        base = _minimax_base(self.base_url)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{base}/v1/image_generation",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "prompt": input.prompt,
                    "aspect_ratio": input.aspect_ratio,
                    "response_format": "url",
                },
            )
            resp.raise_for_status()
            data = (resp.json() or {}).get("data") or {}

            # Base64 payloads arrive inline regardless of requested format.
            b64_list = data.get("image_base64") or []
            if b64_list:
                return base64.b64decode(b64_list[0])

            # URL payloads are temporary -- download immediately.
            urls = data.get("image_urls") or []
            if urls:
                dl = await client.get(urls[0])
                dl.raise_for_status()
                return bytes(dl.content)

        raise ImageProviderError("MiniMax image response contained no image data")


@dataclass
class GeminiImageAdapter:
    """Gemini ``:generateContent`` with IMAGE response modality (nano-banana).

    Reference support is intentionally advertised as ``False`` until a real
    provider-payload test confirms that
    ``gemini-2.5-flash-image`` accepts inline reference bytes the way the
    generic ``:generateContent`` API does. Until then the orchestration
    layer drops any ``ReferenceImage`` values before they reach this
    adapter, so the request body remains a single text part.
    """

    api_key: str
    model: str = _GEMINI_DEFAULT_MODEL
    base_url: str = _GEMINI_DEFAULT_BASE

    def capabilities(self) -> ImageCapabilities:
        return ImageCapabilities(
            provider_id="google_ai_studio",
            model=self.model,
            supports_reference_images=False,
            supported_aspect_ratios=_GEMINI_SUPPORTED_ASPECT_RATIOS,
        )

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        # aspect_ratio is accepted for interface parity; Gemini infers framing
        # from the prompt text, so the router bakes it into the prompt.
        return await self.generate_image_structured(ImageGenerationInput(prompt=prompt, aspect_ratio=aspect_ratio))

    async def generate_image_structured(self, input: ImageGenerationInput) -> bytes:
        caps = self.capabilities()
        _validate_aspect_ratio(caps, input.aspect_ratio)
        url = f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent"
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": input.prompt}]}],
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


# ---------------------------------------------------------------------------
# Orchestration helpers
# ---------------------------------------------------------------------------


async def generate_image_compat(
    adapter: ImageProviderAdapter,
    prompt: str,
    *,
    aspect_ratio: str = "1:1",
) -> bytes:
    """Compatibility wrapper that adapts legacy positional call sites.

    Existing router code does
    ``await adapter.generate_image(prompt, aspect_ratio=aspect_ratio)``.
    During the structured-input migration that call shape is preserved by
    routing through the adapter's structured form. New code should call
    :meth:`ImageProviderAdapter.generate_image_structured` directly.
    """
    return await adapter.generate_image(prompt, aspect_ratio=aspect_ratio)


def capabilities_for_adapter(adapter: ImageProviderAdapter) -> ImageCapabilities:
    """Return the capabilities for an adapter-like object.

    Mostly a convenience for tests; runtime callers can also call
    :meth:`ImageProviderAdapter.capabilities` directly.
    """
    return adapter.capabilities()


def filter_references_for_adapter(
    adapter: ImageProviderAdapter,
    input: ImageGenerationInput,
) -> ImageGenerationInput:
    """Drop reference images the adapter cannot consume.

    Per the brief: a provider whose capabilities report
    ``supports_reference_images=False`` must never receive reference-image
    bytes. This helper is the orchestration-layer guard that enforces that
    invariant before the request reaches the adapter.
    """
    caps = adapter.capabilities()
    if caps.supports_reference_images or not input.reference_images:
        return input
    return ImageGenerationInput(
        prompt=input.prompt,
        aspect_ratio=input.aspect_ratio,
        reference_images=(),
    )


async def dispatch_image_generation(
    adapter: ImageProviderAdapter,
    input: ImageGenerationInput,
) -> bytes:
    """Run filtering + dispatch atomically so callers cannot bypass the invariant.

    The orchestration layer must never hand a
    :class:`ImageGenerationInput` straight to an adapter when the adapter
    advertises ``supports_reference_images=False``. Routing through this
    helper guarantees the reference filter is applied before the adapter
    sees the input.
    """
    filtered = filter_references_for_adapter(adapter, input)
    return await adapter.generate_image_structured(filtered)


# ---------------------------------------------------------------------------
# Reference conditioning — selection + MinIO loader (Task 11)
# ---------------------------------------------------------------------------
#
# These helpers exist so that when a future provider advertises
# ``supports_reference_images=True``, the orchestration layer can pull bytes
# from MinIO and feed them through ``ImageGenerationInput`` without a round
# of bespoke plumbing. They are NOT enabled for any shipped adapter today —
# both MiniMax and Gemini still report ``supports_reference_images=False`` —
# but they are exercised end-to-end by a fabricated reference-capable
# adapter in ``tests/test_image_providers.py``.
#
# Selection ordering: primary references first, then supporting references in
# newest-first order. Caps: ``max_total`` (provider-wide), ``max_per_subject``
# (one character cannot flood the prompt), ``max_per_provider`` (one image
# model cannot flood the prompt). Ties in ``created_at`` fall back to
# ``asset_id`` so the selection is fully deterministic for the same input.


_PRIMARY_ROLE = 0
_SUPPORTING_ROLE = 1
_ROLE_ORDER = {"primary": _PRIMARY_ROLE, "supporting": _SUPPORTING_ROLE}


def _reference_role(reference: Any) -> int:
    """Map a reference asset's ``reference_status`` to a sort key.

    Unknown roles sort last so they never displace primary/supporting refs.
    """
    raw = getattr(reference, "reference_status", None)
    value = getattr(raw, "value", raw)
    if isinstance(value, str):
        return _ROLE_ORDER.get(value.lower(), 99)
    return 99


def _reference_subject_id(reference: Any) -> str | None:
    subject = getattr(reference, "subject_id", None)
    return str(subject) if subject else None


def _reference_provider_id(reference: Any) -> str | None:
    pid = getattr(reference, "provider_id", None)
    return str(pid) if pid else None


def _reference_created_at(reference: Any) -> tuple[int, str]:
    """Sort key for ``created_at`` with deterministic fallback to asset_id.

    Returns ``(sort_bucket, key_string)``: ``sort_bucket`` is 0 when
    ``created_at`` is present (newest-first ordering), 1 when absent
    (sentinel bucket sorted last). ``key_string`` ties resolve
    deterministically by ``asset_id``.
    """
    created_at = getattr(reference, "created_at", None)
    asset_id = str(getattr(reference, "asset_id", ""))
    if created_at is None:
        return (1, asset_id)
    try:
        ts = float(created_at.timestamp())
    except AttributeError:
        return (1, asset_id)
    # Newer-first ordering: invert the timestamp with a fixed-width integer
    # string so the lexicographic comparison matches the numeric ordering.
    # The offset is chosen to keep the result non-negative across the
    # realistic datetime range (year 1900..2100).
    micro = int(ts * 1_000_000)
    inverted = 100_000_000_000_000_000 - micro
    return (0, f"{inverted:018d}|{asset_id}")


def select_references(
    references: Sequence[Any],
    *,
    max_total: int = 4,
    max_per_subject: int = 2,
    max_per_provider: int = 4,
) -> list[Any]:
    """Pick a stable subset of approved references for a reference-capable adapter.

    Ordering: primary references first, then supporting references in
    newest-first order. Within the same role + timestamp, ``asset_id``
    breaks the tie so the selection is fully deterministic for the same
    input. The three caps are applied greedily: per-subject and
    per-provider caps act as budget counters; ``max_total`` caps the
    returned list size. Caps <= 0 disable the corresponding bound.
    """
    candidates = sorted(
        references,
        key=lambda ref: (
            _reference_role(ref),
            _reference_created_at(ref),
        ),
    )
    subject_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    selected: list[Any] = []
    for ref in candidates:
        if max_total > 0 and len(selected) >= max_total:
            break
        subject = _reference_subject_id(ref)
        provider = _reference_provider_id(ref)
        if subject is not None and max_per_subject > 0:
            if subject_counts.get(subject, 0) >= max_per_subject:
                continue
        if provider is not None and max_per_provider > 0:
            if provider_counts.get(provider, 0) >= max_per_provider:
                continue
        selected.append(ref)
        if subject is not None:
            subject_counts[subject] = subject_counts.get(subject, 0) + 1
        if provider is not None:
            provider_counts[provider] = provider_counts.get(provider, 0) + 1
    return selected


async def load_reference_images(
    minio: Any,
    references: Sequence[Any],
) -> list[ReferenceImage]:
    """Download the bytes for a selected reference list from MinIO.

    Each entry in ``references`` is duck-typed and must expose ``minio_key``
    (the storage object key) and ``content_type`` (MIME type, defaulting to
    ``image/png``). The loader calls ``minio.download(key)`` in selection
    order; the returned bytes are wrapped in :class:`ReferenceImage`
    preserving the same order so the adapter payload shape mirrors the
    selector's output byte-for-byte.

    Callers are expected to invoke :func:`select_references` first; this
    helper trusts the input list and makes no further filtering decisions.
    Empty ``references`` short-circuits to ``[]`` without a round-trip.
    """
    if not references:
        return []
    loaded: list[ReferenceImage] = []
    for ref in references:
        key = str(getattr(ref, "minio_key", "") or "")
        if not key:
            # Skip entries with no usable key — the selector should not have
            # included them, but the loader is the safety net.
            continue
        content = await minio.download(key)
        content_type = str(getattr(ref, "content_type", "image/png") or "image/png")
        loaded.append(ReferenceImage(content=bytes(content), content_type=content_type))
    return loaded


# ---------------------------------------------------------------------------
# Registry/selection
# ---------------------------------------------------------------------------


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

    Preference: is_default image row -> connected image row -> any image row.
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


__all__ = [
    "ImageCapabilities",
    "ImageGenerationInput",
    "ImageProviderAdapter",
    "ImageProviderError",
    "MiniMaxImageAdapter",
    "GeminiImageAdapter",
    "ReferenceImage",
    "adapter_for_provider_row",
    "capabilities_for_adapter",
    "dispatch_image_generation",
    "filter_references_for_adapter",
    "generate_image_compat",
    "load_reference_images",
    "resolve_image_adapter",
    "select_references",
]
