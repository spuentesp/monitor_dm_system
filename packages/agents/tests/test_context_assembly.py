"""
Tests for the ContextAssembly agent.

Covers:
- _fetch_entities: MCP tool call + JSON parsing + empty/invalid responses
- _fetch_memories: MCP tool call with story/query filter handling
- _fetch_recent_turns: MCP tool call + parsing
- _search_memories: Qdrant search wrapper
- _search_snippets: Qdrant search wrapper
- _build_scene_summary: scene summary from MongoDB
- _summarise_context: DSPy module call
- assemble: full pipeline composition
- retrieve_turn_context: query formulation + parallel fetch + summarize

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_context_assembly.py -v
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_agents.context_assembly.agent import ContextAssembly

# ===========================================================================
# _fetch_entities
# ===========================================================================


class TestFetchEntities:
    @pytest.mark.asyncio
    async def test_uses_cached_entities_when_available(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        cached_entities = [{"id": "cached", "name": "Goblin"}]
        agent._cache_key = MagicMock(return_value="solo_play:scene_entities:test")
        agent._cache_get_json = MagicMock(return_value=cached_entities)
        agent.call_tool = AsyncMock()

        result = await agent._fetch_entities(scene_id=uuid4())

        assert result == cached_entities
        agent.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_parsed_json_list(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        entities = [{"id": "e1", "name": "Goblin"}, {"id": "e2", "name": "Chest"}]
        agent.call_tool = AsyncMock(return_value=json.dumps(entities))

        result = await agent._fetch_entities(scene_id=uuid4())

        assert result == entities
        agent.call_tool.assert_called_once_with(
            "neo4j_get_entities_by_scene",
            {"scene_id": str(agent.call_tool.call_args[0][1]["scene_id"])},
        )

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_tool_returns_none(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value=None)

        result = await agent._fetch_entities(scene_id=uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_tool_returns_empty_string(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="")

        result = await agent._fetch_entities(scene_id=uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_invalid_json(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="not json{{{")

        result = await agent._fetch_entities(scene_id=uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_list_when_tool_returns_list_directly(self):
        """When tool returns a Python list instead of JSON string, still works."""
        agent = ContextAssembly.__new__(ContextAssembly)
        entities = [{"id": "e1"}]
        agent.call_tool = AsyncMock(return_value=entities)

        result = await agent._fetch_entities(scene_id=uuid4())

        assert result == entities


# ===========================================================================
# _fetch_recent_turns
# ===========================================================================


class TestFetchRecentTurns:
    @pytest.mark.asyncio
    async def test_returns_parsed_turns(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        turns = [{"role": "user", "text": "I attack"}, {"role": "gm", "text": "You miss."}]
        agent.call_tool = AsyncMock(return_value=json.dumps(turns))

        result = await agent._fetch_recent_turns(scene_id=uuid4())

        assert result == turns

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_empty_response(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value=None)

        result = await agent._fetch_recent_turns(scene_id=uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_bad_json(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="<<<bad>>>")

        result = await agent._fetch_recent_turns(scene_id=uuid4())

        assert result == []


# ===========================================================================
# _search_memories
# ===========================================================================


class TestSearchMemories:
    @pytest.mark.asyncio
    async def test_returns_parsed_memories(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        memories = [{"content": "goblin was guarding the chest", "score": 0.91}]
        agent.call_tool = AsyncMock(return_value=json.dumps(memories))
        story_id = uuid4()

        result = await agent._search_memories("goblin chest", story_id=story_id)

        assert result == memories
        agent.call_tool.assert_called_once_with(
            "qdrant_search",
            {
                "collection": "memories",
                "query_text": "goblin chest",
                "limit": 8,
                "filter": {"story_id": str(story_id)},
            },
        )

    @pytest.mark.asyncio
    async def test_returns_empty_on_none_response(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value=None)

        result = await agent._search_memories("any query", story_id=uuid4())

        assert result == []


# ===========================================================================
# _search_snippets
# ===========================================================================


class TestSearchSnippets:
    @pytest.mark.asyncio
    async def test_returns_parsed_snippets(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        snippets = [{"document": "lore text", "score": 0.85}]
        agent.call_tool = AsyncMock(return_value=json.dumps(snippets))

        result = await agent._search_snippets("ancient ruins")

        assert result == snippets

    @pytest.mark.asyncio
    async def test_returns_empty_on_invalid_json(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="bad")

        result = await agent._search_snippets("query")

        assert result == []

    @pytest.mark.asyncio
    async def test_scopes_snippets_to_universe(self):
        # T-093: when a universe is given, the qdrant search must carry a
        # universe_id filter so one world never retrieves another's snippets.
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value=json.dumps([]))

        await agent._search_snippets("ruins", universe_id="11111111-1111-1111-1111-111111111111")

        params = agent.call_tool.call_args[0][1]
        assert params["collection"] == "snippets"
        assert params["filter"] == {"universe_id": "11111111-1111-1111-1111-111111111111"}

    @pytest.mark.asyncio
    async def test_no_universe_filter_when_unscoped(self):
        # Backward compatible: no universe → no filter key (legacy behaviour).
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value=json.dumps([]))

        await agent._search_snippets("ruins")

        params = agent.call_tool.call_args[0][1]
        assert "filter" not in params


# ===========================================================================
# _fetch_game_system
# ===========================================================================


class TestFetchGameSystem:
    @pytest.mark.asyncio
    async def test_prefers_explicit_system_id(self, monkeypatch):
        agent = ContextAssembly.__new__(ContextAssembly)

        expected = {
            "system_id": "narrative-pure-id",
            "name": "Narrative Pure",
            "core_mechanic": {"type": "narrative"},
        }

        collection = MagicMock()
        collection.find_one.side_effect = [expected]
        mongodb = MagicMock()
        mongodb.get_collection.return_value = collection

        monkeypatch.setattr(
            "monitor_data.db.mongodb.get_mongodb_client",
            lambda: mongodb,
        )
        monkeypatch.setattr(agent, "_cache_get_json", lambda _k: None)
        monkeypatch.setattr(agent, "_cache_set_json", lambda _k, _v, **_kw: None)

        result = await agent._fetch_game_system(
            universe_id="u-1",
            system_id="narrative-pure-id",
        )

        assert result == expected
        collection.find_one.assert_called_once_with(
            {"system_id": "narrative-pure-id"},
            projection={"_id": 0},
        )

    @pytest.mark.asyncio
    async def test_prefers_pack_embedded_source_binding(self, monkeypatch):
        agent = ContextAssembly.__new__(ContextAssembly)

        embedded_doc = {
            "name": "Haunted Seas",
            "core_mechanic": {"type": "dice_pool", "formula": "2d6"},
            "attributes": [],
            "skills": [],
            "resources": [],
        }

        collection = MagicMock()
        mongodb = MagicMock()
        mongodb.get_collection.return_value = collection

        monkeypatch.setattr(
            "monitor_data.db.mongodb.get_mongodb_client",
            lambda: mongodb,
        )
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
            lambda _uid: SimpleNamespace(
                game_system_data=SimpleNamespace(model_dump=lambda mode="json": embedded_doc),
                game_system_id=None,
            ),
        )

        result = await agent._fetch_game_system(
            universe_id="u-1",
            system_source_type="pack_embedded",
            system_source_id=str(uuid4()),
        )

        assert result == embedded_doc
        collection.find_one.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_binding_can_be_resolved(self, monkeypatch):
        agent = ContextAssembly.__new__(ContextAssembly)

        collection = MagicMock()
        mongodb = MagicMock()
        mongodb.get_collection.return_value = collection

        monkeypatch.setattr(
            "monitor_data.db.mongodb.get_mongodb_client",
            lambda: mongodb,
        )

        result = await agent._fetch_game_system(universe_id="u-1")

        assert result == {}
        collection.find_one.assert_not_called()


# ===========================================================================
# _build_scene_summary
# ===========================================================================


class TestBuildSceneSummary:
    @pytest.mark.asyncio
    async def test_returns_summary_string(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="A dimly lit dungeon corridor")

        result = await agent._build_scene_summary(scene_id=uuid4())

        assert result == "A dimly lit dungeon corridor"

    @pytest.mark.asyncio
    async def test_returns_fallback_when_none(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value=None)

        result = await agent._build_scene_summary(scene_id=uuid4())

        assert result == "Unknown scene"

    @pytest.mark.asyncio
    async def test_returns_fallback_when_empty_string(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value="")

        result = await agent._build_scene_summary(scene_id=uuid4())

        assert result == "Unknown scene"


# ===========================================================================
# _summarise_context
# ===========================================================================


class TestSummariseContext:
    @pytest.mark.asyncio
    async def test_uses_deterministic_scoring_to_summarise(self):
        agent = ContextAssembly()

        result = await agent._summarise_context(
            player_action="approach the chest",
            entities=[
                {
                    "id": "e1",
                    "name": "Chest",
                    "description": "A wooden chest.",
                    "entity_type": "Entity",
                }
            ],
            memories=[{"content": "A goblin guards the treasure."}],
            snippets=[],
        )

        assert "Context for action: approach the chest" in result
        assert "[Entity] Chest (Entity) A wooden chest." in result
        assert "[Memory] A goblin guards the treasure." in result

    @pytest.mark.asyncio
    async def test_ranks_by_relevance_to_player_action(self):
        agent = ContextAssembly()

        # 'dragon' should rank higher than 'market' for this action
        result = await agent._summarise_context(
            player_action="The dragon breathes fire",
            entities=[
                {"name": "Market", "description": "Busy bazaar."},
                {"name": "Dragon", "description": "Great red beast."},
            ],
            memories=[],
            snippets=[],
        )

        dragon_pos = result.find("Dragon")
        market_pos = result.find("Market")
        assert dragon_pos < market_pos


# ===========================================================================
# _fetch_memories (with story/scene query filter)
# ===========================================================================


class TestFetchMemories:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_query(self):
        """Empty query string short-circuits and returns []."""
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock()

        result = await agent._fetch_memories(scene_id=uuid4(), story_id=uuid4(), query="")

        assert result == []
        agent.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_qdrant_search_with_memories_filter(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        memories = [{"content": "the guard patrols at night"}]
        agent.call_tool = AsyncMock(return_value=json.dumps(memories))

        story_id = uuid4()
        result = await agent._fetch_memories(scene_id=uuid4(), story_id=story_id, query="guard patrol")

        assert result == memories
        call_args = agent.call_tool.call_args[0]
        assert call_args[0] == "qdrant_search"
        assert call_args[1]["collection"] == "memories"
        assert "guard patrol" in call_args[1]["query_text"]

    @pytest.mark.asyncio
    async def test_returns_empty_on_none_response(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(return_value=None)

        result = await agent._fetch_memories(scene_id=uuid4(), story_id=uuid4(), query="something")

        assert result == []


# ===========================================================================
# assemble (public API)
# ===========================================================================


class TestAssemble:
    @pytest.mark.asyncio
    async def test_assemble_returns_entities_memories_turns(self):
        """assemble() merges all three fetch results into a single dict."""
        agent = ContextAssembly.__new__(ContextAssembly)
        agent._cache_key = MagicMock(return_value="solo_play:assemble:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._fetch_entities = AsyncMock(return_value=[{"id": "e1"}])
        agent._fetch_memories = AsyncMock(return_value=[{"content": "mem1"}])
        agent._fetch_recent_turns = AsyncMock(return_value=[{"role": "user"}])
        agent._fetch_game_system = AsyncMock(return_value={})
        agent._fetch_runtime_profile = AsyncMock(return_value={})

        result = await agent.assemble(scene_id=uuid4(), story_id=uuid4())

        assert "entities" in result
        assert "memories" in result
        assert "turns" in result
        assert result["entities"] == [{"id": "e1"}]
        assert result["memories"] == [{"content": "mem1"}]
        assert result["turns"] == [{"role": "user"}]

    @pytest.mark.asyncio
    async def test_assemble_adds_summary_when_player_action_given(self):
        """assemble() calls _summarise_context when player_action is provided."""
        agent = ContextAssembly.__new__(ContextAssembly)
        agent._cache_key = MagicMock(return_value="solo_play:assemble:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._fetch_entities = AsyncMock(return_value=[])
        agent._fetch_memories = AsyncMock(return_value=[])
        agent._fetch_recent_turns = AsyncMock(return_value=[])
        agent._fetch_game_system = AsyncMock(return_value={})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._summarise_context = AsyncMock(return_value="Brief summary.")

        result = await agent.assemble(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action="I look around",
        )

        assert "summary" in result
        assert result["summary"] == "Brief summary."
        agent._summarise_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_assemble_no_summary_without_player_action(self):
        """assemble() omits summary when player_action is not provided."""
        agent = ContextAssembly.__new__(ContextAssembly)
        agent._cache_key = MagicMock(return_value="solo_play:assemble:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._fetch_entities = AsyncMock(return_value=[])
        agent._fetch_memories = AsyncMock(return_value=[])
        agent._fetch_recent_turns = AsyncMock(return_value=[])
        agent._fetch_game_system = AsyncMock(return_value={})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._summarise_context = AsyncMock()

        result = await agent.assemble(scene_id=uuid4(), story_id=uuid4())

        assert "summary" not in result
        agent._summarise_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_assemble_injects_lorebook_entries(self, monkeypatch):
        """assemble() should call mongodb_scan_lorebook via call_tool and include results in profile_context."""
        agent = ContextAssembly.__new__(ContextAssembly)
        agent._cache_key = MagicMock(return_value="solo_play:assemble:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._fetch_entities = AsyncMock(return_value=[])
        agent._fetch_memories = AsyncMock(return_value=[])
        agent._fetch_recent_turns = AsyncMock(return_value=[])
        agent._fetch_game_system = AsyncMock(return_value={})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._summarise_context = AsyncMock(return_value="Summary with lore.")

        # Mock call_tool to return lorebook entries when called with the scan tool
        async def mock_call_tool(tool_name, arguments):
            if tool_name == "mongodb_scan_lorebook":
                return {
                    "before": [],
                    "after": ["Lore about dragons"],
                    "depth": [],
                    "triggered_entry_ids": ["e1"],
                }
            if tool_name == "mongodb_get_scan_config":
                return {
                    "scan_depth": 2,
                    "token_budget": 500,
                    "recursive_scanning": True,
                    "case_sensitive": False,
                    "match_whole_words": False,
                    "include_names": True,
                }
            return {}

        agent.call_tool = AsyncMock(side_effect=mock_call_tool)

        actor_context = {"id": str(uuid4()), "name": "Hero"}
        player_context_id = actor_context["id"]
        player_action = "I look for dragons"

        await agent.assemble(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action=player_action,
            actor_context=actor_context,
        )

        agent.call_tool.assert_any_call(
            "mongodb_scan_lorebook",
            {
                "character_ids": [player_context_id],
                "text": player_action,
                "history": [],
                "config": {
                    "scan_depth": 2,
                    "token_budget": 500,
                    "recursive_scanning": True,
                    "case_sensitive": False,
                    "match_whole_words": False,
                    "include_names": True,
                },
                "turn_index": 0,
                "increment_triggers": True,
            },
        )

        # Check if profile_context passed to _summarise_context contains the lore
        profile_context_passed = agent._summarise_context.call_args[1]["profile_context"]
        assert "RELEVANT LOREBOOK ENTRIES:" in profile_context_passed
        assert "Lore about dragons" in profile_context_passed

        # Check if matched_lore is in the result dict
        result = await agent.assemble(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action=player_action,
            actor_context=actor_context,
        )
        assert result["lorebook_entries"] == ["Lore about dragons"]


# ===========================================================================
# retrieve_turn_context (public API)
# ===========================================================================


class TestRetrieveTurnContext:
    @pytest.mark.asyncio
    async def test_returns_entities_memories_snippets_summary(self):
        """retrieve_turn_context returns all four keys."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "goblin threat"
        fake_queries.snippet_query = "dungeon"
        mock_formulator = MagicMock(return_value=fake_queries)
        agent._query_formulator = mock_formulator
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()

        agent._build_scene_summary = AsyncMock(return_value="Dark corridor")
        agent._fetch_entities = AsyncMock(return_value=[{"id": "e1"}])
        agent._fetch_game_system = AsyncMock(return_value={"name": "Narrative Pure"})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._search_memories = AsyncMock(return_value=[{"content": "mem"}])
        agent._search_snippets_for_entities = AsyncMock(return_value=[{"doc": "lore"}])
        agent._summarise_context = AsyncMock(return_value="Enemy close.")

        story_id = uuid4()
        result = await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=story_id,
            player_action="draw sword",
        )

        assert "entities" in result
        assert "memories" in result
        assert "snippets" in result
        assert "summary" in result
        assert result["summary"] == "Enemy close."
        agent._search_memories.assert_awaited_once_with(
            "goblin threat",
            story_id=story_id,
            universe_id=None,
        )

    @pytest.mark.asyncio
    async def test_query_formulator_called_with_player_action(self):
        """retrieve_turn_context passes player_action to the query formulator."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "q"
        fake_queries.snippet_query = "q"
        mock_formulator = MagicMock(return_value=fake_queries)
        agent._query_formulator = mock_formulator
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()

        agent._build_scene_summary = AsyncMock(return_value="scene")
        agent._fetch_entities = AsyncMock(return_value=[])
        agent._fetch_game_system = AsyncMock(return_value={})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._search_memories = AsyncMock(return_value=[])
        agent._search_snippets_for_entities = AsyncMock(return_value=[])
        agent._summarise_context = AsyncMock(return_value="x")

        story_id = uuid4()
        await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=story_id,
            player_action="cast a spell",
        )

        call_kwargs = mock_formulator.call_args[1]
        assert call_kwargs["player_action"] == "cast a spell"
        agent._search_memories.assert_awaited_once_with("q", story_id=story_id, universe_id=None)

    @pytest.mark.asyncio
    async def test_reuses_cached_turn_context_on_repeat_lookup(self):
        """A repeated identical turn should hit the runtime cache instead of repeating retrieval work."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "goblin threat"
        fake_queries.snippet_query = "dungeon"
        agent._query_formulator = MagicMock(return_value=fake_queries)

        expected = {
            "entities": [{"id": "e1"}],
            "memories": [{"content": "mem"}],
            "snippets": [{"doc": "lore"}],
            "summary": "Enemy close.",
            "source_profile": {"system_name": "Narrative Pure"},
            "source_scope": {
                "system_name": "Narrative Pure",
                "preferred_semantic_categories": ["general"],
                "preferred_terms": [],
            },
            "traversal_mask": {
                "intent_family": "general",
                "preferred_rel_types": ["RELATED_TO", "KNOWS", "LOCATED_IN", "PARTICIPATES_IN"],
                "allowed_rel_types": ["RELATED_TO", "KNOWS", "LOCATED_IN", "PARTICIPATES_IN"],
                "seed_entity_ids": ["e1"],
                "source_categories": ["general"],
                "hop_limit": 2,
            },
            "traversal_candidates": [{"counterpart_name": "Prince Marcel"}],
        }

        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(side_effect=[None, expected])
        agent._cache_set_json = MagicMock()
        agent._build_scene_summary = AsyncMock(return_value="Dark corridor")
        agent._fetch_entities = AsyncMock(return_value=expected["entities"])
        agent._fetch_game_system = AsyncMock(return_value={"name": "Narrative Pure"})
        agent._fetch_runtime_profile = AsyncMock(return_value=expected["source_profile"])
        agent._search_memories = AsyncMock(return_value=expected["memories"])
        agent._collect_traversal_candidates = AsyncMock(return_value=expected["traversal_candidates"])
        agent._search_snippets_for_entities = AsyncMock(return_value=expected["snippets"])
        agent._summarise_context = AsyncMock(return_value=expected["summary"])

        first = await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action="draw sword",
        )
        second = await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action="draw sword",
        )

        assert first == expected
        assert second == expected
        agent._build_scene_summary.assert_called_once()
        agent._fetch_entities.assert_called_once()
        agent._search_memories.assert_called_once()
        agent._collect_traversal_candidates.assert_called_once()
        agent._search_snippets_for_entities.assert_called_once()
        agent._summarise_context.assert_called_once()
        agent._cache_set_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_memory_only_turn_context_skips_entities_snippets_and_summary(self):
        """Hot turn retrieval should skip unused entity/snippet/summary work."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "goblin threat"
        fake_queries.snippet_query = "unused snippet query"
        agent._query_formulator = MagicMock(return_value=fake_queries)
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()

        agent._build_scene_summary = AsyncMock(return_value="Dark corridor")
        agent._fetch_entities = AsyncMock(return_value=[{"id": "e1"}])
        agent._fetch_game_system = AsyncMock(return_value={"name": "Narrative Pure"})
        agent._fetch_runtime_profile = AsyncMock(return_value={"system_name": "Narrative Pure"})
        agent._search_memories = AsyncMock(return_value=[{"content": "mem"}])
        agent._fetch_recent_conversation_turns = AsyncMock(return_value=[])
        agent._search_snippets_for_entities = AsyncMock(return_value=[{"doc": "lore"}])
        agent._summarise_context = AsyncMock(return_value="Enemy close.")

        story_id = uuid4()
        result = await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=story_id,
            player_action="draw sword",
            detail_level="memory_only",
        )

        assert result == {
            "memories": [{"content": "mem"}],
            "source_profile": {"system_name": "Narrative Pure"},
            "source_scope": {
                "system_name": "Narrative Pure",
                "preferred_semantic_categories": ["general"],
                "preferred_terms": [],
            },
        }
        agent._search_memories.assert_awaited_once_with(
            "goblin threat",
            story_id=story_id,
            universe_id=None,
        )
        agent._fetch_entities.assert_not_called()
        agent._fetch_recent_conversation_turns.assert_not_called()
        agent._search_snippets_for_entities.assert_not_called()
        agent._summarise_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_only_dialogue_turn_enriches_memories_with_recent_conversation(self):
        """Dialogue turns should pull recent conversation snippets into memory_only context."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "ask about the gate"
        fake_queries.snippet_query = "unused"
        agent._query_formulator = MagicMock(return_value=fake_queries)
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._build_scene_summary = AsyncMock(return_value="City gatehouse")
        agent._fetch_entities = AsyncMock(return_value=[])
        agent._fetch_game_system = AsyncMock(return_value={"name": "Narrative Pure"})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._search_memories = AsyncMock(return_value=[{"content": "existing memory"}])
        agent._fetch_recent_conversation_turns = AsyncMock(
            return_value=[
                {
                    "conversation_id": "c-1",
                    "turn_index": 1,
                    "speaker_role": "player",
                    "entity_name": "Player",
                    "text": "I ask for entry to the city.",
                    "timestamp": "2026-01-01T10:04:00+00:00",
                },
                {
                    "conversation_id": "c-1",
                    "turn_index": 2,
                    "speaker_role": "npc",
                    "entity_name": "Gate Captain",
                    "text": "State your purpose.",
                    "timestamp": "2026-01-01T10:05:00+00:00",
                },
            ]
        )
        agent._search_snippets_for_entities = AsyncMock(return_value=[])
        agent._summarise_context = AsyncMock(return_value="unused")

        result = await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action="I ask the captain for entry",
            detail_level="memory_only",
        )

        assert "memories" in result
        assert result["memories"][0]["source"] == "conversation_turn"
        assert any("Gate Captain" in item.get("content", "") for item in result["memories"])
        assert any(item.get("source") == "conversation_window" for item in result["memories"])
        assert any(item.get("content") == "existing memory" for item in result["memories"])
        assert "conversation_turns" in result
        assert "source_scope" in result
        agent._fetch_recent_conversation_turns.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_memory_only_dialogue_turn_appends_focus_terms_to_memory_query(self):
        """Memory-only dialogue retrieval should enrich memory query with dialogue focus terms."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "ask about gate"
        fake_queries.snippet_query = "unused"
        agent._query_formulator = MagicMock(return_value=fake_queries)
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._build_scene_summary = AsyncMock(return_value="City gatehouse")
        agent._fetch_entities = AsyncMock(return_value=[])
        agent._fetch_game_system = AsyncMock(return_value={"name": "Narrative Pure"})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._fetch_recent_conversation_turns = AsyncMock(
            return_value=[
                {
                    "conversation_id": "c-1",
                    "turn_index": 1,
                    "speaker_role": "npc",
                    "entity_name": "Gate Captain",
                    "text": "State your purpose.",
                    "timestamp": "2026-01-01T10:05:00+00:00",
                },
                {
                    "conversation_id": "c-1",
                    "turn_index": 2,
                    "speaker_role": "player",
                    "entity_name": "Player",
                    "text": "I ask for entry.",
                    "timestamp": "2026-01-01T10:06:00+00:00",
                },
            ]
        )
        agent._search_memories = AsyncMock(return_value=[])
        agent._search_snippets_for_entities = AsyncMock(return_value=[])
        agent._summarise_context = AsyncMock(return_value="unused")

        with patch(
            "monitor_agents.context_assembly.agent.compose_dialogue_focus_terms",
            return_value=["Gate Captain", "entry"],
        ):
            await agent.retrieve_turn_context(
                scene_id=uuid4(),
                story_id=uuid4(),
                player_action="I ask for entry",
                detail_level="memory_only",
            )

        enriched_query = agent._search_memories.await_args.args[0]
        assert "Gate Captain" in enriched_query
        assert "entry" in enriched_query

    @pytest.mark.asyncio
    async def test_profile_aliases_expand_turn_queries_and_summary_context(self):
        """Profile lexicon/aliases should expand retrieval queries and reach the summary step."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "embrace politics"
        fake_queries.snippet_query = "ask the prince about the embrace"
        agent._query_formulator = MagicMock(return_value=fake_queries)

        agent._build_scene_summary = AsyncMock(return_value="Elysium audience")
        agent._fetch_entities = AsyncMock(return_value=[{"name": "Prince Marcel"}])
        agent._fetch_game_system = AsyncMock(return_value={"name": "V20"})
        agent._fetch_runtime_profile = AsyncMock(
            return_value={
                "system_name": "V20",
                "term_lexicon": {"Embrace": ["Siring"], "Kindred": ["Cainites"]},
                "taxonomy_containers": ["Clan"],
                "canon_signal_terms": ["Prince"],
                "confidence_by_field": {
                    "system_name": 0.97,
                    "term_lexicon": 0.94,
                    "taxonomy_containers": 0.91,
                    "canon_signal_terms": 0.88,
                },
            }
        )
        agent._search_memories = AsyncMock(return_value=[])
        agent._fetch_recent_conversation_turns = AsyncMock(return_value=[])
        agent._search_snippets_for_entities = AsyncMock(return_value=[])
        agent._summarise_context = AsyncMock(return_value="Courtly tension hangs in the hall.")

        await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action="I ask the prince about the embrace",
        )

        memory_query = agent._search_memories.call_args[0][0]
        snippet_query = agent._search_snippets_for_entities.call_args[0][0]
        summary_kwargs = agent._summarise_context.call_args[1]

        assert "Siring" in memory_query
        assert "Prince" in snippet_query
        assert "System: V20" in summary_kwargs["profile_context"]

    @pytest.mark.asyncio
    async def test_full_dialogue_turn_context_enriches_memories_and_surfaces_turns(self):
        """Full retrieval should include dialogue turn context for conversational actions."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "ask about the archives"
        fake_queries.snippet_query = "archives access"
        agent._query_formulator = MagicMock(return_value=fake_queries)
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._build_scene_summary = AsyncMock(return_value="Archive vestibule")
        agent._fetch_entities = AsyncMock(return_value=[{"id": "e1", "name": "Archivist"}])
        agent._fetch_game_system = AsyncMock(return_value={"name": "Narrative Pure"})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._search_memories = AsyncMock(return_value=[{"content": "baseline memory"}])
        agent._fetch_recent_conversation_turns = AsyncMock(
            return_value=[
                {
                    "conversation_id": "c-1",
                    "turn_index": 2,
                    "speaker_role": "player",
                    "entity_name": "Player",
                    "text": "I ask whether the archives can be opened.",
                    "timestamp": "2026-01-01T10:05:00+00:00",
                },
                {
                    "conversation_id": "c-1",
                    "turn_index": 3,
                    "speaker_role": "npc",
                    "entity_name": "Archivist",
                    "text": "Only those with the seal may enter.",
                    "timestamp": "2026-01-01T10:06:00+00:00",
                },
            ]
        )
        agent._collect_traversal_candidates = AsyncMock(return_value=[])
        agent._search_snippets_for_entities = AsyncMock(return_value=[{"doc": "snippet"}])
        agent._summarise_context = AsyncMock(return_value="summary")

        result = await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action="I ask the archivist about access",
            detail_level="full",
        )

        assert result["memories"][0]["source"] == "conversation_turn"
        assert any("Archivist" in item.get("content", "") for item in result["memories"])
        assert any(item.get("source") == "conversation_window" for item in result["memories"])
        assert any(item.get("content") == "baseline memory" for item in result["memories"])
        assert "conversation_turns" in result
        snippet_query_used = agent._search_snippets_for_entities.await_args.args[0]
        assert "Archivist" in snippet_query_used

    @pytest.mark.asyncio
    async def test_source_scope_is_exposed_for_turn_retrieval(self):
        """Turn retrieval should return source_scope metadata for Phase 3 routing visibility."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "check faction politics"
        fake_queries.snippet_query = "ask the prince for aid"
        agent._query_formulator = MagicMock(return_value=fake_queries)

        profile = {
            "system_name": "V20",
            "taxonomy_containers": ["Clan"],
            "canon_signal_terms": ["Prince"],
        }
        agent._build_scene_summary = AsyncMock(return_value="Elysium audience")
        agent._fetch_entities = AsyncMock(return_value=[])
        agent._fetch_game_system = AsyncMock(return_value={"name": "V20"})
        agent._fetch_runtime_profile = AsyncMock(return_value=profile)
        agent._search_memories = AsyncMock(return_value=[])
        agent._fetch_recent_conversation_turns = AsyncMock(return_value=[])
        agent._search_snippets_for_entities = AsyncMock(return_value=[])
        agent._summarise_context = AsyncMock(return_value="summary")
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()

        result = await agent.retrieve_turn_context(
            scene_id=uuid4(),
            story_id=uuid4(),
            player_action="I ask the prince for aid",
        )

        assert result["source_scope"]["system_name"] == "V20"
        assert "social_moral" in result["source_scope"]["preferred_semantic_categories"]
        assert "Prince" in result["source_scope"]["preferred_terms"]

    @pytest.mark.asyncio
    async def test_full_dialogue_turn_context_appends_window_terms_to_snippet_query(self):
        """Composed dialogue focus terms should be injected into snippet retrieval queries."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "ask about entry"
        fake_queries.snippet_query = "gatehouse"
        agent._query_formulator = MagicMock(return_value=fake_queries)
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._build_scene_summary = AsyncMock(return_value="Gatehouse")
        agent._fetch_entities = AsyncMock(return_value=[{"id": "e1", "name": "Gate Captain"}])
        agent._fetch_game_system = AsyncMock(return_value={"name": "Narrative Pure"})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._search_memories = AsyncMock(return_value=[])
        agent._fetch_recent_conversation_turns = AsyncMock(
            return_value=[
                {
                    "conversation_id": "c-1",
                    "turn_index": 1,
                    "speaker_role": "player",
                    "entity_name": "Player",
                    "text": "I ask for entry.",
                    "timestamp": "2026-01-01T10:00:00+00:00",
                },
                {
                    "conversation_id": "c-1",
                    "turn_index": 2,
                    "speaker_role": "npc",
                    "entity_name": "Gate Captain",
                    "text": "State your purpose and present papers.",
                    "timestamp": "2026-01-01T10:01:00+00:00",
                },
            ]
        )
        agent._collect_traversal_candidates = AsyncMock(return_value=[])
        agent._search_snippets_for_entities = AsyncMock(return_value=[])
        agent._summarise_context = AsyncMock(return_value="summary")

        with patch(
            "monitor_agents.context_assembly.agent.compose_dialogue_focus_terms",
            return_value=["window_signal_term", "window_signal_term", "captain_term"],
        ):
            await agent.retrieve_turn_context(
                scene_id=uuid4(),
                story_id=uuid4(),
                player_action="I ask the guard for entry",
                detail_level="full",
            )

        snippet_query_used = agent._search_snippets_for_entities.await_args.args[0]
        assert "window_signal_term" in snippet_query_used
        assert "captain_term" in snippet_query_used

    @pytest.mark.asyncio
    async def test_full_dialogue_turn_context_caps_snippet_query_length_budget(self):
        """Snippet query enrichment should respect max query-length budget."""
        agent = ContextAssembly.__new__(ContextAssembly)

        fake_queries = MagicMock()
        fake_queries.memory_query = "ask about archives"
        fake_queries.snippet_query = "base"
        agent._query_formulator = MagicMock(return_value=fake_queries)
        agent._cache_key = MagicMock(return_value="solo_play:turn_context:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._build_scene_summary = AsyncMock(return_value="Archive vestibule")
        agent._fetch_entities = AsyncMock(return_value=[{"id": "e1", "name": "Archivist"}])
        agent._fetch_game_system = AsyncMock(return_value={"name": "Narrative Pure"})
        agent._fetch_runtime_profile = AsyncMock(return_value={})
        agent._search_memories = AsyncMock(return_value=[])
        agent._fetch_recent_conversation_turns = AsyncMock(
            return_value=[
                {
                    "conversation_id": "c-1",
                    "turn_index": 1,
                    "speaker_role": "npc",
                    "entity_name": "Archivist",
                    "text": "Only sealed writs are accepted.",
                    "timestamp": "2026-01-01T10:01:00+00:00",
                },
                {
                    "conversation_id": "c-1",
                    "turn_index": 2,
                    "speaker_role": "player",
                    "entity_name": "Player",
                    "text": "I ask about entry requirements.",
                    "timestamp": "2026-01-01T10:02:00+00:00",
                },
            ]
        )
        agent._collect_traversal_candidates = AsyncMock(return_value=[{"counterpart_name": "LongName"}])
        agent._search_snippets_for_entities = AsyncMock(return_value=[])
        agent._summarise_context = AsyncMock(return_value="summary")

        very_long_terms = [f"term_{index}_{'x' * 24}" for index in range(50)]
        with (
            patch(
                "monitor_agents.context_assembly.agent.compose_dialogue_focus_terms",
                return_value=very_long_terms,
            ),
            patch(
                "monitor_agents.context_assembly.agent.collect_traversal_query_terms",
                return_value=very_long_terms,
            ),
        ):
            await agent.retrieve_turn_context(
                scene_id=uuid4(),
                story_id=uuid4(),
                player_action="I ask the archivist for access",
                detail_level="full",
            )

        snippet_query_used = agent._search_snippets_for_entities.await_args.args[0]
        assert len(snippet_query_used) <= 320


class TestProfileAwareSnippetRanking:
    @pytest.mark.asyncio
    async def test_search_snippets_for_entities_prioritizes_profile_relevant_alias_hits(self):
        """Profile-relevant snippet hits should outrank generic higher-score noise."""
        agent = ContextAssembly.__new__(ContextAssembly)
        agent._cache_key = MagicMock(return_value="solo_play:entity_snippets:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._ttl = MagicMock(return_value=60)
        agent.call_tool = AsyncMock(
            side_effect=[
                json.dumps([]),
                json.dumps(
                    [
                        {
                            "chunk_id": "noise",
                            "text": "A damp tunnel map with rusted piping.",
                            "score": 0.92,
                        },
                        {
                            "chunk_id": "relevant",
                            "text": "The siring rite binds childe and sire in Kindred society.",
                            "score": 0.55,
                        },
                    ]
                ),
            ]
        )

        _stub_retriever = MagicMock()
        _stub_retriever.embed_query = AsyncMock(return_value=[0.25, 0.5])
        with patch(
            "monitor_data.retrieval.default_retrieval_service",
            return_value=_stub_retriever,
        ):
            snippets = await agent._search_snippets_for_entities(
                "ask about the embrace",
                ["Prince Marcel"],
                source_profile={
                    "term_lexicon": {"Embrace": ["Siring"], "Kindred": ["Cainites"]},
                    "canon_signal_terms": ["Prince"],
                    "taxonomy_containers": ["Clan"],
                },
                player_action="I ask about the embrace",
            )

        assert snippets[0]["chunk_id"] == "relevant"


class TestTraversalCollection:
    @pytest.mark.asyncio
    async def test_collect_traversal_candidates_includes_ranked_path_results(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(
            side_effect=[
                [
                    {
                        "seed_entity_id": "e1",
                        "seed_name": "Captain Ilya",
                        "target_entity_id": "e9",
                        "target_name": "Archivist",
                        "rel_chain": ["KNOWS", "LOCATED_IN"],
                        "hop_count": 2,
                    }
                ],
                [],
                {"name": "Archivist"},
            ]
        )

        candidates = await agent._collect_traversal_candidates(
            entities=[{"id": "e1", "name": "Captain Ilya"}],
            traversal_mask={
                "preferred_rel_types": ["KNOWS"],
                "seed_entity_ids": ["e1"],
                "hop_limit": 2,
            },
        )

        assert candidates
        assert candidates[0]["source"] == "ranked_path"
        assert candidates[0]["counterpart_entity_id"] == "e9"
        assert candidates[0]["rel_type"] == "KNOWS"
        assert candidates[0]["hop_count"] == 2

    @pytest.mark.asyncio
    async def test_collect_traversal_candidates_filters_and_scores_relationships(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(
            side_effect=[
                [],
                [
                    {
                        "from_entity_id": "e1",
                        "to_entity_id": "e2",
                        "rel_type": "KNOWS",
                        "properties": {"strength": 3},
                        "counterpart_entity_id": "e2",
                        "counterpart_name": "Prince Marcel",
                    },
                    {
                        "from_entity_id": "e1",
                        "to_entity_id": "e3",
                        "rel_type": "RELATED_TO",
                        "properties": {},
                        "counterpart_entity_id": "e3",
                        "counterpart_name": "The Seneschal",
                    },
                ],
                {"name": "Prince Marcel"},
                {"name": "The Seneschal"},
            ]
        )

        candidates = await agent._collect_traversal_candidates(
            entities=[{"id": "e1", "name": "Captain Ilya"}],
            traversal_mask={
                "preferred_rel_types": ["KNOWS"],
                "seed_entity_ids": ["e1"],
            },
        )

        assert len(candidates) == 2
        assert candidates[0]["rel_type"] == "KNOWS"
        assert candidates[0]["counterpart_name"] == "Prince Marcel"
        assert all(candidate.get("source") == "neighborhood" for candidate in candidates)
        first_call_name = agent.call_tool.await_args_list[0].args[0]
        assert first_call_name == "neo4j_find_ranked_paths"

    @pytest.mark.asyncio
    async def test_collect_traversal_candidates_falls_back_to_list_relationships(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(
            side_effect=[
                [],
                RuntimeError("tool unavailable"),
                {
                    "relationships": [
                        {
                            "from_entity_id": "e1",
                            "to_entity_id": "e2",
                            "rel_type": "KNOWS",
                            "properties": {"strength": 3},
                        },
                        {
                            "from_entity_id": "e1",
                            "to_entity_id": "e3",
                            "rel_type": "RELATED_TO",
                            "properties": {},
                        },
                    ]
                },
                {"name": "Prince Marcel"},
                {"name": "The Seneschal"},
            ]
        )

        candidates = await agent._collect_traversal_candidates(
            entities=[{"id": "e1", "name": "Captain Ilya"}],
            traversal_mask={
                "preferred_rel_types": ["KNOWS"],
                "seed_entity_ids": ["e1"],
            },
        )

        assert len(candidates) == 2
        assert candidates[0]["rel_type"] == "KNOWS"
        assert candidates[0]["counterpart_name"] == "Prince Marcel"

    @pytest.mark.asyncio
    async def test_collect_traversal_candidates_dedupes_path_and_neighborhood_duplicates(self):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent.call_tool = AsyncMock(
            side_effect=[
                [
                    {
                        "seed_entity_id": "e1",
                        "seed_name": "Captain Ilya",
                        "target_entity_id": "e2",
                        "target_name": "Prince Marcel",
                        "rel_chain": ["KNOWS"],
                        "hop_count": 1,
                    }
                ],
                [
                    {
                        "from_entity_id": "e1",
                        "to_entity_id": "e2",
                        "rel_type": "KNOWS",
                        "properties": {"strength": 3},
                        "counterpart_entity_id": "e2",
                        "counterpart_name": "Prince Marcel",
                    }
                ],
                {"name": "Prince Marcel"},
            ]
        )

        candidates = await agent._collect_traversal_candidates(
            entities=[{"id": "e1", "name": "Captain Ilya"}],
            traversal_mask={
                "preferred_rel_types": ["KNOWS"],
                "seed_entity_ids": ["e1"],
                "hop_limit": 2,
            },
        )

        assert len(candidates) == 1
        assert candidates[0]["counterpart_entity_id"] == "e2"
        assert candidates[0]["rel_type"] == "KNOWS"

    @pytest.mark.asyncio
    async def test_search_snippets_for_entities_reuses_shared_query_vector(self):
        """Entity-filtered snippet retrieval should embed once and reuse that vector everywhere."""
        agent = ContextAssembly.__new__(ContextAssembly)
        agent._cache_key = MagicMock(return_value="solo_play:entity_snippets:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._ttl = MagicMock(return_value=60)
        agent.call_tool = AsyncMock(
            side_effect=[
                json.dumps([]),
                json.dumps([]),
                json.dumps([]),
            ]
        )

        shared_vector = [0.1, 0.2, 0.3]
        stub_retriever = MagicMock()
        stub_retriever.embed_query = AsyncMock(return_value=shared_vector)
        with patch(
            "monitor_data.retrieval.default_retrieval_service",
            return_value=stub_retriever,
        ):
            await agent._search_snippets_for_entities(
                "ask about the embrace",
                ["Prince Marcel", "Seneschal"],
                player_action="I ask about the embrace",
            )

        stub_retriever.embed_query.assert_awaited_once_with("ask about the embrace")
        assert len(agent.call_tool.await_args_list) == 3
        for call in agent.call_tool.await_args_list:
            tool_name, params = call.args
            assert tool_name == "qdrant_search"
            assert params["query_vector"] == shared_vector
            assert "query_text" not in params


class TestRuntimeProfileFallback:
    @pytest.mark.asyncio
    async def test_fetch_runtime_profile_falls_back_to_source_mindscape(self, monkeypatch):
        agent = ContextAssembly.__new__(ContextAssembly)
        agent._cache_key = MagicMock(return_value="solo_play:runtime_profile:test")
        agent._cache_get_json = MagicMock(return_value=None)
        agent._cache_set_json = MagicMock()
        agent._ttl = MagicMock(return_value=60)

        pack = SimpleNamespace(
            system_name="Death in Space",
            tags=["osr"],
            source_profile_data=None,
            source_mindscape=SimpleNamespace(
                system_name="Death in Space",
                themes=["cosmic horror", "resource scarcity"],
                taxonomy_hints=["Void", "Omens"],
                summary="A decaying-galaxy survival game about desperate scavengers.",
            ),
        )

        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_list_knowledge_packs",
            lambda _filter: SimpleNamespace(packs=[pack]),
        )

        result = await agent._fetch_runtime_profile(system_name="Death in Space")

        assert result["system_name"] == "Death in Space"
        assert "Void" in result["taxonomy_containers"]
        assert "cosmic horror" in result["genre_tone"]


# ===========================================================================
# G3: check_and_compress_if_needed
# ===========================================================================


class TestCheckAndCompressIfNeeded:
    @pytest.mark.asyncio
    async def test_returns_context_unchanged_when_within_budget(self):
        """When assembled context is within the token budget, return unchanged."""
        agent = ContextAssembly()
        small_context = {
            "entities": [],
            "memories": [{"text": "short memory"}],
            "snippets": [],
            "source_profile": "",
        }
        result = await agent.check_and_compress_if_needed(small_context, player_action="I look around")
        assert result.get("_compressed") is None
        assert result["memories"] == [{"text": "short memory"}]

    @pytest.mark.asyncio
    async def test_truncates_when_over_budget(self):
        """When assembled context exceeds token budget, memories are summarised."""
        agent = ContextAssembly()
        # Force the budget check to report zero available tokens
        agent._token_budget = MagicMock()
        agent._token_budget.available_for_context.return_value = -1
        # Mock _summarise_context to avoid needing a real TokenBudget
        agent._summarise_context = AsyncMock(return_value="Summarised: dragon memory")

        large_context = {
            "entities": [],
            "memories": [{"text": "memory of the dragon"}] * 5,
            "snippets": [],
            "source_profile": "",
        }
        result = await agent.check_and_compress_if_needed(large_context, player_action="I attack the dragon")
        # Result should have _compressed=True and a single summarised memory
        assert result.get("_compressed") is True
        assert len(result["memories"]) == 1
        assert "is_summary" in result["memories"][0]

    @pytest.mark.asyncio
    async def test_returns_unchanged_when_no_memories(self):
        """When context is over budget but has no memories, return unchanged."""
        agent = ContextAssembly()
        # Force the budget check to report zero available tokens
        agent._token_budget = MagicMock()
        agent._token_budget.available_for_context.return_value = -1

        large_context = {
            "entities": [{"id": "e1", "name": "foo"}],
            "memories": [],
            "snippets": [],
            "source_profile": "",
        }
        result = await agent.check_and_compress_if_needed(large_context, player_action="I look around")
        assert result.get("_compressed") is None
        assert result["memories"] == []
