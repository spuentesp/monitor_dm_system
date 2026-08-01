"""Best-effort recorder that persists structured roleplay errors to MongoDB.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1) only
CALLED BY: scene_loop, gm_agent, resolver, narrator, canonkeeper, preplay_support,
    character_conversation router

Extends the ingestion pipeline's structured LastError pattern
(monitor_data.schemas.ingestion_jobs) into the live play loop, which
previously only logged failures via structlog/logging with nothing
persisted or queryable afterward. See docs history / GAP notes for why:
real live runs surface a steady stream of small, independent bugs across
every subsystem that the hermetic test suite cannot catch (it mocks
LLM/Mongo/Neo4j), and until now there was no durable record of them.

Recording an error must never itself raise — a failure in
``RoleplayErrorRecorder.record`` is logged and swallowed so it can never
break the play loop it is trying to observe.
"""

from __future__ import annotations

from uuid import UUID

import anyio
import structlog

from monitor_data.schemas.roleplay_errors import (
    RoleplayError,
    RoleplayErrorCategory,
    RoleplayErrorSource,
)
from monitor_data.tools.mongodb_tools import mongodb_record_roleplay_error

log = structlog.get_logger(__name__)


class RoleplayErrorRecorder:
    """Thin, never-raising wrapper around ``mongodb_record_roleplay_error``."""

    @staticmethod
    async def record(
        *,
        source: RoleplayErrorSource,
        category: RoleplayErrorCategory,
        message: str,
        detail: str | None = None,
        fatal: bool = False,
        llm_error_class: str | None = None,
        universe_id: UUID | None = None,
        story_id: UUID | None = None,
        scene_id: UUID | None = None,
        conversation_id: str | None = None,
        turn_id: UUID | None = None,
        entity_id: UUID | None = None,
    ) -> None:
        """Persist a single roleplay error event. Never raises.

        ``message`` should be the human-readable failure text (typically
        ``str(exc)``); ``detail`` is optional free-form diagnostic context
        (e.g. a traceback tail).
        """
        try:
            params = RoleplayError(
                source=source,
                category=category,
                message=message[:2000],
                detail=detail[:4000] if detail else None,
                fatal=fatal,
                llm_error_class=llm_error_class,
                universe_id=universe_id,
                story_id=story_id,
                scene_id=scene_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                entity_id=entity_id,
            )
            await anyio.to_thread.run_sync(mongodb_record_roleplay_error, params)
        except Exception as exc:  # noqa: BLE001 - recording must never break the caller
            log.warning(
                "roleplay_error_recorder.record_failed",
                source=str(source),
                category=str(category),
                error=str(exc),
            )
