"""OpenAI-compatible ``/v1/chat/completions`` endpoint.

Top-of-funnel surface that turns RisuAI, SillyTavern, LiteLLM, and any
other OpenAI-shaped client into a MONITOR frontend.

Routing modes (chosen by the request body):

- **Plain OpenAI** (no session fields): one LM call via the registry.
  Supports streaming (SSE) and non-streaming.
- **Session mode** (``monitor_session_id`` or ``character_id``): the request
  is routed through the light-RP conversation loop, so the response benefits
  from MONITOR's persona binding, lorebook scanning, and NPC memory. The
  reply is non-streaming in v2 — the conversation loop has no streaming
  surface yet, and ``stream=true`` is rejected explicitly so the client
  surfaces the limitation rather than getting a misleading single chunk.

LAYER: 3 (UI backend)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from monitor_agents.llm_registry import LLMRegistry
from monitor_data.db.postgres import get_postgres_client
from monitor_data.schemas.llm_config import ModelRole

logger = structlog.get_logger()

router = APIRouter()


class OpenAIMessage(BaseModel):
    role: str = Field(description='"system" | "user" | "assistant"')
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="monitor-default", description="Client-facing model name; advisory only in v2.")
    messages: list[OpenAIMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = False

    # Session-mode fields. Either ``monitor_session_id`` (resume) or
    # ``character_id`` (open a new conversation) must be present to engage
    # the conversation loop. ``persona_character_id`` binds a persona card.
    monitor_session_id: str | None = Field(default=None)
    character_id: str | None = Field(default=None)
    persona_character_id: str | None = Field(default=None)


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: OpenAIMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


def _now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _sampling_overrides(body: ChatCompletionRequest) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if body.temperature is not None:
        out["temperature"] = body.temperature
    if body.max_tokens is not None:
        out["max_tokens"] = body.max_tokens
    if body.top_p is not None:
        out["top_p"] = body.top_p
    return out


def _is_session(body: ChatCompletionRequest) -> bool:
    return bool(body.monitor_session_id or body.character_id)


# ---------------------------------------------------------------------------
# Plain OpenAI path (no session)
# ---------------------------------------------------------------------------


async def _resolve_plain_client() -> Any:
    postgres = get_postgres_client()
    registry = LLMRegistry(postgres)
    client = await registry.for_role(ModelRole.STANDARD)
    if client is None:
        raise HTTPException(status_code=503, detail="No LLM configured for the STANDARD role.")
    return client


async def _plain_non_stream(body: ChatCompletionRequest) -> ChatCompletionResponse:
    client = await _resolve_plain_client()
    msgs = [m.model_dump() for m in body.messages]
    try:
        text = await client.complete_text(msgs, **_sampling_overrides(body))
    except Exception as exc:
        logger.warning("openai_completions_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Upstream LM call failed: {exc}") from exc
    return ChatCompletionResponse(
        id=_new_completion_id(),
        created=_now_epoch(),
        model=body.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=OpenAIMessage(role="assistant", content=text),
            )
        ],
        usage=ChatCompletionUsage(),
    )


async def _plain_stream(body: ChatCompletionRequest) -> StreamingResponse:
    client = await _resolve_plain_client()
    completion_id = _new_completion_id()
    created = _now_epoch()
    msgs = [m.model_dump() for m in body.messages]

    async def _event_generator() -> AsyncIterator[str]:
        first_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": body.model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(first_chunk)}\n\n"
        try:
            async for fragment in client.stream_text(msgs, **_sampling_overrides(body)):
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": body.model,
                    "choices": [
                        {"index": 0, "delta": {"content": fragment}, "finish_reason": None}
                    ],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as exc:
            logger.warning("openai_stream_failed", exc_info=True)
            err_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": body.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                "error": {"message": str(exc)},
            }
            yield f"data: {json.dumps(err_chunk)}\n\n"
        stop_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": body.model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        yield f"data: {json.dumps(stop_chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Session path (character + persona + lorebook)
# ---------------------------------------------------------------------------


async def _session_non_stream(body: ChatCompletionRequest) -> ChatCompletionResponse:
    if body.stream:
        raise HTTPException(
            status_code=400,
            detail="stream=true is not supported in session mode yet. "
            "Set stream=false or omit the session fields to use plain streaming.",
        )

    # Import the module rather than the names so tests can patch the
    # attributes on the source module and the lookup re-reads at call time.
    from . import character_conversation as cc

    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list.")
    last_user = next(
        (m for m in reversed(body.messages) if m.role == "user"),
        None,
    )
    if last_user is None:
        raise HTTPException(
            status_code=400,
            detail="session mode requires at least one user message in `messages`.",
        )

    if body.monitor_session_id:
        try:
            reply = await cc.send_message(
                body.monitor_session_id,
                last_user.content,
                False,
                character_id=body.character_id,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=409,
                detail=f"Conversation {body.monitor_session_id} is no longer active.",
            ) from exc
        except Exception as exc:
            logger.warning("openai_session_send_failed", exc_info=True)
            raise HTTPException(status_code=502, detail=f"Send failed: {exc}") from exc
    else:
        if not body.character_id:
            raise HTTPException(
                status_code=400,
                detail="session mode requires either x-monitor-session or character_id.",
            )
        opened = await cc.start_conversation(
            body.character_id,
            persona_character_id=body.persona_character_id,
        )
        try:
            reply = await cc.send_message(
                str(opened["conversation_id"]),
                last_user.content,
                False,
                character_id=body.character_id,
            )
        except Exception as exc:
            logger.warning("openai_session_send_failed", exc_info=True)
            raise HTTPException(status_code=502, detail=f"Send failed: {exc}") from exc

    text = str(reply.get("text") or "")
    return ChatCompletionResponse(
        id=_new_completion_id(),
        created=_now_epoch(),
        model=body.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=OpenAIMessage(role="assistant", content=text),
            )
        ],
        usage=ChatCompletionUsage(),
    )


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(body: ChatCompletionRequest) -> Any:
    """OpenAI-compatible chat completion, routed through MONITOR's LLM registry
    or the conversation loop, depending on the request."""
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list.")

    if _is_session(body):
        return await _session_non_stream(body)

    if body.stream:
        return await _plain_stream(body)

    return await _plain_non_stream(body)
