"""
Tests for story loop nodes, routing logic, and graph structure.

Mocks all external calls (MongoDB, CanonKeeper) so tests run without
real DB connections or LLM API keys.

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_story_loop.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Lazy imports to avoid settings validation at import time
# ---------------------------------------------------------------------------


def _import_story_loop():
    from monitor_agents.loops.story_loop import (
        StoryState,
        build_story_graph,
        finalize_story,
        init_story,
        route_after_scene,
        run_scene,
        transition_scene,
    )

    return (
        StoryState,
        build_story_graph,
        finalize_story,
        init_story,
        route_after_scene,
        run_scene,
        transition_scene,
    )


# ===========================================================================
# StoryState
# ===========================================================================


class TestStoryState:
    def test_minimal_construction(self):
        (StoryState, *_) = _import_story_loop()
        story_id = uuid4()
        universe_id = uuid4()
        state = StoryState(story_id=story_id, universe_id=universe_id)
        assert state.story_id == story_id
        assert state.universe_id == universe_id

    def test_default_fields(self):
        (StoryState, *_) = _import_story_loop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4())
        assert state.story_outline is None
        assert state.scenes == []
        assert state.current_scene_id is None
        assert state.scenes_completed == 0
        assert state.story_complete is False

    def test_with_initial_scenes(self):
        (StoryState, *_) = _import_story_loop()
        scene1 = uuid4()
        state = StoryState(
            story_id=uuid4(),
            universe_id=uuid4(),
            scenes=[scene1],
            current_scene_id=scene1,
            scenes_completed=1,
        )
        assert len(state.scenes) == 1
        assert state.scenes[0] == scene1
        assert state.scenes_completed == 1

    def test_story_complete_flag(self):
        (StoryState, *_) = _import_story_loop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4(), story_complete=True)
        assert state.story_complete is True

    def test_outline_set(self):
        (StoryState, *_) = _import_story_loop()
        outline = {"acts": 3, "premise": "A hero rises"}
        state = StoryState(story_id=uuid4(), universe_id=uuid4(), story_outline=outline)
        assert state.story_outline == outline


# ===========================================================================
# route_after_scene
# ===========================================================================


class TestRouteAfterScene:
    def test_story_complete_routes_to_finalize(self):
        (StoryState, _, _, _, route_after_scene, *_) = _import_story_loop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4(), story_complete=True)
        assert route_after_scene(state) == "finalize"

    def test_story_not_complete_routes_to_transition(self):
        (StoryState, _, _, _, route_after_scene, *_) = _import_story_loop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4())
        assert route_after_scene(state) == "transition"

    def test_default_story_complete_is_false_routes_transition(self):
        (StoryState, _, _, _, route_after_scene, *_) = _import_story_loop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4(), story_complete=False)
        assert route_after_scene(state) == "transition"


# ===========================================================================
# build_story_graph
# ===========================================================================


class TestBuildStoryGraph:
    def test_graph_compiles(self):
        (_, build_story_graph, *_) = _import_story_loop()
        graph = build_story_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_graph_has_expected_nodes(self):
        (_, build_story_graph, *_) = _import_story_loop()
        graph = build_story_graph()
        node_names = set(graph.nodes.keys())
        assert "init_story" in node_names
        assert "run_scene" in node_names
        assert "transition" in node_names
        assert "finalize" in node_names


# ===========================================================================
# init_story node
# ===========================================================================


class TestInitStoryNode:
    @pytest.mark.asyncio
    async def test_init_creates_first_scene_when_none_exists(self):
        """When no current_scene_id, init_story creates a scene and returns it."""
        (StoryState, _, _, init_story, *_) = _import_story_loop()
        story_id = uuid4()
        universe_id = uuid4()
        state = StoryState(story_id=story_id, universe_id=universe_id)

        fake_outline = {"acts": 2, "theme": "adventure"}
        fake_scene_id = uuid4()

        with (
            patch("monitor_agents.canonkeeper.agent.CanonKeeper") as mock_ck_class,
            patch(
                "monitor_agents.loops.story_loop._load_story_outline",
                new=AsyncMock(return_value=fake_outline),
            ),
            patch(
                "monitor_agents.loops.story_loop._create_scene",
                new=AsyncMock(return_value=fake_scene_id),
            ),
        ):
            mock_ck = mock_ck_class.return_value
            mock_ck.story_exists = AsyncMock(return_value=True)

            result = await init_story(state)

        assert "story_outline" in result
        assert result["story_outline"] == fake_outline
        assert "current_scene_id" in result
        assert result["current_scene_id"] == fake_scene_id
        assert fake_scene_id in result["scenes"]

    @pytest.mark.asyncio
    async def test_init_skips_scene_creation_if_already_exists(self):
        """When current_scene_id already set, init_story only loads outline."""
        (StoryState, _, _, init_story, *_) = _import_story_loop()
        existing_scene = uuid4()
        state = StoryState(
            story_id=uuid4(),
            universe_id=uuid4(),
            current_scene_id=existing_scene,
        )
        fake_outline = {"acts": 1}

        with (
            patch("monitor_agents.canonkeeper.agent.CanonKeeper") as mock_ck_class,
            patch(
                "monitor_agents.loops.story_loop._load_story_outline",
                new=AsyncMock(return_value=fake_outline),
            ),
            patch(
                "monitor_agents.loops.story_loop._create_scene",
                new=AsyncMock(side_effect=AssertionError("should not be called")),
            ),
        ):
            mock_ck = mock_ck_class.return_value
            mock_ck.story_exists = AsyncMock(return_value=True)

            result = await init_story(state)

        assert result["story_outline"] == fake_outline
        assert "current_scene_id" not in result

    @pytest.mark.asyncio
    async def test_init_returns_empty_outline_when_none_in_db(self):
        """When MongoDB has no outline, it calls _create_story_outline."""
        (StoryState, _, _, init_story, *_) = _import_story_loop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4())
        fake_scene_id = uuid4()
        fake_created_outline = {"title": "New Story"}

        with (
            patch("monitor_agents.canonkeeper.agent.CanonKeeper") as mock_ck_class,
            patch(
                "monitor_agents.loops.story_loop._load_story_outline",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "monitor_agents.loops.story_loop._create_story_outline",
                new=AsyncMock(return_value=fake_created_outline),
            ),
            patch(
                "monitor_agents.loops.story_loop._create_scene",
                new=AsyncMock(return_value=fake_scene_id),
            ),
        ):
            mock_ck = mock_ck_class.return_value
            mock_ck.story_exists = AsyncMock(return_value=True)

            result = await init_story(state)

        assert result["story_outline"] == fake_created_outline


# ===========================================================================
# run_scene node
# ===========================================================================


class TestRunSceneNode:
    @pytest.mark.asyncio
    async def test_run_scene_returns_scene_count(self):
        """run_scene records the scene completion count for graph routing."""
        (StoryState, _, _, _, _, run_scene, _) = _import_story_loop()
        state = StoryState(
            story_id=uuid4(),
            universe_id=uuid4(),
            scenes_completed=2,
        )
        result = await run_scene(state)
        assert result == {"scenes_completed": 2, "scenes_history": []}


# ===========================================================================
# transition_scene node
# ===========================================================================


class TestTransitionSceneNode:
    @pytest.mark.asyncio
    async def test_transition_creates_next_scene(self):
        """transition_scene creates a new scene and increments counter."""
        (StoryState, *_) = _import_story_loop()
        scene0 = uuid4()
        state = StoryState(
            story_id=uuid4(),
            universe_id=uuid4(),
            scenes=[scene0],
            current_scene_id=scene0,
            scenes_completed=1,
        )
        new_scene_id = uuid4()

        with patch(
            "monitor_agents.loops.story_loop._create_scene",
            new=AsyncMock(return_value=new_scene_id),
        ):
            from monitor_agents.loops.story_loop import transition_scene

            result = await transition_scene(state)

        assert result["current_scene_id"] == new_scene_id
        assert new_scene_id in result["scenes"]
        assert result["scenes_completed"] == 2

    @pytest.mark.asyncio
    async def test_transition_noop_when_story_complete(self):
        """transition_scene returns {} when story is already complete."""
        (StoryState, *_) = _import_story_loop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4(), story_complete=True)

        with patch(
            "monitor_agents.loops.story_loop._create_scene",
            new=AsyncMock(side_effect=AssertionError("should not be called")),
        ):
            from monitor_agents.loops.story_loop import transition_scene

            result = await transition_scene(state)

        assert result == {}


# ===========================================================================
# finalize_story node
# ===========================================================================


class TestFinalizeStoryNode:
    @pytest.mark.asyncio
    async def test_finalize_calls_canonkeeper(self):
        """finalize_story delegates to CanonKeeper.finalize_story."""
        (StoryState, *_) = _import_story_loop()
        story_id = uuid4()
        state = StoryState(story_id=story_id, universe_id=uuid4())

        mock_ck = AsyncMock()
        mock_ck.finalize_story = AsyncMock(return_value=None)

        with patch("monitor_agents.canonkeeper.agent.CanonKeeper", return_value=mock_ck):
            from monitor_agents.loops.story_loop import finalize_story

            result = await finalize_story(state)

        mock_ck.finalize_story.assert_called_once_with(story_id=story_id)
        assert result == {}

    @pytest.mark.asyncio
    async def test_finalize_returns_empty_dict(self):
        """finalize_story always returns {}."""
        (StoryState, *_) = _import_story_loop()
        state = StoryState(story_id=uuid4(), universe_id=uuid4())

        mock_ck = AsyncMock()
        mock_ck.finalize_story = AsyncMock()

        with patch("monitor_agents.canonkeeper.agent.CanonKeeper", return_value=mock_ck):
            from monitor_agents.loops.story_loop import finalize_story

            result = await finalize_story(state)

        assert result == {}


# ===========================================================================
# _create_scene helper
# ===========================================================================


class TestCreateSceneHelper:
    @pytest.mark.asyncio
    async def test_create_scene_inserts_document(self):
        """_create_scene delegates to the Mongo scene tool and returns a UUID."""
        from monitor_agents.loops.story_loop import _create_scene

        story_id = uuid4()
        universe_id = uuid4()
        scene_id = uuid4()
        fake_created_scene = MagicMock(scene_id=scene_id)

        with patch(
            "monitor_agents.loops.story_loop.run_sync_read",
            new=AsyncMock(return_value=fake_created_scene),
        ) as mock_run:
            result = await _create_scene(story_id=story_id, universe_id=universe_id, order=0)

        assert result == scene_id
        params = mock_run.await_args.args[1]
        assert params.story_id == story_id
        assert params.universe_id == universe_id
        assert params.narrative_order == 0
        assert params.status.value == "active"

    @pytest.mark.asyncio
    async def test_create_scene_uses_provided_order(self):
        """_create_scene stores the given narrative order in the tool payload."""
        from monitor_agents.loops.story_loop import _create_scene

        fake_created_scene = MagicMock(scene_id=uuid4())

        with patch(
            "monitor_agents.loops.story_loop.run_sync_read",
            new=AsyncMock(return_value=fake_created_scene),
        ) as mock_run:
            await _create_scene(story_id=uuid4(), universe_id=uuid4(), order=5)

        params = mock_run.await_args.args[1]
        assert params.narrative_order == 5


# ===========================================================================
# Bootstrap Resiliency (Phase 2 improvements)
# ===========================================================================


class TestBootstrapResiliency:
    """Tests for bootstrap resiliency features implemented in init_story."""

    @pytest.mark.asyncio
    async def test_create_story_outline_inserts_to_mongodb(self):
        """_create_story_outline creates a story outline through the Mongo tool."""
        from monitor_agents.loops.story_loop import _create_story_outline

        story_id = uuid4()
        universe_id = uuid4()
        fake_created_outline = MagicMock(model_dump=lambda mode="json": {"story_id": str(story_id), "premise": "x"})

        with patch(
            "monitor_agents.loops.story_loop.run_sync_read",
            new=AsyncMock(return_value=fake_created_outline),
        ) as mock_run:
            result = await _create_story_outline(story_id, universe_id)

        params = mock_run.await_args.args[1]
        assert params.story_id == story_id
        assert result["story_id"] == str(story_id)
        assert result["universe_id"] == str(universe_id)
        assert "premise" in result

    @pytest.mark.asyncio
    async def test_init_story_verifies_story_exists_in_neo4j(self):
        """init_story checks if story exists in Neo4j before proceeding."""
        (StoryState, _, _, init_story, *_) = _import_story_loop()
        story_id = uuid4()
        universe_id = uuid4()
        state = StoryState(story_id=story_id, universe_id=universe_id)

        fake_outline = {"premise": "Test premise"}
        fake_scene_id = uuid4()

        mock_ck = AsyncMock()
        mock_ck.story_exists = AsyncMock(return_value=False)
        mock_ck.create_story = AsyncMock()
        fake_factory = MagicMock()
        fake_factory.create_canonkeeper.return_value = mock_ck

        mock_create_scene = AsyncMock(return_value=fake_scene_id)

        with (
            patch(
                "monitor_agents.loops.story_loop.get_agent_factory",
                return_value=fake_factory,
            ),
            patch(
                "monitor_agents.loops.story_loop._create_story_outline",
                new=AsyncMock(return_value=fake_outline),
            ),
            patch(
                "monitor_agents.loops.story_loop._create_scene",
                new=mock_create_scene,
            ),
            patch(
                "monitor_agents.loops.story_loop._load_story_outline",
                new=AsyncMock(return_value=None),
            ),
        ):
            result = await init_story(state)

        # Verify story existence was checked
        mock_ck.story_exists.assert_called_once_with(story_id)
        # Verify story was created in Neo4j
        mock_ck.create_story.assert_called_once()
        # Verify scene was created
        assert result["current_scene_id"] == fake_scene_id

    @pytest.mark.asyncio
    async def test_init_story_skips_story_creation_when_exists(self):
        """init_story skips story creation when story already exists in Neo4j."""
        (StoryState, _, _, init_story, *_) = _import_story_loop()
        story_id = uuid4()
        universe_id = uuid4()
        state = StoryState(story_id=story_id, universe_id=universe_id)

        fake_outline = {"premise": "Existing story"}
        fake_scene_id = uuid4()

        mock_ck = AsyncMock()
        mock_ck.story_exists = AsyncMock(return_value=True)
        mock_ck.create_story = AsyncMock()
        fake_factory = MagicMock()
        fake_factory.create_canonkeeper.return_value = mock_ck

        mock_create_scene = AsyncMock(return_value=fake_scene_id)

        with (
            patch(
                "monitor_agents.loops.story_loop.get_agent_factory",
                return_value=fake_factory,
            ),
            patch(
                "monitor_agents.loops.story_loop._load_story_outline",
                new=AsyncMock(return_value=fake_outline),
            ),
            patch(
                "monitor_agents.loops.story_loop._create_scene",
                new=mock_create_scene,
            ),
        ):
            result = await init_story(state)

        # Verify story existence was checked
        mock_ck.story_exists.assert_called_once_with(story_id)
        # Verify story creation was skipped (since story exists)
        mock_ck.create_story.assert_not_called()
        # Verify scene was still created
        assert result["current_scene_id"] == fake_scene_id


# ===========================================================================
# Arc Evaluation
# ===========================================================================


def _import_arc_eval():
    from monitor_agents.loops.story_loop import (
        StoryState,
        evaluate_arc,
    )

    return StoryState, evaluate_arc


class TestStoryLoopPlanning:
    @pytest.mark.asyncio
    async def test_story_loop_generates_next_scene(self):
        from unittest.mock import patch
        from uuid import uuid4

        from monitor_agents.loops.story_loop import StoryLoop, StoryState

        # Mock DSPy module
        with patch("monitor_agents.story.story.StoryPlannerModule.forward") as mock_forward:
            mock_forward.return_value = {
                "next_scene_type": "combat",
                "plot_hook": "The goblins ambush the party.",
            }

            story_id = uuid4()
            universe_id = uuid4()
            loop = StoryLoop(story_id=story_id, universe_id=universe_id)
            state = StoryState(story_id=story_id, universe_id=universe_id, arc_label="Rising Action")
            result = await loop.plan_next_scene(state)

            assert result["next_scene_type"] == "combat"
            assert "goblins ambush" in result["plot_hook"]
