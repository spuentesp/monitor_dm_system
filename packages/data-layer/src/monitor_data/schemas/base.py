"""
Base Pydantic schemas for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only

These schemas provide common fields and enums used across all data models.
"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CanonLevel(str, Enum):
    """Canon level for entities, facts, and events."""
    PROPOSED = "proposed"
    CANON = "canon"
    RETCONNED = "retconned"


class Authority(str, Enum):
    """Authority type for data provenance."""
    SOURCE = "source"
    GM = "gm"
    PLAYER = "player"
    SYSTEM = "system"


class BaseNodeSchema(BaseModel):
    """Base schema for all Neo4j nodes."""
    id: UUID = Field(..., description="Unique identifier")
    created_at: datetime = Field(..., description="Creation timestamp")


class BaseCreateSchema(BaseModel):
    """Base schema for create operations."""
    pass


class BaseUpdateSchema(BaseModel):
    """Base schema for update operations."""
    pass


class BaseResponseSchema(BaseModel):
    """Base schema for response operations."""
    id: UUID = Field(..., description="Unique identifier")
    created_at: datetime = Field(..., description="Creation timestamp")


class ErrorResponse(BaseModel):
    """Standard error response schema."""
    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code")
    details: Optional[dict] = Field(None, description="Additional error details")
