"""Tests for monitor_agents.lorebook_directives."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from monitor_agents.lorebook_directives import (
    LorebookDirective,
    apply_lorebook_directives,
    parse_output_directives,
)


class TestParseOutputDirectives:
    def test_no_directives_passthrough(self):
        text = 'She nods slowly. "We leave at dawn."'
        cleaned, directives = parse_output_directives(text)
        assert cleaned == text
        assert directives == []

    def test_empty_text(self):
        assert parse_output_directives("") == ("", [])

    def test_strips_directive_lines(self):
        text = 'The innkeeper pales.\n@@activate the_red_hand\n"We were never here."'
        cleaned, directives = parse_output_directives(text)
        assert cleaned == 'The innkeeper pales.\n"We were never here."'
        assert directives == [LorebookDirective(verb="activate", entry_name="the_red_hand")]

    def test_multiple_directives_and_verbs(self):
        text = "@@activate First Entry\nProse here.\n@@Deactivate second entry\n"
        cleaned, directives = parse_output_directives(text)
        assert cleaned == "Prose here."
        assert [d.verb for d in directives] == ["activate", "deactivate"]
        assert directives[1].entry_name == "second entry"

    def test_directive_must_start_line(self):
        text = "She said @@activate foo mid-sentence."
        cleaned, directives = parse_output_directives(text)
        assert directives == []
        assert cleaned == text

    def test_blank_collapse(self):
        text = "Before.\n\n@@activate x\n\nAfter."
        cleaned, _ = parse_output_directives(text)
        assert cleaned == "Before.\n\nAfter."


class _FakeAgent:
    """call_tool double that serves entries and fails on any write."""

    def __init__(self, entries_by_character: dict[str, list[dict]]):
        self._entries = entries_by_character
        self.queries: list[dict] = []

    async def call_tool(self, name: str, args: dict):
        if name == "mongodb_get_lorebook_entries":
            self.queries.append(args)
            return list(self._entries.get(args["character_id"], []))
        raise AssertionError(f"unexpected tool call: {name}")


class TestApplyLorebookDirectives:
    """Directives switch entries for one conversation only; nothing is written."""

    def test_activates_matching_entry_case_insensitive(self):
        agent = _FakeAgent({"char-1": [{"id": "e1", "comment": "The Red Hand"}]})
        overrides = asyncio.run(
            apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("activate", "the red hand")], {})
        )
        assert overrides == {"e1": True}

    def test_lookup_includes_inactive_entries(self):
        agent = _FakeAgent({"char-1": [{"id": "e1", "comment": "x", "is_active": False}]})
        asyncio.run(apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("activate", "x")], {}))
        assert agent.queries[0]["include_inactive"] is True

    def test_deactivate_sets_false_and_keeps_earlier_overrides(self):
        agent = _FakeAgent({"char-1": [{"id": "e1", "comment": "x"}]})
        overrides = asyncio.run(
            apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("deactivate", "x")], {"e9": True})
        )
        assert overrides == {"e9": True, "e1": False}

    def test_input_overrides_are_not_mutated(self):
        agent = _FakeAgent({"char-1": [{"id": "e1", "comment": "x"}]})
        before = {"e9": True}
        asyncio.run(apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("activate", "x")], before))
        assert before == {"e9": True}

    def test_unknown_name_skipped(self):
        agent = _FakeAgent({"char-1": [{"id": "e1", "comment": "x"}]})
        overrides = asyncio.run(
            apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("activate", "ghost")], {})
        )
        assert overrides == {}

    def test_searches_all_characters(self):
        agent = _FakeAgent(
            {
                "char-1": [{"id": "e1", "comment": "a"}],
                "universe:u1": [{"id": "e2", "comment": "b"}],
            }
        )
        overrides = asyncio.run(
            apply_lorebook_directives(agent, ["char-1", "universe:u1"], [LorebookDirective("activate", "b")], {})
        )
        assert overrides == {"e2": True}

    def test_tool_failure_is_swallowed(self):
        agent = _FakeAgent({})
        agent.call_tool = AsyncMock(side_effect=RuntimeError("db down"))
        overrides = asyncio.run(
            apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("activate", "x")], {"e9": True})
        )
        assert overrides == {"e9": True}


class TestConversationLoopWiring:
    """generate_npc_responses strips directives and applies them per turn."""

    def test_direct_turn_strips_and_applies(self):
        from monitor_agents.loops import conversation_loop as cl

        state = cl.ConversationState(
            conversation_id=__import__("uuid").uuid4(),
            universe_id=__import__("uuid").uuid4(),
            mode=cl.ConversationMode.DIRECT,
            npc_ids=[__import__("uuid").uuid4()],
            current_player_input="Hello.",
            lorebook_character_ids=["char-1"],
            npc_contexts={},
        )
        npc_id = str(state.npc_ids[0])
        state.npc_contexts = {npc_id: {"name": "Maeve"}}

        reply_text = '"Fine."\n@@activate the_red_hand'
        fake_voice = AsyncMock()
        fake_voice.call_tool = AsyncMock(side_effect=RuntimeError("no scan"))
        fake_voice.respond_direct = AsyncMock(
            return_value={
                "npc_response": reply_text,
                "emotional_state_after": "calm",
                "proposals": [],
            }
        )

        with pytest.MonkeyPatch.context() as mp:
            import monitor_agents.npc_voice.agent as npc_agent_mod

            mp.setattr(npc_agent_mod, "NPCVoice", lambda: fake_voice)
            applied: list[list[LorebookDirective]] = []

            async def fake_apply(agent, cids, directives, overrides):
                applied.append(directives)
                return {**overrides, "e1": True}

            mp.setattr("monitor_agents.lorebook_directives.apply_lorebook_directives", fake_apply)
            out = asyncio.run(cl.generate_npc_responses(state))

        responses = out["current_npc_responses"]
        assert responses[0]["text"] == '"Fine."'
        assert out["turns"][-1]["text"] == '"Fine."'
        assert applied == [[LorebookDirective("activate", "the_red_hand")]]
        assert out["lorebook_overrides"] == {"e1": True}


def test_voice_strips_directives_before_saving_the_turn():
    """The reply is saved and remembered without the directive lines."""
    import types
    from uuid import uuid4

    from monitor_agents.npc_voice import agent as npc_agent_mod

    saved: list[str] = []
    voice = npc_agent_mod.NPCVoice.__new__(npc_agent_mod.NPCVoice)
    voice._direct_module = lambda **_kw: types.SimpleNamespace(
        npc_response='"Fine."\n@@activate The Red Hand',
        emotional_state_after="calm",
        relationship_delta="none",
    )

    async def call_tool(name, args):
        if name == "mongodb_append_conversation_turn":
            saved.append(args["params"]["text"])
        if name == "mongodb_create_memory":
            saved.append(args["params"]["text"])
        if name == "qdrant_search_memories":
            return {"results": []}
        return {}

    voice.call_tool = call_tool
    npc = {"name": "Maeve", "role": "innkeeper", "profile": {}, "facts": []}
    result = asyncio.run(
        voice.respond_direct(
            conversation_id=uuid4(),
            npc_id=uuid4(),
            player_said="Hello.",
            npc_data=npc,
            universe_id=uuid4(),
            parse_directives=True,
        )
    )

    assert result["npc_response"] == '"Fine."'
    assert result["lorebook_directives"] == [LorebookDirective("activate", "The Red Hand")]
    assert saved and all("@@" not in text for text in saved)


def test_scan_respects_conversation_overrides():
    from monitor_data.schemas.lorebook import LorebookEntry
    from monitor_data.tools.mongodb_tools import lorebook_tools

    def entry(entry_id: str, active: bool) -> LorebookEntry:
        return LorebookEntry(
            id=entry_id,
            character_id="char-1",
            keywords=["storm"],
            content=f"content {entry_id}",
            is_active=active,
            created_at="2026-01-01T00:00:00Z",
        )

    calls: list[dict] = []

    def fake_entries(character_id, include_inactive=False, **_kw):
        calls.append({"include_inactive": include_inactive})
        entries = [entry("off", False), entry("on", True)]
        return entries if include_inactive else [e for e in entries if e.is_active]

    with __import__("unittest.mock").mock.patch.object(lorebook_tools, "mongodb_get_lorebook_entries", fake_entries):
        plain = lorebook_tools.mongodb_scan_lorebook(["char-1"], "a storm", increment_triggers=False)
        flipped = lorebook_tools.mongodb_scan_lorebook(
            ["char-1"], "a storm", increment_triggers=False, active_overrides={"off": True, "on": False}
        )

    assert sorted(plain.triggered_entry_ids) == ["on"]
    assert sorted(flipped.triggered_entry_ids) == ["off"]
