"""
AudioCaptureAgent — a recording becomes a capture entry (CF-10 / G02).

Audio is another input mode for the Session Recorder, not a second canon
path. The agent transcribes a recording with whichever backend the
workspace has configured, stores the transcript and its segments, and
turns a *reviewed* segment into the same candidate proposals a typed entry
produces. Canon still only moves through the CF-8 queue.

The backend is chosen by configuration, not by code: a hosted
OpenAI-compatible endpoint, a local whisper install, or nothing at all —
in which case the agent says so plainly rather than pretending.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1 schemas + MCP tools), monitor_agents.base
CALLED BY: UI backend routers (Layer 3)
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog
from monitor_agents.base import BaseAgent
from monitor_data.schemas.transcripts import (
    Transcript,
    TranscriptCreate,
    TranscriptSegmentCreate,
    TranscriptUpdate,
)

log = structlog.get_logger()


def _as_dict(raw: Any) -> dict[str, Any]:
    """A tool result as a dict (the MCP layer may hand back JSON text)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


class AudioCaptureError(RuntimeError):
    """Audio capture could not be carried out."""


class AudioCaptureAgent(BaseAgent):
    """Transcribes recordings and feeds them into the capture flow."""

    def __init__(self, agent_id: str | None = None, model: str | None = None) -> None:
        super().__init__(
            agent_type="AudioCaptureAgent",
            agent_id=agent_id or "audio-capture-agent",
            model=model,
        )

    async def run(self) -> None:
        """Implemented for BaseAgent compliance; routes call the methods below."""

    async def transcribe(
        self,
        audio: bytes,
        *,
        universe_id: UUID,
        owner_id: str,
        filename: str = "recording.wav",
        content_type: str = "audio/wav",
        session_id: UUID | None = None,
        scene_id: UUID | None = None,
        story_id: UUID | None = None,
        language: str | None = None,
        audio_key: str | None = None,
    ) -> Transcript:
        """Transcribe a recording and store the transcript.

        Args:
            audio: The recording's bytes.
            universe_id: The universe the recording belongs to.
            owner_id: The GM who owns it.
            filename: The recording's file name (the provider uses it for
                the file name it is sent under).
            content_type: The recording's media type.
            session_id: The recording session it belongs to.
            scene_id: The scene the recording covers.
            story_id: The story it belongs to.
            language: A language hint, when the GM knows it.
            audio_key: Where the recording is stored, when it was kept.

        Returns:
            The stored transcript.

        Raises:
            AudioCaptureError: When no transcription backend is configured,
                or the backend refused the recording.
        """
        adapter = await self._resolve_adapter()
        try:
            result = await adapter.transcribe(
                audio,
                filename=filename,
                content_type=content_type,
                language=language,
            )
        except Exception as exc:  # noqa: BLE001  # reason: the provider's failure is the caller's answer
            raise AudioCaptureError(str(exc)) from exc

        segments = [
            TranscriptSegmentCreate(
                index=segment.index,
                start=segment.start,
                end=segment.end,
                text=segment.text,
                speaker=segment.speaker,
            )
            for segment in result.segments
            if segment.text.strip()
        ]

        raw = await self.call_tool(
            "mongodb_create_transcript",
            {
                "params": TranscriptCreate(
                    universe_id=universe_id,
                    story_id=story_id,
                    session_id=session_id,
                    scene_id=scene_id,
                    owner_id=owner_id,
                    text=result.text,
                    language=result.language,
                    duration=result.duration,
                    provider=result.provider,
                    model=result.model,
                    audio_key=audio_key,
                    segments=segments,
                ).model_dump(mode="json")
            },
        )
        payload = _as_dict(raw)
        if not payload:
            raise AudioCaptureError("The transcript could not be stored.")
        log.info(
            "audio_transcribed",
            provider=result.provider,
            model=result.model,
            segments=len(segments),
            duration=result.duration,
        )
        try:
            return Transcript.model_validate(payload)
        except Exception as exc:  # noqa: BLE001  # reason: a malformed transcript degrades to a failure, not a silent loss
            raise AudioCaptureError("The stored transcript could not be read back.") from exc

    async def update_transcript(
        self,
        transcript_id: UUID,
        *,
        text: str | None = None,
        segments: list[TranscriptSegmentCreate] | None = None,
    ) -> Transcript | None:
        """Apply the GM's edits to a transcript (edited text, reviewed segments)."""
        raw = await self.call_tool(
            "mongodb_update_transcript",
            {
                "transcript_id": str(transcript_id),
                "params": TranscriptUpdate(text=text, segments=segments).model_dump(
                    mode="json", exclude_none=True
                ),
            },
        )
        payload = _as_dict(raw)
        if not payload:
            return None
        try:
            return Transcript.model_validate(payload)
        except Exception as exc:  # noqa: BLE001  # reason: a malformed transcript is a failure, not a silent loss
            raise AudioCaptureError("The stored transcript could not be read back.") from exc

    async def queue_segment(
        self,
        transcript_id: UUID,
        segment_index: int,
        *,
        entry_text: str | None = None,
    ) -> list[str]:
        """Turn one reviewed segment into capture proposals (the CF-1 path).

        A segment becomes a capture entry, and the entry goes through the
        same insight extraction a typed entry does — so the proposals that
        come out are the same proposals the GM would have got by typing.

        Args:
            transcript_id: The transcript the segment belongs to.
            segment_index: Which segment to queue.
            entry_text: The GM's corrected text, when they edited it.

        Returns:
            The ids of the staged proposals.
        """
        from monitor_agents.ingestion.capture_insights import CaptureInsightAgent

        raw = await self.call_tool(
            "mongodb_get_transcript", {"transcript_id": str(transcript_id)}
        )
        transcript = _as_dict(raw)
        if not transcript:
            raise AudioCaptureError("The transcript could not be read.")
        segments = transcript.get("segments") or []
        segment = next(
            (s for s in segments if int(s.get("index") or 0) == segment_index), None
        )
        if segment is None:
            raise AudioCaptureError(f"The transcript has no segment {segment_index}.")

        text = (entry_text or str(segment.get("text") or "")).strip()
        if not text:
            raise AudioCaptureError("The segment has no text to capture.")
        if not transcript.get("scene_id") and not transcript.get("story_id"):
            # A proposal has to belong to a scene or a story, exactly as a
            # typed capture entry does.
            raise AudioCaptureError(
                "This transcript is not attached to a scene or a story, so its "
                "segments cannot be queued as capture proposals."
            )

        universe_id = transcript.get("universe_id")
        insight = await CaptureInsightAgent().analyze_entry(
            universe_id=UUID(str(universe_id)),
            entry_text=text,
        )
        proposals = insight.candidate_facts
        if not proposals:
            return []

        from monitor_data.schemas.base import Authority, ProposalType
        from monitor_data.schemas.proposed_changes import ProposedChangeCreate

        staged: list[str] = []
        for statement in proposals:
            created = await self.call_tool(
                "mongodb_create_proposed_change",
                {
                    "params": ProposedChangeCreate(
                        scene_id=UUID(str(transcript["scene_id"]))
                        if transcript.get("scene_id")
                        else None,
                        story_id=UUID(str(transcript["story_id"]))
                        if transcript.get("story_id")
                        else None,
                        change_type=ProposalType.FACT,
                        content={
                            "statement": statement,
                            "universe_id": universe_id,
                            "source_segment": segment_index,
                        },
                        confidence=0.8,
                        authority=Authority.GM,
                        proposer="AudioCaptureAgent",
                        source=f"audio_segment:{transcript_id}:{segment_index}",
                        proposal_type="capture_candidate_fact",
                    ).model_dump(mode="json")
                },
            )
            payload = _as_dict(created)
            proposal_id = str(payload.get("proposal_id") or "")
            if proposal_id:
                staged.append(proposal_id)
        log.info(
            "audio_segment_queued",
            transcript_id=str(transcript_id),
            segment_index=segment_index,
            proposals=len(staged),
        )
        return staged

    async def _resolve_adapter(self) -> Any:
        """The transcription backend this workspace has configured."""
        from monitor_data.db.postgres import get_postgres_client
        from monitor_data.llm.transcription_providers import (
            resolve_transcription_adapter,
        )

        try:
            adapter = await resolve_transcription_adapter(get_postgres_client())
        except Exception as exc:  # noqa: BLE001  # reason: a registry failure is a configuration failure
            raise AudioCaptureError(
                f"The transcription backend could not be resolved: {exc}"
            ) from exc
        if adapter is None:
            raise AudioCaptureError(
                "No transcription backend is configured. Set up a provider with "
                "role='transcription', or configure MONITOR_TRANSCRIPTION_COMMAND "
                "for a local whisper install."
            )
        return adapter


__all__ = ["AudioCaptureAgent", "AudioCaptureError"]
