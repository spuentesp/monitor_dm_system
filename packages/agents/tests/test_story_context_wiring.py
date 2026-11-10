"""
Tests for the campaign's continuity wiring: the ledger in the context, the
story state read from its checkpoint, and the ledger in the narrator's prompt.

A campaign that continues needs three things to hold: the story's arc comes
from the checkpoint (so a restart changes nothing), the ledger reaches the
model on every turn of a scene, and the facts the model sees are the ones
that still hold.

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_story_context_wiring.py -v
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest


class TestLedgerCompression:
    def test_the_last_entries_stay_in_full_and_the_older_ones_become_a_line(self):
        from monitor_agents.context_assembly.agent import compress_story_ledger

        entries = [
            {"scene_index": 1, "summary": "They took the ferry. The ferry sank. Everyone drowned."},
            {"scene_index": 2, "summary": "They walked along the drowned road."},
            {"scene_index": 3, "summary": "They found the sealed vault."},
            {"scene_index": 4, "summary": "They opened the vault and saw the drowned king."},
        ]

        block = compress_story_ledger(entries)

        assert len(block) == 4
        # The two newest entries are in full.
        assert block[-1]["summary"] == "They opened the vault and saw the drowned king."
        assert block[-2]["summary"] == "They found the sealed vault."
        # The older ones are one line each.
        assert block[0]["compressed"] is True
        assert block[0]["summary"] == "They took the ferry"
        assert block[1]["compressed"] is True
        assert block[1]["summary"] == "They walked along the drowned road."

    def test_the_block_stays_inside_its_budget(self):
        from monitor_agents.context_assembly.agent import compress_story_ledger
        from monitor_agents.token_budget import count_tokens

        entries = [{"scene_index": index, "summary": "A long scene summary. " * 80} for index in range(1, 12)]

        block = compress_story_ledger(entries, max_tokens=400)

        assert count_tokens(str(block)) <= 400
        # The newest entries survive: they are what just happened.
        assert block[-1]["scene_index"] == 11

    def test_a_story_without_a_ledger_has_no_block(self):
        from monitor_agents.context_assembly.agent import compress_story_ledger

        assert compress_story_ledger([]) == []


class TestContextAssemblyLedger:
    @pytest.mark.asyncio
    async def test_the_assembled_context_carries_the_ledger(self):
        from monitor_agents.context_assembly.agent import ContextAssembly

        agent = ContextAssembly()
        story_id = uuid4()

        with (
            patch.object(
                ContextAssembly,
                "_fetch_entities",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                ContextAssembly,
                "_fetch_recent_turns",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                ContextAssembly,
                "_fetch_game_system",
                AsyncMock(return_value={}),
            ),
            patch.object(
                ContextAssembly,
                "_fetch_plot_threads",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                ContextAssembly,
                "_fetch_story_ledger",
                AsyncMock(
                    return_value=[
                        {"scene_index": 1, "summary": "They took the ferry across the black water."},
                        {"scene_index": 2, "summary": "They found the sealed vault."},
                    ]
                ),
            ),
            patch.object(
                ContextAssembly,
                "_fetch_memories",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                ContextAssembly,
                "_fetch_knowledge",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                ContextAssembly,
                "_fetch_canon_facts",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                ContextAssembly,
                "_fetch_runtime_profile",
                AsyncMock(return_value={}),
            ),
        ):
            result = await agent.assemble(scene_id=uuid4(), story_id=story_id)

        assert [entry["scene_index"] for entry in result["story_ledger"]] == [1, 2]

    @pytest.mark.asyncio
    async def test_the_ledger_is_read_from_the_story(self):
        """The context assembly reads the ledger of the story it serves."""
        from monitor_agents.context_assembly.agent import ContextAssembly

        agent = ContextAssembly()
        story_id = uuid4()
        calls: list[dict] = []

        async def fake_call_tool(self, name, arguments):
            calls.append((name, arguments))
            return []

        with patch(
            "monitor_agents.context_assembly.agent.ContextAssembly.call_tool",
            new=fake_call_tool,
        ):
            entries = await agent._fetch_story_ledger(story_id)

        assert entries == []
        assert calls[0][0] == "mongodb_list_story_ledger_entries"
        assert calls[0][1]["story_id"] == str(story_id)


class TestTemporalFacts:
    def test_a_superseded_fact_is_dropped(self):
        from monitor_data.tools.temporal_tools import get_current_facts

        now = datetime(1012, 3, 1, 12, 0, tzinfo=UTC)
        old_id = str(uuid4())
        facts = [
            {
                "id": old_id,
                "statement": "The vault is in the drowned road.",
                "time_ref": now.isoformat(),
                "duration": None,
            },
            {
                "id": str(uuid4()),
                "statement": "The vault is under the chapel.",
                "time_ref": now.isoformat(),
                "duration": None,
                "replaces": old_id,
            },
        ]

        current = get_current_facts(facts, now)

        assert [fact["statement"] for fact in current] == ["The vault is under the chapel."]

    def test_the_facts_are_ordered_by_the_time_they_happened(self):
        from monitor_data.tools.temporal_tools import get_current_facts

        now = datetime(1012, 3, 1, 12, 0, tzinfo=UTC)
        facts = [
            {
                "id": str(uuid4()),
                "statement": "The tide went out.",
                "time_ref": datetime(1012, 3, 1, 11, 0, tzinfo=UTC).isoformat(),
                "duration": None,
            },
            {
                "id": str(uuid4()),
                "statement": "The ferry left.",
                "time_ref": datetime(1012, 3, 1, 9, 0, tzinfo=UTC).isoformat(),
                "duration": None,
            },
        ]

        current = get_current_facts(facts, now)

        assert [fact["statement"] for fact in current] == ["The ferry left.", "The tide went out."]

    def test_a_fact_that_is_not_valid_yet_is_not_current(self):
        from monitor_data.tools.temporal_tools import get_current_facts

        now = datetime(1012, 3, 1, 12, 0, tzinfo=UTC)
        facts = [
            {
                "id": str(uuid4()),
                "statement": "The king returns.",
                "time_ref": datetime(1012, 3, 2, 12, 0, tzinfo=UTC).isoformat(),
                "duration": None,
            }
        ]

        assert get_current_facts(facts, now) == []


class TestLoadContextContinuity:
    @pytest.mark.asyncio
    async def test_the_story_state_is_read_from_the_checkpoint(self):
        """The arc comes from the checkpoint, not from this process."""
        from monitor_agents.loops.scene_loop import SceneState, load_context
        from monitor_agents.loops.story_loop import StoryState

        checkpoint = StoryState(
            story_id=uuid4(),
            universe_id=uuid4(),
            arc_label="climax",
            tension_score=0.8,
            active_threads=["The drowned road"],
            ledger_entries=[{"scene_index": 1, "summary": "They took the ferry across the black water."}],
        )
        seen: list[dict] = []

        async def fake_load(state):
            seen.append({"story_id": str(state.story_id)})
            return checkpoint

        with (
            patch(
                "monitor_agents.loops.scene_loop._load_story_state",
                new=fake_load,
            ),
            patch(
                "monitor_agents.context_assembly.agent.ContextAssembly.assemble",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4())
            result = await load_context(state)

        assert seen == [{"story_id": str(state.story_id)}]
        assert result["story_state"].arc_label == "climax"
        assert result["story_state"].tension_score == 0.8

    @pytest.mark.asyncio
    async def test_the_ledger_reaches_the_established_facts(self):
        """The GM reads the campaign's history as facts — once.

        Join task 12: the ledger's one-liners travel on the GM's
        established-facts channel (``source_profile``); the Narrator reads
        the same history from the story state's CAMPAIGN LEDGER block
        instead, so the campaign's history is never injected twice.
        """
        from monitor_agents.loops.scene_loop import SceneState, load_context

        context = {
            "story_ledger": [
                {
                    "scene_index": 1,
                    "summary": "They took the ferry across the black water.",
                    "compressed": True,
                }
            ],
            "facts": [
                {"id": "f1", "statement": "The ferry sank with everyone aboard."},
            ],
        }

        with (
            patch(
                "monitor_agents.loops.scene_loop._load_story_state",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "monitor_agents.context_assembly.agent.ContextAssembly.assemble",
                new_callable=AsyncMock,
                return_value=context,
            ),
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4())
            result = await load_context(state)

        # The GM channel carries the ledger one-liner...
        assert "Scene 1: They took the ferry across the black water." in result["source_profile"]["established_facts"]
        assert "The ferry sank with everyone aboard." in result["established_facts"]
        # ...and the shared established facts (the Narrator's channel) do not
        # repeat it — the Narrator reads the ledger from the story state.
        assert "Scene 1: They took the ferry across the black water." not in result["established_facts"]

    @pytest.mark.asyncio
    async def test_a_canon_statement_is_not_repeated_on_later_turns(self):
        """The carried facts channel de-duplicates the canon re-fetch."""
        from monitor_agents.loops.scene_loop import SceneState, load_context

        context = {
            "story_ledger": [],
            "facts": [{"id": "f1", "statement": "The ferry sank with everyone aboard."}],
        }

        with (
            patch(
                "monitor_agents.loops.scene_loop._load_story_state",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "monitor_agents.context_assembly.agent.ContextAssembly.assemble",
                new_callable=AsyncMock,
                return_value=context,
            ),
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                established_facts=["The ferry sank with everyone aboard."],
            )
            result = await load_context(state)

        assert result["established_facts"].count("The ferry sank with everyone aboard.") == 1

    @pytest.mark.asyncio
    async def test_the_ledger_travels_on_the_story_state(self):
        """The Narrator reads the ledger from the story state it is given."""
        from monitor_agents.loops.scene_loop import SceneState, load_context
        from monitor_agents.loops.story_loop import StoryState

        context = {
            "story_ledger": [
                {"scene_index": 2, "summary": "They found the sealed vault."},
            ]
        }
        story_state = StoryState(story_id=uuid4(), universe_id=uuid4())

        with (
            patch(
                "monitor_agents.loops.scene_loop._load_story_state",
                new=AsyncMock(return_value=story_state),
            ),
            patch(
                "monitor_agents.context_assembly.agent.ContextAssembly.assemble",
                new_callable=AsyncMock,
                return_value=context,
            ),
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4())
            result = await load_context(state)

        assert [entry["scene_index"] for entry in result["story_state"].ledger_entries] == [2]


class TestNarratorLedger:
    def test_the_ledger_is_rendered_for_the_narrator(self):
        from monitor_agents.narrator.agent import _story_ledger_block

        block = _story_ledger_block(
            [
                {
                    "scene_index": 1,
                    "summary": "They took the ferry across the black water.",
                    "open_questions": ["Who paid the ferryman?"],
                }
            ]
        )

        assert "CAMPAIGN LEDGER" in block
        assert "They took the ferry across the black water." in block
        assert "Who paid the ferryman?" in block

    def test_a_story_without_a_ledger_renders_nothing(self):
        from monitor_agents.narrator.agent import _story_ledger_block

        assert _story_ledger_block([]) == ""
        assert _story_ledger_block(None) == ""

    def test_the_last_scene_recap_is_not_cut_to_120_characters(self):
        from monitor_agents.narrator.agent import _opening_recap_block

        recap = "They crossed the black water. " * 20
        block = _opening_recap_block(recap)

        assert recap.strip() in block


class TestCanonFactsInContext:
    @pytest.mark.asyncio
    async def test_the_canon_is_read_for_the_universe(self):
        """The facts come from the universe the scene is played in."""
        from monitor_agents.context_assembly.agent import ContextAssembly

        agent = ContextAssembly()
        calls: list[tuple[str, dict]] = []

        async def fake_call_tool(self, name, arguments):
            calls.append((name, arguments))
            return []

        with patch(
            "monitor_agents.context_assembly.agent.ContextAssembly.call_tool",
            new=fake_call_tool,
        ):
            facts = await agent._fetch_canon_facts(
                "11111111-1111-1111-1111-111111111111",
                check_time=datetime(1012, 3, 1, 12, 0, tzinfo=UTC),
            )

        assert facts == []
        name, arguments = calls[0]
        assert name == "neo4j_list_facts"
        assert arguments["filters"]["universe_id"] == "11111111-1111-1111-1111-111111111111"
        assert arguments["filters"]["status"] == "active"


class TestRecapLedger:
    @pytest.mark.asyncio
    async def test_the_recap_reads_the_storys_ledger(self, monkeypatch):
        """The story so far is built from the campaign's own memory."""
        from monitor_agents.recap.agent import RecapAgent

        seen: list[UUID] = []

        class _Entry:
            def model_dump(self, mode: str = "json") -> dict:
                return {
                    "scene_index": 1,
                    "summary": "They took the ferry across the black water.",
                    "start_time": "1012-03-01T09:00:00+00:00",
                    "end_time": "1012-03-01T11:00:00+00:00",
                    "open_questions": ["Who paid the ferryman?"],
                }

        def fake_list(story_id):
            seen.append(story_id)
            return [_Entry()]

        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.stories.mongodb_list_story_ledger_entries",
            fake_list,
        )

        agent = RecapAgent()
        entries = await agent._read_ledger(uuid4())

        assert len(seen) == 1
        assert entries[0]["summary"].startswith("They took the ferry")


class TestMemoryTimeRef:
    @pytest.mark.asyncio
    async def test_a_memory_records_when_it_happened(self, monkeypatch):
        """The memory carries the scene's in-world time."""
        from monitor_agents.services import persistence_service

        created: list[object] = []

        def fake_create_memory(params):
            created.append(params)
            return SimpleNamespace(memory_id=uuid4())

        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.mongodb_create_memory",
            fake_create_memory,
        )

        when = datetime(1012, 3, 1, 9, 30, tzinfo=UTC)
        await persistence_service.PersistenceService.persist_memories(
            entity_id=uuid4(),
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            memories=[{"text": "The vault door is sealed.", "time_ref": when}],
        )

        assert len(created) == 1
        assert created[0].metadata["time_ref"] == when.isoformat()
