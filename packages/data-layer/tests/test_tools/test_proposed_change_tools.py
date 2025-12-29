"""
Unit tests for MongoDB proposed change operations (DL-5).

Tests cover:
- mongodb_create_proposed_change
- mongodb_get_proposed_change
- mongodb_list_proposed_changes
- mongodb_update_proposed_change
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4
from datetime import datetime, timezone

import pytest

from monitor_data.schemas.proposed_changes import (
    ProposedChangeCreate,
    ProposedChangeUpdate,
    ProposedChangeFilter,
    Evidence,
    DecisionMetadata,
)
from monitor_data.schemas.base import ProposalStatus, ProposalType, Authority
from monitor_data.tools.mongodb_tools import (
    mongodb_create_proposed_change,
    mongodb_get_proposed_change,
    mongodb_list_proposed_changes,
    mongodb_update_proposed_change,
)


# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_mongodb_client() -> Mock:
    """Provide a mock MongoDB client."""
    client = Mock()
    collection = Mock()
    client.get_collection.return_value = collection
    return client


@pytest.fixture
def scene_doc_data(
    story_data: Dict[str, Any], universe_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Provide sample scene document data."""
    return {
        "scene_id": str(uuid4()),
        "story_id": story_data["id"],
        "universe_id": universe_data["id"],
        "title": "Test Scene",
        "status": "active",
        "proposed_changes": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def proposed_change_doc(scene_doc_data: Dict[str, Any]) -> Dict[str, Any]:
    """Provide sample proposed change document."""
    return {
        "proposal_id": str(uuid4()),
        "scene_id": scene_doc_data["scene_id"],
        "story_id": None,
        "turn_id": None,
        "change_type": ProposalType.FACT.value,
        "content": {"statement": "The sky is blue", "entity_ids": []},
        "evidence": [
            {"type": "turn", "ref_id": str(uuid4())},
        ],
        "confidence": 0.9,
        "authority": Authority.PLAYER.value,
        "proposer": "TestAgent",
        "status": ProposalStatus.PENDING.value,
        "decision_metadata": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


# =============================================================================
# TESTS: mongodb_create_proposed_change
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_fact(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
    scene_doc_data: Dict[str, Any],
):
    """Test creating a proposed change with type 'fact'."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB collections
    scenes_collection = Mock()
    proposed_changes_collection = Mock()
    mock_mongodb_client.get_collection.side_effect = lambda name: {
        "scenes": scenes_collection,
        "proposed_changes": proposed_changes_collection,
    }[name]

    # Mock scene exists
    scenes_collection.find_one.return_value = scene_doc_data
    scenes_collection.update_one.return_value = Mock()
    proposed_changes_collection.insert_one.return_value = Mock()

    evidence = [Evidence(type="turn", ref_id=uuid4())]
    params = ProposedChangeCreate(
        scene_id=UUID(scene_doc_data["scene_id"]),
        change_type=ProposalType.FACT,
        content={"statement": "The sky is blue", "entity_ids": []},
        evidence=evidence,
        confidence=0.9,
        authority=Authority.PLAYER,
        proposer="Narrator",
    )

    result = mongodb_create_proposed_change(params)

    assert result.change_type == ProposalType.FACT
    assert result.scene_id == UUID(scene_doc_data["scene_id"])
    assert result.status == ProposalStatus.PENDING
    assert result.confidence == 0.9
    assert result.proposer == "Narrator"
    assert result.decision_metadata is None
    proposed_changes_collection.insert_one.assert_called_once()
    scenes_collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_entity(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
    scene_doc_data: Dict[str, Any],
):
    """Test creating a proposed change with type 'entity'."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB collections
    scenes_collection = Mock()
    proposed_changes_collection = Mock()
    mock_mongodb_client.get_collection.side_effect = lambda name: {
        "scenes": scenes_collection,
        "proposed_changes": proposed_changes_collection,
    }[name]

    scenes_collection.find_one.return_value = scene_doc_data
    scenes_collection.update_one.return_value = Mock()
    proposed_changes_collection.insert_one.return_value = Mock()

    params = ProposedChangeCreate(
        scene_id=UUID(scene_doc_data["scene_id"]),
        change_type=ProposalType.ENTITY,
        content={
            "name": "Gandalf",
            "entity_type": "character",
            "properties": {"race": "Maia", "class": "Wizard"},
        },
        confidence=1.0,
        authority=Authority.GM,
        proposer="CanonKeeper",
    )

    result = mongodb_create_proposed_change(params)

    assert result.change_type == ProposalType.ENTITY
    assert result.content["name"] == "Gandalf"
    assert result.authority == Authority.GM
    proposed_changes_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_relationship(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
    scene_doc_data: Dict[str, Any],
):
    """Test creating a proposed change with type 'relationship'."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock MongoDB collections
    scenes_collection = Mock()
    proposed_changes_collection = Mock()
    mock_mongodb_client.get_collection.side_effect = lambda name: {
        "scenes": scenes_collection,
        "proposed_changes": proposed_changes_collection,
    }[name]

    scenes_collection.find_one.return_value = scene_doc_data
    scenes_collection.update_one.return_value = Mock()
    proposed_changes_collection.insert_one.return_value = Mock()

    from_id = uuid4()
    to_id = uuid4()
    params = ProposedChangeCreate(
        scene_id=UUID(scene_doc_data["scene_id"]),
        change_type=ProposalType.RELATIONSHIP,
        content={
            "from": str(from_id),
            "to": str(to_id),
            "rel_type": "ALLY_OF",
            "properties": {"strength": 0.8},
        },
        confidence=0.95,
        authority=Authority.SYSTEM,
        proposer="Resolver",
    )

    result = mongodb_create_proposed_change(params)

    assert result.change_type == ProposalType.RELATIONSHIP
    assert result.content["rel_type"] == "ALLY_OF"
    proposed_changes_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_story_level(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test creating a story-level proposed change (no scene_id)."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock story exists in Neo4j
    mock_neo4j_client.execute_read.return_value = [{"id": story_data["id"]}]

    # Mock MongoDB collection
    proposed_changes_collection = Mock()
    mock_mongodb_client.get_collection.return_value = proposed_changes_collection
    proposed_changes_collection.insert_one.return_value = Mock()

    params = ProposedChangeCreate(
        story_id=UUID(story_data["id"]),
        change_type=ProposalType.EVENT,
        content={"description": "A major battle occurred", "timestamp": "2024-01-01"},
        confidence=1.0,
        authority=Authority.GM,
        proposer="Orchestrator",
    )

    result = mongodb_create_proposed_change(params)

    assert result.story_id == UUID(story_data["id"])
    assert result.scene_id is None
    assert result.change_type == ProposalType.EVENT
    proposed_changes_collection.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_invalid_scene(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test creating a proposed change with invalid scene_id."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock scene doesn't exist
    scenes_collection = Mock()
    mock_mongodb_client.get_collection.return_value = scenes_collection
    scenes_collection.find_one.return_value = None

    params = ProposedChangeCreate(
        scene_id=uuid4(),
        change_type=ProposalType.FACT,
        content={"statement": "Test"},
        proposer="TestAgent",
    )

    with pytest.raises(ValueError, match="Scene .* not found"):
        mongodb_create_proposed_change(params)


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_invalid_story(
    mock_get_mongo: Mock,
    mock_get_neo4j: Mock,
    mock_mongodb_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test creating a proposed change with invalid story_id."""
    mock_get_mongo.return_value = mock_mongodb_client
    mock_get_neo4j.return_value = mock_neo4j_client

    # Mock story doesn't exist in Neo4j
    mock_neo4j_client.execute_read.return_value = []

    proposed_changes_collection = Mock()
    mock_mongodb_client.get_collection.return_value = proposed_changes_collection

    params = ProposedChangeCreate(
        story_id=uuid4(),
        change_type=ProposalType.FACT,
        content={"statement": "Test"},
        proposer="TestAgent",
    )

    with pytest.raises(ValueError, match="Story .* not found"):
        mongodb_create_proposed_change(params)


def test_create_proposed_change_no_scene_or_story():
    """Test that creating a proposal without scene_id or story_id fails validation."""
    with pytest.raises(
        ValueError, match="Either scene_id or story_id must be provided"
    ):
        ProposedChangeCreate(
            change_type=ProposalType.FACT,
            content={"statement": "Test"},
            proposer="TestAgent",
        )


# =============================================================================
# TESTS: mongodb_get_proposed_change
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_proposed_change_success(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test retrieving a proposed change by ID."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = proposed_change_doc

    proposal_id = UUID(proposed_change_doc["proposal_id"])
    result = mongodb_get_proposed_change(proposal_id)

    assert result is not None
    assert result.proposal_id == proposal_id
    assert result.change_type == ProposalType.FACT
    assert result.status == ProposalStatus.PENDING
    collection.find_one.assert_called_once_with({"proposal_id": str(proposal_id)})


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_proposed_change_not_found(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
):
    """Test retrieving a non-existent proposed change."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = None

    result = mongodb_get_proposed_change(uuid4())

    assert result is None


# =============================================================================
# TESTS: mongodb_list_proposed_changes
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_proposed_changes_by_scene(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test listing proposed changes filtered by scene_id."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value
    collection.count_documents.return_value = 1
    collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
        proposed_change_doc
    ]

    scene_id = UUID(proposed_change_doc["scene_id"])
    params = ProposedChangeFilter(scene_id=scene_id)
    result = mongodb_list_proposed_changes(params)

    assert result.total == 1
    assert len(result.proposed_changes) == 1
    assert result.proposed_changes[0].scene_id == scene_id
    collection.count_documents.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_proposed_changes_by_story(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    story_data: Dict[str, Any],
):
    """Test listing proposed changes filtered by story_id."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Create a story-level proposal doc
    story_proposal_doc = {
        "proposal_id": str(uuid4()),
        "scene_id": None,
        "story_id": story_data["id"],
        "turn_id": None,
        "change_type": ProposalType.EVENT.value,
        "content": {"description": "Test event"},
        "evidence": [],
        "confidence": 1.0,
        "authority": Authority.GM.value,
        "proposer": "Orchestrator",
        "status": ProposalStatus.PENDING.value,
        "decision_metadata": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    collection = mock_mongodb_client.get_collection.return_value
    collection.count_documents.return_value = 1
    collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
        story_proposal_doc
    ]

    story_id = UUID(story_data["id"])
    params = ProposedChangeFilter(story_id=story_id)
    result = mongodb_list_proposed_changes(params)

    assert result.total == 1
    assert len(result.proposed_changes) == 1
    assert result.proposed_changes[0].story_id == story_id
    # Verify filter was passed correctly
    call_args = collection.count_documents.call_args[0][0]
    assert call_args["story_id"] == str(story_id)
    collection.count_documents.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_proposed_changes_by_status(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test listing proposed changes filtered by status."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value
    collection.count_documents.return_value = 2
    collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
        proposed_change_doc,
        proposed_change_doc,
    ]

    params = ProposedChangeFilter(status=ProposalStatus.PENDING)
    result = mongodb_list_proposed_changes(params)

    assert result.total == 2
    assert len(result.proposed_changes) == 2
    # Verify filter was passed correctly
    call_args = collection.count_documents.call_args[0][0]
    assert call_args["status"] == ProposalStatus.PENDING.value


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_proposed_changes_by_change_type(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test listing proposed changes filtered by change_type."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value
    collection.count_documents.return_value = 1
    collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
        proposed_change_doc
    ]

    params = ProposedChangeFilter(change_type=ProposalType.FACT)
    result = mongodb_list_proposed_changes(params)

    assert result.total == 1
    # Verify filter was passed correctly
    call_args = collection.count_documents.call_args[0][0]
    assert call_args["change_type"] == ProposalType.FACT.value


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_proposed_changes_pagination(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test pagination in list_proposed_changes."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value
    collection.count_documents.return_value = 100

    # Create mock cursor
    mock_cursor = Mock()
    mock_sort = Mock()
    mock_skip = Mock()
    mock_limit = Mock()

    mock_cursor.sort = Mock(return_value=mock_sort)
    mock_sort.skip = Mock(return_value=mock_skip)
    mock_skip.limit = Mock(return_value=mock_limit)
    mock_limit.__iter__ = Mock(return_value=iter([proposed_change_doc]))

    collection.find.return_value = mock_cursor

    params = ProposedChangeFilter(limit=10, offset=20)
    result = mongodb_list_proposed_changes(params)

    assert result.total == 100
    assert result.limit == 10
    assert result.offset == 20
    mock_sort.skip.assert_called_once_with(20)
    mock_skip.limit.assert_called_once_with(10)


# =============================================================================
# TESTS: mongodb_update_proposed_change
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_proposed_change_accept(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test accepting a pending proposed change."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value

    # Mock find operations
    canonical_ref = uuid4()
    accepted_doc = proposed_change_doc.copy()
    accepted_doc["status"] = ProposalStatus.ACCEPTED.value
    accepted_doc["decision_metadata"] = {
        "decided_by": "CanonKeeper",
        "decided_at": datetime.now(timezone.utc),
        "reason": "Valid change",
        "canonical_ref": str(canonical_ref),
    }

    collection.find_one.side_effect = [
        proposed_change_doc,  # Initial find for validation
        accepted_doc,  # Find after update
    ]
    collection.update_one.return_value = Mock()

    decision = DecisionMetadata(
        decided_by="CanonKeeper",
        decided_at=datetime.now(timezone.utc),
        reason="Valid change",
        canonical_ref=canonical_ref,
    )
    params = ProposedChangeUpdate(
        status=ProposalStatus.ACCEPTED, decision_metadata=decision
    )

    proposal_id = UUID(proposed_change_doc["proposal_id"])
    result = mongodb_update_proposed_change(proposal_id, params)

    assert result.status == ProposalStatus.ACCEPTED
    assert result.decision_metadata is not None
    assert result.decision_metadata.decided_by == "CanonKeeper"
    assert result.decision_metadata.canonical_ref == canonical_ref
    collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_proposed_change_reject(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test rejecting a pending proposed change."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value

    rejected_doc = proposed_change_doc.copy()
    rejected_doc["status"] = ProposalStatus.REJECTED.value
    rejected_doc["decision_metadata"] = {
        "decided_by": "CanonKeeper",
        "decided_at": datetime.now(timezone.utc),
        "reason": "Conflicts with canon",
        "canonical_ref": None,
    }

    collection.find_one.side_effect = [
        proposed_change_doc,  # Initial find for validation
        rejected_doc,  # Find after update
    ]
    collection.update_one.return_value = Mock()

    decision = DecisionMetadata(
        decided_by="CanonKeeper",
        decided_at=datetime.now(timezone.utc),
        reason="Conflicts with canon",
    )
    params = ProposedChangeUpdate(
        status=ProposalStatus.REJECTED, decision_metadata=decision
    )

    proposal_id = UUID(proposed_change_doc["proposal_id"])
    result = mongodb_update_proposed_change(proposal_id, params)

    assert result.status == ProposalStatus.REJECTED
    assert result.decision_metadata is not None
    assert result.decision_metadata.reason == "Conflicts with canon"
    assert result.decision_metadata.canonical_ref is None
    collection.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_proposed_change_invalid_transition(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test invalid status transition (already accepted)."""
    mock_get_mongo.return_value = mock_mongodb_client

    # Mock an already accepted proposal
    accepted_doc = proposed_change_doc.copy()
    accepted_doc["status"] = ProposalStatus.ACCEPTED.value

    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = accepted_doc

    decision = DecisionMetadata(
        decided_by="CanonKeeper",
        decided_at=datetime.now(timezone.utc),
        reason="Test",
    )
    params = ProposedChangeUpdate(
        status=ProposalStatus.REJECTED, decision_metadata=decision
    )

    proposal_id = UUID(proposed_change_doc["proposal_id"])

    with pytest.raises(ValueError, match="Cannot update proposal with status accepted"):
        mongodb_update_proposed_change(proposal_id, params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_proposed_change_invalid_status(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
    proposed_change_doc: Dict[str, Any],
):
    """Test updating to pending (invalid - can only go to accepted/rejected)."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = proposed_change_doc

    decision = DecisionMetadata(
        decided_by="CanonKeeper",
        decided_at=datetime.now(timezone.utc),
        reason="Test",
    )
    params = ProposedChangeUpdate(
        status=ProposalStatus.PENDING, decision_metadata=decision
    )

    proposal_id = UUID(proposed_change_doc["proposal_id"])

    with pytest.raises(
        ValueError, match="Can only transition from pending to accepted or rejected"
    ):
        mongodb_update_proposed_change(proposal_id, params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_proposed_change_not_found(
    mock_get_mongo: Mock,
    mock_mongodb_client: Mock,
):
    """Test updating a non-existent proposed change."""
    mock_get_mongo.return_value = mock_mongodb_client

    collection = mock_mongodb_client.get_collection.return_value
    collection.find_one.return_value = None

    decision = DecisionMetadata(
        decided_by="CanonKeeper",
        decided_at=datetime.now(timezone.utc),
        reason="Test",
    )
    params = ProposedChangeUpdate(
        status=ProposalStatus.ACCEPTED, decision_metadata=decision
    )

    with pytest.raises(ValueError, match="Proposal .* not found"):
        mongodb_update_proposed_change(uuid4(), params)
