"""
Behavior tests for P-21: Downtime & Character Progression.

Tests verify that actual implementation matches behavior specifications:
1. System flow matches step-by-step actions
2. All preconditions and postconditions are enforced
3. Error cases are handled correctly
4. Success criteria are met

Use Case: https://github.com/spuentesp/monitor_dm_system/blob/main/docs/use-cases/behaviors/P-21-behaviors.md
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


import uuid
from datetime import datetime
from typing import Any
from enum import Enum

import pytest
from pydantic import BaseModel


# --- Mock Schema Classes (based on behavior spec) ---

class UpgradeType(Enum):
    """Type of upgrade."""
    LEVEL_UP = "level_up"
    ATTRIBUTE = "attribute"
    SKILL = "skill"


class UpgradeOption(BaseModel):
    """Upgrade option available to character."""
    type: UpgradeType
    attribute: str | None = None
    skill: str | None = None
    cost: int
    description: str
    new_value: int | None = None
    new_level: int | None = None


class CharacterProgression(BaseModel):
    """Character progression data."""
    character_id: str
    name: str
    level: int
    xp: int
    xp_to_next_level: int
    attributes: dict[str, int]
    skills: dict[str, int]
    available_upgrades: list[UpgradeOption]


class ProgressionRules(BaseModel):
    """Progression rules from game system."""
    system_id: str
    system_name: str
    core_mechanic: str
    level_up_xp: int
    attribute_costs: dict[str, int]
    skill_costs: dict[str, int]
    level_benefits: dict[int, list[str]]
    max_attributes: dict[str, int]
    max_skills: dict[str, int]


class ValidationResult(BaseModel):
    """Validation result for upgrade selection."""
    valid: bool
    errors: list[str]


class ProposedChange(BaseModel):
    """Proposed change for CanonKeeper."""
    entity_id: str
    change_type: str
    changes: dict[str, Any]
    reason: str
    evidence_refs: list[dict[str, Any]]


class CanonResult(BaseModel):
    """Result from CanonKeeper."""
    success: bool
    conflicts: list[dict[str, Any]]
    errors: list[str]


class TurnType(Enum):
    """Turn type enum."""
    ACTION = "ACTION"
    NARRATION = "NARRATION"
    PROGRESSION = "PROGRESSION"


class TurnCreate(BaseModel):
    """Turn creation request."""
    speaker_id: str
    turn_type: TurnType
    content: str
    metadata: dict[str, Any]


class Turn(BaseModel):
    """Turn entity."""
    turn_id: uuid.UUID
    speaker_id: str
    turn_type: TurnType
    content: str
    metadata: dict[str, Any]


class Scene(BaseModel):
    """Scene entity."""
    scene_id: uuid.UUID
    story_id: uuid.UUID
    tags: list[str]
    turns: list[Turn]
    updated_at: datetime


class Story(BaseModel):
    """Story entity."""
    story_id: uuid.UUID
    arc_label: str | None
    updated_at: datetime


# --- Mock Agent Classes (based on behavior spec) ---

class ProgressionLoop:
    """Mock ProgressionLoop agent."""
    
    def __init__(self, mcp_client, canonkeeper, narrator):
        self.mcp_client = mcp_client
        self.canonkeeper = canonkeeper
        self.narrator = narrator
        self.scenes = {}
        self.created_turns = []
        self.downtime_detections = []
    
    def detect_downtime_trigger(self, story: Story, scene: Scene) -> bool:
        """Detect if downtime trigger is active."""
        # Check story arc status
        if story.arc_label == 'resolution':
            self.downtime_detections.append(("story_arc", story.story_id))
            return True
        
        # Check scene designation
        if scene.tags:
            if 'rest' in scene.tags or 'downtime' in scene.tags:
                self.downtime_detections.append(("scene_tag", scene.scene_id))
                return True
        
        return False
    
    def query_character_progression(self, character_id: str) -> CharacterProgression:
        """Query character entity from Neo4j."""
        # Mock: Return character progression data
        return CharacterProgression(
            character_id=character_id,
            name="Aragorn",
            level=1,
            xp=1000,
            xp_to_next_level=1000,
            attributes={"strength": 14, "dexterity": 12, "constitution": 14},
            skills={"stealth": 0, "perception": 0},
            available_upgrades=[]
        )
    
    def query_progression_rules(self, system_id: str, level: int) -> ProgressionRules:
        """Query progression rules from game system."""
        # Mock: Return progression rules
        return ProgressionRules(
            system_id=system_id,
            system_name="D&D 5e",
            core_mechanic="D20",
            level_up_xp=1000,
            attribute_costs={"strength": 50, "dexterity": 50, "constitution": 50},
            skill_costs={"stealth": 25, "perception": 25},
            level_benefits={
                1: ["Proficiency Bonus +2", "Hit Points +8"],
                2: ["Proficiency Bonus +2", "Hit Points +8"],
                3: ["Proficiency Bonus +2", "Hit Points +8", "Extra Attack"]
            },
            max_attributes={"strength": 20, "dexterity": 20, "constitution": 20},
            max_skills={"stealth": 5, "perception": 5}
        )
    
    def calculate_upgrades(self, progression: CharacterProgression, rules: ProgressionRules) -> list[UpgradeOption]:
        """Calculate available upgrades based on XP."""
        available_upgrades = []
        
        # Level up
        if progression.xp >= rules.level_up_xp:
            available_upgrades.append(UpgradeOption(
                type=UpgradeType.LEVEL_UP,
                cost=rules.level_up_xp,
                description=f'Level up to {progression.level + 1}',
                new_level=progression.level + 1
            ))
        
        # Attributes
        for attr, cost in rules.attribute_costs.items():
            if progression.xp >= cost:
                current_value = progression.attributes.get(attr, 10)
                max_value = rules.max_attributes.get(attr, 20)
                if current_value < max_value:
                    available_upgrades.append(UpgradeOption(
                        type=UpgradeType.ATTRIBUTE,
                        attribute=attr,
                        cost=cost,
                        description=f'Increase {attr} from {current_value} to {current_value + 1}',
                        new_value=current_value + 1
                    ))
        
        # Skills
        for skill, cost in rules.skill_costs.items():
            if progression.xp >= cost:
                current_level = progression.skills.get(skill, 0)
                max_level = rules.max_skills.get(skill, 5)
                if current_level < max_level:
                    available_upgrades.append(UpgradeOption(
                        type=UpgradeType.SKILL,
                        skill=skill,
                        cost=cost,
                        description=f'Train {skill} from {current_level} to {current_level + 1}',
                        new_level=current_level + 1
                    ))
        
        return available_upgrades
    
    def present_progression_ui(self, progression: CharacterProgression, upgrades: list[UpgradeOption]) -> str:
        """Present progression UI or prompt."""
        if not upgrades:
            return f"No upgrades available with current XP ({progression.xp})."
        
        prompt = f"""
🔔 DOWNTIME & PROGRESSION 🔔

Character: {progression.name}
Level: {progression.level}
XP: {progression.xp} / {progression.xp_to_next_level}

Available Upgrades:
"""
        
        for i, upgrade in enumerate(upgrades, 1):
            prompt += f"{i}. {upgrade.description} (Cost: {upgrade.cost} XP)\n"
        
        prompt += "\nSelect upgrades by number (comma-separated), or 'done' to skip.\n"
        
        return prompt
    
    def parse_selection(self, input: str, upgrades: list[UpgradeOption]) -> list[UpgradeOption]:
        """Parse user selection."""
        if input.lower() == 'done':
            return []
        
        try:
            selected_indices = [int(x.strip()) for x in input.split(',')]
        except ValueError:
            return []  # Invalid input
        
        selected_upgrades = []
        
        for index in selected_indices:
            if 1 <= index <= len(upgrades):
                selected_upgrades.append(upgrades[index - 1])
        
        return selected_upgrades
    
    def validate_selection(self, upgrades: list[UpgradeOption], rules: ProgressionRules, progression: CharacterProgression) -> ValidationResult:
        """Validate selection against game system rules."""
        validation = ValidationResult(valid=True, errors=[])
        
        total_cost = sum(u.cost for u in upgrades)
        if total_cost > progression.xp:
            validation.valid = False
            validation.errors.append(f"Total cost ({total_cost}) exceeds available XP ({progression.xp})")
        
        for upgrade in upgrades:
            if upgrade.type == UpgradeType.ATTRIBUTE:
                current_value = progression.attributes.get(upgrade.attribute or "", 10)
                max_value = rules.max_attributes.get(upgrade.attribute or "", 20)
                if current_value >= max_value:
                    validation.valid = False
                    validation.errors.append(f"{upgrade.attribute} already at max ({max_value})")
            
            if upgrade.type == UpgradeType.SKILL:
                current_level = progression.skills.get(upgrade.skill or "", 0)
                max_level = rules.max_skills.get(upgrade.skill or "", 5)
                if current_level >= max_level:
                    validation.valid = False
                    validation.errors.append(f"{upgrade.skill} already at max ({max_level})")
        
        return validation
    
    def create_proposed_changes(self, character_id: str, upgrades: list[UpgradeOption]) -> list[ProposedChange]:
        """Create ProposedChanges for CanonKeeper."""
        proposed_changes = []
        
        for upgrade in upgrades:
            if upgrade.type == UpgradeType.LEVEL_UP:
                proposed_changes.append(ProposedChange(
                    entity_id=character_id,
                    change_type='level_up',
                    changes={'level': upgrade.new_level},
                    reason="Character progression during downtime",
                    evidence_refs=[{"source": "progression", "upgrade_type": "level_up"}]
                ))
            
            if upgrade.type == UpgradeType.ATTRIBUTE:
                proposed_changes.append(ProposedChange(
                    entity_id=character_id,
                    change_type='attribute_increase',
                    changes={f'attributes.{upgrade.attribute}': upgrade.new_value},
                    reason="Character progression during downtime",
                    evidence_refs=[{"source": "progression", "upgrade_type": "attribute", "attribute": upgrade.attribute}]
                ))
            
            if upgrade.type == UpgradeType.SKILL:
                proposed_changes.append(ProposedChange(
                    entity_id=character_id,
                    change_type='skill_training',
                    changes={f'skills.{upgrade.skill}': upgrade.new_level},
                    reason="Character progression during downtime",
                    evidence_refs=[{"source": "progression", "upgrade_type": "skill", "skill": upgrade.skill}]
                ))
        
        return proposed_changes
    
    async def append_progression_turns(
        self,
        scene_id: uuid.UUID,
        user_selection: str,
        response: str,
        upgrades: list[UpgradeOption],
        user_id: str
    ) -> list[Turn]:
        """Append progression turns to scene."""
        scene = self.scenes.get(scene_id)
        if not scene:
            raise ValueError("Scene not found")
        
        # Create user turn
        user_turn = Turn(
            turn_id=uuid.uuid4(),
            speaker_id=user_id,
            turn_type=TurnType.PROGRESSION,
            content=user_selection,
            metadata={
                "downtime_triggered": True,
                "upgrades_selected": [u.type.value for u in upgrades],
                "xp_spent": sum(u.cost for u in upgrades)
            }
        )
        
        # Create GM turn
        gm_turn = Turn(
            turn_id=uuid.uuid4(),
            speaker_id="system:progression",
            turn_type=TurnType.NARRATION,
            content=response,
            metadata={
                "progression_applied": len(upgrades) > 0,
                "upgrades_applied": [u.description for u in upgrades],
                "canonized": len(upgrades) > 0
            }
        )
        
        self.created_turns.extend([user_turn, gm_turn])
        scene.turns.extend([user_turn, gm_turn])
        self.scenes[scene_id] = scene
        
        return [user_turn, gm_turn]


class CanonKeeper:
    """Mock CanonKeeper agent."""
    
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.committed_changes = []
    
    async def evaluate_and_commit(self, proposed_changes: list[ProposedChange]) -> CanonResult:
        """Evaluate and commit changes."""
        # Mock: Always accept and commit
        for change in proposed_changes:
            self.committed_changes.append(change)
        
        return CanonResult(
            success=True,
            conflicts=[],
            errors=[]
        )


class NarratorAgent:
    """Mock NarratorAgent."""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.descriptions = []
    
    def describe_progression(self, upgrades: list[UpgradeOption], character_name: str) -> str:
        """Generate narrative description of progression."""
        if not upgrades:
            return f"{character_name} rests and reflects on their journey."
        
        upgrade_descriptions = [u.description for u in upgrades]
        
        description = (
            f"{character_name} spends their downtime training and reflecting, "
            f"gaining new abilities and insights: {', '.join(upgrade_descriptions)}."
        )
        
        self.descriptions.append((character_name, upgrades, description))
        return description


# --- Fixtures ---

@pytest.fixture
def user_id():
    """Mock user ID."""
    return str(uuid.uuid4())


@pytest.fixture
def character_id():
    """Mock character ID."""
    return str(uuid.uuid4())


@pytest.fixture
def system_id():
    """Mock game system ID."""
    return "dnd-5e"


@pytest.fixture
def story_id():
    """Mock story ID."""
    return uuid.uuid4()


@pytest.fixture
def scene_id():
    """Mock scene ID."""
    return uuid.uuid4()


@pytest.fixture
def fake_mcp_client():
    """Fake MCP client from conftest."""
    from tests.conftest import FakeMCPClient
    return FakeMCPClient()


@pytest.fixture
def fake_llm_client():
    """Fake LLM client from conftest."""
    from tests.conftest import FakeLLMClient
    return FakeLLMClient()


@pytest.fixture
def canonkeeper(fake_mcp_client):
    """CanonKeeper agent fixture."""
    return CanonKeeper(fake_mcp_client)


@pytest.fixture
def narrator(fake_llm_client):
    """NarratorAgent fixture."""
    return NarratorAgent(fake_llm_client)


@pytest.fixture
def progression_loop(fake_mcp_client, canonkeeper, narrator):
    """ProgressionLoop agent fixture."""
    return ProgressionLoop(fake_mcp_client, canonkeeper, narrator)


@pytest.fixture
def story(story_id):
    """Story fixture."""
    return Story(
        story_id=story_id,
        arc_label="resolution",
        updated_at=datetime.utcnow()
    )


@pytest.fixture
def scene(story_id, scene_id):
    """Scene fixture."""
    return Scene(
        scene_id=scene_id,
        story_id=story_id,
        tags=["rest"],
        turns=[],
        updated_at=datetime.utcnow()
    )


# --- Test Scenarios from Behavior Spec ---


# Scenario 1: Level Up

@pytest.mark.unit
async def test_p21_scenario_1_level_up(
    progression_loop,
    canonkeeper,
    narrator,
    story,
    scene,
    character_id,
    system_id,
    user_id
):
    """
    Scenario 1: Level Up
    
    Given:
    - Character: "Aragorn"
    - Level: 1, XP: 1000
    - Game system: D&D 5e
    - Level up cost: 1000 XP
    
    When:
    - Downtime detected (story arc resolution)
    - Upgrades calculated: Level up available
    - User selects: "1" (level up)
    - Validation passes
    - CanonKeeper commits
    
    Then:
    - Character level updated to 2
    - XP reduced to 0
    - Narrator describes: "Aragorn reflects on his recent battles..."
    - User turn appended with metadata: upgrades_selected: ["level_up"], xp_spent: 1000
    - GM turn appended with metadata: progression_applied: True, upgrades_applied: ["Level up to 2"]
    """
    # Setup
    scene_id = scene.scene_id
    progression_loop.scenes[scene_id] = scene
    
    # Action 1: Detect Downtime Trigger
    downtime_detected = progression_loop.detect_downtime_trigger(story, scene)
    assert downtime_detected is True, "Should detect downtime trigger"
    assert len(progression_loop.downtime_detections) >= 1, "Should log downtime detection"
    
    # Action 2: Query Character Entity
    progression = progression_loop.query_character_progression(character_id)
    assert progression.name == "Aragorn", f"Expected name 'Aragorn', got '{progression.name}'"
    assert progression.level == 1, f"Expected level 1, got {progression.level}"
    assert progression.xp == 1000, f"Expected XP 1000, got {progression.xp}"
    
    # Action 3: Query Game System Rules
    rules = progression_loop.query_progression_rules(system_id, progression.level)
    assert rules.system_name == "D&D 5e", f"Expected system 'D&D 5e', got '{rules.system_name}'"
    assert rules.level_up_xp == 1000, f"Expected level_up_xp 1000, got {rules.level_up_xp}"
    
    # Action 4: Calculate Available Upgrades
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    assert len(upgrades) >= 1, f"Expected at least 1 upgrade, got {len(upgrades)}"
    
    # Should have level up available
    level_up_upgrades = [u for u in upgrades if u.type == UpgradeType.LEVEL_UP]
    assert len(level_up_upgrades) == 1, f"Expected 1 level up upgrade, got {len(level_up_upgrades)}"
    
    # Action 5: Present Progression UI
    prompt = progression_loop.present_progression_ui(progression, upgrades)
    assert "DOWNTIME & PROGRESSION" in prompt, "Prompt should mention downtime"
    assert progression.name in prompt, f"Prompt should include character name '{progression.name}'"
    assert "Level" in prompt, "Prompt should show level"
    assert "XP" in prompt, "Prompt should show XP"
    assert "Available Upgrades" in prompt, "Prompt should show upgrades"
    
    # Action 6: Parse User Selection
    user_selection = "1"
    selected_upgrades = progression_loop.parse_selection(user_selection, upgrades)
    assert len(selected_upgrades) == 1, f"Expected 1 selected upgrade, got {len(selected_upgrades)}"
    assert selected_upgrades[0].type == UpgradeType.LEVEL_UP, "Selected upgrade should be level up"
    
    # Action 7: Validate Selection
    validation = progression_loop.validate_selection(selected_upgrades, rules, progression)
    assert validation.valid is True, f"Validation should pass, errors: {validation.errors}"
    assert len(validation.errors) == 0, f"Should have no validation errors, got: {validation.errors}"
    
    # Action 8: Create ProposedChanges
    proposed_changes = progression_loop.create_proposed_changes(character_id, selected_upgrades)
    assert len(proposed_changes) == 1, f"Expected 1 proposed change, got {len(proposed_changes)}"
    assert proposed_changes[0].change_type == "level_up", "Change type should be level_up"
    assert proposed_changes[0].changes['level'] == 2, "New level should be 2"
    assert len(proposed_changes[0].evidence_refs) > 0, "Should have evidence refs"
    
    # Action 9: CanonKeeper Evaluates and Commits
    canon_result = await canonkeeper.evaluate_and_commit(proposed_changes)
    assert canon_result.success is True, "CanonKeeper should succeed"
    assert len(canon_result.errors) == 0, "Should have no errors"
    assert len(canonkeeper.committed_changes) == 1, "Should have 1 committed change"
    
    # Action 10: Narrator Describes Progression
    description = narrator.describe_progression(selected_upgrades, progression.name)
    assert description is not None, "Narrator should return description"
    assert progression.name in description, "Description should mention character name"
    assert "training" in description.lower() or "reflect" in description.lower(), \
        "Description should mention training or reflection"
    
    # Action 11: Append Turns
    turns = await progression_loop.append_progression_turns(
        scene_id,
        user_selection,
        description,
        selected_upgrades,
        user_id
    )
    
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    
    user_turn = turns[0]
    assert user_turn.turn_type == TurnType.PROGRESSION, f"Expected PROGRESSION, got {user_turn.turn_type}"
    assert user_turn.metadata.get("downtime_triggered") is True, "Should have downtime_triggered metadata"
    assert user_turn.metadata.get("upgrades_selected") == ["level_up"], "Should have upgrades_selected metadata"
    assert user_turn.metadata.get("xp_spent") == 1000, f"Expected xp_spent 1000, got {user_turn.metadata.get('xp_spent')}"
    
    gm_turn = turns[1]
    assert gm_turn.turn_type == TurnType.NARRATION, f"Expected NARRATION, got {gm_turn.turn_type}"
    assert gm_turn.speaker_id == "system:progression", f"Expected speaker 'system:progression', got {gm_turn.speaker_id}"
    assert gm_turn.metadata.get("progression_applied") is True, "Should have progression_applied=True"
    assert gm_turn.metadata.get("canonized") is True, "Should have canonized=True"
    assert len(gm_turn.metadata.get("upgrades_applied", [])) > 0, "Should have upgrades_applied metadata"


# Scenario 2: Multiple Upgrades

@pytest.mark.unit
async def test_p21_scenario_2_multiple_upgrades(
    progression_loop,
    canonkeeper,
    narrator,
    scene,
    user_id
):
    """
    Scenario 2: Multiple Upgrades
    
    Given:
    - Character: "Gimli"
    - Level: 1, XP: 150
    - Game system: D&D 5e
    - Attribute costs: {"strength": 50, "constitution": 50}
    - Current attributes: {"strength": 14, "constitution": 14}
    
    When:
    - Downtime detected
    - Upgrades calculated: Strength +1 (50 XP), Constitution +1 (50 XP)
    - User selects: "1,2" (both attributes)
    - Validation passes (total cost: 100 XP ≤ 150 XP)
    - CanonKeeper commits
    
    Then:
    - Strength updated to 15
    - Constitution updated to 15
    - XP reduced to 50
    - Narrator describes progression
    - User turn appended with metadata: upgrades_selected: ["attribute", "attribute"], xp_spent: 100
    - GM turn appended with metadata: progression_applied: True, upgrades_applied: both attributes
    """
    # Setup
    scene_id = scene.scene_id
    progression_loop.scenes[scene_id] = scene
    
    character_id = "gimli-id"
    
    # Create character progression for Gimli
    progression = CharacterProgression(
        character_id=character_id,
        name="Gimli",
        level=1,
        xp=150,
        xp_to_next_level=1000,
        attributes={"strength": 14, "constitution": 14},
        skills=[],
        available_upgrades=[]
    )
    
    # Create rules with attribute costs
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={"strength": 50, "constitution": 50},
        skill_costs={},
        level_benefits={},
        max_attributes={"strength": 20, "constitution": 20},
        max_skills={}
    )
    
    # Calculate upgrades
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    assert len(upgrades) >= 2, f"Expected at least 2 upgrades, got {len(upgrades)}"
    
    # Select both attribute upgrades
    user_selection = "1,2"
    selected_upgrades = progression_loop.parse_selection(user_selection, upgrades)
    
    # Should have 2 upgrades selected
    assert len(selected_upgrades) == 2, f"Expected 2 selected upgrades, got {len(selected_upgrades)}"
    
    # Validate selection
    validation = progression_loop.validate_selection(selected_upgrades, rules, progression)
    assert validation.valid is True, f"Validation should pass, errors: {validation.errors}"
    
    # Calculate total cost
    total_cost = sum(u.cost for u in selected_upgrades)
    assert total_cost == 100, f"Expected total cost 100, got {total_cost}"
    assert total_cost <= progression.xp, f"Total cost {total_cost} should be ≤ XP {progression.xp}"
    
    # Create proposed changes
    proposed_changes = progression_loop.create_proposed_changes(character_id, selected_upgrades)
    assert len(proposed_changes) == 2, f"Expected 2 proposed changes, got {len(proposed_changes)}"
    
    # Check that both attributes are in proposed changes
    change_types = [c.change_type for c in proposed_changes]
    assert "attribute_increase" in change_types, "Should have attribute_increase change"
    
    # CanonKeeper commits
    canon_result = await canonkeeper.evaluate_and_commit(proposed_changes)
    assert canon_result.success is True, "CanonKeeper should succeed"
    
    # Narrator describes
    description = narrator.describe_progression(selected_upgrades, progression.name)
    assert description is not None, "Narrator should return description"
    
    # Append turns
    turns = await progression_loop.append_progression_turns(
        scene_id,
        user_selection,
        description,
        selected_upgrades,
        user_id
    )
    
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    
    # Check user turn metadata
    user_turn = turns[0]
    assert user_turn.metadata.get("xp_spent") == 100, f"Expected xp_spent 100, got {user_turn.metadata.get('xp_spent')}"
    assert len(user_turn.metadata.get("upgrades_selected", [])) == 2, "Should have 2 upgrades selected"
    
    # Check GM turn metadata
    gm_turn = turns[1]
    assert len(gm_turn.metadata.get("upgrades_applied", [])) == 2, "Should have 2 upgrades applied"


# Scenario 3: No Upgrades Available

@pytest.mark.unit
async def test_p21_scenario_3_no_upgrades_available(
    progression_loop,
    narrator,
    scene,
    user_id
):
    """
    Scenario 3: No Upgrades Available
    
    Given:
    - Character: "Legolas"
    - Level: 5, XP: 10
    - Game system: D&D 5e
    - All attributes at max (20)
    - All skills at max (5)
    
    When:
    - Downtime detected
    - Upgrades calculated: None (insufficient XP, maxed stats)
    - System prompts: "No upgrades available with current XP."
    
    Then:
    - No upgrades selected
    - No XP spent
    - Narrator describes rest
    - User turn appended with metadata: upgrades_selected: [], xp_spent: 0
    - GM turn appended with metadata: progression_applied: False
    """
    # Setup
    scene_id = scene.scene_id
    progression_loop.scenes[scene_id] = scene
    
    # Create character with maxed stats
    progression = CharacterProgression(
        character_id="legolas-id",
        name="Legolas",
        level=5,
        xp=10,
        xp_to_next_level=5000,
        attributes={"strength": 20, "dexterity": 20, "constitution": 20},
        skills={"stealth": 5, "perception": 5},
        available_upgrades=[]
    )
    
    # Create rules with max limits
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=5000,
        attribute_costs={"strength": 50, "dexterity": 50, "constitution": 50},
        skill_costs={"stealth": 25, "perception": 25},
        level_benefits={},
        max_attributes={"strength": 20, "dexterity": 20, "constitution": 20},
        max_skills={"stealth": 5, "perception": 5}
    )
    
    # Calculate upgrades
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    assert len(upgrades) == 0, f"Expected 0 upgrades, got {len(upgrades)}"
    
    # Present UI should show no upgrades available
    prompt = progression_loop.present_progression_ui(progression, upgrades)
    assert "No upgrades available" in prompt, "Prompt should indicate no upgrades available"
    assert "XP" in prompt, "Prompt should mention XP"
    
    # User selects 'done'
    user_selection = "done"
    selected_upgrades = progression_loop.parse_selection(user_selection, upgrades)
    assert len(selected_upgrades) == 0, "Should have 0 selected upgrades"
    
    # Narrator describes
    description = narrator.describe_progression(selected_upgrades, progression.name)
    assert description is not None, "Narrator should return description"
    
    # Append turns
    turns = await progression_loop.append_progression_turns(
        scene_id,
        user_selection,
        description,
        selected_upgrades,
        user_id
    )
    
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    
    # Check metadata
    user_turn = turns[0]
    assert user_turn.metadata.get("xp_spent") == 0, "XP spent should be 0"
    assert len(user_turn.metadata.get("upgrades_selected", [])) == 0, "Should have 0 upgrades selected"
    
    gm_turn = turns[1]
    assert gm_turn.metadata.get("progression_applied") is False, "Progression should not be applied"


# Scenario 4: Insufficient XP for Selection

@pytest.mark.unit
async def test_p21_scenario_4_insufficient_xp(
    progression_loop,
    scene,
    user_id
):
    """
    Scenario 4: Insufficient XP for Selection
    
    Given:
    - Character: "Boromir"
    - Level: 1, XP: 75
    - Game system: D&D 5e
    - Attribute costs: {"strength": 50, "charisma": 50}
    
    When:
    - Downtime detected
    - Upgrades calculated: Strength +1 (50 XP), Charisma +1 (50 XP)
    - User selects: "1,2" (both attributes)
    - Validation fails (total cost: 100 XP > 75 XP)
    - System prompts: "Total cost (100) exceeds available XP (75)."
    - User reselects: "1" (only Strength)
    
    Then:
    - Strength updated to new value
    - Charisma unchanged
    - XP reduced to 25
    - Turn metadata shows single upgrade
    """
    # Setup
    scene_id = scene.scene_id
    progression_loop.scenes[scene_id] = scene
    
    character_id = "boromir-id"
    
    # Create character progression
    progression = CharacterProgression(
        character_id=character_id,
        name="Boromir",
        level=1,
        xp=75,
        xp_to_next_level=1000,
        attributes={"strength": 14, "charisma": 14},
        skills=[],
        available_upgrades=[]
    )
    
    # Create rules
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={"strength": 50, "charisma": 50},
        skill_costs={},
        level_benefits={},
        max_attributes={"strength": 20, "charisma": 20},
        max_skills={}
    )
    
    # Calculate upgrades
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    assert len(upgrades) >= 2, f"Expected at least 2 upgrades, got {len(upgrades)}"
    
    # User tries to select both
    user_selection_initial = "1,2"
    selected_upgrades_initial = progression_loop.parse_selection(user_selection_initial, upgrades)
    assert len(selected_upgrades_initial) == 2, "Should parse 2 upgrades initially"
    
    # Validate - should fail due to insufficient XP
    validation_initial = progression_loop.validate_selection(selected_upgrades_initial, rules, progression)
    assert validation_initial.valid is False, "Validation should fail for insufficient XP"
    assert len(validation_initial.errors) > 0, "Should have validation errors"
    assert any("exceeds" in error.lower() for error in validation_initial.errors), \
        "Error should mention exceeding XP"
    
    # User reselects only one upgrade
    user_selection_corrected = "1"
    selected_upgrades_corrected = progression_loop.parse_selection(user_selection_corrected, upgrades)
    assert len(selected_upgrades_corrected) == 1, "Should have 1 corrected upgrade"
    
    # Validate - should pass now
    validation_corrected = progression_loop.validate_selection(selected_upgrades_corrected, rules, progression)
    assert validation_corrected.valid is True, "Validation should pass for corrected selection"
    
    # Check total cost
    total_cost = sum(u.cost for u in selected_upgrades_corrected)
    assert total_cost == 50, f"Expected total cost 50, got {total_cost}"
    assert total_cost <= progression.xp, f"Total cost {total_cost} should be ≤ XP {progression.xp}"
    
    # Remaining XP
    remaining_xp = progression.xp - total_cost
    assert remaining_xp == 25, f"Expected remaining XP 25, got {remaining_xp}"


# Scenario 5: Skill Training

@pytest.mark.unit
async def test_p21_scenario_5_skill_training(
    progression_loop,
    canonkeeper,
    narrator,
    scene,
    user_id
):
    """
    Scenario 5: Skill Training
    
    Given:
    - Character: "Frodo"
    - Level: 1, XP: 50
    - Game system: D&D 5e
    - Skill costs: {"stealth": 25, "perception": 25}
    - Current skills: {"stealth": 0, "perception": 0}
    
    When:
    - Downtime detected
    - Upgrades calculated: Stealth +1 (25 XP), Perception +1 (25 XP)
    - User selects: "1,2" (both skills)
    - Validation passes (total cost: 50 XP ≤ 50 XP)
    - CanonKeeper commits
    
    Then:
    - Stealth updated to 1
    - Perception updated to 1
    - XP reduced to 0
    - Narrator describes skill training
    - Turn metadata shows both skills
    """
    # Setup
    scene_id = scene.scene_id
    progression_loop.scenes[scene_id] = scene
    
    character_id = "frodo-id"
    
    # Create character progression
    progression = CharacterProgression(
        character_id=character_id,
        name="Frodo",
        level=1,
        xp=50,
        xp_to_next_level=1000,
        attributes={},
        skills={"stealth": 0, "perception": 0},
        available_upgrades=[]
    )
    
    # Create rules with skill costs
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={},
        skill_costs={"stealth": 25, "perception": 25},
        level_benefits={},
        max_attributes={},
        max_skills={"stealth": 5, "perception": 5}
    )
    
    # Calculate upgrades
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    assert len(upgrades) >= 2, f"Expected at least 2 upgrades, got {len(upgrades)}"
    
    # Should have skill upgrades
    skill_upgrades = [u for u in upgrades if u.type == UpgradeType.SKILL]
    assert len(skill_upgrades) >= 2, f"Expected at least 2 skill upgrades, got {len(skill_upgrades)}"
    
    # Select both skills
    user_selection = "1,2"
    selected_upgrades = progression_loop.parse_selection(user_selection, upgrades)
    assert len(selected_upgrades) >= 2, f"Expected at least 2 selected upgrades, got {len(selected_upgrades)}"
    
    # Validate
    validation = progression_loop.validate_selection(selected_upgrades, rules, progression)
    assert validation.valid is True, f"Validation should pass, errors: {validation.errors}"
    
    # Total cost should be 50 XP
    total_cost = sum(u.cost for u in selected_upgrades)
    assert total_cost == 50, f"Expected total cost 50, got {total_cost}"
    
    # Create proposed changes
    proposed_changes = progression_loop.create_proposed_changes(character_id, selected_upgrades)
    assert len(proposed_changes) >= 2, f"Expected at least 2 proposed changes, got {len(proposed_changes)}"
    
    # Check that skills are in proposed changes
    skill_changes = [c for c in proposed_changes if c.change_type == "skill_training"]
    assert len(skill_changes) >= 2, f"Expected at least 2 skill changes, got {len(skill_changes)}"
    
    # CanonKeeper commits
    canon_result = await canonkeeper.evaluate_and_commit(proposed_changes)
    assert canon_result.success is True, "CanonKeeper should succeed"
    
    # Narrator describes
    description = narrator.describe_progression(selected_upgrades, progression.name)
    assert description is not None, "Narrator should return description"
    assert progression.name in description, "Description should mention character name"
    
    # Append turns
    turns = await progression_loop.append_progression_turns(
        scene_id,
        user_selection,
        description,
        selected_upgrades,
        user_id
    )
    
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    
    # Check metadata
    user_turn = turns[0]
    assert user_turn.metadata.get("xp_spent") == 50, f"Expected xp_spent 50, got {user_turn.metadata.get('xp_spent')}"
    assert "skill" in user_turn.metadata.get("upgrades_selected", []), "Should have skill upgrades selected"


# --- Error Case Tests ---

@pytest.mark.unit
async def test_p21_error_case_invalid_user_selection(progression_loop, scene):
    """
    Error Case: Invalid user selection
    
    When:
    - User provides invalid input
    
    Then:
    - Should handle gracefully, return empty list
    """
    # Calculate some upgrades
    progression = CharacterProgression(
        character_id="test-id",
        name="Test",
        level=1,
        xp=100,
        xp_to_next_level=1000,
        attributes={"strength": 14},
        skills={},
        available_upgrades=[]
    )
    
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={"strength": 50},
        skill_costs={},
        level_benefits={},
        max_attributes={"strength": 20},
        max_skills={}
    )
    
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    
    # Invalid input
    invalid_input = "what should I do?"
    selected_upgrades = progression_loop.parse_selection(invalid_input, upgrades)
    assert len(selected_upgrades) == 0, "Should return empty list for invalid input"


@pytest.mark.unit
def test_p21_error_case_duplicate_selection(progression_loop):
    """
    Error Case: Duplicate selection
    
    When:
    - User selects same upgrade multiple times
    
    Then:
    - Should handle duplicates correctly
    """
    progression = CharacterProgression(
        character_id="test-id",
        name="Test",
        level=1,
        xp=100,
        xp_to_next_level=1000,
        attributes={"strength": 14},
        skills={},
        available_upgrades=[]
    )
    
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={"strength": 50},
        skill_costs={},
        level_benefits={},
        max_attributes={"strength": 20},
        max_skills={}
    )
    
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    
    # Select same upgrade twice
    duplicate_input = "1,1"
    selected_upgrades = progression_loop.parse_selection(duplicate_input, upgrades)
    
    # Should have 2 entries (duplicate)
    assert len(selected_upgrades) == 2, "Should allow duplicate selections (validation will catch it)"


@pytest.mark.unit
def test_p21_error_case_max_attribute_reached(progression_loop):
    """
    Error Case: Max attribute reached
    
    When:
    - User tries to upgrade attribute already at max
    
    Then:
    - Validation should fail with appropriate error
    """
    progression = CharacterProgression(
        character_id="test-id",
        name="Test",
        level=1,
        xp=100,
        xp_to_next_level=1000,
        attributes={"strength": 20},  # Already at max
        skills={},
        available_upgrades=[]
    )
    
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={"strength": 50},
        skill_costs={},
        level_benefits={},
        max_attributes={"strength": 20},  # Max is 20
        max_skills={}
    )
    
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    
    # No upgrades should be available (strength already at max)
    assert len(upgrades) == 0, f"Expected 0 upgrades, got {len(upgrades)}"


# --- Success Criteria Tests ---

@pytest.mark.unit
def test_p21_success_criteria_downtime_detection(progression_loop, story, scene):
    """
    Success Criteria: Downtime detection 100% accuracy
    """
    # Test story arc trigger
    story_arc = Story(
        story_id=uuid.uuid4(),
        arc_label="resolution",
        updated_at=datetime.utcnow()
    )
    scene_no_tags = Scene(
        scene_id=uuid.uuid4(),
        story_id=story_arc.story_id,
        tags=[],
        turns=[],
        updated_at=datetime.utcnow()
    )
    
    detected = progression_loop.detect_downtime_trigger(story_arc, scene_no_tags)
    assert detected is True, "Should detect downtime from story arc"
    
    # Test scene tag trigger (rest)
    story_no_arc = Story(
        story_id=uuid.uuid4(),
        arc_label=None,
        updated_at=datetime.utcnow()
    )
    scene_rest = Scene(
        scene_id=uuid.uuid4(),
        story_id=story_no_arc.story_id,
        tags=["rest"],
        turns=[],
        updated_at=datetime.utcnow()
    )
    
    detected = progression_loop.detect_downtime_trigger(story_no_arc, scene_rest)
    assert detected is True, "Should detect downtime from rest tag"
    
    # Test scene tag trigger (downtime)
    scene_downtime = Scene(
        scene_id=uuid.uuid4(),
        story_id=story_no_arc.story_id,
        tags=["downtime"],
        turns=[],
        updated_at=datetime.utcnow()
    )
    
    detected = progression_loop.detect_downtime_trigger(story_no_arc, scene_downtime)
    assert detected is True, "Should detect downtime from downtime tag"
    
    # Test no trigger
    story_active = Story(
        story_id=uuid.uuid4(),
        arc_label="active",
        updated_at=datetime.utcnow()
    )
    scene_active = Scene(
        scene_id=uuid.uuid4(),
        story_id=story_active.story_id,
        tags=["combat"],
        turns=[],
        updated_at=datetime.utcnow()
    )
    
    detected = progression_loop.detect_downtime_trigger(story_active, scene_active)
    assert detected is False, "Should not detect downtime when no trigger"


@pytest.mark.unit
def test_p21_success_criteria_upgrade_calculation(progression_loop):
    """
    Success Criteria: Upgrade calculation 100% accuracy
    """
    # Test level up calculation
    progression = CharacterProgression(
        character_id="test-id",
        name="Test",
        level=1,
        xp=1000,
        xp_to_next_level=1000,
        attributes={},
        skills={},
        available_upgrades=[]
    )
    
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={},
        skill_costs={},
        level_benefits={},
        max_attributes={},
        max_skills={}
    )
    
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    level_up_upgrades = [u for u in upgrades if u.type == UpgradeType.LEVEL_UP]
    assert len(level_up_upgrades) == 1, "Should calculate level up when XP sufficient"
    
    # Test insufficient XP
    progression.xp = 500
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    level_up_upgrades = [u for u in upgrades if u.type == UpgradeType.LEVEL_UP]
    assert len(level_up_upgrades) == 0, "Should not calculate level up when XP insufficient"


@pytest.mark.unit
def test_p21_success_criteria_selection_parsing(progression_loop):
    """
    Success Criteria: Selection parsing 100% accuracy
    """
    progression = CharacterProgression(
        character_id="test-id",
        name="Test",
        level=1,
        xp=100,
        xp_to_next_level=1000,
        attributes={},
        skills={},
        available_upgrades=[]
    )
    
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={"strength": 50, "dexterity": 50},
        skill_costs={},
        level_benefits={},
        max_attributes={"strength": 20, "dexterity": 20},
        max_skills={}
    )
    
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    
    # Test single selection
    selected = progression_loop.parse_selection("1", upgrades)
    assert len(selected) == 1, "Should parse single selection"
    
    # Test multiple selection
    selected = progression_loop.parse_selection("1,2", upgrades)
    assert len(selected) == 2, "Should parse multiple selections"
    
    # Test 'done'
    selected = progression_loop.parse_selection("done", upgrades)
    assert len(selected) == 0, "Should parse 'done' as empty"


@pytest.mark.unit
def test_p21_success_criteria_rule_validation(progression_loop):
    """
    Success Criteria: Rule validation 100% accuracy
    """
    progression = CharacterProgression(
        character_id="test-id",
        name="Test",
        level=1,
        xp=100,
        xp_to_next_level=1000,
        attributes={"strength": 14},
        skills={},
        available_upgrades=[]
    )
    
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={"strength": 50},
        skill_costs={},
        level_benefits={},
        max_attributes={"strength": 20},
        max_skills={}
    )
    
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    
    # Test valid selection
    validation = progression_loop.validate_selection(upgrades, rules, progression)
    assert validation.valid is True, "Validation should pass for valid selection"
    assert len(validation.errors) == 0, "Should have no errors for valid selection"
    
    # Test invalid XP (add more upgrades than XP allows)
    extra_upgrades = [upgrades[0]] * 3  # 3 upgrades would cost 150 XP
    validation = progression_loop.validate_selection(extra_upgrades, rules, progression)
    assert validation.valid is False, "Validation should fail for insufficient XP"
    assert len(validation.errors) > 0, "Should have errors for insufficient XP"


# --- Postconditions Tests ---

@pytest.mark.unit
async def test_p21_postconditions_progression_applied(
    progression_loop,
    canonkeeper,
    narrator,
    scene,
    user_id
):
    """
    Verify postconditions:
    1. Character stats updated in Neo4j (via CanonKeeper)
    2. XP deducted from character
    3. Progression logged in turns
    4. Narrator describes progression
    """
    scene_id = scene.scene_id
    progression_loop.scenes[scene_id] = scene
    
    character_id = "test-id"
    
    progression = CharacterProgression(
        character_id=character_id,
        name="Test",
        level=1,
        xp=100,
        xp_to_next_level=1000,
        attributes={"strength": 14},
        skills={},
        available_upgrades=[]
    )
    
    rules = ProgressionRules(
        system_id="dnd-5e",
        system_name="D&D 5e",
        core_mechanic="D20",
        level_up_xp=1000,
        attribute_costs={"strength": 50},
        skill_costs={},
        level_benefits={},
        max_attributes={"strength": 20},
        max_skills={}
    )
    
    upgrades = progression_loop.calculate_upgrades(progression, rules)
    selected_upgrades = upgrades[:1]  # Select first upgrade
    
    # Create proposed changes
    proposed_changes = progression_loop.create_proposed_changes(character_id, selected_upgrades)
    
    # CanonKeeper commits (updates Neo4j)
    canon_result = await canonkeeper.evaluate_and_commit(proposed_changes)
    assert canon_result.success is True, "Postcondition 1: CanonKeeper should commit changes"
    assert len(canonkeeper.committed_changes) > 0, "Postcondition 1: Changes should be committed"
    
    # Postcondition 2: XP deducted (tracked in turn metadata)
    xp_spent = sum(u.cost for u in selected_upgrades)
    assert xp_spent > 0, "Postcondition 2: XP should be spent"
    
    # Narrator describes
    description = narrator.describe_progression(selected_upgrades, progression.name)
    assert description is not None, "Postcondition 4: Narrator should describe progression"
    
    # Append turns (Postcondition 3: Progression logged)
    turns = await progression_loop.append_progression_turns(
        scene_id,
        "1",
        description,
        selected_upgrades,
        user_id
    )
    
    assert len(turns) == 2, "Postcondition 3: Should have 2 turns"
    assert turns[0].metadata.get("xp_spent") == xp_spent, "Postcondition 2 & 3: Turn metadata should show XP spent"
    assert turns[1].content == description, "Postcondition 3: Turn should contain narrator description"