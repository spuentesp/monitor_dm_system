"""Tests for the deterministic state-transition rules (G-9 Phase 2).

Covers:
- ``check_state_transition``: terminal-tag finality, mutual exclusion, and the
  explicit override escape hatch
- ``CanonKeeper._check_state_transition_rules`` + ``_flag_proposal_for_review``:
  the agent wiring — which proposals are checked, how the flag is stamped, and
  that a failure never breaks evaluation
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.canonkeeper.transition_rules import (
    check_state_transition,
)


class TestCheckStateTransition:
    def test_plain_transition_is_allowed(self):
        assert (
            check_state_transition(
                current_tags=["alive", "neutral"],
                add_tags=["wounded"],
                remove_tags=["neutral"],
            )
            is None
        )

    def test_removing_a_terminal_tag_is_a_violation(self):
        violation = check_state_transition(
            current_tags=["dead"],
            add_tags=[],
            remove_tags=["dead"],
        )
        assert violation is not None
        assert violation.rule == "terminal_tag_removal"

    def test_adding_agency_to_a_terminal_entity_is_a_violation(self):
        violation = check_state_transition(
            current_tags=["dead"],
            add_tags=["alive"],
            remove_tags=[],
        )
        assert violation is not None
        assert violation.rule == "terminal_tag_agency"

    def test_override_reason_legalises_the_transition(self):
        assert (
            check_state_transition(
                current_tags=["dead"],
                add_tags=["alive"],
                remove_tags=["dead"],
                override_reason="The sire restored her with a blood rite.",
            )
            is None
        )

    def test_mutually_exclusive_tags_are_a_violation(self):
        violation = check_state_transition(
            current_tags=["neutral"],
            add_tags=["dead", "alive"],
            remove_tags=[],
        )
        assert violation is not None
        assert violation.rule == "mutual_exclusion"

    def test_mutual_exclusion_respects_removal(self):
        assert (
            check_state_transition(
                current_tags=["dead", "alive"],
                add_tags=[],
                remove_tags=["alive"],
            )
            is None
        )

    def test_tags_are_case_insensitive(self):
        violation = check_state_transition(
            current_tags=["DEAD"],
            add_tags=["Alive"],
            remove_tags=[],
        )
        assert violation is not None


def _state_change_proposal(**content) -> dict:
    return {
        "proposal_id": str(uuid4()),
        "change_type": "state_change",
        "content": content,
    }


class TestTransitionRuleWiring:
    @pytest.mark.asyncio
    async def test_non_state_change_proposals_are_skipped(self):
        keeper = CanonKeeper()
        keeper.call_tool = AsyncMock()

        result = await keeper._check_state_transition_rules(
            {"proposal_id": str(uuid4()), "change_type": "fact", "content": {}}
        )

        assert result is None
        keeper.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_state_change_without_tags_is_skipped(self):
        keeper = CanonKeeper()
        keeper.call_tool = AsyncMock()

        result = await keeper._check_state_transition_rules(_state_change_proposal())

        assert result is None
        keeper.call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_dead_entity_that_acts_is_flagged(self):
        keeper = CanonKeeper()
        keeper.call_tool = AsyncMock(return_value={"entity_id": "e-1", "state_tags": ["dead"]})

        result = await keeper._check_state_transition_rules(
            _state_change_proposal(entity_id="e-1", add_tags=["alive"], remove_tags=[])
        )

        assert result is not None
        assert result.rule == "terminal_tag_agency"

    @pytest.mark.asyncio
    async def test_tag_lookup_failure_yields_no_violation(self):
        keeper = CanonKeeper()
        keeper.call_tool = AsyncMock(side_effect=Exception("neo4j down"))

        result = await keeper._check_state_transition_rules(
            _state_change_proposal(entity_id="e-1", add_tags=["alive"], remove_tags=[])
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_flag_is_stamped_and_mirrored_onto_the_proposal(self):
        keeper = CanonKeeper()
        keeper.call_tool = AsyncMock(return_value={})
        proposal = _state_change_proposal(entity_id="e-1", add_tags=["alive"], remove_tags=[])

        from monitor_agents.canonkeeper.transition_rules import TransitionViolation

        await keeper._flag_proposal_for_review(
            proposal, TransitionViolation(rule="terminal_tag_agency", reason="because")
        )

        keeper.call_tool.assert_awaited_once()
        args = keeper.call_tool.await_args[0]
        assert args[0] == "mongodb_flag_proposal_review"
        assert args[1]["needs_review"] is True
        assert args[1]["reason"] == "because"
        assert args[1]["source"] == "transition_rule:terminal_tag_agency"
        # Mirrored onto the caller's dict so the verdict record can carry it.
        assert proposal["needs_review"] is True
        assert proposal["review_reason"] == "because"

    @pytest.mark.asyncio
    async def test_failed_flag_write_does_not_raise(self):
        keeper = CanonKeeper()
        keeper.call_tool = AsyncMock(side_effect=Exception("mongo down"))
        proposal = _state_change_proposal(entity_id="e-1", add_tags=["alive"], remove_tags=[])

        from monitor_agents.canonkeeper.transition_rules import TransitionViolation

        await keeper._flag_proposal_for_review(
            proposal, TransitionViolation(rule="terminal_tag_agency", reason="because")
        )

        assert "needs_review" not in proposal
