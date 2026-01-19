"""
Pydantic schemas for Party Inventory and Split operations (DL-16).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries (pydantic, uuid, datetime, enum) and base schemas
CALLED BY: mongodb_tools.py

These schemas define the data contracts for party inventory management and
party split tracking. Party inventory holds items owned collectively by the
party (not individual characters). Party splits track when a party temporarily
divides and later rejoins.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# ENUMS
# =============================================================================


class ItemCategory(str, Enum):
    """Item category classification for party inventory."""

    WEAPONS = "weapons"
    ARMOR = "armor"
    CONSUMABLES = "consumables"
    TREASURE = "treasure"
    QUEST_ITEMS = "quest_items"
    MISC = "misc"


class TransferSourceType(str, Enum):
    """Source type for inventory transfers."""

    PARTY = "party"
    CHARACTER = "character"


class TransferTargetType(str, Enum):
    """Target type for inventory transfers."""

    PARTY = "party"
    CHARACTER = "character"


class SplitStatus(str, Enum):
    """Status of a party split."""

    ACTIVE = "active"
    RESOLVED = "resolved"


# =============================================================================
# INVENTORY ITEM SCHEMAS
# =============================================================================


class InventoryItem(BaseModel):
    """A single item in the party inventory."""

    name: str = Field(min_length=1, max_length=200, description="Item name")
    quantity: int = Field(ge=1, description="Number of items")
    category: ItemCategory = Field(default=ItemCategory.MISC)
    value: Optional[int] = Field(
        None,
        ge=0,
        description="Item value in copper pieces (optional, for tracking wealth)",
    )
    notes: Optional[str] = Field(
        None, max_length=500, description="Notes about the item"
    )
    added_at: datetime = Field(description="When the item was added to inventory")


# =============================================================================
# PARTY INVENTORY CRUD SCHEMAS
# =============================================================================


class PartyInventoryCreate(BaseModel):
    """Request to create a party inventory."""

    party_id: UUID = Field(description="Party this inventory belongs to")
    initial_gold: int = Field(
        default=0, ge=0, description="Initial gold in copper pieces"
    )
    initial_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Initial items [{name, quantity, category?, value?, notes?}]",
    )


class PartyInventoryResponse(BaseModel):
    """Response with party inventory data."""

    inventory_id: UUID
    party_id: UUID
    gold: int = Field(description="Gold in copper pieces")
    items: List[InventoryItem]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# =============================================================================
# INVENTORY OPERATIONS
# =============================================================================


class AddInventoryItemRequest(BaseModel):
    """Request to add an item to party inventory."""

    party_id: UUID
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, default=1)
    category: Optional[ItemCategory] = Field(None)
    value: Optional[int] = Field(None, ge=0)
    notes: Optional[str] = Field(None, max_length=500)


class RemoveInventoryItemRequest(BaseModel):
    """Request to remove an item from party inventory."""

    party_id: UUID
    item_name: str = Field(min_length=1, max_length=200)
    quantity: Optional[int] = Field(
        None,
        ge=1,
        description="Quantity to remove (if None or >= current quantity, removes all)",
    )


class TransferItemRequest(BaseModel):
    """Request to transfer an item between party and character inventory."""

    from_type: TransferSourceType
    from_id: UUID = Field(
        description="party_id if from_type=party, entity_id if from_type=character"
    )
    to_type: TransferTargetType
    to_id: UUID = Field(
        description="party_id if to_type=party, entity_id if to_type=character"
    )
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, default=1)


class UpdateGoldRequest(BaseModel):
    """Request to update party gold."""

    party_id: UUID
    amount: int = Field(
        description="Amount to add (positive) or subtract (negative) in copper pieces"
    )
    reason: Optional[str] = Field(
        None, max_length=200, description="Reason for gold change"
    )


# =============================================================================
# PARTY SPLIT SCHEMAS
# =============================================================================


class SubParty(BaseModel):
    """A sub-party in a party split."""

    name: str = Field(
        min_length=1, max_length=100, description="Sub-party identifier (e.g., 'Alpha')"
    )
    member_ids: List[UUID] = Field(
        min_length=1, description="Entity IDs of characters in this sub-party"
    )
    location_id: Optional[UUID] = Field(
        None, description="Current location of this sub-party"
    )
    purpose: Optional[str] = Field(
        None, max_length=200, description="Purpose of this sub-party's mission"
    )


class PartySplitCreate(BaseModel):
    """Request to create a party split."""

    party_id: UUID = Field(description="Party being split")
    sub_parties: List[SubParty] = Field(
        min_length=2, description="At least 2 sub-parties required"
    )


class PartySplitResponse(BaseModel):
    """Response with party split data."""

    split_id: UUID
    party_id: UUID
    sub_parties: List[SubParty]
    status: SplitStatus
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ResolvePartySplitRequest(BaseModel):
    """Request to resolve a party split."""

    split_id: UUID
    resolution_notes: Optional[str] = Field(
        None, max_length=500, description="Notes about how the split was resolved"
    )


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class ActiveSplitsResponse(BaseModel):
    """Response with active splits for a party."""

    party_id: UUID
    splits: List[PartySplitResponse]


class SplitHistoryFilter(BaseModel):
    """Filter for split history query."""

    party_id: UUID
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SplitHistoryResponse(BaseModel):
    """Response with split history."""

    party_id: UUID
    splits: List[PartySplitResponse]
    total: int
    limit: int
    offset: int
