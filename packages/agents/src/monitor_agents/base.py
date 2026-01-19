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
        # Import here to avoid circular dependencies if any
        # Layer 2 imports Layer 1
        from monitor_data.server import call_tool as server_call_tool, discover_tools

        # Ensure tools are discovered
        if not hasattr(server_call_tool, "_discovered"):
             discover_tools()
             server_call_tool._discovered = True

        # Inject agent context for Auth middleware
        full_args = arguments.copy()
        full_args["agent_type"] = self.agent_type
        full_args["agent_id"] = self.agent_id

        # Call the tool via the server's decorated function
        # Note: server.call_tool returns [TextContent], we need to parse it back if possible
        # or return the raw result. For internal use, we might want the direct result.
        # However, the server.call_tool serializes to JSON/TextContent.
        #
        # For efficiency and type safety in internal calls, we should ideally use the 
        # registry directly, but we want the Middleware (Auth/Validation).
        # The server.call_tool provides that.
        
        result_contents = await server_call_tool(tool_name, full_args)
        
        # Parse result - usually it's a single TextContent with JSON
        if result_contents and len(result_contents) > 0:
            return result_contents[0].text
        return None

    @abstractmethod
    async def run(self) -> None:
        """
        Main agent execution method.

        Each agent implements its own run logic.
        """
        pass
