"""
MCP Server Entry Point for MONITOR Data Layer.

This module initializes and runs the MCP server that exposes
data layer tools to agents.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only
CALLED BY: Agents (Layer 2) via MCP protocol

Usage:
    $ monitor-data
    # or
    $ python -m monitor_data.server
"""

import asyncio
import logging
import sys
from typing import Any, Callable, Dict, List, get_type_hints
import inspect

from mcp.server import Server  # type: ignore[import-not-found]
from mcp.types import Tool, TextContent  # type: ignore[import-not-found]
from mcp import stdio_server  # type: ignore[import-not-found]

# Import all tool modules
from monitor_data.tools import neo4j_tools, mongodb_tools, qdrant_tools

# Import middleware
from monitor_data.middleware import (
    check_authority,
    validate_tool_input,
    log_tool_call,
    ToolCallTimer,
    AuthorizationError,
    ValidationError,
    get_validation_error_response,
)

# Import health check
from monitor_data.health import get_health_status

# Configure logging to stderr (safe for STDIO transport)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

# Create MCP server instance
server = Server("monitor-data-layer")

# Tool registry: maps tool name to (function, module)
TOOL_REGISTRY: Dict[str, Callable] = {}


def discover_tools() -> None:
    """
    Discover and register all tool functions from tool modules.

    Scans neo4j_tools, mongodb_tools, and qdrant_tools modules
    for functions starting with module prefixes (neo4j_, mongodb_, qdrant_).
    """
    modules = [
        (neo4j_tools, "neo4j_"),
        (mongodb_tools, "mongodb_"),
        (qdrant_tools, "qdrant_"),
    ]

    for module, prefix in modules:
        for name in dir(module):
            if name.startswith(prefix):
                func = getattr(module, name)
                if callable(func) and not name.startswith("_"):
                    TOOL_REGISTRY[name] = func
                    logger.debug(f"Registered tool: {name}")

    logger.info(f"Discovered {len(TOOL_REGISTRY)} tools")


def extract_tool_schema(func: Callable) -> Dict[str, Any]:
    """
    Extract JSON Schema from function's Pydantic parameter type hints.

    Args:
        func: Tool function to extract schema from

    Returns:
        JSON Schema dict for the tool's input parameters

    Examples:
        >>> def my_tool(params: MyRequest) -> MyResponse:
        ...     pass
        >>> schema = extract_tool_schema(my_tool)
        >>> schema['type']
        'object'
    """
    try:
        # Get type hints
        hints = get_type_hints(func)

        # Get function signature
        sig = inspect.signature(func)

        # Build schema from parameters
        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue

            param_type = hints.get(param_name)

            # If parameter has a Pydantic model type, use its schema
            if param_type and hasattr(param_type, "model_json_schema"):
                # Pydantic v2 schema
                param_schema = param_type.model_json_schema()  # type: ignore[union-attr]
                properties[param_name] = param_schema

                # If parameter has no default, it's required
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
            else:
                # Simple type - create basic schema
                type_map: Dict[Any, str] = {
                    str: "string",
                    int: "integer",
                    float: "number",
                    bool: "boolean",
                    list: "array",
                    dict: "object",
                }
                json_type = (
                    type_map.get(param_type, "string") if param_type else "string"
                )

                properties[param_name] = {"type": json_type}

                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

        schema = {
            "type": "object",
            "properties": properties,
        }

        if required:
            schema["required"] = required

        return schema

    except Exception as e:
        logger.error(f"Failed to extract schema for {func.__name__}: {e}")
        # Return minimal schema as fallback
        return {"type": "object"}


@server.list_tools()
async def list_tools() -> List[Tool]:
    """
    List all available tools with their schemas.

    Returns:
        List of Tool objects with names, descriptions, and input schemas
    """
    tools = []

    for tool_name, func in TOOL_REGISTRY.items():
        # Extract description from docstring
        description = (func.__doc__ or "").strip().split("\n")[0]
        if not description:
            description = f"Execute {tool_name}"

        # Extract schema from function signature
        input_schema = extract_tool_schema(func)

        tools.append(
            Tool(
                name=tool_name,
                description=description,
                inputSchema=input_schema,
            )
        )

    logger.debug(f"Listing {len(tools)} tools")
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """
    Execute a tool with middleware enforcement.

    Middleware execution order:
    1. Lookup tool function
    2. Check authority (auth middleware)
    3. Validate input (validation middleware)
    4. Log request (logging middleware)
    5. Execute tool function
    6. Log result (logging middleware)
    7. Return response

    Args:
        name: Tool name
        arguments: Tool input arguments

    Returns:
        List of TextContent with tool response

    Raises:
        Error with appropriate code if tool fails
    """
    timer = ToolCallTimer()

    with timer:
        try:
            # Extract agent context from arguments
            agent_type = arguments.pop("agent_type", "Unknown")
            agent_id = arguments.pop("agent_id", None)

            # 1. Lookup tool
            if name not in TOOL_REGISTRY:
                log_tool_call(
                    name,
                    agent_type,
                    agent_id,
                    arguments,
                    success=False,
                    error_message="Tool not found",
                )
                raise ValueError(f"Unknown tool: {name}")

            tool_func = TOOL_REGISTRY[name]

            # 2. Check authority (auth middleware)
            try:
                if not check_authority(name, agent_type):
                    from monitor_data.middleware.auth import get_allowed_agents

                    allowed = get_allowed_agents(name)
                    error_msg = (
                        f"Agent '{agent_type}' is not authorized to call '{name}'. "
                        f"Allowed agents: {', '.join(allowed)}"
                    )

                    log_tool_call(
                        name,
                        agent_type,
                        agent_id,
                        arguments,
                        success=False,
                        error_message=error_msg,
                        execution_time_ms=timer.elapsed_ms,
                    )

                    return [
                        TextContent(
                            type="text",
                            text=f"Authorization error: {error_msg}",
                        )
                    ]

            except AuthorizationError as e:
                log_tool_call(
                    name,
                    agent_type,
                    agent_id,
                    arguments,
                    success=False,
                    error_message=str(e),
                    execution_time_ms=timer.elapsed_ms,
                )
                return [TextContent(type="text", text=f"Authorization error: {str(e)}")]

            # 3. Validate input (validation middleware)
            try:
                validated_args = validate_tool_input(name, tool_func, arguments)
            except ValidationError as e:
                error_response = get_validation_error_response(e)
                log_tool_call(
                    name,
                    agent_type,
                    agent_id,
                    arguments,
                    success=False,
                    error_message=error_response["message"],
                    execution_time_ms=timer.elapsed_ms,
                )
                return [
                    TextContent(
                        type="text",
                        text=f"Validation error: {error_response['message']}",
                    )
                ]

            # 4. Execute tool
            logger.debug(f"Executing tool: {name}")

            # Call the tool function
            # Check if function is async
            if inspect.iscoroutinefunction(tool_func):
                result = await tool_func(**validated_args)
            else:
                result = tool_func(**validated_args)

            # 5. Log success
            log_tool_call(
                name,
                agent_type,
                agent_id,
                arguments,
                success=True,
                execution_time_ms=timer.elapsed_ms,
            )

            # 6. Format response
            # Convert result to string (handle Pydantic models)
            if hasattr(result, "model_dump_json"):
                result_text = result.model_dump_json(indent=2)
            elif hasattr(result, "json"):
                result_text = result.json(indent=2)
            else:
                import json

                result_text = json.dumps(result, indent=2, default=str)

            return [TextContent(type="text", text=result_text)]

        except Exception as e:
            # Log unexpected errors
            logger.error(f"Tool execution error for '{name}': {e}", exc_info=True)

            # Comment 1 fix: Use extracted agent variables, not arguments.get()
            log_tool_call(
                name,
                agent_type,
                agent_id,
                arguments,
                success=False,
                error_message=str(e),
                execution_time_ms=timer.elapsed_ms,
            )

            return [TextContent(type="text", text=f"Error executing tool: {str(e)}")]


async def main() -> None:
    """
    Start the MCP server.

    Registers all tools from:
    - monitor_data.tools.neo4j_tools
    - monitor_data.tools.mongodb_tools
    - monitor_data.tools.qdrant_tools

    Applies middleware:
    - monitor_data.middleware.auth (authority enforcement)
    - monitor_data.middleware.validation (schema validation)
    - monitor_data.middleware.logging (request/response logging)
    """
    logger.info("Starting MONITOR Data Layer MCP Server")

    # Discover and register all tools
    discover_tools()

    # Log health status
    try:
        health = get_health_status()
        logger.info(f"Health status: {health['overall_status']}")
        for component, status in health["components"].items():
            logger.info(f"  {component}: {status['status']}")
    except Exception as e:
        logger.warning(f"Health check failed: {e}")

    # Run server with STDIO transport
    logger.info("Server ready, listening on STDIO")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)
