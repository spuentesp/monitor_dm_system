"""
AppInitializer — Application startup and health-check agent (SYS-1).

Orchestrates health checks for all data-layer services (Neo4j, MongoDB,
Qdrant, MinIO, LLM) and returns a consolidated initialization status.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries
CALLED BY: CLI (Layer 3)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from monitor_agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AppInitializer(BaseAgent):
    """
    Initialize the MONITOR application by checking all service health.

    Calls each data-layer health-check tool and aggregates results into
    a single initialization report.
    """

    def __init__(
        self,
        agent_type: str = "AppInitializer",
        agent_id: str = "app-initializer-001",
        model: Optional[str] = None,
        mcp_client: Optional[Any] = None,
        llm_client: Optional[Any] = None,
    ) -> None:
        super().__init__(agent_type=agent_type, agent_id=agent_id, model=model)
        self._mcp_client = mcp_client
        self._llm_client = llm_client

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call an MCP tool, using injected client if available."""
        if self._mcp_client is not None:
            return await self._mcp_client.call_tool(tool_name, arguments)
        return await super().call_tool(tool_name, arguments)

    async def initialize(self) -> Dict[str, Any]:
        """
        Run health checks for all services and return initialization status.

        Returns:
            Dict with keys:
                success (bool): True only if ALL services are healthy
                health_status (dict): Per-service health results
                errors (list[str]): Error messages for unhealthy services
                warnings (list[str]): Non-critical warnings
        """
        health_status: Dict[str, Any] = {}
        errors: List[str] = []
        warnings: List[str] = []

        checks = [
            ("neo4j", "neo4j_health_check"),
            ("mongodb", "mongodb_health_check"),
            ("qdrant", "qdrant_health_check"),
            ("minio", "minio_health_check"),
            ("llm", "llm_health_check"),
        ]

        for service_name, tool_name in checks:
            try:
                start = time.monotonic()
                result = await self.call_tool(tool_name, {})
                elapsed_ms = int((time.monotonic() - start) * 1000)

                healthy = result.get("healthy", False) if isinstance(result, dict) else False
                health_status[service_name] = {
                    "healthy": healthy,
                    "message": result.get("message", "")
                    if isinstance(result, dict)
                    else str(result),
                    "response_time_ms": result.get("response_time_ms", elapsed_ms)
                    if isinstance(result, dict)
                    else elapsed_ms,
                }

                if not healthy:
                    errors.append(
                        f"{service_name}: {result.get('message', 'unhealthy') if isinstance(result, dict) else 'unhealthy'}"
                    )
                elif elapsed_ms > 2000:
                    warnings.append(f"{service_name}: slow response ({elapsed_ms}ms)")

            except Exception as exc:
                health_status[service_name] = {
                    "healthy": False,
                    "message": str(exc),
                    "response_time_ms": -1,
                }
                errors.append(f"{service_name}: {exc}")

        success = len(errors) == 0

        return {
            "success": success,
            "health_status": health_status,
            "errors": errors,
            "warnings": warnings,
        }

    async def run(self) -> Dict[str, Any]:
        """Run the initialization check. Entry point for BaseAgent.run()."""
        return await self.initialize()
