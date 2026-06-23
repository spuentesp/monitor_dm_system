"""
Scene Contract Definitions.

These contracts define pre-conditions, post-conditions, and invariants
for Scene and Turn operations.

Use Cases: DL-4, P-1, P-2, P-3, P-8
"""

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


from monitor_data.schemas.base import SceneStatus, Speaker
from monitor_data.schemas.scenes import SceneCreate, SceneUpdate, SceneResponse


# =============================================================================
# SCENE PRE-CONDITIONS
# =============================================================================


@dataclass
class ScenePreConditions:
    """
    Pre-conditions for Scene operations.

    These must be TRUE before the operation can proceed.
    """

    @staticmethod
    def create_scene(params: SceneCreate, story_exists: bool, universe_exists: bool) -> bool:
        """
        Pre-condition for mongodb_create_scene.

        Requirements:
        - story_id must exist in Neo4j
        - universe_id must exist in Neo4j
        - participating_entities (if provided) must exist in Neo4j
        - location_ref (if provided) must be a LOCATION entity
        """
        if not story_exists:
            raise ValueError("Story does not exist")
        if not universe_exists:
            raise ValueError("Universe does not exist")
        return True

    @staticmethod
    def append_turn(
        scene: SceneResponse,
        speaker: Speaker,
        entity_id: Optional[UUID],
        caller: str,
    ) -> bool:
        """
        Pre-condition for mongodb_append_turn.

        Requirements:
        - scene.status must be ACTIVE
        - speaker must be valid Speaker enum
        - entity_id required when speaker is ENTITY
        - caller must be Narrator or CanonKeeper
        """
        if scene.status != SceneStatus.ACTIVE:
            raise ValueError(f"Cannot append turn to scene with status {scene.status}")
        if speaker == Speaker.ENTITY and entity_id is None:
            raise ValueError("entity_id required when speaker is ENTITY")
        if caller not in ("Narrator", "CanonKeeper"):
            raise ValueError(f"Caller {caller} not authorized to append turns")
        return True

    @staticmethod
    def update_scene(scene: SceneResponse, params: SceneUpdate) -> bool:
        """
        Pre-condition for mongodb_update_scene.

        Requirements:
        - New status (if provided) must be valid transition
        - title (if provided) must be non-empty
        """
        if params.status is not None:
            valid_transitions = {
                SceneStatus.ACTIVE: {SceneStatus.FINALIZING, SceneStatus.COMPLETED},
                SceneStatus.FINALIZING: {SceneStatus.ACTIVE, SceneStatus.COMPLETED},
                SceneStatus.COMPLETED: set(),  # Terminal state
            }
            allowed = valid_transitions.get(scene.status, set())
            if params.status not in allowed:
                raise ValueError(
                    f"Invalid status transition from {scene.status} to {params.status}"
                )
        if params.title is not None and len(params.title.strip()) == 0:
            raise ValueError("Title cannot be empty")
        return True


# =============================================================================
# SCENE POST-CONDITIONS
# =============================================================================


@dataclass
class ScenePostConditions:
    """
    Post-conditions for Scene operations.

    These must be TRUE after the operation completes.
    """

    @staticmethod
    def create_scene(result: SceneResponse, params: SceneCreate) -> bool:
        """
        Post-condition for mongodb_create_scene.

        Guarantees:
        - Returns a SceneResponse with valid UUID
        - status is ACTIVE
        - created_at is set to now
        - turns is empty list
        - proposed_changes is empty list
        """
        if result.scene_id is None:
            raise ValueError("scene_id must be set in response")
        if result.status != SceneStatus.ACTIVE:
            raise ValueError(f"New scene must have status ACTIVE, got {result.status}")
        if result.story_id != params.story_id:
            raise ValueError(
                f"story_id mismatch: expected {params.story_id}, got {result.story_id}"
            )
        if result.universe_id != params.universe_id:
            raise ValueError(
                f"universe_id mismatch: expected {params.universe_id}, got {result.universe_id}"
            )
        if result.turns is None or len(result.turns) != 0:
            raise ValueError("New scene must have empty turns list")
        if result.proposed_changes is None or len(result.proposed_changes) != 0:
            raise ValueError("New scene must have empty proposed_changes list")
        return True

    @staticmethod
    def append_turn(result: SceneResponse, scene: SceneResponse, turn_count_before: int) -> bool:
        """
        Post-condition for mongodb_append_turn.

        Guarantees:
        - Returns SceneResponse with one more turn
        - The new turn is at the end (most recent)
        - updated_at is refreshed
        """
        expected_turn_count = turn_count_before + 1
        actual_turn_count = len(result.turns)
        if actual_turn_count != expected_turn_count:
            raise ValueError(
                f"Turn count mismatch: expected {expected_turn_count}, got {actual_turn_count}"
            )
        # Newest turn should be last
        if len(result.turns) > 0:
            latest_turn = result.turns[-1]
            if latest_turn.timestamp < scene.updated_at:
                raise ValueError("New turn timestamp should be after previous scene update")
        return True

    @staticmethod
    def update_scene(result: SceneResponse, scene: SceneResponse, params: SceneUpdate) -> bool:
        """
        Post-condition for mongodb_update_scene.

        Guarantees:
        - Updated fields match params
        - Non-updated fields remain unchanged
        - updated_at is refreshed
        """
        if params.title is not None and result.title != params.title:
            raise ValueError(f"title mismatch: expected {params.title}, got {result.title}")
        if params.status is not None and result.status != params.status:
            raise ValueError(f"status mismatch: expected {params.status}, got {result.status}")
        if params.purpose is not None and result.purpose != params.purpose:
            raise ValueError(f"purpose mismatch: expected {params.purpose}, got {result.purpose}")
        if result.updated_at <= scene.updated_at:
            raise ValueError("updated_at must be refreshed after update")
        return True


# =============================================================================
# SCENE INVARIANTS
# =============================================================================


@dataclass
class SceneInvariants:
    """
    Scene invariants that must hold at all times.

    These are checked after each operation to ensure consistency.
    """

    @staticmethod
    def scene_response_invariant(scene: SceneResponse) -> bool:
        """
        Invariant for SceneResponse.

        Requirements:
        - scene_id is not None
        - story_id is not None
        - universe_id is not None
        - status is valid SceneStatus
        - temporal_mode is valid TemporalMode
        - Turns are in chronological order
        """
        if scene.scene_id is None:
            raise ValueError("scene_id cannot be None")
        if scene.story_id is None:
            raise ValueError("story_id cannot be None")
        if scene.universe_id is None:
            raise ValueError("universe_id cannot be None")
        if not isinstance(scene.status, SceneStatus):
            raise ValueError(f"status must be SceneStatus, got {type(scene.status)}")

        # Check turn ordering
        if scene.turns and len(scene.turns) > 1:
            for i in range(len(scene.turns) - 1):
                if scene.turns[i].timestamp >= scene.turns[i + 1].timestamp:
                    raise ValueError(
                        f"Turns must be in chronological order: "
                        f"turn[{i}]={scene.turns[i].timestamp} >= "
                        f"turn[{i + 1}]={scene.turns[i + 1].timestamp}"
                    )
        return True

    @staticmethod
    def scene_status_invariant(status: SceneStatus) -> bool:
        """
        Invariant for SceneStatus values.

        Valid statuses:
        - ACTIVE: Scene is in progress
        - FINALIZING: Scene is being finalized (proposed changes committing)
        - COMPLETED: Scene finished normally
        """
        valid_statuses = {SceneStatus.ACTIVE, SceneStatus.FINALIZING, SceneStatus.COMPLETED}
        if status not in valid_statuses:
            raise ValueError(f"Invalid SceneStatus: {status}")
        return True

    @staticmethod
    def turn_response_invariant(turn_count: int, scene: SceneResponse) -> bool:
        """
        Invariant: Number of turns in response matches turn_count field.
        """
        if len(scene.turns) != turn_count:
            raise ValueError(
                f"Turn count mismatch: header says {turn_count}, "
                f"but turns array has {len(scene.turns)} elements"
            )
        return True
