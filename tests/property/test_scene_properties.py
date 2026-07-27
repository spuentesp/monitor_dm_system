"""
Property-based tests for scene and turn sequence invariants.

These tests use Hypothesis to verify that scene state transitions and
turn ordering rules hold across thousands of randomly generated sequences.

Key invariants tested:
  - SceneStatus: valid transitions only (ACTIVE→FINALIZING→COMPLETED, no back-transitions from COMPLETED)
  - Turn ordering: chronological timestamps, Speaker validation
  - TurnResponse: entity_id required for ENTITY speaker
  - SceneResponse: new scenes start ACTIVE with empty turns

Use Cases: DL-4, P-1, P-2, P-3
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone, UTC
from uuid import UUID, uuid4

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from monitor_data.contracts.scene_contracts import (
    SceneInvariants,
    ScenePostConditions,
    ScenePreConditions,
)
from monitor_data.schemas.base import SceneStatus, Speaker, TemporalMode
from monitor_data.schemas.scenes import (
    SceneCreate,
    SceneResponse,
    SceneUpdate,
    TurnCreate,
    TurnResponse,
)

# =============================================================================
# CUSTOM STRATEGIES
# =============================================================================


def naive_timestamp_strategy() -> st.SearchStrategy[datetime]:
    """Generate valid naive datetime values (Hypothesis datetimes() prohibits tzinfo)."""
    return st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
    )


def turn_response_strategy() -> st.SearchStrategy[TurnResponse]:
    """Generate valid TurnResponse instances."""
    return st.builds(
        TurnResponse,
        turn_id=st.uuids(),
        speaker=st.sampled_from(list(Speaker)),
        entity_id=st.none() | st.uuids(),
        text=st.text(min_size=1, max_size=500),
        timestamp=naive_timestamp_strategy(),
    )


def scene_response_with_turns_strategy(
    num_turns: int = 3,
) -> st.SearchStrategy[SceneResponse]:
    """Generate SceneResponse instances with chronologically ordered turns."""
    base_time = datetime(2025, 1, 1, tzinfo=UTC)
    # Generate distinct, ordered timestamps
    offsets = st.lists(
        st.integers(min_value=0, max_value=86400),
        min_size=num_turns,
        max_size=num_turns,
        unique=True,
    ).map(sorted)

    return st.builds(
        SceneResponse,
        scene_id=st.just(uuid4()),
        story_id=st.just(uuid4()),
        universe_id=st.just(uuid4()),
        title=st.text(min_size=1, max_size=200),
        purpose=st.text(min_size=0, max_size=1000),
        status=st.sampled_from(list(SceneStatus)),
        temporal_mode=st.sampled_from(list(TemporalMode)),
        created_at=st.just(base_time),
        updated_at=st.just(base_time + timedelta(hours=1)),
        turns=offsets.map(
            lambda off: [
                TurnResponse(
                    turn_id=uuid4(),
                    speaker=Speaker.USER if i % 2 == 0 else Speaker.GM,
                    text=f"Turn {i}",
                    timestamp=base_time + timedelta(seconds=off[i]),
                )
                for i in range(num_turns)
            ]
        ),
        proposed_changes=st.just([]),
    )


def valid_status_transition_strategy() -> st.SearchStrategy[
    tuple[SceneStatus, SceneStatus]
]:
    """Generate pairs of (from_status, to_status) representing valid transitions."""
    return st.sampled_from(
        [
            (SceneStatus.ACTIVE, SceneStatus.FINALIZING),
            (SceneStatus.ACTIVE, SceneStatus.COMPLETED),
            (SceneStatus.FINALIZING, SceneStatus.ACTIVE),
            (SceneStatus.FINALIZING, SceneStatus.COMPLETED),
        ]
    )


# =============================================================================
# TESTS: SceneStatus Transitions
# =============================================================================


class TestSceneStatusTransitionProperties:
    """Property-based tests for scene status transitions."""

    @given(transition=valid_status_transition_strategy())
    @settings(max_examples=50, deadline=1000)
    def test_valid_transitions_accepted(
        self, transition: tuple[SceneStatus, SceneStatus]
    ) -> None:
        """Valid status transitions are accepted by the pre-condition check."""
        from_status, to_status = transition
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="test",
            purpose="testing valid transitions",
            status=from_status,
            temporal_mode=TemporalMode.PRESENT,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            turns=[],
            proposed_changes=[],
        )
        update = SceneUpdate(status=to_status)
        # Should not raise
        result = ScenePreConditions.update_scene(scene, update)
        assert result is True

    @given(
        from_status=st.just(SceneStatus.COMPLETED),
        to_status=st.sampled_from(list(SceneStatus)),
    )
    @settings(max_examples=50, deadline=1000)
    def test_completed_is_terminal(
        self, from_status: SceneStatus, to_status: SceneStatus
    ) -> None:
        """COMPLETED is a terminal state — no transitions out."""
        assume(to_status != SceneStatus.COMPLETED)  # Only test outgoing
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="test",
            purpose="testing terminal state",
            status=from_status,
            temporal_mode=TemporalMode.PRESENT,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            turns=[],
            proposed_changes=[],
        )
        update = SceneUpdate(status=to_status)
        with pytest.raises(ValueError, match="Invalid status transition"):
            ScenePreConditions.update_scene(scene, update)

    @given(
        from_status=st.just(SceneStatus.ACTIVE),
        to_status=st.just(SceneStatus.ACTIVE),
    )
    @settings(max_examples=10, deadline=1000)
    def test_active_to_active_rejected(
        self, from_status: SceneStatus, to_status: SceneStatus
    ) -> None:
        """ACTIVE→ACTIVE is not a valid transition (no self-loop)."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=uuid4(),
            universe_id=uuid4(),
            title="test",
            purpose="testing no self-loop",
            status=from_status,
            temporal_mode=TemporalMode.PRESENT,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            turns=[],
            proposed_changes=[],
        )
        update = SceneUpdate(status=to_status)
        with pytest.raises(ValueError, match="Invalid status transition"):
            ScenePreConditions.update_scene(scene, update)


# =============================================================================
# TESTS: Turn Ordering
# =============================================================================


class TestTurnOrderingProperties:
    """Property-based tests for turn chronological ordering."""

    @given(scene=scene_response_with_turns_strategy(num_turns=5))
    @settings(max_examples=100, deadline=2000)
    def test_turns_in_chronological_order(self, scene: SceneResponse) -> None:
        """Turns must be in strict chronological order."""
        if len(scene.turns) > 1:
            for i in range(len(scene.turns) - 1):
                assert scene.turns[i].timestamp < scene.turns[i + 1].timestamp, (
                    f"Turn {i} ({scene.turns[i].timestamp}) >= Turn {i + 1} ({scene.turns[i + 1].timestamp})"
                )

    @given(scene=scene_response_with_turns_strategy(num_turns=5))
    @settings(max_examples=100, deadline=2000)
    def test_scene_invariant_accepts_ordered_turns(self, scene: SceneResponse) -> None:
        """SceneResponse invariant passes for chronologically ordered turns."""
        result = SceneInvariants.scene_response_invariant(scene)
        assert result is True

    @given(
        scene=scene_response_with_turns_strategy(num_turns=3),
        speaker=st.sampled_from(list(Speaker)),
        entity_id=st.none() | st.uuids(),
    )
    @settings(max_examples=100, deadline=2000)
    def test_append_turn_requires_active_scene(
        self, scene: SceneResponse, speaker: Speaker, entity_id: UUID | None
    ) -> None:
        """Turns can only be appended to ACTIVE scenes."""
        if scene.status == SceneStatus.ACTIVE:
            # ACTIVE scene: should accept (if speaker constraints met)
            if speaker == Speaker.ENTITY and entity_id is None:
                with pytest.raises(ValueError, match="entity_id required"):
                    ScenePreConditions.append_turn(
                        scene, speaker, entity_id, "Narrator"
                    )
            else:
                result = ScenePreConditions.append_turn(
                    scene, speaker, entity_id, "Narrator"
                )
                assert result is True
        else:
            # Non-ACTIVE scene: should reject
            with pytest.raises(ValueError, match="Cannot append turn"):
                ScenePreConditions.append_turn(scene, speaker, entity_id, "Narrator")

    @given(
        entity_id=st.none(),
    )
    @settings(max_examples=10, deadline=1000)
    def test_entity_speaker_requires_entity_id(self, entity_id: None) -> None:
        """ENTITY speaker must provide entity_id."""
        with pytest.raises(ValueError, match="entity_id required"):
            TurnCreate(
                speaker=Speaker.ENTITY,
                entity_id=entity_id,
                text="test",
            )


# =============================================================================
# TESTS: SceneCreate Post-Conditions
# =============================================================================


class TestSceneCreatePostConditions:
    """Property-based tests for scene creation post-conditions."""

    @given(
        story_id=st.uuids(),
        universe_id=st.uuids(),
        title=st.text(min_size=1, max_size=200),
        purpose=st.text(min_size=0, max_size=1000),
    )
    @settings(max_examples=50, deadline=2000)
    def test_new_scene_is_active_with_empty_turns(
        self, story_id: UUID, universe_id: UUID, title: str, purpose: str
    ) -> None:
        """A newly created SceneResponse has ACTIVE status and empty turns."""
        scene = SceneResponse(
            scene_id=uuid4(),
            story_id=story_id,
            universe_id=universe_id,
            title=title,
            purpose=purpose,
            status=SceneStatus.ACTIVE,
            temporal_mode=TemporalMode.PRESENT,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            turns=[],
            proposed_changes=[],
        )
        assert scene.status == SceneStatus.ACTIVE
        assert len(scene.turns) == 0
        assert len(scene.proposed_changes) == 0

    @given(
        story_id=st.uuids(),
        universe_id=st.uuids(),
        title=st.text(min_size=1, max_size=200),
        purpose=st.text(min_size=0, max_size=1000),
    )
    @settings(max_examples=50, deadline=2000)
    def test_post_condition_validates_new_scene(
        self, story_id: UUID, universe_id: UUID, title: str, purpose: str
    ) -> None:
        """Post-condition check passes for a valid new scene."""
        params = SceneCreate(
            story_id=story_id,
            universe_id=universe_id,
            title=title,
            purpose=purpose,
        )
        result = SceneResponse(
            scene_id=uuid4(),
            story_id=story_id,
            universe_id=universe_id,
            title=title,
            purpose=purpose,
            status=SceneStatus.ACTIVE,
            temporal_mode=TemporalMode.PRESENT,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            turns=[],
            proposed_changes=[],
        )
        post_result = ScenePostConditions.create_scene(result, params)
        assert post_result is True


# =============================================================================
# TESTS: TurnResponse
# =============================================================================


class TestTurnResponseProperties:
    """Property-based tests for TurnResponse invariants."""

    @given(turn=turn_response_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_turn_has_valid_speaker(self, turn: TurnResponse) -> None:
        """Every TurnResponse has a valid Speaker enum value."""
        assert isinstance(turn.speaker, Speaker)
        assert turn.speaker.value in {s.value for s in Speaker}

    @given(turn=turn_response_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_turn_id_is_valid_uuid(self, turn: TurnResponse) -> None:
        """Every TurnResponse has a valid UUID."""
        assert isinstance(turn.turn_id, UUID)

    @given(turn=turn_response_strategy())
    @settings(max_examples=200, deadline=2000)
    def test_turn_text_non_empty(self, turn: TurnResponse) -> None:
        """Every TurnResponse has non-empty text."""
        assert len(turn.text) > 0


# =============================================================================
# TESTS: Scene Invariants
# =============================================================================


class TestSceneInvariantProperties:
    """Property-based tests for scene-wide invariants."""

    @given(status=st.sampled_from(list(SceneStatus)))
    @settings(max_examples=20, deadline=1000)
    def test_scene_status_invariant_accepts_all(self, status: SceneStatus) -> None:
        """All SceneStatus values pass the status invariant."""
        result = SceneInvariants.scene_status_invariant(status)
        assert result is True

    @given(scene=scene_response_with_turns_strategy(num_turns=3))
    @settings(max_examples=100, deadline=2000)
    def test_turn_count_matches_header(self, scene: SceneResponse) -> None:
        """The turn_count invariant validates correctly."""
        actual_count = len(scene.turns)
        result = SceneInvariants.turn_response_invariant(actual_count, scene)
        assert result is True

    @given(scene=scene_response_with_turns_strategy(num_turns=3))
    @settings(max_examples=100, deadline=2000)
    def test_scene_has_required_references(self, scene: SceneResponse) -> None:
        """scene_id, story_id, universe_id are all set."""
        assert scene.scene_id is not None
        assert scene.story_id is not None
        assert scene.universe_id is not None
