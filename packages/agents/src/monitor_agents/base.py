"""
Base Agent Class for MONITOR.

All agents inherit from BaseAgent which provides:
- Anthropic client wrapped by ``instructor`` for strict Pydantic output
- Tenacity retry with exponential backoff on LLM calls
- Logfire span tracing around every agent call
- MCP tool calling interface (delegates to data-layer server)

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries
CALLED BY: CLI (Layer 3), other agents
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Any, TypeVar

import logfire
from monitor_data.config import settings
from monitor_data.db.postgres import get_postgres_client
from monitor_data.schemas.llm_config import ModelRole
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from monitor_agents.dspy_runtime import (
    default_role_for_node,
    normalize_node_name,
    stream_callback_var,
)
from monitor_agents.llm_errors import (
    LLMErrorClass,
    classify_llm_error,
    is_retryable_exception,
)
from monitor_agents.llm_registry import LLMRegistry

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# ---------------------------------------------------------------------------
# Logfire instrumentation (no-op outside a live Logfire project)
# ---------------------------------------------------------------------------
logfire.configure(send_to_logfire=False)  # local-only by default; set env vars to enable
with suppress(Exception):
    logfire.instrument_anthropic()
with suppress(Exception):
    logfire.instrument_openai()

# ---------------------------------------------------------------------------
# LLM retry policy
# ---------------------------------------------------------------------------
_LLM_RETRY: dict[str, Any] = {
    "stop": stop_after_attempt(settings.llm_retry_attempts),
    "wait": wait_exponential(
        multiplier=1,
        min=settings.llm_retry_min_wait,
        max=settings.llm_retry_max_wait,
    ),
    "retry": retry_if_exception(is_retryable_exception),
    "reraise": True,
}


class BaseAgent(ABC):
    """
    Abstract base class for all MONITOR agents.

    Attributes:
        agent_type: The type of agent (e.g., "CanonKeeper", "Narrator")
        agent_id: Unique identifier for this agent instance
        model: LLM model to use

    All agents are STATELESS.  State lives in databases, not agents.
    """

    def __init__(
        self,
        agent_type: str,
        agent_id: str,
        model: str | None = None,
    ) -> None:
        self.agent_type = agent_type
        self.agent_id = agent_id
        self.model = model or settings.llm_model

    # ------------------------------------------------------------------
    # Structured LLM calls
    # ------------------------------------------------------------------

    def _node_name(self) -> str:
        return normalize_node_name(self.agent_type)

    def _default_model_role(self) -> ModelRole:
        return default_role_for_node(self._node_name())

    @retry(**_LLM_RETRY)
    async def call_llm_structured(
        self,
        response_model: type[T],
        messages: list[dict[str, Any]],
        max_tokens: int = 2048,
    ) -> T:
        """
        Call the configured LLM and enforce a Pydantic response model via instructor.

        Resolution order:
          1. explicit provider assigned to this agent node
          2. best available provider for the agent's complexity role
        """
        registry = LLMRegistry(get_postgres_client())
        client = await registry.for_node_or_role(self._node_name(), self._default_model_role())

        with logfire.span(
            "{agent_type}.call_llm_structured",
            agent_type=self.agent_type,
            agent_id=self.agent_id,
            model=client.model,
            response_model=response_model.__name__,
        ):
            try:
                return await client.create(
                    response_model=response_model,
                    messages=messages,
                    max_tokens=max_tokens,
                )
            except Exception as exc:
                # A provider with a broken credential/quota should not take the
                # whole agent down when a working default provider exists.
                info = classify_llm_error(exc)
                if info.error_class in (LLMErrorClass.AUTH, LLMErrorClass.QUOTA):
                    fallback = await registry.default_client()
                    if fallback is not None and fallback.model != client.model:
                        logger.warning(
                            "LLM provider for %s failed (%s: %s); falling back to default provider %s",
                            self.agent_type,
                            info.error_class.value,
                            info.message[:120],
                            fallback.model,
                        )
                        return await fallback.create(
                            response_model=response_model,
                            messages=messages,
                            max_tokens=max_tokens,
                        )
                raise

    # ------------------------------------------------------------------
    # MCP tool calls
    # ------------------------------------------------------------------

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Call an MCP tool via the data-layer server.

        The agent_type is injected into arguments for authority middleware.

        Args:
            tool_name: Name of the MCP tool to call.
            arguments: Tool arguments (agent_type injected automatically).

        Returns:
            Parsed tool result text.

        Raises:
            PermissionError: If agent lacks authority for this tool.
        """
        # Surface MCP tool invocations to the client as tool_call /
        # tool_result WS events. Each call gets a fresh id so the result
        # can be correlated back even when tools fire concurrently inside
        # a single turn. Errors are caught and surfaced as a tool_result
        # with an error payload so the UI can render the failure inline
        # instead of crashing the turn.
        import uuid as _uuid

        from monitor_data.server import call_tool as server_call_tool

        call_id = str(_uuid.uuid4())
        cb = stream_callback_var.get()
        full_args = {**arguments, "agent_type": self.agent_type, "agent_id": self.agent_id}
        if cb is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    cb(
                        "tool_call",
                        {
                            "id": call_id,
                            "name": tool_name,
                            "args": arguments,
                        },
                    )
                )
            except RuntimeError:
                pass

        with logfire.span(
            "{agent_type}.call_tool",
            agent_type=self.agent_type,
            agent_id=self.agent_id,
            tool_name=tool_name,
            call_id=call_id,
        ):
            try:
                result_contents = await server_call_tool(tool_name, full_args)
            except Exception as exc:
                if cb is not None:
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(
                            cb(
                                "tool_result",
                                {
                                    "tool_call_id": call_id,
                                    "name": tool_name,
                                    "error": repr(exc),
                                },
                            )
                        )
                    except RuntimeError:
                        pass
                raise

        # Surface the successful result to the client. Truncated to 2000
        # chars so a giant Mongo cursor or embedding blob doesn't blow up
        # the WS payload — the agent keeps the full result for downstream
        # reasoning; the UI gets a preview only.
        if cb is not None:
            try:
                loop = asyncio.get_running_loop()
                # Use the raw text from the MCP server response when
                # available — it gives the UI a meaningful preview. Falls
                # back to repr of the full result for non-text payloads.
                # Capped at 2000 chars so a giant Mongo cursor doesn't
                # blow up the WS payload — the agent keeps the full
                # result for downstream reasoning.
                _raw_text = result_contents[0].text if result_contents and hasattr(result_contents[0], "text") else None
                if _raw_text and len(_raw_text) > 2000:
                    _raw_text = _raw_text[:2000] + "...[truncated]"
                loop.create_task(
                    cb(
                        "tool_result",
                        {
                            "tool_call_id": call_id,
                            "name": tool_name,
                            "result_preview": _raw_text or repr(result_contents),
                        },
                    )
                )
            except RuntimeError:
                pass

        if result_contents:
            result = result_contents[0].text
            if not isinstance(result, str):
                return result

            stripped = result.strip()
            if stripped:
                should_parse = (
                    stripped[0] in '[{"'
                    or stripped in {"null", "true", "false"}
                    or (stripped[0].isdigit())
                    or (stripped[0] == "-" and len(stripped) > 1 and stripped[1].isdigit())
                )
                if should_parse:
                    try:
                        return json.loads(stripped)
                    except json.JSONDecodeError:
                        logger.warning(
                            "call_tool: JSON parse failed for tool %s, returning raw string",
                            tool_name,
                            exc_info=True,
                        )
            return result
        return None

    @abstractmethod
    async def run(self) -> None:
        """
        Main agent execution method.

        Each agent implements its own run logic.
        """
        pass
