"""
Canonical read helpers for Layer-2 agents.

Agents call these instead of importing from monitor_data.tools.neo4j_tools
directly, so the data-layer import boundary stays clean. Sync functions
run in a thread so async agents don't block the event loop.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypeVar, TYPE_CHECKING
from uuid import UUID

import anyio

T = TypeVar("T")

if TYPE_CHECKING:
    from monitor_data.schemas.facts import FactFilter
    from monitor_data.schemas.entities import EntityFilter, EntityListResponse
    from monitor_data.schemas.scenes import SceneCreate, SceneFilter, SceneResponse, SceneUpdate
    from monitor_data.schemas.story_outlines import StoryOutlineCreate, StoryOutlineResponse


# ---------------------------------------------------------------------------
# For the RecapAgent pattern — wraps a sync DB call in a thread so it can
# be awaited from an async agent method.
# ---------------------------------------------------------------------------


async def run_sync_read(func: callable, *args: Any, **kwargs: Any) -> T:
    """Run a sync DB read function in a thread, returning the result to an async caller.

    Usage:
        facts = await run_sync_read(neo4j_list_facts, filters)
    """

    def _call() -> T:
        return func(*args, **kwargs)

    return await anyio.to_thread.run_sync(_call)


# ---------------------------------------------------------------------------
# Individual helpers — call these from async agent methods with run_sync_read:
#
#   facts = await run_sync_read(neo4j_list_facts, filters)
#
# Or directly in a sync context (e.g. inside run_sync_read's own thread):
#
#   facts = await anyio.to_thread.run_sync(lambda: neo4j_list_facts(filters))
# ---------------------------------------------------------------------------


def neo4j_get_universe(universe_id: UUID) -> Optional[Dict[str, Any]]:
    """Fetch a universe node by UUID (sync). Returns {} if not found."""
    from monitor_data.tools.neo4j_tools.core import neo4j_get_universe as _fn

    result = _fn(universe_id)
    if result is None:
        return None
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)


def neo4j_list_facts(filters: "FactFilter") -> List[Dict[str, Any]]:
    """List facts matching a filter (sync)."""
    from monitor_data.tools.neo4j_tools.facts import neo4j_list_facts as _fn

    result = _fn(filters)
    # Each item is a FactResponse — convert to dict for callers that expect JSON-like output
    return [r.model_dump(mode="json") if hasattr(r, "model_dump") else dict(r) for r in result]


def mongodb_get_story_outline(story_id: UUID) -> Dict[str, Any] | None:
    """Fetch a story outline by UUID (sync)."""
    from monitor_data.tools.mongodb_tools.stories import mongodb_get_story_outline as _fn

    result = _fn(story_id)
    if result is None:
        return None
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)


def mongodb_list_scenes(filters: "SceneFilter") -> Dict[str, Any]:
    """List scenes matching a filter (sync)."""
    from monitor_data.tools.mongodb_tools.scenes import mongodb_list_scenes as _fn

    result = _fn(filters)
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)


def mongodb_create_scene(params: "SceneCreate") -> "SceneResponse":
    """Create a scene document in MongoDB (sync)."""
    from monitor_data.tools.mongodb_tools.scenes import mongodb_create_scene as _fn

    return _fn(params)


def mongodb_create_story_outline(params: "StoryOutlineCreate") -> "StoryOutlineResponse":
    """Create a story outline document in MongoDB (sync)."""
    from monitor_data.tools.mongodb_tools.stories import mongodb_create_story_outline as _fn

    return _fn(params)


def neo4j_list_entities(filters: "EntityFilter") -> "EntityListResponse":
    """List entities matching a filter (sync). Returns EntityListResponse."""
    from monitor_data.tools.neo4j_tools.entities import neo4j_list_entities as _fn

    return _fn(filters)


def mongodb_update_turn_resolution(
    scene_id: UUID,
    turn_id: UUID,
    resolution_id: UUID,
    summary: Optional[str] = None,
    checkpoint: Optional[Dict[str, Any]] = None,
) -> bool:
    """Link a resolution_ref to a turn in MongoDB (sync). Returns True if updated."""
    from monitor_data.tools.mongodb_tools.scenes import mongodb_update_turn_resolution as _fn

    return _fn(
        scene_id=scene_id,
        turn_id=turn_id,
        resolution_id=resolution_id,
        summary=summary,
        checkpoint=checkpoint,
    )


def mongodb_create_resolution(params: Any) -> Any:
    """Create a resolution record in MongoDB (sync)."""
    from monitor_data.tools.mongodb_tools import mongodb_create_resolution as _fn

    return _fn(params)


def mongodb_get_scene(scene_id: UUID) -> Any:
    """Get a scene by UUID (sync)."""
    from monitor_data.tools.mongodb_tools.scenes import mongodb_get_scene as _fn

    return _fn(scene_id)


def mongodb_update_scene(scene_id: UUID, params: "SceneUpdate") -> "SceneResponse":
    """Update a scene document in MongoDB (sync)."""
    from monitor_data.tools.mongodb_tools.scenes import mongodb_update_scene as _fn

    return _fn(scene_id, params)
