import pytest
from unittest.mock import patch, ANY
from uuid import uuid4

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_data.schemas.agent_responses import CanonKeeperVerdict, CanonKeeperDecision

pytestmark = pytest.mark.asyncio

@patch("monitor_agents.canonkeeper.agent.CanonKeeper.call_tool")
async def test_commit_fact_handles_temporal_event_create(mock_call_tool):
    agent = CanonKeeper.__new__(CanonKeeper)
    mock_call_tool.return_value = {"id": "neo4j_uuid"}
    
    # Needs a proposals_coll mock
    class MockColl:
        def update_one(self, *args, **kwargs):
            pass
            
    proposal = {
        "change_type": "event",
        "content": {
            "operation": "create",
            "universe_id": str(uuid4()),
            "title": "A Great Battle",
            "start_time": "1000-01-01T00:00:00Z"
        }
    }
    
    prop_id = str(uuid4())
    
    verdict = CanonKeeperVerdict(
        proposal_id=prop_id,
        decision=CanonKeeperDecision.ACCEPTED,
        reasoning="This is a good event",
        canon_node_type="event",
        canon_properties={}
    )
    
    # We patch _store_neo4j_id_on_proposal so it doesn't fail on mongo
    with patch.object(agent, "_store_neo4j_id_on_proposal") as mock_store:
        await agent._commit_fact(
            proposals_coll=MockColl(),
            proposal_id=prop_id,
            proposal=proposal,
            source_id_strs=[],
            verdict=verdict
        )
        
        mock_call_tool.assert_called_once_with(
            "neo4j_create_event", 
            {"params": ANY}
        )
        mock_store.assert_called_once_with(
            ANY, prop_id, "neo4j_uuid"
        )

@patch("monitor_agents.canonkeeper.agent.CanonKeeper.call_tool")
async def test_commit_fact_handles_temporal_event_update(mock_call_tool):
    agent = CanonKeeper.__new__(CanonKeeper)
    mock_call_tool.return_value = {"id": "neo4j_uuid_2"}
    
    proposal = {
        "change_type": "event",
        "content": {
            "operation": "update",
            "event_id": str(uuid4()),
            "description": "Updated desc"
        }
    }
    prop_id = str(uuid4())
    verdict = CanonKeeperVerdict(proposal_id=prop_id, decision=CanonKeeperDecision.ACCEPTED, reasoning="This is a good event", canon_node_type="event", canon_properties={})
    
    with patch.object(agent, "_store_neo4j_id_on_proposal"):
        await agent._commit_fact(None, prop_id, proposal, [], verdict)
        
        mock_call_tool.assert_called_once_with(
            "neo4j_update_event", 
            {"event_id": proposal["content"]["event_id"], "updates": {"description": "Updated desc"}}
        )

@patch("monitor_agents.canonkeeper.agent.CanonKeeper.call_tool")
async def test_commit_fact_handles_temporal_event_delete(mock_call_tool):
    agent = CanonKeeper.__new__(CanonKeeper)
    
    proposal = {
        "change_type": "event",
        "content": {
            "operation": "delete",
            "event_id": str(uuid4()),
            "force": True
        }
    }
    prop_id = str(uuid4())
    verdict = CanonKeeperVerdict(proposal_id=prop_id, decision=CanonKeeperDecision.ACCEPTED, reasoning="This is a good event", canon_node_type="event", canon_properties={})
    
    with patch.object(agent, "_store_neo4j_id_on_proposal"):
        await agent._commit_fact(None, prop_id, proposal, [], verdict)
        
        mock_call_tool.assert_called_once_with(
            "neo4j_delete_event", 
            {"event_id": proposal["content"]["event_id"], "force": True}
        )
