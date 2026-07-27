"""
Tests for the Proposal Review flow (I-4) — E2E tests.

Unit-level tests (schema validation, CanonKeeper auto_accept) have been
moved to tests/contracts/test_I_4_contracts.py so they run without
requiring RUN_E2E=1.

This file contains only integration tests that require a live MongoDB.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.base import (
    ProposalStatus,
)
from monitor_data.schemas.knowledge_packs import (
    ApplyKnowledgePackRequest,
    ExtractedAxiom,
    ExtractedEntityArchetype,
    ExtractedLoreFact,
    KnowledgePackCreate,
    KnowledgePackStatus,
    KnowledgePackType,
)
from monitor_data.schemas.proposed_changes import (
    DecisionMetadata,
    ProposedChangeFilter,
    ProposedChangeUpdate,
)

# =============================================================================
# Integration tests — proposal review workflow (requires MongoDB)
# =============================================================================


@pytest.mark.e2e
class TestProposalReviewWorkflow:
    """
    Full proposal review flow:
      1. Create a KnowledgePack
      2. Apply → creates PENDING proposals
      3. List proposals → filter by source
      4. Accept some, reject others
      5. Verify only accepted are present

    Requires MongoDB (RUN_E2E=1).
    """

    @pytest.fixture(autouse=True)
    def _setup_env(self, e2e_databases):
        """Ensure databases are connected."""
        pass

    @pytest.mark.asyncio
    async def test_apply_creates_pending_proposals(self):
        """mongodb_apply_knowledge_pack creates PENDING proposals."""
        from monitor_data.db.mongodb import get_mongodb_client
        from monitor_data.tools.mongodb_tools import (
            mongodb_apply_knowledge_pack,
            mongodb_create_knowledge_pack,
            mongodb_delete_knowledge_pack,
            mongodb_list_proposed_changes,
        )

        mv_id = uuid4()
        pack_id = uuid4()

        try:
            # Create a minimal pack
            pack = mongodb_create_knowledge_pack(
                KnowledgePackCreate(
                    pack_id=pack_id,
                    status=KnowledgePackStatus.READY,
                    name="Test Review Pack",
                    pack_type=KnowledgePackType.RULEBOOK,
                    axioms=[
                        ExtractedAxiom(
                            statement="Magic exists in this world",
                            domain="magic",
                            confidence=0.95,
                        ),
                    ],
                    entity_archetypes=[
                        ExtractedEntityArchetype(
                            name="Wizard",
                            entity_type="character",
                            entity_roles=["spellcaster"],
                            confidence=0.85,
                        ),
                    ],
                    lore_facts=[
                        ExtractedLoreFact(
                            statement="The Tower of Sorcery was built in 1245 AE",
                            fact_type="historical",
                            entity_names=["Tower of Sorcery"],
                            confidence=0.7,
                        ),
                    ],
                ),
            )

            assert pack.status == KnowledgePackStatus.READY

            # Apply → creates proposals
            result = mongodb_apply_knowledge_pack(
                pack_id,
                ApplyKnowledgePackRequest(
                    multiverse_id=mv_id,
                    conflict_resolution="merge",
                ),
            )

            assert result["proposals_created"] == 3  # 1 axiom + 1 entity + 1 lore
            assert result["axioms_proposed"] == 1
            assert result["entities_proposed"] == 1
            assert result["lore_facts_proposed"] == 1

            # List proposals for this pack
            proposals = mongodb_list_proposed_changes(
                ProposedChangeFilter(
                    source=f"knowledge_pack:{pack_id}",
                    limit=100,
                )
            )
            assert proposals.total == 3
            assert all(
                p.status == ProposalStatus.PENDING for p in proposals.proposed_changes
            )

        finally:
            # Cleanup
            mongo = get_mongodb_client()
            mongo.get_collection("proposed_changes").delete_many(
                {"source": f"knowledge_pack:{pack_id}"}
            )
            try:
                mongodb_delete_knowledge_pack(pack_id)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_accept_reject_proposals(self):
        """Accept some proposals, reject others."""
        from monitor_data.db.mongodb import get_mongodb_client
        from monitor_data.tools.mongodb_tools import (
            mongodb_apply_knowledge_pack,
            mongodb_create_knowledge_pack,
            mongodb_delete_knowledge_pack,
            mongodb_list_proposed_changes,
            mongodb_update_proposed_change,
        )

        mv_id = uuid4()
        pack_id = uuid4()

        try:
            # Create pack with 2 items
            mongodb_create_knowledge_pack(
                KnowledgePackCreate(
                    pack_id=pack_id,
                    status=KnowledgePackStatus.READY,
                    name="Test Accept/Reject",
                    pack_type=KnowledgePackType.HOMEBREW,
                    axioms=[
                        ExtractedAxiom(
                            statement="Dragons breathe fire",
                            domain="creatures",
                            confidence=0.9,
                        ),
                    ],
                    entity_archetypes=[
                        ExtractedEntityArchetype(
                            name="Red Dragon",
                            entity_type="character",
                            entity_roles=["monster"],
                            confidence=0.8,
                        ),
                    ],
                ),
            )

            mongodb_apply_knowledge_pack(
                pack_id,
                ApplyKnowledgePackRequest(
                    multiverse_id=mv_id,
                    conflict_resolution="merge",
                ),
            )

            # Get proposals
            proposals = mongodb_list_proposed_changes(
                ProposedChangeFilter(
                    source=f"knowledge_pack:{pack_id}",
                    limit=100,
                )
            )
            assert proposals.total == 2

            # Accept first, reject second
            now = datetime.now(UTC)
            p1, p2 = proposals.proposed_changes[0], proposals.proposed_changes[1]

            accepted = mongodb_update_proposed_change(
                p1.proposal_id,
                ProposedChangeUpdate(
                    status=ProposalStatus.ACCEPTED,
                    decision_metadata=DecisionMetadata(
                        decided_by="user",
                        decided_at=now,
                        reason="Looks correct",
                    ),
                ),
            )
            assert accepted.status == ProposalStatus.ACCEPTED

            rejected = mongodb_update_proposed_change(
                p2.proposal_id,
                ProposedChangeUpdate(
                    status=ProposalStatus.REJECTED,
                    decision_metadata=DecisionMetadata(
                        decided_by="user",
                        decided_at=now,
                        reason="Duplicate",
                    ),
                ),
            )
            assert rejected.status == ProposalStatus.REJECTED

            # Verify counts
            pending = mongodb_list_proposed_changes(
                ProposedChangeFilter(
                    source=f"knowledge_pack:{pack_id}",
                    status=ProposalStatus.PENDING,
                )
            )
            assert pending.total == 0

            accepted_list = mongodb_list_proposed_changes(
                ProposedChangeFilter(
                    source=f"knowledge_pack:{pack_id}",
                    status=ProposalStatus.ACCEPTED,
                )
            )
            assert accepted_list.total == 1

        finally:
            mongo = get_mongodb_client()
            mongo.get_collection("proposed_changes").delete_many(
                {"source": f"knowledge_pack:{pack_id}"}
            )
            try:
                mongodb_delete_knowledge_pack(pack_id)
            except Exception:
                pass
