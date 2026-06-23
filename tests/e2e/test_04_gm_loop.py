"""
E2E Test 04 — GM Loop / Solo Play (P-1..P-5, P-8)

Exercises the core play path after the world + system fixtures are in place:
  story fixture → scene fixture → Resolver → Narrator → SceneLoop checkpointing

Use cases covered
-----------------
P-1  Start new story (via ``e2e_story`` fixture)
P-2  Start scene (via ``e2e_scene`` fixture)
P-3  Turn loop / core gameplay
P-4  Resolve player action
P-5  Handle dialogue / narration
P-8  Canonize a scene checkpoint on finalize
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.e2e
@pytest.mark.integration
class TestResolverAndSceneLoop:
    """Core GM-loop coverage for the playable story path."""

    @pytest.mark.asyncio
    async def test_resolver_resolve_turn_returns_structured_outcome(
        self,
        seeded_world: Dict[str, Any],
    ) -> None:
        """P-4: Resolver returns a complete outcome payload for an action turn."""
        from monitor_agents.resolver import Resolver

        resolver = Resolver()
        result = await resolver.resolve_turn(
            scene_id=str(seeded_world["universe_id"]),
            user_input="I kick open the cellar door and search for cultists.",
            play_mode="dice_standard",
            context={
                "entities": [
                    {
                        "name": "Aldric the Bold",
                        "properties": {
                            "attributes": {
                                "Strength": 16,
                                "Dexterity": 12,
                                "Wisdom": 10,
                                "Charisma": 10,
                            }
                        },
                    }
                ],
                "turns": [],
            },
        )

        assert result["action_type"] == "action"
        assert result["success_level"] in {
            "success",
            "failure",
            "partial_success",
            "critical_success",
            "critical_failure",
        }
        # The resolver may classify the action as trivial/auto (no roll) or
        # roll dice — both are valid structured outcomes; dice stay in range.
        assert result["resolution_type"] in {
            "dice",
            "trivial",
            "auto_success",
            "narrative",
            "propose_roll",
        }
        if result["roll_total"] is not None:
            assert 1 <= result["roll_total"] <= 30
        assert result["roll_breakdown"]
        assert result["stat"]
        assert result["difficulty_class"]

    @pytest.mark.asyncio
    async def test_scene_loop_runs_action_turn_and_returns_narrative(
        self,
        e2e_story: Any,
        e2e_scene: Any,
        mock_context_assembly,
        mock_dspy_narrator,
        mock_narrator_llm,
    ) -> None:
        """P-3/P-4/P-5: A single action turn produces GM narrative and proposals."""
        from monitor_agents.loops.scene_loop import SceneLoop

        loop = SceneLoop(
            scene_id=e2e_scene.scene_id,
            story_id=e2e_story.id,
            max_turns=3,
        )
        result = await loop.run("I follow the hooded stranger into the alley.")

        assert result["narrative_text"]
        assert "hooded stranger" in result["narrative_text"].lower()
        assert result["turns_count"] == 1
        assert isinstance(result.get("pending_proposals", []), list)

    @pytest.mark.asyncio
    async def test_scene_loop_persists_player_and_gm_turns(
        self,
        e2e_story: Any,
        e2e_scene: Any,
        mock_context_assembly,
        mock_dspy_narrator,
        mock_narrator_llm,
    ) -> None:
        """P-3: Running the scene loop persists the exchange into MongoDB."""
        from monitor_agents.loops.scene_loop import SceneLoop
        from monitor_data.tools.mongodb_tools import mongodb_get_scene

        loop = SceneLoop(
            scene_id=e2e_scene.scene_id,
            story_id=e2e_story.id,
            max_turns=3,
        )
        await loop.run("I ask the stranger about the missing prince.")

        scene = mongodb_get_scene(e2e_scene.scene_id)
        assert scene is not None
        assert len(scene.turns) >= 2
        assert scene.turns[-2].speaker.value == "user"
        assert scene.turns[-1].speaker.value == "gm"
        assert scene.turns[-1].text.strip()

    @pytest.mark.asyncio
    async def test_scene_loop_finalize_triggers_canonization_checkpoint(
        self,
        e2e_story: Any,
        e2e_scene: Any,
        mock_context_assembly,
        mock_dspy_narrator,
        mock_narrator_llm,
    ) -> None:
        """P-8: Finalizing a scene triggers the canonization checkpoint."""
        from monitor_agents.canonkeeper import CanonKeeper
        from monitor_agents.loops.scene_loop import SceneLoop

        loop = SceneLoop(
            scene_id=e2e_scene.scene_id,
            story_id=e2e_story.id,
            max_turns=3,
        )
        await loop.run("I agree to meet the stranger at midnight.")

        with patch.object(
            CanonKeeper,
            "evaluate_proposals",
            new_callable=AsyncMock,
            return_value=[],
        ) as evaluate_mock:
            await loop.finalize()

        evaluate_mock.assert_awaited()
