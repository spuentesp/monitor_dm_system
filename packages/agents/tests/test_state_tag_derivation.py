"""Tests for de-hardcoded, system-derived state-tag derivation.

Covers the C2 (no-hardcoding) remediation:
- ``canonical_state_tags`` derives wounded/unconscious from the game system's
  Health track threshold/depleted data — never a hardcoded HP<=0 vocabulary.
- ``evaluate_track_threshold`` reads the real ``ThresholdEffect`` schema
  (value / direction / effect), aligned with ``resource_engine``.
- ``_normalise_state_tag_update`` passes tags through without an alias table.
"""

from monitor_agents.canonkeeper import _normalise_state_tag_update
from monitor_agents.game_system._tracks_conditions import evaluate_track_threshold
from monitor_agents.game_system._types import build_system_data
from monitor_agents.loops.scene_support import canonical_state_tags

# Mirrors the Mistlands Core Health track shape now seeded in builtin_systems.json.
MISTLANDS_LIKE = {
    "tracks": [
        {
            "name": "Health",
            "abbreviation": "HP",
            "min_value": 0,
            "max_value": 10,
            "default_value": 10,
            "track_type": "hp",
            "depleted_effect": "Unconscious",
            "threshold_effects": [
                {"value": 5, "direction": "at_or_below", "effect": "Wounded"}
            ],
        }
    ]
}


# ---------------------------------------------------------------------------
# canonical_state_tags — system-derived, no hardcoded vocabulary
# ---------------------------------------------------------------------------


def test_full_health_yields_no_tags():
    tags = canonical_state_tags([], {}, {"Health": {"current": 10, "max": 10}}, MISTLANDS_LIKE)
    assert tags == []


def test_wounded_derived_from_system_threshold():
    # Staged HP = 10 - 6 = 4 (<= 5) -> Wounded, from track data not a literal.
    tags = canonical_state_tags(
        [], {"Health": -6}, {"Health": {"current": 10, "max": 10}}, MISTLANDS_LIKE
    )
    assert "wounded" in tags
    assert "unconscious" not in tags


def test_unconscious_at_depletion():
    tags = canonical_state_tags([], {}, {"Health": {"current": 0, "max": 10}}, MISTLANDS_LIKE)
    assert "wounded" in tags  # 0 <= 5
    assert "unconscious" in tags  # depleted_effect at min_value


def test_resource_resolves_by_abbreviation():
    tags = canonical_state_tags([], {}, {"HP": {"current": 0, "max": 10}}, MISTLANDS_LIKE)
    assert "unconscious" in tags


def test_condition_tags_pass_through():
    tags = canonical_state_tags(["frenzy", "Hidden"], {}, {}, MISTLANDS_LIKE)
    assert "frenzy" in tags
    assert "hidden" in tags


def test_no_system_means_no_hardcoded_vocabulary():
    # Without a bound system there is no HP<=0 inference — only the condition tags.
    tags = canonical_state_tags(["wounded"], {"HP": -3}, {"HP": {"current": 0}})
    assert tags == ["wounded"]


def test_long_effect_sentences_are_not_emitted_as_tags():
    sentence_system = {
        "tracks": [
            {
                "name": "Health",
                "abbreviation": "HP",
                "min_value": 0,
                "max_value": 10,
                "track_type": "hp",
                "threshold_effects": [
                    {
                        "value": 0,
                        "direction": "at_or_below",
                        "effect": "You are incapacitated and will die in 3 rounds.",
                    }
                ],
            }
        ]
    }
    tags = canonical_state_tags([], {}, {"Health": {"current": 0, "max": 10}}, sentence_system)
    assert tags == []  # full sentence is not a tag


# ---------------------------------------------------------------------------
# evaluate_track_threshold — reads the real schema keys
# ---------------------------------------------------------------------------


def test_threshold_reads_value_direction_effect():
    sd = build_system_data(MISTLANDS_LIKE)
    res = evaluate_track_threshold(sd, "Health", 4, 10)
    assert "Wounded" in res["thresholds_triggered"]
    assert res["depleted_effect"] is None

    depleted = evaluate_track_threshold(sd, "Health", 0, 10)
    assert depleted["depleted_effect"] == "Unconscious"


def test_threshold_at_or_above_direction():
    sd = build_system_data(
        {
            "tracks": [
                {
                    "name": "Hunger",
                    "track_type": "stress",
                    "min_value": 0,
                    "max_value": 5,
                    "threshold_effects": [
                        {"value": 5, "direction": "at_or_above", "effect": "Frenzy"}
                    ],
                }
            ]
        }
    )
    assert "Frenzy" in evaluate_track_threshold(sd, "Hunger", 5, 5)["thresholds_triggered"]
    assert "Frenzy" not in evaluate_track_threshold(sd, "Hunger", 3, 5)["thresholds_triggered"]


def test_legacy_threshold_label_keys_still_tolerated():
    sd = build_system_data(
        {
            "tracks": [
                {
                    "name": "Health",
                    "track_type": "resource",
                    "min_value": 0,
                    "max_value": 10,
                    "threshold_effects": [{"threshold": 5, "label": "Hurt"}],
                }
            ]
        }
    )
    assert "Hurt" in evaluate_track_threshold(sd, "Health", 4, 10)["thresholds_triggered"]


# ---------------------------------------------------------------------------
# canonkeeper — no alias table, no HP inference
# ---------------------------------------------------------------------------


def test_tags_pass_through_without_alias_remap():
    # 'injured' is no longer coerced to 'wounded' by a hardcoded alias table.
    out = _normalise_state_tag_update(
        {"entity_id": "e1", "add_tags": ["Injured", "off_balance"]}
    )
    assert out["add_tags"] == ["injured", "off_balance"]


def test_no_hp_based_tag_inference():
    # HP<=0 no longer auto-injects unconscious/wounded; the system drives that now.
    out = _normalise_state_tag_update(
        {"entity_id": "e1", "resources": {"HP": {"current": 0}}}
    )
    assert out["add_tags"] == []
