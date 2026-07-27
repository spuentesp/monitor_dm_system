from __future__ import annotations

from monitor_agents.utils.query_traversal import (
    build_traversal_mask,
    collect_traversal_query_terms,
    get_counterpart_entity_id,
    infer_intent_family,
    score_candidate_relationship,
)


def test_infer_intent_family_detects_social_queries() -> None:
    assert infer_intent_family("I ask the captain to negotiate passage") == "social"


def test_build_traversal_mask_uses_seed_entities_and_relation_bundle() -> None:
    mask = build_traversal_mask(
        player_action="Where is the relic hidden?",
        source_scope={"preferred_semantic_categories": ["lore_history"]},
        seed_entity_ids=["e1", "e2"],
    )

    assert mask["intent_family"] == "spatial"
    assert "LOCATED_IN" in mask["preferred_rel_types"]
    assert mask["seed_entity_ids"] == ["e1", "e2"]


def test_score_candidate_relationship_boosts_preferred_type() -> None:
    preferred = ["KNOWS", "ALLIED_WITH"]
    low = score_candidate_relationship({"rel_type": "RELATED_TO", "properties": {}}, preferred_rel_types=preferred)
    high = score_candidate_relationship(
        {"rel_type": "KNOWS", "properties": {"strength": 4}},
        preferred_rel_types=preferred,
    )

    assert high > low


def test_collect_traversal_query_terms_respects_limit() -> None:
    candidates = [{"anchor_name": f"Entity{i}", "counterpart_name": f"Other{i}", "rel_type": "REL"} for i in range(20)]
    terms = collect_traversal_query_terms(candidates, limit=5)
    assert len(terms) <= 5


def test_collect_traversal_query_terms_with_empty_input() -> None:
    terms = collect_traversal_query_terms([])
    assert terms == []


def test_get_counterpart_entity_id() -> None:
    rel = {"from_entity_id": "a1", "to_entity_id": "c1", "rel_type": "KNOWS"}
    result = get_counterpart_entity_id(rel, anchor_entity_id="a1")
    assert result == "c1"


def test_get_counterpart_entity_id_reverse() -> None:
    """Should return from_id when anchor is to_id."""
    rel = {"from_entity_id": "a1", "to_entity_id": "c1", "rel_type": "KNOWS"}
    result = get_counterpart_entity_id(rel, anchor_entity_id="c1")
    assert result == "a1"


def test_infer_intent_family_handles_various_inputs() -> None:
    assert infer_intent_family("I attack the goblin") in (
        "combat",
        "social",
        "spatial",
        "lore",
        "item",
        "general",
    )
    assert infer_intent_family("What is in the chest?") in (
        "combat",
        "social",
        "spatial",
        "lore",
        "item",
        "general",
    )
    assert infer_intent_family("") in ("combat", "social", "spatial", "lore", "item", "general")


def test_build_traversal_mask_with_no_source_scope() -> None:
    mask = build_traversal_mask(
        player_action="Who is the king?",
        source_scope=None,
        seed_entity_ids=["e1"],
    )
    assert mask["intent_family"] is not None
    assert "seed_entity_ids" in mask


def test_collect_traversal_query_terms_deduplicates_names_and_types() -> None:
    terms = collect_traversal_query_terms(
        [
            {
                "anchor_name": "Captain Ilya",
                "counterpart_name": "Prince Marcel",
                "rel_type": "KNOWS",
            },
            {
                "anchor_name": "Captain Ilya",
                "counterpart_name": "Prince Marcel",
                "rel_type": "KNOWS",
            },
        ]
    )

    assert "Captain Ilya" in terms
    assert "Prince Marcel" in terms
    assert "KNOWS" in terms
    assert len(terms) == 3
