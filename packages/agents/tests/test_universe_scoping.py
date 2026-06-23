"""
Tests for universe scoping in ContextAssembly.

LAYER: agents
SCOPE: unit tests
"""

from __future__ import annotations


from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from monitor_agents.context_assembly import ContextAssembly


class TestUniverseScopingContextAssembly:
    @pytest.mark.asyncio
    async def test_fetch_memories_scopes_by_universe_id(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="[]")

        scene_id = uuid4()
        story_id = uuid4()
        univ_id = uuid4()

        await agent._fetch_memories(
            scene_id=scene_id,
            story_id=story_id,
            query="test query",
            entity_id=None,
            universe_id=str(univ_id),
        )

        assert agent.call_tool.called
        call_args = agent.call_tool.call_args[0]
        tool_name = call_args[0]
        params = call_args[1]

        assert tool_name == "qdrant_search"
        assert params["collection"] == "memories"
        assert params["filter"]["story_id"] == str(story_id)
        assert params["filter"]["universe_id"] == str(univ_id)

    @pytest.mark.asyncio
    async def test_search_memories_scopes_by_universe_id(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="[]")

        story_id = uuid4()
        univ_id = uuid4()

        await agent._search_memories(
            query="test query",
            story_id=story_id,
            universe_id=str(univ_id),
        )

        assert agent.call_tool.called
        call_args = agent.call_tool.call_args[0]
        tool_name = call_args[0]
        params = call_args[1]

        assert tool_name == "qdrant_search"
        assert params["collection"] == "memories"
        assert params["filter"]["story_id"] == str(story_id)
        assert params["filter"]["universe_id"] == str(univ_id)

    @pytest.mark.asyncio
    async def test_search_snippets_scopes_by_universe_id(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="[]")

        univ_id = uuid4()

        await agent._search_snippets(
            query="test query",
            universe_id=str(univ_id),
        )

        assert agent.call_tool.called
        call_args = agent.call_tool.call_args[0]
        tool_name = call_args[0]
        params = call_args[1]

        assert tool_name == "qdrant_search"
        assert params["collection"] == "snippets"
        assert params["filter"]["universe_id"] == str(univ_id)

    @pytest.mark.asyncio
    async def test_search_snippets_for_entities_scopes_by_universe_id(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="[]")

        univ_id = uuid4()

        with patch(
            "monitor_agents.context_assembly.embed_text", AsyncMock(return_value=[0.1] * 1536)
        ):
            await agent._search_snippets_for_entities(
                query="test query",
                entity_names=["Goblin", "Chest"],
                universe_id=str(univ_id),
            )

        assert agent.call_tool.called
        # Check all calls made to call_tool have the universe_id filter
        for mock_call in agent.call_tool.call_args_list:
            call_args = mock_call[0]
            tool_name = call_args[0]
            params = call_args[1]
            if tool_name == "qdrant_search":
                assert params["filter"]["universe_id"] == str(univ_id)
