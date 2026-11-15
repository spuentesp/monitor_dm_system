"""
Light RP router — the Conversatory's Phase 7 surfaces.

One-click start with any character (a card or a universe NPC), streaming
send, the "what this character remembers about you" view with per-memory
delete, and graduating a light chat into a guided-start campaign.

Service logic lives in ``character_conversation`` (same ownership); this
module is the thin HTTP surface. Mounted alongside ``entities`` so the
Conversatory's URLs stay in the ``/api/entities/characters/...`` family.

LAYER: 3 (UI backend / FastAPI router)
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.base import EntityType
from monitor_data.schemas.entities import EntityFilter
from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities
from monitor_ui.auth import Principal, get_current_user, get_postgres
from monitor_ui.ownership import (
    require_character_owner,
    require_entity_owner,
    require_universe_owner,
    resource_route_guard,
)

from . import character_conversation as cc

log = structlog.get_logger()

router = APIRouter(dependencies=[Depends(resource_route_guard)])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UniverseCharacterStartRequest(BaseModel):
    """One-click chat with a character in a universe."""

    entity_id: str = Field(..., description="Neo4j entity id of the universe character")
    persona_character_id: str | None = Field(default=None, description="Optional persona card to play as")


class MemoryListResponse(BaseModel):
    """What this character remembers about the user."""

    memories: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class GraduatePrepareResponse(BaseModel):
    """Incarnation + guided-start opening question for graduation."""

    character_id: str
    universe_id: str
    entity_id: str
    version_id: str
    start_options: list[dict[str, Any]] = Field(default_factory=list)
    start_options_source: str = "none"
    question: str = ""
    suggested_answers: list[str] = Field(default_factory=list)


class GraduateRequest(BaseModel):
    """Graduate a light chat into a campaign (guided start handoff)."""

    universe_id: str | None = None
    persona_character_id: str | None = None
    start_answer: str = Field(default="", description="The player's answer to the start question")
    start_options: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The options the player saw (echoed back for choice resolution)",
    )
    question_text: str = ""
    tone: str | None = None


class StreamSendRequest(BaseModel):
    """One player line to stream a reply for."""

    text: str = Field(..., min_length=1)
    include_cross_incarnation: bool = False


class ConversationTurnOut(BaseModel):
    """One persisted turn of a light-RP conversation."""

    turn_index: int
    speaker_role: str
    entity_name: str | None = None
    text: str
    emotional_state: str | None = None
    timestamp: str | None = None


class ConversationTranscriptResponse(BaseModel):
    """Full transcript of a conversation, oldest first — used to reopen a past chat."""

    conversation_id: str
    status: str
    turns: list[ConversationTurnOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# One-click start
# ---------------------------------------------------------------------------


@router.get("/universes/{universe_id}/characters")
async def list_universe_characters(
    universe_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> list[dict[str, Any]]:
    """Chat-capable characters in a universe (for the one-click start picker)."""
    from uuid import UUID

    await require_universe_owner(db, principal, universe_id)
    result = neo4j_list_entities(
        EntityFilter(universe_id=UUID(universe_id), entity_type=EntityType.CHARACTER, limit=limit)
    )
    entities = getattr(result, "entities", result)
    out: list[dict[str, Any]] = []
    for entity in entities or []:
        data: dict[str, Any] = entity.model_dump() if hasattr(entity, "model_dump") else dict(cast(Any, entity))
        out.append(
            {
                "entity_id": str(data.get("id", "")),
                "name": data.get("name", ""),
                "description": data.get("description", ""),
                "universe_id": str(data.get("universe_id", "")),
            }
        )
    return out


@router.post("/universe-characters/start")
async def start_universe_character_chat(
    body: UniverseCharacterStartRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict[str, Any]:
    """One action: open a chat with a universe character (first message included)."""
    await require_entity_owner(db, principal, body.entity_id)
    if body.persona_character_id:
        await require_character_owner(principal, body.persona_character_id)
    try:
        return await cc.start_universe_character_chat(
            body.entity_id,
            persona_character_id=body.persona_character_id,
            owner_id=str(principal.user_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001  # reason: intentional boundary: documented failure tolerance (in start_universe_character_chat)
        log.warning("universe_character_chat_start_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Could not start chat: {exc}") from exc


# ---------------------------------------------------------------------------
# Streaming send
# ---------------------------------------------------------------------------


@router.post("/characters/{character_id}/conversations/{conversation_id}/send-stream")
async def stream_character_message(
    character_id: str,
    conversation_id: str,
    body: StreamSendRequest,
    principal: Principal = Depends(get_current_user),
) -> StreamingResponse:
    """Send one line; stream the reply as SSE token events.

    Event shapes: ``{"type": "token", "text": ...}`` per chunk, then one
    ``{"type": "done", ...}`` with the emotional / relationship read. NPC
    memory writes happen after the stream completes.
    """
    await require_character_owner(principal, character_id)

    stream = await cc.send_message_stream(
        conversation_id,
        body.text,
        body.include_cross_incarnation,
        character_id=character_id,
    )

    # Pull the first event eagerly so resolution / generation failures map to
    # a real HTTP status instead of a truncated 200.
    try:
        first = await stream.__anext__()
    except StopAsyncIteration:
        first = None
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=f"Conversation {conversation_id} is no longer active.") from exc
    except Exception as exc:  # noqa: BLE001  # reason: intentional boundary: documented failure tolerance (in stream_character_message)
        log.warning("conversation_stream_send_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Reply failed: {exc}") from exc

    async def _sse() -> AsyncIterator[str]:
        async def _events() -> AsyncIterator[dict[str, Any]]:
            if first is not None:
                yield first
            async for event in stream:
                yield event

        async for event in _events():
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _sse(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/characters/{character_id}/conversations/{conversation_id}/turns",
    response_model=ConversationTranscriptResponse,
)
async def get_conversation_turns(
    character_id: str,
    conversation_id: str,
    principal: Principal = Depends(get_current_user),
) -> ConversationTranscriptResponse:
    """Full transcript of a light-RP chat, oldest first — for reopening a past conversation."""
    await require_character_owner(principal, character_id)
    transcript = await asyncio.to_thread(cc.get_conversation_transcript, character_id, conversation_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="Conversation not found for this character.")
    return ConversationTranscriptResponse(**transcript)


# ---------------------------------------------------------------------------
# "What this character remembers about you"
# ---------------------------------------------------------------------------


@router.get("/characters/{character_id}/memories/about-you", response_model=MemoryListResponse)
async def get_memories_about_you(
    character_id: str,
    universe_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    principal: Principal = Depends(get_current_user),
) -> MemoryListResponse:
    """List what this character remembers about the user, newest first."""
    await require_character_owner(principal, character_id)
    try:
        return MemoryListResponse(**cc.list_memories_about_you(character_id, universe_id=universe_id, limit=limit))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/characters/{character_id}/memories/{memory_id}", status_code=204)
async def delete_memory(
    character_id: str,
    memory_id: str,
    principal: Principal = Depends(get_current_user),
) -> None:
    """Delete one memory — the view and semantic recall both forget it."""
    await require_character_owner(principal, character_id)
    try:
        deleted = cc.delete_character_memory(character_id, memory_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found for this character.")


# ---------------------------------------------------------------------------
# Graduate to a campaign
# ---------------------------------------------------------------------------


@router.get("/characters/{character_id}/graduate/prepare", response_model=GraduatePrepareResponse)
async def graduate_prepare(
    character_id: str,
    universe_id: str | None = Query(default=None),
    tone: str | None = Query(default=None),
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> GraduatePrepareResponse:
    """Step 1: incarnation in the chosen universe + the guided start's question.

    Calls the Phase 2 guided-start entry points (WorldSeed start options,
    session_zero's start question) — no re-implementation.
    """
    await require_character_owner(principal, character_id)
    if universe_id:
        await require_universe_owner(db, principal, universe_id)
    try:
        result = await cc.graduate_prepare(character_id, universe_id=universe_id, tone=tone)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001  # reason: intentional boundary: documented failure tolerance (in graduate_prepare)
        log.warning("graduate_prepare_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Graduate preparation failed: {exc}") from exc
    return GraduatePrepareResponse(**result)


@router.post("/characters/{character_id}/graduate")
async def graduate_to_campaign(
    character_id: str,
    body: GraduateRequest,
    principal: Principal = Depends(get_current_user),
    db: PostgresClient = Depends(get_postgres),
) -> dict[str, Any]:
    """Step 2: carry character, persona and memories into the guided start.

    Returns ``session_create`` — the exact ``POST /api/chat`` payload that
    opens the guided-start campaign with this character bound.
    """
    await require_character_owner(principal, character_id)
    if body.universe_id:
        await require_universe_owner(db, principal, body.universe_id)
    if body.persona_character_id:
        await require_character_owner(principal, body.persona_character_id)
    try:
        return await cc.graduate_to_campaign(
            character_id,
            universe_id=body.universe_id,
            persona_character_id=body.persona_character_id,
            start_answer=body.start_answer,
            start_options=body.start_options,
            question_text=body.question_text,
            tone=body.tone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001  # reason: intentional boundary: documented failure tolerance (in graduate_to_campaign)
        log.warning("graduate_to_campaign_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Graduation failed: {exc}") from exc
