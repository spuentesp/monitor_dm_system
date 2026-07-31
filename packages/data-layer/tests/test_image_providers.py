"""Image provider adapter tests — httpx fully mocked, no network."""

from __future__ import annotations

import asyncio
import base64

import pytest

from monitor_data.llm.image_providers import (
    GeminiImageAdapter,
    ImageProviderError,
    MiniMaxImageAdapter,
    adapter_for_provider_row,
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


def test_factory_requires_api_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_TOKEN", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(ImageProviderError):
        adapter_for_provider_row({"provider": "minimax", "api_key": "", "base_url": None})


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
