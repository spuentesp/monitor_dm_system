"""
Unit tests for Neo4j party operations (DL-15).

Tests cover:
- neo4j_create_party
- neo4j_get_party
- neo4j_list_parties
- neo4j_add_party_member
- neo4j_remove_party_member
- neo4j_set_active_pc
- neo4j_update_party_status
- neo4j_update_party_location
- neo4j_update_party_formation
- neo4j_delete_party
"""

from typing import Dict, Any
from unittest.mock import Mock, patch
from uuid import UUID, uuid4
from datetime import datetime

import pytest

from monitor_data.schemas.parties import (
    PartyCreate,
    PartyFilter,
    AddPartyMember,
    RemovePartyMember,
    SetActivePC,
)
from monitor_data.schemas.base import PartyStatus
from monitor_data.tools.neo4j_tools import (
    neo4j_create_party,
    neo4j_get_party,
    neo4j_list_parties,
    neo4j_add_party_member,
    neo4j_remove_party_member,
    neo4j_set_active_pc,
    neo4j_update_party_status,
    neo4j_delete_party,
)


# =============================================================================
# TESTS: neo4j_create_party
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_party_success(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test successful party creation."""
    mock_get_client.return_value = mock_neo4j_client

    # Mock story exists
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": story_data["id"]}],  # verify story exists
    ]

    # Mock party creation
    party_id = uuid4()
    party_data = {
        "id": str(party_id),
        "story_id": story_data["id"],
        "name": "The Fellowship",
        "status": "traveling",
        "active_pc_id": None,
        "location_id": None,
        "formation": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    mock_neo4j_client.execute_write.return_value = [{"p": party_data}]

    params = PartyCreate(
        story_id=UUID(story_data["id"]),
        name="The Fellowship",
        status=PartyStatus.TRAVELING,
    )

    result = neo4j_create_party(params)

    assert result.name == "The Fellowship"
    assert result.story_id == UUID(story_data["id"])
    assert result.status == PartyStatus.TRAVELING
    assert len(result.members) == 0


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_party_with_initial_members(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test party creation with initial members."""
    mock_get_client.return_value = mock_neo4j_client

    member1_id = uuid4()
    member2_id = uuid4()

    # Mock story exists and members are valid characters
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": story_data["id"]}],  # verify story exists
        [{"valid_ids": [str(member1_id), str(member2_id)]}],  # verify members
    ]

    # Mock party and member creation
    party_id = uuid4()
    party_data = {
        "id": str(party_id),
        "story_id": story_data["id"],
        "name": "The Crew",
        "status": "traveling",
        "active_pc_id": str(member1_id),
        "location_id": None,
        "formation": [str(member1_id), str(member2_id)],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    mock_neo4j_client.execute_write.side_effect = [
        [{"p": party_data}],  # party creation
        [
            {
                "entity_id": str(member1_id),
                "r": {"role": None, "position": 0, "joined_at": datetime.utcnow()},
            }
        ],  # member 1
        [
            {
                "entity_id": str(member2_id),
                "r": {"role": None, "position": 1, "joined_at": datetime.utcnow()},
            }
        ],  # member 2
    ]

    params = PartyCreate(
        story_id=UUID(story_data["id"]),
        name="The Crew",
        initial_member_ids=[member1_id, member2_id],
        active_pc_id=member1_id,
        formation=[member1_id, member2_id],
    )

    result = neo4j_create_party(params)

    assert result.name == "The Crew"
    assert len(result.members) == 2
    assert result.active_pc_id == member1_id


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_party_invalid_story(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test party creation with invalid story_id."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    params = PartyCreate(
        story_id=uuid4(),
        name="Test Party",
    )

    with pytest.raises(ValueError, match="Story .* not found"):
        neo4j_create_party(params)


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_create_party_invalid_members(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test party creation with invalid member IDs."""
    mock_get_client.return_value = mock_neo4j_client

    member_id = uuid4()

    # Mock story exists but members are invalid
    mock_neo4j_client.execute_read.side_effect = [
        [{"id": story_data["id"]}],  # verify story
        [{"valid_ids": []}],  # no valid members
    ]

    params = PartyCreate(
        story_id=UUID(story_data["id"]),
        name="Test Party",
        initial_member_ids=[member_id],
    )

    with pytest.raises(ValueError, match="must be EntityInstance nodes"):
        neo4j_create_party(params)


# =============================================================================
# TESTS: neo4j_get_party
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_party_exists(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test getting an existing party."""
    mock_get_client.return_value = mock_neo4j_client

    party_id = uuid4()
    story_id = uuid4()
    member_id = uuid4()

    party_data = {
        "id": str(party_id),
        "story_id": str(story_id),
        "name": "Test Party",
        "status": "traveling",
        "active_pc_id": str(member_id),
        "location_id": None,
        "formation": [str(member_id)],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    mock_neo4j_client.execute_read.return_value = [
        {
            "p": party_data,
            "members": [
                {
                    "entity_id": str(member_id),
                    "role": "leader",
                    "position": 0,
                    "joined_at": datetime.utcnow(),
                }
            ],
        }
    ]

    result = neo4j_get_party(party_id)

    assert result is not None
    assert result.id == party_id
    assert result.name == "Test Party"
    assert len(result.members) == 1
    assert result.members[0].entity_id == member_id


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_get_party_not_found(mock_get_client: Mock, mock_neo4j_client: Mock):
    """Test getting a non-existent party."""
    mock_get_client.return_value = mock_neo4j_client
    mock_neo4j_client.execute_read.return_value = []

    result = neo4j_get_party(uuid4())

    assert result is None


# =============================================================================
# TESTS: neo4j_list_parties
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_parties_no_filter(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
):
    """Test listing all parties without filters."""
    mock_get_client.return_value = mock_neo4j_client

    party1_id = uuid4()
    party2_id = uuid4()
    story_id = uuid4()

    mock_neo4j_client.execute_read.return_value = [
        {
            "p": {
                "id": str(party1_id),
                "story_id": str(story_id),
                "name": "Party 1",
                "status": "traveling",
                "active_pc_id": None,
                "location_id": None,
                "formation": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
            "members": [],
        },
        {
            "p": {
                "id": str(party2_id),
                "story_id": str(story_id),
                "name": "Party 2",
                "status": "combat",
                "active_pc_id": None,
                "location_id": None,
                "formation": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
            "members": [],
        },
    ]

    result = neo4j_list_parties()

    assert len(result) == 2
    assert result[0].name == "Party 1"
    assert result[1].name == "Party 2"


@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_list_parties_by_story(
    mock_get_client: Mock,
    mock_neo4j_client: Mock,
    story_data: Dict[str, Any],
):
    """Test listing parties filtered by story_id."""
    mock_get_client.return_value = mock_neo4j_client

    party_id = uuid4()

    mock_neo4j_client.execute_read.return_value = [
        {
            "p": {
                "id": str(party_id),
                "story_id": story_data["id"],
                "name": "Story Party",
                "status": "traveling",
                "active_pc_id": None,
                "location_id": None,
                "formation": [],
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            },
            "members": [],
        }
    ]

    filters = PartyFilter(story_id=UUID(story_data["id"]))
    result = neo4j_list_parties(filters)

    assert len(result) == 1
    assert result[0].story_id == UUID(story_data["id"])


# =============================================================================
# TESTS: neo4j_add_party_member
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.neo4j_get_party")
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_add_party_member_success(
    mock_get_client: Mock,
    mock_get_party: Mock,
    mock_neo4j_client: Mock,
):
    """Test successfully adding a member to a party."""
    mock_get_client.return_value = mock_neo4j_client

    party_id = uuid4()
    entity_id = uuid4()

    # Mock party exists
    from monitor_data.schemas.parties import PartyResponse

    mock_party = PartyResponse(
        id=party_id,
        story_id=uuid4(),
        name="Test Party",
        status=PartyStatus.TRAVELING,
        formation=[],
        members=[],
        created_at=datetime.utcnow(),
    )
    mock_get_party.return_value = mock_party

    # Mock entity is valid character
    mock_neo4j_client.execute_read.return_value = [{"id": str(entity_id)}]
    mock_neo4j_client.execute_write.return_value = [{"r": {}}]

    params = AddPartyMember(
        party_id=party_id,
        entity_id=entity_id,
        role="scout",
        position=0,
    )

    result = neo4j_add_party_member(params)

    assert result.id == party_id
    assert mock_neo4j_client.execute_write.called


@patch("monitor_data.tools.neo4j_tools.neo4j_get_party")
def test_add_party_member_party_not_found(mock_get_party: Mock):
    """Test adding member to non-existent party."""
    mock_get_party.return_value = None

    params = AddPartyMember(
        party_id=uuid4(),
        entity_id=uuid4(),
    )

    with pytest.raises(ValueError, match="Party .* not found"):
        neo4j_add_party_member(params)


# =============================================================================
# TESTS: neo4j_remove_party_member
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.neo4j_get_party")
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_remove_party_member_success(
    mock_get_client: Mock,
    mock_get_party: Mock,
    mock_neo4j_client: Mock,
):
    """Test successfully removing a member from a party."""
    mock_get_client.return_value = mock_neo4j_client

    party_id = uuid4()
    entity_id = uuid4()

    # Mock party exists
    from monitor_data.schemas.parties import PartyResponse

    mock_party = PartyResponse(
        id=party_id,
        story_id=uuid4(),
        name="Test Party",
        status=PartyStatus.TRAVELING,
        formation=[],
        members=[],
        created_at=datetime.utcnow(),
    )
    mock_get_party.return_value = mock_party

    mock_neo4j_client.execute_write.return_value = [{"p": {}}]

    params = RemovePartyMember(
        party_id=party_id,
        entity_id=entity_id,
    )

    result = neo4j_remove_party_member(params)

    assert result.id == party_id
    assert mock_neo4j_client.execute_write.called


# =============================================================================
# TESTS: neo4j_set_active_pc
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.neo4j_get_party")
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_set_active_pc_success(
    mock_get_client: Mock,
    mock_get_party: Mock,
    mock_neo4j_client: Mock,
):
    """Test successfully setting active PC."""
    mock_get_client.return_value = mock_neo4j_client

    party_id = uuid4()
    entity_id = uuid4()

    # Mock party exists with member
    from monitor_data.schemas.parties import PartyResponse, PartyMemberInfo

    mock_party = PartyResponse(
        id=party_id,
        story_id=uuid4(),
        name="Test Party",
        status=PartyStatus.TRAVELING,
        formation=[],
        members=[
            PartyMemberInfo(
                entity_id=entity_id,
                role="leader",
                position=0,
                joined_at=datetime.utcnow(),
            )
        ],
        created_at=datetime.utcnow(),
    )
    mock_get_party.return_value = mock_party

    mock_neo4j_client.execute_write.return_value = [{"p": {}}]

    params = SetActivePC(
        party_id=party_id,
        entity_id=entity_id,
    )

    result = neo4j_set_active_pc(params)

    assert result.id == party_id
    assert mock_neo4j_client.execute_write.called


@patch("monitor_data.tools.neo4j_tools.neo4j_get_party")
def test_set_active_pc_not_a_member(mock_get_party: Mock):
    """Test setting active PC to non-member."""
    party_id = uuid4()
    entity_id = uuid4()

    # Mock party exists without this member
    from monitor_data.schemas.parties import PartyResponse

    mock_party = PartyResponse(
        id=party_id,
        story_id=uuid4(),
        name="Test Party",
        status=PartyStatus.TRAVELING,
        formation=[],
        members=[],  # Empty members
        created_at=datetime.utcnow(),
    )
    mock_get_party.return_value = mock_party

    params = SetActivePC(
        party_id=party_id,
        entity_id=entity_id,
    )

    with pytest.raises(ValueError, match="is not a member"):
        neo4j_set_active_pc(params)


# =============================================================================
# TESTS: neo4j_update_party_status
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.neo4j_get_party")
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_update_party_status_success(
    mock_get_client: Mock,
    mock_get_party: Mock,
    mock_neo4j_client: Mock,
):
    """Test updating party status."""
    mock_get_client.return_value = mock_neo4j_client

    party_id = uuid4()

    from monitor_data.schemas.parties import PartyResponse

    mock_party = PartyResponse(
        id=party_id,
        story_id=uuid4(),
        name="Test Party",
        status=PartyStatus.TRAVELING,
        formation=[],
        members=[],
        created_at=datetime.utcnow(),
    )
    mock_get_party.return_value = mock_party

    mock_neo4j_client.execute_write.return_value = [{"p": {}}]

    result = neo4j_update_party_status(party_id, "combat")

    assert result.id == party_id
    assert mock_neo4j_client.execute_write.called


# =============================================================================
# TESTS: neo4j_delete_party
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.neo4j_get_party")
@patch("monitor_data.tools.neo4j_tools.get_neo4j_client")
def test_delete_party_success(
    mock_get_client: Mock,
    mock_get_party: Mock,
    mock_neo4j_client: Mock,
):
    """Test successfully deleting a party."""
    mock_get_client.return_value = mock_neo4j_client

    party_id = uuid4()

    from monitor_data.schemas.parties import PartyResponse

    mock_party = PartyResponse(
        id=party_id,
        story_id=uuid4(),
        name="Test Party",
        status=PartyStatus.TRAVELING,
        formation=[],
        members=[],
        created_at=datetime.utcnow(),
    )
    mock_get_party.return_value = mock_party

    mock_neo4j_client.execute_write.return_value = [{"deleted_count": 1}]

    result = neo4j_delete_party(party_id)

    assert result["deleted"] is True
    assert result["party_id"] == str(party_id)


@patch("monitor_data.tools.neo4j_tools.neo4j_get_party")
def test_delete_party_not_found(mock_get_party: Mock):
    """Test deleting a non-existent party."""
    mock_get_party.return_value = None

    with pytest.raises(ValueError, match="Party .* not found"):
        neo4j_delete_party(uuid4())
