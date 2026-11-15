"""
Basic workings — the Session Recorder's mid-session corrections (G03 / CF-1).

The recorder is where the GM's notes become canon candidates. G03 lets the
GM fix the record *at the table*: edit an entry, strike it, undo the strike.
The rule that makes this safe is that a correction carries its
consequences — striking an entry retracts the proposals it produced, and
the undo restores exactly those, not any proposal the GM rejected in CF-8
for an unrelated reason.

Use Cases: CF-1 (G03 amendment)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from monitor_agents.ingestion.capture_insights import CaptureInsightAgent
from monitor_agents.ingestion.session_ingest import SessionIngestAgent
from monitor_data.schemas.base import ProposalType
from monitor_data.schemas.proposed_changes import ProposedChangeCreate
from monitor_data.tools.mongodb_tools.proposals import (
    mongodb_create_proposed_change,
)
from tests.behavior._hermetic_stack import HermeticStack

STRIKE_REASON = "struck at the table"


@pytest.fixture
def entry_id() -> str:
    return str(uuid4())


@pytest.fixture
def scene_id(hermetic: HermeticStack) -> UUID:
    """A scene the capture proposals hang off."""
    scene = uuid4()
    hermetic.seed(
        "scenes",
        [
            {
                "scene_id": str(scene),
                "story_id": str(uuid4()),
                "universe_id": str(uuid4()),
                "title": "The sealed door",
                "purpose": "Advance the harbour investigation.",
                "status": "active",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ],
    )
    return scene


@pytest.fixture
def logged_entry(hermetic: HermeticStack, entry_id: str, scene_id: UUID) -> dict[str, Any]:
    """A logged recorder entry, as the chat router would have written it."""
    doc = {
        "id": entry_id,
        "session_id": "sess-1",
        "role": "gm",
        "content": "Mira opened the sealed door.",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    hermetic.seed("chat_messages", [doc])
    return doc


def _pending_proposal(scene_id: UUID, entry_id: str) -> str:
    """A pending capture proposal produced by the given entry."""
    created = mongodb_create_proposed_change(
        ProposedChangeCreate(
            scene_id=scene_id,
            change_type=ProposalType.FACT,
            content={"statement": "Mira opened the sealed door."},
            authority="gm",
            proposer="CaptureInsightAgent",
            source=f"capture_entry:{entry_id}",
            proposal_type="capture_candidate_fact",
        )
    )
    return str(created.proposal_id)


class TestEntryReading:
    async def test_a_logged_entry_can_be_read_back(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any]
    ) -> None:
        entry = await SessionIngestAgent().get_entry(str(logged_entry["id"]))

        assert entry is not None
        assert entry["content"] == "Mira opened the sealed door."
        assert entry["session_id"] == "sess-1"

    async def test_an_unknown_entry_is_none(self, hermetic: HermeticStack) -> None:
        assert await SessionIngestAgent().get_entry(str(uuid4())) is None


class TestEdit:
    async def test_editing_rewrites_the_text(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any]
    ) -> None:
        updated = await SessionIngestAgent().update_entry(
            str(logged_entry["id"]), "Mira opened the sealed gate."
        )

        assert updated["content"] == "Mira opened the sealed gate."
        assert updated["edited_at"]

    async def test_editing_an_unknown_entry_is_refused(self, hermetic: HermeticStack) -> None:
        with pytest.raises(ValueError, match="not found"):
            await SessionIngestAgent().update_entry(str(uuid4()), "text")

    async def test_an_empty_edit_is_refused(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any]
    ) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            await SessionIngestAgent().update_entry(str(logged_entry["id"]), "   ")

    async def test_a_struck_entry_is_frozen(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any]
    ) -> None:
        agent = SessionIngestAgent()
        await agent.strike_entry(str(logged_entry["id"]))

        with pytest.raises(ValueError, match="restore it before editing"):
            await agent.update_entry(str(logged_entry["id"]), "a different account")


class TestStrike:
    async def test_striking_keeps_the_entry_with_an_audit_trail(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any]
    ) -> None:
        struck = await SessionIngestAgent().strike_entry(str(logged_entry["id"]))

        assert struck["struck"] is True
        assert struck["struck_reason"] == STRIKE_REASON
        assert struck["struck_at"]
        # The text is still there — the audit trail is the point.
        assert struck["content"] == "Mira opened the sealed door."

    async def test_striking_records_the_proposals_it_retracted(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any], scene_id: UUID
    ) -> None:
        proposal_id = _pending_proposal(scene_id, str(logged_entry["id"]))

        struck = await SessionIngestAgent().strike_entry(
            str(logged_entry["id"]), retracted_proposal_ids=[proposal_id]
        )

        assert struck["struck_proposal_ids"] == [proposal_id]

    async def test_striking_an_unknown_entry_is_refused(self, hermetic: HermeticStack) -> None:
        with pytest.raises(ValueError, match="not found"):
            await SessionIngestAgent().strike_entry(str(uuid4()))

    async def test_hard_delete_is_not_supported(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any]
    ) -> None:
        """v1 is soft-delete only — the audit trail must survive."""
        result = await SessionIngestAgent().call_tool(
            "mongodb_delete_session_entry",
            {"entry_id": str(logged_entry["id"]), "soft": False},
        )

        assert "hard delete" in str(result)
        # The entry is untouched.
        entry = await SessionIngestAgent().get_entry(str(logged_entry["id"]))
        assert entry is not None
        assert entry["struck"] is False


class TestUndo:
    async def test_restoring_brings_the_entry_back(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any]
    ) -> None:
        agent = SessionIngestAgent()
        await agent.strike_entry(str(logged_entry["id"]))

        restored = await agent.restore_entry(str(logged_entry["id"]))

        assert restored["struck"] is False
        assert restored["struck_at"] is None
        assert restored["struck_reason"] is None

    async def test_the_undo_names_the_proposals_it_restores(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any], scene_id: UUID
    ) -> None:
        proposal_id = _pending_proposal(scene_id, str(logged_entry["id"]))
        agent = SessionIngestAgent()
        await agent.strike_entry(str(logged_entry["id"]), retracted_proposal_ids=[proposal_id])

        restored = await agent.restore_entry(str(logged_entry["id"]))

        assert restored["restored_proposal_ids"] == [proposal_id]


class TestProposalRetraction:
    async def test_a_pending_proposal_can_be_retracted(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any], scene_id: UUID
    ) -> None:
        proposal_id = _pending_proposal(scene_id, str(logged_entry["id"]))

        proposal = await CaptureInsightAgent().retract_proposal(
            proposal_id, reason=STRIKE_REASON, entry_id=str(logged_entry["id"])
        )

        assert proposal["status"] == "rejected"
        assert proposal["decision_metadata"]["reason"] == STRIKE_REASON

    async def test_a_retract_can_be_undone(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any], scene_id: UUID
    ) -> None:
        proposal_id = _pending_proposal(scene_id, str(logged_entry["id"]))
        agent = CaptureInsightAgent()
        await agent.retract_proposal(proposal_id, reason=STRIKE_REASON)

        proposal = await agent.restore_proposal(proposal_id, reason=STRIKE_REASON)

        assert proposal["status"] == "pending"
        assert proposal["decision_metadata"] is None

    async def test_a_regular_rejection_is_never_restored_by_the_undo(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any], scene_id: UUID
    ) -> None:
        """The undo matches on the retract's actor *and* reason."""
        proposal_id = _pending_proposal(scene_id, str(logged_entry["id"]))
        agent = CaptureInsightAgent()
        await agent.retract_proposal(proposal_id, reason=STRIKE_REASON)

        with pytest.raises(ValueError, match="refusing to restore"):
            await agent.restore_proposal(proposal_id, reason="rejected in CF-8 review")

    async def test_only_pending_proposals_can_be_retracted(
        self, hermetic: HermeticStack, logged_entry: dict[str, Any], scene_id: UUID
    ) -> None:
        proposal_id = _pending_proposal(scene_id, str(logged_entry["id"]))
        agent = CaptureInsightAgent()
        await agent.retract_proposal(proposal_id, reason=STRIKE_REASON)

        with pytest.raises(ValueError, match="Only pending proposals"):
            await agent.retract_proposal(proposal_id, reason=STRIKE_REASON)

    async def test_retracting_an_unknown_proposal_is_refused(self, hermetic: HermeticStack) -> None:
        with pytest.raises(ValueError, match="not found"):
            await CaptureInsightAgent().retract_proposal(str(uuid4()))
