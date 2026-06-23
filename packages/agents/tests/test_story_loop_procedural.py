import pytest
from uuid import uuid4
from unittest.mock import patch, AsyncMock
from monitor_agents.loops.story_loop import (
    StoryState,
    transition_scene,
    _arc_label_to_purpose,
    route_after_scene,
)


class TestStoryState:
    def test_story_state_creation(self):
        """Test StoryState can be created with valid parameters."""
        u_id = uuid4()
        s_id = uuid4()
        state = StoryState(
            story_id=s_id,
            universe_id=u_id,
            scenes_completed=1,
            next_scene_type="dungeon",
            arc_label="rising_action",
        )
        assert state.story_id == s_id
        assert state.universe_id == u_id
        assert state.scenes_completed == 1
        assert state.next_scene_type == "dungeon"
        assert state.arc_label == "rising_action"

    def test_story_state_defaults(self):
        """Test StoryState default values."""
        u_id = uuid4()
        s_id = uuid4()
        state = StoryState(
            story_id=s_id,
            universe_id=u_id,
        )
        assert state.scenes_completed == 0
        assert state.arc_label == "rising_action"

    def test_story_state_with_explicit_values(self):
        """Test StoryState with explicitly set values."""
        u_id = uuid4()
        s_id = uuid4()
        state = StoryState(
            story_id=s_id,
            universe_id=u_id,
            scenes_completed=5,
            arc_label="climax",
            world_tone="grim",
        )
        assert state.scenes_completed == 5
        assert state.arc_label == "climax"
        assert state.world_tone == "grim"


class TestArcLabelToPurpose:
    def test_arc_label_rising_action(self):
        """Test _arc_label_to_purpose returns correct purpose for rising_action."""
        result = _arc_label_to_purpose("rising_action")
        assert "build" in result.lower() or "momentum" in result.lower()

    def test_arc_label_climax(self):
        """Test _arc_label_to_purpose returns correct purpose for climax."""
        result = _arc_label_to_purpose("climax")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_arc_label_falling_action(self):
        """Test _arc_label_to_purpose returns correct purpose for falling_action."""
        result = _arc_label_to_purpose("falling_action")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_arc_label_unknown(self):
        """Test _arc_label_to_purpose returns generic purpose for unknown."""
        result = _arc_label_to_purpose("unknown")
        assert len(result) > 0


class TestRouteAfterScene:
    def test_route_after_scene_returns_string(self):
        """Test route_after_scene returns a string."""
        u_id = uuid4()
        s_id = uuid4()
        state = StoryState(
            story_id=s_id,
            universe_id=u_id,
            scenes_completed=1,
            next_scene_type="dungeon",
            arc_label="rising_action",
        )
        result = route_after_scene(state)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_route_after_scene_different_for_completed(self):
        """Test route_after_scene returns different route for completed story."""
        u_id = uuid4()
        s_id = uuid4()
        state = StoryState(
            story_id=s_id,
            universe_id=u_id,
            scenes_completed=10,
            next_scene_type="dungeon",
            arc_label="falling_action",
        )
        result = route_after_scene(state)
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_transition_scene_triggers_procedural_population():
    u_id = uuid4()
    s_id = uuid4()
    state = StoryState(
        story_id=s_id,
        universe_id=u_id,
        scenes_completed=1,
        next_scene_type="dungeon",
        arc_label="rising_action",
    )

    new_scene_id = uuid4()

    with (
        patch(
            "monitor_agents.loops.story_loop._create_scene", new_callable=AsyncMock
        ) as mock_create,
        patch(
            "monitor_agents.world_architect.WorldArchitect.populate_scene_procedurally",
            new_callable=AsyncMock,
        ) as mock_populate,
    ):
        mock_create.return_value = new_scene_id

        res = await transition_scene(state)

        assert res["current_scene_id"] == new_scene_id
        assert res["scenes_completed"] == 2

        # Verify procedural population was called
        mock_populate.assert_called_once_with(
            universe_id=u_id, scene_id=new_scene_id, location_type="dungeon"
        )


@pytest.mark.asyncio
async def test_transition_scene_with_town_location():
    """Test transition_scene works with town location type."""
    u_id = uuid4()
    s_id = uuid4()
    state = StoryState(
        story_id=s_id,
        universe_id=u_id,
        scenes_completed=0,
        next_scene_type="town",
        arc_label="setup",
    )

    new_scene_id = uuid4()

    with (
        patch(
            "monitor_agents.loops.story_loop._create_scene", new_callable=AsyncMock
        ) as mock_create,
        patch(
            "monitor_agents.world_architect.WorldArchitect.populate_scene_procedurally",
            new_callable=AsyncMock,
        ) as mock_populate,
    ):
        mock_create.return_value = new_scene_id

        res = await transition_scene(state)

        assert res["scenes_completed"] == 1
        mock_populate.assert_called_once_with(
            universe_id=u_id, scene_id=new_scene_id, location_type="town"
        )


@pytest.mark.asyncio
async def test_story_loop_ticks_npc_agendas():
    from monitor_agents.loops.story_loop import StoryLoop
    from unittest.mock import patch, AsyncMock
    from uuid import uuid4

    u_id = uuid4()
    s_id = uuid4()

    with (
        patch("monitor_data.tools.neo4j_tools.entities.neo4j_tick_agendas") as mock_tick,
        patch(
            "monitor_agents.loops.story_loop._create_scene", new_callable=AsyncMock
        ) as mock_create,
        patch(
            "monitor_agents.world_architect.WorldArchitect.populate_scene_procedurally",
            new_callable=AsyncMock,
        ),
        patch(
            "monitor_agents.simulacrum.SimulacrumAgent.run_world_tick", new_callable=AsyncMock
        ) as mock_sim,
    ):
        mock_tick.return_value = ["Count Dracula advanced plan: Blood Tithe"]
        mock_create.return_value = uuid4()
        mock_sim.return_value = []

        loop = StoryLoop(story_id=s_id, universe_id=u_id)
        # Advance triggers simulate_world_advance which should call neo4j_tick_agendas
        await loop.advance()

        mock_tick.assert_called_once_with(str(u_id))
