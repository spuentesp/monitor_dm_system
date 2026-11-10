"""OpenAI-compatible ``/v1/chat/completions`` endpoint.

Top-of-funnel surface that turns RisuAI, SillyTavern, LiteLLM, and any
other OpenAI-shaped client into a MONITOR frontend.

Routing modes (chosen by the request body):

- **Plain OpenAI** (no session fields): one LM call via the registry.
  Supports streaming (SSE) and non-streaming.
- **Session mode** (``monitor_session_id`` or ``character_id``): the request
  is routed through the light-RP conversation loop, so the response benefits
  from MONITOR's persona binding, lorebook scanning, and NPC memory. Requests
  carrying only ``character_id`` continue the conversation their history
  belongs to (see ``client_history_fingerprint``). Both ``stream=true``
  (SSE ``chat.completion.chunk`` events) and non-streaming replies are
  supported; the loop's memory writes happen after the stream completes.

LAYER: 3 (UI backend)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from monitor_agents.llm_registry import LLMRegistry
from monitor_data.db.postgres import get_postgres_client
from monitor_ui.auth import Principal, get_current_user
from monitor_ui.ownership import require_character_owner, resource_route_guard
from monitor_data.schemas.llm_config import ModelRole

logger = structlog.get_logger()

router = APIRouter(dependencies=[Depends(resource_route_guard)])


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
    # Session mode only. Clients that can echo it may pass it back on later requests.
    monitor_session_id: str | None = None


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
                    "choices": [{"index": 0, "delta": {"content": fragment}, "finish_reason": None}],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _event_generator)
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


async def _resolve_session_conversation(
    body: ChatCompletionRequest,
) -> tuple[str, list[tuple[str, str]], OpenAIMessage]:
    """Resolve (or open) the conversation this request continues.

    Returns ``(conversation_id, history_before_last_user, last_user_message)``.
    OpenAI-shaped clients resend their history, so everything before the last
    player line tells us where this request sits in the chat. System messages
    are the client's prompt; in session mode the character card is the
    authority.
    """
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

    last_user_index = max(i for i, m in enumerate(body.messages) if m.role == "user")
    history = [(m.role, m.content) for m in body.messages[:last_user_index] if m.role != "system"]
    position = cc.client_history_fingerprint(history)

    conversation_id = body.monitor_session_id
    if not conversation_id and body.character_id and position:
        try:
            conversation_id = await cc.find_client_conversation(body.character_id, body.persona_character_id, position)
        except Exception:  # noqa: BLE001  # reason: a failed lookup costs continuity, not the reply; a new conversation still answers
            logger.warning("openai_session_lookup_failed", exc_info=True)

    if not conversation_id:
        if not body.character_id:
            raise HTTPException(
                status_code=400,
                detail="session mode requires either monitor_session_id or character_id.",
            )
        try:
            opened = await cc.start_conversation(
                body.character_id,
                persona_character_id=body.persona_character_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            logger.warning("openai_session_start_failed", exc_info=True)
            raise HTTPException(status_code=502, detail=f"Could not open a conversation: {exc}") from exc
        conversation_id = str(opened["conversation_id"])

    return str(conversation_id), history, last_user


async def _session_remember_position(
    body: ChatCompletionRequest,
    conversation_id: str,
    history: list[tuple[str, str]],
    last_user: OpenAIMessage,
    reply_text: str,
) -> None:
    """Record the client-history positions that lead back to this conversation."""
    from . import character_conversation as cc

    if not body.character_id:
        return
    try:
        after = history + [("user", last_user.content), ("assistant", reply_text)]
        await cc.remember_client_conversation(
            conversation_id,
            body.character_id,
            body.persona_character_id,
            [cc.client_history_fingerprint(history), cc.client_history_fingerprint(after)],
        )
    except Exception:  # noqa: BLE001  # reason: the reply exists; failing here would discard it over continuity bookkeeping
        logger.warning("openai_session_remember_failed", exc_info=True)


async def _session_stream(body: ChatCompletionRequest) -> StreamingResponse:
    """Session mode with ``stream=true``: SSE chunks of the loop's reply.

    The conversation loop's memory writes for this turn are deferred and
    flushed after the stream completes (see ``send_message_stream``).
    """
    from . import character_conversation as cc

    conversation_id, history, last_user = await _resolve_session_conversation(body)

    try:
        stream = await cc.send_message_stream(
            conversation_id,
            last_user.content,
            False,
            character_id=body.character_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Conversation {conversation_id} is no longer active.",
        ) from exc
    except Exception as exc:
        logger.warning("openai_session_send_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}") from exc

    completion_id = _new_completion_id()
    created = _now_epoch()
    reply_parts: list[str] = []

    async def _event_generator() -> AsyncIterator[str]:
        first_chunk = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": body.model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            "monitor_session_id": conversation_id,
        }
        yield f"data: {json.dumps(first_chunk)}\n\n"
        done_event: dict[str, Any] | None = None
        try:
            async for event in stream:
                if event.get("type") == "token":
                    text = str(event.get("text") or "")
                    reply_parts.append(text)
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": body.model,
                        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                elif event.get("type") == "done":
                    done_event = event
        except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _event_generator)
            logger.warning("openai_session_stream_failed", exc_info=True)
            err_chunk = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": body.model,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "error"}],
                "error": {"message": str(exc)},
            }
            yield f"data: {json.dumps(err_chunk)}\n\n"
        if done_event is not None:
            await _session_remember_position(body, conversation_id, history, last_user, "".join(reply_parts))
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Monitor-Session-Id": conversation_id,
        },
    )


async def _session_non_stream(body: ChatCompletionRequest) -> ChatCompletionResponse:
    # Import the module rather than the names so tests can patch the
    # attributes on the source module and the lookup re-reads at call time.
    from . import character_conversation as cc

    conversation_id, history, last_user = await _resolve_session_conversation(body)

    try:
        reply = await cc.send_message(
            conversation_id,
            last_user.content,
            False,
            character_id=body.character_id,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Conversation {conversation_id} is no longer active.",
        ) from exc
    except Exception as exc:
        logger.warning("openai_session_send_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}") from exc

    text = str(reply.get("text") or "")
    await _session_remember_position(body, conversation_id, history, last_user, text)

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
        monitor_session_id=conversation_id,
    )


async def _require_conversation_owner(principal: Principal, conversation_id: str) -> None:
    """A resumed conversation must belong to a character the caller owns.

    The standalone-card link lives in the conversation doc's
    ``client_session.character_id`` (same field the resume path reads).
    """
    from monitor_data.db.mongodb import get_mongodb_client

    try:
        uuid.UUID(str(conversation_id))
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None
    doc = (
        get_mongodb_client()
        .get_collection("conversations")
        .find_one(
            {"conversation_id": str(conversation_id)},
            {"client_session": 1},
        )
    )
    char_id = None
    if isinstance(doc, dict):
        cs = doc.get("client_session")
        if isinstance(cs, dict):
            char_id = cs.get("character_id")
    if not char_id:
        raise HTTPException(status_code=404, detail="Not found")
    await require_character_owner(principal, str(char_id))


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    body: ChatCompletionRequest,
    principal: Principal = Depends(get_current_user),
) -> Any:
    """OpenAI-compatible chat completion, routed through MONITOR's LLM registry
    or the conversation loop, depending on the request.

    Authenticated via per-user API token (Bearer) or browser session cookie.
    Session mode is resource-scoped: the referenced character (and, on
    resume, the conversation's owning character) must belong to the caller,
    else 404. Plain mode only invokes the caller's LLM quota path.
    """
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list.")

    if _is_session(body):
        # Character-scoped session mode: both the target character and the
        # persona must belong to the caller; a resumed conversation must
        # belong to an owned character.
        if body.character_id:
            await require_character_owner(principal, body.character_id)
        if body.persona_character_id:
            await require_character_owner(principal, body.persona_character_id)
        if body.monitor_session_id:
            # Resume path: the conversation must belong to an owned character,
            # even when character_id is also supplied.
            await _require_conversation_owner(principal, body.monitor_session_id)
        if body.stream:
            return await _session_stream(body)
        return await _session_non_stream(body)

    if body.stream:
        return await _plain_stream(body)

    return await _plain_non_stream(body)
