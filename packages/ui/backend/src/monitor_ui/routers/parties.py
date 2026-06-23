"""
Party router — group character management (P-13, DL-15).

LAYER: 3 (UI backend / FastAPI router)
IMPORTS FROM: monitor_data (Layer 1)
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from monitor_data.schemas.parties import PartyResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class PartyCreateRequest(BaseModel):
    """Simplified request body for creating a party via API."""

    story_id: str
    name: str = Field(min_length=1, max_length=200)
    initial_member_ids: list[str] = Field(default_factory=list)
    active_pc_id: str | None = None
    location_id: str | None = None


class AddMemberRequest(BaseModel):
    """Request body for adding a member to a party."""

    entity_id: str
    role: str | None = None
    position: int | None = None


@router.post("", response_model=PartyResponse, status_code=201)
async def create_party(body: PartyCreateRequest) -> PartyResponse:
    """Create a new party for a story (P-13)."""
    from monitor_data.schemas.parties import PartyCreate
    from monitor_data.tools.neo4j_tools.parties import neo4j_create_party

    try:
        params = PartyCreate(
            story_id=UUID(body.story_id),
            name=body.name,
            initial_member_ids=[UUID(mid) for mid in body.initial_member_ids],
            active_pc_id=UUID(body.active_pc_id) if body.active_pc_id else None,
            location_id=UUID(body.location_id) if body.location_id else None,
        )
        return neo4j_create_party(params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create party: {exc}") from exc


@router.get("", response_model=list[PartyResponse])
async def list_parties(
    story_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[PartyResponse]:
    """List parties, optionally filtered by story_id (P-13)."""
    from monitor_data.schemas.parties import PartyFilter
    from monitor_data.tools.neo4j_tools.parties import neo4j_list_parties

    try:
        params = PartyFilter(
            story_id=UUID(story_id) if story_id else None,
            limit=limit,
            offset=offset,
        )
        return neo4j_list_parties(params)
    except Exception as exc:
        logger.warning("list_parties failed: %s", exc)
        return []


@router.post("/{party_id}/members", response_model=PartyResponse)
async def add_member(party_id: str, body: AddMemberRequest) -> PartyResponse:
    """Add a character to a party (P-13)."""
    from monitor_data.schemas.parties import AddPartyMember
    from monitor_data.tools.neo4j_tools.parties import neo4j_add_party_member

    try:
        params = AddPartyMember(
            party_id=UUID(party_id),
            entity_id=UUID(body.entity_id),
            role=body.role,
            position=body.position,
        )
        return neo4j_add_party_member(params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to add member: {exc}") from exc


@router.delete("/{party_id}/members/{entity_id}", response_model=PartyResponse)
async def remove_member(party_id: str, entity_id: str) -> PartyResponse:
    """Remove a character from a party (P-13)."""
    from monitor_data.schemas.parties import RemovePartyMember
    from monitor_data.tools.neo4j_tools.parties import neo4j_remove_party_member

    try:
        params = RemovePartyMember(
            party_id=UUID(party_id),
            entity_id=UUID(entity_id),
        )
        return neo4j_remove_party_member(params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to remove member: {exc}") from exc


@router.post("/{party_id}/active-pc", response_model=PartyResponse)
async def set_active_pc(party_id: str, body: AddMemberRequest) -> PartyResponse:
    """Set the active PC for turn-based actions (P-13)."""
    from monitor_data.schemas.parties import SetActivePC
    from monitor_data.tools.neo4j_tools.parties import neo4j_set_active_pc

    try:
        params = SetActivePC(
            party_id=UUID(party_id),
            entity_id=UUID(body.entity_id),
        )
        return neo4j_set_active_pc(params)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid UUID: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to set active PC: {exc}") from exc