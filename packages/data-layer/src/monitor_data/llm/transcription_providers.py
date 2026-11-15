"""
Pluggable speech-to-text providers (CF-10 / G02).

Audio capture needs a transcription backend, and the workspace may have
several: a local whisper.cpp install that never sends audio anywhere, a
hosted endpoint that does, or a gateway that fronts one of them. Which
one is in use is a *configuration* question, not a code question — the
capture flow must not care.

So the adapters live here, behind one small protocol, and the registry
resolves them from the same ``llm_providers`` rows the chat registry uses
(a row with ``role='transcription'``). Adding a backend is a new adapter
plus a row; nothing in the capture flow changes.

Two families:

- **Hosted** — anything that speaks the OpenAI audio API
  (``POST {base_url}/audio/transcriptions``). That is OpenAI itself, Groq,
  Azure, and every OpenAI-compatible gateway — including a self-hosted
  one, which is how a workspace that fronts its own models plugs in.
- **Local** — a whisper.cpp (or faster-whisper) binary run on the host.
  No egress, no per-minute cost, no vendor key.

The table of which provider types can transcribe is explicit: a chat
provider without an audio endpoint is not silently coerced into one.

LAYER: 1 (data-layer)
IMPORTS FROM: external libraries only + monitor_data.schemas
CALLED BY: agents (Layer 2), UI backend (Layer 3)
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from monitor_data.schemas.llm_config import LLMProviderType, ModelRole

# How long a hosted transcription may take. A long recording is minutes of
# audio; the default is generous on purpose.
_TIMEOUT_SECONDS = 600.0

# Provider types whose endpoints speak the OpenAI audio API. Anything else
# needs its own adapter — the chat providers (Anthropic, MiniMax, MiMo,
# Ollama) do not expose one.
AUDIO_CAPABLE_PROVIDERS: frozenset[LLMProviderType] = frozenset(
    {
        LLMProviderType.OPENAI,
        LLMProviderType.GROQ,
        LLMProviderType.AZURE_OPENAI,
        LLMProviderType.CUSTOM,
    }
)


class TranscriptionError(RuntimeError):
    """A transcription failed — no provider, no credential, or a refusal."""


@dataclass(frozen=True)
class TranscriptionSegment:
    """One stretch of speech."""

    index: int
    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    """What a provider made of an recording."""

    text: str
    language: str | None = None
    duration: float | None = None
    segments: tuple[TranscriptionSegment, ...] = ()
    provider: str = ""
    model: str = ""


class TranscriptionAdapter(Protocol):
    """What every transcription backend has to be able to do."""

    name: str

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "recording.wav",
        content_type: str = "audio/wav",
        language: str | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio blob."""


# ---------------------------------------------------------------------------
# Hosted: the OpenAI audio API
# ---------------------------------------------------------------------------


@dataclass
class OpenAICompatibleTranscriptionAdapter:
    """Transcribes through ``POST {base_url}/audio/transcriptions``.

    Works with OpenAI, Groq, Azure and every OpenAI-compatible gateway —
    including a self-hosted one, which is how a workspace that fronts its
    own models plugs in.
    """

    api_key: str
    base_url: str
    model: str = "whisper-1"
    name: str = "openai-compatible"

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "recording.wav",
        content_type: str = "audio/wav",
        language: str | None = None,
    ) -> TranscriptionResult:
        if not self.api_key:
            raise TranscriptionError("No API key configured for the transcription provider.")
        url = f"{self.base_url.rstrip('/')}/audio/transcriptions"
        files = {"file": (filename, audio, content_type)}
        data: dict[str, Any] = {"model": self.model, "response_format": "verbose_json"}
        if language:
            data["language"] = language

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    data=data,
                )
        except httpx.HTTPError as exc:
            raise TranscriptionError(f"The transcription provider could not be reached: {exc}") from exc

        if response.status_code >= 400:
            raise TranscriptionError(
                f"The transcription provider refused the request ({response.status_code}): "
                f"{response.text[:400]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise TranscriptionError("The transcription provider returned a malformed answer.") from exc
        return _result_from_payload(payload, provider=self.name, model=self.model)


def _result_from_payload(
    payload: dict[str, Any], *, provider: str, model: str
) -> TranscriptionResult:
    """Read a transcription payload, whatever shape the provider used."""
    text = str(payload.get("text") or "")
    segments: list[TranscriptionSegment] = []
    for index, raw in enumerate(payload.get("segments") or []):
        if not isinstance(raw, dict):
            continue
        segments.append(
            TranscriptionSegment(
                index=int(raw.get("id") or index),
                start=float(raw.get("start") or 0.0),
                end=float(raw.get("end") or 0.0),
                text=str(raw.get("text") or "").strip(),
                speaker=(str(raw["speaker"]) if raw.get("speaker") is not None else None),
            )
        )
    duration = payload.get("duration")
    language = payload.get("language")
    return TranscriptionResult(
        text=text,
        language=str(language) if language else None,
        duration=float(duration) if isinstance(duration, (int, float)) else None,
        segments=tuple(segments),
        provider=provider,
        model=model,
    )


# ---------------------------------------------------------------------------
# Local: whisper.cpp / faster-whisper on the host
# ---------------------------------------------------------------------------


@dataclass
class LocalWhisperAdapter:
    """Runs a local transcription binary.

    The command is a template: ``{audio_path}`` is replaced with the path
    of the recording, and the binary must print a JSON object on stdout —
    ``{"text": ..., "segments": [{"start": ..., "end": ..., "text": ...}]}``
    — which is what whisper.cpp's ``--output-json`` and faster-whisper's
    CLI both produce.

    No audio leaves the host.
    """

    command: list[str]
    model_path: str | None = None
    language: str | None = None
    name: str = "local-whisper"
    timeout_seconds: float = _TIMEOUT_SECONDS

    async def transcribe(
        self,
        audio: bytes,
        *,
        filename: str = "recording.wav",
        content_type: str = "audio/wav",
        language: str | None = None,
    ) -> TranscriptionResult:
        if not self.command:
            raise TranscriptionError("No local transcription command is configured.")
        binary = self.command[0]
        if shutil.which(binary) is None and not Path(binary).exists():
            raise TranscriptionError(f"The local transcription binary '{binary}' was not found.")

        suffix = Path(filename).suffix or ".wav"
        with tempfile.TemporaryDirectory(prefix="monitor-audio-") as tmp:
            audio_path = Path(tmp) / f"recording{suffix}"
            audio_path.write_bytes(audio)
            command = [
                part.replace("{audio_path}", str(audio_path)) for part in self.command
            ]
            if self.model_path and "{model_path}" in " ".join(command):
                command = [
                    part.replace("{model_path}", self.model_path) for part in command
                ]
            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError as exc:
                raise TranscriptionError(f"The local transcription could not be started: {exc}") from exc

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=self.timeout_seconds
                )
            except TimeoutError as exc:
                process.kill()
                raise TranscriptionError("The local transcription timed out.") from exc

        if process.returncode != 0:
            detail = stderr.decode("utf-8", "replace").strip()[:400]
            raise TranscriptionError(
                f"The local transcription failed (exit {process.returncode}): {detail}"
            )
        try:
            payload = json.loads(stdout.decode("utf-8", "replace"))
        except ValueError as exc:
            raise TranscriptionError("The local transcription returned malformed output.") from exc
        if not isinstance(payload, dict):
            raise TranscriptionError("The local transcription returned an unexpected answer.")
        return _result_from_payload(
            payload, provider=self.name, model=self.model_path or "local"
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _env_key_for(provider: LLMProviderType) -> str:
    """The credential fallback, mirroring the image providers' lookup."""
    if provider is LLMProviderType.MINIMAX:
        return os.getenv("MINIMAX_TOKEN", "").strip() or os.getenv("MINIMAX_API_KEY", "").strip()
    if provider is LLMProviderType.GOOGLE_AI_STUDIO:
        return os.getenv("GOOGLE_API_KEY", "").strip()
    if provider is LLMProviderType.OPENAI:
        return os.getenv("OPENAI_API_KEY", "").strip()
    if provider is LLMProviderType.GROQ:
        return os.getenv("GROQ_API_KEY", "").strip()
    if provider is LLMProviderType.AZURE_OPENAI:
        return os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    return ""


def adapter_for_provider_row(row: dict[str, Any]) -> TranscriptionAdapter:
    """Build the transcription adapter for one ``llm_providers`` row.

    Raises:
        TranscriptionError: When the provider type cannot transcribe, or
            has no credential.
    """
    provider_name = str(row.get("provider") or "").strip()
    try:
        provider = LLMProviderType(provider_name)
    except ValueError as exc:
        raise TranscriptionError(
            f"Unknown provider type '{provider_name}' for transcription."
        ) from exc

    if provider not in AUDIO_CAPABLE_PROVIDERS:
        raise TranscriptionError(
            f"Provider '{provider.value}' does not expose an audio transcription endpoint. "
            "Use a hosted OpenAI-compatible endpoint or a local whisper install."
        )

    api_key = (row.get("api_key") or "").strip() or _env_key_for(provider)
    if not api_key:
        raise TranscriptionError(
            f"No API key configured for the transcription provider '{row.get('id')}'."
        )

    base_url = (row.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        base_url = _DEFAULT_BASE_URLS.get(provider, "")
    if not base_url:
        raise TranscriptionError(
            f"No base URL configured for the transcription provider '{row.get('id')}'."
        )

    return OpenAICompatibleTranscriptionAdapter(
        api_key=api_key,
        base_url=base_url,
        model=(row.get("model") or "").strip() or "whisper-1",
        name=str(row.get("name") or provider.value),
    )


_DEFAULT_BASE_URLS: dict[LLMProviderType, str] = {
    LLMProviderType.OPENAI: "https://api.openai.com/v1",
    LLMProviderType.GROQ: "https://api.groq.com/openai/v1",
}


def local_command_from_env() -> list[str]:
    """The local transcription command, when the host has one configured.

    ``MONITOR_TRANSCRIPTION_COMMAND`` holds a shell-style command line
    (``whisper-cli -m {model_path} -f {audio_path} -oj``); it is split on
    whitespace, so a path with spaces needs quoting.
    """
    raw = os.getenv("MONITOR_TRANSCRIPTION_COMMAND", "").strip()
    if not raw:
        return []
    return [part for part in raw.split() if part]


def local_model_path_from_env() -> str:
    """The local model file, when one is configured."""
    return os.getenv("MONITOR_TRANSCRIPTION_MODEL_PATH", "").strip()


async def resolve_transcription_adapter(postgres: Any) -> TranscriptionAdapter | None:
    """Pick the transcription backend for this workspace.

    Preference: a ``role='transcription'`` provider row (default first,
    then connected, then any) — and a local install when no hosted one is
    configured. Returns None when neither is available.
    """
    rows = await postgres.providers_list()
    transcription_rows = [
        r
        for r in rows
        if (r.get("role") or "").strip().lower() == ModelRole.TRANSCRIPTION.value
    ]
    transcription_rows.sort(
        key=lambda r: (
            not r.get("is_default"),
            (r.get("status") or "").lower() != "connected",
        )
    )
    for row in transcription_rows:
        try:
            return adapter_for_provider_row(row)
        except TranscriptionError:
            continue

    command = local_command_from_env()
    if command:
        return LocalWhisperAdapter(
            command=command,
            model_path=local_model_path_from_env() or None,
        )
    return None


__all__ = [
    "AUDIO_CAPABLE_PROVIDERS",
    "LocalWhisperAdapter",
    "OpenAICompatibleTranscriptionAdapter",
    "TranscriptionAdapter",
    "TranscriptionError",
    "TranscriptionResult",
    "TranscriptionSegment",
    "adapter_for_provider_row",
    "local_command_from_env",
    "local_model_path_from_env",
    "resolve_transcription_adapter",
]
