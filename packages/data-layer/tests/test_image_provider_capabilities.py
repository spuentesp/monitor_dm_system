"""
Tests for ImageCapabilities, ImageGenerationInput, and the extended
ImageProviderAdapter protocol.

These tests live next to ``test_image_providers.py`` but cover the new
contract surface (capability metadata, structured input, reference-image
filtering, aspect-ratio validation). They must be hermetic — no network.
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest

from monitor_data.llm.image_providers import (
    GeminiImageAdapter,
    ImageCapabilities,
    ImageGenerationInput,
    ImageProviderAdapter,
    ImageProviderError,
    MiniMaxImageAdapter,
    ReferenceImage,
    adapter_for_provider_row,
    capabilities_for_adapter,
    dispatch_image_generation,
    filter_references_for_adapter,
    generate_image_compat,
    resolve_image_adapter,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


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
    def __init__(self, posts=None, gets=None):
        self._posts = list(posts or [])
        self._gets = list(gets or [])
        self.post_calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.post_calls.append({"url": url, **kwargs})
        return self._posts.pop(0)

    async def get(self, url):
        return self._gets.pop(0)


PNG_BYTES = b"\x89PNG-fake-bytes-capabilities"
PNG_B64 = base64.b64encode(PNG_BYTES).decode()


def _png_part_mime() -> str:
    return "image/png"


def _make_minimax_payload(b64: str = PNG_B64) -> dict:
    return {"data": {"image_base64": [b64]}}


def _make_gemini_payload(b64: str = PNG_B64) -> dict:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [{"inlineData": {"mimeType": "image/png", "data": b64}}],
                }
            }
        ]
    }


def _install_minimax_client(monkeypatch, payload=None):
    client = _FakeClient(posts=[_FakeResponse(payload or _make_minimax_payload())])
    monkeypatch.setattr(
        "monitor_data.llm.image_providers.httpx.AsyncClient",
        lambda **kw: client,
    )
    return client


def _install_gemini_client(monkeypatch, payload=None):
    client = _FakeClient(posts=[_FakeResponse(payload or _make_gemini_payload())])
    monkeypatch.setattr(
        "monitor_data.llm.image_providers.httpx.AsyncClient",
        lambda **kw: client,
    )
    return client


# ===========================================================================
# ImageCapabilities dataclass
# ===========================================================================


class TestImageCapabilities:
    def test_minimax_capabilities_text_only(self):
        """MiniMax (``image-01``) does not advertise inline reference-image
        support — payload contract is text-only.
        """
        caps = MiniMaxImageAdapter(api_key="k").capabilities()
        assert isinstance(caps, ImageCapabilities)
        assert caps.provider_id == "minimax"
        assert caps.model == "image-01"
        assert caps.supports_reference_images is False
        assert "1:1" in caps.supported_aspect_ratios
        assert "16:9" in caps.supported_aspect_ratios
        assert "9:16" in caps.supported_aspect_ratios

    def test_gemini_capabilities_default_to_no_references(self):
        """Gemini's generic ``:generateContent`` can accept inline data, but
        Task 3 only opts the image-generation model into reference images
        after a verified payload test. Until then, reference support stays
        False to avoid shipping an unverified contract.
        """
        caps = GeminiImageAdapter(api_key="k").capabilities()
        assert isinstance(caps, ImageCapabilities)
        assert caps.provider_id == "google_ai_studio"
        assert caps.model == "gemini-2.5-flash-image"
        assert caps.supports_reference_images is False
        # Gemini accepts a fixed aspect-ratio set baked into the prompt.
        assert "1:1" in caps.supported_aspect_ratios

    def test_capabilities_supported_aspect_ratios_is_collection(self):
        """``supported_aspect_ratios`` must behave like a set-like collection
        for fast ``in`` checks and serialization-stable iteration.
        """
        caps = MiniMaxImageAdapter(api_key="k").capabilities()
        ratio_set = set(caps.supported_aspect_ratios)
        assert isinstance(caps.supported_aspect_ratios, (frozenset, set, tuple, list))
        assert "1:1" in ratio_set

    def test_to_dict_round_trip_through_json(self):
        """``to_dict()`` produces a JSON-compatible mapping that survives
        ``json.dumps`` / ``json.loads`` and reconstructs an equivalent
        :class:`ImageCapabilities`. Aspect ratios must round-trip as a list,
        not a set, so callers can persist the result with a stable shape.
        """
        original = MiniMaxImageAdapter(api_key="k").capabilities()
        snapshot = original.to_dict()

        assert snapshot["provider_id"] == "minimax"
        assert snapshot["model"] == "image-01"
        assert snapshot["supports_reference_images"] is False
        assert isinstance(snapshot["supported_aspect_ratios"], list)
        # Ratios are sorted for deterministic output.
        assert snapshot["supported_aspect_ratios"] == sorted(snapshot["supported_aspect_ratios"])

        encoded = json.dumps(snapshot)
        decoded = json.loads(encoded)
        assert decoded == snapshot

        rebuilt = ImageCapabilities(
            provider_id=decoded["provider_id"],
            model=decoded["model"],
            supports_reference_images=decoded["supports_reference_images"],
            supported_aspect_ratios=frozenset(decoded["supported_aspect_ratios"]),
        )
        assert rebuilt == original
        # Field-by-field structural equality.
        assert rebuilt.provider_id == original.provider_id
        assert rebuilt.model == original.model
        assert rebuilt.supports_reference_images == original.supports_reference_images
        assert set(rebuilt.supported_aspect_ratios) == set(original.supported_aspect_ratios)


# ===========================================================================
# ImageGenerationInput dataclass
# ===========================================================================


class TestImageGenerationInput:
    def test_default_construction(self):
        """Bare prompt, no references, default 1:1 aspect ratio."""
        inp = ImageGenerationInput(prompt="a fox spirit")
        assert inp.prompt == "a fox spirit"
        assert inp.aspect_ratio == "1:1"
        assert inp.reference_images == ()

    def test_explicit_fields(self):
        img = ReferenceImage(content=PNG_BYTES, content_type="image/png")
        inp = ImageGenerationInput(
            prompt="p",
            aspect_ratio="16:9",
            reference_images=(img,),
        )
        assert inp.aspect_ratio == "16:9"
        assert list(inp.reference_images) == [img]

    def test_reference_image_carries_bytes_and_content_type(self):
        img = ReferenceImage(content=b"abc", content_type="image/jpeg")
        assert img.content == b"abc"
        assert img.content_type == "image/jpeg"


# ===========================================================================
# generate_image_compat — legacy 2-arg / kwarg compatibility wrapper
# ===========================================================================


class TestGenerateImageCompat:
    def test_minimax_compat_accepts_prompt_and_aspect_ratio_kwarg(self, monkeypatch):
        client = _install_minimax_client(monkeypatch)
        adapter = MiniMaxImageAdapter(api_key="sk-test")

        # Positional (prompt) + aspect_ratio kwarg, the call shape today.
        out = _run(generate_image_compat(adapter, "a fox spirit", aspect_ratio="16:9"))
        assert out == PNG_BYTES

        call = client.post_calls[0]
        assert call["json"]["prompt"] == "a fox spirit"
        assert call["json"]["aspect_ratio"] == "16:9"
        # The compat wrapper must not leak reference-image payloads to a
        # provider whose capabilities report no support for them.
        assert "image_base64" not in call["json"]
        assert "image" not in (call["json"].get("contents") or [{}])[0]

    def test_gemini_compat_preserves_request_shape(self, monkeypatch):
        client = _install_gemini_client(monkeypatch)
        adapter = GeminiImageAdapter(api_key="gk-test")

        out = _run(generate_image_compat(adapter, "a drowned court", aspect_ratio="16:9"))
        assert out == PNG_BYTES
        call = client.post_calls[0]
        assert call["json"]["generationConfig"]["responseModalities"] == ["TEXT", "IMAGE"]
        # References are not supported, so the Gemini payload contains only
        # a single text part — no inline data.
        parts = call["json"]["contents"][0]["parts"]
        assert parts == [{"text": "a drowned court"}]

    def test_compat_rejects_unsupported_aspect_ratio(self):
        adapter = MiniMaxImageAdapter(api_key="k")
        with pytest.raises(ImageProviderError):
            _run(generate_image_compat(adapter, "p", aspect_ratio="7:11"))


# ===========================================================================
# Extended ImageProviderAdapter protocol surface
# ===========================================================================


class TestExtendedAdapterProtocol:
    def test_capabilities_and_generate_image_structured_present(self):
        adapter = MiniMaxImageAdapter(api_key="k")
        assert hasattr(adapter, "capabilities")
        assert hasattr(adapter, "generate_image_structured")
        # Legacy positional ``generate_image(prompt, *, aspect_ratio)`` form
        # is preserved for existing router call sites.
        assert hasattr(adapter, "generate_image")

    def test_structured_generate_image_unsupported_aspect_ratio_raises(self):
        adapter = MiniMaxImageAdapter(api_key="k")
        bad = ImageGenerationInput(prompt="p", aspect_ratio="7:11")
        with pytest.raises(ImageProviderError):
            _run(adapter.generate_image_structured(bad))

    def test_protocol_runtime_checkable(self):
        adapter = MiniMaxImageAdapter(api_key="k")
        assert isinstance(adapter, ImageProviderAdapter)


# ===========================================================================
# Aspect-ratio validation (adapter level)
# ===========================================================================


class TestAspectRatioValidation:
    def test_minimax_accepts_supported_aspect_ratio(self, monkeypatch):
        client = _install_minimax_client(monkeypatch)
        adapter = MiniMaxImageAdapter(api_key="k")
        for ratio in ("1:1", "16:9", "9:16", "4:3", "3:4"):
            client.post_calls.clear()
            client._posts.append(_FakeResponse(_make_minimax_payload()))
            out = _run(adapter.generate_image_structured(ImageGenerationInput(prompt="p", aspect_ratio=ratio)))
            assert out == PNG_BYTES

    def test_minimax_rejects_unsupported_aspect_ratio(self):
        adapter = MiniMaxImageAdapter(api_key="k")
        with pytest.raises(ImageProviderError) as exc:
            _run(adapter.generate_image_structured(ImageGenerationInput(prompt="p", aspect_ratio="21:9")))
        assert "aspect_ratio" in str(exc.value).lower()


# ===========================================================================
# Orchestration-layer reference filtering
# ===========================================================================


class _RecordingAdapter:
    """Fabricated adapter that records the structured input it receives.

    The reference-filtering tests below wrap a real provider with this
    stand-in so the assertion targets the actual
    :class:`ImageGenerationInput` the orchestration helper hands to the
    adapter — not the bytes the adapter ultimately serialises over HTTP.
    The two ``capabilities`` shapes prove the filtering invariant in both
    directions: with reference support disabled (the real-world default
    for both shipped providers), and with reference support enabled (the
    identity-pass-through case).
    """

    def __init__(
        self,
        *,
        supports_reference_images: bool,
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
        self.received: list[ImageGenerationInput] = []

    def capabilities(self) -> ImageCapabilities:
        return self._caps

    async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
        # Legacy positional form: route through the structured-input path so
        # the recorded call shape mirrors the one real adapters expose.
        return await self.generate_image_structured(ImageGenerationInput(prompt=prompt, aspect_ratio=aspect_ratio))

    async def generate_image_structured(self, input: ImageGenerationInput) -> bytes:
        self.received.append(input)
        return PNG_BYTES


class TestReferenceImageFiltering:
    """Brief requirement: a provider with ``supports_reference_images=False``
    must never receive reference-image bytes from the orchestration layer.

    These tests run the real ``dispatch_image_generation`` helper (filtering
    + dispatch atomic) against a fabricated adapter that records the
    ``ImageGenerationInput`` it actually receives, so the assertion proves
    the helper — not the real adapter's JSON serialisation — drops the
    bytes.
    """

    SENTINEL = b"\x89PNG-SENTINEL-BYTE-MARKER-must-not-leak"

    def _run_through_dispatch(self, adapter, prompt, aspect_ratio, reference):
        """Run ``dispatch_image_generation`` so the filter and dispatch
        happen together — callers cannot bypass the invariant by calling
        ``generate_image_structured`` directly with an unfiltered input.
        """
        return _run(
            dispatch_image_generation(
                adapter,
                ImageGenerationInput(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    reference_images=(reference,),
                ),
            )
        )

    def test_dispatch_drops_references_for_minimax_capable_adapter(self):
        """When the orchestration helper routes MiniMax-shaped requests,
        the fabricated adapter records an ``ImageGenerationInput`` whose
        ``reference_images`` is empty — no sentinel bytes leak through.
        """
        adapter = _RecordingAdapter(
            supports_reference_images=False,
            provider_id="minimax",
            model="image-01",
            supported_aspect_ratios=frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"}),
        )
        reference = ReferenceImage(content=self.SENTINEL, content_type="image/png")

        out = self._run_through_dispatch(adapter, prompt="a fox spirit", aspect_ratio="1:1", reference=reference)

        assert out == PNG_BYTES
        assert len(adapter.received) == 1
        recorded = adapter.received[0]
        assert recorded.prompt == "a fox spirit"
        assert recorded.aspect_ratio == "1:1"
        assert list(recorded.reference_images) == []
        # The sentinel bytes never reach the adapter in any form.
        assert self.SENTINEL not in recorded.reference_images
        for ref in recorded.reference_images:
            assert self.SENTINEL not in ref.content

    def test_dispatch_drops_references_for_gemini_capable_adapter(self):
        """Same invariant for Gemini — the dispatched input has no references
        and no sentinel bytes survive in any field the adapter saw.
        """
        adapter = _RecordingAdapter(
            supports_reference_images=False,
            provider_id="google_ai_studio",
            model="gemini-2.5-flash-image",
            supported_aspect_ratios=frozenset({"1:1", "16:9", "9:16", "4:3", "3:4"}),
        )
        reference = ReferenceImage(content=self.SENTINEL, content_type="image/png")

        out = self._run_through_dispatch(adapter, prompt="a drowned court", aspect_ratio="16:9", reference=reference)

        assert out == PNG_BYTES
        assert len(adapter.received) == 1
        recorded = adapter.received[0]
        assert recorded.prompt == "a drowned court"
        assert recorded.aspect_ratio == "16:9"
        assert list(recorded.reference_images) == []
        assert self.SENTINEL not in recorded.reference_images
        for ref in recorded.reference_images:
            assert self.SENTINEL not in ref.content

    def test_filter_references_passthrough_when_supported(self):
        """If a hypothetical adapter reports reference support, references
        flow through unchanged — identity equality with the original
        ``ReferenceImage`` confirms no rewriting or reordering happened.
        """

        class _RefCapableAdapter:
            def __init__(self) -> None:
                self._caps = ImageCapabilities(
                    provider_id="test",
                    model="test",
                    supports_reference_images=True,
                    supported_aspect_ratios=frozenset({"1:1"}),
                )

            def capabilities(self) -> ImageCapabilities:
                return self._caps

            async def generate_image(self, prompt: str, *, aspect_ratio: str = "1:1") -> bytes:
                return PNG_BYTES

            async def generate_image_structured(self, input: ImageGenerationInput) -> bytes:
                return PNG_BYTES

        adapter = _RefCapableAdapter()
        reference = ReferenceImage(content=b"x", content_type="image/png")
        out = filter_references_for_adapter(
            adapter,
            ImageGenerationInput(
                prompt="p",
                aspect_ratio="1:1",
                reference_images=(reference,),
            ),
        )
        assert out is not None
        # Identity pass-through: the same object, not a copy.
        assert list(out.reference_images) == [reference]
        assert out.reference_images[0] is reference
        # Adapter still satisfies the runtime-checkable protocol.
        assert isinstance(adapter, ImageProviderAdapter)


# ===========================================================================
# Factory surface — selectors unchanged, capabilities reachable
# ===========================================================================


class TestFactoryAndResolution:
    def test_adapter_for_provider_row_returns_capable_adapter(self):
        adapter = adapter_for_provider_row(
            {
                "provider": "minimax",
                "api_key": "k",
                "base_url": None,
                "model": "image-01",
            }
        )
        caps = capabilities_for_adapter(adapter)
        assert caps.provider_id == "minimax"
        assert caps.supports_reference_images is False

    def test_resolve_image_adapter_still_selects_default(self):
        """The existing selection order must be preserved."""

        class _PG:
            async def providers_list(self):
                return [
                    {
                        "id": "img-g",
                        "provider": "google_ai_studio",
                        "role": "image",
                        "api_key": "g",
                        "status": "connected",
                        "is_default": False,
                        "model": "gemini-2.5-flash-image",
                    },
                    {
                        "id": "img-m",
                        "provider": "minimax",
                        "role": "image",
                        "api_key": "m",
                        "status": "connected",
                        "is_default": True,
                        "model": "image-01",
                        "base_url": None,
                    },
                ]

        adapter = _run(resolve_image_adapter(_PG()))
        assert isinstance(adapter, MiniMaxImageAdapter)
