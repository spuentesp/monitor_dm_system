"""
Logging middleware for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only
CALLED BY: MCP server (server.py)

This middleware logs all tool calls with caller identity, parameters,
and result status for auditing and debugging.
"""

import logging
import time
from typing import Any, Dict, Optional
from uuid import UUID
import json

# Configure logger to write to stderr (safe for STDIO transport)
logger = logging.getLogger(__name__)


class ToolCallLogger:
    """
    Logs MCP tool calls with metadata for auditing and debugging.

    Captures:
    - Caller identity (agent_id, agent_type)
    - Tool name
    - Input parameters (sanitized)
    - Execution time
    - Success/failure status
    - Error messages (if failed)
    """

    def __init__(self):
        """Initialize the tool call logger."""
        self.logger = logger

    def log_tool_call(
        self,
        tool_name: str,
        agent_type: str,
        agent_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        execution_time_ms: Optional[float] = None,
    ) -> None:
        """
        Log a tool call with metadata.

        Args:
            tool_name: Name of the tool called
            agent_type: Type of calling agent (CanonKeeper, Narrator, etc.)
            agent_id: Optional unique identifier for the agent instance
            parameters: Input parameters (will be sanitized)
            success: Whether the call succeeded
            error_message: Error message if failed
            execution_time_ms: Execution time in milliseconds

        Examples:
            >>> logger = ToolCallLogger()
            >>> logger.log_tool_call(
            ...     "neo4j_create_entity",
            ...     "CanonKeeper",
            ...     parameters={"name": "Gandalf"},
            ...     success=True,
            ...     execution_time_ms=45.2
            ... )
        """
        log_data: Dict[str, Any] = {
            "tool": tool_name,
            "agent_type": agent_type,
            "agent_id": agent_id,
            "success": success,
            "execution_time_ms": execution_time_ms,
        }

        if not success and error_message:
            log_data["error"] = error_message

        # Comment 2 fix: Use _sanitize_parameters for better debugging
        if parameters:
            log_data["params"] = self._sanitize_parameters(parameters)

        # Format as single-line JSON for structured logging
        log_message = json.dumps(log_data)

        if success:
            self.logger.info(log_message)
        else:
            self.logger.error(log_message)

    def _sanitize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize parameters to remove sensitive data before logging.

        Args:
            parameters: Raw input parameters

        Returns:
            Sanitized parameters safe for logging
        """
        sanitized: Dict[str, Any] = {}
        sensitive_keys = {
            "password",
            "token",
            "secret",
            "api_key",
            "private_key",
            "credentials",
        }

        for key, value in parameters.items():
            # Check if key contains sensitive words
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, (str, int, float, bool, type(None))):
                sanitized[key] = value
            elif isinstance(value, UUID):
                sanitized[key] = str(value)
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts
                sanitized[key] = self._sanitize_parameters(value)
            elif isinstance(value, list):
                sanitized[key] = f"<list:{len(value)} items>"
            else:
                sanitized[key] = f"<{type(value).__name__}>"

        return sanitized


# Global logger instance
_tool_call_logger = ToolCallLogger()


def log_tool_call(
    tool_name: str,
    agent_type: str,
    agent_id: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    execution_time_ms: Optional[float] = None,
) -> None:
    """
    Log a tool call using the global logger instance.

    Args:
        tool_name: Name of the tool called
        agent_type: Type of calling agent
        agent_id: Optional unique identifier for the agent
        parameters: Input parameters
        success: Whether the call succeeded
        error_message: Error message if failed
        execution_time_ms: Execution time in milliseconds
    """
    _tool_call_logger.log_tool_call(
        tool_name,
        agent_type,
        agent_id,
        parameters,
        success,
        error_message,
        execution_time_ms,
    )


class ToolCallTimer:
    """Context manager for timing tool calls."""

    def __init__(self):
        self.start_time = None
        self.end_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.end_time = time.time()

    @property
    def elapsed_ms(self) -> float:
        """
        Get elapsed time in milliseconds.

        Returns current elapsed time even if context manager hasn't exited yet.
        """
        if self.start_time is None:
            return 0.0

        # If end_time is None, calculate based on current time (Comment 4 fix)
        end = self.end_time if self.end_time is not None else time.time()
        return (end - self.start_time) * 1000.0
