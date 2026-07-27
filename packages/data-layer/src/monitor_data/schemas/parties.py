"""
Pydantic schemas for Party operations (DL-15).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Party CRUD operations.
Parties represent groups of player characters acting together in a story.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import PartyStatus

# =============================================================================
# PARTY MEMBER SCHEMAS
# =============================================================================


class PartyMemberInfo(BaseModel):
    """Information about a party member."""

    entity_id: UUID
    role: str | None = Field(None, max_length=50, description="e.g., 'leader', 'scout', 'healer'")
    position: int | None = Field(None, ge=0, description="Position in marching order (0-based)")
    joined_at: datetime


# =============================================================================
# PARTY CRUD SCHEMAS
# =============================================================================


class PartyCreate(BaseModel):
    """Request to create a Party."""

    story_id: UUID
    name: str = Field(min_length=1, max_length=200, description="Party name")
    status: PartyStatus = Field(default=PartyStatus.TRAVELING)
    initial_member_ids: list[UUID] = Field(
        default_factory=list, description="Initial party members (EntityInstance IDs)"
    )
    active_pc_id: UUID | None = Field(None, description="Currently active PC for turn-based actions")
    location_id: UUID | None = Field(None, description="Current location (EntityInstance of type location)")
    formation: list[UUID] = Field(
        default_factory=list,
        description="Ordered list of entity_ids for marching order",
    )


class PartyUpdate(BaseModel):
    """Request to update a Party."""

    name: str | None = Field(None, min_length=1, max_length=200)
    status: PartyStatus | None = None
    location_id: UUID | None = None
    formation: list[UUID] | None = None


class PartyResponse(BaseModel):
    """Response with Party data."""

    id: UUID
    story_id: UUID
    name: str
    status: PartyStatus
    active_pc_id: UUID | None = None
    location_id: UUID | None = None
    formation: list[UUID]
    members: list[PartyMemberInfo] = Field(default_factory=list, description="Current party members")
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# PARTY MEMBER OPERATIONS
# =============================================================================


class AddPartyMember(BaseModel):
    """Request to add a member to a party."""

    party_id: UUID
    entity_id: UUID
    role: str | None = Field(None, max_length=50)
    position: int | None = Field(None, ge=0)


class RemovePartyMember(BaseModel):
    """Request to remove a member from a party."""

    party_id: UUID
    entity_id: UUID


class SetActivePC(BaseModel):
    """Request to set the active PC."""

    party_id: UUID
    entity_id: UUID


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class PartyFilter(BaseModel):
    """Filter parameters for listing parties."""

    story_id: UUID | None = None
    status: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
