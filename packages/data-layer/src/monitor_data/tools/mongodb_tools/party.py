"""Auto-extracted MongoDB tools sub-module."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.party_inventory import (
    ActiveSplitsResponse,
    AddCharacterItemRequest,
    AddInventoryItemRequest,
    CharacterInventoryCreate,
    CharacterInventoryResponse,
    EquipItemRequest,
    InventoryItem,
    ItemCategory,
    PartyInventoryCreate,
    PartyInventoryResponse,
    PartySplitCreate,
    PartySplitResponse,
    RemoveCharacterItemRequest,
    RemoveInventoryItemRequest,
    ResolvePartySplitRequest,
    SplitHistoryFilter,
    SplitHistoryResponse,
    SplitStatus,
    SubParty,
    TransferItemRequest,
    TransferSourceType,
    TransferTargetType,
    UpdateCharacterGoldRequest,
    UpdateGoldRequest,
)

# =============================================================================
# INVENTORY OPERATIONS
# =============================================================================


def mongodb_create_party_inventory(
    params: PartyInventoryCreate,
) -> PartyInventoryResponse:
    """
    Create a new party inventory document in MongoDB.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Party inventory creation parameters

    Returns:
        PartyInventoryResponse with created inventory data

    Raises:
        ValueError: If party_id doesn't exist in Neo4j or inventory already exists
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify party exists in Neo4j
    party_check_query = """
    MATCH (p:Party {id: $party_id})
    RETURN p.id as id
    """
    result = neo4j_client.execute_read(party_check_query, {"party_id": str(params.party_id)})
    if not result:
        raise ValueError(f"Party {params.party_id} not found")

    # Check if inventory already exists
    inventories_collection = mongo_client.get_collection("party_inventories")
    existing = inventories_collection.find_one({"party_id": str(params.party_id)})
    if existing:
        raise ValueError(f"Inventory for party {params.party_id} already exists")

    # Create inventory document
    now = datetime.now(UTC)
    inventory_id = uuid4()

    # Process initial items
    items = []
    if params.initial_items:
        for item_data in params.initial_items:
            item = InventoryItem(
                name=item_data["name"],
                quantity=item_data.get("quantity", 1),
                category=ItemCategory(item_data.get("category", ItemCategory.MISC)),
                value=item_data.get("value"),
                notes=item_data.get("notes"),
                added_at=now,
            )
            items.append(item.model_dump(mode="json"))

    inventory_doc = {
        "inventory_id": str(inventory_id),
        "party_id": str(params.party_id),
        "gold": params.initial_gold,
        "items": items,
        "created_at": now,
        "updated_at": now,
    }

    inventories_collection.insert_one(inventory_doc)

    return PartyInventoryResponse(
        inventory_id=inventory_id,
        party_id=params.party_id,
        gold=params.initial_gold,
        items=[InventoryItem(**item) for item in items],
        created_at=now,
        updated_at=now,
    )


def mongodb_get_party_inventory(party_id: UUID) -> PartyInventoryResponse:
    """
    Get party inventory by party_id.

    Authority: All agents
    Use Case: DL-16

    Args:
        party_id: Party UUID

    Returns:
        PartyInventoryResponse with inventory data

    Raises:
        ValueError: If inventory not found
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("party_inventories")

    inventory_doc = inventories_collection.find_one({"party_id": str(party_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for party {party_id} not found")

    return PartyInventoryResponse(
        inventory_id=UUID(inventory_doc["inventory_id"]),
        party_id=UUID(inventory_doc["party_id"]),
        gold=inventory_doc["gold"],
        items=[InventoryItem(**item) for item in inventory_doc.get("items", [])],
        created_at=inventory_doc["created_at"],
        updated_at=inventory_doc.get("updated_at"),
    )


def mongodb_add_inventory_item(
    params: AddInventoryItemRequest,
) -> PartyInventoryResponse:
    """
    Add an item to party inventory or increment quantity if it exists.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Add item parameters

    Returns:
        PartyInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory not found
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("party_inventories")

    # Get current inventory
    inventory_doc = inventories_collection.find_one({"party_id": str(params.party_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for party {params.party_id} not found")

    now = datetime.now(UTC)
    items = inventory_doc.get("items", [])

    # Normalize item name for case-insensitive comparison
    normalized_name = params.item_name.strip().casefold()

    # Check if item already exists (case-insensitive)
    existing_item = None
    for item in items:
        item_name = item.get("name", "")
        if item_name.strip().casefold() == normalized_name:
            existing_item = item
            break

    if existing_item:
        # Increment quantity
        existing_item["quantity"] += params.quantity
    else:
        # Add new item (store with stripped whitespace but preserve case)
        new_item = InventoryItem(
            name=params.item_name.strip(),
            quantity=params.quantity,
            category=params.category or ItemCategory.MISC,
            value=params.value,
            notes=params.notes,
            added_at=now,
        )
        items.append(new_item.model_dump(mode="json"))

    # Update inventory
    inventories_collection.update_one(
        {"party_id": str(params.party_id)},
        {"$set": {"items": items, "updated_at": now}},
    )

    return mongodb_get_party_inventory(params.party_id)


def mongodb_remove_inventory_item(
    params: RemoveInventoryItemRequest,
) -> PartyInventoryResponse:
    """
    Remove an item from party inventory or decrement quantity.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Remove item parameters

    Returns:
        PartyInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory or item not found, or insufficient quantity
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("party_inventories")

    # Get current inventory
    inventory_doc = inventories_collection.find_one({"party_id": str(params.party_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for party {params.party_id} not found")

    now = datetime.now(UTC)
    items = inventory_doc.get("items", [])

    # Find the item
    item_index = None
    for i, item in enumerate(items):
        if item["name"] == params.item_name:
            item_index = i
            break

    if item_index is None:
        raise ValueError(f"Item '{params.item_name}' not found in inventory")

    item = items[item_index]

    # Check for insufficient quantity
    if params.quantity is not None and params.quantity > item["quantity"]:
        raise ValueError(f"Insufficient quantity: have {item['quantity']}, trying to remove {params.quantity}")

    if params.quantity is None or params.quantity >= item["quantity"]:
        # Remove item completely
        items.pop(item_index)
    else:
        # Decrement quantity
        item["quantity"] -= params.quantity

    # Update inventory
    inventories_collection.update_one(
        {"party_id": str(params.party_id)},
        {"$set": {"items": items, "updated_at": now}},
    )

    return mongodb_get_party_inventory(params.party_id)


def mongodb_update_party_gold(params: UpdateGoldRequest) -> PartyInventoryResponse:
    """
    Update party gold (add or subtract).

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Update gold parameters

    Returns:
        PartyInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory not found or gold would become negative
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("party_inventories")

    # Get current inventory
    inventory_doc = inventories_collection.find_one({"party_id": str(params.party_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for party {params.party_id} not found")

    current_gold = inventory_doc.get("gold", 0)
    new_gold = current_gold + params.amount

    if new_gold < 0:
        raise ValueError(f"Insufficient gold: have {current_gold}, trying to subtract {-params.amount}")

    now = datetime.now(UTC)

    # Update inventory
    inventories_collection.update_one(
        {"party_id": str(params.party_id)},
        {"$set": {"gold": new_gold, "updated_at": now}},
    )

    return mongodb_get_party_inventory(params.party_id)


def mongodb_transfer_item(params: TransferItemRequest) -> dict[str, str]:
    """
    Transfer an item between inventories.

    Supports party-to-party, character-to-party, party-to-character,
    and character-to-character transfers.

    Authority: Orchestrator
    Use Case: DL-16

    Args:
        params: Transfer item parameters

    Returns:
        Dict with transfer confirmation

    Raises:
        ValueError: If an inventory is missing, the item is missing, or quantity is insufficient
    """
    mongo_client = get_mongodb_client()

    if params.from_type == TransferSourceType.CHARACTER or params.to_type == TransferTargetType.CHARACTER:
        return _transfer_character_item(params)

    if params.from_id == params.to_id:
        raise ValueError("Source and destination party inventories must be different")

    inventories_collection = mongo_client.get_collection("party_inventories")
    source_inventory = inventories_collection.find_one({"party_id": str(params.from_id)})
    if not source_inventory:
        raise ValueError(f"Source inventory for party {params.from_id} not found")

    target_inventory = inventories_collection.find_one({"party_id": str(params.to_id)})
    if not target_inventory:
        raise ValueError(f"Target inventory for party {params.to_id} not found")

    normalized_name = params.item_name.strip().casefold()
    source_items = list(source_inventory.get("items", []))
    target_items = list(target_inventory.get("items", []))

    source_item = next(
        (item for item in source_items if str(item.get("name", "")).strip().casefold() == normalized_name),
        None,
    )
    if not source_item:
        raise ValueError(f"Item '{params.item_name}' not found in source inventory")

    current_quantity = int(source_item.get("quantity", 0) or 0)
    if current_quantity < params.quantity:
        raise ValueError(f"Insufficient quantity: have {current_quantity}, trying to transfer {params.quantity}")

    if current_quantity == params.quantity:
        source_items = [
            item for item in source_items if str(item.get("name", "")).strip().casefold() != normalized_name
        ]
    else:
        source_item["quantity"] = current_quantity - params.quantity

    target_item = next(
        (item for item in target_items if str(item.get("name", "")).strip().casefold() == normalized_name),
        None,
    )
    if target_item is not None:
        target_item["quantity"] = int(target_item.get("quantity", 0) or 0) + params.quantity
    else:
        target_items.append(
            {
                "name": str(source_item.get("name") or params.item_name).strip(),
                "quantity": params.quantity,
                "category": source_item.get("category", ItemCategory.MISC.value),
                "value": source_item.get("value"),
                "notes": source_item.get("notes"),
                "added_at": datetime.now(UTC),
            }
        )

    now = datetime.now(UTC)
    inventories_collection.update_one(
        {"party_id": str(params.from_id)},
        {"$set": {"items": source_items, "updated_at": now}},
    )
    inventories_collection.update_one(
        {"party_id": str(params.to_id)},
        {"$set": {"items": target_items, "updated_at": now}},
    )

    return {
        "status": "transferred",
        "message": f"Transferred {params.quantity}x {params.item_name.strip()} from party {params.from_id} to party {params.to_id}",
    }


def mongodb_create_party_split(params: PartySplitCreate) -> PartySplitResponse:
    """
    Create a party split record.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Party split creation parameters

    Returns:
        PartySplitResponse with created split data

    Raises:
        ValueError: If party doesn't exist or validation fails
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify party exists
    party_check_query = """
    MATCH (p:Party {id: $party_id})
    RETURN p.id as id
    """
    result = neo4j_client.execute_read(party_check_query, {"party_id": str(params.party_id)})
    if not result:
        raise ValueError(f"Party {params.party_id} not found")

    # Validate sub-parties (check that all members exist)
    all_member_ids = []
    for sub_party in params.sub_parties:
        all_member_ids.extend(sub_party.member_ids)

    # Check for duplicate member IDs across sub-parties
    if len(all_member_ids) != len(set(all_member_ids)):
        raise ValueError(
            "Duplicate member IDs found across sub-parties. Each character can only be assigned to one sub-party."
        )

    # Verify locations if provided
    for sub_party in params.sub_parties:
        # Verify location if provided
        if sub_party.location_id:
            location_check_query = """
            MATCH (l:Entity {id: $location_id})
            WHERE l.entity_type = 'location'
            RETURN l.id as id
            """
            result = neo4j_client.execute_read(location_check_query, {"location_id": str(sub_party.location_id)})
            if not result:
                raise ValueError(f"Location {sub_party.location_id} not found")

    # Verify all members exist
    for member_id in all_member_ids:
        member_check_query = """
        MATCH (e:Entity {id: $entity_id})
        RETURN e.id as id
        """
        result = neo4j_client.execute_read(member_check_query, {"entity_id": str(member_id)})
        if not result:
            raise ValueError(f"Entity {member_id} not found")

    # Create split document
    now = datetime.now(UTC)
    split_id = uuid4()

    sub_parties_list = [sub_party.model_dump(mode="json") for sub_party in params.sub_parties]

    split_doc = {
        "split_id": str(split_id),
        "party_id": str(params.party_id),
        "sub_parties": sub_parties_list,
        "status": SplitStatus.ACTIVE.value,
        "created_at": now,
        "resolved_at": None,
        "resolution_notes": None,
    }

    splits_collection = mongo_client.get_collection("party_splits")
    splits_collection.insert_one(split_doc)

    return PartySplitResponse(
        split_id=split_id,
        party_id=params.party_id,
        sub_parties=params.sub_parties,
        status=SplitStatus.ACTIVE,
        created_at=now,
        resolved_at=None,
        resolution_notes=None,
    )


def mongodb_get_active_splits(party_id: UUID) -> ActiveSplitsResponse:
    """
    Get all active splits for a party.

    Authority: All agents
    Use Case: DL-16

    Args:
        party_id: Party UUID

    Returns:
        ActiveSplitsResponse with active splits
    """
    mongo_client = get_mongodb_client()
    splits_collection = mongo_client.get_collection("party_splits")

    # Find all active splits for party
    splits_docs = splits_collection.find({"party_id": str(party_id), "status": SplitStatus.ACTIVE.value})

    splits = [
        PartySplitResponse(
            split_id=UUID(split_doc["split_id"]),
            party_id=UUID(split_doc["party_id"]),
            sub_parties=[SubParty(**sub_party) for sub_party in split_doc["sub_parties"]],
            status=SplitStatus(split_doc["status"]),
            created_at=split_doc["created_at"],
            resolved_at=split_doc.get("resolved_at"),
            resolution_notes=split_doc.get("resolution_notes"),
        )
        for split_doc in splits_docs
    ]

    return ActiveSplitsResponse(party_id=party_id, splits=splits)


def mongodb_resolve_party_split(
    params: ResolvePartySplitRequest,
) -> PartySplitResponse:
    """
    Resolve a party split (mark as rejoined).

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Resolve split parameters

    Returns:
        PartySplitResponse with resolved split data

    Raises:
        ValueError: If split not found or already resolved
    """
    mongo_client = get_mongodb_client()
    splits_collection = mongo_client.get_collection("party_splits")

    # Get current split
    split_doc = splits_collection.find_one({"split_id": str(params.split_id)})
    if not split_doc:
        raise ValueError(f"Split {params.split_id} not found")

    if split_doc["status"] == SplitStatus.RESOLVED.value:
        raise ValueError(f"Split {params.split_id} is already resolved")

    now = datetime.now(UTC)

    # Update split
    splits_collection.update_one(
        {"split_id": str(params.split_id)},
        {
            "$set": {
                "status": SplitStatus.RESOLVED.value,
                "resolved_at": now,
                "resolution_notes": params.resolution_notes,
            }
        },
    )

    # Return updated split
    updated_split_doc = splits_collection.find_one({"split_id": str(params.split_id)})
    if not updated_split_doc:
        raise ValueError(f"Split {params.split_id} not found after update")

    return PartySplitResponse(
        split_id=UUID(updated_split_doc["split_id"]),
        party_id=UUID(updated_split_doc["party_id"]),
        sub_parties=[SubParty(**sub_party) for sub_party in updated_split_doc["sub_parties"]],
        status=SplitStatus(updated_split_doc["status"]),
        created_at=updated_split_doc["created_at"],
        resolved_at=updated_split_doc.get("resolved_at"),
        resolution_notes=updated_split_doc.get("resolution_notes"),
    )


def mongodb_get_split_history(params: SplitHistoryFilter) -> SplitHistoryResponse:
    """
    Get split history for a party (all splits, including resolved).

    Authority: All agents
    Use Case: DL-16

    Args:
        params: Split history filter parameters

    Returns:
        SplitHistoryResponse with split history
    """
    mongo_client = get_mongodb_client()
    splits_collection = mongo_client.get_collection("party_splits")

    # Count total splits
    total = splits_collection.count_documents({"party_id": str(params.party_id)})

    # Find splits with pagination
    splits_docs = (
        splits_collection.find({"party_id": str(params.party_id)})
        .sort("created_at", -1)  # Most recent first
        .skip(params.offset)
        .limit(params.limit)
    )

    splits = [
        PartySplitResponse(
            split_id=UUID(split_doc["split_id"]),
            party_id=UUID(split_doc["party_id"]),
            sub_parties=[SubParty(**sub_party) for sub_party in split_doc["sub_parties"]],
            status=SplitStatus(split_doc["status"]),
            created_at=split_doc["created_at"],
            resolved_at=split_doc.get("resolved_at"),
            resolution_notes=split_doc.get("resolution_notes"),
        )
        for split_doc in splits_docs
    ]

    return SplitHistoryResponse(
        party_id=params.party_id,
        splits=splits,
        total=total,
        limit=params.limit,
        offset=params.offset,
    )


# =============================================================================
# CHARACTER INVENTORY OPERATIONS (DL-16 completion)
# =============================================================================


def mongodb_create_character_inventory(
    params: CharacterInventoryCreate,
) -> CharacterInventoryResponse:
    """
    Create a new character inventory document in MongoDB.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Character inventory creation parameters

    Returns:
        CharacterInventoryResponse with created inventory data

    Raises:
        ValueError: If entity doesn't exist in Neo4j or inventory already exists
    """
    mongo_client = get_mongodb_client()
    neo4j_client = get_neo4j_client()

    # Verify entity exists in Neo4j
    entity_check_query = """
    MATCH (e:Entity {id: $entity_id})
    RETURN e.id as id
    """
    result = neo4j_client.execute_read(entity_check_query, {"entity_id": str(params.entity_id)})
    if not result:
        raise ValueError(f"Entity {params.entity_id} not found")

    # Check if inventory already exists
    inventories_collection = mongo_client.get_collection("character_inventories")
    existing = inventories_collection.find_one({"entity_id": str(params.entity_id)})
    if existing:
        raise ValueError(f"Inventory for character {params.entity_id} already exists")

    # Create inventory document
    now = datetime.now(UTC)
    inventory_id = uuid4()

    # Process initial items
    items = []
    if params.initial_items:
        for item_data in params.initial_items:
            item = InventoryItem(
                name=item_data["name"],
                quantity=item_data.get("quantity", 1),
                category=ItemCategory(item_data.get("category", ItemCategory.MISC)),
                value=item_data.get("value"),
                notes=item_data.get("notes"),
                added_at=now,
            )
            items.append(item.model_dump(mode="json"))

    inventory_doc = {
        "inventory_id": str(inventory_id),
        "entity_id": str(params.entity_id),
        "gold": params.initial_gold,
        "items": items,
        "equipped": [],
        "created_at": now,
        "updated_at": now,
    }

    inventories_collection.insert_one(inventory_doc)

    return CharacterInventoryResponse(
        inventory_id=inventory_id,
        entity_id=params.entity_id,
        gold=params.initial_gold,
        items=[InventoryItem(**item) for item in items],
        equipped=[],
        created_at=now,
        updated_at=now,
    )


def mongodb_get_character_inventory(entity_id: UUID) -> CharacterInventoryResponse:
    """
    Get character inventory by entity_id.

    Authority: All agents
    Use Case: DL-16

    Args:
        entity_id: Character entity UUID

    Returns:
        CharacterInventoryResponse with inventory data

    Raises:
        ValueError: If inventory not found
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("character_inventories")

    inventory_doc = inventories_collection.find_one({"entity_id": str(entity_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for character {entity_id} not found")

    return CharacterInventoryResponse(
        inventory_id=UUID(inventory_doc["inventory_id"]),
        entity_id=UUID(inventory_doc["entity_id"]),
        gold=inventory_doc["gold"],
        items=[InventoryItem(**item) for item in inventory_doc.get("items", [])],
        equipped=inventory_doc.get("equipped", []),
        created_at=inventory_doc["created_at"],
        updated_at=inventory_doc.get("updated_at"),
    )


def mongodb_add_character_item(
    params: AddCharacterItemRequest,
) -> CharacterInventoryResponse:
    """
    Add an item to character inventory or increment quantity if it exists.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Add item parameters

    Returns:
        CharacterInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory not found
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("character_inventories")

    inventory_doc = inventories_collection.find_one({"entity_id": str(params.entity_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for character {params.entity_id} not found")

    now = datetime.now(UTC)
    items = inventory_doc.get("items", [])
    equipped = inventory_doc.get("equipped", [])

    # Normalize item name for case-insensitive comparison
    normalized_name = params.item_name.strip().casefold()

    # Check if item already exists
    existing_item = None
    for item in items:
        if item.get("name", "").strip().casefold() == normalized_name:
            existing_item = item
            break

    if existing_item:
        # Increment quantity
        existing_item["quantity"] += params.quantity
    else:
        # Add new item
        new_item = InventoryItem(
            name=params.item_name.strip(),
            quantity=params.quantity,
            category=params.category or ItemCategory.MISC,
            value=params.value,
            notes=params.notes,
            added_at=now,
        )
        items.append(new_item.model_dump(mode="json"))

    # Mark as equipped if requested
    if params.equipped and params.item_name.strip() not in equipped:
        equipped.append(params.item_name.strip())

    # Update inventory
    inventories_collection.update_one(
        {"entity_id": str(params.entity_id)},
        {"$set": {"items": items, "equipped": equipped, "updated_at": now}},
    )

    return mongodb_get_character_inventory(params.entity_id)


def mongodb_remove_character_item(
    params: RemoveCharacterItemRequest,
) -> CharacterInventoryResponse:
    """
    Remove an item from character inventory or decrement quantity.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Remove item parameters

    Returns:
        CharacterInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory or item not found, or insufficient quantity
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("character_inventories")

    inventory_doc = inventories_collection.find_one({"entity_id": str(params.entity_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for character {params.entity_id} not found")

    now = datetime.now(UTC)
    items = inventory_doc.get("items", [])
    equipped = inventory_doc.get("equipped", [])

    # Find the item
    item_index = None
    for i, item in enumerate(items):
        if item["name"] == params.item_name:
            item_index = i
            break

    if item_index is None:
        raise ValueError(f"Item '{params.item_name}' not found in inventory")

    item = items[item_index]

    # Check for insufficient quantity
    if params.quantity is not None and params.quantity > item["quantity"]:
        raise ValueError(f"Insufficient quantity: have {item['quantity']}, trying to remove {params.quantity}")

    if params.quantity is None or params.quantity >= item["quantity"]:
        # Remove item completely
        items.pop(item_index)
        # Also unequip if it was equipped
        if params.item_name in equipped:
            equipped = [e for e in equipped if e != params.item_name]
    else:
        # Decrement quantity
        item["quantity"] -= params.quantity

    # Update inventory
    inventories_collection.update_one(
        {"entity_id": str(params.entity_id)},
        {"$set": {"items": items, "equipped": equipped, "updated_at": now}},
    )

    return mongodb_get_character_inventory(params.entity_id)


def mongodb_update_character_gold(
    params: UpdateCharacterGoldRequest,
) -> CharacterInventoryResponse:
    """
    Update character gold (add or subtract).

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Update gold parameters

    Returns:
        CharacterInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory not found or gold would become negative
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("character_inventories")

    inventory_doc = inventories_collection.find_one({"entity_id": str(params.entity_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for character {params.entity_id} not found")

    current_gold = inventory_doc.get("gold", 0)
    new_gold = current_gold + params.amount

    if new_gold < 0:
        raise ValueError(f"Insufficient gold: have {current_gold}, trying to subtract {-params.amount}")

    now = datetime.now(UTC)

    inventories_collection.update_one(
        {"entity_id": str(params.entity_id)},
        {"$set": {"gold": new_gold, "updated_at": now}},
    )

    return mongodb_get_character_inventory(params.entity_id)


def mongodb_equip_item(params: EquipItemRequest) -> CharacterInventoryResponse:
    """
    Equip or unequip an item in character inventory.

    Authority: Orchestrator, CanonKeeper
    Use Case: DL-16

    Args:
        params: Equip/unequip parameters

    Returns:
        CharacterInventoryResponse with updated inventory

    Raises:
        ValueError: If inventory or item not found
    """
    mongo_client = get_mongodb_client()
    inventories_collection = mongo_client.get_collection("character_inventories")

    inventory_doc = inventories_collection.find_one({"entity_id": str(params.entity_id)})
    if not inventory_doc:
        raise ValueError(f"Inventory for character {params.entity_id} not found")

    items = inventory_doc.get("items", [])
    equipped = list(inventory_doc.get("equipped", []))

    # Verify item exists in inventory
    normalized_name = params.item_name.strip().casefold()
    item_found = any(item.get("name", "").strip().casefold() == normalized_name for item in items)
    if not item_found:
        raise ValueError(f"Item '{params.item_name}' not found in inventory")

    now = datetime.now(UTC)

    if params.equipped:
        # Equip: add to equipped list if not already there
        if params.item_name.strip() not in equipped:
            equipped.append(params.item_name.strip())
    else:
        # Unequip: remove from equipped list
        equipped = [e for e in equipped if e.strip().casefold() != normalized_name]

    inventories_collection.update_one(
        {"entity_id": str(params.entity_id)},
        {"$set": {"equipped": equipped, "updated_at": now}},
    )

    return mongodb_get_character_inventory(params.entity_id)


# =============================================================================
# CHARACTER ↔ PARTY TRANSFER HELPER
# =============================================================================


def _transfer_character_item(params: TransferItemRequest) -> dict[str, str]:
    """
    Handle transfers involving character inventories.

    Supports: character→party, party→character, character→character.

    Args:
        params: Transfer item parameters

    Returns:
        Dict with transfer confirmation

    Raises:
        ValueError: If source/target inventory or item not found
    """
    mongo_client = get_mongodb_client()
    party_collection = mongo_client.get_collection("party_inventories")
    char_collection = mongo_client.get_collection("character_inventories")

    normalized_name = params.item_name.strip().casefold()

    # Resolve source inventory
    if params.from_type.value == "character":
        source_doc = char_collection.find_one({"entity_id": str(params.from_id)})
        if not source_doc:
            raise ValueError(f"Character inventory for {params.from_id} not found")
        source_items = list(source_doc.get("items", []))
        source_collection = char_collection
        source_key = "entity_id"
    else:
        source_doc = party_collection.find_one({"party_id": str(params.from_id)})
        if not source_doc:
            raise ValueError(f"Party inventory for {params.from_id} not found")
        source_items = list(source_doc.get("items", []))
        source_collection = party_collection
        source_key = "party_id"

    # Resolve target inventory
    if params.to_type.value == "character":
        target_doc = char_collection.find_one({"entity_id": str(params.to_id)})
        if not target_doc:
            raise ValueError(f"Character inventory for {params.to_id} not found")
        target_items = list(target_doc.get("items", []))
        target_collection = char_collection
        target_key = "entity_id"
    else:
        target_doc = party_collection.find_one({"party_id": str(params.to_id)})
        if not target_doc:
            raise ValueError(f"Party inventory for {params.to_id} not found")
        target_items = list(target_doc.get("items", []))
        target_collection = party_collection
        target_key = "party_id"

    # Find item in source
    source_item = next(
        (item for item in source_items if str(item.get("name", "")).strip().casefold() == normalized_name),
        None,
    )
    if not source_item:
        raise ValueError(f"Item '{params.item_name}' not found in source inventory")

    current_quantity = int(source_item.get("quantity", 0) or 0)
    if current_quantity < params.quantity:
        raise ValueError(f"Insufficient quantity: have {current_quantity}, trying to transfer {params.quantity}")

    # Remove from source
    if current_quantity == params.quantity:
        source_items = [
            item for item in source_items if str(item.get("name", "")).strip().casefold() != normalized_name
        ]
    else:
        source_item["quantity"] = current_quantity - params.quantity

    # Add to target
    target_item = next(
        (item for item in target_items if str(item.get("name", "")).strip().casefold() == normalized_name),
        None,
    )
    if target_item is not None:
        target_item["quantity"] = int(target_item.get("quantity", 0) or 0) + params.quantity
    else:
        target_items.append(
            {
                "name": str(source_item.get("name") or params.item_name).strip(),
                "quantity": params.quantity,
                "category": source_item.get("category", ItemCategory.MISC.value),
                "value": source_item.get("value"),
                "notes": source_item.get("notes"),
                "added_at": datetime.now(UTC).isoformat(),
            }
        )

    # Handle equipped list for character inventories
    now = datetime.now(UTC)
    source_update = {"items": source_items, "updated_at": now}
    target_update = {"items": target_items, "updated_at": now}

    # If removing from character, also unequip
    if params.from_type.value == "character":
        equipped = list(source_doc.get("equipped", []))
        equipped = [e for e in equipped if e.strip().casefold() != normalized_name]
        source_update["equipped"] = equipped

    # If adding to character, don't auto-equip
    # (user must explicitly equip via mongodb_equip_item)

    source_collection.update_one(
        {source_key: str(params.from_id)},
        {"$set": source_update},
    )
    target_collection.update_one(
        {target_key: str(params.to_id)},
        {"$set": target_update},
    )

    from_label = f"{params.from_type.value} {params.from_id}"
    to_label = f"{params.to_type.value} {params.to_id}"
    return {
        "status": "transferred",
        "message": (f"Transferred {params.quantity}x {params.item_name.strip()} from {from_label} to {to_label}"),
    }
