"""
Tests for scene loop nodes and routing logic.

Mocks all external calls (ContextAssembly, Resolver, Narrator, CanonKeeper)
so tests run without real DB connections or LLM API keys.

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_scene_loop.py -v
"""

from __future__ import annotations

from datetime import UTC
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from monitor_agents.image_suggestions import ImageSuggestion

# ---------------------------------------------------------------------------
# Import the module under test (lazy to avoid settings validation at import time)
# ---------------------------------------------------------------------------


def _import_scene_loop():
    from monitor_agents.loops.scene_loop import (
        SceneState,
        build_scene_graph,
        canonize_checkpoint,
        load_context,
        narrate,
        persist_turn_artifacts,
        resolve_action,
        route_after_narration,
    )

    return (
        SceneState,
        build_scene_graph,
        canonize_checkpoint,
        load_context,
        narrate,
        persist_turn_artifacts,
        resolve_action,
        route_after_narration,
    )


# ===========================================================================
# SceneState
# ===========================================================================


class TestSceneState:
    def test_minimal_construction(self):
        (SceneState, *_) = _import_scene_loop()
        scene_id = uuid4()
        story_id = uuid4()
        state = SceneState(scene_id=scene_id, story_id=story_id)
        assert state.scene_id == scene_id
        assert state.story_id == story_id
        assert state.user_input is None
        assert state.resolution is None
        assert state.narrative_text is None
        assert state.pending_proposals == []
        assert state.scene_complete is False
        assert state.turns_count == 0
        assert state.max_turns == 50

    def test_custom_max_turns(self):
        (SceneState, *_) = _import_scene_loop()
        state = SceneState(scene_id=uuid4(), story_id=uuid4(), max_turns=10)
        assert state.max_turns == 10

    def test_with_user_input(self):
        (SceneState, *_) = _import_scene_loop()
        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            user_input="I search the room",
        )
        assert state.user_input == "I search the room"


# ===========================================================================
# load_context node
# ===========================================================================


class TestLoadContextNode:
    @pytest.mark.asyncio
    async def test_load_context_populates_state(self):
        (SceneState, _, _, load_context, *_) = _import_scene_loop()

        fake_context = {
            "entities": [{"id": "e1", "name": "Rhal"}],
            "memories": [{"memory_id": "m1", "content": "The station was cold"}],
            "turns": [{"turn_id": "t1", "content": "..."}],
        }

        with patch(
            "monitor_agents.context_assembly.agent.ContextAssembly.assemble",
            new_callable=AsyncMock,
            return_value=fake_context,
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4())
            result = await load_context(state)

        assert result["entity_context"] == fake_context["entities"]
        assert result["memory_context"] == fake_context["memories"]
        assert result["previous_turns"] == fake_context["turns"]

    @pytest.mark.asyncio
    async def test_load_context_empty_databases(self):
        (SceneState, _, _, load_context, *_) = _import_scene_loop()

        with patch(
            "monitor_agents.context_assembly.agent.ContextAssembly.assemble",
            new_callable=AsyncMock,
            return_value={},
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4())
            result = await load_context(state)

        assert result["entity_context"] == []
        assert result["memory_context"] == []
        assert result["previous_turns"] == []

    @pytest.mark.asyncio
    async def test_load_context_passes_selected_system_id(self):
        (SceneState, _, _, load_context, *_) = _import_scene_loop()

        with patch(
            "monitor_agents.context_assembly.agent.ContextAssembly.assemble",
            new_callable=AsyncMock,
            return_value={},
        ) as mock_assemble:
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                system_id="narrative-pure-id",
            )
            await load_context(state)

        assert mock_assemble.await_args.kwargs["system_id"] == "narrative-pure-id"


# ===========================================================================
# resolve_action node
# ===========================================================================


class TestResolveActionNode:
    @pytest.mark.asyncio
    async def test_no_user_input_returns_none_resolution(self):
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()

        state = SceneState(scene_id=uuid4(), story_id=uuid4(), user_input=None)
        result = await resolve_action(state)
        assert result == {"resolution": None}

    @pytest.mark.asyncio
    async def test_with_user_input_calls_resolver(self):
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()

        fake_resolution = {
            "success_level": "success",
            "success": True,
            "effects": ["momentum_gained"],
            "proposals": [],
            "roll_breakdown": "1d20(15) + 2 = 17 vs DC 13",
        }

        with patch(
            "monitor_agents.resolver.Resolver.resolve_turn",
            new_callable=AsyncMock,
            return_value=(fake_resolution, None),
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I search the room",
                entity_context=[{"id": "e1"}],
                previous_turns=[],
            )
            result = await resolve_action(state)

        assert result["resolution"] == fake_resolution
        assert result["pending_proposals"] == []

    @pytest.mark.asyncio
    async def test_director_notes_merged_into_source_profile(self):
        """Player-established facts (director notes) must reach the resolver,
        which reads established_facts from source_profile."""
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()

        fake_resolution = {"success_level": "success", "proposals": []}
        mock_resolve = AsyncMock(return_value=(fake_resolution, None))
        with patch("monitor_agents.resolver.Resolver.resolve_turn", mock_resolve):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I look around",
                established_facts=["this happens in Santiago de Chile"],
                source_profile={"established_facts": ["pre-existing fact"]},
            )
            await resolve_action(state)

        sent_profile = mock_resolve.call_args.kwargs["context"]["source_profile"]
        assert sent_profile["established_facts"] == [
            "this happens in Santiago de Chile",
            "pre-existing fact",
        ]
        # The state's own source_profile must not be mutated.
        assert state.source_profile == {"established_facts": ["pre-existing fact"]}
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()

        existing_proposal = {"proposal_id": "p-existing"}
        new_proposal = {"proposal_id": "p-new"}
        fake_resolution = {"proposals": [new_proposal], "success_level": "success"}

        with patch(
            "monitor_agents.resolver.Resolver.resolve_turn",
            new_callable=AsyncMock,
            return_value=(fake_resolution, None),
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="act",
                pending_proposals=[existing_proposal],
            )
            result = await resolve_action(state)

        assert len(result["pending_proposals"]) == 2
        assert existing_proposal in result["pending_proposals"]
        assert new_proposal in result["pending_proposals"]


# ===========================================================================
# gm_verdict plumbing — Phase A of the narration-gap fix
# ===========================================================================
# The Resolver returns (resolution, gm_verdict); resolve_action stores the
# verdict on state.gm_verdict and pops the internal "_gm_verdict" sentinel
# so state.resolution stays clean; the narrate node passes gm_verdict to
# Narrator.narrate_turn so the existing _refine_gm_draft path (Path 1)
# is reachable from production for the first time.
# ===========================================================================


class TestGMVerdictPlumbing:
    @pytest.mark.asyncio
    async def test_resolve_action_stores_gm_verdict(self):
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()
        fake_verdict = MagicMock()
        fake_verdict.narrative_draft = "You lean in and whisper to the guard…"
        fake_resolution = {
            "success_level": "pending",
            "proposals": [],
            "resolution_type": "propose_roll",
            "stat": "Charisma",
            "difficulty_class": 13,
            "roll_breakdown": "propose_roll — Charisma check (DC 13)",
            "_gm_verdict": fake_verdict,  # internal sentinel
        }
        with patch(
            "monitor_agents.resolver.Resolver.resolve_turn",
            new_callable=AsyncMock,
            return_value=(fake_resolution, fake_verdict),
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I try to convince the guard",
            )
            result = await resolve_action(state)

        # The verdict is captured.
        assert result["gm_verdict"] is fake_verdict
        # The internal sentinel is stripped from state.resolution.
        assert "_gm_verdict" not in result["resolution"]

    @pytest.mark.asyncio
    async def test_resolve_action_stores_none_when_no_verdict(self):
        """When GMAgent fell through to its seed (gm_verdict=None), the
        field is None — the Narrator's legacy _generate path runs."""
        (SceneState, _, _, _, _, _, resolve_action, _) = _import_scene_loop()
        fake_resolution = {"success_level": "success", "proposals": []}
        with patch(
            "monitor_agents.resolver.Resolver.resolve_turn",
            new_callable=AsyncMock,
            return_value=(fake_resolution, None),
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I look around",
            )
            result = await resolve_action(state)
        assert result["gm_verdict"] is None

    @pytest.mark.asyncio
    async def test_narrate_passes_gm_verdict_to_narrator(self):
        """The narrate node reads state.gm_verdict and forwards it."""
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        fake_verdict = MagicMock()
        fake_verdict.narrative_draft = "The guard hesitates…"

        captured: dict = {}

        async def _capture(**kwargs):
            captured.update(kwargs)
            return {"narrative_text": "ok", "proposals": [], "turn_id": "t-1"}

        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            side_effect=_capture,
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I lean in to the guard",
                resolution={"success_level": "pending"},
                gm_verdict=fake_verdict,
            )
            await narrate(state)

        # The narrate node forwarded the verdict to the Narrator.
        assert captured.get("gm_verdict") is fake_verdict

    def test_scene_state_has_gm_verdict_field(self):
        (SceneState, *_rest) = _import_scene_loop()
        # Field exists, defaults to None.
        assert "gm_verdict" in SceneState.model_fields
        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert state.gm_verdict is None


# ===========================================================================
# narrate node
# ===========================================================================


class TestNarrateNode:
    @pytest.mark.asyncio
    async def test_narrate_returns_narrative_text(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        expected_text = "The shadows deepen as Rhal steps forward…"
        fake_narrator_result = {
            "narrative_text": expected_text,
            "proposals": [],
        }

        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={
                **fake_narrator_result,
                "turn_id": "turn-123",
            },
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I step forward",
                resolution={"success_level": "success"},
            )
            result = await narrate(state)

        assert result["narrative_text"] == expected_text
        assert result["turns_count"] == 1
        assert result["turn_id"] == "turn-123"

    @pytest.mark.asyncio
    async def test_narrate_increments_turns_count(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": []},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                turns_count=4,
                user_input="go on",
            )
            result = await narrate(state)

        assert result["turns_count"] == 5

    @pytest.mark.asyncio
    async def test_narrator_proposals_appended(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        old_p = {"proposal_id": "old"}
        new_p = {"proposal_id": "narrator-new"}
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "x", "proposals": [new_p]},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="go",
                pending_proposals=[old_p],
            )
            result = await narrate(state)

        assert len(result["pending_proposals"]) == 2


# ===========================================================================
# canonize_checkpoint node
# ===========================================================================


class TestPersistTurnArtifactsNode:
    @pytest.mark.asyncio
    async def test_persist_turn_artifacts_links_resolution_to_turn(self):
        (SceneState, _, _, _, _, persist_turn_artifacts, _, _) = _import_scene_loop()

        scene_id = uuid4()
        story_id = uuid4()
        actor_id = uuid4()
        turn_id = uuid4()
        resolution_id = uuid4()

        fake_created_resolution = MagicMock(id=resolution_id)
        mock_collection = MagicMock()
        mock_mongo = MagicMock()
        mock_mongo.get_collection.return_value = mock_collection

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_resolution",
                return_value=fake_created_resolution,
            ) as mock_create_resolution,
            patch(
                "monitor_data.db.mongodb.get_mongodb_client",
                return_value=mock_mongo,
            ),
        ):
            state = SceneState(
                scene_id=scene_id,
                story_id=story_id,
                actor_id=actor_id,
                user_input="I force the hatch open",
                turn_id=turn_id,
                narrative_text="The hatch screams open under the strain.",
                resolution={
                    "action_type": "action",
                    "resolution_type": "dice",
                    "success_level": "partial_success",
                    "roll_total": 11,
                    "difficulty_class": 12,
                    "modifier": 1,
                    "roll_detail": {"rolls": [10], "reason": "Force it"},
                    "effects": ["fiction_advances", "setback"],
                },
            )
            result = await persist_turn_artifacts(state)

        assert result["resolution_id"] == str(resolution_id)
        mock_create_resolution.assert_called_once()
        mock_collection.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_turn_artifacts_returns_resolution_even_if_working_state_fails(self):
        (SceneState, _, _, _, _, persist_turn_artifacts, _, _) = _import_scene_loop()

        scene_id = uuid4()
        story_id = uuid4()
        actor_id = uuid4()
        turn_id = uuid4()
        resolution_id = uuid4()

        fake_created_resolution = MagicMock(id=resolution_id)
        mock_collection = MagicMock()
        mock_mongo = MagicMock()
        mock_mongo.get_collection.return_value = mock_collection

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_resolution",
                return_value=fake_created_resolution,
            ) as mock_create_resolution,
            patch(
                "monitor_agents.services.persistence_service.PersistenceService.persist_working_state",
                side_effect=RuntimeError("working state unavailable"),
            ),
            patch(
                "monitor_data.db.mongodb.get_mongodb_client",
                return_value=mock_mongo,
            ),
        ):
            state = SceneState(
                scene_id=scene_id,
                story_id=story_id,
                actor_id=actor_id,
                user_input="I force the hatch open",
                turn_id=turn_id,
                narrative_text="The hatch screams open under the strain.",
                resolution={
                    "action_type": "action",
                    "resolution_type": "dice",
                    "success_level": "partial_success",
                    "roll_total": 11,
                    "difficulty_class": 12,
                    "modifier": 1,
                    "roll_detail": {"rolls": [10], "reason": "Force it"},
                    "effects": ["fiction_advances", "setback"],
                },
            )
            result = await persist_turn_artifacts(state)

        assert result == {
            "resolution_id": str(resolution_id),
            "pending_proposals": [],
        }
        mock_create_resolution.assert_called_once()
        mock_collection.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_turn_artifacts_updates_working_state_and_checkpoint(self):
        (SceneState, _, _, _, _, persist_turn_artifacts, _, _) = _import_scene_loop()

        scene_id = uuid4()
        story_id = uuid4()
        actor_id = uuid4()
        turn_id = uuid4()
        resolution_id = uuid4()
        state_id = uuid4()

        fake_created_resolution = MagicMock(id=resolution_id)
        fake_working_state = MagicMock(
            state=MagicMock(
                state_id=state_id,
                resources={
                    "HP": {"current": 9, "max": 10},
                    "pressure": {"current": 1, "max": 9},
                },
                current_stats={"STR": 2},
                modifications=[],
                temporary_effects=[],
            )
        )
        mock_collection = MagicMock()
        mock_mongo = MagicMock()
        mock_mongo.get_collection.return_value = mock_collection

        with (
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_resolution",
                return_value=fake_created_resolution,
            ),
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_get_working_state",
                return_value=None,
            ),
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_working_state",
                return_value=fake_working_state,
            ) as mock_create_state,
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_update_working_state",
                return_value=fake_working_state,
            ) as mock_update_state,
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_add_modification",
                return_value=fake_working_state,
            ) as mock_add_modification,
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_create_proposed_change",
                side_effect=lambda params: MagicMock(
                    proposal_id=uuid4(), change_type=params.change_type, content=params.content
                ),
            ) as mock_create_proposed_change,
            patch(
                "monitor_data.db.mongodb.get_mongodb_client",
                return_value=mock_mongo,
            ),
        ):
            state = SceneState(
                scene_id=scene_id,
                story_id=story_id,
                actor_id=actor_id,
                user_input="I wrench the hatch open before the vacuum takes me.",
                turn_id=turn_id,
                narrative_text="You get the hatch open, but the strain costs you breath and composure.",
                game_context={
                    "resources": [
                        {"name": "HP", "abbreviation": "HP", "default_value": 10},
                        {"name": "Oxygen", "abbreviation": "O2", "default_value": 6},
                    ]
                },
                entity_context=[
                    {
                        "entity_id": str(actor_id),
                        "properties": {
                            "attributes": {"STR": 2},
                            "resources": {"HP": 10, "Oxygen": 6},
                        },
                    }
                ],
                resolution={
                    "action_type": "action",
                    "intent_type": "action",
                    "resolution_type": "dice",
                    "success_level": "partial_success",
                    "roll_total": 11,
                    "difficulty_class": 12,
                    "modifier": 1,
                    "risk_preview": "Failure here costs air and position.",
                    "roll_detail": {"rolls": [10], "reason": "Force it"},
                    "effects": ["fiction_advances", "setback"],
                },
            )
            result = await persist_turn_artifacts(state)

        assert result["resolution_id"] == str(resolution_id)
        assert result["working_state_id"] == str(state_id)
        assert result["working_state"]["resources"]["HP"]["current"] == 9
        assert result["working_state"]["resources"]["pressure"]["current"] == 1
        assert result["scene_checkpoint"]["success_level"] == "partial_success"
        assert result["pending_proposals"]
        assert result["pending_proposals"][0]["change_type"] == "state_change"
        mock_create_state.assert_called_once()
        mock_update_state.assert_called_once()
        assert mock_add_modification.call_count >= 1
        assert mock_create_proposed_change.call_count >= 1
        mock_collection.update_one.assert_called()


# ===========================================================================
# GAP-4: persist_memories_node
# ===========================================================================


class TestPersistMemoriesNode:
    @pytest.mark.asyncio
    async def test_persist_memories_node_calls_persist_memories(self):
        (
            SceneState,
            _,
            _,
            _,
            _,
            _,
            _,
            _,
        ) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import persist_memories_node

        actor_id = uuid4()
        scene_id = uuid4()
        story_id = uuid4()
        universe_id = uuid4()
        memories = [
            {"memory_id": str(uuid4()), "content": "The cargo bay was cold"},
            {"memory_id": str(uuid4()), "content": "Rhal heard a sound"},
        ]

        state = SceneState(
            scene_id=scene_id,
            story_id=story_id,
            actor_id=actor_id,
            universe_id=universe_id,
            memories_to_persist=memories,
        )

        with patch(
            "monitor_agents.services.persistence_service.PersistenceService.persist_memories",
            new_callable=AsyncMock,
            return_value=[m["memory_id"] for m in memories],
        ) as mock_persist:
            result = await persist_memories_node(state)

        mock_persist.assert_called_once_with(
            entity_id=actor_id,
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
            memories=memories,
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_persist_memories_node_skips_when_no_memories(self):
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import persist_memories_node

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            memories_to_persist=[],
        )

        result = await persist_memories_node(state)

        assert result == {}

    @pytest.mark.asyncio
    async def test_persist_memories_node_skips_when_no_actor_id(self):
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import persist_memories_node

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=None,
            memories_to_persist=[{"memory_id": "m1", "content": "test"}],
        )

        with patch(
            "monitor_agents.services.persistence_service.PersistenceService.persist_memories",
            new_callable=AsyncMock,
        ) as mock_persist:
            result = await persist_memories_node(state)

        mock_persist.assert_not_called()
        assert result == {}


# ===========================================================================
# GAP-E: complete_current_scene
# ===========================================================================


class TestCompleteCurrentSceneNode:
    @pytest.mark.asyncio
    async def test_complete_current_scene_persists_memories(self):
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import complete_current_scene

        actor_id = uuid4()
        scene_id = uuid4()
        story_id = uuid4()
        universe_id = uuid4()
        memories = [{"memory_id": str(uuid4()), "content": "Rhal found the signal"}]

        state = SceneState(
            scene_id=scene_id,
            story_id=story_id,
            actor_id=actor_id,
            universe_id=universe_id,
            memories_to_persist=memories,
            total_minutes_passed=15,
        )

        with patch(
            "monitor_agents.services.persistence_service.PersistenceService.persist_memories",
            new_callable=AsyncMock,
            return_value=[m["memory_id"] for m in memories],
        ) as mock_persist:
            await complete_current_scene(state)

        mock_persist.assert_called_once_with(
            entity_id=actor_id,
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
            memories=memories,
        )

    @pytest.mark.asyncio
    async def test_complete_current_scene_advances_story_state(self):
        (SceneState, *_) = _import_scene_loop()
        from datetime import datetime

        from monitor_agents.loops.scene_loop import StoryState, complete_current_scene

        scene_id = uuid4()
        story_id = uuid4()
        actor_id = uuid4()
        universe_id = uuid4()

        original_time = datetime(2023, 6, 15, 14, 30, tzinfo=UTC)
        state = SceneState(
            scene_id=scene_id,
            story_id=story_id,
            actor_id=actor_id,
            story_state=StoryState(
                story_id=story_id,
                universe_id=universe_id,
                in_game_time=original_time,
                scenes_completed=3,
            ),
            total_minutes_passed=20,
        )

        with patch(
            "monitor_agents.services.persistence_service.PersistenceService.persist_memories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await complete_current_scene(state)

        assert "story_state" in result
        new_time = result["story_state"]["in_game_time"]
        expected_time = datetime(2023, 6, 15, 14, 50, tzinfo=UTC)
        assert new_time == expected_time
        assert result["story_state"]["scenes_completed"] == 4

    @pytest.mark.asyncio
    async def test_complete_current_scene_triggers_downtime_on_resolution(self):
        """G-5: When story arc reaches 'resolution', downtime_available is set."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import StoryState, complete_current_scene

        scene_id = uuid4()
        story_id = uuid4()
        actor_id = uuid4()
        universe_id = uuid4()

        state = SceneState(
            scene_id=scene_id,
            story_id=story_id,
            actor_id=actor_id,
            story_state=StoryState(
                story_id=story_id,
                universe_id=universe_id,
                scenes_completed=5,
                arc_label="resolution",
            ),
            total_minutes_passed=10,
        )

        with patch(
            "monitor_agents.services.persistence_service.PersistenceService.persist_memories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await complete_current_scene(state)

        assert result.get("downtime_available") is True

    @pytest.mark.asyncio
    async def test_complete_current_scene_no_downtime_when_arc_active(self):
        """G-5: When story arc is 'rising_action', downtime_available is NOT set."""
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import StoryState, complete_current_scene

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=uuid4(),
            story_state=StoryState(
                story_id=uuid4(),
                universe_id=uuid4(),
                scenes_completed=2,
                arc_label="rising_action",
            ),
            total_minutes_passed=10,
        )

        with patch(
            "monitor_agents.services.persistence_service.PersistenceService.persist_memories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await complete_current_scene(state)

        assert "downtime_available" not in result or result.get("downtime_available") is not True

    @pytest.mark.asyncio
    async def test_complete_current_scene_no_story_state_returns_empty(self):
        (SceneState, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import complete_current_scene

        # When story_state is None, complete_current_scene returns {}
        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            actor_id=None,
            memories_to_persist=[],
            story_state=None,
            total_minutes_passed=5,
        )

        with patch(
            "monitor_agents.services.persistence_service.PersistenceService.persist_memories",
            new_callable=AsyncMock,
        ) as mock_persist:
            result = await complete_current_scene(state)

        mock_persist.assert_not_called()
        assert result == {}


class TestCanonizeCheckpointNode:
    @pytest.mark.asyncio
    async def test_no_proposals_returns_empty(self):
        (SceneState, _, canonize_checkpoint, *_) = _import_scene_loop()

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            pending_proposals=[],
        )
        result = await canonize_checkpoint(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_with_proposals_calls_canonkeeper(self):
        (SceneState, _, canonize_checkpoint, *_) = _import_scene_loop()

        proposals = [{"proposal_id": "p1"}, {"proposal_id": "p2"}]

        with patch(
            "monitor_agents.canonkeeper.agent.CanonKeeper.evaluate_proposals",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_ck:
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                pending_proposals=proposals,
            )
            result = await canonize_checkpoint(state)

        mock_ck.assert_called_once()
        assert result == {"pending_proposals": []}

    @pytest.mark.asyncio
    async def test_proposals_cleared_after_canonize(self):
        (SceneState, _, canonize_checkpoint, *_) = _import_scene_loop()

        with patch(
            "monitor_agents.canonkeeper.agent.CanonKeeper.evaluate_proposals",
            new_callable=AsyncMock,
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                pending_proposals=[{"p": 1}, {"p": 2}, {"p": 3}],
            )
            result = await canonize_checkpoint(state)

        assert result["pending_proposals"] == []


# ===========================================================================
# route_after_narration
# ===========================================================================


class TestRouteAfterNarration:
    def setup_method(self):
        from langgraph.graph import END

        self._END = END

    def _state(self, turns: int = 1, complete: bool = False, max_turns: int = 50):
        from monitor_agents.loops.scene_loop import SceneState

        return SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            turns_count=turns,
            scene_complete=complete,
            max_turns=max_turns,
        )

    def test_normal_turn_routes_to_end(self):
        from monitor_agents.loops.scene_loop import route_after_narration

        state = self._state(turns=1, complete=False)
        result = route_after_narration(state)
        assert result == self._END

    def test_scene_complete_routes_to_complete_current_scene(self):
        from monitor_agents.loops.scene_loop import route_after_narration

        state = self._state(turns=3, complete=True)
        result = route_after_narration(state)
        assert result == "complete_current_scene"

    def test_max_turns_reached_routes_to_complete_current_scene(self):
        from monitor_agents.loops.scene_loop import route_after_narration

        state = self._state(turns=50, complete=False, max_turns=50)
        result = route_after_narration(state)
        assert result == "complete_current_scene"

    def test_one_below_max_routes_to_end(self):
        from monitor_agents.loops.scene_loop import route_after_narration

        state = self._state(turns=49, complete=False, max_turns=50)
        result = route_after_narration(state)
        assert result == self._END

    def test_complete_overrides_turn_count(self):
        """scene_complete takes priority over turns_count < max_turns."""
        from monitor_agents.loops.scene_loop import route_after_narration

        state = self._state(turns=1, complete=True, max_turns=50)
        result = route_after_narration(state)
        assert result == "complete_current_scene"


# ===========================================================================
# build_scene_graph
# ===========================================================================


class TestBuildSceneGraph:
    def test_graph_compiles(self):
        (_, build_scene_graph, *_) = _import_scene_loop()
        graph = build_scene_graph()
        assert graph is not None

    def test_graph_has_expected_nodes(self):
        (_, build_scene_graph, *_) = _import_scene_loop()
        graph = build_scene_graph()
        node_names = set(graph.nodes.keys())
        expected = {"load_context", "resolve", "narrate", "canonize"}
        assert expected.issubset(node_names)

    def test_compiled_graph_is_runnable(self):
        (_, build_scene_graph, *_) = _import_scene_loop()
        graph = build_scene_graph()
        compiled = graph.compile()
        assert compiled is not None


# ===========================================================================
# SceneState — additional edge cases
# ===========================================================================


class TestSceneStateEdgeCases:
    def test_pending_proposals_defaults_empty(self):
        (SceneState, *_) = _import_scene_loop()
        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert state.pending_proposals == []

    def test_entity_context_defaults_empty(self):
        (SceneState, *_) = _import_scene_loop()
        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert state.entity_context == []

    def test_narrative_text_defaults_none(self):
        (SceneState, *_) = _import_scene_loop()
        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert state.narrative_text is None

    def test_resolution_defaults_none(self):
        (SceneState, *_) = _import_scene_loop()
        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert state.resolution is None


# ===========================================================================
# extract_new_entities node — entity promotion tagging
# ===========================================================================


class TestExtractNewEntitiesPromotion:
    """Entity promotion: [Name](entity:anchor|flavor) tags merge onto
    proposals and repeat mentions accumulate interaction_count instead of
    duplicating. See scene_support.py's parse_entity_tags/merge_entity_proposals.
    """

    @staticmethod
    def _fake_extraction_result(entities: list[dict]) -> Any:
        import json

        prediction = MagicMock()
        prediction.new_entities = json.dumps(entities)
        return prediction

    @pytest.mark.asyncio
    async def test_tagged_entity_missed_by_llm_still_gets_proposed(self):
        """An anchor tag is sufficient promotion evidence on its own —
        even if the LLM detector's confidence filter didn't surface it."""
        from monitor_agents.loops.scene_loop import SceneState, extract_new_entities

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="[Kira Shadowdancer](entity:anchor) rises from her seat.",
            entity_context=[],
        )
        with patch(
            "monitor_agents.extraction.narrative_entity_extraction.NarrativeEntityExtractionModule.forward",
            return_value=self._fake_extraction_result([]),  # LLM found nothing
        ):
            result = await extract_new_entities(state)

        proposals = result["pending_proposals"]
        assert len(proposals) == 1
        assert proposals[0]["content"]["name"] == "Kira Shadowdancer"
        assert proposals[0]["promotion_intent"] == "anchor"

    @pytest.mark.asyncio
    async def test_repeat_mention_across_turns_bumps_interaction_count(self):
        from monitor_agents.loops.scene_loop import SceneState, extract_new_entities

        existing_proposal = {
            "proposal_type": "ENTITY",
            "content": {"name": "Kira Shadowdancer", "entity_type": "CHARACTER"},
            "confidence": 0.8,
            "authority": "SYSTEM",
            "proposer": "narrator",
            "interaction_count": 1,
        }
        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="Kira Shadowdancer nods.",
            entity_context=[],
            pending_proposals=[existing_proposal],
        )
        with patch(
            "monitor_agents.extraction.narrative_entity_extraction.NarrativeEntityExtractionModule.forward",
            return_value=self._fake_extraction_result(
                [{"name": "Kira Shadowdancer", "entity_type": "CHARACTER", "confidence": 0.9}]
            ),
        ):
            result = await extract_new_entities(state)

        proposals = result["pending_proposals"]
        assert len(proposals) == 1, "must dedup, not duplicate the pending proposal"
        assert proposals[0]["interaction_count"] == 2

    @pytest.mark.asyncio
    async def test_mechanical_action_marks_entity_bound(self):
        from monitor_agents.loops.scene_loop import SceneState, extract_new_entities

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="[The Guard](entity:flavor) draws a blade.",
            entity_context=[],
            resolution={"resolution_type": "dice", "action_type": "combat"},
        )
        with patch(
            "monitor_agents.extraction.narrative_entity_extraction.NarrativeEntityExtractionModule.forward",
            return_value=self._fake_extraction_result([]),
        ):
            result = await extract_new_entities(state)

        proposals = result["pending_proposals"]
        assert proposals[0]["is_mechanically_bound"] is True

    @pytest.mark.asyncio
    async def test_no_tags_and_no_llm_entities_returns_empty_update(self):
        from monitor_agents.loops.scene_loop import SceneState, extract_new_entities

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="The chamber falls silent.",
            entity_context=[],
        )
        with patch(
            "monitor_agents.extraction.narrative_entity_extraction.NarrativeEntityExtractionModule.forward",
            return_value=self._fake_extraction_result([]),
        ):
            result = await extract_new_entities(state)

        assert result == {}

    @pytest.mark.asyncio
    async def test_tagged_name_already_canonical_is_not_reproposed(self):
        """A tag naming an entity that already exists in entity_context
        (canonical world) must not spawn a duplicate proposal."""
        from monitor_agents.loops.scene_loop import SceneState, extract_new_entities

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="[Kira Shadowdancer](entity:anchor) rises from her seat.",
            entity_context=[{"name": "Kira Shadowdancer"}],
        )
        with patch(
            "monitor_agents.extraction.narrative_entity_extraction.NarrativeEntityExtractionModule.forward",
            return_value=self._fake_extraction_result([]),
        ):
            result = await extract_new_entities(state)

        assert result == {}


# ===========================================================================
# narrate node — additional cases
# ===========================================================================


class TestNarrateNodeEdgeCases:
    @pytest.mark.asyncio
    async def test_narrate_empty_narrative_text_stored_as_empty_string(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "", "proposals": []},
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4(), user_input="go")
            result = await narrate(state)

        assert result["narrative_text"] == ""

    @pytest.mark.asyncio
    async def test_narrate_with_failed_resolution_returns_text(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        failure_narrative = "You fail to climb the wall, falling back to the ground."
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": failure_narrative, "proposals": []},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="climb the wall",
                resolution={"success_level": "failure", "success": False},
            )
            result = await narrate(state)

        assert result["narrative_text"] == failure_narrative

    @pytest.mark.asyncio
    async def test_narrate_missing_proposals_key_defaults_empty(self):
        """Narrator result without 'proposals' key shouldn't crash."""
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "some text"},  # no 'proposals' key
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4(), user_input="look")
            result = await narrate(state)

        assert result["narrative_text"] == "some text"
        assert result["pending_proposals"] == []


# ===========================================================================
# SceneLoop public API — run() and finalize()
# ===========================================================================


class TestSceneLoopInit:
    def test_default_max_turns(self):
        from monitor_agents.loops.scene_loop import SceneLoop

        loop = SceneLoop.__new__(SceneLoop)
        loop.scene_id = uuid4()
        loop.story_id = uuid4()
        loop.max_turns = 50
        loop._graph = None
        assert loop.max_turns == 50

    def test_custom_max_turns(self):
        from monitor_agents.loops.scene_loop import SceneLoop

        loop = SceneLoop.__new__(SceneLoop)
        loop.max_turns = 20
        assert loop.max_turns == 20


class TestSceneLoopRun:
    @pytest.mark.asyncio
    async def test_run_returns_narrative_text(self):
        from monitor_agents.loops.scene_loop import SceneLoop

        scene_id = uuid4()
        story_id = uuid4()

        expected_state = {
            "scene_id": scene_id,
            "story_id": story_id,
            "narrative_text": "The dungeon crumbles around you.",
            "turns_count": 1,
            "pending_proposals": [],
            "entity_context": [],
            "memory_context": [],
            "previous_turns": [],
            "user_input": "I run",
            "resolution": {"success_level": "success"},
            "scene_complete": False,
            "max_turns": 50,
            "turn_id": None,
        }

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value=expected_state)

        mock_saver = MagicMock()
        mock_saver.__enter__ = MagicMock(return_value=mock_saver)
        mock_saver.__exit__ = MagicMock(return_value=False)

        mock_graph = MagicMock()
        mock_graph.compile.return_value = mock_compiled

        loop = SceneLoop.__new__(SceneLoop)
        loop.scene_id = scene_id
        loop.story_id = story_id
        loop.max_turns = 50
        loop._graph = mock_graph

        with patch("monitor_agents.loops.scene_loop.MongoDBSaver") as mock_cls:
            mock_cls.from_conn_string.return_value = mock_saver
            result = await loop.run(user_input="I run")

        assert result["narrative_text"] == "The dungeon crumbles around you."
        mock_compiled.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_passes_scene_id_as_thread_id(self):
        from monitor_agents.loops.scene_loop import SceneLoop

        scene_id = uuid4()
        story_id = uuid4()
        expected_state = {
            "scene_id": scene_id,
            "story_id": story_id,
            "narrative_text": "...",
            "turns_count": 1,
            "pending_proposals": [],
            "entity_context": [],
            "memory_context": [],
            "previous_turns": [],
            "user_input": "x",
            "resolution": None,
            "scene_complete": False,
            "max_turns": 50,
            "turn_id": None,
        }

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value=expected_state)

        mock_saver = MagicMock()
        mock_saver.__enter__ = MagicMock(return_value=mock_saver)
        mock_saver.__exit__ = MagicMock(return_value=False)

        mock_graph = MagicMock()
        mock_graph.compile.return_value = mock_compiled

        loop = SceneLoop.__new__(SceneLoop)
        loop.scene_id = scene_id
        loop.story_id = story_id
        loop.max_turns = 50
        loop._graph = mock_graph

        with patch("monitor_agents.loops.scene_loop.MongoDBSaver") as mock_cls:
            mock_cls.from_conn_string.return_value = mock_saver
            await loop.run(user_input="x")

        call_kwargs = mock_compiled.ainvoke.call_args
        config = call_kwargs[1]["config"] if call_kwargs[1] else call_kwargs[0][1]
        assert config["configurable"]["thread_id"] == str(scene_id)


class TestSceneLoopFinalize:
    @pytest.mark.asyncio
    async def test_finalize_invokes_with_scene_complete_true(self):
        from monitor_agents.loops.scene_loop import SceneLoop

        scene_id = uuid4()
        story_id = uuid4()

        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value={})

        mock_saver = MagicMock()
        mock_saver.__enter__ = MagicMock(return_value=mock_saver)
        mock_saver.__exit__ = MagicMock(return_value=False)

        mock_graph = MagicMock()
        mock_graph.compile.return_value = mock_compiled

        loop = SceneLoop.__new__(SceneLoop)
        loop.scene_id = scene_id
        loop.story_id = story_id
        loop.max_turns = 50
        loop._graph = mock_graph

        with patch("monitor_agents.loops.scene_loop.MongoDBSaver") as mock_cls:
            mock_cls.from_conn_string.return_value = mock_saver
            await loop.finalize()

        payload = mock_compiled.ainvoke.call_args[0][0]
        assert payload["scene_complete"] is True

    @pytest.mark.asyncio
    async def test_finalize_does_not_pass_user_input(self):
        from monitor_agents.loops.scene_loop import SceneLoop

        scene_id = uuid4()
        mock_compiled = AsyncMock()
        mock_compiled.ainvoke = AsyncMock(return_value={})

        mock_saver = MagicMock()
        mock_saver.__enter__ = MagicMock(return_value=mock_saver)
        mock_saver.__exit__ = MagicMock(return_value=False)

        mock_graph = MagicMock()
        mock_graph.compile.return_value = mock_compiled

        loop = SceneLoop.__new__(SceneLoop)
        loop.scene_id = scene_id
        loop.story_id = uuid4()
        loop.max_turns = 50
        loop._graph = mock_graph

        with patch("monitor_agents.loops.scene_loop.MongoDBSaver") as mock_cls:
            mock_cls.from_conn_string.return_value = mock_saver
            await loop.finalize()

        payload = mock_compiled.ainvoke.call_args[0][0]
        assert payload["user_input"] is None


# ---------------------------------------------------------------------------
# T-092: seed_actor_state falls back to actor_context for PC stats
# ---------------------------------------------------------------------------


class TestSeedActorStateActorContext:
    """The bound PC is often not linked into the scene's entity list, so its
    stats must seed from the resolved actor_context (CharacterContext)."""

    def test_seeds_from_actor_context_when_actor_absent_from_scene(self):
        from monitor_agents.loops.scene_support import seed_actor_state

        actor_id = uuid4()
        # Scene contains only an NPC (no stats), not the PC.
        entity_context = [{"entity_id": str(uuid4()), "name": "Barnaby", "properties": {}}]
        actor_context = {
            "id": str(actor_id),
            "attributes": {"Grit": 12, "Wits": 14},
            "resources": {"Health": {"current": 10, "max": 10}},
        }

        base_stats, resources = seed_actor_state(entity_context, actor_id, {}, actor_context=actor_context)

        assert base_stats == {"Grit": 12, "Wits": 14}
        assert "Health" in resources

    def test_scene_entity_stats_win_when_actor_present(self):
        from monitor_agents.loops.scene_support import seed_actor_state

        actor_id = uuid4()
        entity_context = [
            {"entity_id": str(actor_id), "name": "PC", "properties": {"attributes": {"Grit": 9}}},
        ]
        actor_context = {"id": str(actor_id), "attributes": {"Grit": 99}, "resources": {}}

        base_stats, _ = seed_actor_state(entity_context, actor_id, {}, actor_context=actor_context)

        # The actor IS in the scene with its own stats — those take precedence.
        assert base_stats == {"Grit": 9}

    def test_no_actor_context_is_backward_compatible(self):
        from monitor_agents.loops.scene_support import seed_actor_state

        entity_context = [{"entity_id": str(uuid4()), "properties": {}}]
        base_stats, resources = seed_actor_state(entity_context, uuid4(), {})
        assert base_stats == {}
        assert resources == {}


# =============================================================================
# Combat Resource Delta Extraction (T-092 carryover fix)
# =============================================================================


class TestExtractCombatResourceDeltas:
    """Verify HP deltas from combat results are extracted for working state."""

    def test_pc_takes_damage_emits_negative_delta(self):
        from monitor_agents.loops.scene_loop import _extract_combat_resource_deltas

        pc_id = str(uuid4())
        combat_result = {
            "combatants": [
                {"entity_id": pc_id, "is_pc": True, "hp_current": 7, "hp_max": 10},
                {"entity_id": str(uuid4()), "is_pc": False, "hp_current": 5, "hp_max": 10},
            ],
        }
        entity_context = [
            {"id": pc_id, "properties": {"hp_current": 10}},
        ]

        deltas = _extract_combat_resource_deltas(combat_result, entity_context)

        assert len(deltas) == 1
        assert deltas[0]["resource_key"] == "HP"
        assert deltas[0]["delta"] == -3  # 7 - 10 = -3
        assert deltas[0]["source"] == "combat"

    def test_pc_unchanged_emits_no_delta(self):
        from monitor_agents.loops.scene_loop import _extract_combat_resource_deltas

        pc_id = str(uuid4())
        combat_result = {
            "combatants": [
                {"entity_id": pc_id, "is_pc": True, "hp_current": 10, "hp_max": 10},
            ],
        }
        entity_context = [
            {"id": pc_id, "properties": {"hp_current": 10}},
        ]

        deltas = _extract_combat_resource_deltas(combat_result, entity_context)
        assert deltas == []

    def test_npc_damage_ignored(self):
        """Only PC HP changes are emitted as resource deltas."""
        from monitor_agents.loops.scene_loop import _extract_combat_resource_deltas

        npc_id = str(uuid4())
        combat_result = {
            "combatants": [
                {"entity_id": npc_id, "is_pc": False, "hp_current": 0, "hp_max": 10},
            ],
        }
        entity_context = [
            {"id": npc_id, "properties": {"hp_current": 10}},
        ]

        deltas = _extract_combat_resource_deltas(combat_result, entity_context)
        assert deltas == []

    def test_empty_combat_result_returns_empty(self):
        from monitor_agents.loops.scene_loop import _extract_combat_resource_deltas

        assert _extract_combat_resource_deltas({}, []) == []
        assert _extract_combat_resource_deltas(None, []) == []

    def test_pc_healed_emits_positive_delta(self):
        from monitor_agents.loops.scene_loop import _extract_combat_resource_deltas

        pc_id = str(uuid4())
        combat_result = {
            "combatants": [
                {"entity_id": pc_id, "is_pc": True, "hp_current": 12, "hp_max": 15},
            ],
        }
        entity_context = [
            {"id": pc_id, "properties": {"hp_current": 8}},
        ]

        deltas = _extract_combat_resource_deltas(combat_result, entity_context)

        assert len(deltas) == 1
        assert deltas[0]["delta"] == 4  # 12 - 8 = +4 (healing)


class TestCombatIntegrationMergesDeltas:
    """G-3: verify that combat HP deltas are merged into the scene loop result."""

    def test_combat_result_deltas_merged_into_resource_deltas(self):
        """When _run_combat returns a combat_result with HP changes, the
        scene loop should merge those into result['resource_deltas'] via
        _extract_combat_resource_deltas."""
        from monitor_agents.loops.scene_loop import _extract_combat_resource_deltas

        # Simulate the scene loop flow: combat result comes back with HP changes
        pc_id = str(uuid4())
        combat_result = {
            "narrative_text": "The goblin strikes you for 3 damage!",
            "combat_active": False,
            "victory_side": "pc",
            "combatants": [
                {"entity_id": pc_id, "is_pc": True, "hp_current": 7, "hp_max": 10},
                {"entity_id": str(uuid4()), "is_pc": False, "hp_current": 0, "hp_max": 5},
            ],
            "round_number": 2,
        }
        entity_context = [
            {"id": pc_id, "name": "Hero", "properties": {"hp_current": 10, "role": "PC"}},
            {"id": str(uuid4()), "name": "Goblin", "properties": {"hp_current": 5}},
        ]

        # Extract deltas (this is what the scene loop does after combat)
        combat_deltas = _extract_combat_resource_deltas(combat_result, entity_context)

        # Simulate merging into result
        result = {
            "narrative_text": "You swing your sword.",
            "resource_deltas": [],
        }
        if combat_deltas:
            existing = result.get("resource_deltas") or []
            existing.extend(combat_deltas)
            result["resource_deltas"] = existing

        # Verify the HP delta is in the result
        assert len(result["resource_deltas"]) == 1
        assert result["resource_deltas"][0]["resource_key"] == "HP"
        assert result["resource_deltas"][0]["delta"] == -3  # 7 - 10 = -3
        assert result["resource_deltas"][0]["source"] == "combat"

    def test_combat_narrative_appended_to_scene_narrative(self):
        """The combat narrative should be appended to the scene narrative."""
        scene_narrative = "You swing your sword at the goblin."
        combat_narrative = "The goblin strikes back! You take 3 damage."

        # Simulate the scene loop's narrative merge
        result_narrative = scene_narrative + "\n\n" + combat_narrative

        assert "You swing your sword" in result_narrative
        assert "The goblin strikes back" in result_narrative
        assert "\n\n" in result_narrative


# ===========================================================================
# extract_memories node — resilience against LLM failures
#
# This node runs in the post-narrate fan-out alongside extract_new_entities
# and extract_facts. Unlike extract_new_entities (which already wraps its
# LLM call in try/except), extract_memories had NO exception handling —
# a provider failure (rate limit, quota, outage) here crashed the whole
# turn even though narration itself had already succeeded (or gracefully
# degraded to the GM's draft). Two upstream fixes in this same session
# (bootstrap_resume populating a real actor_context, and the Narrator's
# draft-fallback populating a real narrative_text) meant this node's
# early-return guard no longer always short-circuited — so the gap,
# previously masked, started firing for real. See
# docs/testing/OPEN_ISSUES_CHARACTER_PARSING.md for the timeline.
# ===========================================================================


class TestExtractMemoriesNodeResilience:
    @pytest.mark.asyncio
    async def test_extractor_failure_does_not_crash_the_turn(self):
        from monitor_agents.loops.scene_loop import SceneState, extract_memories

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="The chamber falls silent.",
            actor_context={"name": "Kira Shadowdancer"},
            resolution={"success_level": "success"},
        )

        with patch(
            "monitor_agents.extraction.memory_extraction.MemoryExtractor.forward",
            side_effect=RuntimeError("rate limit exceeded"),
        ):
            result = await extract_memories(state)

        assert result == {"memories_to_persist": []}

    @pytest.mark.asyncio
    async def test_extractor_success_returns_memories(self):
        from monitor_agents.loops.scene_loop import SceneState, extract_memories

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="The chamber falls silent.",
            actor_context={"name": "Kira Shadowdancer"},
            resolution={"success_level": "success"},
        )
        fake_memories = [{"content": "Learned the Prince's true identity."}]

        with patch(
            "monitor_agents.extraction.memory_extraction.MemoryExtractor.forward",
            return_value=fake_memories,
        ):
            result = await extract_memories(state)

        assert result == {"memories_to_persist": fake_memories}

    @pytest.mark.asyncio
    async def test_no_narrative_text_short_circuits_before_extractor_call(self):
        from monitor_agents.loops.scene_loop import SceneState, extract_memories

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="",
            actor_context={"name": "Kira Shadowdancer"},
        )
        with patch("monitor_agents.extraction.memory_extraction.MemoryExtractor.forward") as mock_forward:
            result = await extract_memories(state)

        assert result == {"memories_to_persist": []}
        mock_forward.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_actor_context_short_circuits_before_extractor_call(self):
        from monitor_agents.loops.scene_loop import SceneState, extract_memories

        state = SceneState(
            scene_id=uuid4(),
            story_id=uuid4(),
            narrative_text="The chamber falls silent.",
            actor_context=None,
        )
        with patch("monitor_agents.extraction.memory_extraction.MemoryExtractor.forward") as mock_forward:
            result = await extract_memories(state)

        assert result == {"memories_to_persist": []}
        mock_forward.assert_not_called()


# ===========================================================================
# narrate node — image suggestions (Task 9)
# ===========================================================================
# Suggestions are computed by the pure heuristics in
# monitor_agents.image_suggestions and travel as DATA on SceneState → narrate
# result → done-frame metadata. The agents package never imports or calls UI
# WebSocket functions (layer direction); scripts/check_layer_dependencies.py
# is the enforcement gate.
# ===========================================================================


class TestNarrateImageSuggestions:
    def test_scene_state_has_image_suggestions_field(self):
        (SceneState, *_) = _import_scene_loop()
        assert "image_suggestions" in SceneState.model_fields
        state = SceneState(scene_id=uuid4(), story_id=uuid4())
        assert state.image_suggestions == []

    @pytest.mark.asyncio
    async def test_narrate_returns_image_suggestions_key(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-1"},
        ):
            state = SceneState(scene_id=uuid4(), story_id=uuid4(), user_input="I wait.")
            result = await narrate(state)

        assert "image_suggestions" in result
        assert result["image_suggestions"] == []

    @pytest.mark.asyncio
    async def test_narrate_populates_suggestion_on_location_trigger(self):
        """Third turn + a current location → one location_change suggestion,
        sourced from this turn's id."""
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        loc_id = uuid4()
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-123"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I step inside.",
                turns_count=2,  # this narrate produces turn 3 — a cadence window
                turn_context={"location_name": "The Rusted Flagon"},
                entity_context=[{"id": str(loc_id), "entity_type": "location", "name": "The Rusted Flagon"}],
            )
            result = await narrate(state)

        suggestions = result["image_suggestions"]
        assert len(suggestions) == 1
        s = suggestions[0]
        assert s["reason"] == "location_change"
        assert s["asset_type"] == "location"
        assert s["subject_entity_ids"] == [str(loc_id)]
        assert s["source_turn_id"] == "turn-123"

    @pytest.mark.asyncio
    async def test_narrate_uses_previous_turns_for_turn_number(self):
        """In production each run starts with turns_count=0 (the checkpoint is
        re-initialized per run), so the cadence turn number must also account
        for the MongoDB-backed previous_turns window."""
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-3"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I look around.",
                turns_count=0,
                previous_turns=[{"turn_id": "t1"}, {"turn_id": "t2"}],  # → turn 3, a window
                turn_context={"location_name": "Ashmarket"},
                entity_context=[],
            )
            result = await narrate(state)

        assert len(result["image_suggestions"]) == 1
        assert result["image_suggestions"][0]["reason"] == "location_change"

    @pytest.mark.asyncio
    async def test_narrate_accumulates_prior_suggestions(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        prior = {
            "suggestion_id": str(uuid4()),
            "asset_type": "scene",
            "subject_entity_ids": [],
            "reason": "climax",
            "aspect_ratio": "16:9",
            "source_turn_id": "turn-old",
        }
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-3"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I step inside.",
                turns_count=2,
                turn_context={"location_name": "Ashmarket"},
                image_suggestions=[prior],
            )
            result = await narrate(state)

        # Prior retained first, the new location suggestion appended.
        assert result["image_suggestions"][0]["suggestion_id"] == prior["suggestion_id"]
        assert len(result["image_suggestions"]) == 2
        assert result["image_suggestions"][1]["reason"] == "location_change"

    @pytest.mark.asyncio
    async def test_narrate_respects_scene_cap(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()

        def _prior(reason: str, subject: str) -> dict:
            return {
                "suggestion_id": str(uuid4()),
                "asset_type": "portrait",
                "subject_entity_ids": [subject],
                "reason": reason,
                "aspect_ratio": "1:1",
                "source_turn_id": "turn-old",
            }

        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-9"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I step inside.",
                turns_count=8,
                turn_context={"location_name": "Ashmarket"},
                image_suggestions=[_prior("npc_entry", str(uuid4())), _prior("climax", str(uuid4()))],
            )
            result = await narrate(state)

        # Cap of 2 per scene reached — nothing new appended.
        assert len(result["image_suggestions"]) == 2

    @pytest.mark.asyncio
    async def test_narrate_appearance_change_in_resolution_triggers_portrait(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        actor_id = uuid4()
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-3"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I tear off the disguise.",
                turns_count=2,
                actor_id=actor_id,
                resolution={"effects": ["appearance_changed: disguise discarded"]},
            )
            result = await narrate(state)

        suggestions = result["image_suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["reason"] == "visual_state_change"
        assert suggestions[0]["asset_type"] == "portrait"
        assert suggestions[0]["subject_entity_ids"] == [str(actor_id)]

    @pytest.mark.asyncio
    async def test_narrate_ordinary_dialogue_turn_suggests_nothing(self):
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": '"Not today," she says.', "proposals": [], "turn_id": "turn-3"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input='"Why not?" I ask.',
                turns_count=2,
                turn_context={"location_name": "", "npcs_present": []},
                pacing={"tempo": 0.5, "phase": "rising"},
            )
            result = await narrate(state)

        assert result["image_suggestions"] == []

    @pytest.mark.asyncio
    async def test_narrate_fires_location_change_without_turn_context(self):
        """Fix round 1: turn_context is never populated in production, so the
        location_name signal must be derived from entity_context inside narrate.
        """
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        loc_id = uuid4()
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-3"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I step inside.",
                turns_count=2,
                turn_context=None,  # production never populates this
                entity_context=[{"id": str(loc_id), "entity_type": "location", "name": "The Rusted Flagon"}],
            )
            result = await narrate(state)

        suggestions = result["image_suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["reason"] == "location_change"
        assert suggestions[0]["subject_entity_ids"] == [str(loc_id)]

    @pytest.mark.asyncio
    async def test_narrate_fires_npc_entry_from_npc_profiles_without_turn_context(self):
        """Fix round 1: npcs_present must come from npc_profiles when turn_context
        is empty, so first-time NPC entrances still trigger portrait suggestions.
        """
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        actor_id = uuid4()
        npc_id = uuid4()
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-3"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input='"Well met," I say.',
                turns_count=2,
                turn_context=None,
                actor_id=actor_id,
                npc_profiles={
                    str(npc_id): {"entity_id": str(npc_id), "name": "Mira"},
                },
            )
            result = await narrate(state)

        suggestions = result["image_suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["reason"] == "npc_entry"
        assert suggestions[0]["subject_entity_ids"] == [str(npc_id)]

    @pytest.mark.asyncio
    async def test_narrate_dedupes_npc_entry_against_scene_loop_instance_history(self):
        """Fix round 1: dedupe must survive the per-run state reset. The
        SceneLoop instance's suggestion history is the durable cross-turn store.
        """
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        from monitor_agents.loops.scene_loop import (
            SceneLoop,
            _IMAGE_SUGGESTION_HISTORY,
        )

        scene_id = uuid4()
        npc_id = uuid4()
        prior = ImageSuggestion(
            suggestion_id=uuid4(),
            asset_type="portrait",
            subject_entity_ids=[npc_id],
            reason="npc_entry",
            aspect_ratio="1:1",
            source_turn_id="turn-old",
        )
        SceneLoop(scene_id=scene_id, story_id=uuid4())
        _IMAGE_SUGGESTION_HISTORY[scene_id].append(prior)
        try:
            with patch(
                "monitor_agents.narrator.agent.Narrator.narrate_turn",
                new_callable=AsyncMock,
                return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-3"},
            ):
                state = SceneState(
                    scene_id=scene_id,
                    story_id=uuid4(),
                    user_input='"Well met again," I say.',
                    turns_count=2,
                    turn_context=None,
                    image_suggestions=[],  # state channel resets; history lives on the loop
                    npc_profiles={str(npc_id): {"entity_id": str(npc_id), "name": "Mira"}},
                )
                result = await narrate(state)

            # No new suggestion — NPC was already suggested, dedupe held.
            assert result["image_suggestions"] == []
        finally:
            _IMAGE_SUGGESTION_HISTORY.pop(scene_id, None)

    @pytest.mark.asyncio
    async def test_narrate_fires_climax_when_durable_turn_count_meets_pacing(self):
        """Fix round 1: pacing.phase is always 'setup' from compute_pacing in
        production because turns_count resets. narrate must compute the climax
        phase from a durable count instead.
        """
        (SceneState, _, _, _, narrate, *_) = _import_scene_loop()
        with patch(
            "monitor_agents.narrator.agent.Narrator.narrate_turn",
            new_callable=AsyncMock,
            return_value={"narrative_text": "...", "proposals": [], "turn_id": "turn-3"},
        ):
            state = SceneState(
                scene_id=uuid4(),
                story_id=uuid4(),
                user_input="I charge.",
                turns_count=0,  # would be "setup" via compute_pacing
                previous_turns=[{"turn_id": "t1"}, {"turn_id": "t2"}],  # → turn_number = 3
                durable_turn_count=2,  # confirms 3rd turn is real
                pending_proposals=[{"proposal_id": "p-1"}],  # required for peak
                turn_context=None,
                pacing={"tempo": 0.8, "phase": "setup"},  # tempo high enough; phase wrong
            )
            result = await narrate(state)

        suggestions = result["image_suggestions"]
        assert len(suggestions) == 1
        assert suggestions[0]["reason"] == "climax"
