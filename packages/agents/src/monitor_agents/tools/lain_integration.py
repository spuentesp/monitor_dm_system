"""Lain tool integration for MONITOR agents.

This module provides Lain MCP tool access to agents in Layer 2.
Lain runs as a stdio MCP server and provides:
- Semantic code search
- Blast radius analysis
- Dependency tracing
- Dead code detection
- Build/test integration

Usage:
    from monitor_agents.tools.lain_integration import get_lain_client

    async with get_lain_client() as client:
        # Search for code related to a concept
        results = await client.semantic_search("scene loop implementation")

        # Check what would break if a file changes
        blast = await client.get_blast_radius("packages/agents/src/monitor_agents/loops.py")
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog

from monitor_data.tools.lain_tools import LainClient

log = structlog.get_logger(__name__)

# Singleton client instance
_lain_client: LainClient | None = None


def get_lain_client() -> LainClient:
    """Get or create the Lain MCP client singleton."""
    global _lain_client
    if _lain_client is None:
        _lain_client = LainClient()
    return _lain_client


@asynccontextmanager
async def lain_session() -> AsyncGenerator[LainClient, None]:
    """Async context manager for Lain sessions.

    Usage:
        async with lain_session() as client:
            result = await client.semantic_search("my query")
    """
    client = get_lain_client()
    async with client as conn:
        yield conn


# Tool name constants for type-safe tool calls
class LainTools:
    """Lain MCP tool names."""

    SEMANTIC_SEARCH = "semantic_search"
    GET_BLAST_RADIUS = "get_blast_radius"
    TRACE_DEPENDENCY = "trace_dependency"
    GET_CALL_CHAIN = "get_call_chain"
    FIND_DEAD_CODE = "find_dead_code"
    EXPLORE_ARCHITECTURE = "explore_architecture"
    RUN_BUILD = "run_build"
    RUN_TESTS = "run_tests"


async def search_code(
    query: str,
    limit: int = 10,
) -> dict:
    """Search codebase using semantic understanding.

    Args:
        query: Natural language query (e.g., "how does the scene loop work?")
        limit: Maximum number of results

    Returns:
        Search results with file paths and relevance scores
    """
    async with lain_session() as client:
        return await client.semantic_search(query, limit)


async def analyze_impact(
    file_path: str,
) -> dict:
    """Analyze what would be affected if this file changes.

    Args:
        file_path: Path relative to workspace (e.g., "packages/agents/src/...")

    Returns:
        List of files/functions that depend on the target
    """
    async with lain_session() as client:
        return await client.get_blast_radius(file_path)


async def trace_symbol(
    symbol: str,
) -> dict:
    """Trace a symbol's definition and all its usages.

    Args:
        symbol: Function, class, or variable name

    Returns:
        Definition location and call sites
    """
    async with lain_session() as client:
        return await client.trace_dependency(symbol)


async def get_function_chain(
    function_name: str,
) -> dict:
    """Get the complete call chain for a function.

    Args:
        function_name: Name of function to trace

    Returns:
        Hierarchical call tree
    """
    async with lain_session() as client:
        return await client.get_call_chain(function_name)


async def detect_dead_code() -> dict:
    """Find unused functions, classes, and variables.

    Returns:
        List of dead code locations
    """
    async with lain_session() as client:
        return await client.find_dead_code()


async def explore_arch() -> dict:
    """Explore codebase architecture and module relationships.

    Returns:
        Architecture overview with module dependencies
    """
    async with lain_session() as client:
        return await client.explore_architecture()


async def run_project_build() -> dict:
    """Run the project's build command.

    Returns:
        Build output and any errors
    """
    async with lain_session() as client:
        return await client.run_build()


async def run_project_tests(
    pattern: str | None = None,
) -> dict:
    """Run project tests, optionally filtered by pattern.

    Args:
        pattern: Optional glob pattern (e.g., "packages/agents/**")

    Returns:
        Test results with pass/fail status
    """
    async with lain_session() as client:
        return await client.run_tests(pattern)
