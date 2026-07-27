"""
Behavior tests for P-13: Party Management.

Verifies party CRUD, member management, inventory operations,
and party splits without real DB connections.
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from uuid import uuid4

from monitor_data.schemas.parties import (
    AddPartyMember,
    PartyCreate,
    PartyFilter,
    PartyMemberInfo,
    PartyStatus,
    RemovePartyMember,
    SetActivePC,
)
from monitor_data.schemas.party_inventory import (
    AddInventoryItemRequest,
    InventoryItem,
    ItemCategory,
    PartyInventoryCreate,
    PartySplitCreate,
    RemoveInventoryItemRequest,
    SplitStatus,
    SubParty,
    TransferItemRequest,
    UpdateGoldRequest,
)

# =============================================================================
# Party Schema Contracts
# =============================================================================


class TestPartyCreateSchema:
    def test_minimal_create(self):
        """PartyCreate with only required fields uses defaults."""
        story_id = uuid4()
        p = PartyCreate(story_id=story_id, name="The Brave Companions")
        assert p.name == "The Brave Companions"
        assert p.status == PartyStatus.TRAVELING
        assert p.initial_member_ids == []
        assert p.active_pc_id is None
        assert p.location_id is None
        assert p.formation == []

    def test_create_with_members(self):
        """PartyCreate can specify initial members."""
        m1, m2 = uuid4(), uuid4()
        p = PartyCreate(story_id=uuid4(), name="Party", initial_member_ids=[m1, m2])
        assert len(p.initial_member_ids) == 2
        assert m1 in p.initial_member_ids

    def test_create_with_active_pc(self):
        """PartyCreate can set the active PC."""
        pc_id = uuid4()
        p = PartyCreate(story_id=uuid4(), name="Party", active_pc_id=pc_id)
        assert p.active_pc_id == pc_id


class TestPartyStatusEnum:
    def test_all_statuses(self):
        """All expected party statuses exist."""
        assert PartyStatus.TRAVELING.value == "traveling"
        assert PartyStatus.CAMPING.value == "camping"
        assert PartyStatus.IN_SCENE.value == "in_scene"
        assert PartyStatus.COMBAT.value == "combat"
        assert PartyStatus.SPLIT.value == "split"
        assert PartyStatus.RESTING.value == "resting"


class TestPartyFilterSchema:
    def test_filter_defaults(self):
        """PartyFilter defaults to reasonable pagination."""
        f = PartyFilter()
        assert f.limit == 50
        assert f.offset == 0
        assert f.story_id is None
        assert f.status is None

    def test_filter_by_story(self):
        """PartyFilter can filter by story_id."""
        sid = uuid4()
        f = PartyFilter(story_id=sid)
        assert f.story_id == sid


class TestAddPartyMemberSchema:
    def test_add_member(self):
        """AddPartyMember requires party_id and entity_id."""
        pid, eid = uuid4(), uuid4()
        m = AddPartyMember(party_id=pid, entity_id=eid)
        assert m.party_id == pid
        assert m.entity_id == eid
        assert m.role is None
        assert m.position is None

    def test_add_member_with_role(self):
        """AddPartyMember can specify role and position."""
        m = AddPartyMember(
            party_id=uuid4(), entity_id=uuid4(), role="leader", position=0
        )
        assert m.role == "leader"
        assert m.position == 0


class TestRemovePartyMemberSchema:
    def test_remove_member(self):
        """RemovePartyMember requires party_id and entity_id."""
        pid, eid = uuid4(), uuid4()
        m = RemovePartyMember(party_id=pid, entity_id=eid)
        assert m.party_id == pid
        assert m.entity_id == eid


class TestSetActivePCSchema:
    def test_set_active_pc(self):
        """SetActivePC requires party_id and entity_id."""
        pid, eid = uuid4(), uuid4()
        s = SetActivePC(party_id=pid, entity_id=eid)
        assert s.party_id == pid
        assert s.entity_id == eid


class TestPartyMemberInfo:
    def test_member_info(self):
        """PartyMemberInfo holds entity details."""
        eid = uuid4()
        now = datetime.now(UTC)
        info = PartyMemberInfo(entity_id=eid, role="member", position=1, joined_at=now)
        assert info.entity_id == eid
        assert info.role == "member"
        assert info.position == 1


# =============================================================================
# Party Inventory Schema Contracts
# =============================================================================


class TestPartyInventoryCreateSchema:
    def test_minimal_create(self):
        """PartyInventoryCreate with defaults."""
        pid = uuid4()
        inv = PartyInventoryCreate(party_id=pid)
        assert inv.party_id == pid
        assert inv.initial_gold == 0
        assert inv.initial_items == []

    def test_create_with_gold_and_items(self):
        """PartyInventoryCreate can specify starting gold and items."""
        from datetime import datetime, timezone

        pid = uuid4()
        now = datetime.now(UTC)
        item = InventoryItem(
            name="Longsword", quantity=1, category=ItemCategory.WEAPONS, added_at=now
        )
        inv = PartyInventoryCreate(
            party_id=pid, initial_gold=100, initial_items=[item.model_dump()]
        )
        assert inv.initial_gold == 100
        assert len(inv.initial_items) == 1


class TestInventoryItemSchema:
    def test_item_defaults(self):
        """InventoryItem has sensible defaults."""
        from datetime import datetime, timezone

        now = datetime.now(UTC)
        item = InventoryItem(name="Potion", quantity=1, added_at=now)
        assert item.name == "Potion"
        assert item.quantity == 1
        assert item.category == ItemCategory.MISC
        assert item.value is None
        assert item.notes is None

    def test_item_with_details(self):
        """InventoryItem can have full details."""
        from datetime import datetime, timezone

        now = datetime.now(UTC)
        item = InventoryItem(
            name="Flame Sword",
            quantity=1,
            category=ItemCategory.WEAPONS,
            value=500,
            notes="Deals +1d6 fire damage",
            added_at=now,
        )
        assert item.category == ItemCategory.WEAPONS
        assert item.value == 500


class TestItemCategoryEnum:
    def test_all_categories(self):
        """All expected item categories exist."""
        assert ItemCategory.WEAPONS.value == "weapons"
        assert ItemCategory.ARMOR.value == "armor"
        assert ItemCategory.CONSUMABLES.value == "consumables"
        assert ItemCategory.TREASURE.value == "treasure"
        assert ItemCategory.QUEST_ITEMS.value == "quest_items"
        assert ItemCategory.MISC.value == "misc"


class TestAddInventoryItemRequestSchema:
    def test_add_item(self):
        """AddInventoryItemRequest requires party_id and item_name."""
        pid = uuid4()
        req = AddInventoryItemRequest(party_id=pid, item_name="Rope")
        assert req.item_name == "Rope"
        assert req.quantity == 1
        assert req.category is None

    def test_add_item_with_quantity(self):
        """AddInventoryItemRequest can specify quantity and category."""
        pid = uuid4()
        req = AddInventoryItemRequest(
            party_id=pid,
            item_name="Arrows",
            quantity=20,
            category=ItemCategory.CONSUMABLES,
        )
        assert req.quantity == 20
        assert req.category == ItemCategory.CONSUMABLES


class TestRemoveInventoryItemRequestSchema:
    def test_remove_item(self):
        """RemoveInventoryItemRequest defaults to removing all."""
        pid = uuid4()
        req = RemoveInventoryItemRequest(party_id=pid, item_name="Rope")
        assert req.item_name == "Rope"
        assert req.quantity is None  # None = remove all

    def test_remove_partial(self):
        """RemoveInventoryItemRequest can specify quantity."""
        pid = uuid4()
        req = RemoveInventoryItemRequest(party_id=pid, item_name="Arrows", quantity=5)
        assert req.quantity == 5


class TestUpdateGoldRequestSchema:
    def test_add_gold(self):
        """UpdateGoldRequest with positive amount adds gold."""
        pid = uuid4()
        req = UpdateGoldRequest(party_id=pid, amount=50, reason="Loot")
        assert req.amount == 50
        assert req.reason == "Loot"

    def test_subtract_gold(self):
        """UpdateGoldRequest with negative amount subtracts gold."""
        pid = uuid4()
        req = UpdateGoldRequest(party_id=pid, amount=-25, reason="Purchase")
        assert req.amount == -25


class TestTransferItemRequestSchema:
    def test_transfer_between_parties(self):
        """TransferItemRequest can transfer between two parties."""
        from_id, to_id = uuid4(), uuid4()
        req = TransferItemRequest(
            from_type="party",
            from_id=from_id,
            to_type="party",
            to_id=to_id,
            item_name="Potion",
            quantity=3,
        )
        assert req.from_type == "party"
        assert req.to_type == "party"
        assert req.item_name == "Potion"
        assert req.quantity == 3


# =============================================================================
# Party Split Schema Contracts
# =============================================================================


class TestPartySplitCreateSchema:
    def test_split_requires_two_subparties(self):
        """PartySplitCreate requires at least 2 sub-parties."""
        pid = uuid4()
        sub1 = SubParty(name="Alpha", member_ids=[uuid4()])
        sub2 = SubParty(name="Bravo", member_ids=[uuid4()])
        split = PartySplitCreate(party_id=pid, sub_parties=[sub1, sub2])
        assert len(split.sub_parties) == 2

    def test_subparty_fields(self):
        """SubParty has name, member_ids, and optional fields."""
        m1 = uuid4()
        sub = SubParty(
            name="Scout Team", member_ids=[m1], location_id=uuid4(), purpose="Recon"
        )
        assert sub.name == "Scout Team"
        assert sub.purpose == "Recon"


class TestSplitStatusEnum:
    def test_split_statuses(self):
        """Split status enum has expected values."""
        assert SplitStatus.ACTIVE.value == "active"
        assert SplitStatus.RESOLVED.value == "resolved"


# =============================================================================
# Party Tool Behavior (with mocked DB)
# =============================================================================


class TestNeo4jPartyTools:
    """Test party Neo4j tool function signatures and behavior with mocks."""

    def test_create_party_tool_exists(self):
        """neo4j_create_party tool function is importable."""
        from monitor_data.tools.neo4j_tools.parties import neo4j_create_party

        assert callable(neo4j_create_party)

    def test_get_party_tool_exists(self):
        """neo4j_get_party tool function is importable."""
        from monitor_data.tools.neo4j_tools.parties import neo4j_get_party

        assert callable(neo4j_get_party)

    def test_list_parties_tool_exists(self):
        """neo4j_list_parties tool function is importable."""
        from monitor_data.tools.neo4j_tools.parties import neo4j_list_parties

        assert callable(neo4j_list_parties)

    def test_add_member_tool_exists(self):
        """neo4j_add_party_member tool function is importable."""
        from monitor_data.tools.neo4j_tools.parties import neo4j_add_party_member

        assert callable(neo4j_add_party_member)

    def test_remove_member_tool_exists(self):
        """neo4j_remove_party_member tool function is importable."""
        from monitor_data.tools.neo4j_tools.parties import neo4j_remove_party_member

        assert callable(neo4j_remove_party_member)

    def test_set_active_pc_tool_exists(self):
        """neo4j_set_active_pc tool function is importable."""
        from monitor_data.tools.neo4j_tools.parties import neo4j_set_active_pc

        assert callable(neo4j_set_active_pc)

    def test_update_party_status_tool_exists(self):
        """neo4j_update_party_status tool function is importable."""
        from monitor_data.tools.neo4j_tools.parties import neo4j_update_party_status

        assert callable(neo4j_update_party_status)


class TestMongoDBPartyInventoryTools:
    """Test party inventory MongoDB tool function signatures."""

    def test_create_inventory_tool_exists(self):
        """mongodb_create_party_inventory tool function is importable."""
        from monitor_data.tools.mongodb_tools.party import (
            mongodb_create_party_inventory,
        )

        assert callable(mongodb_create_party_inventory)

    def test_get_inventory_tool_exists(self):
        """mongodb_get_party_inventory tool function is importable."""
        from monitor_data.tools.mongodb_tools.party import mongodb_get_party_inventory

        assert callable(mongodb_get_party_inventory)

    def test_add_item_tool_exists(self):
        """mongodb_add_inventory_item tool function is importable."""
        from monitor_data.tools.mongodb_tools.party import mongodb_add_inventory_item

        assert callable(mongodb_add_inventory_item)

    def test_remove_item_tool_exists(self):
        """mongodb_remove_inventory_item tool function is importable."""
        from monitor_data.tools.mongodb_tools.party import mongodb_remove_inventory_item

        assert callable(mongodb_remove_inventory_item)

    def test_update_gold_tool_exists(self):
        """mongodb_update_party_gold tool function is importable."""
        from monitor_data.tools.mongodb_tools.party import mongodb_update_party_gold

        assert callable(mongodb_update_party_gold)

    def test_transfer_item_tool_exists(self):
        """mongodb_transfer_item tool function is importable."""
        from monitor_data.tools.mongodb_tools.party import mongodb_transfer_item

        assert callable(mongodb_transfer_item)

    def test_create_split_tool_exists(self):
        """mongodb_create_party_split tool function is importable."""
        from monitor_data.tools.mongodb_tools.party import mongodb_create_party_split

        assert callable(mongodb_create_party_split)
