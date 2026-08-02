"""Tests for the deterministic image-suggestion heuristics (Task 9).

``monitor_agents.image_suggestions.compute_image_suggestions`` is a pure,
deterministic function: same inputs -> same suggestions (IDs included, no
randomness, no I/O, no LLM). Suggestions are *hints rendered as chips* — they
never trigger generation themselves.

Run:
    uv run pytest packages/agents/tests/test_image_suggestions.py -v
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from monitor_agents.image_suggestions import (
    MAX_SUGGESTIONS_PER_SCENE,
    SUGGESTION_CADENCE_TURNS,
    ImageSuggestion,
    compute_image_suggestions,
    resolution_flags_appearance_change,
)

LOC_ID = uuid4()
NPC_ID = uuid4()
ACTOR_ID = uuid4()


def _location_entity(loc_id: UUID = LOC_ID, name: str = "The Rusted Flagon") -> dict:
    return {"id": str(loc_id), "entity_type": "location", "name": name}


def _suggestion(
    *,
    reason: str,
    subjects: list[UUID] | None = None,
    turn_id: str = "turn-old",
    asset_type: str | None = None,
) -> ImageSuggestion:
    """Build a prior suggestion the way the heuristics would have emitted it."""
    subjects = subjects or []
    asset_type = asset_type or ("portrait" if reason in ("npc_entry", "visual_state_change") else "scene")
    return ImageSuggestion(
        suggestion_id=uuid4(),
        asset_type=asset_type,  # type: ignore[arg-type]
        subject_entity_ids=subjects,
        reason=reason,  # type: ignore[arg-type]
        aspect_ratio="1:1" if asset_type == "portrait" else "16:9",
        source_turn_id=turn_id,
    )


# ===========================================================================
# Model
# ===========================================================================


class TestImageSuggestionModel:
    def test_defaults(self):
        s = ImageSuggestion(
            suggestion_id=uuid4(),
            asset_type="scene",
            reason="climax",
            source_turn_id="turn-1",
        )
        assert s.aspect_ratio == "16:9"
        assert s.subject_entity_ids == []

    def test_json_round_trip(self):
        s = _suggestion(reason="npc_entry", subjects=[NPC_ID])
        dumped = s.model_dump(mode="json")
        assert isinstance(dumped["suggestion_id"], str)
        assert isinstance(dumped["subject_entity_ids"][0], str)
        assert ImageSuggestion.model_validate(dumped) == s


# ===========================================================================
# Trigger: new canonical location
# ===========================================================================


class TestLocationChangeTrigger:
    def test_new_canonical_location_suggests_location_asset(self):
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            pacing={"tempo": 0.5, "phase": "rising"},
            turn_context={"location_name": "The Rusted Flagon"},
            entity_context=[_location_entity()],
        )
        assert len(out) == 1
        s = out[0]
        assert s.reason == "location_change"
        assert s.asset_type == "location"
        assert s.subject_entity_ids == [LOC_ID]
        assert s.aspect_ratio == "16:9"
        assert s.source_turn_id == "turn-3"

    def test_location_without_matching_entity_still_suggests(self):
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            turn_context={"location_name": "Ashmarket"},
            entity_context=[],
        )
        assert len(out) == 1
        assert out[0].reason == "location_change"
        assert len(out[0].subject_entity_ids) == 1  # deterministic derived subject

    def test_same_location_not_suggested_twice(self):
        prior = [_suggestion(reason="location_change", subjects=[LOC_ID], asset_type="location")]
        out = compute_image_suggestions(
            turn_id="turn-6",
            turn_number=6,
            turn_context={"location_name": "The Rusted Flagon"},
            entity_context=[_location_entity()],
            prior_suggestions=prior,
        )
        assert out == []

    def test_different_location_after_move_suggests_again(self):
        prior = [_suggestion(reason="location_change", subjects=[LOC_ID], asset_type="location")]
        new_loc = uuid4()
        out = compute_image_suggestions(
            turn_id="turn-6",
            turn_number=6,
            turn_context={"location_name": "Ashmarket"},
            entity_context=[_location_entity(new_loc, "Ashmarket")],
            prior_suggestions=prior,
        )
        assert len(out) == 1
        assert out[0].subject_entity_ids == [new_loc]


# ===========================================================================
# Trigger: first NPC entrance
# ===========================================================================


class TestNpcEntryTrigger:
    def test_first_npc_entrance_suggests_portrait(self):
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            turn_context={"npcs_present": [{"entity_id": str(NPC_ID), "name": "Marta"}]},
        )
        assert len(out) == 1
        s = out[0]
        assert s.reason == "npc_entry"
        assert s.asset_type == "portrait"
        assert s.subject_entity_ids == [NPC_ID]
        assert s.aspect_ratio == "1:1"

    def test_npc_entry_deduped_against_prior(self):
        prior = [_suggestion(reason="npc_entry", subjects=[NPC_ID])]
        out = compute_image_suggestions(
            turn_id="turn-6",
            turn_number=6,
            turn_context={"npcs_present": [{"entity_id": str(NPC_ID), "name": "Marta"}]},
            prior_suggestions=prior,
        )
        assert out == []

    def test_second_distinct_npc_suggests(self):
        prior = [_suggestion(reason="npc_entry", subjects=[NPC_ID])]
        other = uuid4()
        out = compute_image_suggestions(
            turn_id="turn-6",
            turn_number=6,
            turn_context={
                "npcs_present": [
                    {"entity_id": str(NPC_ID), "name": "Marta"},
                    {"entity_id": str(other), "name": "Brother Vell"},
                ]
            },
            prior_suggestions=prior,
        )
        assert len(out) == 1
        assert out[0].subject_entity_ids == [other]

    def test_npc_without_entity_id_uses_deterministic_subject(self):
        kwargs = dict(
            turn_id="turn-3",
            turn_number=3,
            turn_context={"npcs_present": [{"name": "Marta"}]},
        )
        first = compute_image_suggestions(**kwargs)
        second = compute_image_suggestions(**kwargs)
        assert len(first) == 1
        assert first[0].subject_entity_ids == second[0].subject_entity_ids


# ===========================================================================
# Trigger: explicit appearance-state change
# ===========================================================================


class TestVisualStateChangeTrigger:
    def test_explicit_appearance_change_suggests_actor_portrait(self):
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            actor_id=ACTOR_ID,
            appearance_state_changed=True,
        )
        assert len(out) == 1
        s = out[0]
        assert s.reason == "visual_state_change"
        assert s.asset_type == "portrait"
        assert s.subject_entity_ids == [ACTOR_ID]
        assert s.aspect_ratio == "1:1"

    def test_appearance_change_without_actor_yields_nothing(self):
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            actor_id=None,
            appearance_state_changed=True,
        )
        assert out == []

    def test_appearance_change_deduped_against_prior(self):
        prior = [_suggestion(reason="visual_state_change", subjects=[ACTOR_ID])]
        out = compute_image_suggestions(
            turn_id="turn-6",
            turn_number=6,
            actor_id=ACTOR_ID,
            appearance_state_changed=True,
            prior_suggestions=prior,
        )
        assert out == []


# ===========================================================================
# Trigger: climax pacing
# ===========================================================================


class TestClimaxTrigger:
    def test_peak_phase_suggests_scene_image(self):
        out = compute_image_suggestions(
            turn_id="turn-9",
            turn_number=9,
            pacing={"tempo": 0.9, "phase": "peak"},
        )
        assert len(out) == 1
        s = out[0]
        assert s.reason == "climax"
        assert s.asset_type == "scene"
        assert s.subject_entity_ids == []
        assert s.aspect_ratio == "16:9"

    def test_climax_only_once_per_scene(self):
        prior = [_suggestion(reason="climax", asset_type="scene")]
        out = compute_image_suggestions(
            turn_id="turn-12",
            turn_number=12,
            pacing={"tempo": 0.95, "phase": "peak"},
            prior_suggestions=prior,
        )
        assert out == []


# ===========================================================================
# No trigger: ordinary dialogue
# ===========================================================================


class TestNoSuggestionForOrdinaryDialogue:
    def test_plain_dialogue_turn_yields_nothing(self):
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            pacing={"tempo": 0.5, "phase": "rising"},
            turn_context={"location_name": "", "npcs_present": []},
            entity_context=[{"id": str(uuid4()), "entity_type": "character", "name": "Rhal"}],
        )
        assert out == []

    def test_no_turn_context_and_setup_phase_yields_nothing(self):
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            pacing={"tempo": 0.4, "phase": "setup"},
            turn_context=None,
        )
        assert out == []


# ===========================================================================
# Rate limits
# ===========================================================================


class TestRateLimits:
    @pytest.mark.parametrize("turn_number", [1, 2, 4, 5, 7, 8])
    def test_cadence_blocks_off_window_turns(self, turn_number: int):
        out = compute_image_suggestions(
            turn_id=f"turn-{turn_number}",
            turn_number=turn_number,
            pacing={"tempo": 0.9, "phase": "peak"},
            turn_context={"location_name": "Ashmarket"},
            entity_context=[],
        )
        assert out == []

    @pytest.mark.parametrize("turn_number", [3, 6, 9, 12])
    def test_cadence_allows_window_turns(self, turn_number: int):
        out = compute_image_suggestions(
            turn_id=f"turn-{turn_number}",
            turn_number=turn_number,
            pacing={"tempo": 0.9, "phase": "peak"},
        )
        assert len(out) == 1

    def test_cadence_constant_is_three(self):
        assert SUGGESTION_CADENCE_TURNS == 3

    def test_max_two_suggestions_per_scene(self):
        assert MAX_SUGGESTIONS_PER_SCENE == 2
        prior = [
            _suggestion(reason="location_change", subjects=[LOC_ID], asset_type="location"),
            _suggestion(reason="npc_entry", subjects=[NPC_ID]),
        ]
        out = compute_image_suggestions(
            turn_id="turn-9",
            turn_number=9,
            pacing={"tempo": 0.9, "phase": "peak"},
            turn_context={"npcs_present": [{"entity_id": str(uuid4()), "name": "New"}]},
            prior_suggestions=prior,
        )
        assert out == []

    def test_at_most_one_suggestion_per_window(self):
        """Multiple triggers firing in one window still yield a single chip."""
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            pacing={"tempo": 0.9, "phase": "peak"},
            turn_context={
                "location_name": "The Rusted Flagon",
                "npcs_present": [{"entity_id": str(NPC_ID), "name": "Marta"}],
            },
            entity_context=[_location_entity()],
            actor_id=ACTOR_ID,
            appearance_state_changed=True,
        )
        assert len(out) == 1
        # Priority order follows the brief: location first.
        assert out[0].reason == "location_change"


# ===========================================================================
# Determinism
# ===========================================================================


class TestDeterminism:
    def test_same_state_same_suggestions(self):
        kwargs = dict(
            turn_id="turn-3",
            turn_number=3,
            pacing={"tempo": 0.9, "phase": "peak"},
            turn_context={
                "location_name": "The Rusted Flagon",
                "npcs_present": [{"entity_id": str(NPC_ID), "name": "Marta"}],
            },
            entity_context=[_location_entity()],
        )
        first = compute_image_suggestions(**kwargs)
        second = compute_image_suggestions(**kwargs)
        assert first == second
        assert first[0].suggestion_id == second[0].suggestion_id

    def test_suggestion_id_changes_with_turn(self):
        base = dict(
            turn_number=3,
            pacing={"tempo": 0.9, "phase": "peak"},
        )
        a = compute_image_suggestions(turn_id="turn-a", **base)
        b = compute_image_suggestions(turn_id="turn-b", **base)
        assert a[0].suggestion_id != b[0].suggestion_id

    def test_suggestion_id_is_content_derived_not_random(self):
        out = compute_image_suggestions(
            turn_id="turn-3",
            turn_number=3,
            turn_context={"location_name": "The Rusted Flagon"},
            entity_context=[_location_entity()],
        )
        # A UUID derived from the inputs — stable across processes, never random.
        assert out[0].suggestion_id.version == 5


# ===========================================================================
# Prior-history robustness
# ===========================================================================


class TestPriorSuggestionForms:
    def test_prior_accepts_json_dicts(self):
        """Prior suggestions arrive as plain dicts after a checkpoint/Mongo
        round trip; dedupe and caps must work on those too."""
        prior = [_suggestion(reason="npc_entry", subjects=[NPC_ID]).model_dump(mode="json")]
        out = compute_image_suggestions(
            turn_id="turn-6",
            turn_number=6,
            turn_context={"npcs_present": [{"entity_id": str(NPC_ID), "name": "Marta"}]},
            prior_suggestions=prior,
        )
        assert out == []


# ===========================================================================
# resolution_flags_appearance_change helper
# ===========================================================================


class TestAppearanceFlagExtraction:
    def test_explicit_flag(self):
        assert resolution_flags_appearance_change({"appearance_change": True}) is True

    def test_effect_string_mentioning_appearance(self):
        assert resolution_flags_appearance_change({"effects": ["appearance_changed: ash stains"]}) is True

    def test_ordinary_effects_do_not_flag(self):
        assert resolution_flags_appearance_change({"effects": ["fiction_advances"]}) is False

    def test_none_resolution(self):
        assert resolution_flags_appearance_change(None) is False

    def test_empty_resolution(self):
        assert resolution_flags_appearance_change({}) is False


# ===========================================================================
# derive_turn_signals — per-turn signal derivation (Task 9, fix round 1)
# ===========================================================================
# In production the graph never populates SceneState.turn_context (no
# build_turn_context node exists), so the location/NPC triggers could never
# fire. The narrate node therefore derives the signals from the per-turn
# entity_context that load_context actually provides.


class TestDeriveTurnSignals:
    def _derive(self, *args, **kwargs):
        from monitor_agents.image_suggestions import derive_turn_signals

        return derive_turn_signals(*args, **kwargs)

    def test_location_entity_yields_location_name(self):
        out = self._derive([{"id": str(uuid4()), "entity_type": "location", "name": "Ashmarket"}])
        assert out["location_name"] == "Ashmarket"

    def test_current_state_tag_wins_over_first_location(self):
        out = self._derive(
            [
                {"id": str(uuid4()), "entity_type": "location", "name": "Far Ruins"},
                {
                    "id": str(uuid4()),
                    "entity_type": "location",
                    "name": "Ashmarket",
                    "state_tags": ["current"],
                },
            ]
        )
        assert out["location_name"] == "Ashmarket"

    def test_character_entities_yield_npcs_present(self):
        npc_id = uuid4()
        out = self._derive([{"id": str(npc_id), "entity_type": "character", "name": "Marta"}])
        assert out["npcs_present"] == [{"entity_id": str(npc_id), "name": "Marta"}]

    def test_actor_is_excluded_from_npcs(self):
        actor_id = uuid4()
        out = self._derive(
            [{"id": str(actor_id), "entity_type": "character", "name": "Rhal"}],
            actor_id=actor_id,
        )
        assert out["npcs_present"] == []

    def test_pc_role_excluded_from_npcs(self):
        out = self._derive(
            [
                {
                    "id": str(uuid4()),
                    "entity_type": "character",
                    "name": "Rhal",
                    "properties": {"role": "PC"},
                }
            ]
        )
        assert out["npcs_present"] == []

    def test_uppercase_entity_type_accepted(self):
        out = self._derive([{"id": str(uuid4()), "entity_type": "LOCATION", "name": "Ashmarket"}])
        assert out["location_name"] == "Ashmarket"

    def test_empty_context_yields_empty_signals(self):
        assert self._derive([]) == {"location_name": "", "npcs_present": []}

    def test_non_dict_entries_ignored(self):
        out = self._derive(["junk", None, {"entity_type": "object", "name": "Table"}])
        assert out == {"location_name": "", "npcs_present": []}
