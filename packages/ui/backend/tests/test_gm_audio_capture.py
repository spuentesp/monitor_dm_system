"""CF-10 — the audio capture routes.

A recording goes in; a transcript comes out; a reviewed segment becomes
the same capture proposals a typed entry produces. The transcription
backend is configuration — the routes do not care which one is in use.

Use Cases: CF-10 (G02)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_ui.main import app
from tests.behavior._hermetic_stack import HermeticStack

client = TestClient(app)

_local_auth = pytest.mark.usefixtures("local_auth_mode")


@pytest.fixture
def hermetic(monkeypatch: pytest.MonkeyPatch) -> Any:
    stack = HermeticStack()
    stack.install(monkeypatch)
    try:
        yield stack
    finally:
        stack.uninstall()


class _FakeMinio:
    def __init__(self) -> None:
        self.uploads: dict[str, bytes] = {}

    async def upload(self, key: str, data: bytes, content_type: str = "", **kwargs: Any) -> None:
        self.uploads[key] = data

    async def download(self, key: str, **kwargs: Any) -> bytes:
        return self.uploads.get(key, b"")


def _stub_backend(monkeypatch: pytest.MonkeyPatch, *, ok: bool = True) -> None:
    """Point the capture agent at a scripted transcription backend."""
    from monitor_data.llm import transcription_providers as providers

    class _Adapter:
        name = "fake-asr"
        model = "fake-model"

        async def transcribe(self, audio, **kwargs):  # noqa: ANN001, ANN202
            from monitor_data.llm.transcription_providers import (
                TranscriptionResult,
                TranscriptionSegment,
            )

            if not ok:
                from monitor_data.llm.transcription_providers import TranscriptionError

                raise TranscriptionError("the backend refused the recording")
            return TranscriptionResult(
                text="The council met at dusk.",
                language="en",
                duration=3.0,
                segments=(
                    TranscriptionSegment(
                        index=0, start=0.0, end=3.0, text="The council met at dusk."
                    ),
                ),
                provider="fake-asr",
                model="fake-model",
            )

    async def _resolve(postgres: Any) -> Any:
        return _Adapter()

    monkeypatch.setattr(providers, "resolve_transcription_adapter", _resolve)


@pytest.fixture
def minio(monkeypatch: pytest.MonkeyPatch) -> _FakeMinio:
    fake = _FakeMinio()
    monkeypatch.setattr("monitor_ui.routers.gm_tools.get_minio_client", lambda: fake)
    return fake


class TestTranscribeRoute:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_recording_becomes_a_transcript(
        self, hermetic: HermeticStack, minio: _FakeMinio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_backend(monkeypatch)
        universe_id = uuid4()

        resp = client.post(
            "/api/gm/audio/transcribe",
            data={"universe_id": str(universe_id)},
            files={"file": ("take.wav", b"audio-bytes", "audio/wav")},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["text"] == "The council met at dusk."
        assert body["provider"] == "fake-asr"
        assert len(body["segments"]) == 1
        assert body["segments"][0]["text"] == "The council met at dusk."

    @pytest.mark.usefixtures("local_auth_mode")
    def test_the_recording_is_stored_under_an_owner_scoped_key(
        self, hermetic: HermeticStack, minio: _FakeMinio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_backend(monkeypatch)
        universe_id = uuid4()

        resp = client.post(
            "/api/gm/audio/transcribe",
            data={"universe_id": str(universe_id)},
            files={"file": ("take.wav", b"audio-bytes", "audio/wav")},
        )

        keys = list(minio.uploads)
        assert len(keys) == 1
        assert keys[0].startswith(f"audio/{universe_id}/")
        assert resp.json()["audio_key"] == keys[0]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_the_transcript_is_readable_afterwards(
        self, hermetic: HermeticStack, minio: _FakeMinio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_backend(monkeypatch)
        universe_id = uuid4()

        created = client.post(
            "/api/gm/audio/transcribe",
            data={"universe_id": str(universe_id)},
            files={"file": ("take.wav", b"audio-bytes", "audio/wav")},
        )
        transcript_id = created.json()["transcript_id"]

        read = client.get(f"/api/gm/audio/transcripts/{transcript_id}")

        assert read.status_code == 200, read.text
        assert read.json()["transcript_id"] == transcript_id
        assert read.json()["text"] == "The council met at dusk."

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_refused_recording_is_reported(
        self, hermetic: HermeticStack, minio: _FakeMinio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_backend(monkeypatch, ok=False)

        resp = client.post(
            "/api/gm/audio/transcribe",
            data={"universe_id": str(uuid4())},
            files={"file": ("take.wav", b"audio-bytes", "audio/wav")},
        )

        assert resp.status_code == 422
        assert "refused the recording" in resp.json()["detail"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_empty_recording_is_refused(
        self, hermetic: HermeticStack, minio: _FakeMinio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_backend(monkeypatch)

        resp = client.post(
            "/api/gm/audio/transcribe",
            data={"universe_id": str(uuid4())},
            files={"file": ("take.wav", b"", "audio/wav")},
        )

        assert resp.status_code == 400

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_unknown_transcript_is_a_404(self, hermetic: HermeticStack) -> None:
        resp = client.get(f"/api/gm/audio/transcripts/{uuid4()}")
        assert resp.status_code == 404


class TestQueueSegmentRoute:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_reviewed_segment_becomes_a_capture_proposal(
        self, hermetic: HermeticStack, minio: _FakeMinio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_backend(monkeypatch)
        universe_id = uuid4()
        scene_id = uuid4()
        hermetic.seed(
            "scenes",
            [
                {
                    "scene_id": str(scene_id),
                    "story_id": str(uuid4()),
                    "universe_id": str(universe_id),
                    "title": "The council",
                    "purpose": "Attend the council.",
                    "status": "active",
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            ],
        )
        created = client.post(
            "/api/gm/audio/transcribe",
            data={"universe_id": str(universe_id), "scene_id": str(scene_id)},
            files={"file": ("take.wav", b"audio-bytes", "audio/wav")},
        )
        transcript_id = created.json()["transcript_id"]

        # The insight extraction is the CF-1 path; stub it with one fact.
        from monitor_agents.ingestion.capture_insights import CaptureInsight, CaptureInsightAgent

        async def _analyze(self, universe_id, entry_text):  # noqa: ANN001, ANN202
            return CaptureInsight(
                participants=["Mira"],
                locations=["the Customs House"],
                candidate_facts=["The harbour council met at dusk."],
            )

        monkeypatch.setattr(CaptureInsightAgent, "analyze_entry", _analyze)

        resp = client.post(
            f"/api/gm/audio/transcripts/{transcript_id}/queue",
            json={"segment_index": 0, "text": "The council met at dusk."},
        )

        assert resp.status_code == 200, resp.text
        proposal_ids = resp.json()["proposal_ids"]
        assert len(proposal_ids) == 1

        staged = hermetic.collection("proposed_changes").find_one(
            {"proposal_id": proposal_ids[0]}
        )
        assert staged is not None
        assert staged["status"] == "pending"
        assert staged["content"]["statement"] == "The harbour council met at dusk."
        assert staged["source"] == f"audio_segment:{transcript_id}:0"

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_unknown_segment_is_refused(
        self, hermetic: HermeticStack, minio: _FakeMinio, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_backend(monkeypatch)
        created = client.post(
            "/api/gm/audio/transcribe",
            data={"universe_id": str(uuid4())},
            files={"file": ("take.wav", b"audio-bytes", "audio/wav")},
        )
        transcript_id = created.json()["transcript_id"]

        resp = client.post(
            f"/api/gm/audio/transcripts/{transcript_id}/queue",
            json={"segment_index": 99},
        )

        assert resp.status_code == 422
