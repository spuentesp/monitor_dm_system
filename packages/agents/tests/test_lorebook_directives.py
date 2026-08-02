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
        text = "She nods slowly. \"We leave at dawn.\""
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
    """call_tool double that serves entries from a dict and records updates."""

    def __init__(self, entries_by_character: dict[str, list[dict]]):
        self._entries = entries_by_character
        self.updates: list[dict] = []

    async def call_tool(self, name: str, args: dict):
        if name == "mongodb_get_lorebook_entries":
            return list(self._entries.get(args["character_id"], []))
        if name == "mongodb_update_lorebook_entry":
            self.updates.append(args)
            return {}
        raise AssertionError(f"unexpected tool call: {name}")


class TestApplyLorebookDirectives:
    def test_activates_matching_entry_case_insensitive(self):
        agent = _FakeAgent(
            {"char-1": [{"id": "e1", "comment": "The Red Hand"}]}
        )
        applied = asyncio.run(
            apply_lorebook_directives(
                agent, ["char-1"], [LorebookDirective("activate", "the red hand")]
            )
        )
        assert applied == 1
        assert agent.updates == [
            {"entry_id": "e1", "updates": {"is_active": True}}
        ]

    def test_deactivate_sets_false(self):
        agent = _FakeAgent({"char-1": [{"id": "e1", "comment": "x"}]})
        applied = asyncio.run(
            apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("deactivate", "x")])
        )
        assert applied == 1
        assert agent.updates[0]["updates"] == {"is_active": False}

    def test_unknown_name_skipped(self):
        agent = _FakeAgent({"char-1": [{"id": "e1", "comment": "x"}]})
        applied = asyncio.run(
            apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("activate", "ghost")])
        )
        assert applied == 0
        assert agent.updates == []

    def test_searches_all_characters(self):
        agent = _FakeAgent(
            {
                "char-1": [{"id": "e1", "comment": "a"}],
                "universe:u1": [{"id": "e2", "comment": "b"}],
            }
        )
        applied = asyncio.run(
            apply_lorebook_directives(
                agent, ["char-1", "universe:u1"], [LorebookDirective("activate", "b")]
            )
        )
        assert applied == 1
        assert agent.updates[0]["entry_id"] == "e2"

    def test_tool_failure_is_swallowed(self):
        agent = _FakeAgent({})
        agent.call_tool = AsyncMock(side_effect=RuntimeError("db down"))
        applied = asyncio.run(
            apply_lorebook_directives(agent, ["char-1"], [LorebookDirective("activate", "x")])
        )
        assert applied == 0


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

            async def fake_apply(agent, cids, directives):
                applied.append(directives)
                return len(directives)

            mp.setattr(
                "monitor_agents.lorebook_directives.apply_lorebook_directives", fake_apply
            )
            out = asyncio.run(cl.generate_npc_responses(state))

        responses = out["current_npc_responses"]
        assert responses[0]["text"] == '"Fine."'
        assert out["turns"][-1]["text"] == '"Fine."'
        assert applied == [[LorebookDirective("activate", "the_red_hand")]]
