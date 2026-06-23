"""
Behavior tests for CF-2: Generate Session Recap

Tests generating human-readable session summaries with multiple sections,
including narrative summary, key events, decisions, NPCs, threads, and loot.
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


import pytest
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from dataclasses import dataclass
from enum import Enum

# Mock schema classes for testing
class TurnType:
    ACTION = "action"
    DIALOGUE = "dialogue"
    LORE = "lore"
    DECISION = "decision"
    CONSEQUENCE = "consequence"

class Turn:
    def __init__(self, id: str, scene_id: str, turn_type: str, content: str, timestamp: datetime, metadata: Optional[Dict] = None):
        self.id = id
        self.scene_id = scene_id
        self.turn_type = turn_type
        self.content = content
        self.timestamp = timestamp
        self.metadata = metadata or {}

@dataclass
class TurnStats:
    total: int
    by_type: Dict[str, int]
    duration: timedelta

class ProposedChange:
    def __init__(self, id: str, scene_id: str, change_type: str, description: str, confidence: float, status: str = "accepted"):
        self.id = id
        self.scene_id = scene_id
        self.change_type = change_type
        self.description = description
        self.confidence = confidence
        self.status = status

@dataclass
class ProposalStats:
    total_accepted: int
    by_type: Dict[str, int]
    by_scene: Dict[str, int]

@dataclass
class Decision:
    description: str
    decision_maker: str
    options_considered: List[str]
    chosen_option: str
    consequence: str
    scene_id: str
    turn_id: str

@dataclass
class NPCSummary:
    name: str
    role: str
    significance: str  # "major", "minor", "background"
    scenes: List[str]
    relationship: str

@dataclass
class ThreadSummary:
    name: str
    status: str  # "opened", "closed", "advanced", "stalled"
    description: str
    next_steps: Optional[str]

@dataclass
class Loot:
    item_name: str
    recipient: str
    acquisition_method: str  # "found", "given", "purchased"
    scene_id: str
    turn_id: str

@dataclass
class Recap:
    id: str
    story_id: Optional[str]
    scene_id: Optional[str]
    generated_at: datetime
    target_audience: str  # "gm_only", "party", "public"
    detail_level: str  # "brief", "standard", "detailed"
    summary: str
    key_events: List[str]
    decisions_made: List[Decision]
    npcs_encountered: List[NPCSummary]
    threads_opened: List[ThreadSummary]
    threads_closed: List[ThreadSummary]
    loot_rewards: List[Loot]
    turn_stats: TurnStats
    proposal_stats: ProposalStats

class Scene:
    def __init__(self, id: str, story_id: str, title: str, status: str, metadata: Optional[Dict] = None):
        self.id = id
        self.story_id = story_id
        self.title = title
        self.status = status
        self.metadata = metadata or {}

class Story:
    def __init__(self, id: str, title: str, game_system_id: str, genre: str = "fantasy"):
        self.id = id
        self.title = title
        self.game_system_id = game_system_id
        self.genre = genre

# Mock agent classes for testing
class SystemAgent:
    def __init__(self, mongodb: Any, neo4j: Any):
        self.mongodb = mongodb
        self.neo4j = neo4j
    
    async def get_scene(self, scene_id: str) -> Scene:
        """Get scene by ID."""
        pass
    
    async def list_scenes(self, story_id: str, order: str = "desc", limit: Optional[int] = None) -> List[Scene]:
        """List scenes in story."""
        pass
    
    async def get_turns(self, scene_id: str) -> List[Turn]:
        """Get all turns for a scene."""
        pass
    
    async def get_proposed_changes(self, scene_id: str, status: str = "accepted") -> List[ProposedChange]:
        """Get proposals for a scene."""
        pass
    
    async def create_recap(self, recap: Recap) -> str:
        """Save recap to MongoDB."""
        pass
    
    async def update_scene(self, scene_id: str, data: Dict) -> bool:
        """Update scene with recap link."""
        pass

class Neo4jAgent:
    def __init__(self, neo4j_client: Any):
        self.neo4j_client = neo4j_client
    
    async def list_entities(self, story_id: str, entity_type: str) -> List[Dict]:
        """List entities in story."""
        pass
    
    async def list_plot_threads(self, story_id: str, status: str) -> List[Dict]:
        """List plot threads in story."""
        pass

class NarratorAgent:
    def __init__(self, llm_client: Any):
        self.llm_client = llm_client
    
    async def generate_recap(self, scene_history: Dict, target_audience: str, detail_level: str) -> str:
        """Generate narrative summary using LLM."""
        pass
    
    async def extract_decisions(self, turns: List[Turn]) -> List[Decision]:
        """Extract decisions from turns."""
        pass
    
    async def extract_loot(self, turns: List[Turn]) -> List[Loot]:
        """Extract loot from turns."""
        pass

# Test fixtures
@pytest.fixture
def fake_mongodb():
    """Fake MongoDB client for testing."""
    mongodb = Mock()
    mongodb.call_tool = AsyncMock()
    return mongodb

@pytest.fixture
def fake_neo4j():
    """Fake Neo4j client for testing."""
    neo4j = Mock()
    neo4j.call_tool = AsyncMock()
    return neo4j

@pytest.fixture
def fake_llm():
    """Fake LLM client for testing."""
    llm = Mock()
    llm.complete = AsyncMock()
    return llm

@pytest.fixture
def system_agent(fake_mongodb, fake_neo4j):
    """System agent instance."""
    return SystemAgent(fake_mongodb, fake_neo4j)

@pytest.fixture
def neo4j_agent(fake_neo4j):
    """Neo4j agent instance."""
    return Neo4jAgent(fake_neo4j)

@pytest.fixture
def narrator_agent(fake_llm):
    """Narrator agent instance."""
    return NarratorAgent(fake_llm)

@pytest.fixture
def sample_story():
    """Sample story for testing."""
    return Story(
        id="story-123",
        title="The Dragon's Wrath",
        game_system_id="dnd5e-001",
        genre="fantasy"
    )

@pytest.fixture
def sample_scene(sample_story):
    """Sample finalized scene for testing."""
    return Scene(
        id="scene-123",
        story_id=sample_story.id,
        title="Tavern Confrontation",
        status="final",
        metadata={"location": "The Rusty Anchor", "duration": "2 hours"}
    )

@pytest.fixture
def sample_turns(sample_scene):
    """Sample turns for testing."""
    base_time = datetime(2024, 1, 15, 19, 0)
    return [
        Turn(
            id="turn-001",
            scene_id=sample_scene.id,
            turn_type=TurnType.DIALOGUE,
            content="I'll have a word with the innkeeper",
            timestamp=base_time,
            metadata={"speaker": "Fighter"}
        ),
        Turn(
            id="turn-002",
            scene_id=sample_scene.id,
            turn_type=TurnType.ACTION,
            content="The party investigates the basement",
            timestamp=base_time + timedelta(minutes=15),
            metadata={}
        ),
        Turn(
            id="turn-003",
            scene_id=sample_scene.id,
            turn_type=TurnType.DECISION,
            content="The party decides to pursue the dragon rumors",
            timestamp=base_time + timedelta(minutes=30),
            metadata={"decision_maker": "party"}
        )
    ]


# ============================================================================
# SCENARIO 1: Single Scene Recap (Standard)
# ============================================================================

@pytest.mark.unit
async def test_scenario1_single_scene_recap(system_agent, narrator_agent, neo4j_agent, fake_mongodb, fake_neo4j, fake_llm, sample_scene, sample_turns):
    """
    Scenario 1: Single scene recap with standard detail level.
    
    Steps:
    1. Validate input and retrieve scene
    2. Fetch all turns and proposals
    3. Analyze accepted proposals
    4. Extract key decisions
    5. Identify NPCs encountered
    6. Analyze plot thread progression
    7. Extract loot and rewards
    8. Generate narrative summary (LLM)
    9. Compile structured recap
    10. Display and export options
    
    Expected Results:
    - Recap generated with all sections
    - Narrative summary covers major events
    - Key decisions extracted and listed
    - NPCs encountered listed with roles
    - Threads opened/closed identified
    - Loot/rewards extracted if present
    - Statistics accurate (50 turns, duration)
    - Markdown export successful
    """
    # Setup: Mock scene retrieval
    system_agent.get_scene = AsyncMock(return_value=sample_scene)
    system_agent.get_turns = AsyncMock(return_value=sample_turns)
    system_agent.get_proposed_changes = AsyncMock(return_value=[
        ProposedChange(
            id="prop-001",
            scene_id=sample_scene.id,
            change_type="new_entity",
            description="The Rusty Anchor: Ancient tavern",
            confidence=0.95
        )
    ])
    
    neo4j_agent.list_entities = AsyncMock(return_value=[
        {"name": "The Rusty Anchor", "type": "location"},
        {"name": "Innkeeper", "type": "character"}
    ])
    
    neo4j_agent.list_plot_threads = AsyncMock(side_effect=[
        [{"name": "Dragon Threat", "status": "opened"}],  # Open threads
        []  # Closed threads
    ])
    
    narrator_agent.generate_recap = AsyncMock(return_value="The party arrived at the Rusty Anchor tavern. They investigated the basement and decided to pursue dragon rumors. A mysterious thread was opened.")
    
    narrator_agent.extract_decisions = AsyncMock(return_value=[
        Decision(
            description="Pursue dragon rumors",
            decision_maker="party",
            options_considered=["Investigate basement", "Ignore rumors", "Pursue dragons"],
            chosen_option="Pursue dragons",
            consequence="Party embarks on dragon hunt",
            scene_id=sample_scene.id,
            turn_id="turn-003"
        )
    ])
    
    narrator_agent.extract_loot = AsyncMock(return_value=[
        Loot(
            item_name="Mysterious Key",
            recipient="party",
            acquisition_method="found",
            scene_id=sample_scene.id,
            turn_id="turn-002"
        )
    ])
    
    system_agent.create_recap = AsyncMock(return_value="recap-001")
    system_agent.update_scene = AsyncMock(return_value=True)
    
    # Execute: Step 1 - Validate and retrieve scene
    scene = await system_agent.get_scene(sample_scene.id)
    assert scene.id == sample_scene.id
    assert scene.status == "final"
    
    # Execute: Step 2 - Fetch turns and proposals
    turns = await system_agent.get_turns(sample_scene.id)
    proposals = await system_agent.get_proposed_changes(sample_scene.id)
    assert len(turns) == 3
    assert len(proposals) == 1
    
    # Execute: Step 3 - Analyze proposals
    proposal_stats = ProposalStats(
        total_accepted=len(proposals),
        by_type={"new_entity": 1},
        by_scene={sample_scene.id: 1}
    )
    
    # Execute: Step 4 - Extract decisions
    decisions = await narrator_agent.extract_decisions(turns)
    assert len(decisions) == 1
    assert decisions[0].decision_maker == "party"
    
    # Execute: Step 5 - Identify NPCs
    entities = await neo4j_agent.list_entities(sample_scene.story_id, "character")
    assert len(entities) == 1
    assert entities[0]["name"] == "Innkeeper"
    
    # Execute: Step 6 - Analyze plot threads
    open_threads = await neo4j_agent.list_plot_threads(sample_scene.story_id, "open")
    closed_threads = await neo4j_agent.list_plot_threads(sample_scene.story_id, "resolved")
    assert len(open_threads) == 1
    assert open_threads[0]["name"] == "Dragon Threat"
    assert len(closed_threads) == 0
    
    # Execute: Step 7 - Extract loot
    loot = await narrator_agent.extract_loot(turns)
    assert len(loot) == 1
    assert loot[0].item_name == "Mysterious Key"
    
    # Execute: Step 8 - Generate narrative summary
    scene_history = {
        "turns": turns,
        "proposals": proposals,
        "decisions": decisions,
        "npcs": entities,
        "threads": open_threads,
        "loot": loot
    }
    summary = await narrator_agent.generate_recap(scene_history, "gm_only", "standard")
    assert "Rusty Anchor" in summary
    assert "dragon rumors" in summary
    
    # Execute: Step 9 - Compile structured recap
    turn_stats = TurnStats(
        total=len(turns),
        by_type={TurnType.DIALOGUE: 1, TurnType.ACTION: 1, TurnType.DECISION: 1},
        duration=timedelta(minutes=30)
    )
    
    npcs = [NPCSummary(
        name="Innkeeper",
        role="Tavern owner",
        significance="minor",
        scenes=[sample_scene.id],
        relationship="Informant"
    )]
    
    threads_opened = [ThreadSummary(
        name="Dragon Threat",
        status="opened",
        description="Party discovers dragon rumors",
        next_steps="Investigate dragon lair"
    )]
    
    recap = Recap(
        id="recap-001",
        story_id=sample_scene.story_id,
        scene_id=sample_scene.id,
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="standard",
        summary=summary,
        key_events=["Arrived at Rusty Anchor", "Investigated basement", "Decided to pursue dragons"],
        decisions_made=decisions,
        npcs_encountered=npcs,
        threads_opened=threads_opened,
        threads_closed=[],
        loot_rewards=loot,
        turn_stats=turn_stats,
        proposal_stats=proposal_stats
    )
    
    # Execute: Step 10 - Save recap
    recap_id = await system_agent.create_recap(recap)
    assert recap_id == "recap-001"
    
    # Verify: Recap saved and linked
    assert system_agent.create_recap.called


# ============================================================================
# SCENARIO 2: Full Story Recap (Multi-Scene)
# ============================================================================

@pytest.mark.unit
async def test_scenario2_full_story_recap(system_agent, narrator_agent, neo4j_agent, fake_mongodb, fake_neo4j, fake_llm, sample_story):
    """
    Scenario 2: Full story recap across multiple scenes.
    
    Steps:
    1. Retrieve all scenes in story
    2. Process each scene
    3. Compile arc-level overview
    4. Generate comprehensive recap
    
    Expected Results:
    - Recap covers all 5 scenes
    - Narrative summary provides arc-level overview
    - Key events listed across all scenes
    - Decisions made across story captured
    - NPCs encountered across story listed
    - Threads opened/closed across story tracked
    - Loot/rewards accumulated across story
    - PDF export successful
    """
    # Setup: Mock 5 scenes
    scenes = []
    for i in range(5):
        scene = Scene(
            id=f"scene-{i}",
            story_id=sample_story.id,
            title=f"Scene {i+1}",
            status="final"
        )
        scenes.append(scene)
    
    system_agent.list_scenes = AsyncMock(return_value=scenes)
    
    # Mock turns for each scene
    system_agent.get_turns = AsyncMock(side_effect=[
        [Turn(f"turn-{i}-j", f"scene-{i}", TurnType.ACTION, "Action", datetime.now()) for j in range(20)]
        for i in range(5)
    ])
    
    system_agent.get_proposed_changes = AsyncMock(return_value=[])
    
    narrator_agent.generate_recap = AsyncMock(return_value="The party embarked on a grand adventure across five scenes. They faced challenges, made important decisions, and ultimately emerged victorious. The story arc progressed from investigation to confrontation to resolution.")
    
    # Execute: Retrieve all scenes
    all_scenes = await system_agent.list_scenes(sample_story.id, order="asc")
    assert len(all_scenes) == 5
    
    # Execute: Process all scenes
    all_turns = []
    for scene in all_scenes:
        turns = await system_agent.get_turns(scene.id)
        all_turns.extend(turns)
    
    assert len(all_turns) == 100  # 20 turns per scene
    
    # Execute: Generate arc-level summary
    scene_history = {
        "turns": all_turns,
        "proposals": [],
        "decisions": [],
        "npcs": [],
        "threads": [],
        "loot": []
    }
    
    summary = await narrator_agent.generate_recap(scene_history, "gm_only", "standard")
    assert "five scenes" in summary.lower() or "five" in summary.lower()
    
    # Compile comprehensive recap
    turn_stats = TurnStats(
        total=100,
        by_type={TurnType.ACTION: 100},
        duration=timedelta(hours=10)
    )
    
    proposal_stats = ProposalStats(
        total_accepted=0,
        by_type={},
        by_scene={}
    )
    
    recap = Recap(
        id="recap-full-story",
        story_id=sample_story.id,
        scene_id=None,
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="standard",
        summary=summary,
        key_events=[f"Scene {i+1} events" for i in range(5)],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=turn_stats,
        proposal_stats=proposal_stats
    )
    
    # Verify: Recap covers all scenes
    assert recap.scene_id is None  # Full story recap
    assert recap.story_id == sample_story.id
    assert turn_stats.total == 100


# ============================================================================
# SCENARIO 3: Most Recent Scene Recap (Quick)
# ============================================================================

@pytest.mark.unit
async def test_scenario3_most_recent_scene_recap(system_agent, narrator_agent, neo4j_agent, fake_mongodb, fake_neo4j, fake_llm, sample_story):
    """
    Scenario 3: Quick recap of most recent scene.
    
    Steps:
    1. Retrieve most recent scene in story
    2. Generate recap for that scene only
    3. Share with players via link
    
    Expected Results:
    - Recap generated for scene 3 only
    - Narrative summary covers recent session
    - Key events from last session listed
    - Recent decisions captured
    - Recent NPCs listed
    - Recent thread progress identified
    - Share link generated and accessible
    """
    # Setup: Mock scenes, scene 3 is most recent
    scenes = [
        Scene(id="scene-1", story_id=sample_story.id, title="Scene 1", status="final"),
        Scene(id="scene-2", story_id=sample_story.id, title="Scene 2", status="final"),
        Scene(id="scene-3", story_id=sample_story.id, title="Scene 3", status="final")
    ]
    
    system_agent.list_scenes = AsyncMock(return_value=[scenes[2]])  # Only last scene
    
    system_agent.get_turns = AsyncMock(return_value=[
        Turn("turn-3-1", "scene-3", TurnType.ACTION, "Recent action", datetime.now()),
        Turn("turn-3-2", "scene-3", TurnType.DIALOGUE, "Recent dialogue", datetime.now())
    ])
    
    system_agent.get_proposed_changes = AsyncMock(return_value=[])
    
    narrator_agent.generate_recap = AsyncMock(return_value="In the most recent session, the party took action and had important dialogue. This scene focused on immediate goals and short-term objectives.")
    
    narrator_agent.extract_decisions = AsyncMock(return_value=[
        Decision(
            description="Continue investigation",
            decision_maker="party",
            options_considered=["Continue", "Rest", "Retreat"],
            chosen_option="Continue",
            consequence="Press forward",
            scene_id="scene-3",
            turn_id="turn-3-1"
        )
    ])
    
    neo4j_agent.list_entities = AsyncMock(return_value=[{"name": "Recent NPC", "type": "character"}])
    neo4j_agent.list_plot_threads = AsyncMock(return_value=[])
    
    # Execute: Get most recent scene
    recent_scenes = await system_agent.list_scenes(sample_story.id, order="desc", limit=1)
    assert len(recent_scenes) == 1
    assert recent_scenes[0].id == "scene-3"
    
    recent_scene = recent_scenes[0]
    
    # Execute: Get turns for recent scene
    turns = await system_agent.get_turns(recent_scene.id)
    assert len(turns) == 2
    
    # Execute: Extract decisions
    decisions = await narrator_agent.extract_decisions(turns)
    assert len(decisions) == 1
    
    # Execute: Identify NPCs
    entities = await neo4j_agent.list_entities(sample_story.id, "character")
    assert len(entities) == 1
    assert entities[0]["name"] == "Recent NPC"
    
    # Execute: Generate summary
    scene_history = {
        "turns": turns,
        "proposals": [],
        "decisions": decisions,
        "npcs": entities,
        "threads": [],
        "loot": []
    }
    
    summary = await narrator_agent.generate_recap(scene_history, "party", "standard")
    assert "recent" in summary.lower()
    
    # Compile recap
    turn_stats = TurnStats(
        total=2,
        by_type={TurnType.ACTION: 1, TurnType.DIALOGUE: 1},
        duration=timedelta(minutes=30)
    )
    
    recap = Recap(
        id="recap-recent",
        story_id=sample_story.id,
        scene_id="scene-3",
        generated_at=datetime.now(),
        target_audience="party",  # Player accessible
        detail_level="standard",
        summary=summary,
        key_events=["Recent action", "Recent dialogue"],
        decisions_made=decisions,
        npcs_encountered=[NPCSummary(
            name="Recent NPC",
            role="Minor character",
            significance="minor",
            scenes=["scene-3"],
            relationship="Met in recent session"
        )],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=turn_stats,
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Verify: Recap is for recent scene only
    assert recap.scene_id == "scene-3"
    assert recap.target_audience == "party"


# ============================================================================
# SCENARIO 4: Recap with Custom Detail Level
# ============================================================================

@pytest.mark.unit
async def test_scenario4_custom_detail_level(system_agent, narrator_agent, fake_llm, sample_scene, sample_turns):
    """
    Scenario 4: Recap with different detail levels.
    
    Steps:
    1. Generate brief recap
    2. Generate detailed recap
    3. Compare and verify differences
    
    Expected Results:
    - Brief recap: 1-2 paragraphs, high-level overview only
    - Detailed recap: 3-4 paragraphs, includes minor details
    - Both recaps accurate to story
    - Detail level appropriately applied
    """
    # Setup
    system_agent.get_scene = AsyncMock(return_value=sample_scene)
    system_agent.get_turns = AsyncMock(return_value=sample_turns)
    
    # Mock brief recap
    narrator_agent.generate_recap = AsyncMock(side_effect=[
        "The party arrived at the Rusty Anchor. They investigated and decided to pursue the dragon.",  # Brief
        "The party arrived at the Rusty Anchor tavern, drawn by rumors of danger. After a brief conversation with the innkeeper, they investigated the basement where they found evidence of dragon activity. After careful consideration, the party decided to pursue the dragon rumors, understanding the risks involved. This decision would set them on a dangerous path."  # Detailed
    ])
    
    # Execute: Generate brief recap
    scene_history = {"turns": sample_turns, "proposals": [], "decisions": [], "npcs": [], "threads": [], "loot": []}
    
    brief_summary = await narrator_agent.generate_recap(scene_history, "gm_only", "brief")
    assert len(brief_summary) < 200  # Brief should be short
    
    brief_recap = Recap(
        id="recap-brief",
        story_id=sample_scene.story_id,
        scene_id=sample_scene.id,
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="brief",
        summary=brief_summary,
        key_events=["Arrived at Rusty Anchor", "Decided to pursue dragon"],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=3, by_type={}, duration=timedelta(minutes=30)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Execute: Generate detailed recap
    detailed_summary = await narrator_agent.generate_recap(scene_history, "gm_only", "detailed")
    assert len(detailed_summary) > 200  # Detailed should be longer
    
    detailed_recap = Recap(
        id="recap-detailed",
        story_id=sample_scene.story_id,
        scene_id=sample_scene.id,
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="detailed",
        summary=detailed_summary,
        key_events=["Arrived at Rusty Anchor", "Spoke with innkeeper", "Investigated basement", "Found dragon evidence", "Decided to pursue dragon"],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=3, by_type={}, duration=timedelta(minutes=30)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Verify: Detail levels differ
    assert brief_recap.detail_level == "brief"
    assert detailed_recap.detail_level == "detailed"
    assert len(brief_summary) < len(detailed_summary)
    assert len(brief_recap.key_events) < len(detailed_recap.key_events)


# ============================================================================
# SCENARIO 5: Recap for Player Audience
# ============================================================================

@pytest.mark.unit
async def test_scenario5_player_audience_recap(system_agent, narrator_agent, fake_llm, sample_scene, sample_turns):
    """
    Scenario 5: Recap filtered for player audience.
    
    Steps:
    1. Generate recap with player audience
    2. Verify GM-only info excluded
    
    Expected Results:
    - Recap generated with player-friendly content
    - GM-only secrets excluded from recap
    - Spoilers hidden or vague
    - Players can access and understand recap
    """
    # Setup
    system_agent.get_scene = AsyncMock(return_value=sample_scene)
    system_agent.get_turns = AsyncMock(return_value=sample_turns)
    
    # Mock player-safe recap (no GM secrets)
    narrator_agent.generate_recap = AsyncMock(return_value="The party arrived at the Rusty Anchor. They investigated the basement and found something interesting. They decided to pursue this new lead together.")
    
    # Execute: Generate player audience recap
    scene_history = {"turns": sample_turns, "proposals": [], "decisions": [], "npcs": [], "threads": [], "loot": []}
    
    summary = await narrator_agent.generate_recap(scene_history, "party", "standard")
    
    # Verify: GM-only secrets not mentioned
    assert "dragon" not in summary.lower() or "rumors" in summary.lower()  # If mentioned, should be vague
    assert "secret" not in summary.lower()
    
    # Compile player-safe recap
    recap = Recap(
        id="recap-player",
        story_id=sample_scene.story_id,
        scene_id=sample_scene.id,
        generated_at=datetime.now(),
        target_audience="party",  # Player accessible
        detail_level="standard",
        summary=summary,
        key_events=["Arrived at Rusty Anchor", "Investigated basement", "Found interesting clue", "Decided to pursue lead"],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=3, by_type={}, duration=timedelta(minutes=30)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Verify: Player-accessible
    assert recap.target_audience == "party"
    assert all("secret" not in event.lower() for event in recap.key_events)


# ============================================================================
# ERROR CASES
# ============================================================================

@pytest.mark.unit
async def test_error_scene_not_found(system_agent, fake_mongodb):
    """
    Error Case 1: Scene ID doesn't exist.
    
    Expected: Raise SceneNotFoundError with clear message
    """
    # Setup: Scene doesn't exist
    system_agent.get_scene = AsyncMock(side_effect=Exception("Scene not found: scene-999"))
    
    # Execute & Verify: Error raised
    with pytest.raises(Exception) as exc_info:
        await system_agent.get_scene("scene-999")
    
    assert "Scene not found" in str(exc_info.value)


@pytest.mark.unit
async def test_error_scene_not_finalized(system_agent, fake_mongodb):
    """
    Error Case 2: Scene status is not "review" or "final".
    
    Expected: Raise SceneNotFinalizedError with message explaining scene must be finalized
    """
    # Setup: Scene not finalized
    not_finalized_scene = Scene(
        id="scene-not-final",
        story_id="story-123",
        title="Draft Scene",
        status="draft"  # Not finalized
    )
    
    system_agent.get_scene = AsyncMock(return_value=not_finalized_scene)
    
    # Execute: Get scene
    scene = await system_agent.get_scene("scene-not-final")
    
    # Verify: Scene is not finalized
    assert scene.status == "draft"
    
    # In real implementation, this would raise SceneNotFinalizedError
    # For this test, we verify the scene status check
    if scene.status not in ["review", "final"]:
        raise Exception(f"Scene not finalized: status is {scene.status}")


@pytest.mark.unit
async def test_error_empty_scene(system_agent, fake_mongodb):
    """
    Error Case 3: Scene has no turns or is empty.
    
    Expected: Raise EmptySceneError with message explaining scene is empty
    """
    # Setup: Scene with no turns
    system_agent.get_turns = AsyncMock(return_value=[])
    
    # Execute: Get turns
    turns = await system_agent.get_turns("scene-empty")
    
    # Verify: Scene is empty
    assert len(turns) == 0
    
    # In real implementation, this would raise EmptySceneError
    if len(turns) == 0:
        raise Exception("Scene is empty: no turns found")


@pytest.mark.unit
async def test_error_llm_failure(narrator_agent, fake_llm, sample_turns):
    """
    Error Case 4: Narrator LLM fails to generate summary.
    
    Expected: Use template-based summary (fallback), log error
    """
    # Setup: LLM fails
    narrator_agent.generate_recap = AsyncMock(side_effect=Exception("LLM timeout"))
    
    # Execute & Verify: Error raised (in real implementation, would use fallback)
    with pytest.raises(Exception) as exc_info:
        scene_history = {"turns": sample_turns, "proposals": [], "decisions": [], "npcs": [], "threads": [], "loot": []}
        await narrator_agent.generate_recap(scene_history, "gm_only", "standard")
    
    assert "LLM timeout" in str(exc_info.value)


@pytest.mark.unit
async def test_error_export_failure():
    """
    Error Case 5: Cannot export recap to requested format.
    
    Expected: Retry with alternative format, log error
    """
    # Setup: Export function fails
    def export_recap(recap: Recap, format: str):
        if format == "pdf":
            raise Exception("PDF export failed")
        return f"Recap exported as {format}"
    
    # Execute: Try PDF export (fails)
    recap = Recap(
        id="recap-001",
        story_id="story-123",
        scene_id="scene-123",
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="standard",
        summary="Test summary",
        key_events=[],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=0, by_type={}, duration=timedelta(0)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    with pytest.raises(Exception) as exc_info:
        export_recap(recap, "pdf")
    
    assert "PDF export failed" in str(exc_info.value)
    
    # Execute: Try Markdown export (succeeds)
    result = export_recap(recap, "markdown")
    assert result == "Recap exported as markdown"


# ============================================================================
# SUCCESS CRITERIA TESTS
# ============================================================================

@pytest.mark.unit
async def test_success_criterion_summary_quality(narrator_agent, fake_llm, sample_turns):
    """
    Success Criterion 1: Narrative summary accurately captures session events (≥90% coverage).
    
    Verify: Summary covers major events accurately
    """
    # Setup: Comprehensive scene with 100 turns
    many_turns = [
        Turn(f"turn-{i}", "scene-001", TurnType.ACTION, f"Event {i}", datetime.now())
        for i in range(100)
    ]
    
    narrator_agent.generate_recap = AsyncMock(return_value="The party experienced many events. They began by arriving, then explored, then fought, then rested, and finally departed. Each phase brought new challenges and discoveries.")
    
    # Execute: Generate summary
    scene_history = {"turns": many_turns, "proposals": [], "decisions": [], "npcs": [], "threads": [], "loot": []}
    summary = await narrator_agent.generate_recap(scene_history, "gm_only", "standard")
    
    # Verify: Summary covers major phases (arrival, exploration, combat, rest, departure)
    phases = ["arriving", "explor", "fight", "rest", "depart"]
    coverage = sum(1 for phase in phases if phase in summary.lower())
    coverage_percentage = (coverage / len(phases)) * 100
    
    assert coverage_percentage >= 80  # At least 80% coverage of major phases


@pytest.mark.unit
async def test_success_criterion_structured_data_completeness():
    """
    Success Criterion 2: All major decisions, NPCs, and threads captured.
    
    Verify: Structured data is complete and accurate
    """
    # Setup: Complete recap with all structured data
    decisions = [
        Decision(
            description="Decision 1",
            decision_maker="party",
            options_considered=["A", "B"],
            chosen_option="A",
            consequence="Outcome A",
            scene_id="scene-001",
            turn_id="turn-001"
        )
    ]
    
    npcs = [
        NPCSummary(
            name="NPC 1",
            role="Role",
            significance="major",
            scenes=["scene-001"],
            relationship="Ally"
        )
    ]
    
    threads = [
        ThreadSummary(
            name="Thread 1",
            status="opened",
            description="Description",
            next_steps="Next steps"
        )
    ]
    
    loot = [
        Loot(
            item_name="Item 1",
            recipient="party",
            acquisition_method="found",
            scene_id="scene-001",
            turn_id="turn-001"
        )
    ]
    
    # Compile recap
    recap = Recap(
        id="recap-complete",
        story_id="story-123",
        scene_id="scene-001",
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="standard",
        summary="Summary",
        key_events=["Event 1", "Event 2"],
        decisions_made=decisions,
        npcs_encountered=npcs,
        threads_opened=threads,
        threads_closed=[],
        loot_rewards=loot,
        turn_stats=TurnStats(total=2, by_type={}, duration=timedelta(0)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Verify: All structured data present
    assert len(recap.decisions_made) == 1
    assert len(recap.npcs_encountered) == 1
    assert len(recap.threads_opened) == 1
    assert len(recap.loot_rewards) == 1
    assert len(recap.key_events) == 2


@pytest.mark.unit
async def test_success_criterion_tone_consistency(narrator_agent, fake_llm):
    """
    Success Criterion 3: Recap matches story tone and genre.
    
    Verify: Summary uses appropriate language for genre
    """
    # Setup: Fantasy genre story
    scene_history = {
        "turns": [],
        "proposals": [],
        "decisions": [],
        "npcs": [],
        "threads": [],
        "loot": [],
        "genre": "fantasy",
        "tone": "epic"
    }
    
    narrator_agent.generate_recap = AsyncMock(return_value="The brave knights ventured forth, their armor gleaming in the sunlight. Dragons soared above, casting shadows on the ancient castle. Magic pulsed through the air as the heroes prepared for their legendary quest.")
    
    # Execute: Generate summary
    summary = await narrator_agent.generate_recap(scene_history, "gm_only", "standard")
    
    # Verify: Fantasy-appropriate language
    fantasy_words = ["knights", "dragons", "castle", "magic", "quest", "legendary"]
    has_fantasy_tone = any(word in summary.lower() for word in fantasy_words)
    
    assert has_fantasy_tone


@pytest.mark.unit
async def test_success_criterion_export_successful():
    """
    Success Criterion 4: All export formats work correctly.
    
    Verify: Recap can be exported to multiple formats
    """
    # Setup: Complete recap
    recap = Recap(
        id="recap-export",
        story_id="story-123",
        scene_id="scene-001",
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="standard",
        summary="Summary",
        key_events=["Event 1"],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=1, by_type={}, duration=timedelta(0)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Mock export functions
    def export_markdown(r: Recap) -> str:
        return f"# Recap\n\n{r.summary}"
    
    def export_pdf(r: Recap) -> bytes:
        return b"PDF content"
    
    def export_plain_text(r: Recap) -> str:
        return r.summary
    
    # Execute: Export to all formats
    markdown_result = export_markdown(recap)
    pdf_result = export_pdf(recap)
    plain_text_result = export_plain_text(recap)
    
    # Verify: All formats successful
    assert isinstance(markdown_result, str)
    assert isinstance(pdf_result, bytes)
    assert isinstance(plain_text_result, str)
    assert "Recap" in markdown_result
    assert recap.summary in plain_text_result


@pytest.mark.unit
async def test_success_criterion_player_accessibility():
    """
    Success Criterion 5: Players can access shared recaps.
    
    Verify: Player-audience recaps are accessible and safe
    """
    # Setup: Player-accessible recap
    recap = Recap(
        id="recap-player",
        story_id="story-123",
        scene_id="scene-001",
        generated_at=datetime.now(),
        target_audience="party",  # Player accessible
        detail_level="standard",
        summary="The party arrived and explored. They found a clue and decided to investigate further.",
        key_events=["Arrived", "Explored", "Found clue", "Decided to investigate"],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=4, by_type={}, duration=timedelta(0)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Verify: Recap is player-safe
    assert recap.target_audience == "party"
    assert all("secret" not in event.lower() for event in recap.key_events)
    assert "secret" not in recap.summary.lower()
    assert "spoiler" not in recap.summary.lower()


@pytest.mark.unit
async def test_success_criterion_performance():
    """
    Success Criterion 6: Recap generated within 30 seconds for typical session (50-100 turns).
    
    Verify: Generation performance is acceptable
    """
    # Setup: Typical session with 75 turns
    import time
    
    typical_turns = [
        Turn(f"turn-{i}", "scene-001", TurnType.ACTION, f"Event {i}", datetime.now())
        for i in range(75)
    ]
    
    narrator_agent = NarratorAgent(Mock())
    narrator_agent.generate_recap = AsyncMock(return_value="Summary of session events.")
    
    # Execute: Generate recap and measure time
    start_time = time.time()
    
    scene_history = {"turns": typical_turns, "proposals": [], "decisions": [], "npcs": [], "threads": [], "loot": []}
    summary = await narrator_agent.generate_recap(scene_history, "gm_only", "standard")
    
    end_time = time.time()
    duration = end_time - start_time
    
    # Verify: Generated within 30 seconds
    assert duration < 30.0
    assert summary is not None


# ============================================================================
# POSTCONDITIONS VERIFICATION
# ============================================================================

@pytest.mark.unit
async def test_postcondition_recap_generated(system_agent, narrator_agent, fake_llm, sample_scene, sample_turns):
    """
    Postcondition 1: Recap generated with all sections.
    
    Verify: Structured recap created with all required sections
    """
    # Setup
    system_agent.get_scene = AsyncMock(return_value=sample_scene)
    system_agent.get_turns = AsyncMock(return_value=sample_turns)
    system_agent.get_proposed_changes = AsyncMock(return_value=[])
    
    narrator_agent.generate_recap = AsyncMock(return_value="Summary")
    narrator_agent.extract_decisions = AsyncMock(return_value=[])
    narrator_agent.extract_loot = AsyncMock(return_value=[])
    
    # Execute: Generate recap
    scene_history = {
        "turns": sample_turns,
        "proposals": [],
        "decisions": [],
        "npcs": [],
        "threads": [],
        "loot": []
    }
    
    summary = await narrator_agent.generate_recap(scene_history, "gm_only", "standard")
    
    # Compile recap
    recap = Recap(
        id="recap-post1",
        story_id=sample_scene.story_id,
        scene_id=sample_scene.id,
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="standard",
        summary=summary,
        key_events=[],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=3, by_type={}, duration=timedelta(0)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Verify: All sections present
    assert recap.summary is not None
    assert recap.key_events is not None
    assert recap.decisions_made is not None
    assert recap.npcs_encountered is not None
    assert recap.threads_opened is not None
    assert recap.threads_closed is not None
    assert recap.loot_rewards is not None
    assert recap.turn_stats is not None
    assert recap.proposal_stats is not None


@pytest.mark.unit
async def test_postcondition_recap_saved(system_agent, fake_mongodb):
    """
    Postcondition 2: Recap stored in MongoDB.
    
    Verify: Recap document saved to MongoDB
    """
    # Setup
    recap = Recap(
        id="recap-post2",
        story_id="story-123",
        scene_id="scene-001",
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="standard",
        summary="Summary",
        key_events=[],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=0, by_type={}, duration=timedelta(0)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    system_agent.create_recap = AsyncMock(return_value="recap-post2")
    
    # Execute: Save recap
    recap_id = await system_agent.create_recap(recap)
    
    # Verify: Recap saved
    assert recap_id == "recap-post2"
    assert system_agent.create_recap.called


@pytest.mark.unit
async def test_postcondition_recap_linked(system_agent, fake_mongodb):
    """
    Postcondition 3: Recap linked to story/scene.
    
    Verify: Scene updated with recap link
    """
    # Setup
    system_agent.update_scene = AsyncMock(return_value=True)
    
    # Execute: Update scene with recap link
    success = await system_agent.update_scene("scene-001", {"recap_id": "recap-001"})
    
    # Verify: Scene updated
    assert success is True
    assert system_agent.update_scene.called
    assert system_agent.update_scene.call_args[1]["args"][0] == "scene-001"
    assert system_agent.update_scene.call_args[1]["args"][1]["recap_id"] == "recap-001"


@pytest.mark.unit
async def test_postcondition_export_options_available():
    """
    Postcondition 4: Export options available.
    
    Verify: User can export or share recap in multiple formats
    """
    # Setup: Complete recap
    recap = Recap(
        id="recap-export",
        story_id="story-123",
        scene_id="scene-001",
        generated_at=datetime.now(),
        target_audience="gm_only",
        detail_level="standard",
        summary="Summary",
        key_events=[],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=0, by_type={}, duration=timedelta(0)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Mock export options
    export_options = ["markdown", "pdf", "plain_text", "html"]
    
    # Verify: All export options available
    for option in export_options:
        assert option in export_options
    
    # In real implementation, each export option would be tested


@pytest.mark.unit
async def test_postcondition_player_accessible():
    """
    Postcondition 5: If target audience is "party" or "public", players can view.
    
    Verify: Player-audience recaps are accessible
    """
    # Setup: Player-accessible recap
    recap = Recap(
        id="recap-player",
        story_id="story-123",
        scene_id="scene-001",
        generated_at=datetime.now(),
        target_audience="party",  # Player accessible
        detail_level="standard",
        summary="Player-safe summary",
        key_events=[],
        decisions_made=[],
        npcs_encountered=[],
        threads_opened=[],
        threads_closed=[],
        loot_rewards=[],
        turn_stats=TurnStats(total=0, by_type={}, duration=timedelta(0)),
        proposal_stats=ProposalStats(total_accepted=0, by_type={}, by_scene={})
    )
    
    # Verify: Player accessible
    assert recap.target_audience in ["party", "public"]
    
    # In real implementation, this would verify player access permissions