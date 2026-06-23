import pytest
from uuid import uuid4
from unittest.mock import MagicMock, patch
from monitor_agents.world_architect import WorldArchitect


class TestWorldArchitect:
    def test_world_architect_initialization(self):
        """Test WorldArchitect can be initialized."""
        architect = WorldArchitect()
        assert architect is not None

    def test_world_architect_initialization_with_id(self):
        """Test WorldArchitect initializes with agent_id."""
        architect = WorldArchitect(agent_id="test-architect")
        assert architect.agent_id == "test-architect"


@pytest.mark.asyncio
async def test_populate_scene_procedurally_no_tables():
    architect = WorldArchitect()
    u_id = uuid4()
    s_id = uuid4()

    # Mock mongodb_list_random_tables to return empty
    with patch("monitor_data.tools.mongodb_tools.mongodb_list_random_tables") as mock_list:
        mock_list.return_value = MagicMock(tables=[])

        proposals = await architect.populate_scene_procedurally(u_id, s_id)
        assert proposals == []


@pytest.mark.asyncio
async def test_populate_scene_procedurally_with_tables():
    architect = WorldArchitect()
    u_id = uuid4()
    s_id = uuid4()

    mock_table = MagicMock()
    mock_table.table_id = str(uuid4())
    mock_table.name = "Dungeon Encounters"
    mock_table.table_type.value = "encounter"

    mock_roll = {"table_name": "Dungeon Encounters", "value": "An angry Orc"}

    with (
        patch("monitor_data.tools.mongodb_tools.mongodb_list_random_tables") as mock_list,
        patch("monitor_data.tools.mongodb_tools.mongodb_roll_on_table") as mock_roll_tool,
        patch.object(WorldArchitect, "_commit_proposals") as mock_commit,
    ):
        mock_list.return_value = MagicMock(tables=[mock_table])
        mock_roll_tool.return_value = mock_roll
        mock_commit.return_value = (1, [], {})

        proposals = await architect.populate_scene_procedurally(u_id, s_id, "dungeon")

        assert len(proposals) == 1
        assert proposals[0]["payload"]["name"] == "An angry Orc"
        assert proposals[0]["payload"]["entity_type"] == "npc"
        mock_commit.assert_called_once()


@pytest.mark.asyncio
async def test_populate_scene_procedurally_with_town_location():
    """Test populating a town location."""
    architect = WorldArchitect()
    u_id = uuid4()
    s_id = uuid4()

    mock_table = MagicMock()
    mock_table.table_id = str(uuid4())
    mock_table.name = "Town Events"
    mock_table.table_type.value = "event"

    mock_roll = {"table_name": "Town Events", "value": "A merchant caravan arrives"}

    with (
        patch("monitor_data.tools.mongodb_tools.mongodb_list_random_tables") as mock_list,
        patch("monitor_data.tools.mongodb_tools.mongodb_roll_on_table") as mock_roll_tool,
        patch.object(WorldArchitect, "_commit_proposals") as mock_commit,
    ):
        mock_list.return_value = MagicMock(tables=[mock_table])
        mock_roll_tool.return_value = mock_roll
        mock_commit.return_value = (1, [], {})

        proposals = await architect.populate_scene_procedurally(u_id, s_id, "town")

        assert len(proposals) == 1
        mock_commit.assert_called_once()


@pytest.mark.asyncio
async def test_populate_scene_procedurally_with_wilderness_location():
    """Test populating a wilderness location."""
    architect = WorldArchitect()
    u_id = uuid4()
    s_id = uuid4()

    with patch("monitor_data.tools.mongodb_tools.mongodb_list_random_tables") as mock_list:
        mock_list.return_value = MagicMock(tables=[])

        proposals = await architect.populate_scene_procedurally(u_id, s_id, "wilderness")

        assert proposals == []


@pytest.mark.asyncio
async def test_populate_scene_procedurally_multiple_tables():
    """Test populating with multiple tables."""
    architect = WorldArchitect()
    u_id = uuid4()
    s_id = uuid4()

    mock_table1 = MagicMock()
    mock_table1.table_id = str(uuid4())
    mock_table1.name = "Dungeon Encounters"
    mock_table1.table_type.value = "encounter"

    mock_table2 = MagicMock()
    mock_table2.table_id = str(uuid4())
    mock_table2.name = "Dungeon Treasure"
    mock_table2.table_type.value = "treasure"

    with (
        patch("monitor_data.tools.mongodb_tools.mongodb_list_random_tables") as mock_list,
        patch("monitor_data.tools.mongodb_tools.mongodb_roll_on_table") as mock_roll_tool,
        patch.object(WorldArchitect, "_commit_proposals") as mock_commit,
    ):
        mock_list.return_value = MagicMock(tables=[mock_table1, mock_table2])
        mock_roll_tool.side_effect = [
            {"table_name": "Dungeon Encounters", "value": "An Orc"},
            {"table_name": "Dungeon Treasure", "value": "10 gold coins"},
        ]
        mock_commit.return_value = (2, [], {})

        proposals = await architect.populate_scene_procedurally(u_id, s_id, "dungeon")

        assert len(proposals) == 2


class TestWorldArchitectProceduralHelpers:
    """Tests for WorldArchitect procedural helper methods."""

    def test_world_architect_has_populate_scene_method(self):
        """WorldArchitect should have populate_scene_procedurally method."""
        architect = WorldArchitect()
        assert hasattr(architect, "populate_scene_procedurally")
        assert callable(getattr(architect, "populate_scene_procedurally"))

    @pytest.mark.asyncio
    async def test_world_architect_populate_scene_accepts_universe_and_scene_id(self):
        """populate_scene_procedurally should accept universe_id and scene_id."""
        architect = WorldArchitect()
        u_id = uuid4()
        s_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.mongodb_list_random_tables") as mock_list:
            mock_list.return_value = MagicMock(tables=[])
            result = await architect.populate_scene_procedurally(u_id, s_id)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_world_architect_populate_scene_returns_list(self):
        """populate_scene_procedurally should return a list."""
        architect = WorldArchitect()
        u_id = uuid4()
        s_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.mongodb_list_random_tables") as mock_list:
            mock_list.return_value = MagicMock(tables=[])
            result = await architect.populate_scene_procedurally(u_id, s_id)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_world_architect_populate_scene_with_none_location(self):
        """populate_scene_procedurally should handle None location."""
        architect = WorldArchitect()
        u_id = uuid4()
        s_id = uuid4()

        with patch("monitor_data.tools.mongodb_tools.mongodb_list_random_tables") as mock_list:
            mock_list.return_value = MagicMock(tables=[])
            result = await architect.populate_scene_procedurally(u_id, s_id, None)
            assert isinstance(result, list)
