"""Live MCP/Neo4j regression for reviewed character-knowledge corrections.

Only UUIDs created by this test are deleted in cleanup. Run explicitly with
RUN_INTEGRATION=1; the normal hermetic suite skips this test.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.cast import fact_visible_to
from monitor_data.tools.mongodb_tools.knowledge_audit import mongodb_list_knowledge_audit
from monitor_data.schemas.knowledge_audit import KnowledgeAuditFilter
from monitor_data.config import settings
from monitor_data.db.mongodb import get_mongodb_client


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_fact_retraction_reaches_knowledge_consumers(monkeypatch: pytest.MonkeyPatch) -> None:
    keeper = CanonKeeper()
    multiverses = await keeper.call_tool("neo4j_list_multiverses", {})
    if not isinstance(multiverses, list) or not multiverses:
        pytest.skip("A multiverse is required to create an isolated test universe")
    universe_id, character_id, fact_id, memory_id, scene_id = uuid4(), uuid4(), uuid4(), uuid4(), uuid4()
    created: list[tuple[str, str]] = []
    vector_client = None
    proposal_ids: list[str] = []

    async def create(name: str, params: dict, identifier: str, cleanup: str) -> dict:
        created.append((cleanup, identifier))
        result = await keeper.call_tool(name, {"params": params})
        if not isinstance(result, dict) or str(result.get("id")) != identifier:
            pytest.fail(f"{name} did not create the test record: {result}")
        return result

    try:
        await create("neo4j_create_universe", {
            "id": str(universe_id), "multiverse_id": str(multiverses[0]["id"]),
            "name": "Isolated knowledge correction test", "description": "Temporary test data",
        }, str(universe_id), "neo4j_delete_universe")
        await create("neo4j_create_entity", {
            "id": str(character_id), "universe_id": str(universe_id),
            "name": "Isolated test character", "entity_type": "character",
        }, str(character_id), "neo4j_delete_entity")
        await create("neo4j_create_fact", {
            "id": str(fact_id), "universe_id": str(universe_id),
            "statement": "The test gate opened.", "fact_type": "state",
        }, str(fact_id), "neo4j_delete_fact")

        before = await keeper.call_tool("neo4j_get_fact", {"fact_id": str(fact_id)})
        assert fact_visible_to(before, character_id)
        from monitor_data.schemas.base import ProposalType
        from monitor_data.schemas.proposed_changes import ProposedChangeCreate
        from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change
        from monitor_ui.auth import LOCAL_USER_ID, Principal
        from monitor_ui.routers.canon_review import accept_proposal
        from monitor_ui.routers import canon_review
        from fastapi import HTTPException
        from monitor_data.db import redis as redis_module

        class Preferences:
            async def pref_get(self, user_id, key):
                return {}

        class NoCache:
            def delete_prefix(self, prefix):
                return 0

        monkeypatch.setattr(redis_module, "get_redis_client", lambda: NoCache())
        get_mongodb_client().get_collection("scenes").insert_one({
            "scene_id": str(scene_id), "universe_id": str(universe_id), "proposed_changes": [],
        })
        proposal = mongodb_create_proposed_change(ProposedChangeCreate(
            scene_id=scene_id, change_type=ProposalType.FACT, authority="gm", proposer="KnowledgeAuditAgent",
            content={"universe_id": str(universe_id), "participants": [str(character_id)],
                     "statement": "The test gate opened.",
                     "knowledge_correction": {"action": "retract", "item_kind": "fact", "item_id": str(fact_id)}},
        ))
        proposal_id = str(proposal.proposal_id)
        proposal_ids.append(proposal_id)
        accepted = await accept_proposal(proposal_id, "Live integration test", None,
                                         Principal(LOCAL_USER_ID, True, "local"), Preferences())
        assert accepted.status.value == "accepted"
        after = await keeper.call_tool("neo4j_get_fact", {"fact_id": str(fact_id)})
        assert not fact_visible_to(after, character_id)
        audit = mongodb_list_knowledge_audit(KnowledgeAuditFilter(entity_id=character_id, universe_id=universe_id))
        assert all(str(item.id) != str(fact_id) for item in audit.items)

        from qdrant_client import QdrantClient, models

        vector_client = QdrantClient(url=settings.resolved_qdrant_url)
        if not vector_client.collection_exists("memories"):
            pytest.skip("The live Qdrant memories collection does not exist")
        info = vector_client.get_collection("memories")
        vector_config = info.config.params.vectors
        if isinstance(vector_config, dict):
            pytest.skip("This live check requires an unnamed vector configuration")
        now = datetime.now(UTC)
        memories = get_mongodb_client().get_collection("character_memories")
        memories.insert_one({
            "memory_id": str(memory_id), "universe_id": str(universe_id), "entity_id": str(character_id),
            "text": "A temporary memory", "importance": 0.5, "certainty": 1.0,
            "emotional_valence": 0.0, "metadata": {}, "created_at": now,
            "last_accessed": now, "access_count": 0,
        })
        vector_client.upsert("memories", points=[models.PointStruct(
            id=str(memory_id), vector=[0.01] * vector_config.size,
            payload={"memory_id": str(memory_id), "universe_id": str(universe_id), "entity_id": str(character_id)},
        )], wait=True)
        await keeper.apply_knowledge_correction({
            "universe_id": str(universe_id), "participants": [str(character_id)],
            "statement": "A corrected temporary memory",
            "knowledge_correction": {"action": "correct", "item_kind": "memory", "item_id": str(memory_id),
                                     "original_statement": "A temporary memory"},
        })
        assert memories.find_one({"memory_id": str(memory_id)})["text"] == "A corrected temporary memory"
        indexed = vector_client.retrieve("memories", ids=[str(memory_id)], with_vectors=True)
        assert len(indexed) == 1
        assert isinstance(indexed[0].vector, list)
        assert max(indexed[0].vector) - min(indexed[0].vector) > 1e-6
        memory_proposal = mongodb_create_proposed_change(ProposedChangeCreate(
            scene_id=scene_id, change_type=ProposalType.FACT, authority="gm", proposer="KnowledgeAuditAgent",
            content={"universe_id": str(universe_id), "participants": [str(character_id)],
                     "statement": "A corrected temporary memory",
                     "knowledge_correction": {"action": "retract", "item_kind": "memory", "item_id": str(memory_id)}},
        ))
        proposal_ids.append(str(memory_proposal.proposal_id))
        update_proposal = canon_review.mongodb_update_proposed_change
        attempts = 0

        def fail_once(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ValueError("Simulated verdict write failure")
            return update_proposal(*args, **kwargs)

        monkeypatch.setattr(canon_review, "mongodb_update_proposed_change", fail_once)
        with pytest.raises(HTTPException) as failure:
            await accept_proposal(str(memory_proposal.proposal_id), "Live integration test", None,
                                  Principal(LOCAL_USER_ID, True, "local"), Preferences())
        assert failure.value.status_code == 409
        assert memories.find_one({"memory_id": str(memory_id)}) is None
        assert vector_client.retrieve("memories", ids=[str(memory_id)]) == []
        accepted_memory = await accept_proposal(str(memory_proposal.proposal_id), "Live integration test", None,
                                                Principal(LOCAL_USER_ID, True, "local"), Preferences())
        assert accepted_memory.status.value == "accepted"
        assert memories.find_one({"memory_id": str(memory_id)}) is None
        assert vector_client.retrieve("memories", ids=[str(memory_id)]) == []
    finally:
        if proposal_ids:
            get_mongodb_client().get_collection("proposed_changes").delete_many({"proposal_id": {"$in": proposal_ids}})
        get_mongodb_client().get_collection("scenes").delete_one({"scene_id": str(scene_id)})
        get_mongodb_client().get_collection("character_memories").delete_one({"memory_id": str(memory_id)})
        if vector_client is not None:
            if vector_client.collection_exists("memories"):
                vector_client.delete("memories", points_selector=[str(memory_id)], wait=True)
            vector_client.close()
        cleanup_errors = []
        for tool, identifier in reversed(created):
            parameter = {"neo4j_delete_fact": "fact_id", "neo4j_delete_entity": "entity_id",
                         "neo4j_delete_universe": "universe_id"}[tool]
            getter = {"neo4j_delete_fact": "neo4j_get_fact", "neo4j_delete_entity": "neo4j_get_entity",
                      "neo4j_delete_universe": "neo4j_get_universe"}[tool]
            existing = await keeper.call_tool(getter, {parameter: identifier})
            if existing is None:
                continue
            result = await keeper.call_tool(tool, {parameter: identifier, "force": True})
            if not isinstance(result, dict) or not result.get("deleted"):
                cleanup_errors.append(f"{tool} {identifier}: {result}")
        if cleanup_errors:
            pytest.fail("Cleanup failed: " + "; ".join(cleanup_errors))
