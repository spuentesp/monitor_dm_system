"""
MCP Server Entry Point for MONITOR Data Layer.

This module initializes and runs the MCP server that exposes
data layer tools to agents via HTTP/JSON-RPC.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only
CALLED BY: Agents (Layer 2) via MCP protocol

Usage:
    $ monitor-data
    # or
    $ python -m monitor_data.server
"""

import asyncio
import inspect
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, NoReturn, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from monitor_data.middleware.auth import (
    check_authority,
    require_authority,
    AuthorizationError,
    AUTHORITY_MATRIX,
)
from monitor_data.middleware.validation import (
    validate_request,
    validate_response,
    RequestValidationError,
)
from monitor_data.tools import neo4j_tools


# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("monitor_data.server")


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================


class ToolCallRequest(BaseModel):
    """Request to call a tool via MCP."""

    tool_name: str = Field(..., description="Name of the tool to call")
    agent_id: str = Field(..., description="Unique ID of the calling agent")
    agent_type: str = Field(
        ...,
        description="Type of agent (Orchestrator, CanonKeeper, Narrator, etc.)",
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments"
    )


class ToolCallResponse(BaseModel):
    """Response from a tool call."""

    success: bool
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None


class ToolSchema(BaseModel):
    """Schema describing a tool."""

    name: str
    description: str
    authority: List[str]
    parameters: Dict[str, Any]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: datetime
    databases: Dict[str, bool]


# =============================================================================
# TOOL REGISTRY
# =============================================================================


class ToolRegistry:
    """Registry of all available MCP tools."""

    def __init__(self):
        self.tools: Dict[str, Callable] = {}
        self._register_tools()

    def _register_tools(self):
        """Register all tools from the tools modules."""
        # Register Neo4j tools
        for name, func in inspect.getmembers(neo4j_tools, inspect.isfunction):
            if name.startswith("neo4j_"):
                self.tools[name] = func
                logger.info(f"Registered tool: {name}")

    def get_tool(self, name: str) -> Optional[Callable]:
        """Get a tool by name."""
        return self.tools.get(name)

    def list_tools(self) -> List[ToolSchema]:
        """List all registered tools with their schemas."""
        schemas = []
        for name, func in self.tools.items():
            # Get signature
            sig = inspect.signature(func)
            
            # Get authority requirements
            authority = AUTHORITY_MATRIX.get(name, ["*"])
            
            # Build parameter schema
            parameters = {}
            for param_name, param in sig.parameters.items():
                # Get type annotation
                param_type = param.annotation
                if param_type != inspect.Parameter.empty:
                    parameters[param_name] = {
                        "type": str(param_type),
                        "required": param.default == inspect.Parameter.empty,
                    }
            
            schemas.append(
                ToolSchema(
                    name=name,
                    description=func.__doc__ or "",
                    authority=authority,
                    parameters=parameters,
                )
            )
        return schemas


# =============================================================================
# FASTAPI APP
# =============================================================================

app = FastAPI(
    title="MONITOR Data Layer MCP Server",
    version="0.1.0",
    description="MCP server exposing data layer tools to agents",
)

# Initialize tool registry
registry = ToolRegistry()


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware to log all requests."""
    start_time = datetime.now(timezone.utc)
    
    # Log request
    logger.info(
        f"Request: {request.method} {request.url.path}",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client": request.client.host if request.client else None,
        },
    )
    
    # Process request
    response = await call_next(request)
    
    # Log response
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
    logger.info(
        f"Response: {response.status_code} ({duration:.3f}s)",
        extra={
            "status_code": response.status_code,
            "duration": duration,
        },
    )
    
    return response


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for k8s liveness/readiness probes.
    
    Returns server status, version, and database connectivity.
    
    Note: Database connectivity checks are simplified for now.
    In production, these should verify actual connections to:
    - Neo4j: Execute simple query
    - MongoDB: Ping database
    - Qdrant: Check collection existence
    """
    # Check database connectivity
    # TODO: Implement actual connectivity checks
    # Example implementation:
    # try:
    #     neo4j_client = get_neo4j_client()
    #     neo4j_client.verify_connectivity()
    #     neo4j_ok = True
    # except Exception:
    #     neo4j_ok = False
    
    db_status = {
        "neo4j": True,  # Assumes healthy
        "mongodb": True,  # Assumes healthy
        "qdrant": True,  # Assumes healthy
    }
    
    return HealthResponse(
        status="healthy" if all(db_status.values()) else "degraded",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc),
        databases=db_status,
    )


@app.get("/tools", response_model=List[ToolSchema])
async def list_tools():
    """
    List all registered tools with their schemas.
    
    This endpoint provides tool introspection for agents.
    """
    return registry.list_tools()


@app.post("/tools/call", response_model=ToolCallResponse)
async def call_tool(request: ToolCallRequest):
    """
    Call a tool via MCP protocol.
    
    This is the main entry point for tool calls from agents.
    Applies auth and validation middleware before executing the tool.
    """
    start_time = datetime.now(timezone.utc)
    
    # Log the tool call
    logger.info(
        f"Tool call: {request.tool_name} by {request.agent_type}",
        extra={
            "tool_name": request.tool_name,
            "agent_id": request.agent_id,
            "agent_type": request.agent_type,
        },
    )
    
    # Check if tool exists
    tool_func = registry.get_tool(request.tool_name)
    if not tool_func:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{request.tool_name}' not found",
        )
    
    # MIDDLEWARE 1: Authority enforcement
    try:
        require_authority(request.tool_name, request.agent_type)
    except AuthorizationError as e:
        logger.warning(
            f"Authorization failed: {e}",
            extra={
                "tool_name": request.tool_name,
                "agent_type": request.agent_type,
            },
        )
        return ToolCallResponse(
            success=False,
            error={
                "code": 403,
                "type": "UNAUTHORIZED",
                "message": str(e),
                "tool": request.tool_name,
                "agent_type": request.agent_type,
                "allowed_types": e.allowed_agents,
            },
        )
    
    try:
        # MIDDLEWARE 2: Validation (if tool has typed parameters)
        # Get first parameter's type hint for validation
        sig = inspect.signature(tool_func)
        params = list(sig.parameters.values())
        
        if params:
            first_param = params[0]
            param_type = first_param.annotation
            
            # If it's a Pydantic model, validate
            if (
                param_type != inspect.Parameter.empty
                and hasattr(param_type, "__bases__")
                and BaseModel in param_type.__mro__
            ):
                try:
                    validated_args = validate_request(param_type, request.arguments)
                    result = tool_func(validated_args)
                except RequestValidationError as e:
                    logger.warning(
                        f"Validation failed: {e}",
                        extra={
                            "tool_name": request.tool_name,
                            "errors": e.errors,
                        },
                    )
                    return ToolCallResponse(
                        success=False,
                        error={
                            "code": 400,
                            "type": "VALIDATION_ERROR",
                            "message": str(e),
                            "errors": e.errors,
                        },
                    )
            else:
                # Simple arguments (like UUID), pass directly
                result = tool_func(**request.arguments)
        else:
            # No parameters
            result = tool_func()
        
        # Convert Pydantic models to dict for JSON response
        if isinstance(result, BaseModel):
            result = result.model_dump(mode="json")
        
        # Log success
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(
            f"Tool call succeeded: {request.tool_name} ({duration:.3f}s)",
            extra={
                "tool_name": request.tool_name,
                "agent_type": request.agent_type,
                "duration": duration,
                "status": "success",
            },
        )
        
        return ToolCallResponse(success=True, result=result)
        
    except ValueError as e:
        # Business logic errors (e.g., not found)
        logger.error(
            f"Tool call failed: {e}",
            extra={
                "tool_name": request.tool_name,
                "error": str(e),
            },
        )
        return ToolCallResponse(
            success=False,
            error={
                "code": 400,
                "type": "BUSINESS_ERROR",
                "message": str(e),
            },
        )
    
    except Exception as e:
        # Unexpected errors
        logger.exception(
            f"Tool call error: {e}",
            extra={
                "tool_name": request.tool_name,
                "error": str(e),
            },
        )
        return ToolCallResponse(
            success=False,
            error={
                "code": 500,
                "type": "INTERNAL_ERROR",
                "message": str(e),
            },
        )


# =============================================================================
# SERVER STARTUP
# =============================================================================


async def main() -> NoReturn:
    """
    Start the MCP server.

    Registers all tools from:
    - monitor_data.tools.neo4j_tools
    - monitor_data.tools.mongodb_tools
    - monitor_data.tools.qdrant_tools
    - monitor_data.tools.composite_tools

    Applies middleware:
    - monitor_data.middleware.auth (authority enforcement)
    - monitor_data.middleware.validation (schema validation)
    """
    port = int(os.getenv("MCP_SERVER_PORT", "8080"))
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    
    logger.info(f"Starting MCP server on {host}:{port}")
    logger.info(f"Registered {len(registry.tools)} tools")
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
