"""
Unit tests for MongoDB ProposedChange operations.

Tests cover:
- mongodb_create_proposed_change
- mongodb_get_proposed_change
- mongodb_list_proposed_changes
- mongodb_update_proposed_change
"""

from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, timezone

import pytest

from monitor_data.schemas.proposed_changes import (
    ProposedChangeCreate,
    ProposedChangeUpdate,
    ProposedChangeFilter,
    EvidenceRef,
)
from monitor_data.schemas.base import Authority, ProposalStatus, ProposalType
from monitor_data.tools.mongodb_tools import (
    mongodb_create_proposed_change,
    mongodb_get_proposed_change,
    mongodb_list_proposed_changes,
    mongodb_update_proposed_change,
)


# =============================================================================
# TESTS: mongodb_create_proposed_change
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_fact(mock_get_client: Mock):
    """Test creating a proposed change for a fact."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    universe_id = uuid4()
    scene_id = uuid4()
    story_id = uuid4()

    params = ProposedChangeCreate(
        change_type=ProposalType.FACT,
        content={
            "statement": "The wizard cast a fireball",
            "entity_ids": [str(uuid4())],
        },
        scene_id=scene_id,
        story_id=story_id,
        universe_id=universe_id,
        confidence=0.9,
        authority=Authority.PLAYER,
        proposed_by="Narrator",
    )

    result = mongodb_create_proposed_change(params)

    # Assertions
    assert result.change_type == ProposalType.FACT
    assert result.content == params.content
    assert result.scene_id == scene_id
    assert result.story_id == story_id
    assert result.universe_id == universe_id
    assert result.confidence == 0.9
    assert result.authority == Authority.PLAYER
    assert result.proposed_by == "Narrator"
    assert result.status == ProposalStatus.PENDING
    assert result.decision_reason is None
    assert result.canonical_ref is None
    assert mock_collection.insert_one.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_entity(mock_get_client: Mock):
    """Test creating a proposed change for an entity."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    universe_id = uuid4()

    params = ProposedChangeCreate(
        change_type=ProposalType.ENTITY,
        content={
            "name": "Gandalf",
            "entity_type": "character",
            "properties": {"class": "wizard", "level": 20},
        },
        universe_id=universe_id,
        proposed_by="CanonKeeper",
    )

    result = mongodb_create_proposed_change(params)

    # Assertions
    assert result.change_type == ProposalType.ENTITY
    assert result.content["name"] == "Gandalf"
    assert result.universe_id == universe_id
    assert result.status == ProposalStatus.PENDING
    assert mock_collection.insert_one.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_relationship(mock_get_client: Mock):
    """Test creating a proposed change for a relationship."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    universe_id = uuid4()
    from_entity = uuid4()
    to_entity = uuid4()

    params = ProposedChangeCreate(
        change_type=ProposalType.RELATIONSHIP,
        content={
            "from": str(from_entity),
            "to": str(to_entity),
            "rel_type": "ALLY_OF",
            "properties": {"since": "2024-01-01"},
        },
        universe_id=universe_id,
        proposed_by="Narrator",
    )

    result = mongodb_create_proposed_change(params)

    # Assertions
    assert result.change_type == ProposalType.RELATIONSHIP
    assert result.content["rel_type"] == "ALLY_OF"
    assert result.status == ProposalStatus.PENDING
    assert mock_collection.insert_one.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_proposed_change_with_evidence(mock_get_client: Mock):
    """Test creating a proposed change with evidence references."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    universe_id = uuid4()
    turn_id = uuid4()
    source_id = uuid4()

    params = ProposedChangeCreate(
        change_type=ProposalType.FACT,
        content={"statement": "Test fact"},
        universe_id=universe_id,
        evidence_refs=[
            EvidenceRef(type="turn", ref_id=turn_id),
            EvidenceRef(type="source", ref_id=source_id),
        ],
        proposed_by="Narrator",
    )

    result = mongodb_create_proposed_change(params)

    # Assertions
    assert len(result.evidence_refs) == 2
    assert result.evidence_refs[0].type == "turn"
    assert result.evidence_refs[0].ref_id == turn_id
    assert result.evidence_refs[1].type == "source"
    assert result.evidence_refs[1].ref_id == source_id


# =============================================================================
# TESTS: mongodb_get_proposed_change
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_proposed_change_success(mock_get_client: Mock):
    """Test getting a proposed change by ID."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    proposal_id = uuid4()
    universe_id = uuid4()
    created_at = datetime.now(timezone.utc)

    mock_document = {
        "proposal_id": str(proposal_id),
        "change_type": ProposalType.FACT.value,
        "content": {"statement": "Test fact"},
        "scene_id": None,
        "story_id": None,
        "universe_id": str(universe_id),
        "turn_id": None,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "evidence_refs": [],
        "proposed_by": "System",
        "status": ProposalStatus.PENDING.value,
        "decision_reason": None,
        "canonical_ref": None,
        "decided_by": None,
        "created_at": created_at,
        "decided_at": None,
    }
    mock_collection.find_one.return_value = mock_document

    result = mongodb_get_proposed_change(proposal_id)

    # Assertions
    assert result is not None
    assert result.proposal_id == proposal_id
    assert result.change_type == ProposalType.FACT
    assert result.status == ProposalStatus.PENDING
    assert mock_collection.find_one.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_proposed_change_not_found(mock_get_client: Mock):
    """Test getting a non-existent proposed change."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    mock_collection.find_one.return_value = None

    result = mongodb_get_proposed_change(uuid4())

    # Assertions
    assert result is None


# =============================================================================
# TESTS: mongodb_list_proposed_changes
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_by_scene(mock_get_client: Mock):
    """Test listing proposed changes filtered by scene_id."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    scene_id = uuid4()
    universe_id = uuid4()
    created_at = datetime.now(timezone.utc)

    mock_documents = [
        {
            "proposal_id": str(uuid4()),
            "change_type": ProposalType.FACT.value,
            "content": {"statement": f"Fact {i}"},
            "scene_id": str(scene_id),
            "story_id": None,
            "universe_id": str(universe_id),
            "turn_id": None,
            "confidence": 1.0,
            "authority": Authority.SYSTEM.value,
            "evidence_refs": [],
            "proposed_by": "Narrator",
            "status": ProposalStatus.PENDING.value,
            "decision_reason": None,
            "canonical_ref": None,
            "decided_by": None,
            "created_at": created_at,
            "decided_at": None,
        }
        for i in range(3)
    ]

    mock_collection.count_documents.return_value = 3
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.__iter__.return_value = iter(mock_documents)
    mock_collection.find.return_value = mock_cursor

    filters = ProposedChangeFilter(scene_id=scene_id)
    result = mongodb_list_proposed_changes(filters)

    # Assertions
    assert len(result.proposals) == 3
    assert result.total == 3
    assert all(p.scene_id == scene_id for p in result.proposals)
    mock_collection.find.assert_called_once_with({"scene_id": str(scene_id)})


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_by_status(mock_get_client: Mock):
    """Test listing proposed changes filtered by status."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    universe_id = uuid4()
    created_at = datetime.now(timezone.utc)

    mock_documents = [
        {
            "proposal_id": str(uuid4()),
            "change_type": ProposalType.FACT.value,
            "content": {"statement": "Pending fact"},
            "scene_id": None,
            "story_id": None,
            "universe_id": str(universe_id),
            "turn_id": None,
            "confidence": 1.0,
            "authority": Authority.SYSTEM.value,
            "evidence_refs": [],
            "proposed_by": "Narrator",
            "status": ProposalStatus.PENDING.value,
            "decision_reason": None,
            "canonical_ref": None,
            "decided_by": None,
            "created_at": created_at,
            "decided_at": None,
        }
    ]

    mock_collection.count_documents.return_value = 1
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.__iter__.return_value = iter(mock_documents)
    mock_collection.find.return_value = mock_cursor

    filters = ProposedChangeFilter(status=ProposalStatus.PENDING)
    result = mongodb_list_proposed_changes(filters)

    # Assertions
    assert len(result.proposals) == 1
    assert result.proposals[0].status == ProposalStatus.PENDING
    mock_collection.find.assert_called_once_with({"status": ProposalStatus.PENDING.value})


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_list_by_change_type(mock_get_client: Mock):
    """Test listing proposed changes filtered by change_type."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    mock_collection.count_documents.return_value = 0
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.__iter__.return_value = iter([])
    mock_collection.find.return_value = mock_cursor

    filters = ProposedChangeFilter(change_type=ProposalType.ENTITY)
    result = mongodb_list_proposed_changes(filters)

    # Assertions
    assert len(result.proposals) == 0
    mock_collection.find.assert_called_once_with({"change_type": ProposalType.ENTITY.value})


# =============================================================================
# TESTS: mongodb_update_proposed_change
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_accept(mock_get_client: Mock):
    """Test accepting a pending proposal."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    proposal_id = uuid4()
    universe_id = uuid4()
    canonical_ref = uuid4()
    created_at = datetime.now(timezone.utc)
    decided_at = datetime.now(timezone.utc)

    # Mock updated document (accepted) returned by find_one_and_update
    updated_doc = {
        "proposal_id": str(proposal_id),
        "change_type": ProposalType.FACT.value,
        "content": {"statement": "Test fact"},
        "scene_id": None,
        "story_id": None,
        "universe_id": str(universe_id),
        "turn_id": None,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "evidence_refs": [],
        "proposed_by": "Narrator",
        "status": ProposalStatus.ACCEPTED.value,
        "decision_reason": "Valid fact",
        "canonical_ref": str(canonical_ref),
        "decided_by": "CanonKeeper",
        "created_at": created_at,
        "decided_at": decided_at,
    }

    # Mock find_one_and_update to return updated document
    mock_collection.find_one_and_update.return_value = updated_doc

    params = ProposedChangeUpdate(
        status=ProposalStatus.ACCEPTED,
        decision_reason="Valid fact",
        canonical_ref=canonical_ref,
        decided_by="CanonKeeper",
    )

    result = mongodb_update_proposed_change(proposal_id, params)

    # Assertions
    assert result.status == ProposalStatus.ACCEPTED
    assert result.decision_reason == "Valid fact"
    assert result.canonical_ref == canonical_ref
    assert result.decided_by == "CanonKeeper"
    assert mock_collection.find_one_and_update.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_reject(mock_get_client: Mock):
    """Test rejecting a pending proposal."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    proposal_id = uuid4()
    universe_id = uuid4()
    created_at = datetime.now(timezone.utc)
    decided_at = datetime.now(timezone.utc)

    # Mock updated document (rejected) returned by find_one_and_update
    updated_doc = {
        "proposal_id": str(proposal_id),
        "change_type": ProposalType.FACT.value,
        "content": {"statement": "Test fact"},
        "scene_id": None,
        "story_id": None,
        "universe_id": str(universe_id),
        "turn_id": None,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "evidence_refs": [],
        "proposed_by": "Narrator",
        "status": ProposalStatus.REJECTED.value,
        "decision_reason": "Contradicts existing canon",
        "canonical_ref": None,
        "decided_by": "CanonKeeper",
        "created_at": created_at,
        "decided_at": decided_at,
    }

    mock_collection.find_one_and_update.return_value = updated_doc

    params = ProposedChangeUpdate(
        status=ProposalStatus.REJECTED,
        decision_reason="Contradicts existing canon",
        decided_by="CanonKeeper",
    )

    result = mongodb_update_proposed_change(proposal_id, params)

    # Assertions
    assert result.status == ProposalStatus.REJECTED
    assert result.decision_reason == "Contradicts existing canon"
    assert result.canonical_ref is None
    assert mock_collection.find_one_and_update.call_count == 1


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_invalid_transition(mock_get_client: Mock):
    """Test invalid status transition (accepted → pending)."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    proposal_id = uuid4()
    universe_id = uuid4()
    created_at = datetime.now(timezone.utc)

    # Mock existing document (already accepted)
    existing_doc = {
        "proposal_id": str(proposal_id),
        "change_type": ProposalType.FACT.value,
        "content": {"statement": "Test fact"},
        "scene_id": None,
        "story_id": None,
        "universe_id": str(universe_id),
        "turn_id": None,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "evidence_refs": [],
        "proposed_by": "Narrator",
        "status": ProposalStatus.ACCEPTED.value,
        "decision_reason": "Already accepted",
        "canonical_ref": str(uuid4()),
        "decided_by": "CanonKeeper",
        "created_at": created_at,
        "decided_at": created_at,
    }

    # find_one_and_update returns None (no matching document with pending status)
    mock_collection.find_one_and_update.return_value = None
    # find_one returns the existing accepted document
    mock_collection.find_one.return_value = existing_doc

    params = ProposedChangeUpdate(
        status=ProposalStatus.REJECTED,
        decision_reason="Trying to change",
        decided_by="CanonKeeper",
    )

    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot update ProposedChange with status"):
        mongodb_update_proposed_change(proposal_id, params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_transition_to_pending_fails(mock_get_client: Mock):
    """Test that transitioning to pending status fails."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    proposal_id = uuid4()
    universe_id = uuid4()
    created_at = datetime.now(timezone.utc)

    # Mock existing document (pending)
    existing_doc = {
        "proposal_id": str(proposal_id),
        "change_type": ProposalType.FACT.value,
        "content": {"statement": "Test fact"},
        "scene_id": None,
        "story_id": None,
        "universe_id": str(universe_id),
        "turn_id": None,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "evidence_refs": [],
        "proposed_by": "Narrator",
        "status": ProposalStatus.PENDING.value,
        "decision_reason": None,
        "canonical_ref": None,
        "decided_by": None,
        "created_at": created_at,
        "decided_at": None,
    }

    mock_collection.find_one.return_value = existing_doc

    params = ProposedChangeUpdate(
        status=ProposalStatus.PENDING,
        decision_reason="Trying to set to pending",
        decided_by="CanonKeeper",
    )

    # Should raise ValueError
    with pytest.raises(ValueError, match="Cannot transition to 'pending'"):
        mongodb_update_proposed_change(proposal_id, params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_accept_without_canonical_ref_fails(mock_get_client: Mock):
    """Test that accepting without canonical_ref fails."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    proposal_id = uuid4()
    universe_id = uuid4()
    created_at = datetime.now(timezone.utc)

    # Mock existing document (pending)
    existing_doc = {
        "proposal_id": str(proposal_id),
        "change_type": ProposalType.FACT.value,
        "content": {"statement": "Test fact"},
        "scene_id": None,
        "story_id": None,
        "universe_id": str(universe_id),
        "turn_id": None,
        "confidence": 1.0,
        "authority": Authority.SYSTEM.value,
        "evidence_refs": [],
        "proposed_by": "Narrator",
        "status": ProposalStatus.PENDING.value,
        "decision_reason": None,
        "canonical_ref": None,
        "decided_by": None,
        "created_at": created_at,
        "decided_at": None,
    }

    mock_collection.find_one.return_value = existing_doc

    params = ProposedChangeUpdate(
        status=ProposalStatus.ACCEPTED,
        decision_reason="Valid fact",
        canonical_ref=None,  # Missing canonical_ref
        decided_by="CanonKeeper",
    )

    # Should raise ValueError
    with pytest.raises(ValueError, match="canonical_ref is required"):
        mongodb_update_proposed_change(proposal_id, params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_not_found(mock_get_client: Mock):
    """Test updating a non-existent proposed change."""
    # Setup mock
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.db = {"proposed_changes": mock_collection}
    mock_get_client.return_value = mock_client

    # find_one_and_update returns None (no document found)
    mock_collection.find_one_and_update.return_value = None
    # find_one also returns None (document doesn't exist)
    mock_collection.find_one.return_value = None

    params = ProposedChangeUpdate(
        status=ProposalStatus.ACCEPTED,
        canonical_ref=uuid4(),
        decided_by="CanonKeeper",
    )

    # Should raise ValueError
    with pytest.raises(ValueError, match="not found"):
        mongodb_update_proposed_change(uuid4(), params)
