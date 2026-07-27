from __future__ import annotations

from monitor_agents.utils.source_scope_support import (
    append_scope_terms_to_query,
    derive_source_scope,
    rank_snippets_with_source_scope,
)


def test_derive_source_scope_extracts_categories_and_terms_from_action_and_profile() -> None:
    profile = {
        "system_name": "V20",
        "taxonomy_containers": ["Clan", "Sect"],
        "canon_signal_terms": ["Prince", "Primogen"],
    }

    scope = derive_source_scope("I ask the prince to negotiate peace", profile)

    assert scope["system_name"] == "V20"
    assert "social_moral" in scope["preferred_semantic_categories"]
    assert "Prince" in scope["preferred_terms"]


def test_append_scope_terms_to_query_adds_scope_suffix() -> None:
    scope = {
        "preferred_terms": ["Clan", "Prince", "Elysium"],
    }

    query = append_scope_terms_to_query("ask about status", scope, limit=2)

    assert query.startswith("ask about status")
    assert "Clan" in query
    assert "Prince" in query


def test_rank_snippets_with_source_scope_prioritizes_category_and_system_matches() -> None:
    scope = {
        "system_name": "V20",
        "preferred_semantic_categories": ["social_moral"],
        "preferred_terms": ["Prince", "Clan"],
    }
    snippets = [
        {
            "chunk_id": "noise",
            "score": 0.9,
            "semantic_category": "lore_history",
            "source_system_name": "Other",
            "text": "Ancient tunnels and ruins near the harbor.",
        },
        {
            "chunk_id": "relevant",
            "score": 0.4,
            "semantic_category": "social_moral",
            "source_system_name": "V20",
            "text": "The Prince brokers clan disputes in Elysium.",
        },
    ]

    ranked = rank_snippets_with_source_scope(
        snippets,
        scope=scope,
        player_action="I ask the prince for support",
    )

    assert ranked[0]["chunk_id"] == "relevant"


def test_derive_source_scope_with_empty_profile() -> None:
    """derive_source_scope should handle empty profile."""
    profile = {}
    scope = derive_source_scope("some action", profile)

    assert "system_name" in scope
    assert "preferred_semantic_categories" in scope
    assert "preferred_terms" in scope


def test_derive_source_scope_with_missing_keys() -> None:
    """derive_source_scope should handle profile with missing keys."""
    profile = {"system_name": "D&D"}
    scope = derive_source_scope("attack the goblin", profile)

    assert scope["system_name"] == "D&D"


def test_append_scope_terms_to_query_empty_terms() -> None:
    """append_scope_terms_to_query should handle empty terms."""
    scope = {"preferred_terms": []}
    query = append_scope_terms_to_query("test query", scope, limit=2)

    assert query == "test query"


def test_append_scope_terms_to_query_with_limit() -> None:
    """append_scope_terms_to_query should respect limit parameter."""
    scope = {"preferred_terms": ["A", "B", "C", "D"]}
    query = append_scope_terms_to_query("test", scope, limit=2)

    # Should contain at most 2 terms from preferred_terms
    term_count = sum(1 for term in ["A", "B", "C", "D"] if term in query)
    assert term_count <= 2


def test_rank_snippets_with_empty_list() -> None:
    """rank_snippets_with_source_scope should handle empty snippets."""
    scope = {"system_name": "V20", "preferred_terms": []}
    ranked = rank_snippets_with_source_scope([], scope=scope, player_action="any action")

    assert ranked == []


def test_rank_snippets_all_same_score() -> None:
    """rank_snippets_with_source_scope should handle equal scores."""
    scope = {"system_name": "V20", "preferred_terms": [], "preferred_semantic_categories": []}
    snippets = [
        {
            "chunk_id": "a",
            "score": 0.5,
            "semantic_category": "lore",
            "source_system_name": "Other",
            "text": "Text A",
        },
        {
            "chunk_id": "b",
            "score": 0.5,
            "semantic_category": "lore",
            "source_system_name": "Other",
            "text": "Text B",
        },
    ]
    ranked = rank_snippets_with_source_scope(snippets, scope=scope, player_action="action")

    assert len(ranked) == 2


def test_rank_snippets_preserves_field_integrity() -> None:
    """rank_snippets_with_source_scope should preserve snippet fields."""
    scope = {
        "system_name": "V20",
        "preferred_terms": ["Prince"],
        "preferred_semantic_categories": ["social_moral"],
    }
    snippets = [
        {
            "chunk_id": "test",
            "score": 0.8,
            "semantic_category": "social_moral",
            "source_system_name": "V20",
            "text": "The Prince rules.",
        },
    ]
    ranked = rank_snippets_with_source_scope(snippets, scope=scope, player_action="ask about rules")

    assert ranked[0]["chunk_id"] == "test"
    assert ranked[0]["score"] == 0.8
    assert ranked[0]["text"] == "The Prince rules."
