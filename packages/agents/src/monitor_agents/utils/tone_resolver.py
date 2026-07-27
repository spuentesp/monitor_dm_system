"""
GMProfile → Narrator instruction resolver (EXTENSIBLE).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data schemas (via MCP tools), monitor_agents internal utils
CALLED BY: Narrator, SceneLoop

This module resolves a GMProfile (tags, concepts, libraries) into a single
instruction string injected into the Narrator prompt.

EXTENSIBILITY:
- Tones are no longer hardcoded labels.
- Tones are defined by ToneProfile documents in MongoDB.
- Users can create new ToneProfiles and bundle them in ToneLibraries.
- Tags in GMProfile trigger matching ToneProfiles.
"""

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

# ============================================================================
# SAFE FALLBACK INSTRUCTIONS
#
# These are the *last resort* fallback strings used only when MongoDB is
# completely empty of ToneProfiles (e.g. fresh DB before first seed).
#
# The canonical source of truth for built-in tones is now the MongoDB
# `tone_profiles` collection, seeded on every app startup via
# `ensure_tone_builtins()`. These strings MUST match those MongoDB
# documents exactly. They exist solely as an emergency safety net to
# prevent hard crashes if the DB is empty at runtime.
# ============================================================================

_SAFE_FALLBACK_INSTRUCTIONS: dict[str, str] = {
    "dramatic": (
        "Baroque, weighty, emotionally charged. Medium-length sentences with rhythm. "
        "Second-person present tense. Stakes feel personal. Silence and hesitation matter. "
        "The world is indifferent; NPCs have agendas."
    ),
    "grim": (
        "Terse, industrial, cosmic-dread. Short declarative sentences. "
        "Second-person present tense. Death is ordinary. The void is patient. "
        "Never reassure the player. Sensory details lean cold and metallic."
    ),
    "horror": (
        "Dread through omission. Very short sentences. What you don't describe is worse "
        "than what you do. Second-person present. Use the wrong sensory note — smell where "
        "you expect sound. Let silences last. Never name the threat directly."
    ),
    "heroic": (
        "Elevated, mythic register. Longer sentences with momentum. Third-person close "
        "or second-person as appropriate. Actions have weight and consequence. "
        "Hope exists but is earned. Describe the scale of things."
    ),
    "mystery": (
        "Careful and layered. Plant details, don't explain them. Second-person present. "
        "Information is rationed. NPCs know more than they say. "
        "End beats on a question, never an answer."
    ),
    "adventure": (
        "Kinetic and immediate. Short punchy sentences for action, longer for wonder. "
        "Second-person present. Momentum is everything. Humour is allowed."
    ),
}

# Public alias for external consumers (tests, seed scripts).
# This is the single source of truth for built-in tone descriptions.
BUILTIN_TONE_PROFILES: dict[str, str] = _SAFE_FALLBACK_INSTRUCTIONS


# ============================================================================
# ASYNC FALLBACK (used when no profiles matched in any library)
# ============================================================================


async def _async_fallback_to_builtin_profiles(
    mcp_tools: Any,
    tone_tags: list[str],
    fallback: str,
) -> str:
    """
    Async fallback when no ToneProfiles were matched in any ToneLibrary.

    Attempts to find a matching built-in profile by looking up the default
    ToneLibrary and matching trigger_tags. Only falls back to the emergency
    _SAFE_FALLBACK_INSTRUCTIONS strings if MongoDB is completely empty.

    This function is called from ToneResolver.resolve_from_profile when
    _find_matching_profiles returns an empty list.
    """
    # Try to load the default library and look for matching built-in profiles
    if hasattr(mcp_tools, "mongodb_get_default_tone_library"):
        try:
            default_lib = await mcp_tools.mongodb_get_default_tone_library()
        except Exception:
            default_lib = None

        if default_lib:
            lib_data = default_lib.model_dump() if hasattr(default_lib, "model_dump") else default_lib
            profile_ids_raw = lib_data.get("tone_profile_ids", [])
            if profile_ids_raw:
                try:
                    profile_ids = [UUID(str(p)) for p in profile_ids_raw]
                    profiles = await mcp_tools.mongodb_get_tone_profiles_batch(profile_ids)
                    tone_tags_lower = [t.lower().strip() for t in tone_tags]
                    matched_instructions = []
                    for profile in profiles:
                        trigger_tags = profile.get("trigger_tags", [])
                        trigger_tags_lower = [t.lower().strip() for t in trigger_tags]
                        for tone_tag in tone_tags_lower:
                            if tone_tag in trigger_tags_lower:
                                matched_instructions.append(profile["instruction"])
                                break
                    if matched_instructions:
                        base = " ".join(matched_instructions)
                        if tone_tags_lower:
                            unknown = [
                                t
                                for t in tone_tags
                                if t.lower().strip() not in [tt.lower() for tt in trigger_tags_lower]
                            ]
                            if unknown:
                                base += " Additional tone direction: " + ", ".join(unknown) + "."
                        return base
                except Exception:
                    pass  # Fall through to safe fallback

    # Absolute last resort — use the emergency strings (should never reach here
    # in normal operation after first startup seeding)
    return _SAFE_FALLBACK_INSTRUCTIONS.get(
        fallback.lower(),
        _SAFE_FALLBACK_INSTRUCTIONS["dramatic"],
    )


# ============================================================================
# TONE RESOLVER
# ============================================================================


class ToneResolver:
    """
    Orchestrates tone resolution using libraries, profiles, and tags.
    """

    def __init__(self, mcp_tools: Any):
        """
        Initialize with MCP tools for database access.

        Args:
            mcp_tools: MCP tools instance with mongodb_get_tone_library, etc.
        """
        self.mcp_tools = mcp_tools
        self._library_cache: dict[UUID, dict[str, Any]] = {}
        self._default_library_cache: dict[str, Any] | None = None
        self._profile_cache: dict[UUID, dict[str, Any]] = {}

    async def resolve_from_profile(
        self,
        gm_profile: dict[str, Any] | None,
        fallback_tone: str = "dramatic",
    ) -> str:
        """
        Resolve a GMProfile dict into a single tone_context string.

        Args:
            gm_profile: Dict from MongoDB (GMProfileResponse.model_dump()) or None.
            fallback_tone: Legacy session_tone string used when no profile is set.

        Returns:
            A composed narrator instruction string.
        """
        # If no profile, treat fallback_tone as a tag for dynamic lookup
        effective_profile = gm_profile or {
            "tone_tags": [fallback_tone],
            "merge_with_default_library": True,
        }

        # --- Step 1: Check custom override ---
        tone_instructions = effective_profile.get("tone_instructions")
        if tone_instructions:
            # Custom override replaces everything
            base = tone_instructions
        else:
            # Step 1a: Load ToneLibrary(s)
            libraries = await self._load_tone_libraries(effective_profile)

            # Step 1b: Normalize and Match ToneProfiles
            tone_tags = effective_profile.get("tone_tags", [])

            # Normalize tags using synonyms if tool is available
            normalized_tags = []
            if hasattr(self.mcp_tools, "mongodb_normalize_tags"):
                normalized_tags = await self.mcp_tools.mongodb_normalize_tags(tone_tags)
            elif hasattr(self.mcp_tools, "mongodb_normalize_tag"):
                for tag in tone_tags:
                    try:
                        normalized = await self.mcp_tools.mongodb_normalize_tag(tag)
                        normalized_tags.append(normalized)
                    except (TypeError, AttributeError):
                        normalized_tags.append(tag)
            else:
                normalized_tags = tone_tags

            matched_profiles = await self._find_matching_profiles(
                normalized_tags,
                libraries,
            )

            # Step 1c: Merge instructions
            if matched_profiles:
                base = " ".join(p["instruction"] for p in matched_profiles)
            else:
                # No profiles matched — try MongoDB default library lookup
                # (covers the case where builtins exist but tags didn't match)
                base = await _async_fallback_to_builtin_profiles(self.mcp_tools, normalized_tags, fallback_tone)

        # --- Step 2: Inject theme/style/concept tags ---
        tag_sections: list[str] = []

        theme_tags = effective_profile.get("theme_tags", [])
        if theme_tags:
            tag_sections.append("Recurring themes: " + ", ".join(theme_tags) + ".")

        style_tags = effective_profile.get("style_tags", [])
        if style_tags:
            tag_sections.append("Prose style: " + ", ".join(style_tags) + ".")

        concept_tags = effective_profile.get("concept_tags", [])
        if concept_tags:
            concepts = "; ".join(concept_tags)
            tag_sections.append(f"Guiding concepts: {concepts}.")

        constraints = effective_profile.get("narrator_constraints")
        if constraints:
            tag_sections.append(f"Constraints: {constraints}")

        # --- Compose ---
        parts = [base]
        if tag_sections:
            parts.append(" ".join(tag_sections))

        return " ".join(parts)

    async def _load_tone_libraries(
        self,
        gm_profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Load specific and default ToneLibraries based on profile settings."""
        libraries = []

        tone_library_id = gm_profile.get("tone_library_id")
        merge_default = gm_profile.get("merge_with_default_library", True)

        # 1. Specific Library
        if tone_library_id:
            lib_id = UUID(str(tone_library_id))
            lib = await self._get_library(lib_id)
            if lib:
                libraries.append(lib)

        # 2. Default Library
        if merge_default:
            default_lib = await self._get_default_library()
            if default_lib:
                libraries.append(default_lib)

        # Sort by priority descending
        libraries.sort(key=lambda lib: lib.get("priority", 100), reverse=True)
        return libraries

    async def _get_library(self, library_id: UUID) -> dict[str, Any] | None:
        """Get library from cache or DB."""
        if library_id in self._library_cache:
            return self._library_cache[library_id]

        if hasattr(self.mcp_tools, "mongodb_get_tone_library"):
            lib = await self.mcp_tools.mongodb_get_tone_library(library_id)
            if lib:
                self._library_cache[library_id] = lib.model_dump() if hasattr(lib, "model_dump") else lib
                return self._library_cache[library_id]
        return None

    async def _get_default_library(self) -> dict[str, Any] | None:
        """Get default library from cache or DB."""
        if self._default_library_cache is not None:
            return self._default_library_cache

        if hasattr(self.mcp_tools, "mongodb_get_default_tone_library"):
            lib = await self.mcp_tools.mongodb_get_default_tone_library()
            if lib:
                self._default_library_cache = lib.model_dump() if hasattr(lib, "model_dump") else lib
                return self._default_library_cache
        return None

    async def _find_matching_profiles(
        self,
        tone_tags: list[str],
        libraries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Find ToneProfiles matching the tags within the provided libraries.
        """
        if not tone_tags or not libraries:
            return []

        # Collect all tone_profile_ids from libraries
        profile_ids: set[UUID] = set()
        for library in libraries:
            for pid_str in library.get("tone_profile_ids", []):
                profile_ids.add(UUID(str(pid_str)))

        if not profile_ids:
            return []

        # Batch fetch all ToneProfiles
        profiles = await self.mcp_tools.mongodb_get_tone_profiles_batch(
            list(profile_ids),
        )

        # Find matches by trigger_tags
        matched = set()
        tone_tags_lower = [tag.lower().strip() for tag in tone_tags]

        for profile in profiles:
            trigger_tags = profile.get("trigger_tags", [])
            trigger_tags_lower = [t.lower().strip() for t in trigger_tags]

            # Check if any tone_tag matches any trigger_tag
            for tone_tag in tone_tags_lower:
                if tone_tag in trigger_tags_lower:
                    matched.add(profile["profile_id"])
                    break

        # Return matched profiles (as dicts, preserving priority order from libraries)
        profile_dict = {p["profile_id"]: p for p in profiles}
        matched_profiles = []

        # Iterate through libraries in priority order
        for library in libraries:
            for pid_str in library.get("tone_profile_ids", []):
                pid = UUID(str(pid_str))
                if pid in matched and pid in profile_dict:
                    matched_profiles.append(profile_dict[pid])
                    matched.remove(pid)  # Avoid duplicates

        return matched_profiles


# ============================================================================
# LEGACY FUNCTIONS (for backward compatibility)
# ============================================================================


def resolve_tone_from_profile(
    gm_profile: dict[str, Any] | None,
    fallback_tone: str = "dramatic",
    mcp_tools: Any | None = None,
) -> str:
    """
    Legacy function to resolve a GMProfile to narrator instruction.

    If mcp_tools is provided, uses the new extensible ToneResolver.
    Otherwise, falls back to _SAFE_FALLBACK_INSTRUCTIONS (emergency strings only).

    Args:
        gm_profile: Dict from MongoDB (GMProfileResponse.model_dump()) or None.
        fallback_tone: Legacy session_tone string used when no profile is set.
        mcp_tools: Optional MCP tools instance for extensible resolution.

    Returns:
        A composed narrator instruction string.
    """
    if mcp_tools:
        resolver = ToneResolver(mcp_tools)
        import asyncio

        return asyncio.run(resolver.resolve_from_profile(gm_profile, fallback_tone))

    # Fallback to legacy implementation
    # If no profile, treat fallback_tone as a tag for dynamic lookup
    effective_profile = gm_profile or {
        "tone_tags": [fallback_tone],
        "merge_with_default_library": True,
    }

    tone_instructions = effective_profile.get("tone_instructions")
    if tone_instructions:
        base = tone_instructions
    else:
        tone_tags: list[str] = effective_profile.get("tone_tags", [])
        base = _merge_tone_tags(tone_tags, fallback_tone)

    # Inject tags
    tag_sections: list[str] = []

    theme_tags = effective_profile.get("theme_tags", [])
    if theme_tags:
        tag_sections.append("Recurring themes: " + ", ".join(theme_tags) + ".")

    style_tags = effective_profile.get("style_tags", [])
    if style_tags:
        tag_sections.append("Prose style: " + ", ".join(style_tags) + ".")

    concept_tags = effective_profile.get("concept_tags", [])
    if concept_tags:
        concepts = "; ".join(concept_tags)
        tag_sections.append(f"Guiding concepts: {concepts}.")

    constraints = effective_profile.get("narrator_constraints")
    if constraints:
        tag_sections.append(f"Constraints: {constraints}")

    parts = [base]
    if tag_sections:
        parts.append(" ".join(tag_sections))

    return " ".join(parts)


def _merge_tone_tags(
    tone_tags: list[str],
    fallback: str,
) -> str:
    """
    Merge multiple tone tags with built-in profiles (sync-only fallback).

    This is the legacy sync-only path used by resolve_tone_from_profile()
    when no mcp_tools are available. It uses the emergency _SAFE_FALLBACK_INSTRUCTIONS
    strings directly, bypassing MongoDB.

    When mcp_tools are available, ToneResolver.resolve_from_profile() uses
    _async_fallback_to_builtin_profiles() instead, which queries MongoDB.
    """
    if not tone_tags:
        return _SAFE_FALLBACK_INSTRUCTIONS.get(
            fallback.lower(),
            _SAFE_FALLBACK_INSTRUCTIONS["dramatic"],
        )

    matched: list[str] = []
    freeform: list[str] = []

    for tag in tone_tags:
        key = tag.lower().strip()
        if key in _SAFE_FALLBACK_INSTRUCTIONS:
            matched.append(_SAFE_FALLBACK_INSTRUCTIONS[key])
        else:
            freeform.append(tag.strip())

    if matched:
        # Merge multiple built-in profiles
        base = " ".join(matched)
    else:
        # No recognized tags → fallback
        base = _SAFE_FALLBACK_INSTRUCTIONS.get(
            fallback.lower(),
            _SAFE_FALLBACK_INSTRUCTIONS["dramatic"],
        )

    if freeform:
        base += " " + "Additional tone direction: " + ", ".join(freeform) + "."

    return base


def get_profile_name(gm_profile: dict[str, Any] | None) -> str:
    """Extract profile name for logging/display. Returns 'default' if no profile."""
    if gm_profile:
        return str(gm_profile.get("name", "unnamed"))
    return "default"


def profile_has_custom_instructions(gm_profile: dict[str, Any] | None) -> bool:
    """Check if profile has a custom tone_instructions override."""
    return bool(gm_profile and gm_profile.get("tone_instructions"))
