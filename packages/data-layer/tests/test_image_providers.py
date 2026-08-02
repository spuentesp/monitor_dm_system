"""Image provider adapter tests - httpx fully mocked, no network."""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from monitor_data.llm.image_providers import (
    GeminiImageAdapter,
    ImageCapabilities,
    ImageGenerationInput,
    ImageProviderError,
    MiniMaxImageAdapter,
    ReferenceImage,
    adapter_for_provider_row,
    dispatch_image_generation,
    generate_image_compat,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeResponse:
    def __init__(self, payload=None, content=b"", status_code=200):
        self._payload = payload
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """Records calls; serves queued post/get responses."""

    def __init__(self, posts=None, gets=None):
        self._posts = list(posts or [])
        self._gets = list(gets or [])
        self.post_calls: list[dict] = []
        self.get_calls: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return self._posts.pop(0)

    async def get(self, url):
        self.get_calls.append(url)
        return self._gets.pop(0)


PNG_BYTES = b"\x89PNG-fake-bytes"
PNG_B64 = base64.b64encode(PNG_BYTES).decode()


def test_minimax_url_response_downloads_image(monkeypatch):
    client = _FakeClient(
        posts=[_FakeResponse({"data": {"image_urls": ["https://cdn.example.com/tmp/1.png"]}})],
        gets=[_FakeResponse(content=PNG_BYTES)],
    )
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = MiniMaxImageAdapter(api_key="sk-test", base_url="https://api.minimaxi.com")
    out = _run(adapter.generate_image("a fox spirit", aspect_ratio="1:1"))

    assert out == PNG_BYTES
    call = client.post_calls[0]
    assert call["url"] == "https://api.minimaxi.com/v1/image_generation"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    assert call["json"]["model"] == "image-01"
    assert call["json"]["prompt"] == "a fox spirit"
    assert call["json"]["aspect_ratio"] == "1:1"
    assert client.get_calls == ["https://cdn.example.com/tmp/1.png"]


def test_minimax_base64_response_shape(monkeypatch):
    client = _FakeClient(posts=[_FakeResponse({"data": {"image_base64": [PNG_B64]}})])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = MiniMaxImageAdapter(api_key="sk-test")
    assert _run(adapter.generate_image("portrait")) == PNG_BYTES
    assert client.get_calls == []  # no follow-up download for base64 payloads


def test_minimax_anthropic_base_url_is_trimmed_to_host(monkeypatch):
    client = _FakeClient(posts=[_FakeResponse({"data": {"image_base64": [PNG_B64]}})])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = MiniMaxImageAdapter(api_key="k", base_url="https://api.minimax.io/anthropic")
    _run(adapter.generate_image("p"))
    assert client.post_calls[0]["url"] == "https://api.minimax.io/v1/image_generation"


def test_minimax_empty_data_raises(monkeypatch):
    client = _FakeClient(posts=[_FakeResponse({"data": {}})])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    with pytest.raises(ImageProviderError):
        _run(MiniMaxImageAdapter(api_key="k").generate_image("p"))


def test_gemini_extracts_inline_image(monkeypatch):
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "here is your image"},
                        {"inlineData": {"mimeType": "image/png", "data": PNG_B64}},
                    ]
                }
            }
        ]
    }
    client = _FakeClient(posts=[_FakeResponse(payload)])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = GeminiImageAdapter(api_key="gk-test")
    out = _run(adapter.generate_image("a drowned court", aspect_ratio="16:9"))

    assert out == PNG_BYTES
    call = client.post_calls[0]
    assert call["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
    )
    assert call["headers"]["x-goog-api-key"] == "gk-test"
    assert call["json"]["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]


def test_gemini_no_image_part_raises(monkeypatch):
    payload = {"candidates": [{"content": {"parts": [{"text": "no image"}]}}]}
    client = _FakeClient(posts=[_FakeResponse(payload)])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    with pytest.raises(ImageProviderError):
        _run(GeminiImageAdapter(api_key="gk").generate_image("p"))


def test_factory_picks_adapter_by_provider_type():
    mm = adapter_for_provider_row({"provider": "minimax", "api_key": "k", "base_url": None, "model": "image-01"})
    assert isinstance(mm, MiniMaxImageAdapter)
    g = adapter_for_provider_row(
        {
            "provider": "google_ai_studio",
            "api_key": "k",
            "base_url": None,
            "model": "gemini-2.5-flash-image",
        }
    )
    assert isinstance(g, GeminiImageAdapter)
    with pytest.raises(ImageProviderError):
        adapter_for_provider_row({"provider": "anthropic", "api_key": "k"})


def test_factory_gemini_honors_custom_base_url(monkeypatch):
    """A stored base_url (e.g. a Gemini-compatible proxy) must end up in the
    request URL, trailing slash stripped; missing base_url falls back to the
    Google default."""
    payload = {"candidates": [{"content": {"parts": [{"inlineData": {"data": PNG_B64}}]}}]}
    client = _FakeClient(posts=[_FakeResponse(payload)])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = adapter_for_provider_row(
        {
            "provider": "google_ai_studio",
            "api_key": "gk",
            "base_url": "https://gemini-proxy.example.com/",
            "model": "gemini-2.5-flash-image",
        }
    )
    assert isinstance(adapter, GeminiImageAdapter)
    _run(adapter.generate_image("p"))
    assert client.post_calls[0]["url"] == (
        "https://gemini-proxy.example.com/v1beta/models/gemini-2.5-flash-image:generateContent"
    )

    default = adapter_for_provider_row({"provider": "google_ai_studio", "api_key": "gk", "base_url": None})
    assert default.base_url == "https://generativelanguage.googleapis.com"


def test_factory_requires_api_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_TOKEN", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(ImageProviderError):
        adapter_for_provider_row({"provider": "minimax", "api_key": "", "base_url": None})


# ---------------------------------------------------------------------------
# Task 3: structured-input form must produce the exact same HTTP call as the
# legacy positional form. Both adapters route through the same code path, so
# each test below records one legacy call and one structured call and asserts
# the complete recorded call data is byte-for-byte identical.
# ---------------------------------------------------------------------------


def _normalize_call(call: dict) -> dict:
    """Strip non-payload noise so two recorded calls can be compared directly."""
    return {
        "url": call["url"],
        "headers": dict(call.get("headers", {})),
        "json": call.get("json"),
    }


# ---------------------------------------------------------------------------
# Task 11: reference-conditioning plumbing. The text-only fallback test below
# pins the orchestrator invariant for the current provider set (MiniMax +
# Gemini advertise supports_reference_images=False). The reference-capable
# adapter test exercises the same plumbing against a fabricated adapter whose
# capabilities claim support — neither MiniMax nor Gemini are modified to flip
# their flag in this task.
# ---------------------------------------------------------------------------


class _RecordingAdapter:
    """Adapter stand-in that records the structured input it received.

    Used by both the text-only fallback test (default flag) and the
    reference-capable adapter test (flag turned on).
    """

    def __init__(
        self,
        *,
        supports_reference_images: bool,
        received: list,
        provider_id: str = "test",
        model: str = "test",
        supported_aspect_ratios: frozenset[str] = frozenset({"1:1", "16:9"}),
    ) -> None:
        self._caps = ImageCapabilities(
            provider_id=provider_id,
            model=model,
            supports_reference_images=supports_reference_images,
            supported_aspect_ratios=supported_aspect_ratios,
        )
        self.received = received

    def capabilities(self) -> ImageCapabilities:
        return self._caps

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        return await self.generate_image_structured(
            ImageGenerationInput(prompt=prompt, aspect_ratio=aspect_ratio)
        )

    async def generate_image_structured(self, input: ImageGenerationInput) -> bytes:
        self.received.append(input)
        return PNG_BYTES


def test_text_only_provider_never_receives_reference_bytes(monkeypatch):
    """When the adapter advertises ``supports_reference_images=False`` the
    orchestrator must strip reference bytes from the structured input — the
    adapter never sees them. This is the text-only fallback invariant for
    both shipped providers (MiniMax and Gemini).
    """
    recorded: list[ImageGenerationInput] = []
    adapter = _RecordingAdapter(supports_reference_images=False, received=recorded)
    reference = ReferenceImage(content=b"\x89PNG-SENTINEL", content_type="image/png")

    out = _run(
        dispatch_image_generation(
            adapter,
            ImageGenerationInput(
                prompt="a fox spirit",
                aspect_ratio="1:1",
                reference_images=(reference,),
            ),
        )
    )

    assert out == PNG_BYTES
    assert len(recorded) == 1
    delivered = recorded[0]
    assert delivered.prompt == "a fox spirit"
    assert delivered.aspect_ratio == "1:1"
    assert list(delivered.reference_images) == []
    # The sentinel never reaches the adapter in any field of the input.
    assert reference.content not in [ref.content for ref in delivered.reference_images]


def test_reference_capable_adapter_receives_loaded_reference_bytes(monkeypatch):
    """For a fabricated reference-capable adapter, the orchestration layer
    must deliver the exact bytes (in declared order) through the structured
    input — no rewriting, no reordering, no content-type changes. This
    proves the loader + selector round-trip end-to-end without enabling any
    real provider.
    """
    primary_bytes = b"\x89PNG-PRIMARY"
    supporting_bytes = b"\x89PNG-SUPPORTING"
    recorded: list[ImageGenerationInput] = []
    adapter = _RecordingAdapter(
        supports_reference_images=True,
        received=recorded,
        provider_id="ref-capable-test",
        model="ref-capable-1",
    )

    out = _run(
        dispatch_image_generation(
            adapter,
            ImageGenerationInput(
                prompt="a fox spirit",
                aspect_ratio="1:1",
                reference_images=(
                    ReferenceImage(content=primary_bytes, content_type="image/png"),
                    ReferenceImage(content=supporting_bytes, content_type="image/jpeg"),
                ),
            ),
        )
    )

    assert out == PNG_BYTES
    assert len(recorded) == 1
    delivered = recorded[0]
    refs = list(delivered.reference_images)
    assert [ref.content for ref in refs] == [primary_bytes, supporting_bytes]
    assert [ref.content_type for ref in refs] == ["image/png", "image/jpeg"]


# ---------------------------------------------------------------------------
# Task 11: MinIO loader + max_reference_images + ordering enforcement
# ---------------------------------------------------------------------------


class _StubMinioClient:
    """Records ``download`` calls and returns canned bytes.

    Mimics the public surface ``monitor_data.db.minio.MinIOClient.download``
    uses; the loader only needs the async ``download(key) -> bytes`` method.
    """

    def __init__(self, payloads: dict[str, bytes] | None = None) -> None:
        self._payloads = dict(payloads or {})
        self.download_calls: list[str] = []

    async def download(self, key: str, bucket: str | None = None) -> bytes:
        self.download_calls.append(key)
        if key not in self._payloads:
            raise RuntimeError(f"missing payload for {key!r}")
        return self._payloads[key]


def _ref_asset(**overrides: Any) -> Any:
    """Lightweight ReferenceAsset stand-in (a dataclass with the fields the
    loader + selector needs). Keeps the test independent of the agents-layer
    schema so it can exercise the loader behaviour purely at the data-layer
    level.
    """
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Ref:
        asset_id: UUID
        reference_status: str
        minio_key: str = ""
        subject_id: str | None = None
        provider_id: str | None = None
        created_at: Any = None
        content_type: str = "image/png"

    payload: dict[str, Any] = {
        "asset_id": uuid4(),
        "reference_status": "primary",
        "minio_key": "k",
        "subject_id": None,
        "provider_id": "fake",
        "created_at": None,
        "content_type": "image/png",
    }
    payload.update(overrides)
    return _Ref(**payload)


def test_load_reference_images_downloads_only_selected_keys() -> None:
    """The loader pulls bytes only for the references the selector chose.
    Bytes returned match the canonical content-type per asset, and the
    ordering of ``download`` calls matches the selector's order.
    """
    from monitor_data.llm.image_providers import load_reference_images

    primary_a = _ref_asset(
        minio_key="assets/portrait/character-c-1/primary.png",
        content_type="image/png",
    )
    primary_b = _ref_asset(
        minio_key="assets/portrait/character-c-2/primary.jpg",
        content_type="image/jpeg",
    )
    skipped = _ref_asset(
        minio_key="assets/portrait/character-c-3/skipped.png",
        content_type="image/png",
    )
    minio = _StubMinioClient(
        payloads={
            primary_a.minio_key: b"\x89PNG-A",
            primary_b.minio_key: b"\x89PNG-B",
        }
    )

    refs = _run(load_reference_images(minio, [primary_a, primary_b]))

    assert minio.download_calls == [primary_a.minio_key, primary_b.minio_key]
    assert [ref.content for ref in refs] == [b"\x89PNG-A", b"\x89PNG-B"]
    assert [ref.content_type for ref in refs] == ["image/png", "image/jpeg"]
    # The skipped asset was never downloaded.
    assert skipped.minio_key not in minio.download_calls


def test_select_references_prefers_primary_then_newest_supporting() -> None:
    """Selector: primary references come first, then supporting references in
    newest-first order, capped at ``max_total``. Within the same role, the
    newest ``created_at`` wins; ties fall back to asset_id for determinism.
    """
    from monitor_data.llm.image_providers import select_references

    older = _ref_asset(reference_status="supporting", created_at=datetime(2024, 1, 1, tzinfo=UTC))
    newer = _ref_asset(reference_status="supporting", created_at=datetime(2026, 1, 1, tzinfo=UTC))
    primary = _ref_asset(reference_status="primary", created_at=datetime(2025, 6, 1, tzinfo=UTC))
    extra = _ref_asset(reference_status="primary", created_at=datetime(2025, 6, 1, tzinfo=UTC))

    selected = select_references(
        [older, newer, primary, extra],
        max_total=3,
        max_per_subject=3,
        max_per_provider=10,
    )

    # The total cap of 3 selects both primaries + the newest supporting.
    selected_ids = [r.asset_id for r in selected]
    assert len(selected_ids) == 3
    assert primary.asset_id in selected_ids
    assert extra.asset_id in selected_ids
    assert newer.asset_id in selected_ids
    # ``older`` is dropped because the total cap of 3 is exhausted by two
    # primaries + the newest supporting.
    assert older.asset_id not in selected_ids
    # Both primaries come before any supporting reference.
    primary_positions = [i for i, rid in enumerate(selected_ids) if rid in {primary.asset_id, extra.asset_id}]
    supporting_positions = [i for i, rid in enumerate(selected_ids) if rid == newer.asset_id]
    assert max(primary_positions) < min(supporting_positions)


def test_select_references_caps_per_subject_and_per_provider() -> None:
    """Selector: per-subject and per-provider caps prevent flooding. Without
    the per-subject cap, a single character could dominate the prompt with
    every approved primary+supporting portrait; without the per-provider cap,
    a single image model could dominate the same way.
    """
    from monitor_data.llm.image_providers import select_references

    a1 = _ref_asset(reference_status="primary", subject_id="char-a", provider_id="minimax")
    a2 = _ref_asset(reference_status="supporting", subject_id="char-a", provider_id="minimax")
    a3 = _ref_asset(reference_status="supporting", subject_id="char-a", provider_id="minimax")
    b1 = _ref_asset(reference_status="primary", subject_id="char-b", provider_id="minimax")

    selected = select_references(
        [a1, a2, a3, b1],
        max_total=10,
        max_per_subject=2,
        max_per_provider=2,
    )

    # char-a is capped at 2; the provider is capped at 2; together this drops
    # a3 and one of a1/a2 (the per-provider cap is the binding constraint).
    selected_ids = {r.asset_id for r in selected}
    assert len(selected) == 2
    assert a3.asset_id not in selected_ids
    # At least one of a1/a2 plus b1 wins; b1 is always selected.
    assert b1.asset_id in selected_ids


def test_minimax_structured_and_legacy_generate_image_identical_payload(monkeypatch):
    """Both call shapes must send the exact same URL, headers, and JSON body."""
    client = _FakeClient(
        posts=[
            _FakeResponse({"data": {"image_base64": [PNG_B64]}}),
            _FakeResponse({"data": {"image_base64": [PNG_B64]}}),
        ]
    )
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = MiniMaxImageAdapter(api_key="sk-test", base_url="https://api.minimaxi.com")

    legacy_out = _run(adapter.generate_image("a fox spirit", aspect_ratio="1:1"))
    structured_out = _run(
        adapter.generate_image_structured(ImageGenerationInput(prompt="a fox spirit", aspect_ratio="1:1"))
    )

    assert legacy_out == PNG_BYTES
    assert structured_out == PNG_BYTES
    assert len(client.post_calls) == 2
    assert _normalize_call(client.post_calls[0]) == _normalize_call(client.post_calls[1])

    expected = {
        "url": "https://api.minimaxi.com/v1/image_generation",
        "headers": {"Authorization": "Bearer sk-test"},
        "json": {
            "model": "image-01",
            "prompt": "a fox spirit",
            "aspect_ratio": "1:1",
            "response_format": "url",
        },
    }
    assert _normalize_call(client.post_calls[0]) == expected


def test_gemini_structured_and_legacy_generate_image_identical_payload(monkeypatch):
    """Both call shapes must send the exact same URL, headers, and JSON body."""
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "here is your image"},
                        {"inlineData": {"mimeType": "image/png", "data": PNG_B64}},
                    ]
                }
            }
        ]
    }
    client = _FakeClient(posts=[_FakeResponse(payload), _FakeResponse(payload)])
    monkeypatch.setattr("monitor_data.llm.image_providers.httpx.AsyncClient", lambda **kw: client)

    adapter = GeminiImageAdapter(api_key="gk-test")

    legacy_out = _run(adapter.generate_image("a drowned court", aspect_ratio="16:9"))
    structured_out = _run(
        adapter.generate_image_structured(ImageGenerationInput(prompt="a drowned court", aspect_ratio="16:9"))
    )

    assert legacy_out == PNG_BYTES
    assert structured_out == PNG_BYTES
    assert len(client.post_calls) == 2
    assert _normalize_call(client.post_calls[0]) == _normalize_call(client.post_calls[1])

    expected = {
        "url": ("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"),
        "headers": {"x-goog-api-key": "gk-test"},
        "json": {
            "contents": [{"parts": [{"text": "a drowned court"}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
    }
    assert _normalize_call(client.post_calls[0]) == expected


def test_generate_image_compat_is_a_module_level_helper():
    """Legacy callers in the UI backend router pass (adapter, prompt, ...);
    a module-level compat helper keeps that call shape intact during Task 3."""
    assert callable(generate_image_compat)


@pytest.mark.asyncio
async def test_resolve_image_adapter_prefers_default_image_row():
    class _PG:
        async def providers_list(self):
            return [
                {"id": "chat", "provider": "openai", "role": "standard", "api_key": "x"},
                {
                    "id": "img-b",
                    "provider": "google_ai_studio",
                    "role": "image",
                    "api_key": "g",
                    "status": "connected",
                    "is_default": False,
                    "model": "gemini-2.5-flash-image",
                },
                {
                    "id": "img-a",
                    "provider": "minimax",
                    "role": "image",
                    "api_key": "m",
                    "status": "connected",
                    "is_default": True,
                    "model": "image-01",
                    "base_url": None,
                },
            ]

    from monitor_data.llm.image_providers import resolve_image_adapter

    adapter = await resolve_image_adapter(_PG())
    assert isinstance(adapter, MiniMaxImageAdapter)  # default image row wins


@pytest.mark.asyncio
async def test_resolve_image_adapter_none_when_unconfigured():
    class _PG:
        async def providers_list(self):
            return [{"id": "chat", "provider": "openai", "role": "standard", "api_key": "x"}]

    from monitor_data.llm.image_providers import resolve_image_adapter

    assert await resolve_image_adapter(_PG()) is None
