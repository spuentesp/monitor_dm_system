"""
Pydantic schemas for RandomTable operations.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime) and base schemas
CALLED BY: mongodb_tools.py

RandomTables are used by the GM to generate encounters, loot, names, weather,
rumors, and any other random content during play. They are created:
  - From ingested manuals (encounter tables, random NPC trait tables, etc.)
  - Manually by the user
  - Derived from entity templates

Tables support:
  - Simple flat probability (equal weight per entry)
  - Weighted entries (different probabilities per entry)
  - Subtable references (entries that roll on another table)
  - Conditional entries (only available if certain conditions are met)
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class RandomTableType(str, Enum):
    """Category of random table."""

    ENCOUNTER = "encounter"
    LOOT = "loot"
    NAME = "name"
    TRAIT = "trait"
    WEATHER = "weather"
    RUMOR = "rumor"
    NPC = "npc"
    EVENT = "event"
    LOCATION = "location"
    COMPLICATION = "complication"
    CUSTOM = "custom"


# =============================================================================
# TABLE ENTRY SCHEMAS
# =============================================================================


class RandomTableEntry(BaseModel):
    """A single entry in a random table."""

    min_roll: int = Field(description="Minimum roll that selects this entry")
    max_roll: int = Field(description="Maximum roll that selects this entry")
    weight: Optional[float] = Field(
        None, gt=0.0, description="Weight for weighted tables (overrides roll range)"
    )
    value: str = Field(min_length=1, max_length=1000, description="The result text")
    subtable_id: Optional[UUID] = Field(
        None, description="Roll on this subtable as part of the result"
    )
    conditions: Optional[Dict[str, Any]] = Field(
        None,
        description="Conditions that must be true for this entry to be available",
    )


# =============================================================================
# RANDOM TABLE CRUD SCHEMAS
# =============================================================================


class RandomTableCreate(BaseModel):
    """Request to create a RandomTable."""

    universe_id: Optional[UUID] = Field(
        None, description="If null, this is a global (system-wide) table"
    )
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    table_type: RandomTableType = Field(default=RandomTableType.CUSTOM)
    dice_formula: str = Field(
        min_length=1,
        max_length=50,
        description="Dice formula: '1d100', '2d6', '1d20', '1d8+2'",
    )
    weighted: bool = Field(
        default=False,
        description="If True, use weight field instead of roll range for probability",
    )
    entries: List[RandomTableEntry] = Field(
        min_length=1, description="Table entries (at least one required)"
    )
    source_id: Optional[UUID] = Field(
        None, description="Source document this table was extracted from"
    )
    game_system_id: Optional[UUID] = Field(
        None, description="Game system this table applies to (if system-specific)"
    )


class RandomTableUpdate(BaseModel):
    """Request to update a RandomTable."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    table_type: Optional[RandomTableType] = None
    dice_formula: Optional[str] = Field(None, min_length=1, max_length=50)
    weighted: Optional[bool] = None
    entries: Optional[List[RandomTableEntry]] = None


class RandomTableResponse(BaseModel):
    """Response with RandomTable data."""

    table_id: UUID
    universe_id: Optional[UUID] = None
    name: str
    description: str
    table_type: RandomTableType
    dice_formula: str
    weighted: bool
    entries: List[RandomTableEntry]
    source_id: Optional[UUID] = None
    game_system_id: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RandomTableFilter(BaseModel):
    """Filter for listing random tables."""

    universe_id: Optional[UUID] = None
    table_type: Optional[RandomTableType] = None
    game_system_id: Optional[UUID] = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class RandomTableListResponse(BaseModel):
    """Response for list operations."""

    tables: List[RandomTableResponse]
    total: int
    limit: int
    offset: int
