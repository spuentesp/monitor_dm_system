"""
Pydantic schemas for Universe and Multiverse operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Universe and Multiverse CRUD operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import Authority, CanonLevel


# =============================================================================
# MULTIVERSE SCHEMAS
# =============================================================================


class MultiverseCreate(BaseModel):
    """Request to create a Multiverse."""

    omniverse_id: UUID
    name: str = Field(min_length=1, max_length=200)
    system_name: str = Field(
        min_length=1, max_length=200, description="e.g., 'D&D 5e', 'Marvel 616'"
    )
    description: str = Field(min_length=1, max_length=2000)


class MultiverseUpdate(BaseModel):
    """Request to update a Multiverse."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    system_name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)


class MultiverseResponse(BaseModel):
    """Response with Multiverse data."""

    id: UUID
    omniverse_id: UUID
    name: str
    system_name: str
    description: str
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# UNIVERSE SCHEMAS
# =============================================================================


class UniverseCreate(BaseModel):
    """Request to create a Universe."""

    multiverse_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    genre: Optional[str] = Field(
        None, max_length=100, description="e.g., 'fantasy', 'sci-fi'"
    )
    tone: Optional[str] = Field(
        None, max_length=100, description="e.g., 'dark', 'heroic', 'comedic'"
    )
    tech_level: Optional[str] = Field(
        None, max_length=100, description="e.g., 'medieval', 'modern', 'futuristic'"
    )
    authority: Authority = Field(default=Authority.SYSTEM)
    canon_level: CanonLevel = Field(default=CanonLevel.CANON)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class UniverseUpdate(BaseModel):
    """Request to update a Universe.

    Only mutable fields can be updated: name, description, genre, tone, tech_level.
    Structural fields like multiverse_id and canon_level require special operations.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, min_length=1, max_length=2000)
    genre: Optional[str] = Field(None, max_length=100)
    tone: Optional[str] = Field(None, max_length=100)
    tech_level: Optional[str] = Field(None, max_length=100)


class UniverseResponse(BaseModel):
    """Response with Universe data."""

    id: UUID
    multiverse_id: UUID
    name: str
    description: str
    genre: Optional[str]
    tone: Optional[str]
    tech_level: Optional[str]
    canon_level: CanonLevel
    confidence: float
    authority: Authority
    created_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class UniverseFilter(BaseModel):
    """Filter parameters for listing universes."""

    multiverse_id: Optional[UUID] = None
    canon_level: Optional[CanonLevel] = None
    genre: Optional[str] = None
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
