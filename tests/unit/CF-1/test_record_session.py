"""
Behavior tests for CF-1: Record or Capture Assisted Session

Tests recording and capturing human-led RPG sessions with real-time entity extraction,
proposal generation, and scene segmentation.
"""

import pytest

pytest.skip(
    "Spec prototype: this module defines its own mock implementation of the "
    "use case and tests that prototype, not MONITOR code (zero monitor_* "
    "imports). The real implementation is covered by tests/behavior, "
    "tests/contracts, tests/api and packages/*/tests. Kept as a design "
    "artifact; not part of the green suite.",
    allow_module_level=True,
)


from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock

import pytest


# Mock schema classes for testing
class TurnType:
    ACTION = "action"
    DIALOGUE = "dialogue"
    LORE = "lore"
    DECISION = "decision"
    CONSEQUENCE = "consequence"


class Turn:
    def __init__(
        self,
        id: str,
        scene_id: str,
        turn_type: str,
        content: str,
        timestamp: datetime,
        metadata: dict | None = None,
    ):
        self.id = id
        self.scene_id = scene_id
        self.turn_type = turn_type
        self.content = content
        self.timestamp = timestamp
        self.metadata = metadata or {}


class RecordingMode:
    LIVE_NOTES = "live_notes"
    TRANSCRIPT = "transcript"
    AUDIO = "audio"
    HYBRID = "hybrid"


class RecordingState:
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    FINALIZING = "finalizing"


class SceneSummary:
    def __init__(
        self,
        id: str,
        story_id: str,
        title: str,
        summary: str,
        entity_refs: list[str],
        turn_count: int,
    ):
        self.id = id
        self.story_id = story_id
        self.title = title
        self.summary = summary
        self.entity_refs = entity_refs
        self.turn_count = turn_count


class ProposedChange:
    def __init__(
        self,
        id: str,
        scene_id: str,
        change_type: str,
        description: str,
        confidence: float,
    ):
        self.id = id
        self.scene_id = scene_id
        self.change_type = change_type
        self.description = description
        self.confidence = confidence


class RecordingReview:
    def __init__(
        self,
        id: str,
        session_id: str,
        draft_scenes: list[SceneSummary],
        total_turns: int,
        proposals: list[ProposedChange],
    ):
        self.id = id
        self.session_id = session_id
        self.draft_scenes = draft_scenes
        self.total_turns = total_turns
        self.proposals = proposals


class Story:
    def __init__(self, id: str, title: str, game_system_id: str):
        self.id = id
        self.title = title
        self.game_system_id = game_system_id


# Mock agent classes for testing
class Orchestrator:
    def __init__(self, mcp_client: Any, llm_client: Any):
        self.mcp_client = mcp_client
        self.llm_client = llm_client
        self.state = RecordingState.IDLE

    async def start_recording_session(self, story_id: str, mode: str) -> str:
        """Initialize a new recording session."""
        pass

    async def finalize_recording(self, session_id: str) -> RecordingReview:
        """Wrap up recording and generate review options."""
        pass


class Narrator:
    def __init__(self, mcp_client: Any, llm_client: Any):
        self.mcp_client = mcp_client
        self.llm_client = llm_client

    async def parse_gm_input(self, content: str) -> dict:
        """Parse GM input and classify turn type."""
        pass

    async def segment_session_into_scenes(self, session_id: str) -> list[SceneSummary]:
        """Identify scene boundaries and create draft scenes."""
        pass


class Indexer:
    def __init__(self, mcp_client: Any, llm_client: Any):
        self.mcp_client = mcp_client
        self.llm_client = llm_client

    async def extract_entities_realtime(self, content: str) -> dict[str, Any]:
        """Extract entities and relationships from content."""
        pass


# Test fixtures
@pytest.fixture
def fake_mcp():
    """Fake MCP client for testing."""
    mcp = Mock()
    mcp.call_tool = AsyncMock()
    return mcp


@pytest.fixture
def fake_llm():
    """Fake LLM client for testing."""
    llm = Mock()
    llm.complete = AsyncMock()
    return llm


@pytest.fixture
def orchestrator(fake_mcp, fake_llm):
    """Orchestrator agent instance."""
    return Orchestrator(fake_mcp, fake_llm)


@pytest.fixture
def narrator(fake_mcp, fake_llm):
    """Narrator agent instance."""
    return Narrator(fake_mcp, fake_llm)


@pytest.fixture
def indexer(fake_mcp, fake_llm):
    """Indexer agent instance."""
    return Indexer(fake_mcp, fake_llm)


@pytest.fixture
def sample_story():
    """Sample story for testing."""
    return Story(id="story-123", title="Dragon's Wrath", game_system_id="dnd5e-001")


# ============================================================================
# SCENARIO 1: Live Notes Recording
# ============================================================================


@pytest.mark.unit
async def test_scenario1_live_notes_recording(
    orchestrator, narrator, indexer, fake_mcp, sample_story
):
    """
    Scenario 1: GM types live notes during play.

    Steps:
    1. Start recording with LIVE_NOTES mode
    2. Parse GM's live notes input
    3. Extract entities in real-time
    4. Append turns to scene transcript
    5. Finalize recording
    6. Present review options

    Expected Results:
    - Each note is parsed into a turn
    - Entities detected as notes are entered
    - Session stored in MongoDB
    - Review options include: finalize, edit, discard
    """
    # Setup: Start recording session
    session_id = "session-001"
    scene_id = "scene-001"

    orchestrator.start_recording_session = AsyncMock(return_value=session_id)
    orchestrator.state = RecordingState.RECORDING

    narrator.parse_gm_input = AsyncMock(
        side_effect=[
            {
                "turn_type": TurnType.ACTION,
                "content": "The party enters the tavern",
                "metadata": {"source": "live_notes"},
            },
            {
                "turn_type": TurnType.DIALOGUE,
                "content": "I'll have a mug of ale",
                "metadata": {"speaker": "Fighter"},
            },
            {
                "turn_type": TurnType.LORE,
                "content": "The tavern has seen better days",
                "metadata": {"source": "live_notes"},
            },
        ]
    )

    indexer.extract_entities_realtime = AsyncMock(
        side_effect=[
            {"entities": [{"name": "The Rusty Anchor", "type": "location"}]},
            {"entities": [{"name": "Fighter", "type": "character"}]},
            {"entities": []},
        ]
    )

    fake_mcp.call_tool = AsyncMock(
        side_effect=[
            {"turn_id": "turn-001"},
            {"turn_id": "turn-002"},
            {"turn_id": "turn-003"},
        ]
    )

    # Execute: Start recording
    result_session_id = await orchestrator.start_recording_session(
        sample_story.id, RecordingMode.LIVE_NOTES
    )
    assert result_session_id == session_id
    assert orchestrator.state == RecordingState.RECORDING

    # Execute: Process three live notes
    notes = [
        "The party enters the tavern",
        "I'll have a mug of ale",
        "The tavern has seen better days",
    ]

    for note in notes:
        parsed = await narrator.parse_gm_input(note)
        await indexer.extract_entities_realtime(note)
        await fake_mcp.call_tool(
            "append_turn",
            {
                "scene_id": scene_id,
                "turn_type": parsed["turn_type"],
                "content": parsed["content"],
                "metadata": parsed["metadata"],
            },
        )

    # Verify: Three turns created
    assert fake_mcp.call_tool.call_count == 3
    assert narrator.parse_gm_input.call_count == 3
    assert indexer.extract_entities_realtime.call_count == 3

    # Execute: Finalize recording
    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-001",
            session_id=session_id,
            draft_scenes=[
                SceneSummary(
                    id=scene_id,
                    story_id=sample_story.id,
                    title="Tavern Arrival",
                    summary="Party arrives at the Rusty Anchor",
                    entity_refs=["Rusty Anchor", "Fighter"],
                    turn_count=3,
                )
            ],
            total_turns=3,
            proposals=[],
        )
    )

    review = await orchestrator.finalize_recording(session_id)
    assert review.session_id == session_id
    assert len(review.draft_scenes) == 1
    assert review.total_turns == 3


# ============================================================================
# SCENARIO 2: Transcript Upload
# ============================================================================


@pytest.mark.unit
async def test_scenario2_transcript_upload(
    orchestrator, narrator, fake_mcp, sample_story
):
    """
    Scenario 2: GM uploads full transcript after session.

    Steps:
    1. Start recording with TRANSCRIPT mode
    2. Parse transcript content
    3. Extract entities from transcript
    4. Segment into scenes
    5. Generate proposals for canonization
    6. Present review options

    Expected Results:
    - Transcript parsed into multiple turns
    - Scene boundaries detected
    - Entities extracted from full context
    - Proposals generated for new entities/facts
    - Review options include: canonize proposals, edit scenes, discard
    """
    # Setup: Start recording
    session_id = "session-002"

    orchestrator.start_recording_session = AsyncMock(return_value=session_id)

    narrator.parse_gm_input = AsyncMock(
        return_value={
            "turn_type": TurnType.ACTION,
            "content": "The dragon attacks the village",
            "metadata": {"source": "transcript"},
        }
    )

    narrator.segment_session_into_scenes = AsyncMock(
        return_value=[
            SceneSummary(
                id="scene-002a",
                story_id=sample_story.id,
                title="Village Under Attack",
                summary="Dragon descends on peaceful village",
                entity_refs=["Emerald Dragon", "Millfield"],
                turn_count=5,
            ),
            SceneSummary(
                id="scene-002b",
                story_id=sample_story.id,
                title="Heroes Respond",
                summary="Party rushes to defend village",
                entity_refs=["Emerald Dragon", "Party"],
                turn_count=8,
            ),
        ]
    )

    fake_mcp.call_tool = AsyncMock(
        side_effect=[{"proposal_id": "prop-001"}, {"proposal_id": "prop-002"}]
    )

    # Execute: Start recording
    result = await orchestrator.start_recording_session(
        sample_story.id, RecordingMode.TRANSCRIPT
    )
    assert result == session_id

    # Execute: Parse transcript
    transcript = "The dragon attacks the village..."
    parsed = await narrator.parse_gm_input(transcript)
    assert parsed["metadata"]["source"] == "transcript"

    # Execute: Segment into scenes
    scenes = await narrator.segment_session_into_scenes(session_id)
    assert len(scenes) == 2
    assert scenes[0].title == "Village Under Attack"
    assert scenes[1].title == "Heroes Respond"

    # Execute: Generate proposals
    proposals = [
        ProposedChange(
            id="prop-001",
            scene_id="scene-002a",
            change_type="new_entity",
            description="Emerald Dragon: Ancient green dragon",
            confidence=0.92,
        ),
        ProposedChange(
            id="prop-002",
            scene_id="scene-002a",
            change_type="new_fact",
            description="Millfield is under dragon attack",
            confidence=0.95,
        ),
    ]

    # Execute: Finalize with proposals
    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-002",
            session_id=session_id,
            draft_scenes=scenes,
            total_turns=13,
            proposals=proposals,
        )
    )

    review = await orchestrator.finalize_recording(session_id)
    assert len(review.draft_scenes) == 2
    assert review.total_turns == 13
    assert len(review.proposals) == 2
    assert review.proposals[0].change_type == "new_entity"
    assert review.proposals[1].change_type == "new_fact"


# ============================================================================
# SCENARIO 3: Audio Capture with Annotations
# ============================================================================


@pytest.mark.unit
async def test_scenario3_audio_capture_with_annotations(
    orchestrator, narrator, indexer, fake_mcp, sample_story
):
    """
    Scenario 3: Audio recorded with GM annotations.

    Steps:
    1. Start recording with AUDIO mode
    2. Capture audio and transcribe
    3. GM adds annotations to mark key moments
    4. Extract entities with annotation context
    5. Append turns with metadata
    6. Finalize recording

    Expected Results:
    - Audio transcribed to text
    - Annotations preserved as turn metadata
    - Entities extracted with context from annotations
    - Turns include annotation metadata
    - Review shows annotated segments highlighted
    """
    # Setup: Start audio recording
    session_id = "session-003"

    orchestrator.start_recording_session = AsyncMock(return_value=session_id)

    # Simulate transcription with annotation
    narrator.parse_gm_input = AsyncMock(
        return_value={
            "turn_type": TurnType.DIALOGUE,
            "content": "I accept the quest",
            "metadata": {
                "source": "audio",
                "annotation": "critical_plot_point",
                "timestamp": "00:15:30",
            },
        }
    )

    indexer.extract_entities_realtime = AsyncMock(
        return_value={
            "entities": [
                {"name": "Quest Giver", "type": "character"},
                {"name": "The Ancient Contract", "type": "item"},
            ]
        }
    )

    fake_mcp.call_tool = AsyncMock(return_value={"turn_id": "turn-003"})

    # Execute: Start recording
    result = await orchestrator.start_recording_session(
        sample_story.id, RecordingMode.AUDIO
    )
    assert result == session_id

    # Execute: Process transcribed content with annotation
    transcription = "I accept the quest"
    parsed = await narrator.parse_gm_input(transcription)

    assert parsed["metadata"]["source"] == "audio"
    assert parsed["metadata"]["annotation"] == "critical_plot_point"
    assert parsed["metadata"]["timestamp"] == "00:15:30"

    # Execute: Extract entities with annotation context
    entities = await indexer.extract_entities_realtime(transcription)
    assert len(entities["entities"]) == 2
    assert entities["entities"][0]["name"] == "Quest Giver"

    # Execute: Append turn with annotation metadata
    await fake_mcp.call_tool(
        "append_turn",
        {
            "scene_id": "scene-003",
            "turn_type": parsed["turn_type"],
            "content": parsed["content"],
            "metadata": parsed["metadata"],
        },
    )

    assert fake_mcp.call_tool.called

    # Execute: Finalize
    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-003",
            session_id=session_id,
            draft_scenes=[
                SceneSummary(
                    id="scene-003",
                    story_id=sample_story.id,
                    title="Quest Accepted",
                    summary="Party accepts the quest from the Quest Giver",
                    entity_refs=["Quest Giver", "The Ancient Contract"],
                    turn_count=1,
                )
            ],
            total_turns=1,
            proposals=[],
        )
    )

    review = await orchestrator.finalize_recording(session_id)
    assert review.draft_scenes[0].turn_count == 1


# ============================================================================
# SCENARIO 4: GM Annotations for Exclusion
# ============================================================================


@pytest.mark.unit
async def test_scenario4_gm_annotations_exclusion(
    orchestrator, narrator, fake_mcp, sample_story
):
    """
    Scenario 4: GM marks content for exclusion.

    Steps:
    1. Record session normally
    2. GM adds annotation to exclude content
    3. System respects exclusion during processing
    4. Excluded content stored but not indexed
    5. Finalize recording

    Expected Results:
    - Excluded turns stored with metadata
    - Excluded content not used for entity extraction
    - Excluded content not used for proposals
    - Review clearly marks excluded sections
    """
    # Setup: Start recording
    session_id = "session-004"

    orchestrator.start_recording_session = AsyncMock(return_value=session_id)

    # Normal turn
    narrator.parse_gm_input = AsyncMock(
        side_effect=[
            {
                "turn_type": TurnType.ACTION,
                "content": "The party searches the ruins",
                "metadata": {},
            },
            {
                "turn_type": TurnType.DIALOGUE,
                "content": "Out of character: Let's order pizza",
                "metadata": {"exclude": True, "reason": "ooc"},
            },
            {
                "turn_type": TurnType.LORE,
                "content": "The ruins date back 500 years",
                "metadata": {},
            },
        ]
    )

    fake_mcp.call_tool = AsyncMock(
        side_effect=[
            {"turn_id": "turn-004a"},
            {"turn_id": "turn-004b"},  # Excluded turn
            {"turn_id": "turn-004c"},
        ]
    )

    # Execute: Start recording
    result = await orchestrator.start_recording_session(
        sample_story.id, RecordingMode.LIVE_NOTES
    )
    assert result == session_id

    # Execute: Process turns (including excluded one)
    turns = [
        "The party searches the ruins",
        "Out of character: Let's order pizza",
        "The ruins date back 500 years",
    ]

    for turn_content in turns:
        parsed = await narrator.parse_gm_input(turn_content)
        await fake_mcp.call_tool(
            "append_turn",
            {
                "scene_id": "scene-004",
                "turn_type": parsed["turn_type"],
                "content": parsed["content"],
                "metadata": parsed["metadata"],
            },
        )

    # Verify: All turns stored
    assert fake_mcp.call_tool.call_count == 3

    # Verify excluded turn has proper metadata
    excluded_call = fake_mcp.call_tool.call_args_list[1]
    assert excluded_call[1]["args"][0] == "append_turn"
    assert excluded_call[1]["args"][1]["metadata"]["exclude"] is True
    assert excluded_call[1]["args"][1]["metadata"]["reason"] == "ooc"

    # Execute: Finalize with excluded content
    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-004",
            session_id=session_id,
            draft_scenes=[
                SceneSummary(
                    id="scene-004",
                    story_id=sample_story.id,
                    title="Ruins Exploration",
                    summary="Party explores ancient ruins (1 turn excluded)",
                    entity_refs=["Ancient Ruins"],
                    turn_count=2,  # Only non-excluded turns counted
                )
            ],
            total_turns=3,  # But all turns stored
            proposals=[],
        )
    )

    review = await orchestrator.finalize_recording(session_id)
    assert review.draft_scenes[0].turn_count == 2  # Non-excluded
    assert review.total_turns == 3  # Total stored


# ============================================================================
# SCENARIO 5: Multi-Scene Session with Entity Tracking
# ============================================================================


@pytest.mark.unit
async def test_scenario5_multiscene_entity_tracking(
    orchestrator, narrator, indexer, fake_mcp, sample_story
):
    """
    Scenario 5: Session spans multiple scenes with continuous entity tracking.

    Steps:
    1. Start recording
    2. Process Scene 1 content
    3. Detect scene transition
    4. Process Scene 2 content
    5. Track entities across scenes
    6. Generate proposals for relationships
    7. Finalize recording

    Expected Results:
    - Two distinct scenes created
    - Scene boundaries correctly detected
    - Entities tracked across both scenes
    - Relationships between entities detected
    - Proposals for new entities and relationships
    """
    # Setup: Start recording
    session_id = "session-005"

    orchestrator.start_recording_session = AsyncMock(return_value=session_id)

    # Scene 1 content
    narrator.parse_gm_input = AsyncMock(
        side_effect=[
            {
                "turn_type": TurnType.DIALOGUE,
                "content": "King Arthur asks for help",
                "metadata": {},
            },
            {
                "turn_type": TurnType.DIALOGUE,
                "content": "I shall hunt the dragon",
                "metadata": {},
            },
        ]
    )

    narrator.segment_session_into_scenes = AsyncMock(
        return_value=[
            SceneSummary(
                id="scene-005a",
                story_id=sample_story.id,
                title="Royal Audience",
                summary="King Arthur summons the party",
                entity_refs=["King Arthur"],
                turn_count=3,
            ),
            SceneSummary(
                id="scene-005b",
                story_id=sample_story.id,
                title="The Hunt Begins",
                summary="Party departs to hunt the dragon",
                entity_refs=["King Arthur", "Sir Lancelot", "Emerald Dragon"],
                turn_count=4,
            ),
        ]
    )

    indexer.extract_entities_realtime = AsyncMock(
        side_effect=[
            {"entities": [{"name": "King Arthur", "type": "character"}]},
            {
                "entities": [
                    {"name": "Sir Lancelot", "type": "character"},
                    {"name": "Emerald Dragon", "type": "creature"},
                ]
            },
        ]
    )

    fake_mcp.call_tool = AsyncMock(
        side_effect=[
            {"proposal_id": "prop-005a"},
            {"proposal_id": "prop-005b"},
            {"proposal_id": "prop-005c"},
        ]
    )

    # Execute: Start recording
    result = await orchestrator.start_recording_session(
        sample_story.id, RecordingMode.LIVE_NOTES
    )
    assert result == session_id

    # Execute: Process Scene 1
    await narrator.parse_gm_input("King Arthur asks for help")
    entities1 = await indexer.extract_entities_realtime("King Arthur asks for help")
    assert "King Arthur" in [e["name"] for e in entities1["entities"]]

    # Execute: Process Scene 2
    await narrator.parse_gm_input("I shall hunt the dragon")
    entities2 = await indexer.extract_entities_realtime("I shall hunt the dragon")
    assert "Sir Lancelot" in [e["name"] for e in entities2["entities"]]
    assert "Emerald Dragon" in [e["name"] for e in entities2["entities"]]

    # Execute: Segment into scenes
    scenes = await narrator.segment_session_into_scenes(session_id)
    assert len(scenes) == 2
    assert scenes[0].title == "Royal Audience"
    assert scenes[1].title == "The Hunt Begins"

    # Verify: King Arthur appears in both scenes (cross-scene entity tracking)
    assert "King Arthur" in scenes[0].entity_refs
    assert "King Arthur" in scenes[1].entity_refs

    # Execute: Generate proposals including relationships
    proposals = [
        ProposedChange(
            id="prop-005a",
            scene_id="scene-005a",
            change_type="new_entity",
            description="King Arthur: Legendary ruler",
            confidence=0.98,
        ),
        ProposedChange(
            id="prop-005b",
            scene_id="scene-005b",
            change_type="new_relationship",
            description="King Arthur → asks for help → party",
            confidence=0.95,
        ),
        ProposedChange(
            id="prop-005c",
            scene_id="scene-005b",
            change_type="new_relationship",
            description="Sir Lancelot → hunting → Emerald Dragon",
            confidence=0.92,
        ),
    ]

    # Execute: Finalize
    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-005",
            session_id=session_id,
            draft_scenes=scenes,
            total_turns=7,
            proposals=proposals,
        )
    )

    review = await orchestrator.finalize_recording(session_id)
    assert len(review.draft_scenes) == 2
    assert review.total_turns == 7
    assert len(review.proposals) == 3

    # Verify relationship proposals
    relationship_props = [
        p for p in review.proposals if p.change_type == "new_relationship"
    ]
    assert len(relationship_props) == 2
    assert "asks for help" in relationship_props[0].description
    assert "hunting" in relationship_props[1].description


# ============================================================================
# ERROR CASES
# ============================================================================


@pytest.mark.unit
async def test_error_story_not_found(orchestrator, fake_mcp):
    """
    Error Case 1: Story ID not found.

    Expected: System returns clear error, recording not started
    """
    # Setup: Story doesn't exist
    fake_mcp.call_tool = AsyncMock(side_effect=Exception("Story not found: story-999"))

    # Execute & Verify: Error raised
    with pytest.raises(Exception) as exc_info:
        await orchestrator.start_recording_session(
            "story-999", RecordingMode.LIVE_NOTES
        )

    assert "Story not found" in str(exc_info.value)


@pytest.mark.unit
async def test_error_invalid_recording_mode(orchestrator):
    """
    Error Case 2: Invalid recording mode.

    Expected: System returns validation error, recording not started
    """
    # Execute & Verify: Invalid mode
    with pytest.raises(ValueError) as exc_info:
        await orchestrator.start_recording_session("story-123", "invalid_mode")

    assert "Invalid recording mode" in str(exc_info.value)


@pytest.mark.unit
async def test_error_entity_extraction_fails(indexer, fake_mcp):
    """
    Error Case 3: Entity extraction fails.

    Expected: System logs error, continues recording, turn still stored
    """
    # Setup: Entity extraction fails
    indexer.extract_entities_realtime = AsyncMock(side_effect=Exception("LLM timeout"))
    fake_mcp.call_tool = AsyncMock(return_value={"turn_id": "turn-error"})

    # Execute: Attempt entity extraction
    with pytest.raises(Exception) as exc_info:
        await indexer.extract_entities_realtime("Some content")

    assert "LLM timeout" in str(exc_info.value)


@pytest.mark.unit
async def test_error_scene_segmentation_fails(narrator):
    """
    Error Case 4: Scene segmentation fails.

    Expected: System logs error, creates single scene from all turns
    """
    # Setup: Segmentation fails
    narrator.segment_session_into_scenes = AsyncMock(
        side_effect=Exception("LLM timeout")
    )

    # Execute & Verify: Error raised
    with pytest.raises(Exception) as exc_info:
        await narrator.segment_session_into_scenes("session-001")

    assert "LLM timeout" in str(exc_info.value)


@pytest.mark.unit
async def test_error_storage_write_fails(fake_mcp):
    """
    Error Case 5: Storage write fails.

    Expected: System returns error to GM, provides retry option
    """
    # Setup: Storage fails
    fake_mcp.call_tool = AsyncMock(side_effect=Exception("MongoDB connection lost"))

    # Execute & Verify: Error raised
    with pytest.raises(Exception) as exc_info:
        await fake_mcp.call_tool(
            "append_turn",
            {
                "scene_id": "scene-001",
                "turn_type": TurnType.ACTION,
                "content": "Test content",
                "metadata": {},
            },
        )

    assert "MongoDB connection lost" in str(exc_info.value)


@pytest.mark.unit
async def test_error_review_generation_fails(orchestrator):
    """
    Error Case 6: Review generation fails.

    Expected: System returns partial review with warning, recording still accessible
    """
    # Setup: Review generation fails
    orchestrator.finalize_recording = AsyncMock(side_effect=Exception("LLM timeout"))

    # Execute & Verify: Error raised
    with pytest.raises(Exception) as exc_info:
        await orchestrator.finalize_recording("session-001")

    assert "LLM timeout" in str(exc_info.value)


# ============================================================================
# SUCCESS CRITERIA TESTS
# ============================================================================


@pytest.mark.unit
async def test_success_criterion_realtime_capture(orchestrator, narrator, fake_mcp):
    """
    Success Criterion 1: Real-time capture works without blocking GM.

    Verify: Input processed and stored within acceptable latency
    """
    session_id = "session-sc1"

    orchestrator.start_recording_session = AsyncMock(return_value=session_id)

    narrator.parse_gm_input = AsyncMock(
        return_value={
            "turn_type": TurnType.ACTION,
            "content": "The party moves forward",
            "metadata": {},
        }
    )

    fake_mcp.call_tool = AsyncMock(return_value={"turn_id": "turn-sc1"})

    # Execute: Quick succession of inputs
    import time

    start_time = time.time()

    await orchestrator.start_recording_session("story-123", RecordingMode.LIVE_NOTES)
    await narrator.parse_gm_input("The party moves forward")
    await fake_mcp.call_tool(
        "append_turn",
        {
            "scene_id": "scene-sc1",
            "turn_type": TurnType.ACTION,
            "content": "The party moves forward",
            "metadata": {},
        },
    )

    end_time = time.time()

    # Verify: Processing completed within reasonable time (< 1 second for this simple test)
    latency = end_time - start_time
    assert latency < 1.0


@pytest.mark.unit
async def test_success_criterion_entity_detection(indexer):
    """
    Success Criterion 2: Entity detection accuracy.

    Verify: Entities correctly identified with types
    """
    # Setup: Complex content with multiple entities
    content = "Sir Galahad, the noble knight of the Round Table, entered the ancient cathedral of Camelot to meet Archbishop Thomas."

    indexer.extract_entities_realtime = AsyncMock(
        return_value={
            "entities": [
                {"name": "Sir Galahad", "type": "character"},
                {"name": "Round Table", "type": "organization"},
                {"name": "ancient cathedral of Camelot", "type": "location"},
                {"name": "Archbishop Thomas", "type": "character"},
            ]
        }
    )

    # Execute: Extract entities
    result = await indexer.extract_entities_realtime(content)

    # Verify: All entities detected with correct types
    assert len(result["entities"]) == 4
    assert any(
        e["name"] == "Sir Galahad" and e["type"] == "character"
        for e in result["entities"]
    )
    assert any(
        e["name"] == "Round Table" and e["type"] == "organization"
        for e in result["entities"]
    )
    assert any(
        e["name"] == "ancient cathedral of Camelot" and e["type"] == "location"
        for e in result["entities"]
    )
    assert any(
        e["name"] == "Archbishop Thomas" and e["type"] == "character"
        for e in result["entities"]
    )


@pytest.mark.unit
async def test_success_criterion_relationship_detection(indexer):
    """
    Success Criterion 3: Relationship detection accuracy.

    Verify: Relationships between entities correctly identified
    """
    # Setup: Content with relationships
    content = "King Arthur appointed Lancelot as his champion to fight the dragon."

    indexer.extract_entities_realtime = AsyncMock(
        return_value={
            "entities": [
                {"name": "King Arthur", "type": "character"},
                {"name": "Lancelot", "type": "character"},
                {"name": "dragon", "type": "creature"},
            ],
            "relationships": [
                {"subject": "King Arthur", "verb": "appointed", "object": "Lancelot"},
                {"subject": "Lancelot", "verb": "fight", "object": "dragon"},
            ],
        }
    )

    # Execute: Extract entities and relationships
    result = await indexer.extract_entities_realtime(content)

    # Verify: Relationships detected
    assert "relationships" in result
    assert len(result["relationships"]) == 2
    assert result["relationships"][0]["verb"] == "appointed"
    assert result["relationships"][1]["verb"] == "fight"


@pytest.mark.unit
async def test_success_criterion_gm_annotations_respected(
    orchestrator, narrator, fake_mcp
):
    """
    Success Criterion 4: GM annotations respected.

    Verify: Excluded content not used for proposals, annotations preserved
    """
    session_id = "session-sc4"

    orchestrator.start_recording_session = AsyncMock(return_value=session_id)

    narrator.parse_gm_input = AsyncMock(
        return_value={
            "turn_type": TurnType.DIALOGUE,
            "content": "Out of character note",
            "metadata": {"exclude": True, "reason": "ooc"},
        }
    )

    fake_mcp.call_tool = AsyncMock(return_value={"turn_id": "turn-sc4"})

    # Execute: Process excluded turn
    parsed = await narrator.parse_gm_input("Out of character note")

    # Verify: Annotation metadata preserved
    assert parsed["metadata"]["exclude"] is True
    assert parsed["metadata"]["reason"] == "ooc"


@pytest.mark.unit
async def test_success_criterion_scene_segmentation(narrator):
    """
    Success Criterion 5: Scene segmentation accuracy.

    Verify: Scene boundaries correctly identified
    """
    narrator.segment_session_into_scenes = AsyncMock(
        return_value=[
            SceneSummary(
                id="scene-sc5a",
                story_id="story-123",
                title="Scene 1",
                summary="First scene",
                entity_refs=["Entity A"],
                turn_count=5,
            ),
            SceneSummary(
                id="scene-sc5b",
                story_id="story-123",
                title="Scene 2",
                summary="Second scene",
                entity_refs=["Entity A", "Entity B"],
                turn_count=7,
            ),
        ]
    )

    # Execute: Segment session
    scenes = await narrator.segment_session_into_scenes("session-sc5")

    # Verify: Two scenes created
    assert len(scenes) == 2
    assert scenes[0].turn_count == 5
    assert scenes[1].turn_count == 7
    assert scenes[0].title == "Scene 1"
    assert scenes[1].title == "Scene 2"


@pytest.mark.unit
async def test_success_criterion_proposal_generation(orchestrator):
    """
    Success Criterion 6: Proposal generation for canonization.

    Verify: Proposals generated for new entities/facts with confidence scores
    """
    # Setup: Proposals
    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-sc6",
            session_id="session-sc6",
            draft_scenes=[],
            total_turns=10,
            proposals=[
                ProposedChange(
                    id="prop-sc6a",
                    scene_id="scene-sc6",
                    change_type="new_entity",
                    description="New Character: Merlin the Wizard",
                    confidence=0.95,
                ),
                ProposedChange(
                    id="prop-sc6b",
                    scene_id="scene-sc6",
                    change_type="new_fact",
                    description="Merlin lives in Crystal Cave",
                    confidence=0.88,
                ),
            ],
        )
    )

    # Execute: Finalize recording
    review = await orchestrator.finalize_recording("session-sc6")

    # Verify: Proposals with confidence scores
    assert len(review.proposals) == 2
    assert review.proposals[0].confidence == 0.95
    assert review.proposals[1].confidence == 0.88
    assert review.proposals[0].change_type == "new_entity"
    assert review.proposals[1].change_type == "new_fact"


@pytest.mark.unit
async def test_success_criterion_review_options_presented(orchestrator):
    """
    Success Criterion 7: Review options presented to GM.

    Verify: GM can finalize, edit, or discard recording
    """
    # Setup: Review with options
    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-sc7",
            session_id="session-sc7",
            draft_scenes=[],
            total_turns=5,
            proposals=[],
        )
    )

    # Execute: Finalize recording
    review = await orchestrator.finalize_recording("session-sc7")

    # Verify: Review object contains necessary data for GM decision
    assert review.id is not None
    assert review.session_id is not None
    assert review.total_turns == 5
    assert review.draft_scenes is not None
    assert review.proposals is not None

    # GM would use this review to:
    # 1. Review draft scenes
    # 2. Review proposals
    # 3. Choose: finalize, edit, or discard


# ============================================================================
# POSTCONDITIONS VERIFICATION
# ============================================================================


@pytest.mark.unit
async def test_postcondition_draft_scenes_created(orchestrator, sample_story):
    """
    Postcondition 1: Draft scenes created in MongoDB.

    Verify: Scene documents exist with turn references
    """
    # Setup: Finalize with draft scenes
    scenes = [
        SceneSummary(
            id="scene-pc1a",
            story_id=sample_story.id,
            title="Scene 1",
            summary="First scene",
            entity_refs=["Entity A"],
            turn_count=3,
        )
    ]

    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-pc1",
            session_id="session-pc1",
            draft_scenes=scenes,
            total_turns=3,
            proposals=[],
        )
    )

    # Execute: Finalize recording
    review = await orchestrator.finalize_recording("session-pc1")

    # Verify: Draft scenes created
    assert len(review.draft_scenes) == 1
    assert review.draft_scenes[0].id == "scene-pc1a"
    assert review.draft_scenes[0].turn_count == 3


@pytest.mark.unit
async def test_postcondition_transcript_stored(orchestrator):
    """
    Postcondition 2: Transcript stored in MongoDB.

    Verify: Turn documents exist with timestamps and metadata
    """
    # Setup: Finalize with transcript
    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-pc2",
            session_id="session-pc2",
            draft_scenes=[],
            total_turns=5,
            proposals=[],
        )
    )

    # Execute: Finalize recording
    review = await orchestrator.finalize_recording("session-pc2")

    # Verify: Transcript stored (total_turns reflects stored turns)
    assert review.total_turns == 5


@pytest.mark.unit
async def test_postcondition_proposals_created(orchestrator):
    """
    Postcondition 3: Proposals created in MongoDB.

    Verify: ProposedChange documents exist for canonization
    """
    # Setup: Finalize with proposals
    proposals = [
        ProposedChange(
            id="prop-pc3",
            scene_id="scene-pc3",
            change_type="new_entity",
            description="New Entity",
            confidence=0.9,
        )
    ]

    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-pc3",
            session_id="session-pc3",
            draft_scenes=[],
            total_turns=3,
            proposals=proposals,
        )
    )

    # Execute: Finalize recording
    review = await orchestrator.finalize_recording("session-pc3")

    # Verify: Proposals created
    assert len(review.proposals) == 1
    assert review.proposals[0].id == "prop-pc3"
    assert review.proposals[0].change_type == "new_entity"


@pytest.mark.unit
async def test_postcondition_review_options_available(orchestrator):
    """
    Postcondition 4: Review options available to GM.

    Verify: RecordingReview document exists with all necessary data
    """
    # Setup: Finalize with complete review
    scenes = [
        SceneSummary(
            id="scene-pc4",
            story_id="story-123",
            title="Scene 1",
            summary="Summary",
            entity_refs=["Entity"],
            turn_count=5,
        )
    ]

    proposals = [
        ProposedChange(
            id="prop-pc4",
            scene_id="scene-pc4",
            change_type="new_fact",
            description="New Fact",
            confidence=0.95,
        )
    ]

    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-pc4",
            session_id="session-pc4",
            draft_scenes=scenes,
            total_turns=5,
            proposals=proposals,
        )
    )

    # Execute: Finalize recording
    review = await orchestrator.finalize_recording("session-pc4")

    # Verify: Complete review available
    assert review.id == "review-pc4"
    assert review.session_id == "session-pc4"
    assert len(review.draft_scenes) == 1
    assert review.total_turns == 5
    assert len(review.proposals) == 1


@pytest.mark.unit
async def test_postcondition_no_canon_changes_without_review(orchestrator):
    """
    Postcondition 5: No canon changes without GM review.

    Verify: No writes to Neo4j, all changes via ProposedChange
    """
    # Setup: Finalize with proposals
    proposals = [
        ProposedChange(
            id="prop-pc5",
            scene_id="scene-pc5",
            change_type="new_entity",
            description="New Entity",
            confidence=0.9,
        )
    ]

    orchestrator.finalize_recording = AsyncMock(
        return_value=RecordingReview(
            id="review-pc5",
            session_id="session-pc5",
            draft_scenes=[],
            total_turns=3,
            proposals=proposals,
        )
    )

    # Execute: Finalize recording
    review = await orchestrator.finalize_recording("session-pc5")

    # Verify: Proposals exist (not direct canon writes)
    assert len(review.proposals) == 1
    assert review.proposals[0].change_type == "new_entity"

    # Verify: No direct Neo4j writes occurred
    # (In real implementation, this would verify no Neo4j client was called)
    # For this test, we verify proposals exist instead
    assert review.proposals[0].id == "prop-pc5"
