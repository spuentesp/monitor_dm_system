"""
Pydantic schemas for Axiom operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: neo4j_tools.py

These schemas define the data contracts for Axiom CRUD operations.
Axioms represent foundational world rules and constraints tied to universes.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from monitor_data.schemas.base import AxiomAuthority, AxiomDomain, CanonLevel


# =============================================================================
# AXIOM SCHEMAS
# =============================================================================


class AxiomCreate(BaseModel):
    """Request to create an Axiom."""

    universe_id: UUID
    statement: str = Field(
        min_length=1, max_length=2000, description="The axiom statement"
    )
    domain: AxiomDomain = Field(
        default=AxiomDomain.PHYSICS,
        description="Domain of the axiom (physics, magic, society, metaphysics)",
    )

    # Provenance references
    source_ids: Optional[List[UUID]] = Field(
        default=None, description="Source IDs supporting this axiom"
    )
    snippet_ids: Optional[List[str]] = Field(
        default=None,
        description="Snippet IDs from MongoDB (stored for reference only, not as Neo4j edges)",
    )

    # Canonization metadata
    canon_level: CanonLevel = Field(default=CanonLevel.CANON)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    authority: AxiomAuthority = Field(default=AxiomAuthority.SYSTEM)


class AxiomUpdate(BaseModel):
    """Request to update an Axiom.

    Only mutable fields can be updated: statement, canon_level, confidence.
    Structural fields like universe_id and domain require creating a new axiom.
    """

    statement: Optional[str] = Field(None, min_length=1, max_length=2000)
    canon_level: Optional[CanonLevel] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class AxiomResponse(BaseModel):
    """Response with Axiom data including provenance."""

    id: UUID
    universe_id: UUID
    statement: str
    domain: AxiomDomain
    canon_level: CanonLevel
    confidence: float
    authority: AxiomAuthority
    created_at: datetime

    # Provenance data (populated by get operations)
    source_ids: List[UUID] = Field(
        default_factory=list, description="Neo4j Source UUIDs linked via SUPPORTED_BY"
    )
    snippet_ids: List[str] = Field(
        default_factory=list, 
        description="MongoDB Snippet IDs (stored in axiom metadata, not as Neo4j edges)"
    )

    model_config = {"from_attributes": True}


class AxiomFilter(BaseModel):
    """Filter parameters for listing axioms."""

    universe_id: Optional[UUID] = None
    domain: Optional[AxiomDomain] = None
    canon_level: Optional[CanonLevel] = None
    confidence_min: Optional[float] = Field(None, ge=0.0, le=1.0)
    confidence_max: Optional[float] = Field(None, ge=0.0, le=1.0)
    limit: int = Field(default=30, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
