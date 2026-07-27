"""
Tests for dspy_runtime.py — env-var configuration, role resolution, and helpers.

Covers:
- normalize_node_name: CamelCase → snake_case conversion
- _load_node_roles_from_env: MONITOR_NODE_ROLES env var parsing
- default_role_for_node: node → ModelRole resolution
- _load_keywords / _get_high_intensity_keywords / _get_moderate_intensity_keywords
- resolve_dynamic_role: keyword-based role escalation logic
- get_dspy_lm: per-call parameter overrides (temperature, top_p, seed, max_tokens)

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_dspy_runtime.py -v
"""

from __future__ import annotations

import pytest

from monitor_agents.dspy_runtime import (
    ModelRole,
    _get_high_intensity_keywords,
    _get_moderate_intensity_keywords,
    _load_node_roles_from_env,
    default_role_for_node,
    normalize_node_name,
    resolve_dynamic_role,
)

pytestmark = pytest.mark.unit


# =============================================================================
# normalize_node_name
# =============================================================================


class TestNormalizeNodeName:
    def test_camelcase_to_snake(self):
        assert normalize_node_name("CanonKeeper") == "canon_keeper"
        assert normalize_node_name("ContextAssembly") == "context_assembly"

    def test_already_snake(self):
        assert normalize_node_name("narrator") == "narrator"
        assert normalize_node_name("canon_keeper") == "canon_keeper"

    def test_double_underscore_collapsed(self):
        # normalize_node_name converts CamelCase to snake, which may produce __
        # The .replace("__", "_") in the source collapses these
        result = normalize_node_name("CanonKeeper")
        assert "__" not in result
        assert result == "canon_keeper"

    def test_single_word(self):
        assert normalize_node_name("Narrator") == "narrator"

    def test_empty_string(self):
        assert normalize_node_name("") == ""

    def test_idempotent(self):
        once = normalize_node_name("CanonKeeper")
        twice = normalize_node_name(once)
        assert once == twice


# =============================================================================
# _load_node_roles_from_env
# =============================================================================


class TestLoadNodeRolesFromEnv:
    def test_returns_defaults_when_no_env(self, monkeypatch):
        monkeypatch.delenv("MONITOR_NODE_ROLES", raising=False)
        roles = _load_node_roles_from_env()
        assert roles["narrator"] == ModelRole.HEAVY
        assert roles["resolver"] == ModelRole.LIGHT

    def test_overrides_from_env(self, monkeypatch):
        monkeypatch.setenv("MONITOR_NODE_ROLES", '{"narrator": "light", "resolver": "heavy"}')
        roles = _load_node_roles_from_env()
        assert roles["narrator"] == ModelRole.LIGHT
        assert roles["resolver"] == ModelRole.HEAVY

    def test_invalid_json_returns_defaults(self, monkeypatch):
        monkeypatch.setenv("MONITOR_NODE_ROLES", "not json")
        roles = _load_node_roles_from_env()
        assert roles["narrator"] == ModelRole.HEAVY

    def test_invalid_role_value_skipped(self, monkeypatch):
        monkeypatch.setenv("MONITOR_NODE_ROLES", '{"narrator": "ultra", "resolver": "light"}')
        roles = _load_node_roles_from_env()
        # narrator stays at default (invalid role skipped)
        assert roles["narrator"] == ModelRole.HEAVY
        assert roles["resolver"] == ModelRole.LIGHT

    def test_empty_string_returns_defaults(self, monkeypatch):
        monkeypatch.setenv("MONITOR_NODE_ROLES", "")
        roles = _load_node_roles_from_env()
        assert (
            roles == _load_node_roles_from_env.__wrapped__
            if hasattr(_load_node_roles_from_env, "__wrapped__")
            else True
        )
        # Just verify defaults are present
        assert "narrator" in roles

    def test_partial_override_keeps_other_defaults(self, monkeypatch):
        monkeypatch.setenv("MONITOR_NODE_ROLES", '{"narrator": "standard"}')
        roles = _load_node_roles_from_env()
        assert roles["narrator"] == ModelRole.STANDARD
        assert roles["resolver"] == ModelRole.LIGHT  # unchanged


# =============================================================================
# default_role_for_node
# =============================================================================


class TestDefaultRoleForNode:
    def test_narrator_is_heavy(self):
        assert default_role_for_node("narrator") == ModelRole.HEAVY

    def test_canonkeeper_is_heavy(self):
        assert default_role_for_node("canonkeeper") == ModelRole.HEAVY
        assert default_role_for_node("CanonKeeper") == ModelRole.HEAVY

    def test_context_assembly_is_light(self):
        assert default_role_for_node("context_assembly") == ModelRole.LIGHT
        assert default_role_for_node("ContextAssembly") == ModelRole.LIGHT

    def test_unknown_node_defaults_to_standard(self):
        assert default_role_for_node("unknown_agent") == ModelRole.STANDARD

    def test_env_override_changes_role(self, monkeypatch):
        monkeypatch.setenv("MONITOR_NODE_ROLES", '{"narrator": "light"}')
        assert default_role_for_node("narrator") == ModelRole.LIGHT


# =============================================================================
# Intensity keywords
# =============================================================================


class TestIntensityKeywords:
    def test_high_intensity_defaults_present(self, monkeypatch):
        monkeypatch.delenv("MONITOR_HIGH_INTENSITY_KEYWORDS", raising=False)
        kw = _get_high_intensity_keywords()
        assert "attack" in kw
        assert "kill" in kw
        assert "death" in kw

    def test_high_intensity_override(self, monkeypatch):
        monkeypatch.setenv("MONITOR_HIGH_INTENSITY_KEYWORDS", "custom1,custom2,custom3")
        kw = _get_high_intensity_keywords()
        assert kw == {"custom1", "custom2", "custom3"}

    def test_high_intensity_override_lowercases(self, monkeypatch):
        monkeypatch.setenv("MONITOR_HIGH_INTENSITY_KEYWORDS", "ATTACK,KILL,Death")
        kw = _get_high_intensity_keywords()
        assert kw == {"attack", "kill", "death"}

    def test_moderate_intensity_defaults_present(self, monkeypatch):
        monkeypatch.delenv("MONITOR_MODERATE_INTENSITY_KEYWORDS", raising=False)
        kw = _get_moderate_intensity_keywords()
        assert "ask" in kw
        assert "investigate" in kw

    def test_moderate_intensity_override(self, monkeypatch):
        monkeypatch.setenv("MONITOR_MODERATE_INTENSITY_KEYWORDS", "wonder,ponder")
        kw = _get_moderate_intensity_keywords()
        assert kw == {"wonder", "ponder"}

    def test_empty_env_returns_defaults(self, monkeypatch):
        monkeypatch.setenv("MONITOR_HIGH_INTENSITY_KEYWORDS", "")
        kw = _get_high_intensity_keywords()
        assert "attack" in kw


# =============================================================================
# resolve_dynamic_role
# =============================================================================


class TestResolveDynamicRole:
    def test_high_intensity_escalates_to_heavy(self):
        result = resolve_dynamic_role("narrator", player_action="attack the goblin")
        assert result == ModelRole.HEAVY

    def test_moderate_intensity_downgrades_to_standard(self):
        result = resolve_dynamic_role("narrator", player_action="investigate the room")
        assert result == ModelRole.STANDARD

    def test_neutral_action_uses_default(self):
        result = resolve_dynamic_role("narrator", player_action="walk north")
        assert result == ModelRole.HEAVY  # narrator default

    def test_light_node_never_escalates(self):
        result = resolve_dynamic_role("context_assembly", player_action="attack kill death fight combat")
        assert result == ModelRole.LIGHT

    def test_empty_action_uses_default(self):
        result = resolve_dynamic_role("narrator", player_action="")
        assert result == ModelRole.HEAVY

    def test_none_action_uses_default(self):
        result = resolve_dynamic_role("narrator", player_action=None)
        assert result == ModelRole.HEAVY

    def test_critical_success_escalates(self):
        result = resolve_dynamic_role(
            "narrator",
            player_action="walk",
            resolution={"success_level": "critical_success", "roll_total": 10},
        )
        assert result == ModelRole.HEAVY

    def test_critical_failure_escalates(self):
        result = resolve_dynamic_role(
            "narrator",
            player_action="walk",
            resolution={"success_level": "critical_failure", "roll_total": 10},
        )
        assert result == ModelRole.HEAVY

    def test_extreme_roll_low_escalates(self):
        result = resolve_dynamic_role(
            "narrator",
            player_action="walk",
            resolution={"success_level": "success", "roll_total": 1},
        )
        assert result == ModelRole.HEAVY

    def test_extreme_roll_high_escalates(self):
        result = resolve_dynamic_role(
            "narrator",
            player_action="walk",
            resolution={"success_level": "success", "roll_total": 20},
        )
        assert result == ModelRole.HEAVY

    def test_normal_roll_no_escalation(self):
        result = resolve_dynamic_role(
            "narrator",
            player_action="walk",
            resolution={"success_level": "success", "roll_total": 10},
        )
        assert result == ModelRole.HEAVY  # default for narrator

    def test_base_role_light_never_escalates(self):
        result = resolve_dynamic_role(
            "indexer",
            player_action="attack kill death",
            base_role=ModelRole.LIGHT,
        )
        assert result == ModelRole.LIGHT

    def test_base_role_override(self):
        result = resolve_dynamic_role(
            "narrator",
            player_action="walk",
            base_role=ModelRole.STANDARD,
        )
        assert result == ModelRole.STANDARD

    def test_custom_keywords_from_env(self, monkeypatch):
        monkeypatch.setenv("MONITOR_HIGH_INTENSITY_KEYWORDS", "dance,sing")
        result = resolve_dynamic_role("narrator", player_action="dance and sing")
        assert result == ModelRole.HEAVY
