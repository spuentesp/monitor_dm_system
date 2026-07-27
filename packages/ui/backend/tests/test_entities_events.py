import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient

from monitor_ui.main import app
from monitor_data.schemas.base import ProposalType, Authority

client = TestClient(app)

pytestmark = pytest.mark.unit

@patch("monitor_data.tools.mongodb_tools.proposals.mongodb_create_proposed_change")
def test_create_event_uses_proposed_change(mock_mongo_create):
    """Prove UI mutation endpoint creates the correct proposal and doesn't call Neo4j directly."""
    # Setup mock
    mock_proposal = MagicMock()
    mock_proposal.model_dump.return_value = {"proposal_id": "dummy_proposal"}
    mock_mongo_create.return_value = mock_proposal

    universe_id = uuid4()
    
    # Send request
    response = client.post(
        f"/api/entities/entities/{universe_id}/events",
        json={
            "title": "The Fall of the Empire",
            "description": "A big event.",
            "start_time": "1000-01-01T00:00:00Z",
            "end_time": "1000-12-31T23:59:59Z"
        }
    )
    
    assert response.status_code == 201
    assert response.json() == {"proposal_id": "dummy_proposal"}
    
    # Assert Mongo proposal creation was called with correct structure
    mock_mongo_create.assert_called_once()
    proposal = mock_mongo_create.call_args[0][0]
    
    assert proposal.change_type == ProposalType.EVENT
    assert proposal.authority == Authority.GM
    assert proposal.proposer == "UI"
    assert proposal.content["operation"] == "create"
    assert proposal.content["universe_id"] == str(universe_id)
    assert proposal.content["title"] == "The Fall of the Empire"

@patch("monitor_data.tools.mongodb_tools.proposals.mongodb_create_proposed_change")
def test_update_event_uses_proposed_change(mock_mongo_create):
    mock_proposal = MagicMock()
    mock_proposal.model_dump.return_value = {"proposal_id": "dummy_proposal"}
    mock_mongo_create.return_value = mock_proposal

    event_id = uuid4()

    response = client.patch(
        f"/api/entities/entities/events/{event_id}",
        json={
            "description": "An updated description."
        }
    )
    
    assert response.status_code == 200
    mock_mongo_create.assert_called_once()
    
    proposal = mock_mongo_create.call_args[0][0]
    assert proposal.change_type == ProposalType.EVENT
    assert proposal.content["operation"] == "update"
    assert proposal.content["event_id"] == str(event_id)
    assert proposal.content["description"] == "An updated description."

@patch("monitor_data.tools.mongodb_tools.proposals.mongodb_create_proposed_change")
def test_delete_event_uses_proposed_change(mock_mongo_create):
    mock_proposal = MagicMock()
    mock_proposal.model_dump.return_value = {"proposal_id": "dummy_proposal"}
    mock_mongo_create.return_value = mock_proposal

    event_id = uuid4()
    
    response = client.delete(f"/api/entities/entities/events/{event_id}?force=true")
    
    assert response.status_code == 200
    mock_mongo_create.assert_called_once()
    
    proposal = mock_mongo_create.call_args[0][0]
    assert proposal.change_type == ProposalType.EVENT
    assert proposal.content["operation"] == "delete"
    assert proposal.content["event_id"] == str(event_id)
    assert proposal.content["force"] is True
