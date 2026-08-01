from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
from monitor_data.schemas.roleplay_errors import (
    RoleplayError,
    RoleplayErrorCategory,
    RoleplayErrorSource,
)


class TestRoleplayErrorRecorder:
    @pytest.mark.asyncio
    async def test_record_calls_mongodb_tool_with_expected_params(self):
        scene_id = uuid4()
        with patch(
            "monitor_agents.services.roleplay_error_recorder.mongodb_record_roleplay_error"
        ) as mock_tool:
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.GM_AGENT,
                category=RoleplayErrorCategory.GM_DECISION_FAILED,
                message="boom",
                fatal=True,
                scene_id=scene_id,
            )

        mock_tool.assert_called_once()
        (params,) = mock_tool.call_args.args
        assert isinstance(params, RoleplayError)
        assert params.source == RoleplayErrorSource.GM_AGENT
        assert params.category == RoleplayErrorCategory.GM_DECISION_FAILED
        assert params.message == "boom"
        assert params.fatal is True
        assert params.scene_id == scene_id

    @pytest.mark.asyncio
    async def test_record_never_raises_when_mongo_write_fails(self):
        """The one invariant every call site depends on: recording an error
        must never itself break the play loop it's observing."""
        with patch(
            "monitor_agents.services.roleplay_error_recorder.mongodb_record_roleplay_error",
            side_effect=RuntimeError("mongo is down"),
        ):
            # Must not raise.
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.SCENE_LOOP,
                category=RoleplayErrorCategory.UNKNOWN,
                message="anything",
            )

    @pytest.mark.asyncio
    async def test_message_and_detail_are_truncated(self):
        with patch(
            "monitor_agents.services.roleplay_error_recorder.mongodb_record_roleplay_error"
        ) as mock_tool:
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.NARRATOR,
                category=RoleplayErrorCategory.NARRATOR_PARSE_FAILED,
                message="x" * 3000,
                detail="y" * 5000,
            )

        (params,) = mock_tool.call_args.args
        assert len(params.message) == 2000
        assert len(params.detail) == 4000
