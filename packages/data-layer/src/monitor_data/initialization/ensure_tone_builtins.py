"""
Idempotent initialization of built-in ToneProfiles, ToneLibraries, and TagDefinitions.

Called on every app startup via main.py lifespan. Safe to call multiple times —
checks existence before creating. After initial seeding, every call is a no-op.

LAYER: 1 (data-layer)
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from monitor_data.schemas.tag_registry import TagCategory, TagDefinitionCreate
from monitor_data.schemas.tone_libraries import ToneLibraryCreate
from monitor_data.schemas.tone_profiles import ToneProfileCreate, ToneProfileResponse
from monitor_data.tools.mongodb_tools.tag_registry import (
    mongodb_create_tag_definition,
    mongodb_get_tag_definition,
)
from monitor_data.tools.mongodb_tools.tone_libraries import (
    mongodb_create_tone_library,
    mongodb_get_default_tone_library,
)
from monitor_data.tools.mongodb_tools.tone_profiles import (
    mongodb_create_tone_profile,
)

logger = logging.getLogger(__name__)


# =============================================================================
# BUILT-IN TONE PROFILE DEFINITIONS
# These must match the strings previously hardcoded in BUILTIN_TONE_PROFILES.
# Kept here (not in a script) so both the init module and seed_tone_system.py
# can import from a single source of truth.
# =============================================================================

BUILTIN_TONE_PROFILES: list[dict[str, Any]] = [
    {
        "name": "Dramatic",
        "description": ("Rich, emotive prose with attention to sensory detail and emotional weight"),
        "instruction": (
            "Baroque, weighty, emotionally charged. Medium-length sentences with rhythm. "
            "Second-person present tense. Stakes feel personal. Silence and hesitation matter. "
            "The world is indifferent; NPCs have agendas."
        ),
        "trigger_tags": ["dramatic", "baroque", "theatrical", "emotionally_charged"],
        "category": "narrative",
        "language": "en",
        "is_builtin": True,
    },
    {
        "name": "Grim",
        "description": "Terse, industrial, cosmic-dread narrative voice for grim settings",
        "instruction": (
            "Terse, industrial, cosmic-dread. Short declarative sentences. "
            "Second-person present tense. Death is ordinary. The void is patient. "
            "Never reassure the player. Sensory details lean cold and metallic."
        ),
        "trigger_tags": ["grim", "gritty", "dark", "terse", "cosmic_dread"],
        "category": "narrative",
        "language": "en",
        "is_builtin": True,
    },
    {
        "name": "Horror",
        "description": "Dread through omission — what you don't describe is worse than what you do",
        "instruction": (
            "Dread through omission. Very short sentences. What you don't describe is worse "
            "than what you do. Second-person present. Use the wrong sensory note — smell where "
            "you expect sound. Let silences last. Never name the threat directly."
        ),
        "trigger_tags": ["horror", "dread", "scary", "ominous"],
        "category": "narrative",
        "language": "en",
        "is_builtin": True,
    },
    {
        "name": "Heroic",
        "description": "Elevated, mythic register for epic fantasy and heroic tales",
        "instruction": (
            "Elevated, mythic register. Longer sentences with momentum. Third-person close "
            "or second-person as appropriate. Actions have weight and consequence. "
            "Hope exists but is earned. Describe the scale of things."
        ),
        "trigger_tags": ["heroic", "epic", "mythic", "elevated"],
        "category": "narrative",
        "language": "en",
        "is_builtin": True,
    },
    {
        "name": "Mystery",
        "description": "Careful and layered, plants details without explaining them",
        "instruction": (
            "Careful and layered. Plant details, don't explain them. Second-person present. "
            "Information is rationed. NPCs know more than they say. "
            "End beats on a question, never an answer."
        ),
        "trigger_tags": ["mystery", "noir", "investigative", "layered", "careful"],
        "category": "narrative",
        "language": "en",
        "is_builtin": True,
    },
    {
        "name": "Adventure",
        "description": "Kinetic and immediate, punchy action with moments of wonder",
        "instruction": (
            "Kinetic and immediate. Short punchy sentences for action, longer for wonder. "
            "Second-person present. Momentum is everything. Humour is allowed."
        ),
        "trigger_tags": ["adventure", "pulp", "action", "kinetic", "punchy"],
        "category": "narrative",
        "language": "en",
        "is_builtin": True,
    },
]


# =============================================================================
# BUILT-IN TAG DEFINITIONS
# =============================================================================

BUILTIN_TAG_DEFINITIONS: list[dict[str, Any]] = [
    {
        "tag": "dramatic",
        "category": TagCategory.TONE,
        "synonyms": ["baroque", "theatrical", "emotionally_charged"],
        "description": "Weighty, emotionally charged narrative with attention to sensory detail and personal stakes.",
    },
    {
        "tag": "grim",
        "category": TagCategory.TONE,
        "synonyms": ["dark", "gritty", "terse", "cosmic_dread"],
        "description": "Terse, industrial prose with cosmic dread. Death is ordinary; the void is patient.",
    },
    {
        "tag": "horror",
        "category": TagCategory.TONE,
        "synonyms": ["scary", "dread", "ominous"],
        "description": "Dread through omission. What you don't describe is worse than what you do.",
    },
    {
        "tag": "heroic",
        "category": TagCategory.TONE,
        "synonyms": ["epic", "mythic", "elevated"],
        "description": "Elevated, mythic register with weight and consequence. Hope is earned.",
    },
    {
        "tag": "mystery",
        "category": TagCategory.TONE,
        "synonyms": ["noir", "investigative", "layered", "careful"],
        "description": "Careful and layered. Plant details, don't explain them. Information is rationed.",
    },
    {
        "tag": "adventure",
        "category": TagCategory.TONE,
        "synonyms": ["pulp", "action", "kinetic", "punchy"],
        "description": "Kinetic and immediate. Momentum is everything. Short punchy sentences for action, longer for wonder.",
    },
]


# =============================================================================
# INITIALIZATION
# =============================================================================


def ensure_tone_builtins() -> None:
    """
    Idempotent initialization of built-in ToneProfiles, ToneLibraries, and TagDefinitions.

    Called on every app startup. Safe to call multiple times — checks existence
    before creating. After initial seeding, subsequent calls are no-ops.

    Logs each creation so operators can verify the startup state.
    """
    logger.info("Initializing built-in tone system (idempotent)...")

    # --- Tone Profiles ---
    created_profiles: list[str] = []
    profile_ids: list[UUID] = []

    for profile_def in BUILTIN_TONE_PROFILES:
        name = profile_def["name"]
        # Check by name to avoid duplicates on re-run
        existing = _get_tone_profile_by_name(name)
        if not existing:
            params = ToneProfileCreate(**profile_def)
            result = mongodb_create_tone_profile(params)
            profile_ids.append(result.profile_id)
            created_profiles.append(name)
            logger.info("  Created ToneProfile: %s", name)
        else:
            profile_ids.append(existing.profile_id)
            logger.debug("  ToneProfile exists: %s", name)

    # --- Tag Definitions ---
    created_tags: list[str] = []

    for tag_def in BUILTIN_TAG_DEFINITIONS:
        tag = tag_def["tag"]
        if not mongodb_get_tag_definition(tag):
            tag_params = TagDefinitionCreate(**tag_def, is_builtin=True)
            mongodb_create_tag_definition(tag_params)
            created_tags.append(tag)
            logger.info("  Created TagDefinition: %s", tag)
        else:
            logger.debug("  TagDefinition exists: %s", tag)

    # --- Default Tone Library ---
    if not mongodb_get_default_tone_library():
        lib_params = ToneLibraryCreate(
            name="Default System Library",
            description="Built-in tone profiles for the MONITOR DM system.",
            tone_profile_ids=profile_ids,
            is_default=True,
            priority=100,
        )
        result = mongodb_create_tone_library(lib_params)  # type: ignore
        logger.info("  Created Default ToneLibrary: %s", result.name)
    else:
        logger.debug("  Default ToneLibrary already exists")

    # --- Summary ---
    total = len(created_profiles) + len(created_tags)
    if total > 0:
        logger.info(
            "Tone system initialization complete: %d profile(s), %d tag(s) created",
            len(created_profiles),
            len(created_tags),
        )
    else:
        logger.info("Tone system initialization complete: all builtins already present (no-op)")


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _get_tone_profile_by_name(name: str) -> ToneProfileResponse | None:
    """
    Look up a ToneProfile by exact name match.

    Uses list_tone_profiles internally since the MongoDB tool does not
    expose a direct get-by-name lookup.
    """
    from monitor_data.tools.mongodb_tools.tone_profiles import mongodb_list_tone_profiles

    result = mongodb_list_tone_profiles(limit=1000, offset=0)
    for profile in result.profiles:
        if profile.name == name:
            return profile
    return None
