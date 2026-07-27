"""
Tests for CanonKeeper.verify_fact and _heuristic_contradiction_check.

Covers:
- verify_fact: LLM-driven contradiction detection with heuristic fallback
- _heuristic_contradiction_check: Simple negation-based detection

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_canonkeeper_verify_fact.py -v
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper

# ===========================================================================
# _heuristic_contradiction_check
# ===========================================================================


class TestHeuristicContradictionCheck:
    def setup_method(self):
        self.keeper = CanonKeeper(agent_id="test-verify")

    def test_no_context_returns_no_contradiction(self):
        result = self.keeper._heuristic_contradiction_check("The sky is blue", [])
        assert result["has_contradiction"] is False

    def test_negation_detected(self):
        result = self.keeper._heuristic_contradiction_check(
            "The king is not dead",
            ["The king is dead and buried"],
        )
        assert result["has_contradiction"] is True
        assert "king" in result["explanation"].lower() or "contradict" in result["explanation"].lower()

    def test_consistent_facts_no_contradiction(self):
        result = self.keeper._heuristic_contradiction_check(
            "The king is wise",
            ["The king rules with justice"],
        )
        assert result["has_contradiction"] is False

    def test_never_negation(self):
        result = self.keeper._heuristic_contradiction_check(
            "The dragon never sleeps",
            ["The dragon sleeps constantly"],
        )
        assert result["has_contradiction"] is True

    def test_doesnt_negation(self):
        result = self.keeper._heuristic_contradiction_check(
            "The sword doesn't glow",
            ["The sword glows brightly"],
        )
        assert result["has_contradiction"] is True


# ===========================================================================
# verify_fact (async, with mocked LLM)
# ===========================================================================


class TestVerifyFact:
    @pytest.mark.asyncio
    async def test_verify_fact_with_llm(self):
        """Test LLM-driven contradiction detection."""
        keeper = CanonKeeper(agent_id="test-verify")

        mock_result = {
            "has_contradiction": True,
            "explanation": "The king cannot be both alive and dead.",
        }

        with patch("monitor_agents.canonkeeper.verification.ContradictionModule") as mock_module_cls:
            mock_module = mock_module_cls.return_value
            mock_module.forward.return_value = mock_result

            result = await keeper.verify_fact(
                new_fact="The king is alive",
                context=["The king was killed in battle"],
            )

            assert result["has_contradiction"] is True
            assert "king" in result["explanation"].lower() or "contradict" in result["explanation"].lower()

    @pytest.mark.asyncio
    async def test_verify_fact_fallback_to_heuristic(self):
        """Test that heuristic fallback works when LLM fails."""
        keeper = CanonKeeper(agent_id="test-verify")

        with patch("monitor_agents.canonkeeper.verification.ContradictionModule") as mock_module_cls:
            mock_module = mock_module_cls.return_value
            mock_module.forward.side_effect = Exception("LLM unavailable")

            result = await keeper.verify_fact(
                new_fact="The king is not dead",
                context=["The king is dead"],
            )

            # Should fall back to heuristic
            assert result["has_contradiction"] is True

    @pytest.mark.asyncio
    async def test_verify_fact_no_contradiction(self):
        """Test when there's no contradiction."""
        keeper = CanonKeeper(agent_id="test-verify")

        mock_result = {"has_contradiction": False, "explanation": "The facts are consistent."}

        with patch("monitor_agents.canonkeeper.verification.ContradictionModule") as mock_module_cls:
            mock_module = mock_module_cls.return_value
            mock_module.forward.return_value = mock_result

            result = await keeper.verify_fact(
                new_fact="The castle has tall towers",
                context=["The castle overlooks the valley"],
            )

            assert result["has_contradiction"] is False
