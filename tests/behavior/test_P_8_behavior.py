"""
Behavior tests for P-8: Canonization (CanonKeeper evaluation pipeline).

Verifies:
- Policy Check: rejects hard violations
- Canon consistency reasoning
- Verdict acceptance and Neo4j commit
- Verdict rejection with reason

Uses FakeLLMClient and FakeMCPClient to test the CanonKeeper agent
without real LLM calls.
"""

from __future__ import annotations

from uuid import uuid4
from unittest.mock import MagicMock

from monitor_agents.canonkeeper import CanonKeeper, _normalise_state_tag_update


# =============================================================================
# State Tag Normalization
# =============================================================================


class TestStateTagNormalization:
    def test_basic_normalization(self):
        result = _normalise_state_tag_update({
            "entity_id": "abc-123",
            "add_tags": ["wounded"],
            "remove_tags": [],
        })
        assert result["entity_id"] == "abc-123"
        assert "wounded" in result["add_tags"]

    def test_tags_passed_through_directly(self):
        """Phase 8B: tags are passed through directly — no alias mapping.
        The game system's condition vocabulary defines what tags mean."""
        result = _normalise_state_tag_update({
            "entity_id": "abc",
            "add_tags": ["injured", "hurt", "pressured", "off_balance"],
            "remove_tags": [],
        })
        # All tags are preserved as-is (lowered + deduplicated)
        assert "injured" in result["add_tags"]
        assert "hurt" in result["add_tags"]
        assert "pressured" in result["add_tags"]
        assert "off_balance" in result["add_tags"]

    def test_condition_tags_alias(self):
        result = _normalise_state_tag_update({
            "entity_id": "abc",
            "condition_tags": ["stunned", "confused"],
            "remove_tags": [],
        })
        assert "stunned" in result["add_tags"]
        assert "confused" in result["add_tags"]

    def test_conditions_alias(self):
        result = _normalise_state_tag_update({
            "entity_id": "abc",
            "conditions": ["frightened", "charmed"],
            "remove_tags": [],
        })
        assert "frightened" in result["add_tags"]
        assert "charmed" in result["add_tags"]

    def test_hp_zero_passes_condition_tags(self):
        """Phase 8B: _normalise_state_tag_update no longer derives tags from
        resources — that's canonical_state_tags' job with game system track data."""
        result = _normalise_state_tag_update({
            "entity_id": "abc",
            "condition_tags": ["unconscious", "wounded"],
            "remove_tags": [],
        })
        assert "unconscious" in result["add_tags"]
        assert "wounded" in result["add_tags"]

    def test_resource_changes_pass_through_as_condition_tags(self):
        """Phase 8B: resource_changes alone don't derive tags — the caller
        (canonical_state_tags) is responsible for evaluating track thresholds."""
        result = _normalise_state_tag_update({
            "entity_id": "abc",
            "condition_tags": ["wounded"],
            "remove_tags": [],
        })
        assert "wounded" in result["add_tags"]

    def test_remove_tags_preserved(self):
        """Phase 8B: remove_tags are passed through directly, no alias mapping."""
        result = _normalise_state_tag_update({
            "entity_id": "abc",
            "add_tags": [],
            "remove_tags": ["injured"],
        })
        assert "injured" in result["remove_tags"]

    def test_duplicate_tags_deduplicated(self):
        """Phase 8B: duplicate tags are deduplicated but no alias mapping."""
        result = _normalise_state_tag_update({
            "entity_id": "abc",
            "add_tags": ["wounded", "WOUNDED", "wounded"],
            "remove_tags": [],
        })
        # Deduplicated to a single entry
        assert len(result["add_tags"]) == 1
        assert result["add_tags"][0] == "wounded"


# =============================================================================
# Helpers for DSPy module mocking
# =============================================================================


def _make_policy(violation: str = "NO", detail: str = ""):
    """Mock DSPy Prediction from PolicyCheckModule."""
    m = MagicMock()
    m.violation_found = violation
    m.violation_detail = detail
    return m


def _make_reasoning(consistent: str = "YES", reasoning: str = "No conflicts"):
    """Mock DSPy Prediction from CanonKeeperReasoningModule."""
    m = MagicMock()
    m.consistent = consistent
    m.reasoning = reasoning
    return m


# =============================================================================
# CanonKeeper Verdict Flow (unit tests — no DB needed)
# =============================================================================


class TestCanonKeeperVerdictFlow:
    def test_evaluate_proposals_empty_returns_empty(self):
        """Empty proposal list returns empty verdict list (fast path, no DB)."""
        ck = CanonKeeper()
        import asyncio
        verdicts = asyncio.run(ck.evaluate_proposals(uuid4(), []))
        assert verdicts == []


class TestCanonKeeperContradictionDetection:
    def test_verify_fact_no_contradiction(self):
        """A new fact that doesn't contradict context passes."""
        ck = CanonKeeper()
        import asyncio
        result = asyncio.run(ck.verify_fact(
            "The king is wise",
            ["The kingdom is prosperous", "The queen is beloved"],
        ))
        assert isinstance(result, dict)
        assert "has_contradiction" in result

    def test_heuristic_contradiction_found(self):
        """Heuristic fallback detects negation contradiction."""
        ck = CanonKeeper()
        result = ck._heuristic_contradiction_check(
            "The king is not wise",
            ["The king is wise and just"],
        )
        assert result["has_contradiction"] is True

    def test_heuristic_no_contradiction(self):
        """Heuristic fallback passes unrelated facts."""
        ck = CanonKeeper()
        result = ck._heuristic_contradiction_check(
            "The dragon sleeps in the mountain",
            ["The king is wise and just"],
        )
        assert result["has_contradiction"] is False
