"""
DL-15/DL-16: Party Management & Inventory — Contract Tests

Tests the input/output contracts for party and inventory schemas.
These tests validate schema constraints, not database interactions.

Use Cases: DL-15 (Party management), DL-16 (Party inventory), P-13
"""

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.schemas.party_inventory import (
    AddCharacterItemRequest,
    AddInventoryItemRequest,
    CharacterInventoryCreate,
    EquipItemRequest,
    InventoryItem,
    ItemCategory,
    PartyInventoryCreate,
    PartySplitCreate,
    PartySplitResponse,
    RemoveInventoryItemRequest,
    ResolvePartySplitRequest,
    SplitStatus,
    SubParty,
    TransferItemRequest,
    TransferSourceType,
    TransferTargetType,
    UpdateGoldRequest,
)

# =============================================================================
# Enum contract tests
# =============================================================================


@pytest.mark.unit
class TestPartyEnumsContract:
    """Contract tests for party-related enums."""

    def test_item_category_values(self):
        """ItemCategory has expected values."""
        assert ItemCategory.WEAPONS == "weapons"
        assert ItemCategory.ARMOR == "armor"
        assert ItemCategory.CONSUMABLES == "consumables"
        assert ItemCategory.TREASURE == "treasure"
        assert ItemCategory.QUEST_ITEMS == "quest_items"
        assert ItemCategory.MISC == "misc"
        assert len(ItemCategory) == 6

    def test_transfer_source_type_values(self):
        """TransferSourceType has expected values."""
        assert TransferSourceType.PARTY == "party"
        assert TransferSourceType.CHARACTER == "character"

    def test_transfer_target_type_values(self):
        """TransferTargetType has expected values."""
        assert TransferTargetType.PARTY == "party"
        assert TransferTargetType.CHARACTER == "character"

    def test_split_status_values(self):
        """SplitStatus has expected values."""
        assert SplitStatus.ACTIVE == "active"
        assert SplitStatus.RESOLVED == "resolved"


# =============================================================================
# InventoryItem contract tests
# =============================================================================


@pytest.mark.unit
class TestInventoryItemContract:
    """Contract tests for InventoryItem schema."""

    def test_inventory_item_minimal(self):
        """InventoryItem with required fields is valid."""
        now = datetime.now(UTC)
        item = InventoryItem(
            name="Longsword",
            quantity=1,
            added_at=now,
        )
        assert item.name == "Longsword"
        assert item.quantity == 1
        assert item.category == ItemCategory.MISC
        assert item.value is None
        assert item.notes is None

    def test_inventory_item_with_all_fields(self):
        """InventoryItem with all optional fields populated."""
        now = datetime.now(UTC)
        item = InventoryItem(
            name="Health Potion",
            quantity=5,
            category=ItemCategory.CONSUMABLES,
            value=50,
            notes="Restores 2d4+2 HP",
            added_at=now,
        )
        assert item.category == ItemCategory.CONSUMABLES
        assert item.value == 50
        assert "HP" in item.notes

    def test_inventory_item_empty_name_fails(self):
        """InventoryItem with empty name raises ValidationError."""
        with pytest.raises(Exception):
            InventoryItem(
                name="",
                quantity=1,
                added_at=datetime.now(UTC),
            )

    def test_inventory_item_zero_quantity_fails(self):
        """InventoryItem with quantity < 1 raises ValidationError."""
        with pytest.raises(Exception):
            InventoryItem(
                name="test",
                quantity=0,
                added_at=datetime.now(UTC),
            )

    def test_inventory_item_negative_quantity_fails(self):
        """InventoryItem with negative quantity raises ValidationError."""
        with pytest.raises(Exception):
            InventoryItem(
                name="test",
                quantity=-1,
                added_at=datetime.now(UTC),
            )

    def test_inventory_item_negative_value_fails(self):
        """InventoryItem with negative value raises ValidationError."""
        with pytest.raises(Exception):
            InventoryItem(
                name="test",
                quantity=1,
                value=-1,
                added_at=datetime.now(UTC),
            )


# =============================================================================
# PartyInventoryCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestPartyInventoryCreateContract:
    """Contract tests for PartyInventoryCreate schema."""

    def test_create_minimal(self):
        """PartyInventoryCreate with only required fields is valid."""
        pid = uuid4()
        params = PartyInventoryCreate(party_id=pid)
        assert params.party_id == pid
        assert params.initial_gold == 0
        assert params.initial_items == []

    def test_create_with_gold(self):
        """PartyInventoryCreate can specify initial gold."""
        params = PartyInventoryCreate(
            party_id=uuid4(),
            initial_gold=500,
        )
        assert params.initial_gold == 500

    def test_create_with_items(self):
        """PartyInventoryCreate can specify initial items."""
        params = PartyInventoryCreate(
            party_id=uuid4(),
            initial_gold=100,
            initial_items=[
                {"name": "Longsword", "quantity": 1, "category": "weapons"},
                {"name": "Rations", "quantity": 10, "category": "consumables"},
            ],
        )
        assert len(params.initial_items) == 2

    def test_create_negative_gold_fails(self):
        """PartyInventoryCreate with negative gold raises ValidationError."""
        with pytest.raises(Exception):
            PartyInventoryCreate(
                party_id=uuid4(),
                initial_gold=-1,
            )


# =============================================================================
# AddInventoryItemRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestAddInventoryItemRequestContract:
    """Contract tests for AddInventoryItemRequest schema."""

    def test_add_item_minimal(self):
        """AddInventoryItemRequest with required fields is valid."""
        pid = uuid4()
        req = AddInventoryItemRequest(
            party_id=pid,
            item_name="Longsword",
        )
        assert req.party_id == pid
        assert req.item_name == "Longsword"
        assert req.quantity == 1
        assert req.category is None
        assert req.value is None
        assert req.notes is None

    def test_add_item_with_all_fields(self):
        """AddInventoryItemRequest with all optional fields populated."""
        req = AddInventoryItemRequest(
            party_id=uuid4(),
            item_name="Health Potion",
            quantity=5,
            category=ItemCategory.CONSUMABLES,
            value=50,
            notes="Restores 2d4+2 HP",
        )
        assert req.quantity == 5
        assert req.category == ItemCategory.CONSUMABLES
        assert req.value == 50

    def test_add_item_empty_name_fails(self):
        """AddInventoryItemRequest with empty name raises ValidationError."""
        with pytest.raises(Exception):
            AddInventoryItemRequest(
                party_id=uuid4(),
                item_name="",
            )

    def test_add_item_zero_quantity_fails(self):
        """AddInventoryItemRequest with quantity < 1 raises ValidationError."""
        with pytest.raises(Exception):
            AddInventoryItemRequest(
                party_id=uuid4(),
                item_name="test",
                quantity=0,
            )


# =============================================================================
# RemoveInventoryItemRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestRemoveInventoryItemRequestContract:
    """Contract tests for RemoveInventoryItemRequest schema."""

    def test_remove_item_with_quantity(self):
        """RemoveInventoryItemRequest with quantity is valid."""
        req = RemoveInventoryItemRequest(
            party_id=uuid4(),
            item_name="Health Potion",
            quantity=2,
        )
        assert req.quantity == 2

    def test_remove_item_without_quantity(self):
        """RemoveInventoryItemRequest without quantity removes all."""
        req = RemoveInventoryItemRequest(
            party_id=uuid4(),
            item_name="Longsword",
        )
        assert req.quantity is None

    def test_remove_item_empty_name_fails(self):
        """RemoveInventoryItemRequest with empty name raises ValidationError."""
        with pytest.raises(Exception):
            RemoveInventoryItemRequest(
                party_id=uuid4(),
                item_name="",
            )


# =============================================================================
# TransferItemRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestTransferItemRequestContract:
    """Contract tests for TransferItemRequest schema."""

    def test_transfer_party_to_character(self):
        """TransferItemRequest from party to character is valid."""
        req = TransferItemRequest(
            from_type=TransferSourceType.PARTY,
            from_id=uuid4(),
            to_type=TransferTargetType.CHARACTER,
            to_id=uuid4(),
            item_name="Longsword",
            quantity=1,
        )
        assert req.from_type == TransferSourceType.PARTY
        assert req.to_type == TransferTargetType.CHARACTER

    def test_transfer_character_to_party(self):
        """TransferItemRequest from character to party is valid."""
        req = TransferItemRequest(
            from_type=TransferSourceType.CHARACTER,
            from_id=uuid4(),
            to_type=TransferTargetType.PARTY,
            to_id=uuid4(),
            item_name="Gold",
            quantity=100,
        )
        assert req.from_type == TransferSourceType.CHARACTER
        assert req.to_type == TransferTargetType.PARTY

    def test_transfer_default_quantity(self):
        """TransferItemRequest defaults to quantity 1."""
        req = TransferItemRequest(
            from_type=TransferSourceType.PARTY,
            from_id=uuid4(),
            to_type=TransferTargetType.CHARACTER,
            to_id=uuid4(),
            item_name="Potion",
        )
        assert req.quantity == 1


# =============================================================================
# UpdateGoldRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestUpdateGoldRequestContract:
    """Contract tests for UpdateGoldRequest schema."""

    def test_add_gold(self):
        """UpdateGoldRequest with positive amount adds gold."""
        req = UpdateGoldRequest(
            party_id=uuid4(),
            amount=500,
            reason="Found treasure",
        )
        assert req.amount == 500
        assert req.reason == "Found treasure"

    def test_subtract_gold(self):
        """UpdateGoldRequest with negative amount subtracts gold."""
        req = UpdateGoldRequest(
            party_id=uuid4(),
            amount=-200,
            reason="Bought supplies",
        )
        assert req.amount == -200

    def test_zero_gold(self):
        """UpdateGoldRequest with zero amount is valid (no-op)."""
        req = UpdateGoldRequest(
            party_id=uuid4(),
            amount=0,
        )
        assert req.amount == 0


# =============================================================================
# SubParty contract tests
# =============================================================================


@pytest.mark.unit
class TestSubPartyContract:
    """Contract tests for SubParty schema."""

    def test_subparty_minimal(self):
        """SubParty with required fields is valid."""
        mid = uuid4()
        sp = SubParty(
            name="Alpha",
            member_ids=[mid],
        )
        assert sp.name == "Alpha"
        assert sp.member_ids == [mid]
        assert sp.location_id is None
        assert sp.purpose is None

    def test_subparty_with_all_fields(self):
        """SubParty with all optional fields populated."""
        mid = uuid4()
        lid = uuid4()
        sp = SubParty(
            name="Scout team",
            member_ids=[mid],
            location_id=lid,
            purpose="Scout the northern pass",
        )
        assert sp.location_id == lid
        assert sp.purpose == "Scout the northern pass"

    def test_subparty_empty_name_fails(self):
        """SubParty with empty name raises ValidationError."""
        with pytest.raises(Exception):
            SubParty(name="", member_ids=[uuid4()])

    def test_subparty_empty_members_fails(self):
        """SubParty with empty member_ids raises ValidationError."""
        with pytest.raises(Exception):
            SubParty(name="Alpha", member_ids=[])


# =============================================================================
# PartySplitCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestPartySplitCreateContract:
    """Contract tests for PartySplitCreate schema."""

    def test_split_create_minimal(self):
        """PartySplitCreate with 2 sub-parties is valid."""
        pid = uuid4()
        params = PartySplitCreate(
            party_id=pid,
            sub_parties=[
                SubParty(name="Alpha", member_ids=[uuid4()]),
                SubParty(name="Beta", member_ids=[uuid4()]),
            ],
        )
        assert params.party_id == pid
        assert len(params.sub_parties) == 2

    def test_split_create_single_subparty_fails(self):
        """PartySplitCreate with only 1 sub-party raises ValidationError."""
        with pytest.raises(Exception):
            PartySplitCreate(
                party_id=uuid4(),
                sub_parties=[
                    SubParty(name="Alpha", member_ids=[uuid4()]),
                ],
            )

    def test_split_create_three_subparties(self):
        """PartySplitCreate with 3 sub-parties is valid."""
        params = PartySplitCreate(
            party_id=uuid4(),
            sub_parties=[
                SubParty(name="Alpha", member_ids=[uuid4()]),
                SubParty(name="Beta", member_ids=[uuid4()]),
                SubParty(name="Gamma", member_ids=[uuid4()]),
            ],
        )
        assert len(params.sub_parties) == 3


# =============================================================================
# PartySplitResponse contract tests
# =============================================================================


@pytest.mark.unit
class TestPartySplitResponseContract:
    """Contract tests for PartySplitResponse schema."""

    def test_split_response(self):
        """PartySplitResponse with all fields is valid."""
        resp = PartySplitResponse(
            split_id=uuid4(),
            party_id=uuid4(),
            sub_parties=[
                SubParty(name="Alpha", member_ids=[uuid4()]),
                SubParty(name="Beta", member_ids=[uuid4()]),
            ],
            status=SplitStatus.ACTIVE,
            created_at=datetime.now(UTC),
        )
        assert resp.status == SplitStatus.ACTIVE
        assert resp.resolved_at is None
        assert resp.resolution_notes is None

    def test_split_response_resolved(self):
        """PartySplitResponse can represent a resolved split."""
        now = datetime.now(UTC)
        resp = PartySplitResponse(
            split_id=uuid4(),
            party_id=uuid4(),
            sub_parties=[
                SubParty(name="Alpha", member_ids=[uuid4()]),
                SubParty(name="Beta", member_ids=[uuid4()]),
            ],
            status=SplitStatus.RESOLVED,
            created_at=now,
            resolved_at=now,
            resolution_notes="Party reunited at the inn.",
        )
        assert resp.status == SplitStatus.RESOLVED
        assert resp.resolved_at is not None


# =============================================================================
# ResolvePartySplitRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestResolvePartySplitRequestContract:
    """Contract tests for ResolvePartySplitRequest schema."""

    def test_resolve_minimal(self):
        """ResolvePartySplitRequest with only split_id is valid."""
        sid = uuid4()
        req = ResolvePartySplitRequest(split_id=sid)
        assert req.split_id == sid
        assert req.resolution_notes is None

    def test_resolve_with_notes(self):
        """ResolvePartySplitRequest can include resolution notes."""
        req = ResolvePartySplitRequest(
            split_id=uuid4(),
            resolution_notes="Party reunited after scouting.",
        )
        assert "reunited" in req.resolution_notes


# =============================================================================
# CharacterInventoryCreate contract tests
# =============================================================================


@pytest.mark.unit
class TestCharacterInventoryCreateContract:
    """Contract tests for CharacterInventoryCreate schema."""

    def test_create_minimal(self):
        """CharacterInventoryCreate with only required fields is valid."""
        eid = uuid4()
        params = CharacterInventoryCreate(entity_id=eid)
        assert params.entity_id == eid
        assert params.initial_gold == 0
        assert params.initial_items == []

    def test_create_with_gold_and_items(self):
        """CharacterInventoryCreate can specify initial gold and items."""
        params = CharacterInventoryCreate(
            entity_id=uuid4(),
            initial_gold=50,
            initial_items=[
                {"name": "Dagger", "quantity": 1, "category": "weapons"},
            ],
        )
        assert params.initial_gold == 50
        assert len(params.initial_items) == 1


# =============================================================================
# AddCharacterItemRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestAddCharacterItemRequestContract:
    """Contract tests for AddCharacterItemRequest schema."""

    def test_add_item_minimal(self):
        """AddCharacterItemRequest with required fields is valid."""
        eid = uuid4()
        req = AddCharacterItemRequest(
            entity_id=eid,
            item_name="Dagger",
        )
        assert req.entity_id == eid
        assert req.item_name == "Dagger"
        assert req.quantity == 1
        assert req.equipped is False

    def test_add_item_equipped(self):
        """AddCharacterItemRequest can mark item as equipped."""
        req = AddCharacterItemRequest(
            entity_id=uuid4(),
            item_name="Armor",
            equipped=True,
        )
        assert req.equipped is True

    def test_add_item_empty_name_fails(self):
        """AddCharacterItemRequest with empty name raises ValidationError."""
        with pytest.raises(Exception):
            AddCharacterItemRequest(
                entity_id=uuid4(),
                item_name="",
            )


# =============================================================================
# EquipItemRequest contract tests
# =============================================================================


@pytest.mark.unit
class TestEquipItemRequestContract:
    """Contract tests for EquipItemRequest schema."""

    def test_equip_item(self):
        """EquipItemRequest with equipped=True is valid."""
        req = EquipItemRequest(
            entity_id=uuid4(),
            item_name="Longsword",
            equipped=True,
        )
        assert req.equipped is True

    def test_unequip_item(self):
        """EquipItemRequest with equipped=False is valid."""
        req = EquipItemRequest(
            entity_id=uuid4(),
            item_name="Longsword",
            equipped=False,
        )
        assert req.equipped is False

    def test_equip_default_true(self):
        """EquipItemRequest defaults to equipped=True."""
        req = EquipItemRequest(
            entity_id=uuid4(),
            item_name="Longsword",
        )
        assert req.equipped is True
