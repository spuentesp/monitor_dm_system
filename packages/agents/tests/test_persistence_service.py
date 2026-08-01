from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

# Import order matters here: monitor_agents.loops.scene_support pulls in the
# monitor_agents.loops package, whose __init__ imports scene_loop, which
# imports persistence_service back — a pre-existing circular import that
# only surfaces when persistence_service is the very first entry point into
# that cycle. Importing scene_loop first (as production code paths always
# do) sidesteps it.
import monitor_agents.loops.scene_loop  # noqa: F401
from monitor_agents.services.persistence_service import PersistenceService
from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource


class TestPersistMemoriesErrorRecording:
    """persist_memories swallows per-item failures (best-effort) but must
    now also record them via RoleplayErrorRecorder so they're queryable
    afterward instead of only existing as a log line."""

    @pytest.mark.asyncio
    async def test_entity_not_found_records_memory_persist_not_found(self):
        entity_id = uuid4()
        scene_id = uuid4()
        story_id = uuid4()
        universe_id = uuid4()

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_memory",
                side_effect=ValueError(f"Entity {entity_id} not found in Neo4j or MongoDB"),
            ),
            patch(
                "monitor_agents.services.persistence_service.RoleplayErrorRecorder.record",
                new_callable=AsyncMock,
            ) as mock_record,
        ):
            result = await PersistenceService.persist_memories(
                entity_id=entity_id,
                scene_id=scene_id,
                story_id=story_id,
                universe_id=universe_id,
                memories=[{"text": "a memory", "importance": 5}],
            )

        assert result == []
        mock_record.assert_awaited_once()
        _, kwargs = mock_record.call_args
        assert kwargs["source"] == RoleplayErrorSource.SCENE_LOOP
        assert kwargs["category"] == RoleplayErrorCategory.MEMORY_PERSIST_NOT_FOUND
        assert kwargs["fatal"] is False
        assert kwargs["entity_id"] == entity_id
        assert kwargs["scene_id"] == scene_id
        assert kwargs["story_id"] == story_id
        assert kwargs["universe_id"] == universe_id

    @pytest.mark.asyncio
    async def test_non_value_error_records_unknown_category(self):
        entity_id = uuid4()
        scene_id = uuid4()
        story_id = uuid4()
        universe_id = uuid4()

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_memory",
                side_effect=RuntimeError("boom"),
            ),
            patch(
                "monitor_agents.services.persistence_service.RoleplayErrorRecorder.record",
                new_callable=AsyncMock,
            ) as mock_record,
        ):
            await PersistenceService.persist_memories(
                entity_id=entity_id,
                scene_id=scene_id,
                story_id=story_id,
                universe_id=universe_id,
                memories=[{"text": "a memory", "importance": 5}],
            )

        _, kwargs = mock_record.call_args
        assert kwargs["category"] == RoleplayErrorCategory.UNKNOWN

    @pytest.mark.asyncio
    async def test_success_never_records(self):
        entity_id = uuid4()
        response = AsyncMock()
        response.memory_id = uuid4()

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_memory",
                return_value=response,
            ),
            patch(
                "monitor_agents.services.persistence_service.RoleplayErrorRecorder.record",
                new_callable=AsyncMock,
            ) as mock_record,
        ):
            result = await PersistenceService.persist_memories(
                entity_id=entity_id,
                scene_id=uuid4(),
                story_id=uuid4(),
                universe_id=uuid4(),
                memories=[{"text": "a memory", "importance": 5}],
            )

        assert result == [response.memory_id]
        mock_record.assert_not_awaited()
