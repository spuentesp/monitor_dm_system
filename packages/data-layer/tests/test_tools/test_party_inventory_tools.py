"""
Tests for Party Inventory MongoDB tools (DL-16).

Tests all party inventory CRUD operations, item management,
gold tracking, party splits, and split history.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_data.schemas.party_inventory import (
    ItemCategory,
    SplitStatus,
    InventoryItem,
    PartyInventoryCreate,
    PartyInventoryResponse,
    AddInventoryItemRequest,
    RemoveInventoryItemRequest,
    TransferItemRequest,
    TransferSourceType,
    TransferTargetType,
    UpdateGoldRequest,
    SubParty,
    PartySplitCreate,
    ResolvePartySplitRequest,
    SplitHistoryFilter,
)
from monitor_data.tools.mongodb_tools import (
    mongodb_create_party_inventory,
    mongodb_get_party_inventory,
    mongodb_add_inventory_item,
    mongodb_remove_inventory_item,
    mongodb_update_party_gold,
    mongodb_transfer_item,
    mongodb_create_party_split,
    mongodb_get_active_splits,
    mongodb_resolve_party_split,
    mongodb_get_split_history,
)


# =============================================================================
# TEST: mongodb_create_party_inventory
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_inventory_success(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating a party inventory."""
    party_id = uuid4()
    inventory_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories
    mock_inventories.find_one.return_value = None  # No existing inventory

    # Mock Neo4j
    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = [{"id": str(party_id)}]

    params = PartyInventoryCreate(
        party_id=party_id,
        initial_gold=100,
        initial_items=[],
    )

    with patch("monitor_data.tools.mongodb_tools.uuid4", return_value=inventory_id):
        result = mongodb_create_party_inventory(params)

    assert result.inventory_id == inventory_id
    assert result.party_id == party_id
    assert result.gold == 100
    assert len(result.items) == 0
    mock_inventories.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_inventory_with_items(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating a party inventory with initial items."""
    party_id = uuid4()
    inventory_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories
    mock_inventories.find_one.return_value = None

    # Mock Neo4j
    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = [{"id": str(party_id)}]

    params = PartyInventoryCreate(
        party_id=party_id,
        initial_gold=500,
        initial_items=[
            {"name": "Health Potion", "quantity": 5, "category": "consumables"},
            {"name": "Rope", "quantity": 1, "category": "misc", "notes": "50 feet"},
        ],
    )

    with patch("monitor_data.tools.mongodb_tools.uuid4", return_value=inventory_id):
        result = mongodb_create_party_inventory(params)

    assert result.gold == 500
    assert len(result.items) == 2
    assert result.items[0].name == "Health Potion"
    assert result.items[0].quantity == 5
    assert result.items[1].notes == "50 feet"


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_inventory_party_not_found(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating inventory for non-existent party."""
    party_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories
    mock_inventories.find_one.return_value = None

    # Mock Neo4j - party not found
    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = []

    params = PartyInventoryCreate(party_id=party_id)

    with pytest.raises(ValueError, match="Party .* not found"):
        mongodb_create_party_inventory(params)


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_inventory_already_exists(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating inventory when one already exists."""
    party_id = uuid4()

    # Mock MongoDB - inventory already exists
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories
    mock_inventories.find_one.return_value = {"inventory_id": str(uuid4())}

    # Mock Neo4j
    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = [{"id": str(party_id)}]

    params = PartyInventoryCreate(party_id=party_id)

    with pytest.raises(ValueError, match="already exists"):
        mongodb_create_party_inventory(params)


# =============================================================================
# TEST: mongodb_get_party_inventory
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_inventory_success(mock_get_mongodb: Mock):
    """Test retrieving a party inventory."""
    party_id = uuid4()
    inventory_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(inventory_id),
        "party_id": str(party_id),
        "gold": 250,
        "items": [
            {
                "name": "Sword",
                "quantity": 1,
                "category": "weapons",
                "value": 50,
                "notes": None,
                "added_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    result = mongodb_get_party_inventory(party_id)

    assert result.inventory_id == inventory_id
    assert result.party_id == party_id
    assert result.gold == 250
    assert len(result.items) == 1
    assert result.items[0].name == "Sword"


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_inventory_not_found(mock_get_mongodb: Mock):
    """Test retrieving non-existent inventory."""
    party_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories
    mock_inventories.find_one.return_value = None

    with pytest.raises(ValueError, match="Inventory .* not found"):
        mongodb_get_party_inventory(party_id)


# =============================================================================
# TEST: mongodb_add_inventory_item
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.mongodb_get_party_inventory")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_add_item_new(
    mock_get_mongodb: Mock,
    mock_get_inventory: Mock,
):
    """Test adding a new item to inventory."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 100,
        "items": [],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    # Mock get_inventory return
    mock_get_inventory.return_value = PartyInventoryResponse(
        inventory_id=uuid4(),
        party_id=party_id,
        gold=100,
        items=[
            InventoryItem(
                name="Torch",
                quantity=3,
                category=ItemCategory.MISC,
                value=None,
                notes=None,
                added_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )

    params = AddInventoryItemRequest(
        party_id=party_id,
        item_name="Torch",
        quantity=3,
        category=ItemCategory.MISC,
    )

    result = mongodb_add_inventory_item(params)

    assert len(result.items) == 1
    assert result.items[0].name == "Torch"
    assert result.items[0].quantity == 3
    mock_inventories.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.mongodb_get_party_inventory")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_add_item_existing(
    mock_get_mongodb: Mock,
    mock_get_inventory: Mock,
):
    """Test adding quantity to an existing item."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 100,
        "items": [
            {
                "name": "Arrow",
                "quantity": 10,
                "category": "weapons",
                "value": None,
                "notes": None,
                "added_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    # Mock get_inventory return
    mock_get_inventory.return_value = PartyInventoryResponse(
        inventory_id=uuid4(),
        party_id=party_id,
        gold=100,
        items=[
            InventoryItem(
                name="Arrow",
                quantity=25,  # 10 + 15
                category=ItemCategory.WEAPONS,
                value=None,
                notes=None,
                added_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )

    params = AddInventoryItemRequest(
        party_id=party_id,
        item_name="Arrow",
        quantity=15,
    )

    result = mongodb_add_inventory_item(params)

    assert result.items[0].name == "Arrow"
    assert result.items[0].quantity == 25


# =============================================================================
# TEST: mongodb_remove_inventory_item
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.mongodb_get_party_inventory")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_remove_item_partial(
    mock_get_mongodb: Mock,
    mock_get_inventory: Mock,
):
    """Test removing partial quantity of an item."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 100,
        "items": [
            {
                "name": "Ration",
                "quantity": 10,
                "category": "consumables",
                "value": None,
                "notes": None,
                "added_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    # Mock get_inventory return
    mock_get_inventory.return_value = PartyInventoryResponse(
        inventory_id=uuid4(),
        party_id=party_id,
        gold=100,
        items=[
            InventoryItem(
                name="Ration",
                quantity=7,  # 10 - 3
                category=ItemCategory.CONSUMABLES,
                value=None,
                notes=None,
                added_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )

    params = RemoveInventoryItemRequest(
        party_id=party_id,
        item_name="Ration",
        quantity=3,
    )

    result = mongodb_remove_inventory_item(params)

    assert result.items[0].quantity == 7


@patch("monitor_data.tools.mongodb_tools.mongodb_get_party_inventory")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_remove_item_full(
    mock_get_mongodb: Mock,
    mock_get_inventory: Mock,
):
    """Test removing all quantity of an item."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 100,
        "items": [
            {
                "name": "Torch",
                "quantity": 5,
                "category": "misc",
                "value": None,
                "notes": None,
                "added_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    # Mock get_inventory return - item removed
    mock_get_inventory.return_value = PartyInventoryResponse(
        inventory_id=uuid4(),
        party_id=party_id,
        gold=100,
        items=[],  # Item removed
        created_at=now,
        updated_at=now,
    )

    params = RemoveInventoryItemRequest(
        party_id=party_id,
        item_name="Torch",
        quantity=None,  # Remove all
    )

    result = mongodb_remove_inventory_item(params)

    assert len(result.items) == 0


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_remove_item_not_found(mock_get_mongodb: Mock):
    """Test removing item that doesn't exist."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 100,
        "items": [],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    params = RemoveInventoryItemRequest(
        party_id=party_id,
        item_name="NonExistent",
        quantity=1,
    )

    with pytest.raises(ValueError, match="not found in inventory"):
        mongodb_remove_inventory_item(params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_remove_item_insufficient_quantity(mock_get_mongodb: Mock):
    """Test removing more quantity than available."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 100,
        "items": [
            {
                "name": "Potion",
                "quantity": 2,
                "category": "consumables",
                "value": None,
                "notes": None,
                "added_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    params = RemoveInventoryItemRequest(
        party_id=party_id,
        item_name="Potion",
        quantity=5,
    )

    with pytest.raises(ValueError, match="Insufficient quantity"):
        mongodb_remove_inventory_item(params)


# =============================================================================
# TEST: mongodb_update_party_gold
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.mongodb_get_party_inventory")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_gold_positive(
    mock_get_mongodb: Mock,
    mock_get_inventory: Mock,
):
    """Test adding gold to party."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 100,
        "items": [],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    # Mock get_inventory return
    mock_get_inventory.return_value = PartyInventoryResponse(
        inventory_id=uuid4(),
        party_id=party_id,
        gold=250,  # 100 + 150
        items=[],
        created_at=now,
        updated_at=now,
    )

    params = UpdateGoldRequest(
        party_id=party_id,
        amount=150,
        reason="Loot from dragon",
    )

    result = mongodb_update_party_gold(params)

    assert result.gold == 250


@patch("monitor_data.tools.mongodb_tools.mongodb_get_party_inventory")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_gold_negative(
    mock_get_mongodb: Mock,
    mock_get_inventory: Mock,
):
    """Test subtracting gold from party."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 200,
        "items": [],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    # Mock get_inventory return
    mock_get_inventory.return_value = PartyInventoryResponse(
        inventory_id=uuid4(),
        party_id=party_id,
        gold=150,  # 200 - 50
        items=[],
        created_at=now,
        updated_at=now,
    )

    params = UpdateGoldRequest(
        party_id=party_id,
        amount=-50,
        reason="Bought supplies",
    )

    result = mongodb_update_party_gold(params)

    assert result.gold == 150


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_update_gold_insufficient(mock_get_mongodb: Mock):
    """Test subtracting more gold than available."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 50,
        "items": [],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    params = UpdateGoldRequest(
        party_id=party_id,
        amount=-100,
    )

    with pytest.raises(ValueError, match="Insufficient gold"):
        mongodb_update_party_gold(params)


# =============================================================================
# TEST: mongodb_transfer_item
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_transfer_item_character_not_implemented(mock_get_mongodb: Mock):
    """Test transfer with character inventory (not implemented)."""
    party_id = uuid4()
    character_id = uuid4()

    params = TransferItemRequest(
        from_type=TransferSourceType.PARTY,
        from_id=party_id,
        to_type=TransferTargetType.CHARACTER,
        to_id=character_id,
        item_name="Sword",
        quantity=1,
    )

    with pytest.raises(
        NotImplementedError, match="Character inventory not yet implemented"
    ):
        mongodb_transfer_item(params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_transfer_item_validation_success(mock_get_mongodb: Mock):
    """Test transfer validation (party-to-party)."""
    party_id = uuid4()
    other_party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_inventories = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_inventories

    inventory_doc = {
        "inventory_id": str(uuid4()),
        "party_id": str(party_id),
        "gold": 100,
        "items": [
            {
                "name": "Map",
                "quantity": 1,
                "category": "misc",
                "value": None,
                "notes": None,
                "added_at": now,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    mock_inventories.find_one.return_value = inventory_doc

    params = TransferItemRequest(
        from_type=TransferSourceType.PARTY,
        from_id=party_id,
        to_type=TransferTargetType.PARTY,
        to_id=other_party_id,
        item_name="Map",
        quantity=1,
    )

    result = mongodb_transfer_item(params)

    assert result["status"] == "validated"


# =============================================================================
# TEST: mongodb_create_party_split
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_split_success(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating a party split."""
    party_id = uuid4()
    split_id = uuid4()
    member1_id = uuid4()
    member2_id = uuid4()
    member3_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_splits = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_splits

    # Mock Neo4j
    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    # Party exists, all members exist
    mock_neo4j.execute_read.side_effect = [
        [{"id": str(party_id)}],  # Party check
        [{"id": str(member1_id)}],  # Member 1
        [{"id": str(member2_id)}],  # Member 2
        [{"id": str(member3_id)}],  # Member 3
    ]

    sub_parties = [
        SubParty(
            name="Alpha",
            member_ids=[member1_id, member2_id],
            location_id=None,
            purpose="Scout ahead",
        ),
        SubParty(
            name="Bravo",
            member_ids=[member3_id],
            location_id=None,
            purpose="Guard camp",
        ),
    ]

    params = PartySplitCreate(
        party_id=party_id,
        sub_parties=sub_parties,
    )

    with patch("monitor_data.tools.mongodb_tools.uuid4", return_value=split_id):
        result = mongodb_create_party_split(params)

    assert result.split_id == split_id
    assert result.party_id == party_id
    assert len(result.sub_parties) == 2
    assert result.status == SplitStatus.ACTIVE
    mock_splits.insert_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_neo4j_client")
@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_create_split_party_not_found(
    mock_get_mongodb: Mock,
    mock_get_neo4j: Mock,
):
    """Test creating split for non-existent party."""
    party_id = uuid4()

    # Mock Neo4j - party not found
    mock_neo4j = MagicMock()
    mock_get_neo4j.return_value = mock_neo4j
    mock_neo4j.execute_read.return_value = []

    params = PartySplitCreate(
        party_id=party_id,
        sub_parties=[
            SubParty(name="Alpha", member_ids=[uuid4()]),
            SubParty(name="Bravo", member_ids=[uuid4()]),
        ],
    )

    with pytest.raises(ValueError, match="Party .* not found"):
        mongodb_create_party_split(params)


# =============================================================================
# TEST: mongodb_get_active_splits
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_active_splits_success(mock_get_mongodb: Mock):
    """Test retrieving active splits for a party."""
    party_id = uuid4()
    split_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_splits = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_splits

    split_docs = [
        {
            "split_id": str(split_id),
            "party_id": str(party_id),
            "sub_parties": [
                {
                    "name": "Alpha",
                    "member_ids": [str(uuid4())],
                    "location_id": None,
                    "purpose": "Scout",
                },
                {
                    "name": "Bravo",
                    "member_ids": [str(uuid4())],
                    "location_id": None,
                    "purpose": "Guard",
                },
            ],
            "status": "active",
            "created_at": now,
            "resolved_at": None,
            "resolution_notes": None,
        }
    ]
    mock_splits.find.return_value = split_docs

    result = mongodb_get_active_splits(party_id)

    assert result.party_id == party_id
    assert len(result.splits) == 1
    assert result.splits[0].status == SplitStatus.ACTIVE


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_active_splits_none(mock_get_mongodb: Mock):
    """Test retrieving active splits when there are none."""
    party_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_splits = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_splits
    mock_splits.find.return_value = []

    result = mongodb_get_active_splits(party_id)

    assert result.party_id == party_id
    assert len(result.splits) == 0


# =============================================================================
# TEST: mongodb_resolve_party_split
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_resolve_split_success(mock_get_mongodb: Mock):
    """Test resolving a party split."""
    split_id = uuid4()
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_splits = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_splits

    # First call returns active split, second call returns resolved split
    split_doc_active = {
        "split_id": str(split_id),
        "party_id": str(party_id),
        "sub_parties": [
            {
                "name": "Alpha",
                "member_ids": [str(uuid4())],
                "location_id": None,
                "purpose": None,
            },
            {
                "name": "Bravo",
                "member_ids": [str(uuid4())],
                "location_id": None,
                "purpose": None,
            },
        ],
        "status": "active",
        "created_at": now,
        "resolved_at": None,
        "resolution_notes": None,
    }

    split_doc_resolved = split_doc_active.copy()
    split_doc_resolved["status"] = "resolved"
    split_doc_resolved["resolved_at"] = now
    split_doc_resolved["resolution_notes"] = "Party rejoined at tavern"

    mock_splits.find_one.side_effect = [split_doc_active, split_doc_resolved]

    params = ResolvePartySplitRequest(
        split_id=split_id,
        resolution_notes="Party rejoined at tavern",
    )

    result = mongodb_resolve_party_split(params)

    assert result.split_id == split_id
    assert result.status == SplitStatus.RESOLVED
    assert result.resolution_notes == "Party rejoined at tavern"
    mock_splits.update_one.assert_called_once()


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_resolve_split_not_found(mock_get_mongodb: Mock):
    """Test resolving non-existent split."""
    split_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_splits = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_splits
    mock_splits.find_one.return_value = None

    params = ResolvePartySplitRequest(split_id=split_id)

    with pytest.raises(ValueError, match="Split .* not found"):
        mongodb_resolve_party_split(params)


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_resolve_split_already_resolved(mock_get_mongodb: Mock):
    """Test resolving already resolved split."""
    split_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_splits = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_splits

    split_doc = {
        "split_id": str(split_id),
        "party_id": str(uuid4()),
        "sub_parties": [],
        "status": "resolved",  # Already resolved
        "created_at": now,
        "resolved_at": now,
        "resolution_notes": "Already resolved",
    }
    mock_splits.find_one.return_value = split_doc

    params = ResolvePartySplitRequest(split_id=split_id)

    with pytest.raises(ValueError, match="already resolved"):
        mongodb_resolve_party_split(params)


# =============================================================================
# TEST: mongodb_get_split_history
# =============================================================================


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_split_history_success(mock_get_mongodb: Mock):
    """Test retrieving split history for a party."""
    party_id = uuid4()
    now = datetime.now(timezone.utc)

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_splits = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_splits

    # Mock count
    mock_splits.count_documents.return_value = 3

    # Mock find with cursor
    split_docs = [
        {
            "split_id": str(uuid4()),
            "party_id": str(party_id),
            "sub_parties": [],
            "status": "resolved",
            "created_at": now,
            "resolved_at": now,
            "resolution_notes": "Rejoined",
        },
        {
            "split_id": str(uuid4()),
            "party_id": str(party_id),
            "sub_parties": [],
            "status": "active",
            "created_at": now,
            "resolved_at": None,
            "resolution_notes": None,
        },
    ]

    mock_cursor = MagicMock()
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = split_docs
    mock_splits.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor

    params = SplitHistoryFilter(
        party_id=party_id,
        limit=50,
        offset=0,
    )

    result = mongodb_get_split_history(params)

    assert result.party_id == party_id
    assert result.total == 3
    assert len(result.splits) == 2


@patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
def test_get_split_history_with_pagination(mock_get_mongodb: Mock):
    """Test split history with pagination."""
    party_id = uuid4()

    # Mock MongoDB
    mock_mongodb = MagicMock()
    mock_splits = MagicMock()
    mock_get_mongodb.return_value = mock_mongodb
    mock_mongodb.get_collection.return_value = mock_splits

    # Mock count
    mock_splits.count_documents.return_value = 10

    # Mock find with cursor
    mock_cursor = MagicMock()
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = []
    mock_splits.find.return_value = mock_cursor
    mock_cursor.sort.return_value = mock_cursor

    params = SplitHistoryFilter(
        party_id=party_id,
        limit=5,
        offset=5,
    )

    result = mongodb_get_split_history(params)

    assert result.total == 10
    assert result.limit == 5
    assert result.offset == 5
    mock_cursor.skip.assert_called_with(5)
    mock_cursor.limit.assert_called_with(5)
