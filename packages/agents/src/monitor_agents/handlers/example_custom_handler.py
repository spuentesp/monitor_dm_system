"""
Example: Adding a custom commit handler without modifying CanonKeeper.

This demonstrates the Open/Closed Principle - extending behavior
without modifying the core CanonKeeper class.

Usage:
    from monitor_agents.handlers.example_custom_handler import register_handlers
    register_handlers()  # Call once at app startup
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from monitor_agents.handlers.registry import commit_handler


@commit_handler("custom_gizmo")
async def commit_custom_gizmo(
    proposals_coll: Any,
    proposal_id: str,
    proposal: dict[str, Any],
    source_id_strs: list[str] | None,
    verdict: BaseModel,
    agent: Any,  # CanonKeeper instance
) -> None:
    """
    Commit a custom 'gizmo' entity type to Neo4j.

    This handler is registered via the @commit_handler decorator,
    so no modification to CanonKeeper is needed.

    Args:
        proposals_coll: MongoDB collection for proposed_changes
        proposal_id: ID of the proposal document
        proposal: Raw proposal dict from MongoDB
        source_id_strs: Source node IDs for SUPPORTED_BY edges
        verdict: CanonKeeperVerdict with canonical properties
        agent: CanonKeeper instance (provides call_tool, etc.)
    """
    payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}

    result_text = await agent.call_tool(
        "neo4j_create_entity",
        {
            "params": {
                "universe_id": proposal.get("universe_id") or "",
                "name": payload.get("name", "Unnamed Gizmo"),
                "entity_type": "object",
                "sub_type": "gizmo",
                "description": payload.get("description", ""),
                "is_archetype": payload.get("is_archetype", True),
                "properties": {
                    "power_level": payload.get("power_level", 1),
                    "activation_code": payload.get("activation_code", ""),
                    **payload.get("properties", {}),
                },
                "confidence": payload.get("confidence", 0.8),
                "authority": "source",
                "canon_level": payload.get("canon_level", "proposed"),
            }
        },
    )
    agent._check_tool_error(result_text, "neo4j_create_entity")
    agent._store_neo4j_id_on_proposal(proposals_coll, proposal_id, result_text)


@commit_handler("story_completion")
async def commit_story_completion(
    proposals_coll: Any,
    proposal_id: str,
    proposal: dict[str, Any],
    source_id_strs: list[str] | None,
    verdict: BaseModel,
    agent: Any,
) -> None:
    """
    Mark a story as completed in Neo4j.

    This demonstrates that any entity type can be added
    without touching CanonKeeper's core logic.
    """
    payload = proposal.get("payload", {}) or proposal.get("content", {}) or {}

    await agent.call_tool(
        "neo4j_complete_story",
        {
            "story_id": str(payload.get("story_id", "")),
            "finale_summary": payload.get("finale_summary", ""),
            "end_timestamp": payload.get("end_timestamp"),
        },
    )


def register_handlers() -> None:
    """
    Register all custom handlers.

    Call this at application startup:
        from monitor_agents.handlers.example_custom_handler import register_handlers
        register_handlers()
    """
    # Handlers are registered via the @commit_handler decorator,
    # so this function just ensures the module is imported.
    pass
