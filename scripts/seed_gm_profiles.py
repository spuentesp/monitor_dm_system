#!/usr/bin/env python3
"""
Seed built-in GM profiles into MongoDB.

Creates 7 built-in profiles mirroring the 6 canonical tones from
Narrator._TONE_PROFILES plus a "Narrative Pure" profile for
narrative-only mode.

Usage:
    python scripts/seed_gm_profiles.py
    python scripts/seed_gm_profiles.py --force   # overwrite existing builtins
"""
# ruff: noqa: E402

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "packages" / "data-layer" / "src"))

from monitor_data.schemas.gm_profiles import GMProfileCreate, GMProfileFilter  # noqa: E402
from monitor_data.tools.mongodb_tools import (
    mongodb_create_gm_profile,
    mongodb_list_gm_profiles,
    mongodb_delete_gm_profile,
)  # noqa: E402


# ---------------------------------------------------------------------------
# Built-in profile definitions
# ---------------------------------------------------------------------------

BUILTIN_PROFILES = [
    {
        "name": "Dramatic",
        "description": "Baroque, weighty, emotionally charged. The default MONITOR voice.",
        "tone_tags": ["dramatic", "baroque", "emotionally_charged"],
        "theme_tags": ["personal_stakes", "indifferent_world"],
        "style_tags": [
            "medium_sentences",
            "rhythmic",
            "second_person",
            "present_tense",
        ],
        "concept_tags": ["silence_matters", "npcs_have_agendas"],
        "narrator_constraints": None,
        "is_builtin": True,
    },
    {
        "name": "Grim",
        "description": "Terse, industrial, cosmic-dread. Death is ordinary.",
        "tone_tags": ["grim", "terse", "cosmic_dread"],
        "theme_tags": ["mortality", "industrial_decay", "void"],
        "style_tags": [
            "short_sentences",
            "declarative",
            "second_person",
            "present_tense",
            "cold_sensory",
        ],
        "concept_tags": ["never_reassure", "death_is_ordinary"],
        "narrator_constraints": "Never be warm. Never offer comfort without a price.",
        "is_builtin": True,
    },
    {
        "name": "Horror",
        "description": "Dread through omission. What you don't describe is worse.",
        "tone_tags": ["horror", "dread", "ominous"],
        "theme_tags": ["unknown_threat", "wrongness", "isolation"],
        "style_tags": [
            "very_short_sentences",
            "second_person",
            "present_tense",
            "wrong_sensory",
        ],
        "concept_tags": [
            "never_name_the_threat",
            "silence_is_worse",
            "let_dread_build",
        ],
        "narrator_constraints": "Never name the threat directly. Never reassure. Use the wrong sensory note.",
        "is_builtin": True,
    },
    {
        "name": "Heroic",
        "description": "Elevated, mythic register. Hope exists but is earned.",
        "tone_tags": ["heroic", "mythic", "elevated"],
        "theme_tags": ["earning_hope", "consequence", "scale"],
        "style_tags": [
            "long_sentences",
            "momentum",
            "third_person_close",
            "descriptive",
        ],
        "concept_tags": ["actions_have_weight", "describe_the_scale", "hope_is_earned"],
        "narrator_constraints": None,
        "is_builtin": True,
    },
    {
        "name": "Mystery",
        "description": "Careful and layered. Information is rationed. End on questions.",
        "tone_tags": ["mystery", "layered", "careful"],
        "theme_tags": ["hidden_truths", "unreliable_npcs", "layers"],
        "style_tags": ["second_person", "present_tense", "planting_details"],
        "concept_tags": ["npcs_know_more", "end_on_questions", "never_answer_directly"],
        "narrator_constraints": "Never explain a planted detail prematurely. NPCs always know more than they say.",
        "is_builtin": True,
    },
    {
        "name": "Adventure",
        "description": "Kinetic and immediate. Momentum is everything. Humour allowed.",
        "tone_tags": ["adventure", "kinetic", "punchy"],
        "theme_tags": ["exploration", "discovery", "momentum"],
        "style_tags": [
            "short_punchy_action",
            "longer_wonder",
            "second_person",
            "present_tense",
        ],
        "concept_tags": ["keep_moving", "humour_allowed", "wonder_matters"],
        "narrator_constraints": None,
        "is_builtin": True,
    },
    {
        "name": "Narrative Pure",
        "description": "Pure fiction mode. No dice, no rules, just story. For narrative-only play.",
        "tone_tags": ["narrative", "immersive", "literary"],
        "theme_tags": ["character_driven", "world_building"],
        "style_tags": ["second_person", "present_tense", "literary_prose"],
        "concept_tags": ["story_first", "character_agency", "world_reacts"],
        "tone_instructions": (
            "You are a collaborative fiction writer, not a game engine. "
            "Focus entirely on narrative quality. There are no dice, no mechanics, "
            "no success/failure rolls. Every player action is resolved through fiction. "
            "Write like a novel in second person present tense. "
            "Prioritize prose quality, character development, and world immersion."
        ),
        "narrator_constraints": "No dice references. No stat checks. No mechanical language. Pure fiction.",
        "is_builtin": True,
    },
]


def seed(force: bool = False) -> None:
    """Seed built-in GM profiles."""
    # List existing builtins
    existing = mongodb_list_gm_profiles(GMProfileFilter(is_builtin=True))
    existing_names = {p.name for p in existing.profiles}

    if force and existing_names:
        print(
            f"Force mode: deleting {len(existing_names)} existing built-in profiles..."
        )
        for p in existing.profiles:
            mongodb_delete_gm_profile(p.profile_id)
            print(f"  Deleted: {p.name}")
        existing_names = set()

    created = 0
    skipped = 0

    for profile_def in BUILTIN_PROFILES:
        name = profile_def["name"]
        if name in existing_names:
            print(f"  SKIP (exists): {name}")
            skipped += 1
            continue

        profile = GMProfileCreate(**profile_def)
        result = mongodb_create_gm_profile(profile)
        print(f"  CREATED: {result.name} → {result.profile_id}")
        created += 1

    print(f"\nDone. Created: {created}, Skipped: {skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed built-in GM profiles")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite existing built-in profiles"
    )
    args = parser.parse_args()
    seed(force=args.force)


if __name__ == "__main__":
    main()
