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

import json
import logging
from abc import ABC, abstractmethod
from contextlib import suppress
from typing import Any, Type, TypeVar

import logfire
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from pydantic import BaseModel

from monitor_agents.dspy_runtime import default_role_for_node, normalize_node_name
from monitor_agents.llm_errors import (
    LLMErrorClass,
    classify_llm_error,
    is_retryable_exception,
)
from monitor_agents.llm_registry import LLMRegistry
from monitor_data.config import settings
from monitor_data.db.postgres import get_postgres_client
from monitor_data.schemas.llm_config import ModelRole

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
_LLM_RETRY: dict[str, Any] = dict(
    stop=stop_after_attempt(settings.llm_retry_attempts),
    wait=wait_exponential(
        multiplier=1,
        min=settings.llm_retry_min_wait,
        max=settings.llm_retry_max_wait,
    ),
    retry=retry_if_exception(is_retryable_exception),
    reraise=True,
)


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
        response_model: Type[T],
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
                            "LLM provider for %s failed (%s: %s); falling back to "
                            "default provider %s",
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
        from monitor_data.server import call_tool as server_call_tool

        with logfire.span(
            "{agent_type}.call_tool",
            agent_type=self.agent_type,
            agent_id=self.agent_id,
            tool_name=tool_name,
        ):
            full_args = {**arguments, "agent_type": self.agent_type, "agent_id": self.agent_id}
            result_contents = await server_call_tool(tool_name, full_args)

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
