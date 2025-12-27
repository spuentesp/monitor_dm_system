"""
Base Agent Class for MONITOR.

All agents inherit from BaseAgent which provides:
- MCP tool calling interface
- LLM client setup
- Common utilities

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries
CALLED BY: CLI (Layer 3), other agents
"""

import os
from abc import ABC, abstractmethod
from typing import Any

# from anthropic import Anthropic
# from monitor_data.tools import ...


class BaseAgent(ABC):
    """
    Abstract base class for all MONITOR agents.

    Attributes:
        agent_type: The type of agent (e.g., "CanonKeeper", "Narrator")
        agent_id: Unique identifier for this agent instance
        model: LLM model to use (default: claude-sonnet)

    All agents are STATELESS. State lives in databases, not agents.
    """

    def __init__(
        self,
        agent_type: str,
        agent_id: str,
        model: str | None = None,
    ) -> None:
        """
        Initialize the agent.

        Args:
            agent_type: Type identifier (used for authority checks)
            agent_id: Unique instance identifier
            model: LLM model name (default from env or claude-sonnet)
        """
        self.agent_type = agent_type
        self.agent_id = agent_id
        self.model = model or os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

        # TODO: Initialize Anthropic client
        # self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """
        Call an MCP tool via the data layer.

        The agent_type is passed to the tool for authority checking.

        Args:
            tool_name: Name of the MCP tool to call
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            PermissionError: If agent lacks authority for this tool
        """
        # TODO: Implement MCP tool calling
        # context = {"agent_id": self.agent_id, "agent_type": self.agent_type}
        # return await mcp_client.call(tool_name, arguments, context=context)
        raise NotImplementedError("Tool calling not yet implemented")

    @abstractmethod
    async def run(self) -> None:
        """
        Main agent execution method.

        Each agent implements its own run logic.
        """
        pass
