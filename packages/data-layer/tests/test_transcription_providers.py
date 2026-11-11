"""Tests for the pluggable transcription providers (CF-10 / G02).

The point of the registry is that the capture flow does not care which
backend is in use: a hosted OpenAI-compatible endpoint, a local whisper
install, or a gateway that fronts the workspace's own models. What matters
is that the right adapter is chosen for the configuration, and that a
backend which cannot transcribe says so instead of failing obscurely.

Run:
    uv run pytest packages/data-layer/tests/test_transcription_providers.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from monitor_data.llm.transcription_providers import (
    AUDIO_CAPABLE_PROVIDERS,
    LocalWhisperAdapter,
    OpenAICompatibleTranscriptionAdapter,
    TranscriptionError,
    adapter_for_provider_row,
    local_command_from_env,
    resolve_transcription_adapter,
)


class _FakePostgres:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    async def providers_list(self) -> list[dict[str, Any]]:
        return self.rows


class TestProviderRows:
    def test_an_openai_row_becomes_the_openai_adapter(self) -> None:
        adapter = adapter_for_provider_row(
            {
                "id": "p1",
                "name": "OpenAI",
                "provider": "openai",
                "model": "whisper-1",
                "api_key": "sk-test",
            }
        )

        assert isinstance(adapter, OpenAICompatibleTranscriptionAdapter)
        assert adapter.base_url == "https://api.openai.com/v1"
        assert adapter.model == "whisper-1"

    def test_a_custom_gateway_is_openai_compatible(self) -> None:
        """The workspace's own models plug in through an OpenAI-compatible base URL."""
        adapter = adapter_for_provider_row(
            {
                "id": "p2",
                "name": "House gateway",
                "provider": "custom",
                "model": "house-asr",
                "api_key": "key",
                "base_url": "https://gateway.internal/v1/",
            }
        )

        assert isinstance(adapter, OpenAICompatibleTranscriptionAdapter)
        assert adapter.base_url == "https://gateway.internal/v1"
        assert adapter.model == "house-asr"

    def test_a_provider_without_an_audio_endpoint_is_refused(self) -> None:
        for provider in ("anthropic", "minimax", "ollama"):
            with pytest.raises(TranscriptionError, match="does not expose an audio"):
                adapter_for_provider_row(
                    {
                        "id": "p3",
                        "provider": provider,
                        "model": "m",
                        "api_key": "key",
                    }
                )

    def test_a_provider_without_a_credential_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(TranscriptionError, match="No API key"):
            adapter_for_provider_row(
                {"id": "p4", "provider": "openai", "model": "whisper-1", "api_key": ""}
            )

    def test_an_unknown_provider_type_is_refused(self) -> None:
        with pytest.raises(TranscriptionError, match="Unknown provider type"):
            adapter_for_provider_row({"id": "p5", "provider": "telepathy"})

    def test_the_audio_capable_set_is_explicit(self) -> None:
        assert "openai" in {p.value for p in AUDIO_CAPABLE_PROVIDERS}
        assert "minimax" not in {p.value for p in AUDIO_CAPABLE_PROVIDERS}


class TestResolution:
    async def test_a_transcription_row_is_used(self) -> None:
        postgres = _FakePostgres(
            [
                {
                    "id": "chat",
                    "provider": "openai",
                    "role": "standard",
                    "api_key": "k",
                    "status": "connected",
                },
                {
                    "id": "asr",
                    "provider": "openai",
                    "role": "transcription",
                    "model": "whisper-1",
                    "api_key": "k",
                    "status": "connected",
                    "is_default": True,
                },
            ]
        )

        adapter = await resolve_transcription_adapter(postgres)

        assert adapter is not None
        assert adapter.name == "openai"

    async def test_a_local_install_is_used_when_no_hosted_one_is_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONITOR_TRANSCRIPTION_COMMAND", "whisper-cli -f {audio_path}")
        monkeypatch.setenv("MONITOR_TRANSCRIPTION_MODEL_PATH", "/models/base.bin")
        postgres = _FakePostgres([])

        adapter = await resolve_transcription_adapter(postgres)

        assert isinstance(adapter, LocalWhisperAdapter)
        assert adapter.model_path == "/models/base.bin"

    async def test_nothing_configured_means_no_adapter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("MONITOR_TRANSCRIPTION_COMMAND", raising=False)
        postgres = _FakePostgres([])

        assert await resolve_transcription_adapter(postgres) is None

    async def test_the_local_command_is_read_from_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONITOR_TRANSCRIPTION_COMMAND", "whisper-cli -f {audio_path}")
        assert local_command_from_env() == ["whisper-cli", "-f", "{audio_path}"]


class TestOpenAIAdapter:
    async def test_the_provider_answer_becomes_a_result(self, monkeypatch) -> None:
        captured: dict[str, Any] = {}

        async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
            captured["url"] = str(url)
            headers = kwargs.get("headers") or {}
            captured["auth"] = headers.get("Authorization") or headers.get("authorization")
            return httpx.Response(
                200,
                json={
                    "text": "The council met at dusk.",
                    "language": "en",
                    "duration": 12.5,
                    "segments": [
                        {"id": 0, "start": 0.0, "end": 4.0, "text": " The council met"},
                        {"id": 1, "start": 4.0, "end": 12.5, "text": " at dusk."},
                    ],
                },
            )

        monkeypatch.setattr(httpx.AsyncClient, "post", _post)
        adapter = OpenAICompatibleTranscriptionAdapter(
            api_key="sk-test", base_url="https://api.openai.com/v1", model="whisper-1"
        )

        result = await adapter.transcribe(b"audio-bytes", filename="take.wav")

        assert captured["url"] == "https://api.openai.com/v1/audio/transcriptions"
        assert captured["auth"] == "Bearer sk-test"
        assert result.text == "The council met at dusk."
        assert result.language == "en"
        assert result.duration == 12.5
        assert [s.text for s in result.segments] == ["The council met", "at dusk."]
        assert result.segments[0].end == 4.0

    async def test_a_refusal_is_an_error(self, monkeypatch) -> None:
        async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
            return httpx.Response(429, text="rate limited")

        monkeypatch.setattr(httpx.AsyncClient, "post", _post)
        adapter = OpenAICompatibleTranscriptionAdapter(
            api_key="sk-test", base_url="https://api.openai.com/v1"
        )

        with pytest.raises(TranscriptionError, match="refused the request"):
            await adapter.transcribe(b"audio-bytes")

    async def test_a_missing_credential_is_an_error(self) -> None:
        adapter = OpenAICompatibleTranscriptionAdapter(
            api_key="", base_url="https://api.openai.com/v1"
        )

        with pytest.raises(TranscriptionError, match="No API key"):
            await adapter.transcribe(b"audio-bytes")


class TestLocalAdapter:
    def test_the_local_binary_transcribes(self, tmp_path: Path) -> None:
        script = tmp_path / "fake_whisper.py"
        script.write_text(
            "import json, sys\n"
            "print(json.dumps({\n"
            "    'text': 'The council met at dusk.',\n"
            "    'language': 'en',\n"
            "    'duration': 3.0,\n"
            "    'segments': [{'id': 0, 'start': 0.0, 'end': 3.0, 'text': 'The council met at dusk.'}],\n"
            "}))\n",
            encoding="utf-8",
        )
        adapter = LocalWhisperAdapter(
            command=[sys.executable, str(script), "{audio_path}"], model_path="/models/base.bin"
        )

        import asyncio

        result = asyncio.run(adapter.transcribe(b"audio-bytes", filename="take.wav"))

        assert result.text == "The council met at dusk."
        assert result.provider == "local-whisper"
        assert len(result.segments) == 1

    def test_a_missing_binary_is_an_error(self) -> None:
        adapter = LocalWhisperAdapter(command=["definitely-not-installed-whisper"])

        import asyncio

        with pytest.raises(TranscriptionError, match="was not found"):
            asyncio.run(adapter.transcribe(b"audio-bytes"))

    def test_a_failing_binary_is_an_error(self, tmp_path: Path) -> None:
        script = tmp_path / "failing.py"
        script.write_text("import sys\nsys.stderr.write('boom')\nsys.exit(3)\n", encoding="utf-8")
        adapter = LocalWhisperAdapter(command=[sys.executable, str(script)])

        import asyncio

        with pytest.raises(TranscriptionError, match="failed"):
            asyncio.run(adapter.transcribe(b"audio-bytes"))
