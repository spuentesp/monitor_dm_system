"""
Universe Pydantic schemas for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only

Schemas for Multiverse and Universe nodes in Neo4j.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import (
    Authority,
    BaseCreateSchema,
    BaseResponseSchema,
    BaseUpdateSchema,
    CanonLevel,
)


# ============================================================================
# Multiverse Schemas
# ============================================================================


class MultiverseCreate(BaseCreateSchema):
    """Schema for creating a Multiverse."""
    omniverse_id: UUID = Field(..., description="ID of parent Omniverse")
    name: str = Field(..., min_length=1, max_length=255, description="Multiverse name")
    system_name: str = Field(
        ..., min_length=1, max_length=255, description="System name (e.g., 'D&D 5e', 'Marvel 616')"
    )
    description: str = Field(..., min_length=1, description="Multiverse description")


class MultiverseUpdate(BaseUpdateSchema):
    """Schema for updating a Multiverse."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Multiverse name")
    system_name: Optional[str] = Field(
        None, min_length=1, max_length=255, description="System name"
    )
    description: Optional[str] = Field(None, min_length=1, description="Multiverse description")


class MultiverseResponse(BaseResponseSchema):
    """Schema for Multiverse response."""
    omniverse_id: UUID = Field(..., description="ID of parent Omniverse")
    name: str = Field(..., description="Multiverse name")
    system_name: str = Field(..., description="System name")
    description: str = Field(..., description="Multiverse description")


# ============================================================================
# Universe Schemas
# ============================================================================


class UniverseCreate(BaseCreateSchema):
    """Schema for creating a Universe."""
    multiverse_id: UUID = Field(..., description="ID of parent Multiverse")
    name: str = Field(..., min_length=1, max_length=255, description="Universe name")
    description: str = Field(..., min_length=1, description="Universe description")
    genre: Optional[str] = Field(None, max_length=100, description="Genre tag (e.g., 'fantasy', 'sci-fi')")
    tone: Optional[str] = Field(None, max_length=100, description="Tone tag (e.g., 'dark', 'heroic')")
    tech_level: Optional[str] = Field(
        None, max_length=100, description="Technology level (e.g., 'medieval', 'futuristic')"
    )
    authority: Authority = Field(default=Authority.SYSTEM, description="Authority type")


class UniverseUpdate(BaseUpdateSchema):
    """Schema for updating a Universe."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Universe name")
    description: Optional[str] = Field(None, min_length=1, description="Universe description")
    genre: Optional[str] = Field(None, max_length=100, description="Genre tag")
    tone: Optional[str] = Field(None, max_length=100, description="Tone tag")
    tech_level: Optional[str] = Field(None, max_length=100, description="Technology level")


class UniverseResponse(BaseResponseSchema):
    """Schema for Universe response."""
    multiverse_id: UUID = Field(..., description="ID of parent Multiverse")
    name: str = Field(..., description="Universe name")
    description: str = Field(..., description="Universe description")
    genre: Optional[str] = Field(None, description="Genre tag")
    tone: Optional[str] = Field(None, description="Tone tag")
    tech_level: Optional[str] = Field(None, description="Technology level")
    canon_level: CanonLevel = Field(default=CanonLevel.CANON, description="Canon level")
    authority: Authority = Field(..., description="Authority type")


# ============================================================================
# List/Query Schemas
# ============================================================================


class ListUniversesRequest(BaseModel):
    """Schema for listing universes."""
    multiverse_id: Optional[UUID] = Field(None, description="Filter by Multiverse ID")
    canon_level: Optional[CanonLevel] = Field(None, description="Filter by canon level")
    limit: int = Field(default=50, ge=1, le=1000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Offset for pagination")


class ListUniversesResponse(BaseModel):
    """Schema for list universes response."""
    universes: list[UniverseResponse] = Field(..., description="List of universes")
    total: int = Field(..., ge=0, description="Total count of matching universes")
