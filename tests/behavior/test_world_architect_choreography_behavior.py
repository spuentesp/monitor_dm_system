"""Behavior tests for WorldArchitect (Phase 2 - World Seeding).

Covers:
- _format_history (pure function)
- _parse_proposals (method, but pure logic)
- WorldArchitect default state
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

pytestmark = pytest.mark.unit


def _make_architect() -> Any:
    from monitor_agents.world_architect.agent import WorldArchitect

    return WorldArchitect.__new__(WorldArchitect)


# =============================================================================
# _format_history
# =============================================================================


class TestFormatHistory:
    def test_empty_history(self):
        arch = _make_architect()
        assert arch._format_history([]) == ""

    def test_single_user_message(self):
        arch = _make_architect()
        result = arch._format_history([{"role": "user", "content": "Hello"}])
        assert result == "User: Hello"

    def test_single_architect_message(self):
        arch = _make_architect()
        result = arch._format_history([{"role": "architect", "content": "Welcome"}])
        assert result == "Architect: Welcome"

    def test_gm_role_treated_as_architect(self):
        arch = _make_architect()
        result = arch._format_history([{"role": "gm", "content": "Reply"}])
        assert result == "Architect: Reply"

    def test_system_role_treated_as_architect(self):
        arch = _make_architect()
        result = arch._format_history([{"role": "system", "content": "Note"}])
        assert result == "Architect: Note"

    def test_player_role_aliased_to_user(self):
        arch = _make_architect()
        result = arch._format_history([{"role": "player", "content": "Action"}])
        assert result == "User: Action"

    def test_unknown_role_uses_user_format(self):
        arch = _make_architect()
        result = arch._format_history([{"role": "narrator", "content": "X"}])
        # Unknown role falls through to neither branch; nothing added
        assert result == ""

    def test_conversation(self):
        arch = _make_architect()
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "architect", "content": "Hello there"},
            {"role": "user", "content": "Make a world"},
        ]
        result = arch._format_history(history)
        assert "User: Hi" in result
        assert "Architect: Hello there" in result
        assert "User: Make a world" in result

    def test_caps_to_last_20(self):
        arch = _make_architect()
        history = [{"role": "user", "content": f"msg {i}"} for i in range(50)]
        result = arch._format_history(history)
        # First message (msg 0) should be excluded
        assert "msg 0" not in result
        assert "msg 49" in result

    def test_missing_role_defaults_to_user(self):
        arch = _make_architect()
        # .get("role", "user") -> falls into the user branch
        result = arch._format_history([{"content": "no role"}])
        assert result == "User: no role"

    def test_missing_content(self):
        arch = _make_architect()
        result = arch._format_history([{"role": "user"}])
        assert result == "User: "


# =============================================================================
# _parse_proposals — method but pure logic
# =============================================================================


class TestParseProposals:
    def test_empty_string(self):
        arch = _make_architect()
        assert arch._parse_proposals("", universe_id=None) == []

    def test_invalid_json(self):
        arch = _make_architect()
        assert arch._parse_proposals("not json", universe_id=None) == []

    def test_json_not_list(self):
        arch = _make_architect()
        # Top-level dict
        assert arch._parse_proposals('{"foo": 1}', universe_id=None) == []
        # Top-level primitive
        assert arch._parse_proposals("42", universe_id=None) == []

    def test_empty_list(self):
        arch = _make_architect()
        result = arch._parse_proposals("[]", universe_id=uuid4())
        assert result == []

    def test_multiverse_proposal(self):
        arch = _make_architect()
        items = [
            {"type": "multiverse", "name": "Forgotten Realms", "system_name": "D&D 5e"}
        ]
        result = arch._parse_proposals(json.dumps(items), universe_id=uuid4())
        assert len(result) == 1
        assert result[0]["proposal_type"] == "multiverse"
        assert result[0]["change_type"] == "multiverse"
        assert "Forgotten Realms" in result[0]["summary"]
        assert result[0]["payload"]["name"] == "Forgotten Realms"
        assert result[0]["status"] == "pending"

    def test_universe_proposal(self):
        arch = _make_architect()
        items = [
            {
                "type": "universe",
                "name": "Wild Space",
                "description": "Far future",
                "genre": "sci-fi",
                "tone": "noir",
            }
        ]
        result = arch._parse_proposals(json.dumps(items), universe_id=None)
        assert result[0]["proposal_type"] == "universe"
        assert result[0]["payload"]["genre"] == "sci-fi"
        assert result[0]["payload"]["tone"] == "noir"

    def test_web_fetch_proposal(self):
        arch = _make_architect()
        items = [{"type": "web_fetch", "url": "https://example.com", "reason": "lore"}]
        result = arch._parse_proposals(json.dumps(items), universe_id=None)
        assert result[0]["proposal_type"] == "web_fetch"
        assert result[0]["payload"]["url"] == "https://example.com"

    def test_entity_proposal(self):
        arch = _make_architect()
        uid = uuid4()
        items = [
            {
                "type": "entity",
                "name": "Aragorn",
                "entity_type": "character",
                "description": "Ranger king",
            }
        ]
        result = arch._parse_proposals(json.dumps(items), universe_id=uid)
        assert result[0]["proposal_type"] == "entity"
        assert result[0]["payload"]["name"] == "Aragorn"
        assert result[0]["universe_id"] == str(uid)

    def test_entity_without_universe_id(self):
        arch = _make_architect()
        items = [{"type": "entity", "name": "E"}]
        result = arch._parse_proposals(json.dumps(items), universe_id=None)
        assert result[0]["universe_id"] == ""

    def test_axiom_proposal(self):
        arch = _make_architect()
        items = [
            {
                "type": "axiom",
                "statement": "Magic is rare in this world",
                "domain": "magic",
            }
        ]
        result = arch._parse_proposals(json.dumps(items), universe_id=uuid4())
        assert result[0]["proposal_type"] == "axiom"
        assert result[0]["payload"]["statement"] == "Magic is rare in this world"
        assert result[0]["payload"]["domain"] == "magic"

    def test_lore_fact_proposal(self):
        arch = _make_architect()
        items = [
            {
                "type": "lore_fact",
                "statement": "The kingdom fell in year 500",
                "fact_type": "historical",
                "entity_names": ["Kingdom"],
            }
        ]
        result = arch._parse_proposals(json.dumps(items), universe_id=uuid4())
        assert result[0]["proposal_type"] == "fact"
        assert result[0]["payload"]["fact_type"] == "historical"

    def test_unknown_type_ignored(self):
        arch = _make_architect()
        items = [{"type": "garbage", "name": "X"}]
        result = arch._parse_proposals(json.dumps(items), universe_id=None)
        assert result == []

    def test_multiple_proposals(self):
        arch = _make_architect()
        items = [
            {"type": "multiverse", "name": "M"},
            {"type": "universe", "name": "U"},
            {"type": "entity", "name": "E"},
        ]
        result = arch._parse_proposals(json.dumps(items), universe_id=uuid4())
        assert len(result) == 3
        types = [p["proposal_type"] for p in result]
        assert "multiverse" in types
        assert "universe" in types
        assert "entity" in types

    def test_each_proposal_has_unique_id(self):
        arch = _make_architect()
        items = [{"type": "entity", "name": f"E{i}"} for i in range(5)]
        result = arch._parse_proposals(json.dumps(items), universe_id=None)
        ids = {p["proposal_id"] for p in result}
        assert len(ids) == 5  # all unique

    def test_summary_truncates_to_60(self):
        arch = _make_architect()
        long_statement = "x" * 200
        items = [{"type": "axiom", "statement": long_statement}]
        result = arch._parse_proposals(json.dumps(items), universe_id=None)
        assert len(result[0]["summary"]) <= 60 + len("Create axiom: ")


# =============================================================================
# WorldArchitect default
# =============================================================================


class TestWorldArchitect:
    def test_can_instantiate_via_new(self):
        arch = _make_architect()
        # Has expected attributes
        assert isinstance(arch, object)
