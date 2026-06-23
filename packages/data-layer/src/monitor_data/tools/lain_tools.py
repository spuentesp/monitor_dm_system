"""Lain MCP client for code analysis and architectural exploration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

log = structlog.get_logger(__name__)


@dataclass
class LainConfig:
    """Configuration for Lain MCP server."""

    binary_path: str = "/Users/spuentesp/.lain/bin/lain"
    workspace: str = "/Users/spuentesp/personal/monitor_dm_system"
    embedding_model: str = "/Users/spuentesp/personal/monitor_dm_system/.lain/models/model.onnx"


class LainClient:
    """Async client for Lain MCP server.

    Usage:
        async with LainClient() as client:
            result = await client.semantic_search("scene loop implementation")
            blast = await client.get_blast_radius("packages/agents/src")
    """

    def __init__(self, config: LainConfig | None = None) -> None:
        self.config = config or LainConfig()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> LainClient:
        if not MCP_AVAILABLE:
            log.warning("mcp package not installed, Lain tools unavailable")
            return self

        params = StdioServerParameters(
            command=self.config.binary_path,
            args=[
                "--workspace",
                self.config.workspace,
                "--embedding-model",
                self.config.embedding_model,
                "--transport",
                "stdio",
            ],
        )

        self._session = ClientSession(stdio_client(params))
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session:
            await self._session.__aexit__(exc_type, exc_val, exc_tb)
            self._session = None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a Lain MCP tool.

        Args:
            name: Tool name (e.g., 'semantic_search', 'get_blast_radius')
            arguments: Tool arguments

        Returns:
            Tool result dict
        """
        if not self._session:
            return {"error": "Lain client not connected"}

        try:
            result = await self._session.call_tool(name, arguments)
            return {"success": True, "content": result.content}
        except Exception as e:
            log.error("lain_tool_failed", tool=name, error=str(e))
            return {"error": str(e)}

    # Convenience methods for common tools

    async def semantic_search(
        self,
        query: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Semantic code search.

        Args:
            query: Natural language search query
            limit: Max results (default 10)
        """
        return await self.call_tool(
            "semantic_search",
            {"query": query, "limit": limit},
        )

    async def get_blast_radius(
        self,
        file_path: str,
    ) -> dict[str, Any]:
        """Analyze what would break if this file changes.

        Args:
            file_path: Path relative to workspace root
        """
        return await self.call_tool(
            "get_blast_radius",
            {"file_path": file_path},
        )

    async def trace_dependency(
        self,
        symbol: str,
    ) -> dict[str, Any]:
        """Trace where a symbol is defined and used.

        Args:
            symbol: Function, class, or variable name
        """
        return await self.call_tool(
            "trace_dependency",
            {"symbol": symbol},
        )

    async def get_call_chain(
        self,
        function_name: str,
    ) -> dict[str, Any]:
        """Get the full call chain for a function.

        Args:
            function_name: Function to trace
        """
        return await self.call_tool(
            "get_call_chain",
            {"function_name": function_name},
        )

    async def find_dead_code(self) -> dict[str, Any]:
        """Find unused code in the workspace."""
        return await self.call_tool("find_dead_code", {})

    async def explore_architecture(self) -> dict[str, Any]:
        """Explore the codebase architecture."""
        return await self.call_tool("explore_architecture", {})

    async def run_build(self) -> dict[str, Any]:
        """Run the project's build command."""
        return await self.call_tool("run_build", {})

    async def run_tests(
        self,
        pattern: str | None = None,
    ) -> dict[str, Any]:
        """Run tests matching a pattern.

        Args:
            pattern: Optional glob pattern (e.g., 'packages/agents/**')
        """
        return await self.call_tool(
            "run_tests",
            {"pattern": pattern} if pattern else {},
        )
