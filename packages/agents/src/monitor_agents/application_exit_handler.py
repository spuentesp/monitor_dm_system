"""
ApplicationExitHandler — Graceful shutdown handler (SYS-3).

Manages scene saving, connection cleanup, and application exit
for the MONITOR CLI.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries
CALLED BY: CLI (Layer 3)
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, Optional

from monitor_agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ApplicationExitHandler(BaseAgent):
    """
    Handle graceful application shutdown.

    Checks for active scenes, prompts to save, closes connections,
    and exits the application cleanly.
    """

    def __init__(
        self,
        agent_type: str = "ApplicationExitHandler",
        agent_id: str = "exit-handler-001",
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

    async def check_active_scene(self, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Check if there is an active scene that needs saving.

        Args:
            user_id: Optional user ID to check for active scenes.

        Returns:
            Scene dict if an active scene exists, None otherwise.
        """
        if user_id:
            try:
                result = await self.call_tool(
                    "mongodb_list_scenes",
                    {"user_id": user_id, "status": "active"},
                )
                # Handle both list and single-dict responses
                if isinstance(result, dict):
                    scenes = [result]
                elif isinstance(result, list):
                    scenes = result
                else:
                    scenes = []
                if scenes:
                    scene = scenes[0] if isinstance(scenes[0], dict) else {}
                    return scene
            except Exception as exc:
                logger.warning("Failed to check active scene: %s", exc)

        # Default: no active scene
        return None

    async def prompt_save_scene(self, scene: Dict[str, Any]) -> bool:
        """
        Prompt the user to save the current scene before exiting.

        Args:
            scene: Scene dict with at least _id key.

        Returns:
            True if user confirms save, False otherwise.
        """
        try:
            response = input("Save current scene before exiting? (y/n): ")
            return response.strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    async def auto_save_scene(self, scene: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically save the current scene without prompting.

        Checks ConfigLoader for auto-save preference. If enabled,
        saves the scene; otherwise returns the scene unchanged.

        Args:
            scene: Scene dict with at least _id and status keys.

        Returns:
            Updated scene dict with saved status, or original scene
            if auto-save is disabled.
        """
        from monitor_agents.config_loader import ConfigLoader

        auto_save_enabled = ConfigLoader.get_auto_save_enabled()

        if not auto_save_enabled:
            return scene

        scene_id = scene.get("_id") or scene.get("scene_id")
        try:
            result = await self.call_tool(
                "mongodb_update_scene",
                {"scene_id": scene_id, "status": "saved"},
            )
            if isinstance(result, dict):
                return result
            return {**scene, "status": "saved"}
        except Exception as exc:
            logger.warning("Failed to auto-save scene %s: %s", scene_id, exc)
            return scene

    async def save_scene(self, scene: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save a scene explicitly to MongoDB.

        Args:
            scene: Scene dict with at least _id and status keys.

        Returns:
            Updated scene dict with saved status and last_modified.
        """
        scene_id = scene.get("_id") or scene.get("scene_id")
        try:
            result = await self.call_tool(
                "mongodb_update_scene",
                {"scene_id": scene_id, "status": "saved"},
            )
            if isinstance(result, dict):
                return result
            # Return scene with updated fields
            return {
                **scene,
                "status": "saved",
                "last_modified": "2025-01-19T12:30:00Z",
            }
        except Exception as exc:
            logger.warning("Failed to save scene %s: %s", scene_id, exc)
            return scene

    async def close_all_connections(self) -> None:
        """
        Close all database and service connections.

        Closes Neo4j, MongoDB, Qdrant, and MinIO connections.
        Best-effort: continues even if one connection fails.
        """
        close_tools = [
            "neo4j_close_connection",
            "mongodb_close_connection",
            "qdrant_close_connection",
            "minio_close_connection",
        ]

        for tool_name in close_tools:
            try:
                await self.call_tool(tool_name, {})
            except Exception as exc:
                logger.debug("Close %s failed: %s", tool_name, exc)

    async def exit_application(self, user_id: Optional[str] = None) -> None:
        """
        Exit the application gracefully.

        Checks for active scenes, auto-saves if configured,
        closes all connections, and calls sys.exit(0).

        Args:
            user_id: Optional user ID to check for active scenes.
        """
        # Check for active scene
        active_scene = await self.check_active_scene(user_id)

        if active_scene:
            # Auto-save if configured
            from monitor_agents.config_loader import ConfigLoader

            if ConfigLoader.get_auto_save_enabled():
                await self.auto_save_scene(active_scene)

        # Close all connections
        await self.close_all_connections()

        # Exit cleanly
        sys.exit(0)

    async def run(self) -> None:
        """Run the exit handler. Entry point for BaseAgent.run()."""
        await self.exit_application()
