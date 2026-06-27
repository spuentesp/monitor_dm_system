"""
Property-based tests for agent loop invariants.

Tests invariants of:
  - resolve_dynamic_role: keyword-based role escalation
  - Scene loop state transitions
  - Story loop state consistency

Use Cases: P-3, ST-2, SYS-2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from monitor_agents.dspy_runtime import (
    ModelRole,
    default_role_for_node,
    normalize_node_name,
    resolve_dynamic_role,
)


# =============================================================================
# STRATEGIES
# =============================================================================


# Player action text — mix of high-intensity, moderate, and neutral words.
_high_intensity_words = [
    "attack", "kill", "death", "die", "fight", "combat", "critical",
    "betray", "sacrifice", "explosion", "collapse", "scream", "flee",
    "ambush", "trap", "poison", "curse", "blood", "fire", "destroy",
]
_moderate_words = [
    "ask", "question", "investigate", "search", "examine", "talk",
    "negotiate", "persuade", "deceive", "stealth", "hide", "climb",
    "swim", "jump", "cast", "spell", "heal", "craft", "trade",
    "explore", "discover", "sense", "listen", "watch", "follow",
]
_neutral_words = ["walk", "sit", "stand", "look", "wait", "rest", "eat", "drink"]

player_action_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Pc", "Pd", "Zs")),
    min_size=1,
    max_size=200,
)

node_name_strategy = st.sampled_from([
    "narrator", "canon_keeper", "canonkeeper", "context_assembly",
    "query_formulation", "turn_intent", "indexer", "resolver",
    "world_architect", "npc_voice", "plot_hooks", "resource_engine",
    "simulacrum", "analyzer", "session_ingest",
])

resolution_strategy = st.fixed_dictionaries(
    {},
    optional={
        "success_level": st.sampled_from([
            "critical_success", "critical_failure", "catastrophic",
            "success", "failure", "partial",
        ]),
        "description": st.text(min_size=0, max_size=200),
        "roll_total": st.integers(min_value=1, max_value=20),
    },
)


# =============================================================================
# INVARIANT TESTS — resolve_dynamic_role
# =============================================================================


@given(action=player_action_strategy, node=node_name_strategy)
@settings(max_examples=200)
def test_resolve_dynamic_role_never_returns_none(action, node):
    """resolve_dynamic_role must always return a valid ModelRole."""
    result = resolve_dynamic_role(node, player_action=action)
    assert isinstance(result, ModelRole)


@given(
    action=st.sampled_from(_high_intensity_words),
    node=st.sampled_from(["narrator", "canon_keeper", "canonkeeper"]),
)
@settings(max_examples=50)
def test_high_intensity_action_escalates_to_heavy(action, node):
    """High-intensity keywords should escalate narrator/canonkeeper to HEAVY."""
    result = resolve_dynamic_role(node, player_action=action)
    assert result == ModelRole.HEAVY


@given(
    action=st.sampled_from(_moderate_words),
    node=st.sampled_from(["narrator", "canon_keeper", "canonkeeper"]),
)
@settings(max_examples=50)
def test_moderate_action_downgrades_to_standard(action, node):
    """Moderate-intensity keywords should produce STANDARD for narrator."""
    result = resolve_dynamic_role(node, player_action=action)
    assert result == ModelRole.STANDARD


@given(action=st.sampled_from(_neutral_words))
@settings(max_examples=30)
def test_neutral_action_uses_default_role(action):
    """Neutral actions should use the node's default role."""
    result = resolve_dynamic_role("narrator", player_action=action)
    # narrator default is HEAVY
    assert result == ModelRole.HEAVY


@given(node=st.sampled_from(["context_assembly", "query_formulation", "turn_intent", "indexer"]))
@settings(max_examples=30)
def test_light_nodes_never_escalate(node):
    """LIGHT-classified nodes should never be upgraded, regardless of action."""
    result = resolve_dynamic_role(node, player_action="attack kill death fight combat")
    assert result == ModelRole.LIGHT


@given(
    roll_total=st.integers(min_value=1, max_value=20),
    node=st.sampled_from(["narrator", "canon_keeper"]),
)
@settings(max_examples=40)
def test_extreme_rolls_escalate_to_heavy(roll_total, node):
    """Natural 1 or 20 (or extreme values) should escalate to HEAVY."""
    resolution = {"success_level": "success", "roll_total": roll_total}
    result = resolve_dynamic_role(node, player_action="walk", resolution=resolution)
    if roll_total <= 2 or roll_total >= 19:
        assert result == ModelRole.HEAVY


@given(
    success_level=st.sampled_from(["critical_success", "critical_failure", "catastrophic"]),
    node=st.sampled_from(["narrator", "canon_keeper"]),
)
@settings(max_examples=30)
def test_critical_outcomes_escalate_to_heavy(success_level, node):
    """Critical success/failure/catastrophic outcomes should escalate to HEAVY."""
    resolution = {"success_level": success_level, "roll_total": 10}
    result = resolve_dynamic_role(node, player_action="walk", resolution=resolution)
    assert result == ModelRole.HEAVY


# =============================================================================
# INVARIANT TESTS — normalize_node_name
# =============================================================================


@given(name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))))
@settings(max_examples=100)
def test_normalize_node_name_is_idempotent(name):
    """Normalizing twice should produce the same result as normalizing once."""
    once = normalize_node_name(name)
    twice = normalize_node_name(once)
    assert once == twice


@given(name=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("Lu", "Ll"))))
@settings(max_examples=100)
def test_normalize_node_name_is_lowercase(name):
    """Normalized node names should always be lowercase."""
    result = normalize_node_name(name)
    assert result == result.lower()


# =============================================================================
# INVARIANT TESTS — default_role_for_node
# =============================================================================


@given(node=node_name_strategy)
@settings(max_examples=100)
def test_default_role_always_returns_valid_role(node):
    """default_role_for_node must always return a valid ModelRole."""
    result = default_role_for_node(node)
    assert isinstance(result, ModelRole)


@given(node=st.sampled_from(["narrator", "canon_keeper", "canonkeeper"]))
@settings(max_examples=20)
def test_narrator_default_is_heavy(node):
    """Narrator and canonkeeper should default to HEAVY."""
    assert default_role_for_node(node) == ModelRole.HEAVY


@given(node=st.sampled_from(["context_assembly", "query_formulation", "turn_intent", "indexer"]))
@settings(max_examples=20)
def test_light_nodes_default_to_light(node):
    """Classification/extraction nodes should default to LIGHT."""
    assert default_role_for_node(node) == ModelRole.LIGHT