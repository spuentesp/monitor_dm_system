"""Tests for GmTableAgent — Phase 7 Part B (prep, table lookups, session log).

Every test asserts the cross-component wiring: the MCP data fetch is invoked
with the expected arguments, and the typed LLM call is invoked with the
expected response model and grounded prompt content (no canned prose is
asserted). Failures are left to propagate — nothing here silently degrades.

Run:
    uv run pytest packages/agents/tests/test_gm_table.py -q -p no:cacheprovider
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from monitor_agents.gm_table import (
    AdvanceOutcome,
    ComplicationSuggestions,
    GmTableAgent,
    KnownFact,
    NameSuggestions,
    OffScreenSummary,
    PartyKnowledgeAnswer,
    PrepExtraction,
    PrepLocationItem,
    PrepNpcItem,
    PrepThreadItem,
    RulesAnswer,
    SessionLogExtraction,
    SessionLogStatement,
    _parse_tool_result,
    light_table_agent,
)
from monitor_data.schemas.llm_config import ModelRole
from monitor_data.schemas.world_clock import (
    ClockAdvanceRecord,
    WorldClockAdvanceResult,
    WorldClockDeadlineView,
    WorldClockResponse,
)


def _agent_with_mcp(responses: dict[str, object]) -> tuple[GmTableAgent, AsyncMock]:
    """GmTableAgent whose MCP calls are an AsyncMock keyed on tool name."""
    agent = GmTableAgent(agent_id="test-gm-table")
    call_tool = AsyncMock(side_effect=lambda name, args: responses[name])
    agent.call_tool = call_tool  # type: ignore[assignment]
    return agent, call_tool


class TestToolResultParsing:
    def test_bare_list_result(self):
        assert _parse_tool_result([{"id": "1"}], "facts", []) == [{"id": "1"}]

    def test_dict_result_with_key(self):
        assert _parse_tool_result({"entities": [{"name": "Mira"}]}, "entities", []) == [{"name": "Mira"}]

    def test_json_string_result(self):
        assert _parse_tool_result('{"facts": [1]}', "facts", []) == [1]

    def test_unexpected_shape_returns_default(self):
        assert _parse_tool_result(None, "facts", []) == []


class TestTier:
    def test_default_agent_is_standard(self):
        assert GmTableAgent()._default_model_role() == ModelRole.STANDARD

    def test_light_factory_is_light(self):
        assert light_table_agent()._default_model_role() == ModelRole.LIGHT


class TestExtractPrep:
    @pytest.mark.asyncio
    async def test_fetches_names_grounds_extraction_and_resolves_entities(self):
        universe_id = uuid4()
        agent, call_tool = _agent_with_mcp(
            {
                "neo4j_list_entities": {"entities": [{"name": "Mira"}, {"name": "Ironwatch"}]},
                "neo4j_get_entities_by_names": [{"name": "Mira", "id": "entity-1"}],
            }
        )
        extraction = PrepExtraction(
            npcs=[PrepNpcItem(name="Mira", want="the key back")],
            locations=[PrepLocationItem(name="Ironwatch")],
            threads=[PrepThreadItem(title="The sealed door")],
            notes_summary="A return to Ironwatch.",
        )
        llm = AsyncMock(return_value=extraction)
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.extract_prep(universe_id, "Mira wants the key back in Ironwatch")

        # MCP wiring: canon names fetched first, extracted names resolved after.
        call_tool.assert_any_await(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "limit": 100}},
        )
        call_tool.assert_any_await(
            "neo4j_get_entities_by_names",
            {"universe_id": str(universe_id), "names": ["Mira", "Ironwatch"]},
        )
        # LLM wiring: typed model + grounded prompt.
        llm.assert_awaited_once()
        assert llm.call_args.args[0] is PrepExtraction
        prompt = llm.call_args.args[1][1]["content"]
        assert "Mira" in prompt and "Ironwatch" in prompt
        assert "Mira wants the key back" in prompt

        # Result mapping: name resolution filled existing_entity_id.
        assert result.npcs[0].existing_entity_id == "entity-1"
        assert result.locations[0].existing_entity_id is None

    @pytest.mark.asyncio
    async def test_empty_notes_still_grounds_and_skips_resolution_when_no_items(self):
        universe_id = uuid4()
        agent, call_tool = _agent_with_mcp({"neo4j_list_entities": {"entities": []}})
        llm = AsyncMock(return_value=PrepExtraction())
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.extract_prep(universe_id, "nothing at all")

        assert result.npcs == []
        # No extracted names → no name-resolution tool call.
        assert call_tool.await_count == 1


class TestPartyKnowledge:
    @pytest.mark.asyncio
    async def test_witness_filter_and_topic_selection(self):
        universe_id = uuid4()
        me = uuid4()
        someone_else = uuid4()
        facts = [
            {"statement": "the key is with Mira", "witnesses": [str(me)]},
            {"statement": "the docks burned", "witnesses": []},
            {"statement": "the guild master is a vampire", "witnesses": [str(someone_else)]},
        ]
        agent, call_tool = _agent_with_mcp(
            {
                "neo4j_get_entities_by_names": [{"name": "Mira", "id": "entity-1"}],
                "neo4j_list_facts": facts,
            }
        )
        llm = AsyncMock(
            return_value=PartyKnowledgeAnswer(
                topic="Mira",
                summary="They know Mira has the key.",
                facts=[KnownFact(statement="", index=1)],
            )
        )
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.party_knowledge(universe_id, [me], topic="Mira")

        # MCP wiring: topic resolved to an entity, then its facts fetched.
        call_tool.assert_any_await(
            "neo4j_get_entities_by_names",
            {"universe_id": str(universe_id), "names": ["Mira"]},
        )
        call_tool.assert_any_await(
            "neo4j_list_facts",
            {"filters": {"universe_id": str(universe_id), "entity_id": "entity-1", "limit": 50}},
        )
        # LLM wiring: only witnessed/common candidates reach the model.
        prompt = llm.call_args.args[1][1]["content"]
        assert "the key is with Mira" in prompt
        assert "the docks burned" in prompt
        assert "the guild master is a vampire" not in prompt
        # Re-grounding: index 1 maps back to the first known statement.
        assert result.facts == [KnownFact(statement="the key is with Mira", index=1)]
        assert result.summary == "They know Mira has the key."

    @pytest.mark.asyncio
    async def test_no_topic_returns_known_facts_without_llm(self):
        universe_id = uuid4()
        me = uuid4()
        agent, _call_tool = _agent_with_mcp(
            {
                "neo4j_list_facts": [
                    {"statement": "the key is with Mira", "witnesses": [str(me)]},
                    {"statement": "secret", "witnesses": [str(uuid4())]},
                ],
            }
        )
        llm = AsyncMock()
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.party_knowledge(universe_id, [me], topic=None)

        llm.assert_not_awaited()
        assert [f.statement for f in result.facts] == ["the key is with Mira"]

    @pytest.mark.asyncio
    async def test_unresolved_topic_falls_back_to_universe_facts(self):
        universe_id = uuid4()
        agent, call_tool = _agent_with_mcp(
            {
                "neo4j_get_entities_by_names": [],
                "neo4j_list_facts": [{"statement": "the docks burned", "witnesses": []}],
            }
        )
        llm = AsyncMock(return_value=PartyKnowledgeAnswer(summary="The docks burned."))
        agent.call_llm_structured = llm  # type: ignore[assignment]

        await agent.party_knowledge(universe_id, [], topic="the docks")

        call_tool.assert_any_await(
            "neo4j_list_facts",
            {"filters": {"universe_id": str(universe_id), "limit": 100}},
        )


class TestAnswerRules:
    @pytest.mark.asyncio
    async def test_rules_text_flows_into_prompt_and_answer_carries_source(self):
        system_id = uuid4()
        agent, call_tool = _agent_with_mcp(
            {
                "mongodb_get_game_system": {
                    "name": "Iron Watch d6",
                    "core_mechanic": {"formula": "2d6 + skill", "description": "Roll over the target."},
                    "rules": [{"name": "Grappling", "description": "Roll Might.", "rule_type": "combat"}],
                    "attributes": [],
                }
            }
        )
        llm = AsyncMock(return_value=RulesAnswer(answer="Roll Might.", source="Grappling", covered=True))
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.answer_rules(system_id, "How does grappling work?")

        call_tool.assert_awaited_once_with("mongodb_get_game_system", {"system_id": str(system_id)})
        prompt = llm.call_args.args[1][1]["content"]
        assert "2d6 + skill" in prompt
        assert "Grappling" in prompt
        assert "How does grappling work?" in prompt
        assert result.source == "Grappling"

    @pytest.mark.asyncio
    async def test_missing_system_short_circuits_without_llm(self):
        agent, _call_tool = _agent_with_mcp({"mongodb_get_game_system": None})
        llm = AsyncMock()
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.answer_rules(uuid4(), "Anything?")

        llm.assert_not_awaited()
        assert result.covered is False


class TestImprovise:
    @pytest.mark.asyncio
    async def test_suggest_names_is_grounded_on_existing_names(self):
        universe_id = uuid4()
        agent, call_tool = _agent_with_mcp({"neo4j_list_entities": {"entities": [{"name": "Mira"}]}})
        llm = AsyncMock(return_value=NameSuggestions(names=["Tovin"], rationale="fits the setting"))
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.suggest_names(universe_id, "a dock warden", count=1)

        call_tool.assert_awaited_once_with(
            "neo4j_list_entities", {"filters": {"universe_id": str(universe_id), "limit": 50}}
        )
        prompt = llm.call_args.args[1][1]["content"]
        assert "Mira" in prompt and "dock warden" in prompt and "Suggest 1 names" in prompt
        assert result.names == ["Tovin"]

    @pytest.mark.asyncio
    async def test_suggest_complications_is_grounded_on_open_threads(self):
        universe_id = uuid4()
        story_id = uuid4()
        agent, call_tool = _agent_with_mcp({"neo4j_list_plot_threads": {"threads": [{"title": "The sealed door"}]}})
        llm = AsyncMock(
            return_value=ComplicationSuggestions(complications=["The door opens."], rationale="presses the thread")
        )
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.suggest_complications(universe_id, "the party is stalling", count=1, story_id=story_id)

        call_tool.assert_awaited_once_with(
            "neo4j_list_plot_threads",
            {"params": {"status": "active", "story_id": str(story_id)}},
        )
        prompt = llm.call_args.args[1][1]["content"]
        assert "The sealed door" in prompt
        assert result.complications == ["The door opens."]


class TestExtractSessionLog:
    @pytest.mark.asyncio
    async def test_extracts_statements_with_canon_names_in_prompt(self):
        universe_id = uuid4()
        agent, call_tool = _agent_with_mcp({"neo4j_list_entities": {"entities": [{"name": "Mira"}]}})
        llm = AsyncMock(
            return_value=SessionLogExtraction(
                statements=[
                    SessionLogStatement(
                        statement="the key is now with Mira",
                        participants=["Mira"],
                        locations=["Ironwatch"],
                    )
                ]
            )
        )
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.extract_session_log(universe_id, "Mira took back the key at the market")

        call_tool.assert_awaited_once_with(
            "neo4j_list_entities", {"filters": {"universe_id": str(universe_id), "limit": 100}}
        )
        prompt = llm.call_args.args[1][1]["content"]
        assert "Mira" in prompt
        assert "Mira took back the key" in prompt
        assert result.statements[0].statement == "the key is now with Mira"


class TestFailurePropagation:
    @pytest.mark.asyncio
    async def test_llm_failure_propagates(self):
        """No silent degradation: an LLM failure reaches the router as an error."""
        agent, _call_tool = _agent_with_mcp({"neo4j_list_entities": {"entities": []}})
        agent.call_llm_structured = AsyncMock(side_effect=RuntimeError("provider down"))  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="provider down"):
            await agent.extract_prep(uuid4(), "notes")


# ---------------------------------------------------------------------------
# World clock (CF-11)
# ---------------------------------------------------------------------------


def _deadline(title: str, due_at: datetime, status: str) -> WorldClockDeadlineView:
    return WorldClockDeadlineView(
        id=title.lower().replace(" ", "-"),
        title=title,
        due_at=due_at,
        status=status,  # type: ignore[arg-type]
    )


def _advance_payload(
    universe_id,
    story_id,
    *,
    changed: bool = True,
    initialized: bool = False,
    deadlines: list[WorldClockDeadlineView] | None = None,
    crossed: list[WorldClockDeadlineView] | None = None,
    advances: list[ClockAdvanceRecord] | None = None,
    current_at: datetime = datetime(1012, 3, 4, 9, 0, tzinfo=UTC),
) -> dict:
    """A JSON-shaped ``mongodb_advance_world_clock`` result, as MCP returns it."""
    clock = WorldClockResponse(
        universe_id=universe_id,
        story_id=story_id,
        current_at=current_at,
        display=current_at.isoformat(),
        deadlines=deadlines or [],
        advances=advances or [],
        updated_at=current_at,
    )
    return WorldClockAdvanceResult(
        clock=clock,
        changed=changed,
        initialized=initialized,
        crossed=crossed or [],
    ).model_dump(mode="json")


class TestAdvanceAndSummarize:
    @pytest.mark.asyncio
    async def test_advances_fetches_canon_and_grounds_the_offscreen_llm_call(self):
        universe_id = uuid4()
        story_id = uuid4()
        due = _deadline("The ransom is due", datetime(1012, 3, 4, tzinfo=UTC), "due")
        overdue = _deadline("The old promise", datetime(1012, 2, 20, tzinfo=UTC), "overdue")
        upcoming = _deadline("Midsummer festival", datetime(1012, 6, 1, tzinfo=UTC), "upcoming")
        payload = _advance_payload(
            universe_id,
            story_id,
            deadlines=[due, overdue, upcoming],
            crossed=[due],
            advances=[
                ClockAdvanceRecord(
                    from_at=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
                    to_at=datetime(1012, 3, 4, 9, 0, tzinfo=UTC),
                    delta="+3 days",
                    advanced_at=datetime(2026, 11, 10, tzinfo=UTC),
                )
            ],
        )
        agent, call_tool = _agent_with_mcp(
            {
                "mongodb_advance_world_clock": payload,
                "neo4j_list_entities": {"entities": [{"name": "Mira"}]},
                "neo4j_list_facts": [{"statement": "Mira owes the guild a debt"}],
            }
        )
        llm = AsyncMock(
            return_value=OffScreenSummary(
                summary="Three days passed; the guild grew impatient with Mira.",
                npc_activities=["Mira met the guild's collectors at the dock"],
            )
        )
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.advance_and_summarize(universe_id, story_id, delta="+3 days")

        # The advance is the single deterministic clock call, flat kwargs.
        call_tool.assert_any_await(
            "mongodb_advance_world_clock",
            {
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "delta": "+3 days",
                "target_time": None,
            },
        )
        # Canon grounding fetched over MCP before the LLM call.
        call_tool.assert_any_await(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "limit": 100}},
        )
        call_tool.assert_any_await(
            "neo4j_list_facts",
            {"filters": {"universe_id": str(universe_id), "limit": 30}},
        )
        # One typed LLM call; prompt carries elapsed time, deadlines and canon.
        llm.assert_awaited_once()
        assert llm.call_args.args[0] is OffScreenSummary
        prompt = llm.call_args.args[1][1]["content"]
        assert "+3 days" in prompt
        assert "The ransom is due" in prompt
        assert "The old promise" in prompt
        # Upcoming deadlines are not part of the briefing content.
        assert "Midsummer festival" not in prompt
        assert "Mira" in prompt
        assert "Mira owes the guild a debt" in prompt

        # Deterministic outcome: due set excludes upcoming, crossed preserved.
        assert isinstance(result, AdvanceOutcome)
        assert result.changed is True
        assert result.initialized is False
        assert [d.title for d in result.due] == ["The ransom is due", "The old promise"]
        assert [d.title for d in result.crossed] == ["The ransom is due"]
        assert result.offscreen is not None
        assert result.offscreen.npc_activities == ["Mira met the guild's collectors at the dock"]

    @pytest.mark.asyncio
    async def test_idempotent_noop_skips_the_llm_and_extra_fetches(self):
        universe_id = uuid4()
        story_id = uuid4()
        payload = _advance_payload(
            universe_id,
            story_id,
            changed=False,
            deadlines=[_deadline("Soon", datetime(1012, 3, 4, tzinfo=UTC), "due")],
        )
        agent, call_tool = _agent_with_mcp({"mongodb_advance_world_clock": payload})
        llm = AsyncMock(return_value=OffScreenSummary())
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.advance_and_summarize(
            universe_id,
            story_id,
            target_time=datetime(1012, 3, 4, 9, 0, tzinfo=UTC),
        )

        # Absolute target serialized for the wire; nothing else was called.
        call_tool.assert_awaited_once_with(
            "mongodb_advance_world_clock",
            {
                "universe_id": str(universe_id),
                "story_id": str(story_id),
                "delta": None,
                "target_time": "1012-03-04T09:00:00+00:00",
            },
        )
        llm.assert_not_awaited()
        assert result.changed is False
        assert result.offscreen is None
        # The deterministic due set still comes back for the briefing.
        assert [d.title for d in result.due] == ["Soon"]

    @pytest.mark.asyncio
    async def test_first_set_initializes_without_llm(self):
        universe_id = uuid4()
        story_id = uuid4()
        payload = _advance_payload(universe_id, story_id, initialized=True, advances=[])
        agent, call_tool = _agent_with_mcp({"mongodb_advance_world_clock": payload})
        llm = AsyncMock(return_value=OffScreenSummary())
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.advance_and_summarize(
            universe_id,
            story_id,
            target_time=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
        )

        call_tool.assert_awaited_once()
        llm.assert_not_awaited()
        assert result.initialized is True
        assert result.changed is True
        assert result.offscreen is None

    @pytest.mark.asyncio
    async def test_tool_errors_surface_as_value_error_for_422s(self):
        universe_id = uuid4()
        agent, _call_tool = _agent_with_mcp(
            {"mongodb_advance_world_clock": "Error executing tool: No world clock yet for this story"},
        )
        llm = AsyncMock()
        agent.call_llm_structured = llm  # type: ignore[assignment]

        with pytest.raises(ValueError, match="No world clock"):
            await agent.advance_and_summarize(universe_id, uuid4(), delta="+3 days")
        llm.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_canon_to_ground_falls_back_without_an_llm_call(self):
        universe_id = uuid4()
        story_id = uuid4()
        payload = _advance_payload(
            universe_id,
            story_id,
            advances=[
                ClockAdvanceRecord(
                    from_at=datetime(1012, 3, 1, 9, 0, tzinfo=UTC),
                    to_at=datetime(1012, 3, 4, 9, 0, tzinfo=UTC),
                    delta="+3 days",
                    advanced_at=datetime(2026, 11, 10, tzinfo=UTC),
                )
            ],
        )
        agent, _call_tool = _agent_with_mcp(
            {
                "mongodb_advance_world_clock": payload,
                "neo4j_list_entities": {"entities": []},
                "neo4j_list_facts": [],
            }
        )
        llm = AsyncMock()
        agent.call_llm_structured = llm  # type: ignore[assignment]

        result = await agent.advance_and_summarize(universe_id, story_id, delta="+3 days")

        llm.assert_not_awaited()
        assert result.changed is True
        assert result.offscreen is not None
        assert result.offscreen.summary.startswith("Time passed (+3 days)")
        assert result.offscreen.npc_activities == []
