"""OpenAI-compatible ``/v1/chat/completions`` endpoint.

This is the inbound surface that turns RisuAI, SillyTavern, LiteLLM, and any
other OpenAI-shaped client into a MONITOR frontend. The v1 scope is:

- Non-streaming only (``stream=false`` or omitted). Streaming is rejected
  with HTTP 400 so the client surfaces the limitation clearly.
- Stateless: each request is a single LM call. The first ``system`` message
  is treated as the card text (description/personality/etc.). No MONITOR
  session or lorebook is threaded — that's the streaming+session follow-up.
- Model mapping: the OpenAI ``model`` field is accepted for client
  compatibility but the actual call is routed through ``LLMRegistry`` at the
  ``STANDARD`` role (the configured default chat model). Pick a ``model``
  value that reflects what you want to spend; the response echoes the
  request value rather than the internal model id.
- Auth: open in v1. The wrapper sits behind the same dev binding as the
  other routers; front it with reverse-proxy auth or add a bearer-token
  middleware before exposing it.

The endpoint shape is a strict subset of the OpenAI Chat Completions API
(RisuAI/SillyTavern send only ``model`` + ``messages`` + ``temperature`` +
``max_tokens`` in the common case).

LAYER: 3 (UI backend)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
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
    model: str = Field(default="monitor-default", description="Client-facing model name; advisory only in v1.")
    messages: list[OpenAIMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    stream: bool = False


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


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(body: ChatCompletionRequest) -> ChatCompletionResponse:
    """OpenAI-compatible chat completion, routed through MONITOR's LLM registry."""
    if body.stream:
        raise HTTPException(
            status_code=400,
            detail="stream=true is not supported in /v1/chat/completions v1. "
            "Drop the stream flag and retry.",
        )
    if not body.messages:
        raise HTTPException(status_code=400, detail="messages must be a non-empty list.")

    try:
        postgres = get_postgres_client()
        registry = LLMRegistry(postgres)
        client = await registry.for_role(ModelRole.STANDARD)
    except Exception as exc:
        logger.warning("openai_compat_registry_lookup_failed", exc_info=True)
        raise HTTPException(status_code=503, detail=f"LLM registry unavailable: {exc}") from exc

    if client is None:
        raise HTTPException(status_code=503, detail="No LLM configured for the STANDARD role.")

    overrides: dict[str, Any] = {}
    if body.temperature is not None:
        overrides["temperature"] = body.temperature
    if body.max_tokens is not None:
        overrides["max_tokens"] = body.max_tokens
    if body.top_p is not None:
        overrides["top_p"] = body.top_p

    msgs = [m.model_dump() for m in body.messages]
    try:
        text = await client.complete_text(msgs, **overrides)
    except Exception as exc:
        logger.warning("openai_completions_failed", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Upstream LM call failed: {exc}") from exc

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:24]}",
        created=int(datetime.now(timezone.utc).timestamp()),
        model=body.model or client.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=OpenAIMessage(role="assistant", content=text),
            )
        ],
        usage=ChatCompletionUsage(),
    )
