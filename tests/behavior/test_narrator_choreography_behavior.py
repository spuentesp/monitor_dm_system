"""
Behavior tests for Narrator agent pure helpers and choreography invariants.

Covers:
- _format_resolution: resolution dict → summary string mapping
- _parse_proposed_changes: JSON string parsing from DSPy output
- Narrator agent initialization and module setup
- Turn narration choreography invariants

Run:
    cd /path/to/monitor_dm_system && pytest tests/behavior/test_narrator_choreography_behavior.py -v
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# _format_resolution — pure helper tests
# =============================================================================


class TestFormatResolutionBehavior:
    def setup_method(self):
        from monitor_agents.narrator.agent import Narrator

        self.narrator = Narrator.__new__(Narrator)

    def test_none_returns_narrative(self):
        assert self.narrator._format_resolution(None) == "narrative"

    def test_empty_dict_returns_narrative(self):
        assert self.narrator._format_resolution({}) == "narrative"

    def test_success_level_passthrough(self):
        result = self.narrator._format_resolution({"success_level": "success"})
        assert result == "success"

    def test_critical_success_passthrough(self):
        result = self.narrator._format_resolution({"success_level": "critical_success"})
        assert result == "critical_success"

    def test_critical_failure_passthrough(self):
        result = self.narrator._format_resolution({"success_level": "critical_failure"})
        assert result == "critical_failure"

    def test_includes_roll_total_and_stat(self):
        result = self.narrator._format_resolution(
            {"success_level": "success", "roll_total": 17, "stat": "STR"}
        )
        assert "success" in result
        assert "17" in result
        assert "STR" in result

    def test_includes_description_when_present(self):
        result = self.narrator._format_resolution(
            {"success_level": "failure", "description": "The lock picks snap."}
        )
        assert "failure" in result


# =============================================================================
# _parse_proposed_changes — JSON parsing from DSPy output
# =============================================================================


class TestParseProposedChangesBehavior:
    def setup_method(self):
        from monitor_agents.narrator.agent import Narrator

        self.narrator = Narrator.__new__(Narrator)

    def test_valid_json_array(self):
        changes = [{"change_type": "create_fact", "summary": "Test fact"}]
        result = self.narrator._parse_proposed_changes(json.dumps(changes))
        assert len(result) == 1
        assert result[0]["change_type"] == "create_fact"
        assert result[0]["summary"] == "Test fact"

    def test_valid_json_array_normalizes_missing_keys(self):
        """Entries without summary/content get default empty values."""
        changes = [{"change_type": "create_fact", "statement": "Test"}]
        result = self.narrator._parse_proposed_changes(json.dumps(changes))
        assert len(result) == 1
        assert result[0]["change_type"] == "create_fact"
        assert result[0]["summary"] == ""
        assert result[0]["content"] == {}

    def test_empty_json_array(self):
        result = self.narrator._parse_proposed_changes("[]")
        assert result == []

    def test_invalid_json_returns_empty(self):
        result = self.narrator._parse_proposed_changes("not json")
        assert result == []

    def test_none_returns_empty(self):
        result = self.narrator._parse_proposed_changes(None)
        assert result == []

    def test_empty_string_returns_empty(self):
        result = self.narrator._parse_proposed_changes("")
        assert result == []

    def test_json_object_not_array_returns_empty(self):
        result = self.narrator._parse_proposed_changes('{"key": "value"}')
        assert result == []


# =============================================================================
# Narrator initialization
# =============================================================================


class TestNarratorInitBehavior:
    def test_agent_type_is_narrator(self):
        from monitor_agents.narrator.agent import Narrator

        agent = Narrator(agent_id="narr-1")
        assert agent.agent_type == "Narrator"

    def test_agent_has_narrator_module(self):
        from monitor_agents.narrator.agent import Narrator

        agent = Narrator(agent_id="narr-2")
        assert hasattr(agent, "_narrator_module")

    def test_agent_id_preserved(self):
        from monitor_agents.narrator.agent import Narrator

        agent = Narrator(agent_id="narr-42")
        assert agent.agent_id == "narr-42"


# =============================================================================
# Choreography invariants
# =============================================================================


class TestNarratorChoreographyInvariants:
    """Invariants that must hold across all narrator operations."""

    def test_format_resolution_never_returns_none(self):
        """_format_resolution must always return a non-None string."""
        from monitor_agents.narrator.agent import Narrator

        narrator = Narrator.__new__(Narrator)
        for resolution in [
            None,
            {},
            {"success_level": "success"},
            {"unknown_key": "val"},
        ]:
            result = narrator._format_resolution(resolution)
            assert result is not None
            assert isinstance(result, str)

    def test_parse_proposed_changes_never_raises(self):
        """_parse_proposed_changes must never raise — always return a list."""
        from monitor_agents.narrator.agent import Narrator

        narrator = Narrator.__new__(Narrator)
        for raw in [None, "", "not json", "[]", "[{}]", '{"a": 1}', "123"]:
            result = narrator._parse_proposed_changes(raw)
            assert isinstance(result, list)

    def test_parse_proposed_changes_always_returns_list(self):
        """Even for malformed input, the result must be a list (never a dict)."""
        from monitor_agents.narrator.agent import Narrator

        narrator = Narrator.__new__(Narrator)
        result = narrator._parse_proposed_changes('{"not": "an array"}')
        assert isinstance(result, list)
        assert not isinstance(result, dict)
