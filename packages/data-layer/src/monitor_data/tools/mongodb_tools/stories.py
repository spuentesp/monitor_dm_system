"""Auto-extracted MongoDB tools sub-module."""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.schemas.base import BeatStatus
from monitor_data.schemas.story_outlines import (
    BranchingPoint,
    MysteryClue,
    MysteryStructure,
    PacingMetrics,
    StoryBeat,
    StoryOutlineCreate,
    StoryOutlineResponse,
    StoryOutlineUpdate,
)
# =============================================================================
# STORY OUTLINE OPERATIONS (DL-6)
# =============================================================================


def _convert_story_outline_doc_to_response(doc: Dict[str, Any]) -> StoryOutlineResponse:
    """
    Convert a story_outline document from MongoDB to StoryOutlineResponse.

    Args:
        doc: Story outline document from MongoDB

    Returns:
        StoryOutlineResponse object
    """
    # Convert beats
    beats = []
    for beat_dict in doc.get("beats", []):
        beat = StoryBeat(
            beat_id=UUID(beat_dict["beat_id"]),
            title=beat_dict["title"],
            description=beat_dict["description"],
            order=beat_dict["order"],
            status=BeatStatus(beat_dict.get("status", "pending")),
            optional=beat_dict.get("optional", False),
            related_threads=[UUID(tid) for tid in beat_dict.get("related_threads", [])],
            required_for_threads=[UUID(tid) for tid in beat_dict.get("required_for_threads", [])],
            created_at=beat_dict.get("created_at"),
            started_at=beat_dict.get("started_at"),
            completed_at=beat_dict.get("completed_at"),
            completed_in_scene_id=(
                UUID(beat_dict["completed_in_scene_id"])
                if beat_dict.get("completed_in_scene_id")
                else None
            ),
        )
        beats.append(beat)

    # Convert pacing metrics
    pacing_dict = doc.get("pacing_metrics", {})
    pacing = PacingMetrics(**pacing_dict) if pacing_dict else PacingMetrics()

    # Convert mystery structure if present
    mystery_structure = None
    if "mystery_structure" in doc and doc["mystery_structure"]:
        mystery_dict = doc["mystery_structure"]
        mystery_structure = MysteryStructure(
            truth=mystery_dict["truth"],
            question=mystery_dict["question"],
            core_clues=[MysteryClue(**clue) for clue in mystery_dict.get("core_clues", [])],
            bonus_clues=[MysteryClue(**clue) for clue in mystery_dict.get("bonus_clues", [])],
            red_herrings=[MysteryClue(**clue) for clue in mystery_dict.get("red_herrings", [])],
            suspects=mystery_dict.get("suspects", []),
            current_player_theories=mystery_dict.get("current_player_theories", []),
        )

    # Convert branching points
    branching_points = [BranchingPoint(**bp) for bp in doc.get("branching_points", [])]

    return StoryOutlineResponse(
        story_id=UUID(doc["story_id"]),
        theme=doc.get("theme", ""),
        premise=doc.get("premise", ""),
        constraints=doc.get("constraints", []),
        beats=beats,
        structure_type=doc.get("structure_type", "linear"),
        template=doc.get("template", "custom"),
        branching_points=branching_points,
        mystery_structure=mystery_structure,
        pacing_metrics=pacing,
        open_threads=doc.get("open_threads", []),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _calculate_pacing_metrics(
    beats: list[StoryBeat], scenes_since_major_event: int = 0
) -> PacingMetrics:
    """
    Calculate pacing metrics from beats.

    Args:
        beats: List of story beats
        scenes_since_major_event: Counter for pacing

    Returns:
        Calculated pacing metrics
    """
    total_beats = len(beats)
    completed_beats = sum(1 for b in beats if b.status == BeatStatus.COMPLETED)
    in_progress_beats = sum(1 for b in beats if b.status == BeatStatus.IN_PROGRESS)

    # Calculate completion percentage
    estimated_completion = completed_beats / total_beats if total_beats > 0 else 0.0

    # Calculate tension based on active threads and progression
    # Simple heuristic: tension rises as we approach climax (80%+) or have many in-progress beats
    tension_level = 0.0
    if estimated_completion > 0.8:
        tension_level = min(1.0, 0.7 + (estimated_completion - 0.8) * 1.5)
    elif in_progress_beats > 0:
        tension_level = min(0.6, 0.3 + (in_progress_beats * 0.1))

    # Determine current act (simple three-act structure)
    if estimated_completion < 0.25:
        current_act = 1
    elif estimated_completion < 0.75:
        current_act = 2
    else:
        current_act = 3

    return PacingMetrics(
        current_act=current_act,
        tension_level=tension_level,
        scenes_since_major_event=scenes_since_major_event,
        scenes_in_current_act=0,  # Would need scene tracking
        estimated_completion=estimated_completion,
        last_updated=datetime.now(timezone.utc),
    )


def mongodb_create_story_outline(params: StoryOutlineCreate) -> StoryOutlineResponse:
    """
    Create a story outline for a story (DL-6).

    Authority: Orchestrator
    Use Case: P-1, ST-1

    Args:
        params: Story outline creation parameters

    Returns:
        Created story outline

    Raises:
        ValueError: If story doesn't exist in Neo4j
    """
    client = get_mongodb_client()
    neo4j_client = get_neo4j_client()
    outlines_collection = client.get_collection("story_outlines")

    # Verify story exists in Neo4j
    verify_query = "MATCH (s:Story {id: $story_id}) RETURN s.id as id"
    result = neo4j_client.execute_read(verify_query, {"story_id": str(params.story_id)})
    if not result:
        raise ValueError(f"Story {params.story_id} not found")

    # Check if outline already exists
    existing = outlines_collection.find_one({"story_id": str(params.story_id)})
    if existing:
        raise ValueError(f"Story outline for {params.story_id} already exists")

    # Calculate initial pacing metrics
    pacing = _calculate_pacing_metrics(params.beats)

    # Build document
    now = datetime.now(timezone.utc)
    doc = {
        "story_id": str(params.story_id),
        "theme": params.theme,
        "premise": params.premise,
        "constraints": params.constraints,
        "beats": [beat.model_dump(mode="json") for beat in params.beats],
        "structure_type": params.structure_type.value,
        "template": params.template.value,
        "branching_points": [bp.model_dump(mode="json") for bp in params.branching_points],
        "mystery_structure": (
            params.mystery_structure.model_dump(mode="json") if params.mystery_structure else None
        ),
        "pacing_metrics": pacing.model_dump(mode="json"),
        "open_threads": [],  # Will be populated by plot threads
        "created_at": now,
        "updated_at": now,
    }

    # Insert
    outlines_collection.insert_one(doc)

    return _convert_story_outline_doc_to_response(doc)


def mongodb_get_story_outline(story_id: UUID) -> Optional[StoryOutlineResponse]:
    """
    Get story outline for a story (DL-6).

    Authority: All agents
    Use Case: P-2, ST-1

    Args:
        story_id: Story UUID

    Returns:
        Story outline or None if not found
    """
    client = get_mongodb_client()
    outlines_collection = client.get_collection("story_outlines")

    doc = outlines_collection.find_one({"story_id": str(story_id)})
    if not doc:
        return None

    return _convert_story_outline_doc_to_response(doc)


def mongodb_update_story_outline(
    story_id: UUID, params: StoryOutlineUpdate
) -> StoryOutlineResponse:
    """
    Update story outline with partial updates and beat manipulation (DL-6).

    Authority: Orchestrator
    Use Case: P-8, ST-1

    Supports:
    - Updating theme, premise, constraints, structure, template
    - Adding new beats
    - Removing beats by ID
    - Reordering beats
    - Updating existing beats
    - Updating mystery structure
    - Marking clues as discovered

    Beat operations are applied in this order:
    1. update_beats: Modify existing beats (preserves order)
    2. remove_beat_ids: Remove beats by ID
    3. add_beats: Append new beats to the end
    4. reorder_beats: Reorder all beats (must include ALL beat IDs)

    Note: reorder_beats requires all beat IDs to be included. Mixing
    reorder_beats with other beat operations in the same update may lead
    to unexpected results. It's recommended to either use reorder_beats
    alone or use other beat operations separately.

    Args:
        story_id: Story UUID
        params: Update parameters

    Returns:
        Updated story outline

    Raises:
        ValueError: If outline doesn't exist or beat operations invalid
    """
    client = get_mongodb_client()
    outlines_collection = client.get_collection("story_outlines")

    # Get existing document
    doc = outlines_collection.find_one({"story_id": str(story_id)})
    if not doc:
        raise ValueError(f"Story outline for {story_id} not found")

    # Build update document
    update_doc: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}

    # Update simple fields
    if params.theme is not None:
        update_doc["theme"] = params.theme
    if params.premise is not None:
        update_doc["premise"] = params.premise
    if params.constraints is not None:
        update_doc["constraints"] = params.constraints
    if params.structure_type is not None:
        update_doc["structure_type"] = params.structure_type.value
    if params.template is not None:
        update_doc["template"] = params.template.value

    # Handle beat operations
    current_beats = [StoryBeat(**b) for b in doc.get("beats", [])]

    # Update existing beats
    if params.update_beats:
        update_map = {str(b.beat_id): b for b in params.update_beats}
        for i, beat in enumerate(current_beats):
            beat_id_str = str(beat.beat_id)
            if beat_id_str in update_map:
                current_beats[i] = update_map[beat_id_str]

    # Remove beats
    if params.remove_beat_ids:
        remove_ids = {str(bid) for bid in params.remove_beat_ids}
        current_beats = [b for b in current_beats if str(b.beat_id) not in remove_ids]

    # Add beats
    if params.add_beats:
        current_beats.extend(params.add_beats)

    # Reorder beats
    if params.reorder_beats:
        beats_by_id = {str(b.beat_id): b for b in current_beats}
        if len(params.reorder_beats) != len(beats_by_id):
            raise ValueError(
                f"reorder_beats must include all {len(beats_by_id)} beat IDs. "
                f"Got {len(params.reorder_beats)} IDs instead."
            )
        reordered: list[StoryBeat] = []
        for beat_id in params.reorder_beats:
            beat_id_str = str(beat_id)
            if beat_id_str not in beats_by_id:
                raise ValueError(f"Beat ID {beat_id} not found in current beats")
            beat = beats_by_id[beat_id_str]
            beat.order = len(reordered)
            reordered.append(beat)
        current_beats = reordered

    update_doc["beats"] = [beat.model_dump(mode="json") for beat in current_beats]

    # Recalculate pacing metrics
    pacing = _calculate_pacing_metrics(
        current_beats, doc.get("pacing_metrics", {}).get("scenes_since_major_event", 0)
    )
    update_doc["pacing_metrics"] = pacing.model_dump(mode="json")

    # Update mystery structure
    if params.update_mystery_structure:
        update_doc["mystery_structure"] = params.update_mystery_structure.model_dump(mode="json")

    # Mark clue as discovered
    if params.mark_clue_discovered and "mystery_structure" in doc:
        mystery = doc["mystery_structure"]
        if mystery is None:
            raise ValueError(
                "Cannot mark clue as discovered: story outline has no mystery structure"
            )
        clue_id_str = str(params.mark_clue_discovered)
        now = datetime.now(timezone.utc)

        # Search in all clue lists
        for clue_list_name in ["core_clues", "bonus_clues", "red_herrings"]:
            for clue in mystery.get(clue_list_name, []):
                if str(clue.get("clue_id")) == clue_id_str:
                    clue["is_discovered"] = True
                    clue["discovered_at"] = now
                    clue["visibility"] = "discovered"

        update_doc["mystery_structure"] = mystery

    # Branching points
    if params.add_branching_points:
        existing_bp = doc.get("branching_points", [])
        existing_bp.extend([bp.model_dump(mode="json") for bp in params.add_branching_points])
        update_doc["branching_points"] = existing_bp

    # Perform update
    outlines_collection.update_one({"story_id": str(story_id)}, {"$set": update_doc})

    # Return updated outline
    updated = mongodb_get_story_outline(story_id)
    if not updated:
        raise ValueError(f"Story outline {story_id} not found after update")

    return updated
