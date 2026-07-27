"""Behavior tests for source_scope_support (Phase 4 - Retrieval Routing).

Exercises pure helpers — no LLM, no DB.

Covers:
- _as_list (None, single, list, dedupe, empty strings)
- _dedupe (case-insensitive, limit, order preservation)
- derive_source_scope (category keywords, term extraction)
- append_scope_terms_to_query (concatenation, limits)
- rank_snippets_with_source_scope (category bonus, system bonus, term bonus)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# =============================================================================
# _as_list
# =============================================================================


class TestAsList:
    def test_none_returns_empty(self):
        from monitor_agents.utils.source_scope_support import _as_list

        assert _as_list(None) == []

    def test_single_value_wrapped(self):
        from monitor_agents.utils.source_scope_support import _as_list

        assert _as_list("hello") == ["hello"]

    def test_list_passes_through(self):
        from monitor_agents.utils.source_scope_support import _as_list

        assert _as_list(["a", "b"]) == ["a", "b"]

    def test_dedupes_case_insensitive(self):
        from monitor_agents.utils.source_scope_support import _as_list

        result = _as_list(["Hello", "HELLO", "world"])
        assert result == ["Hello", "world"]

    def test_strips_whitespace(self):
        from monitor_agents.utils.source_scope_support import _as_list

        result = _as_list(["  hello  ", "world"])
        assert result == ["hello", "world"]

    def test_skips_empty(self):
        from monitor_agents.utils.source_scope_support import _as_list

        result = _as_list(["a", "", "  ", "b"])
        assert result == ["a", "b"]


# =============================================================================
# _dedupe
# =============================================================================


class TestDedupe:
    def test_preserves_order(self):
        from monitor_agents.utils.source_scope_support import _dedupe

        result = _dedupe(["a", "b", "c"], limit=10)
        assert result == ["a", "b", "c"]

    def test_case_insensitive(self):
        from monitor_agents.utils.source_scope_support import _dedupe

        result = _dedupe(["Foo", "foo", "FOO"], limit=10)
        assert result == ["Foo"]

    def test_respects_limit(self):
        from monitor_agents.utils.source_scope_support import _dedupe

        result = _dedupe(["a", "b", "c", "d", "e"], limit=3)
        assert result == ["a", "b", "c"]

    def test_strips_whitespace(self):
        from monitor_agents.utils.source_scope_support import _dedupe

        result = _dedupe(["  hello  "], limit=10)
        assert result == ["hello"]


# =============================================================================
# derive_source_scope
# =============================================================================


class TestDeriveSourceScope:
    def test_combat_action_picks_combat_rules(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        scope = derive_source_scope("I attack with my sword", {})
        assert "combat_rules" in scope["preferred_semantic_categories"]

    def test_spell_action_picks_power_system(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        scope = derive_source_scope("I cast a spell", {})
        assert "power_system" in scope["preferred_semantic_categories"]

    def test_persuade_picks_social_moral(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        scope = derive_source_scope("I try to persuade him", {})
        assert "social_moral" in scope["preferred_semantic_categories"]

    def test_unknown_action_falls_back_to_general(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        scope = derive_source_scope("zzzqqq", {})
        assert scope["preferred_semantic_categories"] == ["general"]

    def test_empty_action_falls_back_to_general(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        scope = derive_source_scope("", {})
        assert scope["preferred_semantic_categories"] == ["general"]

    def test_max_categories_respected(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        # "attack" (combat) and "spell" (power) and "monster" (creatures) and "history" (lore)
        scope = derive_source_scope(
            "I attack and cast spell on a monster of history", {}, max_categories=2
        )
        assert len(scope["preferred_semantic_categories"]) <= 2

    def test_pulls_terms_from_profile(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        profile = {
            "system_name": "Cyberpunk",
            "canon_signal_terms": ["netrunner", "braindance"],
            "taxonomy_containers": ["world:night_city"],
        }
        scope = derive_source_scope("zzz", profile, max_terms=10)
        assert "netrunner" in scope["preferred_terms"]
        assert "braindance" in scope["preferred_terms"]
        assert "world:night_city" in scope["preferred_terms"]

    def test_dedupes_terms(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        profile = {
            "canon_signal_terms": ["foo", "FOO", "bar"],
            "taxonomy_containers": [],
            "important_named_sets": [],
            "lore_domains": [],
        }
        scope = derive_source_scope("zzz", profile)
        # foo appears once
        assert scope["preferred_terms"].count("foo") == 1
        assert "bar" in scope["preferred_terms"]

    def test_includes_system_name(self):
        from monitor_agents.utils.source_scope_support import derive_source_scope

        scope = derive_source_scope("zzz", {"system_name": "MySystem"})
        assert scope["system_name"] == "MySystem"


# =============================================================================
# append_scope_terms_to_query
# =============================================================================


class TestAppendScopeTerms:
    def test_no_terms_returns_base(self):
        from monitor_agents.utils.source_scope_support import (
            append_scope_terms_to_query,
        )

        result = append_scope_terms_to_query("hello", {"preferred_terms": []})
        assert result == "hello"

    def test_empty_base_returns_terms(self):
        from monitor_agents.utils.source_scope_support import (
            append_scope_terms_to_query,
        )

        result = append_scope_terms_to_query("", {"preferred_terms": ["a", "b"]})
        assert result == "a b"

    def test_concatenates_with_space(self):
        from monitor_agents.utils.source_scope_support import (
            append_scope_terms_to_query,
        )

        result = append_scope_terms_to_query("hello", {"preferred_terms": ["world"]})
        assert result == "hello world"

    def test_limit_respected(self):
        from monitor_agents.utils.source_scope_support import (
            append_scope_terms_to_query,
        )

        result = append_scope_terms_to_query(
            "hello", {"preferred_terms": ["a", "b", "c", "d", "e"]}, limit=2
        )
        assert result == "hello a b"

    def test_none_query_treated_as_empty(self):
        from monitor_agents.utils.source_scope_support import (
            append_scope_terms_to_query,
        )

        result = append_scope_terms_to_query(None, {"preferred_terms": ["a"]})
        assert result == "a"


# =============================================================================
# rank_snippets_with_source_scope
# =============================================================================


class TestRankSnippets:
    def test_empty_input_returns_empty(self):
        from monitor_agents.utils.source_scope_support import (
            rank_snippets_with_source_scope,
        )

        scope = {"preferred_semantic_categories": ["combat_rules"]}
        assert (
            rank_snippets_with_source_scope([], scope=scope, player_action="attack")
            == []
        )

    def test_no_preferences_returns_input(self):
        from monitor_agents.utils.source_scope_support import (
            rank_snippets_with_source_scope,
        )

        snippets = [{"text": "hello", "score": 1.0}]
        scope = {}
        result = rank_snippets_with_source_scope(
            snippets, scope=scope, player_action="zzz"
        )
        assert result == snippets

    def test_category_match_boosts(self):
        from monitor_agents.utils.source_scope_support import (
            rank_snippets_with_source_scope,
        )

        snippets = [
            {"text": "a", "score": 1.0, "semantic_category": "lore_history"},
            {"text": "b", "score": 1.0, "semantic_category": "combat_rules"},
        ]
        scope = {"preferred_semantic_categories": ["combat_rules"]}
        result = rank_snippets_with_source_scope(
            snippets, scope=scope, player_action="attack"
        )
        # combat_rules snippet (b) should be first
        assert result[0]["text"] == "b"

    def test_system_match_boosts(self):
        from monitor_agents.utils.source_scope_support import (
            rank_snippets_with_source_scope,
        )

        snippets = [
            {"text": "a", "score": 1.0, "source_system_name": "OtherSystem"},
            {"text": "b", "score": 1.0, "source_system_name": "TargetSystem"},
        ]
        scope = {"system_name": "TargetSystem"}
        result = rank_snippets_with_source_scope(
            snippets, scope=scope, player_action="zzz"
        )
        # target system snippet (b) should be first
        assert result[0]["text"] == "b"

    def test_term_match_boosts(self):
        from monitor_agents.utils.source_scope_support import (
            rank_snippets_with_source_scope,
        )

        snippets = [
            {"text": "generic content", "score": 1.0},
            {"text": "the netrunner strikes", "score": 1.0},
        ]
        scope = {"preferred_terms": ["netrunner"]}
        result = rank_snippets_with_source_scope(
            snippets, scope=scope, player_action="zzz"
        )
        # netrunner snippet should be first
        assert "netrunner" in result[0]["text"]

    def test_action_match_boosts(self):
        from monitor_agents.utils.source_scope_support import (
            rank_snippets_with_source_scope,
        )

        snippets = [
            {"text": "unrelated", "score": 1.0},
            {"text": "I attack the dragon", "score": 1.0},
        ]
        scope = {"preferred_semantic_categories": ["combat_rules"]}
        result = rank_snippets_with_source_scope(
            snippets, scope=scope, player_action="attack"
        )
        # action-match snippet should be first
        assert "attack" in result[0]["text"]

    def test_handles_missing_score(self):
        from monitor_agents.utils.source_scope_support import (
            rank_snippets_with_source_scope,
        )

        snippets = [{"text": "a"}]  # No score
        scope = {"preferred_semantic_categories": ["combat_rules"]}
        result = rank_snippets_with_source_scope(
            snippets, scope=scope, player_action="zzz"
        )
        assert len(result) == 1
