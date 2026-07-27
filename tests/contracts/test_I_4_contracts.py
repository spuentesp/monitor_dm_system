"""
I-4: Proposal Review — Contract Tests

Unit-level contract tests for the proposal review flow schemas and
CanonKeeper auto_accept parameter. These tests do NOT require a database.

Covers:
  - KnowledgePackStatus.REVIEW_PENDING value
  - ProposedChangeFilter source field
  - DecisionMetadata construction
  - CanonKeeper.apply_pack_to_universe(auto_accept=False) stops at review
  - CanonKeeper.apply_pack_to_universe(auto_accept=True) commits immediately
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from monitor_data.schemas.knowledge_packs import (
    KnowledgePackStatus,
)
from monitor_data.schemas.proposed_changes import (
    DecisionMetadata,
    ProposedChangeFilter,
)

# =============================================================================
# Schema contract tests
# =============================================================================


@pytest.mark.unit
class TestReviewPendingStatus:
    """KnowledgePackStatus has REVIEW_PENDING value."""

    def test_review_pending_exists(self):
        assert KnowledgePackStatus.REVIEW_PENDING == "review_pending"

    def test_all_statuses(self):
        values = [s.value for s in KnowledgePackStatus]
        assert "review_pending" in values
        assert set(values) == {
            "pending",
            "ready",
            "review_pending",
            "applied",
            "failed",
            "archived",
        }


@pytest.mark.unit
class TestProposalFilterSource:
    """ProposedChangeFilter supports source field."""

    def test_source_filter_default(self):
        f = ProposedChangeFilter()
        assert f.source is None

    def test_source_filter_set(self):
        pack_id = uuid4()
        f = ProposedChangeFilter(source=f"knowledge_pack:{pack_id}")
        assert f.source == f"knowledge_pack:{pack_id}"


@pytest.mark.unit
class TestDecisionMetadata:
    """DecisionMetadata can be constructed for user decisions."""

    def test_user_accept_metadata(self):
        now = datetime.now(UTC)
        dm = DecisionMetadata(
            decided_by="user",
            decided_at=now,
            reason="User accepted",
            canonical_ref=None,
        )
        assert dm.decided_by == "user"
        assert dm.reason == "User accepted"

    def test_user_reject_metadata(self):
        now = datetime.now(UTC)
        dm = DecisionMetadata(
            decided_by="user",
            decided_at=now,
            reason="User rejected: incorrect entity type",
        )
        assert dm.decided_by == "user"
        assert "incorrect" in dm.reason


# =============================================================================
# CanonKeeper auto_accept contract tests
# =============================================================================


@pytest.mark.unit
class TestCanonKeeperAutoAccept:
    """CanonKeeper.apply_pack_to_universe respects auto_accept parameter."""

    @pytest.mark.asyncio
    async def test_auto_accept_false_stops_at_review(self):
        """auto_accept=False creates proposals but does NOT commit to Neo4j."""
        from monitor_agents.canonkeeper.agent import CanonKeeper

        pack_id = uuid4()
        mv_id = uuid4()

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_apply_knowledge_pack",
                return_value={"proposals_created": 5},
            ),
            patch(
                "monitor_data.db.mongodb.get_mongodb_client",
            ) as mock_mongo,
        ):
            # Mock MongoDB collections
            mock_proposals = MagicMock()
            mock_proposals.count_documents.return_value = 0
            mock_proposals.find.return_value = []

            mock_packs = MagicMock()
            mock_packs.find_one.return_value = None

            mongo_instance = MagicMock()
            mongo_instance.get_collection.side_effect = lambda name: {
                "proposed_changes": mock_proposals,
                "knowledge_packs": mock_packs,
                "documents": MagicMock(),
            }.get(name, MagicMock())
            mock_mongo.return_value = mongo_instance

            keeper = CanonKeeper()
            result = await keeper.apply_pack_to_universe(
                pack_id=pack_id,
                multiverse_id=mv_id,
                auto_accept=False,
            )

        assert result["proposals_created"] == 5
        assert result["committed"] == 0
        assert result["review_status"] == "pending"

    @pytest.mark.asyncio
    async def test_auto_accept_true_commits(self):
        """auto_accept=True (legacy) commits all proposals immediately."""
        from monitor_agents.canonkeeper.agent import CanonKeeper

        pack_id = uuid4()
        mv_id = uuid4()

        proposal_doc = {
            "proposal_id": str(uuid4()),
            "proposal_type": "create_entity_archetype",
            "content": {"name": "Fighter", "entity_type": "character"},
            "status": "pending",
        }

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_apply_knowledge_pack",
                return_value={"proposals_created": 1},
            ),
            patch(
                "monitor_data.db.mongodb.get_mongodb_client",
            ) as mock_mongo,
            patch.object(
                CanonKeeper,
                "_commit_to_neo4j",
                new_callable=AsyncMock,
            ),
        ):
            mock_proposals = MagicMock()
            mock_proposals.count_documents.return_value = 0
            mock_proposals.find.return_value = [proposal_doc]
            mock_proposals.update_one = MagicMock()

            mock_packs = MagicMock()
            mock_packs.find_one.return_value = {
                "source_document_ids": [],
                "game_system_data": None,
            }

            mongo_instance = MagicMock()
            mongo_instance.get_collection.side_effect = lambda name: {
                "proposed_changes": mock_proposals,
                "knowledge_packs": mock_packs,
                "documents": MagicMock(),
            }.get(name, MagicMock())
            mock_mongo.return_value = mongo_instance

            keeper = CanonKeeper()
            result = await keeper.apply_pack_to_universe(
                pack_id=pack_id,
                multiverse_id=mv_id,
                auto_accept=True,
            )

        assert result["committed"] == 1
        assert result["proposals_created"] == 1
