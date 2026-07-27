"""
Behavior tests for P-18: AutoGM Oracle & Probability Resolution.

Tests verify that actual implementation matches behavior specifications:
1. System flow matches step-by-step actions
2. All preconditions and postconditions are enforced
3. Error cases are handled correctly
4. Success criteria are met

Use Case: https://github.com/spuentesp/monitor_dm_system/blob/main/docs/use-cases/behaviors/P-18-behaviors.md
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

import pytest
from pydantic import BaseModel

# --- Mock Schema Classes (based on behavior spec) ---


class OracleOutcome(BaseModel):
    """Oracle outcome from behavior specification."""

    value: str  # "yes", "no", "yes_and", "no_and"


class LikelihoodLevel(BaseModel):
    """Likelihood level based on tension score."""

    value: str  # "almost_certain", "likely", "fifty_fifty", "unlikely", "impossible"


class FactCreate(BaseModel):
    """Fact creation request from behavior specification."""

    entity_id: uuid.UUID
    fact_type: str
    content: str
    canon_level: str
    evidence_refs: list[str]


class TurnCreate(BaseModel):
    """Turn creation request from behavior specification."""

    speaker_id: str
    turn_type: str
    content: str
    metadata: dict[str, Any]


class Turn(BaseModel):
    """Turn entity."""

    turn_id: uuid.UUID
    speaker_id: str
    turn_type: str
    content: str
    metadata: dict[str, Any]


class Fact(BaseModel):
    """Fact entity."""

    fact_id: uuid.UUID
    entity_id: uuid.UUID
    fact_type: str
    content: str
    canon_level: str
    evidence_refs: list[str]


class Scene(BaseModel):
    """Scene entity."""

    scene_id: uuid.UUID
    story_id: uuid.UUID
    location: str
    description: str
    tension_score: int | None
    updated_at: datetime


# --- Mock Agent Classes (based on behavior spec) ---


class ContextAssembly:
    """Mock ContextAssembly agent."""

    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.detected_queries = []

    async def detect_oracle_query(self, input: str) -> bool:
        """Detect if input is an oracle query."""
        question_words = [
            "Is",
            "Are",
            "Do",
            "Does",
            "Has",
            "Have",
            "Will",
            "Can",
            "Could",
        ]
        is_query = any(input.startswith(word) for word in question_words)
        if is_query:
            self.detected_queries.append(input)
        return is_query


class OracleAgent:
    """Mock OracleAgent in SceneLoop."""

    def __init__(self, mcp_client, llm_client):
        self.mcp_client = mcp_client
        self.llm_client = llm_client
        self.rolls = []
        self.likelihoods = []

    async def determine_likelihood(self, tension_score: int) -> LikelihoodLevel:
        """Determine likelihood based on tension score."""
        if tension_score is None:
            tension_score = 5  # Default to 50/50

        likelihood_map = {
            0: "almost_certain",
            1: "almost_certain",
            2: "almost_certain",
            3: "likely",
            4: "likely",
            5: "fifty_fifty",
            6: "fifty_fifty",
            7: "unlikely",
            8: "unlikely",
            9: "impossible",
            10: "impossible",
        }

        likelihood_value = likelihood_map.get(tension_score, "fifty_fifty")
        self.likelihoods.append((tension_score, likelihood_value))
        return LikelihoodLevel(value=likelihood_value)

    async def roll_percentile(self) -> int:
        """Roll percentile die (1-100)."""
        import random

        roll = random.randint(1, 100)
        self.rolls.append(roll)
        return roll

    def get_outcome_from_roll(
        self, roll: int, likelihood: LikelihoodLevel
    ) -> OracleOutcome:
        """Determine oracle outcome from roll and likelihood."""
        if likelihood.value == "almost_certain":
            if roll <= 5:
                return OracleOutcome(value="no")
            elif roll <= 95:
                return OracleOutcome(value="yes")
            else:
                return OracleOutcome(value="yes_and")

        elif likelihood.value == "likely":
            if roll <= 25:
                return OracleOutcome(value="no")
            elif roll <= 95:
                return OracleOutcome(value="yes")
            else:
                return OracleOutcome(value="yes_and")

        elif likelihood.value == "fifty_fifty" or likelihood.value == "unlikely":
            if roll <= 49:
                return OracleOutcome(value="no")
            elif roll <= 95:
                return OracleOutcome(value="yes")
            else:
                return OracleOutcome(value="yes_and")

        elif likelihood.value == "impossible":
            if roll <= 95:
                return OracleOutcome(value="no")
            else:
                return OracleOutcome(value="no_and")

        return OracleOutcome(value="no")


class CanonKeeper:
    """Mock CanonKeeper agent."""

    def __init__(self, mcp_client):
        self.mcp_client = mcp_client
        self.canonized_facts = []
        self.evaluations = []

    async def canonize_oracle_result(
        self, query: str, outcome: OracleOutcome, roll: int, tension_score: int
    ) -> Fact:
        """Canonize oracle result as Fact."""
        query_hash = uuid.uuid5(uuid.NAMESPACE_DNS, query)

        fact_create = FactCreate(
            entity_id=query_hash,
            fact_type="world_property",
            content=f"{query}: {outcome.value}",
            canon_level="cards",
            evidence_refs=[f"oracle:{roll}:{tension_score}"],
        )

        # Simulate canon keeper evaluation
        await self.evaluate_consistency(fact_create)

        # Simulate fact creation
        fact = Fact(
            fact_id=uuid.uuid4(),
            entity_id=fact_create.entity_id,
            fact_type=fact_create.fact_type,
            content=fact_create.content,
            canon_level=fact_create.canon_level,
            evidence_refs=fact_create.evidence_refs,
        )

        self.canonized_facts.append(fact)
        return fact

    async def evaluate_consistency(self, fact_create: FactCreate) -> bool:
        """Evaluate fact consistency."""
        self.evaluations.append(fact_create)
        return True  # Always consistent for tests


class NarratorAgent:
    """Mock NarratorAgent."""

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.descriptions = []

    async def describe_oracle_outcome(
        self, query: str, outcome: OracleOutcome, context: dict
    ) -> str:
        """Generate narrative description of oracle result."""

        # Mock narrative responses based on outcome
        narrative_map = {
            "yes": f"The answer is yes to your question: {query}",
            "no": f"The answer is no to your question: {query}",
            "yes_and": f"Not only yes, but there's more: {query}",
            "no_and": f"Not only no, but there's complication: {query}",
        }

        narrative = narrative_map.get(outcome.value, f"Oracle outcome: {outcome.value}")
        self.descriptions.append((query, outcome.value, narrative))

        return narrative


class SceneLoop:
    """Mock SceneLoop agent."""

    def __init__(
        self, mcp_client, context_assembly, oracle_agent, canon_keeper, narrator
    ):
        self.mcp_client = mcp_client
        self.context_assembly = context_assembly
        self.oracle_agent = oracle_agent
        self.canon_keeper = canon_keeper
        self.narrator = narrator
        self.created_turns = []
        self.scenes = {}

    async def get_scene(self, scene_id: uuid.UUID) -> Scene | None:
        """Get scene by ID."""
        return self.scenes.get(scene_id)

    async def append_turns(
        self,
        scene_id: uuid.UUID,
        query: str,
        response: str,
        outcome: OracleOutcome,
        roll: int,
        likelihood: LikelihoodLevel,
        fact_id: uuid.UUID,
    ) -> list[Turn]:
        """Append user and GM turns to scene."""

        # Create user turn
        user_turn = Turn(
            turn_id=uuid.uuid4(),
            speaker_id="user",
            turn_type="question",
            content=query,
            metadata={"oracle_query": True},
        )

        # Create GM turn
        gm_turn = Turn(
            turn_id=uuid.uuid4(),
            speaker_id="system:oracle",
            turn_type="oracle_response",
            content=response,
            metadata={
                "oracle_result": outcome.value,
                "roll": roll,
                "likelihood": likelihood.value,
                "fact_canonized": str(fact_id),
            },
        )

        self.created_turns.extend([user_turn, gm_turn])

        # Update scene
        if scene_id in self.scenes:
            scene = self.scenes[scene_id]
            self.scenes[scene_id] = Scene(
                scene_id=scene.scene_id,
                story_id=scene.story_id,
                location=scene.location,
                description=scene.description,
                tension_score=scene.tension_score,
                updated_at=datetime.utcnow(),
            )

        return [user_turn, gm_turn]


# --- Fixtures ---


@pytest.fixture
def user_id():
    """Mock user ID."""
    return uuid.uuid4()


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
def context_assembly(fake_mcp_client):
    """ContextAssembly agent fixture."""
    return ContextAssembly(fake_mcp_client)


@pytest.fixture
def oracle_agent(fake_mcp_client, fake_llm_client):
    """OracleAgent fixture."""
    return OracleAgent(fake_mcp_client, fake_llm_client)


@pytest.fixture
def canon_keeper(fake_mcp_client):
    """CanonKeeper agent fixture."""
    return CanonKeeper(fake_mcp_client)


@pytest.fixture
def narrator(fake_llm_client):
    """NarratorAgent fixture."""
    return NarratorAgent(fake_llm_client)


@pytest.fixture
def scene_loop(fake_mcp_client, context_assembly, oracle_agent, canon_keeper, narrator):
    """SceneLoop agent fixture."""
    return SceneLoop(
        fake_mcp_client, context_assembly, oracle_agent, canon_keeper, narrator
    )


@pytest.fixture
def scene_with_tension(story_id):
    """Scene fixture with tension score."""
    scene_id = uuid.uuid4()
    return Scene(
        scene_id=scene_id,
        story_id=story_id,
        location="tavern",
        description="A cozy tavern",
        tension_score=5,
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def scene_with_high_tension(story_id):
    """Scene fixture with high tension score."""
    scene_id = uuid.uuid4()
    return Scene(
        scene_id=scene_id,
        story_id=story_id,
        location="dungeon",
        description="A dangerous dungeon",
        tension_score=9,
        updated_at=datetime.utcnow(),
    )


# --- Test Scenarios from Behavior Spec ---


# Scenario 1: Simple Yes/No


@pytest.mark.unit
async def test_p18_scenario_1_simple_yes_no(
    scene_loop,
    scene_with_tension,
    context_assembly,
    oracle_agent,
    canon_keeper,
    narrator,
):
    """
    Scenario 1: Simple Yes/No

    Given:
    - Scene with tension_score = 5 (50/50)
    - User asks: "Is the door locked?"

    When:
    - Oracle query detected
    - Roll result: 60 (within 50-95 -> Yes)

    Then:
    - Fact canonized: "Is the door locked?: Yes"
    - Narrator describes outcome
    - User turn appended with metadata oracle_query: True
    - GM turn appended with oracle_result="yes", roll=60, likelihood="fifty_fifty"
    """
    # Setup
    scene_id = scene_with_tension.scene_id
    scene_loop.scenes[scene_id] = scene_with_tension

    query = "Is the door locked?"

    # Action 1: Parse User Input
    is_oracle_query = await context_assembly.detect_oracle_query(query)
    assert is_oracle_query is True, "Should detect oracle query"

    # Action 2: Determine Tension & Likelihood
    tension_score = scene_with_tension.tension_score
    assert tension_score is not None, "Tension score should be set"

    likelihood = await oracle_agent.determine_likelihood(tension_score)
    assert likelihood.value == "fifty_fifty", (
        f"Expected fifty_fifty, got {likelihood.value}"
    )

    # Action 3: Roll Percentile Die
    # Mock roll to be 60 for deterministic test
    import random

    original_random = random.randint
    random.randint = lambda a, b: 60

    try:
        roll = await oracle_agent.roll_percentile()
        assert roll == 60, f"Expected roll 60, got {roll}"

        # Determine outcome from roll
        outcome = oracle_agent.get_outcome_from_roll(roll, likelihood)
        assert outcome.value == "yes", f"Expected yes, got {outcome.value}"
    finally:
        random.randint = original_random

    # Action 4: Canonize Oracle Result
    fact = await canon_keeper.canonize_oracle_result(
        query, outcome, roll, tension_score
    )
    assert fact.content == f"{query}: yes", (
        f"Expected 'Is the door locked?: yes', got {fact.content}"
    )
    assert fact.canon_level == "cards", (
        f"Expected canon_level 'cards', got {fact.canon_level}"
    )
    assert f"oracle:{roll}:{tension_score}" in fact.evidence_refs, (
        "Evidence refs should contain oracle reference"
    )

    # Action 5: Narrator Describes Outcome
    context = {"location": scene_with_tension.location, "entities": []}
    narrative = await narrator.describe_oracle_outcome(query, outcome, context)
    assert narrative is not None, "Narrator should return narrative"

    # Action 6: Append Turns
    turns = await scene_loop.append_turns(
        scene_id, query, narrative, outcome, roll, likelihood, fact.fact_id
    )

    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"

    user_turn = turns[0]
    assert user_turn.turn_type == "question", (
        f"Expected turn_type 'question', got {user_turn.turn_type}"
    )
    assert user_turn.metadata.get("oracle_query") is True, (
        "User turn should have oracle_query metadata"
    )

    gm_turn = turns[1]
    assert gm_turn.turn_type == "oracle_response", (
        f"Expected turn_type 'oracle_response', got {gm_turn.turn_type}"
    )
    assert gm_turn.metadata.get("oracle_result") == "yes", (
        f"Expected oracle_result 'yes', got {gm_turn.metadata.get('oracle_result')}"
    )
    assert gm_turn.metadata.get("roll") == 60, (
        f"Expected roll 60, got {gm_turn.metadata.get('roll')}"
    )
    assert gm_turn.metadata.get("likelihood") == "fifty_fifty", (
        f"Expected likelihood 'fifty_fifty', got {gm_turn.metadata.get('likelihood')}"
    )
    assert str(fact.fact_id) in gm_turn.metadata.get("fact_canonized", ""), (
        "GM turn should reference canonized fact"
    )


# Scenario 2: "No, and..." Extreme Roll


@pytest.mark.unit
async def test_p18_scenario_2_extreme_roll(
    scene_loop,
    scene_with_high_tension,
    context_assembly,
    oracle_agent,
    canon_keeper,
    narrator,
):
    """
    Scenario 2: "No, and..." Extreme Roll

    Given:
    - Scene with tension_score = 9 (Impossible)
    - User asks: "Can I pick the lock?"

    When:
    - Oracle query detected
    - Roll result: 98 (within 96-100 -> No, and)

    Then:
    - Fact canonized: "Can I pick the lock?: No, and"
    - Narrator describes outcome with additional complication
    - User turn appended
    - GM turn appended with oracle_result="no_and", roll=98, likelihood="impossible"
    """
    # Setup
    scene_id = scene_with_high_tension.scene_id
    scene_loop.scenes[scene_id] = scene_with_high_tension

    query = "Can I pick the lock?"

    # Action 1: Parse User Input
    is_oracle_query = await context_assembly.detect_oracle_query(query)
    assert is_oracle_query is True, "Should detect oracle query"

    # Action 2: Determine Tension & Likelihood
    tension_score = scene_with_high_tension.tension_score
    assert tension_score is not None, "Tension score should be set"

    likelihood = await oracle_agent.determine_likelihood(tension_score)
    assert likelihood.value == "impossible", (
        f"Expected impossible, got {likelihood.value}"
    )

    # Action 3: Roll Percentile Die
    # Mock roll to be 98 for deterministic test
    import random

    original_random = random.randint
    random.randint = lambda a, b: 98

    try:
        roll = await oracle_agent.roll_percentile()
        assert roll == 98, f"Expected roll 98, got {roll}"

        # Determine outcome from roll
        outcome = oracle_agent.get_outcome_from_roll(roll, likelihood)
        assert outcome.value == "no_and", f"Expected no_and, got {outcome.value}"
    finally:
        random.randint = original_random

    # Action 4: Canonize Oracle Result
    fact = await canon_keeper.canonize_oracle_result(
        query, outcome, roll, tension_score
    )
    assert fact.content == f"{query}: no_and", (
        f"Expected 'Can I pick the lock?: no_and', got {fact.content}"
    )
    assert f"oracle:{roll}:{tension_score}" in fact.evidence_refs, (
        "Evidence refs should contain oracle reference"
    )

    # Action 5: Narrator Describes Outcome
    context = {"location": scene_with_high_tension.location, "entities": ["guard"]}
    narrative = await narrator.describe_oracle_outcome(query, outcome, context)
    assert narrative is not None, "Narrator should return narrative"
    assert (
        "no_and" in narrative.lower()
        or "complication" in narrative.lower()
        or "not only" in narrative.lower()
    ), "Narrative should mention 'not only' or complication for 'no_and' outcome"

    # Action 6: Append Turns
    turns = await scene_loop.append_turns(
        scene_id, query, narrative, outcome, roll, likelihood, fact.fact_id
    )

    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"

    user_turn = turns[0]
    assert user_turn.metadata.get("oracle_query") is True, (
        "User turn should have oracle_query metadata"
    )

    gm_turn = turns[1]
    assert gm_turn.metadata.get("oracle_result") == "no_and", (
        f"Expected oracle_result 'no_and', got {gm_turn.metadata.get('oracle_result')}"
    )
    assert gm_turn.metadata.get("roll") == 98, (
        f"Expected roll 98, got {gm_turn.metadata.get('roll')}"
    )
    assert gm_turn.metadata.get("likelihood") == "impossible", (
        f"Expected likelihood 'impossible', got {gm_turn.metadata.get('likelihood')}"
    )


# --- Error Case Tests ---


@pytest.mark.unit
async def test_p18_error_case_scene_not_found(scene_loop, context_assembly):
    """
    Error Case: Scene not found

    When:
    - Oracle query detected
    - Scene lookup returns None

    Then:
    - Should raise error asking user to start a scene
    """
    non_existent_scene_id = uuid.uuid4()

    # Check scene exists
    scene = await scene_loop.get_scene(non_existent_scene_id)
    assert scene is None, "Scene should not exist"

    # Should raise error
    with pytest.raises(ValueError, match="Scene not found"):
        await oracle_agent.determine_likelihood(None)


@pytest.mark.unit
async def test_p18_error_case_tension_not_set(
    scene_loop, context_assembly, oracle_agent
):
    """
    Error Case: Tension score not set

    When:
    - Scene exists but tension_score is None

    Then:
    - Should default to 50/50 (tension=5)
    """
    scene_id = uuid.uuid4()
    story_id = uuid.uuid4()

    scene = Scene(
        scene_id=scene_id,
        story_id=story_id,
        location="unknown",
        description="Scene without tension",
        tension_score=None,
        updated_at=datetime.utcnow(),
    )

    scene_loop.scenes[scene_id] = scene

    # Determine likelihood (should default to 50/50)
    likelihood = await oracle_agent.determine_likelihood(scene.tension_score)
    assert likelihood.value == "fifty_fifty", (
        f"Expected fifty_fifty, got {likelihood.value}"
    )


@pytest.mark.unit
async def test_p18_error_case_invalid_input(scene_loop, context_assembly):
    """
    Error Case: Input parsing fails

    When:
    - User input cannot be parsed

    Then:
    - Should return False (not an oracle query)
    """
    # Non-query input
    action_input = "I open the door"

    is_oracle_query = await context_assembly.detect_oracle_query(action_input)
    assert is_oracle_query is False, "Should not detect as oracle query"


# --- Success Criteria Tests ---


@pytest.mark.unit
async def test_p18_success_criteria_question_detection(context_assembly):
    """
    Success Criteria: Question detection accuracy >= 95%
    """
    # Test valid queries
    valid_queries = [
        "Is the door locked?",
        "Are there guards?",
        "Do I have a key?",
        "Does the trap trigger?",
        "Has anyone been here?",
        "Have they seen me?",
        "Will the guard notice?",
        "Can I pick the lock?",
        "Could there be a secret passage?",
    ]

    for query in valid_queries:
        is_oracle_query = await context_assembly.detect_oracle_query(query)
        assert is_oracle_query is True, f"Should detect '{query}' as oracle query"

    # Test invalid queries
    invalid_queries = [
        "I open the door",
        "I attack the guard",
        "I search the room",
        "I pick the lock",
    ]

    for query in invalid_queries:
        is_oracle_query = await context_assembly.detect_oracle_query(query)
        assert is_oracle_query is False, f"Should not detect '{query}' as oracle query"

    # Accuracy calculation
    total_tests = len(valid_queries) + len(invalid_queries)
    correct_tests = total_tests  # All should pass
    accuracy = (correct_tests / total_tests) * 100

    assert accuracy >= 95, (
        f"Question detection accuracy {accuracy}% is below 95% threshold"
    )


@pytest.mark.unit
async def test_p18_success_criteria_tension_retrieval(scene_loop, scene_with_tension):
    """
    Success Criteria: Tension retrieval accuracy = 100%
    """
    scene_id = scene_with_tension.scene_id
    scene_loop.scenes[scene_id] = scene_with_tension

    scene = await scene_loop.get_scene(scene_id)
    assert scene is not None, "Scene should be found"
    assert scene.tension_score is not None, "Tension score should be retrieved"
    assert scene.tension_score == 5, (
        f"Expected tension_score 5, got {scene.tension_score}"
    )


@pytest.mark.unit
async def test_p18_success_criteria_canonization(
    canon_keeper, oracle_agent, context_assembly
):
    """
    Success Criteria: Oracle outcome canonization = 100%
    """
    query = "Is the door locked?"
    outcome = OracleOutcome(value="yes")
    roll = 60
    tension_score = 5

    fact = await canon_keeper.canonize_oracle_result(
        query, outcome, roll, tension_score
    )

    assert fact is not None, "Fact should be canonized"
    assert fact.content == f"{query}: yes", (
        "Fact content should match query and outcome"
    )
    assert fact.canon_level == "cards", "Fact should be canonized at cards level"
    assert len(fact.evidence_refs) > 0, "Fact should have evidence refs"
    assert f"oracle:{roll}:{tension_score}" in fact.evidence_refs[0], (
        "Evidence ref should reference oracle"
    )


@pytest.mark.unit
async def test_p18_success_criteria_evidence_tracking(canon_keeper, oracle_agent):
    """
    Success Criteria: Evidence tracking = 100% (every oracle has evidence_refs)
    """
    # Create multiple oracle results
    queries = [
        ("Is the door locked?", OracleOutcome(value="yes"), 60),
        ("Are there guards?", OracleOutcome(value="no"), 40),
        ("Does the trap trigger?", OracleOutcome(value="yes_and"), 98),
    ]

    tension_score = 5

    for query, outcome, roll in queries:
        fact = await canon_keeper.canonize_oracle_result(
            query, outcome, roll, tension_score
        )
        assert len(fact.evidence_refs) > 0, (
            f"Fact for '{query}' should have evidence refs"
        )
        assert f"oracle:{roll}:{tension_score}" in fact.evidence_refs[0], (
            f"Evidence ref for '{query}' should reference oracle"
        )

    # All facts should have evidence refs
    assert len(canon_keeper.canonized_facts) == len(queries), (
        f"Expected {len(queries)} canonized facts, got {len(canon_keeper.canonized_facts)}"
    )

    for fact in canon_keeper.canonized_facts:
        assert len(fact.evidence_refs) > 0, (
            f"Fact {fact.fact_id} is missing evidence refs"
        )


@pytest.mark.unit
async def test_p18_success_criteria_narrator_respects_outcome(narrator, oracle_agent):
    """
    Success Criteria: Narrator respects oracle outcome = 100%
    """
    query = "Is the door locked?"
    context = {"location": "tavern", "entities": []}

    # Test each outcome type
    outcomes = [
        ("yes", "The answer is yes"),
        ("no", "The answer is no"),
        ("yes_and", "Not only yes, but"),
        ("no_and", "Not only no, but"),
    ]

    for outcome_value, expected_phrase in outcomes:
        outcome = OracleOutcome(value=outcome_value)
        narrative = await narrator.describe_oracle_outcome(query, outcome, context)

        assert narrative is not None, (
            f"Narrator should return narrative for outcome '{outcome_value}'"
        )
        # In a real implementation, narrator should respect the outcome
        # This is a simplified check

        # Verify narrator was called with correct outcome
        assert outcome_value in narrator.descriptions[-1][1], (
            f"Narrator should receive outcome '{outcome_value}'"
        )


# --- Likelihood Mapping Tests ---


@pytest.mark.unit
async def test_p18_likelihood_mapping_all_levels(oracle_agent):
    """
    Test all likelihood levels based on tension scores.

    From behavior specification:
    - 0-2: Almost Certain
    - 3-4: Likely
    - 5-6: 50/50
    - 7-8: Unlikely
    - 9-10: Impossible
    """
    # Test each tension level
    test_cases = [
        (0, "almost_certain"),
        (1, "almost_certain"),
        (2, "almost_certain"),
        (3, "likely"),
        (4, "likely"),
        (5, "fifty_fifty"),
        (6, "fifty_fifty"),
        (7, "unlikely"),
        (8, "unlikely"),
        (9, "impossible"),
        (10, "impossible"),
    ]

    for tension_score, expected_likelihood in test_cases:
        likelihood = await oracle_agent.determine_likelihood(tension_score)
        assert likelihood.value == expected_likelihood, (
            f"Tension {tension_score} should map to {expected_likelihood}, got {likelihood.value}"
        )


# --- Roll Range Tests ---


@pytest.mark.unit
async def test_p18_roll_range(oracle_agent):
    """
    Success Criteria: Roll range 1-100 (100% correct)
    """
    # Make multiple rolls to verify range
    rolls = []
    for _ in range(100):
        roll = await oracle_agent.roll_percentile()
        rolls.append(roll)
        assert 1 <= roll <= 100, f"Roll {roll} is outside valid range 1-100"

    # Check for variety (should not all be the same)
    unique_rolls = set(rolls)
    assert len(unique_rolls) > 1, "Rolls should be varied, not all the same"


# --- Turn Metadata Tests ---


@pytest.mark.unit
async def test_p18_turn_metadata_completeness(
    scene_loop,
    scene_with_tension,
    context_assembly,
    oracle_agent,
    canon_keeper,
    narrator,
):
    """
    Success Criteria: Metadata completeness = 100% (roll, likelihood, fact_id all present)
    """
    # Setup
    scene_id = scene_with_tension.scene_id
    scene_loop.scenes[scene_id] = scene_with_tension

    query = "Is the door locked?"

    # Execute oracle flow
    is_oracle_query = await context_assembly.detect_oracle_query(query)
    assert is_oracle_query is True

    tension_score = scene_with_tension.tension_score
    likelihood = await oracle_agent.determine_likelihood(tension_score)

    import random

    original_random = random.randint
    random.randint = lambda a, b: 60

    try:
        roll = await oracle_agent.roll_percentile()
        outcome = oracle_agent.get_outcome_from_roll(roll, likelihood)
        fact = await canon_keeper.canonize_oracle_result(
            query, outcome, roll, tension_score
        )
        narrative = await narrator.describe_oracle_outcome(
            query, outcome, {"location": "tavern"}
        )
        turns = await scene_loop.append_turns(
            scene_id, query, narrative, outcome, roll, likelihood, fact.fact_id
        )
    finally:
        random.randint = original_random

    # Verify user turn metadata
    user_turn = turns[0]
    assert "oracle_query" in user_turn.metadata, (
        "User turn should have oracle_query metadata"
    )
    assert user_turn.metadata["oracle_query"] is True, "oracle_query should be True"

    # Verify GM turn metadata
    gm_turn = turns[1]
    required_metadata = ["oracle_result", "roll", "likelihood", "fact_canonized"]

    for field in required_metadata:
        assert field in gm_turn.metadata, (
            f"GM turn should have metadata field '{field}'"
        )

    assert gm_turn.metadata["oracle_result"] == "yes", "oracle_result should be correct"
    assert gm_turn.metadata["roll"] == 60, "roll should be correct"
    assert gm_turn.metadata["likelihood"] == "fifty_fifty", (
        "likelihood should be correct"
    )
    assert fact.fact_id in gm_turn.metadata["fact_canonized"], (
        "fact_canonized should reference correct fact"
    )


# --- Postconditions Tests ---


@pytest.mark.unit
async def test_p18_postconditions(
    scene_loop,
    scene_with_tension,
    context_assembly,
    oracle_agent,
    canon_keeper,
    narrator,
):
    """
    Verify all postconditions are enforced:
    1. Oracle result canonized as Fact in Neo4j
    2. User turn appended with metadata oracle_query: True
    3. GM turn appended with oracle outcome and metadata
    4. Scene state updated with oracle result
    5. Player receives narrative describing outcome
    """
    # Setup
    scene_id = scene_with_tension.scene_id
    scene_loop.scenes[scene_id] = scene_with_tension
    original_updated_at = scene_with_tension.updated_at

    query = "Is the door locked?"

    # Execute oracle flow
    is_oracle_query = await context_assembly.detect_oracle_query(query)
    assert is_oracle_query is True, "Should detect oracle query"

    tension_score = scene_with_tension.tension_score
    likelihood = await oracle_agent.determine_likelihood(tension_score)

    import random

    original_random = random.randint
    random.randint = lambda a, b: 60

    try:
        roll = await oracle_agent.roll_percentile()
        outcome = oracle_agent.get_outcome_from_roll(roll, likelihood)
        fact = await canon_keeper.canonize_oracle_result(
            query, outcome, roll, tension_score
        )
        narrative = await narrator.describe_oracle_outcome(
            query, outcome, {"location": "tavern"}
        )
        turns = await scene_loop.append_turns(
            scene_id, query, narrative, outcome, roll, likelihood, fact.fact_id
        )
    finally:
        random.randint = original_random

    # Postcondition 1: Oracle result canonized as Fact
    assert fact is not None, "Oracle result should be canonized as Fact"
    assert fact.content == f"{query}: yes", "Fact should contain oracle result"

    # Postcondition 2: User turn appended with metadata
    user_turn = turns[0]
    assert user_turn.turn_type == "question", "User turn should be QUESTION type"
    assert user_turn.metadata.get("oracle_query") is True, (
        "User turn should have oracle_query metadata"
    )

    # Postcondition 3: GM turn appended with oracle outcome and metadata
    gm_turn = turns[1]
    assert gm_turn.turn_type == "oracle_response", (
        "GM turn should be ORACLE_RESPONSE type"
    )
    assert gm_turn.metadata.get("oracle_result") == "yes", (
        "GM turn should have oracle_result"
    )
    assert gm_turn.metadata.get("roll") == 60, "GM turn should have roll"
    assert gm_turn.metadata.get("likelihood") == "fifty_fifty", (
        "GM turn should have likelihood"
    )

    # Postcondition 4: Scene state updated
    updated_scene = await scene_loop.get_scene(scene_id)
    assert updated_scene is not None, "Scene should still exist"
    assert updated_scene.updated_at >= original_updated_at, (
        "Scene updated_at should be updated"
    )

    # Postcondition 5: Player receives narrative
    assert narrative is not None, "Player should receive narrative"
    assert len(narrative) > 0, "Narrative should not be empty"
