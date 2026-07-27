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
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# =============================================================================
# ENUMS
# =============================================================================


class ItemCategory(StrEnum):
    """Item category classification for party inventory."""

    WEAPONS = "weapons"
    ARMOR = "armor"
    CONSUMABLES = "consumables"
    TREASURE = "treasure"
    QUEST_ITEMS = "quest_items"
    MISC = "misc"


class TransferSourceType(StrEnum):
    """Source type for inventory transfers."""

    PARTY = "party"
    CHARACTER = "character"


class TransferTargetType(StrEnum):
    """Target type for inventory transfers."""

    PARTY = "party"
    CHARACTER = "character"


class SplitStatus(StrEnum):
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
    value: int | None = Field(
        None,
        ge=0,
        description="Item value in copper pieces (optional, for tracking wealth)",
    )
    notes: str | None = Field(None, max_length=500, description="Notes about the item")
    added_at: datetime = Field(description="When the item was added to inventory")


# =============================================================================
# PARTY INVENTORY CRUD SCHEMAS
# =============================================================================


class PartyInventoryCreate(BaseModel):
    """Request to create a party inventory."""

    party_id: UUID = Field(description="Party this inventory belongs to")
    initial_gold: int = Field(default=0, ge=0, description="Initial gold in copper pieces")
    initial_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Initial items [{name, quantity, category?, value?, notes?}]",
    )


class PartyInventoryResponse(BaseModel):
    """Response with party inventory data."""

    inventory_id: UUID
    party_id: UUID
    gold: int = Field(description="Gold in copper pieces")
    items: list[InventoryItem]
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# =============================================================================
# INVENTORY OPERATIONS
# =============================================================================


class AddInventoryItemRequest(BaseModel):
    """Request to add an item to party inventory."""

    party_id: UUID
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, default=1)
    category: ItemCategory | None = Field(None)
    value: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=500)


class RemoveInventoryItemRequest(BaseModel):
    """Request to remove an item from party inventory."""

    party_id: UUID
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int | None = Field(
        None,
        ge=1,
        description="Quantity to remove (if None or >= current quantity, removes all)",
    )


class TransferItemRequest(BaseModel):
    """Request to transfer an item between party and character inventory."""

    from_type: TransferSourceType
    from_id: UUID = Field(description="party_id if from_type=party, entity_id if from_type=character")
    to_type: TransferTargetType
    to_id: UUID = Field(description="party_id if to_type=party, entity_id if to_type=character")
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, default=1)


class UpdateGoldRequest(BaseModel):
    """Request to update party gold."""

    party_id: UUID
    amount: int = Field(description="Amount to add (positive) or subtract (negative) in copper pieces")
    reason: str | None = Field(None, max_length=200, description="Reason for gold change")


# =============================================================================
# PARTY SPLIT SCHEMAS
# =============================================================================


class SubParty(BaseModel):
    """A sub-party in a party split."""

    name: str = Field(min_length=1, max_length=100, description="Sub-party identifier (e.g., 'Alpha')")
    member_ids: list[UUID] = Field(min_length=1, description="Entity IDs of characters in this sub-party")
    location_id: UUID | None = Field(None, description="Current location of this sub-party")
    purpose: str | None = Field(None, max_length=200, description="Purpose of this sub-party's mission")


class PartySplitCreate(BaseModel):
    """Request to create a party split."""

    party_id: UUID = Field(description="Party being split")
    sub_parties: list[SubParty] = Field(min_length=2, description="At least 2 sub-parties required")


class PartySplitResponse(BaseModel):
    """Response with party split data."""

    split_id: UUID
    party_id: UUID
    sub_parties: list[SubParty]
    status: SplitStatus
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_notes: str | None = None

    model_config = {"from_attributes": True}


class ResolvePartySplitRequest(BaseModel):
    """Request to resolve a party split."""

    split_id: UUID
    resolution_notes: str | None = Field(None, max_length=500, description="Notes about how the split was resolved")


# =============================================================================
# QUERY SCHEMAS
# =============================================================================


class ActiveSplitsResponse(BaseModel):
    """Response with active splits for a party."""

    party_id: UUID
    splits: list[PartySplitResponse]


class SplitHistoryFilter(BaseModel):
    """Filter for split history query."""

    party_id: UUID
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SplitHistoryResponse(BaseModel):
    """Response with split history."""

    party_id: UUID
    splits: list[PartySplitResponse]
    total: int
    limit: int
    offset: int


# =============================================================================
# CHARACTER INVENTORY SCHEMAS (DL-16 completion)
# =============================================================================


class CharacterInventoryCreate(BaseModel):
    """Request to create a character inventory."""

    entity_id: UUID = Field(description="Character entity this inventory belongs to")
    initial_gold: int = Field(default=0, ge=0, description="Initial gold in copper pieces")
    initial_items: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Initial items [{name, quantity, category?, value?, notes?}]",
    )


class CharacterInventoryResponse(BaseModel):
    """Response with character inventory data."""

    inventory_id: UUID
    entity_id: UUID
    gold: int = Field(description="Gold in copper pieces")
    items: list[InventoryItem]
    equipped: list[str] = Field(
        default_factory=list,
        description="Names of equipped items (subset of items list)",
    )
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class AddCharacterItemRequest(BaseModel):
    """Request to add an item to character inventory."""

    entity_id: UUID
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, default=1)
    category: ItemCategory | None = Field(None)
    value: int | None = Field(None, ge=0)
    notes: str | None = Field(None, max_length=500)
    equipped: bool = Field(default=False, description="Whether the item is immediately equipped")


class RemoveCharacterItemRequest(BaseModel):
    """Request to remove an item from character inventory."""

    entity_id: UUID
    item_name: str = Field(min_length=1, max_length=200)
    quantity: int | None = Field(
        None,
        ge=1,
        description="Quantity to remove (if None or >= current quantity, removes all)",
    )


class UpdateCharacterGoldRequest(BaseModel):
    """Request to update character gold."""

    entity_id: UUID
    amount: int = Field(description="Amount to add (positive) or subtract (negative) in copper pieces")
    reason: str | None = Field(None, max_length=200, description="Reason for gold change")


class EquipItemRequest(BaseModel):
    """Request to equip/unequip an item in character inventory."""

    entity_id: UUID
    item_name: str = Field(min_length=1, max_length=200)
    equipped: bool = Field(default=True, description="True to equip, False to unequip")
