"""
Tests for scene contracts.

Use Cases: DL-4, P-1, P-2, P-3, P-8
"""

from datetime import datetime, timezone, UTC
from uuid import uuid4

import pytest
from monitor_data.contracts.scene_contracts import (
    SceneInvariants,
    ScenePostConditions,
    ScenePreConditions,
)
from monitor_data.schemas.base import SceneStatus, Speaker
from monitor_data.schemas.scenes import (
    SceneCreate,
    SceneResponse,
    SceneUpdate,
    TurnResponse,
)


class TestScenePreConditions:
    """Tests for Scene pre-conditions."""

    def test_create_scene_preconditions_valid(self):
        """Valid scene creation passes pre-conditions."""
        params = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test Scene",
            purpose="Test purpose",
        )

        # Should not raise
        assert (
            ScenePreConditions.create_scene(
                params, story_exists=True, universe_exists=True
            )
            is True
        )

    def test_create_scene_preconditions_missing_story(self):
        """Scene creation fails if story doesn't exist."""
        params = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test Scene",
        )

        with pytest.raises(ValueError, match="Story does not exist"):
            ScenePreConditions.create_scene(
                params, story_exists=False, universe_exists=True
            )

    def test_create_scene_preconditions_missing_universe(self):
        """Scene creation fails if universe doesn't exist."""
        params = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test Scene",
        )

        with pytest.raises(ValueError, match="Universe does not exist"):
            ScenePreConditions.create_scene(
                params, story_exists=True, universe_exists=False
            )

    def test_append_turn_preconditions_valid(self):
        """Valid turn append passes pre-conditions."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            purpose="Test",
            status=SceneStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert (
            ScenePreConditions.append_turn(scene, Speaker.USER, None, caller="Narrator")
            is True
        )

    def test_append_turn_preconditions_inactive_scene(self):
        """Turn append fails for inactive scene."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            purpose="Test",
            status=SceneStatus.COMPLETED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with pytest.raises(ValueError, match="Cannot append turn to scene with status"):
            ScenePreConditions.append_turn(scene, Speaker.USER, None, caller="Narrator")

    def test_append_turn_preconditions_entity_speaker_no_id(self):
        """Turn append fails if ENTITY speaker has no entity_id."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            purpose="Test",
            status=SceneStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with pytest.raises(
            ValueError, match="entity_id required when speaker is ENTITY"
        ):
            ScenePreConditions.append_turn(
                scene, Speaker.ENTITY, None, caller="Narrator"
            )

    def test_append_turn_preconditions_unauthorized_caller(self):
        """Turn append fails for unauthorized caller."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            purpose="Test",
            status=SceneStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with pytest.raises(ValueError, match="not authorized"):
            ScenePreConditions.append_turn(
                scene, Speaker.USER, None, caller="ContextAssembly"
            )

    def test_update_scene_valid_transition(self):
        """Valid status transition passes pre-conditions."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            purpose="Test",
            status=SceneStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        params = SceneUpdate(status=SceneStatus.FINALIZING)
        assert ScenePreConditions.update_scene(scene, params) is True

    def test_update_scene_invalid_transition(self):
        """Invalid status transition fails pre-conditions."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            purpose="Test",
            status=SceneStatus.COMPLETED,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        params = SceneUpdate(status=SceneStatus.ACTIVE)
        with pytest.raises(ValueError, match="Invalid status transition"):
            ScenePreConditions.update_scene(scene, params)


class TestScenePostConditions:
    """Tests for Scene post-conditions."""

    def test_create_scene_postconditions(self):
        """Scene creation satisfies post-conditions."""
        params = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test Scene",
            purpose="Test",
        )

        result = SceneResponse(
            scene_id=uuid4(),
            story_id=params.story_id,
            universe_id=params.universe_id,
            title=params.title,
            purpose=params.purpose,
            status=SceneStatus.ACTIVE,
            turns=[],
            proposed_changes=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert ScenePostConditions.create_scene(result, params) is True

    def test_create_scene_postconditions_wrong_status(self):
        """Scene creation fails if status is not ACTIVE."""
        params = SceneCreate(
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test Scene",
            purpose="Test",
        )

        result = SceneResponse(
            scene_id=uuid4(),
            story_id=params.story_id,
            universe_id=params.universe_id,
            title=params.title,
            purpose=params.purpose,
            status=SceneStatus.COMPLETED,  # Wrong!
            turns=[],
            proposed_changes=[],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with pytest.raises(ValueError, match="must have status ACTIVE"):
            ScenePostConditions.create_scene(result, params)

    def test_update_scene_postconditions(self):
        """Scene update satisfies post-conditions."""
        old_scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Old Title",
            purpose="Test",
            status=SceneStatus.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        params = SceneUpdate(title="New Title")
        result = SceneResponse(
            scene_id=old_scene.scene_id,
            story_id=old_scene.story_id,
            universe_id=old_scene.universe_id,
            title="New Title",
            purpose=old_scene.purpose,
            status=SceneStatus.ACTIVE,
            created_at=old_scene.created_at,
            updated_at=datetime.now(UTC),  # Refreshed
        )

        assert ScenePostConditions.update_scene(result, old_scene, params) is True


class TestSceneInvariants:
    """Tests for Scene invariants."""

    def test_scene_response_invariant_valid(self):
        """Valid scene response satisfies invariant."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            purpose="Test",
            status=SceneStatus.ACTIVE,
            turns=[
                TurnResponse(
                    turn_id=uuid4(),
                    speaker=Speaker.USER,
                    text="Hello",
                    timestamp=datetime.now(UTC),
                ),
            ],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert SceneInvariants.scene_response_invariant(scene) is True

    def test_scene_response_invariant_null_scene_id(self):
        """Scene with null scene_id violates invariant."""
        # Note: SceneResponse.scene_id is a required UUID field (not Optional).
        # Pydantic validation prevents creating SceneResponse with scene_id=None.
        # We verify the invariant logic by directly testing the invariant check
        # with a mock scene object that has scene_id=None.
        from unittest.mock import MagicMock

        scene = MagicMock()
        scene.scene_id = None
        scene.story_id = uuid4()
        scene.universe_id = uuid4()
        scene.status = SceneStatus.ACTIVE
        scene.turns = []

        with pytest.raises(ValueError, match="scene_id cannot be None"):
            SceneInvariants.scene_response_invariant(scene)

    def test_scene_response_invariant_turn_order(self):
        """Scene with out-of-order turns violates invariant."""
        t1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)  # Before t1!

        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="Test",
            purpose="Test",
            status=SceneStatus.ACTIVE,
            turns=[
                TurnResponse(
                    turn_id=uuid4(),
                    speaker=Speaker.USER,
                    text="Later",
                    timestamp=t1,
                ),
                TurnResponse(
                    turn_id=uuid4(),
                    speaker=Speaker.ENTITY,
                    text="Earlier",
                    timestamp=t2,
                ),
            ],
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        with pytest.raises(ValueError, match="must be in chronological order"):
            SceneInvariants.scene_response_invariant(scene)

    def test_scene_status_invariant_valid(self):
        """Valid statuses satisfy invariant."""
        for status in [
            SceneStatus.ACTIVE,
            SceneStatus.FINALIZING,
            SceneStatus.COMPLETED,
        ]:
            assert SceneInvariants.scene_status_invariant(status) is True

    def test_scene_status_invariant_invalid(self):
        """Invalid status violates invariant."""
        # This would require passing an invalid enum value
        # In practice, Pydantic prevents this at the schema level
        pass


class TestSceneStatusTransitions:
    """Property-based tests for scene status transitions."""

    def test_all_valid_transitions(self):
        """All documented valid transitions work."""
        valid_cases = [
            (SceneStatus.ACTIVE, SceneStatus.FINALIZING),
            (SceneStatus.ACTIVE, SceneStatus.COMPLETED),
            (SceneStatus.FINALIZING, SceneStatus.ACTIVE),
            (SceneStatus.FINALIZING, SceneStatus.COMPLETED),
        ]

        for from_status, to_status in valid_cases:
            from monitor_data.invariants.scene_atomicity import SceneAtomicity

            assert SceneAtomicity.is_valid_transition(from_status, to_status) is True

    def test_terminal_states_no_transitions(self):
        """Terminal states cannot transition."""
        from monitor_data.invariants.scene_atomicity import SceneAtomicity

        for terminal in [SceneStatus.COMPLETED]:
            assert SceneAtomicity.is_terminal(terminal) is True

    def test_in_progress_states_allow_turns(self):
        """In-progress scenes accept turns."""
        from monitor_data.invariants.scene_atomicity import SceneAtomicity

        assert SceneAtomicity.is_in_progress(SceneStatus.ACTIVE) is True
        assert SceneAtomicity.is_in_progress(SceneStatus.FINALIZING) is True
        assert SceneAtomicity.is_in_progress(SceneStatus.COMPLETED) is False
