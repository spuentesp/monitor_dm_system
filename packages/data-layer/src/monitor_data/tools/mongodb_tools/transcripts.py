"""Transcript storage (CF-10 / G02).

A transcript is the GM's recording turned into text: the whole thing, and
its segments. The segments are what the capture flow consumes — one
segment becomes one entry in the Session Recorder, exactly as a typed
entry does.

Mongo only. Nothing here writes to Neo4j; a transcript becomes canon only
through the CF-1 pipeline and then the CF-8 queue, like any other entry.

LAYER: 1 (data-layer)
IMPORTS FROM: external libraries + data-layer db modules only
CALLED BY: agents (Layer 2) via MCP, UI backend (Layer 3)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.transcripts import (
    Transcript,
    TranscriptCreate,
    TranscriptSegment,
    TranscriptUpdate,
)

COLLECTION = "transcripts"


def _doc_to_transcript(doc: dict[str, Any]) -> Transcript:
    """A stored transcript document as its response model."""
    segments = [
        TranscriptSegment(
            id=UUID(str(segment.get("id"))),
            transcript_id=UUID(str(doc["transcript_id"])),
            index=int(segment.get("index") or 0),
            start=float(segment.get("start") or 0.0),
            end=float(segment.get("end") or 0.0),
            text=str(segment.get("text") or ""),
            speaker=segment.get("speaker"),
            reviewed=bool(segment.get("reviewed", False)),
        )
        for segment in doc.get("segments") or []
    ]
    return Transcript(
        transcript_id=UUID(str(doc["transcript_id"])),
        universe_id=UUID(str(doc["universe_id"])),
        story_id=UUID(str(doc["story_id"])) if doc.get("story_id") else None,
        session_id=UUID(str(doc["session_id"])) if doc.get("session_id") else None,
        scene_id=UUID(str(doc["scene_id"])) if doc.get("scene_id") else None,
        owner_id=str(doc.get("owner_id") or ""),
        text=str(doc.get("text") or ""),
        language=doc.get("language"),
        duration=doc.get("duration"),
        provider=str(doc.get("provider") or ""),
        model=str(doc.get("model") or ""),
        audio_key=doc.get("audio_key"),
        segments=segments,
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at") or doc["created_at"],
    )


def mongodb_create_transcript(params: TranscriptCreate) -> Transcript:
    """Store a transcript and its segments.

    Authority: AudioCaptureAgent / UI backend
    Collection: transcripts
    """
    now = datetime.now(UTC)
    transcript_id = uuid4()
    segments = [
        {
            "id": str(uuid4()),
            "index": segment.index,
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
            "speaker": segment.speaker,
            "reviewed": segment.reviewed,
        }
        for segment in params.segments
    ]
    doc = {
        "transcript_id": str(transcript_id),
        "universe_id": str(params.universe_id),
        "story_id": str(params.story_id) if params.story_id else None,
        "session_id": str(params.session_id) if params.session_id else None,
        "scene_id": str(params.scene_id) if params.scene_id else None,
        "owner_id": params.owner_id,
        "text": params.text,
        "language": params.language,
        "duration": params.duration,
        "provider": params.provider,
        "model": params.model,
        "audio_key": params.audio_key,
        "segments": segments,
        "created_at": now,
        "updated_at": now,
    }
    get_mongodb_client().get_collection(COLLECTION).insert_one(doc)
    return _doc_to_transcript(doc)


def mongodb_get_transcript(transcript_id: UUID) -> Transcript | None:
    """One transcript, or None when there is none.

    Authority: * (read-only)
    Collection: transcripts
    """
    doc = get_mongodb_client().get_collection(COLLECTION).find_one(
        {"transcript_id": str(transcript_id)}
    )
    return _doc_to_transcript(doc) if doc else None


def mongodb_list_transcripts(
    universe_id: UUID | None = None,
    session_id: UUID | None = None,
    limit: int = 50,
) -> list[Transcript]:
    """The transcripts of a universe or a recording session, newest first.

    Authority: * (read-only)
    Collection: transcripts
    """
    query: dict[str, Any] = {}
    if universe_id is not None:
        query["universe_id"] = str(universe_id)
    if session_id is not None:
        query["session_id"] = str(session_id)
    collection = get_mongodb_client().get_collection(COLLECTION)
    cursor = collection.find(query).sort("created_at", -1).limit(max(1, min(limit, 200)))
    return [_doc_to_transcript(dict(doc)) for doc in cursor]


def mongodb_update_transcript(
    transcript_id: UUID, params: TranscriptUpdate
) -> Transcript | None:
    """Apply the GM's edits to a transcript (edited text, reviewed segments).

    Authority: UI backend
    Collection: transcripts
    """
    collection = get_mongodb_client().get_collection(COLLECTION)
    doc = collection.find_one({"transcript_id": str(transcript_id)})
    if doc is None:
        return None
    update: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if params.text is not None:
        update["text"] = params.text
    if params.segments is not None:
        update["segments"] = [
            {
                "id": str(uuid4()),
                "index": segment.index,
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "speaker": segment.speaker,
                "reviewed": segment.reviewed,
            }
            for segment in params.segments
        ]
    collection.update_one({"transcript_id": str(transcript_id)}, {"$set": update})
    updated = collection.find_one({"transcript_id": str(transcript_id)})
    return _doc_to_transcript(updated) if updated else None


def mongodb_delete_transcript(transcript_id: UUID) -> bool:
    """Delete a transcript (the GM asked for the recording to be forgotten).

    Authority: UI backend
    Collection: transcripts
    """
    result = get_mongodb_client().get_collection(COLLECTION).delete_one(
        {"transcript_id": str(transcript_id)}
    )
    return bool(getattr(result, "deleted_count", 0))


__all__ = [
    "mongodb_create_transcript",
    "mongodb_delete_transcript",
    "mongodb_get_transcript",
    "mongodb_list_transcripts",
    "mongodb_update_transcript",
]
