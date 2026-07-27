from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_data.schemas.knowledge_packs import KnowledgePackStatus as KPS


@pytest.mark.asyncio
async def test_commit_accepted_empty():
    keeper = CanonKeeper()
    
    # Mock MongoDB
    mongodb_mock = MagicMock()
    proposals_coll = MagicMock()
    mongodb_mock.get_collection.return_value = proposals_coll
    proposals_coll.find.return_value = []
    
    with pytest.MonkeyPatch.context() as m:
        m.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: mongodb_mock)
        result = await keeper.commit_accepted(uuid4())
        
    assert result == {"committed": 0, "errors": []}


@pytest.mark.asyncio
async def test_commit_accepted_success(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    pack_id = uuid4()
    doc_id = uuid4()
    source_id = str(uuid4())
    pid = str(uuid4())
    
    # Mock proposals
    proposal = {
        "proposal_id": pid,
        "proposal_type": "create_lore_fact"
    }
    
    pack_doc = {
        "pack_id": str(pack_id),
        "source_document_ids": [str(doc_id)]
    }
    
    doc_doc = {
        "doc_id": str(doc_id),
        "source_id": source_id
    }
    
    # Mock MongoDB collections
    proposals_coll = MagicMock()
    proposals_coll.find.return_value = [proposal]
    
    packs_coll = MagicMock()
    packs_coll.find_one.return_value = pack_doc
    
    docs_coll = MagicMock()
    docs_coll.find_one.return_value = doc_doc
    
    def mock_get_collection(name):
        if name == "proposed_changes":
            return proposals_coll
        if name == "knowledge_packs":
            return packs_coll
        if name == "documents":
            return docs_coll
        return MagicMock()

    mongodb_mock = MagicMock()
    mongodb_mock.get_collection.side_effect = mock_get_collection

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: mongodb_mock)
    monkeypatch.setattr(keeper, "_commit_to_neo4j", AsyncMock())

    result = await keeper.commit_accepted(pack_id)
    
    assert result["committed"] == 1
    assert result["errors"] == []
    
    proposals_coll.update_one.assert_called_with(
        {"proposal_id": pid},
        {"$set": {"status": "committed"}}
    )
    packs_coll.update_one.assert_called_with(
        {"pack_id": str(pack_id)},
        {"$set": {"status": KPS.APPLIED.value}}
    )

@pytest.mark.asyncio
async def test_commit_accepted_with_mechanics(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    pack_id = uuid4()
    pid = str(uuid4())
    
    proposal = {
        "proposal_id": pid,
        "proposal_type": "create_lore_fact"
    }
    
    pack_doc = {
        "pack_id": str(pack_id),
        "game_system_data": {
            "name": "My System",
            "tiered_abilities": [{"name": "Ability", "parent_category": None}],
            "tracks": [{"name": "HP", "track_type": "resource"}],
            "conditions": [{"name": "Poisoned"}],
            "resolution_mechanics": [{"dice_formula": "1d20", "mechanic_type": "d20", "difficulty_model": "target_number", "success_type": "meet_or_beat"}]
        }
    }
    
    proposals_coll = MagicMock()
    proposals_coll.find.return_value = [proposal]
    packs_coll = MagicMock()
    packs_coll.find_one.return_value = pack_doc
    
    def mock_get_collection(name):
        if name == "proposed_changes":
            return proposals_coll
        if name == "knowledge_packs":
            return packs_coll
        return MagicMock()

    mongodb_mock = MagicMock()
    mongodb_mock.get_collection.side_effect = mock_get_collection

    monkeypatch.setattr("monitor_data.db.mongodb.get_mongodb_client", lambda: mongodb_mock)
    monkeypatch.setattr(keeper, "_commit_to_neo4j", AsyncMock())
    
    mock_ability = MagicMock()
    monkeypatch.setattr("monitor_agents.canonkeeper.agent.neo4j_create_ability_system", mock_ability)
    mock_track = MagicMock()
    monkeypatch.setattr("monitor_agents.canonkeeper.agent.neo4j_create_track", mock_track)
    mock_condition = MagicMock()
    monkeypatch.setattr("monitor_agents.canonkeeper.agent.neo4j_create_condition", mock_condition)
    mock_rm = MagicMock()
    monkeypatch.setattr("monitor_agents.canonkeeper.agent.neo4j_create_resolution_mechanic", mock_rm)
    
    result = await keeper.commit_accepted(pack_id)
    
    assert result["committed"] == 1
    assert result["errors"] == []
    
    mock_ability.assert_called_once()
    mock_track.assert_called_once()
    mock_condition.assert_called_once()
    mock_rm.assert_called_once()
