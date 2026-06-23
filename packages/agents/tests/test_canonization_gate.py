"""
Integration tests for the canonization gate — TEST-3.

Tests the full Scene finalize flow:
  pending proposals → CanonKeeper evaluation → Neo4j writes (accepted)
                                              → MongoDB audit trail

All external calls (LLM, MCP tools, DSPy) are mocked so tests run
without real API keys or running databases.

Run:
    cd packages/agents && pytest tests/test_canonization_gate.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.agent_responses import (
    CanonKeeperDecision,
    CanonKeeperVerdict,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proposal(
    change_type: str = "entity",
    summary: str = "A new character appears",
    universe_id: str | None = None,
    entity_names: List[str] | None = None,
) -> Dict[str, Any]:
    """Build a minimal proposal dict matching what scene_loop accumulates."""
    return {
        "proposal_id": str(uuid4()),
        "change_type": change_type,
        "summary": summary,
        "content": {
            "entity_type": "Character",
            "name": "Lyra Ashveil",
            "properties": {"race": "elf", "class": "ranger"},
        },
        "universe_id": universe_id or str(uuid4()),
        "entity_names": entity_names or ["Lyra Ashveil"],
    }


def _make_verdict(
    proposal_id: str,
    decision: CanonKeeperDecision = CanonKeeperDecision.ACCEPTED,
    canon_node_type: str = "Character",
) -> CanonKeeperVerdict:
    return CanonKeeperVerdict(
        proposal_id=proposal_id,
        decision=decision,
        reasoning=f"Test verdict: {decision.value}",
        canon_node_type=canon_node_type,
        canon_properties={"name": "Lyra Ashveil", "race": "elf"},
        decided_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_mongo():
    """Keep this file hermetic: CanonKeeper._commit_to_neo4j opens the
    proposed_changes collection (and the change-log audit hook writes to
    MongoDB), which would otherwise hit a real socket. Stub the client so the
    commit path runs against in-memory mocks.
    """
    fake_coll = MagicMock()
    fake_coll.find_one.return_value = None
    fake_client = MagicMock()
    fake_client.get_collection.return_value = fake_coll
    with patch(
        "monitor_data.db.mongodb.get_mongodb_client",
        return_value=fake_client,
    ):
        yield


@pytest.fixture
def mock_call_tool():
    """Patch BaseAgent.call_tool to succeed silently."""
    with patch(
        "monitor_agents.base.BaseAgent.call_tool",
        new_callable=AsyncMock,
        return_value=None,
    ) as m:
        yield m


@pytest.fixture
def mock_call_llm():
    """Patch BaseAgent.call_llm_structured."""
    with patch(
        "monitor_agents.base.BaseAgent.call_llm_structured",
        new_callable=AsyncMock,
    ) as m:
        yield m


@pytest.fixture
def passing_dspy():
    """Patch DSPy modules to produce a passing policy + accept reasoning."""
    policy_ok = MagicMock()
    policy_ok.violation_found = "NO"
    policy_ok.violation_detail = "none"

    reasoning_ok = MagicMock()
    reasoning_ok.reasoning = "No contradiction detected. ACCEPT."

    with (
        patch(
            "monitor_agents.prompts.canonkeeper.PolicyCheckModule.__call__",
            return_value=policy_ok,
        ),
        patch(
            "monitor_agents.prompts.canonkeeper.CanonKeeperReasoningModule.__call__",
            return_value=reasoning_ok,
        ),
    ):
        yield


# =============================================================================
# TEST-3: Canonization gate — unit tests
# =============================================================================


class TestCanonizationGate:
    """CanonKeeper.evaluate_proposals() behaviour."""

    @pytest.mark.asyncio
    async def test_accept_valid_proposal(self, mock_call_tool, mock_call_llm, passing_dspy):
        """Valid proposal: passes policy, gets reasoning, is accepted + committed."""
        from monitor_agents.canonkeeper import CanonKeeper

        proposal = _make_proposal()
        mock_call_llm.return_value = _make_verdict(
            proposal["proposal_id"], CanonKeeperDecision.ACCEPTED
        )

        ck = CanonKeeper()
        verdicts = await ck.evaluate_proposals(uuid4(), [proposal])

        assert len(verdicts) == 1
        assert verdicts[0].decision == CanonKeeperDecision.ACCEPTED

        committed = [c.args[0] for c in mock_call_tool.call_args_list]
        assert "neo4j_create_entity" in committed

    @pytest.mark.asyncio
    async def test_policy_gate_blocks_hard_violation(self, mock_call_tool, mock_call_llm):
        """Policy violation immediately rejects — LLM is never called."""
        violation = MagicMock()
        violation.violation_found = "YES"
        violation.violation_detail = "Protected entity deletion attempt"

        with patch(
            "monitor_agents.prompts.canonkeeper.PolicyCheckModule.__call__",
            return_value=violation,
        ):
            from monitor_agents.canonkeeper import CanonKeeper

            proposal = _make_proposal(summary="Delete the Omniversal library")
            verdicts = await CanonKeeper().evaluate_proposals(uuid4(), [proposal])

        assert verdicts[0].decision == CanonKeeperDecision.REJECTED
        assert "Policy violation" in verdicts[0].reasoning
        mock_call_llm.assert_not_called()

        committed = [c.args[0] for c in mock_call_tool.call_args_list]
        assert "neo4j_create_entity" not in committed
        assert "neo4j_create_fact" not in committed

    @pytest.mark.asyncio
    async def test_llm_reject_skips_neo4j_commit(self, mock_call_tool, mock_call_llm, passing_dspy):
        """LLM-issued REJECT verdict: audit recorded, no Neo4j write."""
        from monitor_agents.canonkeeper import CanonKeeper

        proposal = _make_proposal()
        mock_call_llm.return_value = _make_verdict(
            proposal["proposal_id"], CanonKeeperDecision.REJECTED
        )

        await CanonKeeper().evaluate_proposals(uuid4(), [proposal])

        committed = [c.args[0] for c in mock_call_tool.call_args_list]
        assert "neo4j_create_entity" not in committed
        assert "mongodb_record_verdict" in committed

    @pytest.mark.asyncio
    async def test_audit_recorded_for_every_verdict(
        self, mock_call_tool, mock_call_llm, passing_dspy
    ):
        """Both accepted and rejected verdicts are always written to MongoDB."""
        from monitor_agents.canonkeeper import CanonKeeper

        p1 = _make_proposal(summary="New NPC")
        p2 = _make_proposal(summary="Contradictory lore")
        mock_call_llm.side_effect = [
            _make_verdict(p1["proposal_id"], CanonKeeperDecision.ACCEPTED),
            _make_verdict(p2["proposal_id"], CanonKeeperDecision.REJECTED),
        ]

        await CanonKeeper().evaluate_proposals(uuid4(), [p1, p2])

        # mongodb_record_verdict must appear twice (one per proposal)
        audit_calls = [
            c for c in mock_call_tool.call_args_list if c.args[0] == "mongodb_record_verdict"
        ]
        assert len(audit_calls) == 2

    @pytest.mark.asyncio
    async def test_batch_mixed_verdicts_correct_commits(
        self, mock_call_tool, mock_call_llm, passing_dspy
    ):
        """Batch: accepted proposals committed, rejected ones skipped."""
        from monitor_agents.canonkeeper import CanonKeeper

        p_entity = _make_proposal(change_type="entity", summary="New character")
        p_reject = _make_proposal(change_type="entity", summary="Contradicts lore")
        p_fact = _make_proposal(change_type="fact", summary="New relationship")

        mock_call_llm.side_effect = [
            _make_verdict(p_entity["proposal_id"], CanonKeeperDecision.ACCEPTED, "Character"),
            _make_verdict(p_reject["proposal_id"], CanonKeeperDecision.REJECTED, "Character"),
            _make_verdict(p_fact["proposal_id"], CanonKeeperDecision.ACCEPTED, "fact"),
        ]

        verdicts = await CanonKeeper().evaluate_proposals(uuid4(), [p_entity, p_reject, p_fact])

        decisions = {str(v.proposal_id): v.decision for v in verdicts}
        assert decisions[p_entity["proposal_id"]] == CanonKeeperDecision.ACCEPTED
        assert decisions[p_reject["proposal_id"]] == CanonKeeperDecision.REJECTED
        assert decisions[p_fact["proposal_id"]] == CanonKeeperDecision.ACCEPTED

        neo4j_calls = {c.args[0] for c in mock_call_tool.call_args_list if "neo4j" in c.args[0]}
        assert "neo4j_create_entity" in neo4j_calls
        assert "neo4j_create_fact" in neo4j_calls

    @pytest.mark.asyncio
    async def test_empty_proposal_list_returns_empty(self, mock_call_tool):
        """Empty proposals → empty verdicts, no tool calls."""
        from monitor_agents.canonkeeper import CanonKeeper

        verdicts = await CanonKeeper().evaluate_proposals(uuid4(), [])

        assert verdicts == []
        mock_call_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_finalize_story_writes_completed_status(self, mock_call_tool):
        """finalize_story() calls neo4j_update_story_status with status=completed."""
        from monitor_agents.canonkeeper import CanonKeeper

        story_id = uuid4()
        await CanonKeeper().finalize_story(story_id)

        mock_call_tool.assert_called_once()
        tool_name = mock_call_tool.call_args.args[0]
        tool_args = mock_call_tool.call_args.args[1]

        assert tool_name == "neo4j_update_story_status"
        assert tool_args["story_id"] == str(story_id)
        assert tool_args["status"] == "completed"
        assert "completed_at" in tool_args


# =============================================================================
# Schema validation tests
# =============================================================================


class TestCanonKeeperVerdictSchema:
    """Pydantic model contracts for CanonKeeperVerdict."""

    def test_accept_verdict_round_trips(self):
        v = CanonKeeperVerdict(
            proposal_id=str(uuid4()),
            decision=CanonKeeperDecision.ACCEPTED,
            reasoning="Consistent with established lore.",
            canon_node_type="Character",
            canon_properties={"name": "Lyra", "race": "elf"},
            decided_at=datetime.now(timezone.utc),
        )
        assert (
            CanonKeeperVerdict.model_validate(v.model_dump()).decision
            == CanonKeeperDecision.ACCEPTED
        )

    @pytest.mark.asyncio
    async def test_reject_verdict_preserves_reasoning(self):
        v = CanonKeeperVerdict(
            proposal_id=str(uuid4()),
            decision=CanonKeeperDecision.REJECTED,
            reasoning="Lyra died in Arc 2 — cannot reintroduce.",
            canon_node_type="Character",
            canon_properties={},
            decided_at=datetime.now(timezone.utc),
        )
        assert "Arc 2" in v.reasoning

    def test_invalid_decision_value_raises(self):
        with pytest.raises(Exception):
            CanonKeeperVerdict(
                proposal_id=str(uuid4()),
                decision="MAYBE",
                reasoning="reason",
                canon_node_type="Entity",
                canon_properties={},
                decided_at=datetime.now(timezone.utc),
            )
