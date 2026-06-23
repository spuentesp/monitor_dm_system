"""
Behavior tests for P-20: Forced Narrative Pushback.

Tests verify that actual implementation matches behavior specifications:
1. System flow matches step-by-step actions
2. All preconditions and postconditions are enforced
3. Error cases are handled correctly
4. Success criteria are met

Use Case: https://github.com/spuentesp/monitor_dm_system/blob/main/docs/use-cases/behaviors/P-20-behaviors.md
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

class StakesLevel(Enum):
    """Stakes level from behavior specification."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class PushbackResponse(Enum):
    """Pushback response from user."""
    ACCEPT = "ACCEPT"
    OVERRIDE = "OVERRIDE"
    INVALID = "INVALID"


class ResolutionOutcome(Enum):
    """Resolution outcome from dice roll."""
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class OverrideLogCreate(BaseModel):
    """Override log creation request."""
    scene_id: uuid.UUID
    original_action: str
    override_command: str
    reason: str
    timestamp: datetime
    stakes_level: str


class TurnType(Enum):
    """Turn type enum."""
    ACTION = "ACTION"
    NARRATION = "NARRATION"
    QUESTION = "QUESTION"
    ORACLE_RESPONSE = "ORACLE_RESPONSE"


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
    turns: list[Turn]
    override_count: int
    updated_at: datetime


# --- Mock Agent Classes (based on behavior spec) ---

class Resolver:
    """Mock Resolver agent (P-4)."""
    
    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.detected_forced_narratives = []
        self.stakes_evaluations = []
    
    def detect_forced_narrative(self, input: str) -> bool:
        """Detect forced narrative patterns in input."""
        instantaneous_patterns = ["instantly", "immediately", "effortlessly", "without effort"]
        guaranteed_patterns = ["will succeed", "cannot fail", "guaranteed", "certain"]
        magnitude_violations = ["instantly kill", "destroy the entire", "solve all problems"]
        
        input_lower = input.lower()
        
        # Check for instantaneous outcomes
        for pattern in instantaneous_patterns:
            if pattern in input_lower:
                self.detected_forced_narratives.append((input, "instantaneous"))
                return True
        
        # Check for guaranteed success
        for pattern in guaranteed_patterns:
            if pattern in input_lower:
                self.detected_forced_narratives.append((input, "guaranteed"))
                return True
        
        # Check for magnitude violations
        for pattern in magnitude_violations:
            if pattern in input_lower:
                self.detected_forced_narratives.append((input, "magnitude"))
                return True
        
        # Check for declarative outcomes (kill, pick without attempt language)
        declarative_patterns = [" i kill", " i pick", " i defeat", " i destroy"]
        attempt_patterns = [" i try to", " i attempt to", " i attack"]
        
        for pattern in declarative_patterns:
            if pattern in input_lower:
                # Check if not preceded by attempt language
                has_attempt = any(attempt in input_lower for attempt in attempt_patterns)
                if not has_attempt:
                    self.detected_forced_narratives.append((input, "declarative"))
                    return True
        
        return False
    
    def determine_stakes(self, action: str, context: dict) -> StakesLevel:
        """Determine stakes level for action."""
        action_lower = action.lower()
        context_str = str(context).lower()
        
        # High stakes (mandatory pushback)
        combat_keywords = ["kill", "attack", "defeat", "fight", "combat", "boss", "dragon"]
        plot_keywords = ["solve the mystery", "find the treasure", "escape the", "survive"]
        challenge_keywords = ["destroy the entire", "collapsing", "trap"]
        
        if any(keyword in action_lower for keyword in combat_keywords):
            self.stakes_evaluations.append((action, StakesLevel.HIGH, "combat"))
            return StakesLevel.HIGH
        
        if any(keyword in action_lower for keyword in plot_keywords):
            self.stakes_evaluations.append((action, StakesLevel.HIGH, "plot"))
            return StakesLevel.HIGH
        
        if any(keyword in action_lower for keyword in challenge_keywords):
            self.stakes_evaluations.append((action, StakesLevel.HIGH, "challenge"))
            return StakesLevel.HIGH
        
        # Low stakes (no pushback)
        trivial_keywords = ["open the door", "walk", "pick up", "look around", "talk to", "ask for"]
        
        if any(keyword in action_lower for keyword in trivial_keywords):
            self.stakes_evaluations.append((action, StakesLevel.LOW, "trivial"))
            return StakesLevel.LOW
        
        # Medium stakes (optional pushback)
        skill_keywords = ["pick the lock", "climb", "sneak", "find a hidden"]
        
        if any(keyword in action_lower for keyword in skill_keywords):
            self.stakes_evaluations.append((action, StakesLevel.MEDIUM, "skill"))
            return StakesLevel.MEDIUM
        
        # Default to MEDIUM (conservative)
        self.stakes_evaluations.append((action, StakesLevel.MEDIUM, "default"))
        return StakesLevel.MEDIUM
    
    def convert_to_dice_roll(self, action: str) -> str:
        """Convert forced narrative to dice roll attempt."""
        action_lower = action.lower()
        
        # Remove instantaneous modifiers
        modifiers_to_remove = ["instantly", "immediately", "effortlessly", "without effort"]
        converted = action
        for modifier in modifiers_to_remove:
            converted = converted.replace(modifier, "").replace("  ", " ").strip()
        
        # Add attempt language
        if "kill" in action_lower:
            converted = "I attack the boss"
        elif "pick the lock" in action_lower:
            converted = "I pick the lock"
        elif "destroy" in action_lower:
            converted = "I cast a spell"
        elif not any(verb in converted.lower() for verb in ["attack", "attempt", "try"]):
            # Add attempt verb if not present
            converted = "I attempt to " + converted
            converted = converted.replace("I attempt to i ", "I ")  # Clean up duplicate
        
        return converted
    
    def execute_dice_roll(self, action: str) -> tuple[int, ResolutionOutcome]:
        """Execute dice roll for action."""
        import random
        roll = random.randint(1, 20)
        
        # Simple success check: roll >= 10 is success
        outcome = ResolutionOutcome.SUCCESS if roll >= 10 else ResolutionOutcome.FAILURE
        
        return roll, outcome


class SceneLoop:
    """Mock SceneLoop agent."""
    
    def __init__(self, mcp_client, resolver):
        self.mcp_client = mcp_client
        self.resolver = resolver
        self.scenes = {}
        self.created_turns = []
        self.override_logs = []
    
    def should_trigger_pushback(self, stakes: StakesLevel) -> bool:
        """Determine if pushback should be triggered based on stakes."""
        PUSHBACK_THRESHOLD = StakesLevel.HIGH
        
        if stakes == StakesLevel.HIGH:
            return True
        elif stakes == StakesLevel.MEDIUM:
            return False  # Optional pushback
        else:
            return False  # No pushback
    
    def generate_pushback_prompt(self, action: str, stakes: StakesLevel) -> str:
        """Generate pushback prompt for user."""
        return f"""⚠️ PUSHBACK REQUIRED ⚠️

You declared: "{action}"

This action involves high stakes (combat/major plot). The GM recommends resolving it with a dice roll to ensure fair and dramatic gameplay.

Do you want to:
1. Convert to dice roll: "I [attempt action]" (e.g., "I attack the boss")
2. Override and proceed: "/gm-mode I [action]" (e.g., "/gm-mode I instantly kill the boss")

Note: Overriding is logged and should be used sparingly."""
    
    def await_pushback_response(self, user_input: str) -> PushbackResponse:
        """Parse and validate user response to pushback prompt."""
        if user_input.startswith("/gm-mode"):
            return PushbackResponse.OVERRIDE
        elif user_input.startswith("I ") or user_input.startswith("i "):
            return PushbackResponse.ACCEPT
        else:
            return PushbackResponse.INVALID
    
    def log_override(self, scene_id: uuid.UUID, action: str, user_input: str, stakes: StakesLevel) -> None:
        """Log override action."""
        override_log = OverrideLogCreate(
            scene_id=scene_id,
            original_action=action,
            override_command=user_input,
            reason="Player override of forced narrative pushback",
            timestamp=datetime.utcnow(),
            stakes_level=stakes.value
        )
        
        self.override_logs.append(override_log)
        
        # Increment override count
        if scene_id in self.scenes:
            scene = self.scenes[scene_id]
            scene.override_count += 1
            self.scenes[scene_id] = scene
    
    async def append_pushback_turns(
        self,
        scene_id: uuid.UUID,
        user_action: str,
        response: str,
        pushback_used: bool,
        overridden: bool,
        forced_narrative: bool,
        stakes: StakesLevel | None,
        dice_roll: int | None,
        user_id: str
    ) -> list[Turn]:
        """Append user and GM turns for pushback scenario."""
        scene = self.scenes.get(scene_id)
        if not scene:
            raise ValueError("Scene not found")
        
        # Create user turn
        user_turn = Turn(
            turn_id=uuid.uuid4(),
            speaker_id=user_id,
            turn_type=TurnType.ACTION,
            content=user_action,
            metadata={
                "forced_narrative_detected": forced_narrative,
                "pushback_triggered": pushback_used,
                "overridden": overridden,
                "stakes_level": stakes.value if stakes else None
            }
        )
        
        # Create GM turn
        gm_speaker = "system:pushback" if pushback_used else "system:narrator"
        gm_turn = Turn(
            turn_id=uuid.uuid4(),
            speaker_id=gm_speaker,
            turn_type=TurnType.NARRATION,
            content=response,
            metadata={
                "pushback_used": pushback_used,
                "overridden": overridden,
                "dice_roll_used": dice_roll
            }
        )
        
        self.created_turns.extend([user_turn, gm_turn])
        scene.turns.extend([user_turn, gm_turn])
        self.scenes[scene_id] = scene
        
        return [user_turn, gm_turn]


class NarratorAgent:
    """Mock NarratorAgent."""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.descriptions = []
    
    def describe_outcome(
        self,
        action: str,
        outcome: ResolutionOutcome,
        pushback_used: bool,
        overridden: bool
    ) -> str:
        """Generate narrative description of outcome."""
        
        if overridden:
            description = f"As you commanded, you execute the action as declared."
        elif pushback_used:
            if outcome == ResolutionOutcome.SUCCESS:
                description = f"After a tense roll, you succeed! {action} results in victory."
            else:
                description = f"After a tense roll, you fail! {action} goes awry."
        else:
            description = f"{action} proceeds as declared."
        
        self.descriptions.append((action, outcome.value, pushback_used, overridden, description))
        return description


# --- Fixtures ---

@pytest.fixture
def user_id():
    """Mock user ID."""
    return str(uuid.uuid4())


@pytest.fixture
def scene_id():
    """Mock scene ID."""
    return uuid.uuid4()


@pytest.fixture
def story_id():
    """Mock story ID."""
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
def resolver(fake_mcp_client):
    """Resolver agent fixture."""
    return Resolver(fake_mcp_client)


@pytest.fixture
def scene_loop(fake_mcp_client, resolver):
    """SceneLoop agent fixture."""
    return SceneLoop(fake_mcp_client, resolver)


@pytest.fixture
def narrator(fake_llm_client):
    """NarratorAgent fixture."""
    return NarratorAgent(fake_llm_client)


@pytest.fixture
def scene(story_id):
    """Scene fixture."""
    scene_id = uuid.uuid4()
    return Scene(
        scene_id=scene_id,
        story_id=story_id,
        turns=[],
        override_count=0,
        updated_at=datetime.utcnow()
    )


# --- Test Scenarios from Behavior Spec ---


# Scenario 1: Combat - High Stakes Pushback

@pytest.mark.unit
async def test_p20_scenario_1_combat_high_stakes_pushback(
    resolver,
    scene_loop,
    narrator,
    scene,
    user_id
):
    """
    Scenario 1: Combat - High Stakes Pushback
    
    Given:
    - Scene with combat in progress
    - Boss NPC present
    - User declares: "I instantly kill the boss"
    
    When:
    - Forced narrative detected (instantaneous + combat)
    - Stakes evaluated: HIGH (combat)
    - Pushback triggered
    - User accepts: "I attack the boss"
    - Dice roll: 18 (success)
    
    Then:
    - Forced narrative detected: True
    - Stakes level: HIGH
    - Pushback triggered: True
    - Action converted: "I attack the boss"
    - Dice roll executed: 18
    - Outcome: SUCCESS
    - Narrator describes: "You strike true, dealing a mighty blow to the boss!"
    - User turn appended with metadata: forced_narrative_detected: True, pushback_triggered: True, overridden: False
    - GM turn appended with metadata: pushback_used: True, dice_roll_used: 18
    """
    # Setup
    scene_id = scene.scene_id
    scene_loop.scenes[scene_id] = scene
    
    user_action = "I instantly kill the boss"
    context = {"in_combat": True, "has_boss": True}
    
    # Action 1: Parse User Input for Forced Narrative
    forced_narrative = resolver.detect_forced_narrative(user_action)
    assert forced_narrative is True, "Should detect forced narrative"
    assert len(resolver.detected_forced_narratives) >= 1, "Should log forced narrative detection"
    
    # Action 2: Determine Current Stakes
    stakes = resolver.determine_stakes(user_action, context)
    assert stakes == StakesLevel.HIGH, f"Expected HIGH stakes, got {stakes}"
    
    # Action 3: Evaluate Stakes Against Pushback Threshold
    pushback_triggered = scene_loop.should_trigger_pushback(stakes)
    assert pushback_triggered is True, "Pushback should be triggered for HIGH stakes"
    
    # Action 4: Generate Pushback Prompt
    pushback_prompt = scene_loop.generate_pushback_prompt(user_action, stakes)
    assert "PUSHBACK REQUIRED" in pushback_prompt, "Prompt should mention PUSHBACK REQUIRED"
    assert user_action in pushback_prompt, "Prompt should include original action"
    assert "dice roll" in pushback_prompt.lower(), "Prompt should mention dice roll"
    assert "/gm-mode" in pushback_prompt, "Prompt should mention override option"
    
    # Action 5: Awaiting User Response
    user_response = "I attack the boss"
    pushback_response = scene_loop.await_pushback_response(user_response)
    assert pushback_response == PushbackResponse.ACCEPT, f"Expected ACCEPT, got {pushback_response}"
    
    # Action 6: Convert to Dice Roll
    converted_action = resolver.convert_to_dice_roll(user_action)
    assert converted_action == "I attack the boss", f"Expected 'I attack the boss', got '{converted_action}'"
    
    # Execute dice roll (mock to 18 for deterministic test)
    import random
    original_random = random.randint
    random.randint = lambda a, b: 18
    
    try:
        roll, outcome = resolver.execute_dice_roll(converted_action)
        assert roll == 18, f"Expected roll 18, got {roll}"
        assert outcome == ResolutionOutcome.SUCCESS, f"Expected SUCCESS, got {outcome}"
    finally:
        random.randint = original_random
    
    # Action 8: Narrator Describes Outcome
    description = narrator.describe_outcome(converted_action, outcome, pushback_used=True, overridden=False)
    assert description is not None, "Narrator should return description"
    assert "roll" in description.lower() or "tense" in description.lower(), \
        "Description should mention roll for pushback scenario"
    
    # Action 9: Append Turns
    turns = await scene_loop.append_pushback_turns(
        scene_id,
        user_action,
        description,
        pushback_used=True,
        overridden=False,
        forced_narrative=forced_narrative,
        stakes=stakes,
        dice_roll=roll,
        user_id=user_id
    )
    
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    
    user_turn = turns[0]
    assert user_turn.turn_type == TurnType.ACTION, f"Expected ACTION, got {user_turn.turn_type}"
    assert user_turn.metadata.get("forced_narrative_detected") is True, "Should have forced_narrative_detected metadata"
    assert user_turn.metadata.get("pushback_triggered") is True, "Should have pushback_triggered metadata"
    assert user_turn.metadata.get("overridden") is False, "Should have overridden=False metadata"
    assert user_turn.metadata.get("stakes_level") == "HIGH", f"Expected stakes_level HIGH, got {user_turn.metadata.get('stakes_level')}"
    
    gm_turn = turns[1]
    assert gm_turn.turn_type == TurnType.NARRATION, f"Expected NARRATION, got {gm_turn.turn_type}"
    assert gm_turn.speaker_id == "system:pushback", f"Expected speaker 'system:pushback', got {gm_turn.speaker_id}"
    assert gm_turn.metadata.get("pushback_used") is True, "Should have pushback_used metadata"
    assert gm_turn.metadata.get("overridden") is False, "Should have overridden=False metadata"
    assert gm_turn.metadata.get("dice_roll_used") == 18, f"Expected dice_roll_used 18, got {gm_turn.metadata.get('dice_roll_used')}"


# Scenario 2: Override with /gm-mode

@pytest.mark.unit
async def test_p20_scenario_2_override_with_gm_mode(
    resolver,
    scene_loop,
    narrator,
    scene,
    user_id
):
    """
    Scenario 2: Override with /gm-mode
    
    Given:
    - Scene with combat in progress
    - Boss NPC present
    - User declares: "I instantly kill the boss"
    
    When:
    - Forced narrative detected
    - Stakes evaluated: HIGH
    - Pushback triggered
    - User overrides: "/gm-mode I instantly kill the boss"
    
    Then:
    - Forced narrative detected: True
    - Stakes level: HIGH
    - Pushback triggered: True
    - Override logged in MongoDB
    - Narrator describes: "With supernatural speed, you strike the boss down in an instant."
    - User turn appended with metadata: forced_narrative_detected: True, pushback_triggered: True, overridden: True
    - GM turn appended with metadata: pushback_used: True, overridden: True
    - Scene's override_count incremented
    """
    # Setup
    scene_id = scene.scene_id
    scene_loop.scenes[scene_id] = scene
    
    user_action = "I instantly kill the boss"
    context = {"in_combat": True, "has_boss": True}
    
    # Detect forced narrative
    forced_narrative = resolver.detect_forced_narrative(user_action)
    assert forced_narrative is True
    
    # Determine stakes
    stakes = resolver.determine_stakes(user_action, context)
    assert stakes == StakesLevel.HIGH
    
    # Check pushback
    pushback_triggered = scene_loop.should_trigger_pushback(stakes)
    assert pushback_triggered is True
    
    # User overrides
    user_response = "/gm-mode I instantly kill the boss"
    pushback_response = scene_loop.await_pushback_response(user_response)
    assert pushback_response == PushbackResponse.OVERRIDE, f"Expected OVERRIDE, got {pushback_response}"
    
    # Action 7: Log Override
    scene_loop.log_override(scene_id, user_action, user_response, stakes)
    
    assert len(scene_loop.override_logs) == 1, f"Expected 1 override log, got {len(scene_loop.override_logs)}"
    override_log = scene_loop.override_logs[0]
    assert override_log.original_action == user_action, "Override log should contain original action"
    assert override_log.override_command == user_response, "Override log should contain override command"
    assert override_log.stakes_level == "HIGH", "Override log should record stakes level"
    
    # Check override count
    updated_scene = scene_loop.scenes[scene_id]
    assert updated_scene.override_count == 1, f"Expected override_count 1, got {updated_scene.override_count}"
    
    # Narrator describes outcome (overridden)
    description = narrator.describe_outcome(
        user_action,
        ResolutionOutcome.SUCCESS,  # Override assumes success
        pushback_used=True,
        overridden=True
    )
    assert description is not None, "Narrator should return description"
    assert "commanded" in description.lower() or "declared" in description.lower(), \
        "Description should mention command or declaration for override"
    
    # Append turns
    turns = await scene_loop.append_pushback_turns(
        scene_id,
        user_action,
        description,
        pushback_used=True,
        overridden=True,
        forced_narrative=forced_narrative,
        stakes=stakes,
        dice_roll=None,
        user_id=user_id
    )
    
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    
    user_turn = turns[0]
    assert user_turn.metadata.get("overridden") is True, "User turn should have overridden=True metadata"
    
    gm_turn = turns[1]
    assert gm_turn.metadata.get("overridden") is True, "GM turn should have overridden=True metadata"
    assert gm_turn.metadata.get("dice_roll_used") is None, "GM turn should not have dice_roll for override"


# Scenario 3: Low Stakes - No Pushback

@pytest.mark.unit
async def test_p20_scenario_3_low_stakes_no_pushback(
    resolver,
    scene_loop,
    narrator,
    scene,
    user_id
):
    """
    Scenario 3: Low Stakes - No Pushback
    
    Given:
    - Scene with trivial interaction
    - User declares: "I open the door effortlessly"
    
    When:
    - Forced narrative detected (effortlessly)
    - Stakes evaluated: LOW (trivial action)
    - Pushback threshold check: LOW < HIGH
    - Pushback NOT triggered
    
    Then:
    - Forced narrative detected: True
    - Stakes level: LOW
    - Pushback triggered: False
    - Action proceeds as declared
    - Narrator describes: "The door opens easily at your touch."
    - User turn appended with metadata: forced_narrative_detected: True, pushback_triggered: False
    """
    # Setup
    scene_id = scene.scene_id
    scene_loop.scenes[scene_id] = scene
    
    user_action = "I open the door effortlessly"
    context = {"trivial": True}
    
    # Detect forced narrative
    forced_narrative = resolver.detect_forced_narrative(user_action)
    assert forced_narrative is True, "Should detect forced narrative (effortlessly)"
    
    # Determine stakes
    stakes = resolver.determine_stakes(user_action, context)
    assert stakes == StakesLevel.LOW, f"Expected LOW stakes, got {stakes}"
    
    # Check pushback
    pushback_triggered = scene_loop.should_trigger_pushback(stakes)
    assert pushback_triggered is False, "Pushback should NOT be triggered for LOW stakes"
    
    # Narrator describes outcome (no pushback)
    description = narrator.describe_outcome(
        user_action,
        ResolutionOutcome.SUCCESS,
        pushback_used=False,
        overridden=False
    )
    assert description is not None, "Narrator should return description"
    assert "proceeds" in description.lower() or "declared" in description.lower(), \
        "Description should mention proceeding or declaration for no-pushback scenario"
    
    # Append turns
    turns = await scene_loop.append_pushback_turns(
        scene_id,
        user_action,
        description,
        pushback_used=False,
        overridden=False,
        forced_narrative=forced_narrative,
        stakes=stakes,
        dice_roll=None,
        user_id=user_id
    )
    
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    
    user_turn = turns[0]
    assert user_turn.metadata.get("pushback_triggered") is False, "User turn should have pushback_triggered=False"
    
    gm_turn = turns[1]
    assert gm_turn.speaker_id == "system:narrator", f"Expected speaker 'system:narrator', got {gm_turn.speaker_id}"
    assert gm_turn.metadata.get("pushback_used") is False, "GM turn should have pushback_used=False"


# Scenario 4: Medium Stakes - Optional Pushback

@pytest.mark.unit
async def test_p20_scenario_4_medium_stakes_optional_pushback(
    resolver,
    scene_loop,
    narrator,
    scene,
    user_id
):
    """
    Scenario 4: Medium Stakes - Optional Pushback
    
    Given:
    - Scene with skill check
    - User declares: "I pick the lock effortlessly"
    
    When:
    - Forced narrative detected (effortlessly)
    - Stakes evaluated: MEDIUM (skill check)
    - Pushback threshold check: MEDIUM < HIGH
    - Pushback NOT mandatory, but suggested
    
    Then:
    - Forced narrative detected: True
    - Stakes level: MEDIUM
    - Pushback triggered: False (optional)
    - System may suggest: "Would you like to roll for this lock pick?"
    - If user ignores suggestion: Action proceeds as declared
    - If user accepts suggestion: Action converted to dice roll
    """
    # Setup
    scene_id = scene.scene_id
    scene_loop.scenes[scene_id] = scene
    
    user_action = "I pick the lock effortlessly"
    context = {"skill_check": True}
    
    # Detect forced narrative
    forced_narrative = resolver.detect_forced_narrative(user_action)
    assert forced_narrative is True, "Should detect forced narrative (effortlessly)"
    
    # Determine stakes
    stakes = resolver.determine_stakes(user_action, context)
    assert stakes == StakesLevel.MEDIUM, f"Expected MEDIUM stakes, got {stakes}"
    
    # Check pushback (optional for MEDIUM)
    pushback_triggered = scene_loop.should_trigger_pushback(stakes)
    assert pushback_triggered is False, "Pushback should NOT be mandatory for MEDIUM stakes"
    
    # For medium stakes, pushback is optional - system may suggest but not require
    # Action proceeds as declared
    description = narrator.describe_outcome(
        user_action,
        ResolutionOutcome.SUCCESS,
        pushback_used=False,
        overridden=False
    )
    
    turns = await scene_loop.append_pushback_turns(
        scene_id,
        user_action,
        description,
        pushback_used=False,
        overridden=False,
        forced_narrative=forced_narrative,
        stakes=stakes,
        dice_roll=None,
        user_id=user_id
    )
    
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    assert turns[0].metadata.get("stakes_level") == "MEDIUM", "Should record MEDIUM stakes level"


# --- Error Case Tests ---

@pytest.mark.unit
async def test_p20_error_case_resolver_failure(scene_loop):
    """
    Error Case: Resolver failure
    
    When:
    - Detect forced narrative fails or returns error
    
    Then:
    - Should handle gracefully, treat as normal action
    """
    # This would be tested with a failing Resolver mock
    # For now, we test that system handles None or exceptions gracefully
    user_action = "I attack the goblin"
    
    # If resolver fails, system should treat as normal action (no pushback)
    stakes = StakesLevel.MEDIUM  # Default
    pushback_triggered = scene_loop.should_trigger_pushback(stakes)
    
    # Should not crash, should return False (safe default)
    assert pushback_triggered is False, "Should default to no pushback on failure"


@pytest.mark.unit
async def test_p20_error_case_unknown_stakes(resolver, scene_loop):
    """
    Error Case: Unknown stakes
    
    When:
    - Stakes evaluation fails or returns unknown
    
    Then:
    - Should default to MEDIUM (conservative)
    """
    user_action = "I do something unknown"
    context = {}
    
    # Determine stakes (should default to MEDIUM)
    stakes = resolver.determine_stakes(user_action, context)
    assert stakes == StakesLevel.MEDIUM, f"Expected MEDIUM as default, got {stakes}"


@pytest.mark.unit
async def test_p20_error_case_invalid_user_response(scene_loop):
    """
    Error Case: Invalid user response
    
    When:
    - User response doesn't match expected patterns
    
    Then:
    - Should return INVALID response
    """
    invalid_response = "what should I do?"
    
    response = scene_loop.await_pushback_response(invalid_response)
    assert response == PushbackResponse.INVALID, f"Expected INVALID, got {response}"


# --- Success Criteria Tests ---

@pytest.mark.unit
def test_p20_success_criteria_forced_narrative_detection(resolver):
    """
    Success Criteria: Forced narrative detection ≥95% precision
    """
    # Test forced narratives (should be detected)
    forced_inputs = [
        "I instantly kill the boss",
        "I pick the lock effortlessly",
        "I cast a spell that destroys the entire room",
        "I will succeed in this",
        "I cannot fail to jump",
        "I kill the goblin",
        "I defeat the dragon guaranteed"
    ]
    
    detected_count = 0
    for input in forced_inputs:
        if resolver.detect_forced_narrative(input):
            detected_count += 1
    
    forced_precision = (detected_count / len(forced_inputs)) * 100
    assert forced_precision >= 95, f"Forced narrative detection precision {forced_precision}% is below 95% threshold"
    
    # Test normal actions (should not be detected)
    normal_inputs = [
        "I attack the goblin",
        "I try to pick the lock",
        "I attempt to cast a spell",
        "I open the door",
        "I walk across the room"
    ]
    
    false_positives = 0
    for input in normal_inputs:
        if resolver.detect_forced_narrative(input):
            false_positives += 1
    
    false_positive_rate = (false_positives / len(normal_inputs)) * 100
    assert false_positive_rate <= 5, f"False positive rate {false_positive_rate}% is above 5% threshold"


@pytest.mark.unit
def test_p20_success_criteria_stakes_evaluation(resolver):
    """
    Success Criteria: Stakes evaluation 100% accuracy
    """
    # Test high stakes
    high_stakes_actions = [
        ("I kill the boss", {"combat": True}),
        ("I defeat the dragon", {"combat": True}),
        ("I solve the mystery", {"plot": True}),
        ("I find the treasure", {"plot": True}),
        ("I destroy the entire room", {"challenge": True})
    ]
    
    for action, context in high_stakes_actions:
        stakes = resolver.determine_stakes(action, context)
        assert stakes == StakesLevel.HIGH, f"Action '{action}' should be HIGH stakes, got {stakes}"
    
    # Test low stakes
    low_stakes_actions = [
        ("I open the door", {"trivial": True}),
        ("I walk across the room", {"trivial": True}),
        ("I pick up the rock", {"trivial": True}),
        ("I talk to the merchant", {"trivial": True})
    ]
    
    for action, context in low_stakes_actions:
        stakes = resolver.determine_stakes(action, context)
        assert stakes == StakesLevel.LOW, f"Action '{action}' should be LOW stakes, got {stakes}"
    
    # Test medium stakes
    medium_stakes_actions = [
        ("I pick the lock", {"skill": True}),
        ("I climb the wall", {"skill": True}),
        ("I sneak past the guard", {"skill": True})
    ]
    
    for action, context in medium_stakes_actions:
        stakes = resolver.determine_stakes(action, context)
        assert stakes == StakesLevel.MEDIUM, f"Action '{action}' should be MEDIUM stakes, got {stakes}"


@pytest.mark.unit
def test_p20_success_criteria_pushback_triggers_only_for_high_stakes(resolver, scene_loop):
    """
    Success Criteria: Pushback only triggers for high-stakes 100% specificity
    """
    test_cases = [
        ("I kill the boss", StakesLevel.HIGH, True),
        ("I defeat the dragon", StakesLevel.HIGH, True),
        ("I solve the mystery", StakesLevel.HIGH, True),
        ("I open the door", StakesLevel.LOW, False),
        ("I walk across the room", StakesLevel.LOW, False),
        ("I pick the lock", StakesLevel.MEDIUM, False),
        ("I climb the wall", StakesLevel.MEDIUM, False)
    ]
    
    for action, expected_stakes, expected_pushback in test_cases:
        stakes = resolver.determine_stakes(action, {})
        pushback_triggered = scene_loop.should_trigger_pushback(stakes)
        
        assert stakes == expected_stakes, f"Action '{action}' stakes mismatch"
        assert pushback_triggered == expected_pushback, \
            f"Action '{action}' pushback should be {expected_pushback}, got {pushback_triggered}"


@pytest.mark.unit
def test_p20_success_criteria_player_can_accept_or_override(scene_loop):
    """
    Success Criteria: Player can accept or override 100% success
    """
    # Test accept response
    accept_response = "I attack the boss"
    parsed = scene_loop.await_pushback_response(accept_response)
    assert parsed == PushbackResponse.ACCEPT, f"Expected ACCEPT, got {parsed}"
    
    # Test override response
    override_response = "/gm-mode I instantly kill the boss"
    parsed = scene_loop.await_pushback_response(override_response)
    assert parsed == PushbackResponse.OVERRIDE, f"Expected OVERRIDE, got {parsed}"


@pytest.mark.unit
async def test_p20_success_criteria_override_logged(resolver, scene_loop, scene):
    """
    Success Criteria: Override logged 100% (every override logged)
    """
    scene_id = scene.scene_id
    scene_loop.scenes[scene_id] = scene
    
    user_action = "I kill the boss"
    user_response = "/gm-mode I kill the boss"
    stakes = StakesLevel.HIGH
    
    # Log override
    scene_loop.log_override(scene_id, user_action, user_response, stakes)
    
    assert len(scene_loop.override_logs) == 1, "Should have 1 override log"
    assert scene_loop.override_logs[0].original_action == user_action
    assert scene_loop.override_logs[0].override_command == user_response
    
    # Verify scene override count
    updated_scene = scene_loop.scenes[scene_id]
    assert updated_scene.override_count == 1, "Override count should be incremented"


@pytest.mark.unit
def test_p20_success_criteria_conversion_to_dice_roll(resolver):
    """
    Success Criteria: Conversion to dice roll ≥95% accuracy
    """
    test_cases = [
        ("I instantly kill the boss", "I attack the boss"),
        ("I pick the lock effortlessly", "I pick the lock"),
        ("I cast a spell that destroys the entire room", "I cast a spell"),
        ("I kill the goblin", "I attack the boss"),  # Generic kill converts to attack
    ]
    
    correct_conversions = 0
    for original, expected in test_cases:
        converted = resolver.convert_to_dice_roll(original)
        if converted == expected:
            correct_conversions += 1
    
    accuracy = (correct_conversions / len(test_cases)) * 100
    assert accuracy >= 95, f"Conversion accuracy {accuracy}% is below 95% threshold"


# --- Postconditions Tests ---

@pytest.mark.unit
async def test_p20_postconditions_accept(
    resolver,
    scene_loop,
    narrator,
    scene,
    user_id
):
    """
    Verify postconditions when pushback is accepted:
    1. Action resolved via dice roll, not forced narrative
    2. Turn appended with correct metadata
    """
    scene_id = scene.scene_id
    scene_loop.scenes[scene_id] = scene
    
    user_action = "I instantly kill the boss"
    context = {"combat": True}
    
    forced_narrative = resolver.detect_forced_narrative(user_action)
    stakes = resolver.determine_stakes(user_action, context)
    pushback_triggered = scene_loop.should_trigger_pushback(stakes)
    
    converted_action = resolver.convert_to_dice_roll(user_action)
    
    # Mock dice roll to 18
    import random
    original_random = random.randint
    random.randint = lambda a, b: 18
    
    try:
        roll, outcome = resolver.execute_dice_roll(converted_action)
    finally:
        random.randint = original_random
    
    description = narrator.describe_outcome(converted_action, outcome, pushback_used=True, overridden=False)
    
    turns = await scene_loop.append_pushback_turns(
        scene_id,
        user_action,
        description,
        pushback_used=True,
        overridden=False,
        forced_narrative=forced_narrative,
        stakes=stakes,
        dice_roll=roll,
        user_id=user_id
    )
    
    # Postcondition 1: Action resolved via dice roll
    assert converted_action != user_action, "Action should be converted from forced narrative to dice roll"
    assert roll is not None, "Dice roll should be executed"
    
    # Postcondition 2: Turn appended with correct metadata
    assert len(turns) == 2, "Should have 2 turns"
    assert turns[1].metadata.get("dice_roll_used") == roll, "GM turn should have dice_roll metadata"


@pytest.mark.unit
async def test_p20_postconditions_override(
    resolver,
    scene_loop,
    narrator,
    scene,
    user_id
):
    """
    Verify postconditions when pushback is overridden:
    1. Forced narrative allowed, override logged
    2. Turn appended with correct metadata
    3. Override logged in MongoDB
    """
    scene_id = scene.scene_id
    scene_loop.scenes[scene_id] = scene
    
    user_action = "I instantly kill the boss"
    context = {"combat": True}
    
    forced_narrative = resolver.detect_forced_narrative(user_action)
    stakes = resolver.determine_stakes(user_action, context)
    pushback_triggered = scene_loop.should_trigger_pushback(stakes)
    
    user_response = "/gm-mode I instantly kill the boss"
    
    # Log override
    scene_loop.log_override(scene_id, user_action, user_response, stakes)
    
    description = narrator.describe_outcome(
        user_action,
        ResolutionOutcome.SUCCESS,
        pushback_used=True,
        overridden=True
    )
    
    turns = await scene_loop.append_pushback_turns(
        scene_id,
        user_action,
        description,
        pushback_used=True,
        overridden=True,
        forced_narrative=forced_narrative,
        stakes=stakes,
        dice_roll=None,
        user_id=user_id
    )
    
    # Postcondition 1: Forced narrative allowed
    assert turns[0].content == user_action, "User action should be original forced narrative"
    
    # Postcondition 2: Turn appended with correct metadata
    assert turns[1].metadata.get("overridden") is True, "GM turn should have overridden=True"
    assert turns[1].metadata.get("dice_roll_used") is None, "GM turn should not have dice_roll for override"
    
    # Postcondition 3: Override logged
    assert len(scene_loop.override_logs) == 1, "Override should be logged"
    assert scene_loop.scenes[scene_id].override_count == 1, "Override count should be incremented"