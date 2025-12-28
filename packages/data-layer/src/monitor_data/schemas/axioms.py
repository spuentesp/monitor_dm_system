"""
Pydantic schemas for Axiom operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Axiom CRUD operations.
Axioms represent foundational world rules and constraints tied to universes.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field

from monitor_data.schemas.base import AxiomAuthority, CanonLevel


# =============================================================================
# ENUMS
# =============================================================================


class AxiomDomain(str, Enum):
    """Domain classification for axioms."""

    PHYSICS = "physics"
    MAGIC = "magic"
    SOCIETY = "society"
    METAPHYSICS = "metaphysics"


# =============================================================================
# AXIOM SCHEMAS
# =============================================================================


class AxiomCreate(BaseModel):
    """Request to create an Axiom."""

    universe_id: UUID
    statement: str = Field(
        min_length=1,
        max_length=2000,
        description="Foundational world rule (e.g., 'magic requires verbal components')",
    )
    domain: AxiomDomain
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        default=1.0,
        description="Confidence level in this axiom's truth",
    )
    authority: AxiomAuthority = Field(default=AxiomAuthority.SYSTEM)
    canon_level: CanonLevel = Field(default=CanonLevel.CANON)
    source_ids: List[UUID] = Field(
        default_factory=list,
        description="UUIDs of Source nodes that support this axiom (creates SUPPORTED_BY edges)",
    )


class AxiomUpdate(BaseModel):
    """Request to update an Axiom.

    Only mutable fields can be updated: statement, confidence, canon_level.
    """

    statement: Optional[str] = Field(None, min_length=1, max_length=2000)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    canon_level: Optional[CanonLevel] = None


class AxiomResponse(BaseModel):
    """Response with Axiom data."""

    id: UUID
    universe_id: UUID
    statement: str
    domain: AxiomDomain
    confidence: float
    canon_level: CanonLevel
    authority: AxiomAuthority
    created_at: datetime
    # Optional provenance chain (populated by neo4j_get_axiom with provenance)
    sources: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Source nodes that support this axiom (from SUPPORTED_BY edges)",
    )

    model_config = {"from_attributes": True}


class AxiomFilter(BaseModel):
    """Filter parameters for listing axioms."""

    universe_id: Optional[UUID] = None
    domain: Optional[AxiomDomain] = None
    canon_level: Optional[CanonLevel] = None
    confidence_min: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence_max: Optional[float] = Field(None, ge=0.0, le=1.0)
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    sort_by: str = Field(
        default="created_at", description="Field to sort by: created_at, confidence"
    )
    sort_order: str = Field(
        default="desc", description="Sort order: asc, desc", pattern="^(asc|desc)$"
    )


class AxiomListResponse(BaseModel):
    """Response with list of axioms and pagination info."""

    axioms: List[AxiomResponse]
    total: int
    limit: int
    offset: int
