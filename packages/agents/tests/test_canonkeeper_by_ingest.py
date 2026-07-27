"""Regression tests for the F1-4 by-ingest lifecycle (I-4, CF-8).

Covers:
- bulk_enqueue_proposals writes a schema-valid ProposalStatus ("pending"),
  not the invalid "pending_review"
- _auto_canonize attribution is exact: only the current job's pack
  proposals (source == "knowledge_pack:<pack_id>") are selected — not
  every pending proposal in the universe
- the enqueue branch is reachable when MONITOR_AUTO_CANONIZE is unset/0
- commit_accepted_for_job commits only accepted proposals tagged
  source == "ingestion_job:<job_id>"
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from monitor_data.schemas.base import ProposalStatus

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.ingestion.agent import IngestionPipeline


def _mongo_with_collections(collections: dict[str, MagicMock]) -> MagicMock:
    client = MagicMock()
    client.get_collection.side_effect = lambda name: collections[name]
    return client


def _proposal_doc(source: str, status: str = "pending") -> dict[str, Any]:
    return {
        "proposal_id": str(uuid4()),
        "change_type": "fact",
        "proposal_type": "create_lore_fact",
        "content": {"statement": "The moon is hollow"},
        "status": status,
        "source": source,
    }


class TestBulkEnqueueStatus:
    @pytest.mark.asyncio
    async def test_enqueued_status_is_schema_valid(self, monkeypatch: pytest.MonkeyPatch):
        """Enqueue must write ProposalStatus.PENDING, not 'pending_review'."""
        from monitor_data.db import mongodb as mongodb_module

        proposals_coll = MagicMock()
        client = _mongo_with_collections({"proposed_changes": proposals_coll})
        monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: client)

        keeper = CanonKeeper()
        job_id = uuid4()
        result = await keeper.bulk_enqueue_proposals(
            [_proposal_doc(source="knowledge_pack:whatever")],
            ingestion_job_id=job_id,
        )

        assert result == {"enqueued": 1, "errors": []}
        set_doc = proposals_coll.update_one.call_args.args[1]["$set"]
        # Must not raise — the written status is a valid ProposalStatus.
        assert ProposalStatus(set_doc["status"]) is ProposalStatus.PENDING
        assert set_doc["source"] == f"ingestion_job:{job_id}"


class TestAutoCanonizeAttribution:
    def _patch_mongo(self, monkeypatch: pytest.MonkeyPatch, proposals: list[dict[str, Any]]) -> MagicMock:
        from monitor_data.db import mongodb as mongodb_module

        proposals_coll = MagicMock()
        proposals_coll.find.return_value = iter(proposals)
        client = _mongo_with_collections({"proposed_changes": proposals_coll})
        monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: client)
        return proposals_coll

    @pytest.mark.asyncio
    async def test_enqueue_branch_reachable_when_auto_canonize_off(self, monkeypatch: pytest.MonkeyPatch):
        """Default (MONITOR_AUTO_CANONIZE unset): proposals are enqueued
        for review, not silently dropped."""
        monkeypatch.delenv("MONITOR_AUTO_CANONIZE", raising=False)
        pack_id = uuid4()
        job_id = uuid4()
        proposals = [_proposal_doc(source=f"knowledge_pack:{pack_id}")]
        proposals_coll = self._patch_mongo(monkeypatch, proposals)

        keeper = MagicMock()
        keeper.bulk_enqueue_proposals = AsyncMock(return_value={"enqueued": 1, "errors": []})
        keeper.bulk_commit_proposals = AsyncMock()
        monkeypatch.setattr("monitor_agents.canonkeeper.agent.CanonKeeper", MagicMock(return_value=keeper))

        pipeline = IngestionPipeline()
        enqueued, errors = await pipeline._auto_canonize(
            job_id=job_id,
            multiverse_id=uuid4(),
            universe_id=uuid4(),
            analysis_result=SimpleNamespace(pack_id=pack_id),
        )

        assert (enqueued, errors) == (1, 0)
        keeper.bulk_enqueue_proposals.assert_awaited_once()
        keeper.bulk_commit_proposals.assert_not_called()
        # Attribution is exact: the query targets this job's pack only —
        # not every pending proposal in the universe/multiverse.
        query = proposals_coll.find.call_args.args[0]
        assert query == {"status": "pending", "source": f"knowledge_pack:{pack_id}"}

    @pytest.mark.asyncio
    async def test_commit_branch_when_auto_canonize_on(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("MONITOR_AUTO_CANONIZE", "1")
        pack_id = uuid4()
        proposals = [_proposal_doc(source=f"knowledge_pack:{pack_id}")]
        self._patch_mongo(monkeypatch, proposals)

        keeper = MagicMock()
        keeper.bulk_enqueue_proposals = AsyncMock()
        keeper.bulk_commit_proposals = AsyncMock(return_value={"committed": 1, "rejected": 0, "errors": []})
        monkeypatch.setattr("monitor_agents.canonkeeper.agent.CanonKeeper", MagicMock(return_value=keeper))

        pipeline = IngestionPipeline()
        committed, errors = await pipeline._auto_canonize(
            job_id=uuid4(),
            multiverse_id=uuid4(),
            universe_id=uuid4(),
            analysis_result=SimpleNamespace(pack_id=pack_id),
        )

        assert (committed, errors) == (1, 0)
        keeper.bulk_commit_proposals.assert_awaited_once()
        keeper.bulk_enqueue_proposals.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_pack_id_means_noop(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("MONITOR_AUTO_CANONIZE", raising=False)
        proposals_coll = self._patch_mongo(monkeypatch, [])

        pipeline = IngestionPipeline()
        count, errors = await pipeline._auto_canonize(
            job_id=uuid4(),
            multiverse_id=uuid4(),
            universe_id=uuid4(),
            analysis_result=SimpleNamespace(pack_id=None),
        )

        assert (count, errors) == (0, 0)
        proposals_coll.find.assert_not_called()


class TestCommitAcceptedForJob:
    @pytest.mark.asyncio
    async def test_commits_only_accepted_proposals_for_the_job(self, monkeypatch: pytest.MonkeyPatch):
        from monitor_data.db import mongodb as mongodb_module

        job_id = uuid4()
        source_id = uuid4()
        accepted = _proposal_doc(source=f"ingestion_job:{job_id}", status="accepted")

        proposals_coll = MagicMock()
        proposals_coll.find.return_value = iter([accepted])
        jobs_coll = MagicMock()
        jobs_coll.find_one.return_value = {"job_id": str(job_id), "source_id": str(source_id)}
        client = _mongo_with_collections({"proposed_changes": proposals_coll, "ingestion_jobs": jobs_coll})
        monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: client)

        keeper = CanonKeeper()
        commit = AsyncMock()
        monkeypatch.setattr(keeper, "_commit_to_neo4j", commit)

        result = await keeper.commit_accepted_for_job(job_id)

        # Exact scope: accepted proposals of THIS job only.
        query = proposals_coll.find.call_args.args[0]
        assert query == {"source": f"ingestion_job:{job_id}", "status": "accepted"}
        assert result == {"committed": 1, "errors": []}
        commit.assert_awaited_once()
        # Provenance: the job's Neo4j Source node is attached.
        assert commit.call_args.kwargs["source_ids"] == [source_id]
        # Committed proposals are marked so they are not re-processed.
        proposals_coll.update_one.assert_called_once_with(
            {"proposal_id": accepted["proposal_id"]},
            {"$set": {"status": "committed"}},
        )

    @pytest.mark.asyncio
    async def test_no_accepted_proposals_is_noop(self, monkeypatch: pytest.MonkeyPatch):
        from monitor_data.db import mongodb as mongodb_module

        proposals_coll = MagicMock()
        proposals_coll.find.return_value = iter([])
        client = _mongo_with_collections({"proposed_changes": proposals_coll})
        monkeypatch.setattr(mongodb_module, "get_mongodb_client", lambda: client)

        keeper = CanonKeeper()
        result = await keeper.commit_accepted_for_job(uuid4())

        assert result == {"committed": 0, "errors": []}
