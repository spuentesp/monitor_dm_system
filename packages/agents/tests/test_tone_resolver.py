"""
Tests for the ToneResolver utility.

Covers:
- resolve_from_profile: Full resolution flow with ToneLibraries and ToneProfiles.
- _load_tone_libraries: Logic for merging specific and default libraries.
- _find_matching_profiles: Matching tone_tags against ToneProfile.trigger_tags.
- Caching behavior for libraries and profiles.
- Fallback to built-in profiles via MongoDB (async fallback path).
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from monitor_agents.utils.tone_resolver import ToneResolver

# ===========================================================================
# FIXTURES
# ===========================================================================


@pytest.fixture
def mock_mcp_tools():
    """Mock MCP tools for MongoDB operations."""
    tools = MagicMock()
    # Define as AsyncMocks explicitly
    tools.mongodb_get_tone_library = AsyncMock(return_value=None)
    tools.mongodb_get_default_tone_library = AsyncMock(return_value=None)
    tools.mongodb_get_tone_profiles_batch = AsyncMock(return_value=[])
    tools.mongodb_normalize_tags = AsyncMock(side_effect=lambda tags: tags)
    tools.mongodb_normalize_tag = AsyncMock(side_effect=lambda tag: tag)
    return tools


@pytest.fixture
def sample_tone_profile():
    """Create a sample ToneProfile dict."""
    return {
        "profile_id": uuid4(),
        "name": "Grimdark Action",
        "instruction": "Visceral, bloody, and hopeless description of combat.",
        "trigger_tags": ["grim", "action", "combat"],
        "priority": 150,
    }


@pytest.fixture
def sample_library(sample_tone_profile):
    """Create a sample ToneLibrary dict."""
    return {
        "library_id": uuid4(),
        "name": "Standard Library",
        "tone_profile_ids": [str(sample_tone_profile["profile_id"])],
        "priority": 100,
        "is_default": False,
    }


# ===========================================================================
# UNIT TESTS: ToneResolver
# ===========================================================================


class TestToneResolver:
    @pytest.mark.asyncio
    async def test_resolve_no_profile_uses_fallback(self, mock_mcp_tools):
        """If no profile provided, resolve via default library + async fallback.

        When no GMProfile is set, the effective_profile uses fallback_tone as a tag
        and loads the default ToneLibrary from MongoDB. The async fallback then finds
        the matching built-in ToneProfile by trigger_tags. Only when the default
        library is completely empty does it fall back to _SAFE_FALLBACK_INSTRUCTIONS.
        """
        resolver = ToneResolver(mock_mcp_tools)

        # --- Test 1: Default library contains a "dramatic" built-in profile ---
        dramatic_profile = {
            "profile_id": uuid4(),
            "instruction": "Baroque, weighty instruction.",
            "trigger_tags": ["dramatic", "baroque"],
        }
        default_lib_with_dramatic = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(dramatic_profile["profile_id"])],
            "is_default": True,
        }
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(
            model_dump=lambda: default_lib_with_dramatic
        )
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [dramatic_profile]

        result = await resolver.resolve_from_profile(None, fallback_tone="dramatic")
        assert "Baroque, weighty instruction." in result

        # --- Test 2: Default library contains a "grim" built-in profile ---
        grim_profile = {
            "profile_id": uuid4(),
            "instruction": "Terse, industrial instruction.",
            "trigger_tags": ["grim", "gritty"],
        }
        default_lib_with_grim = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(grim_profile["profile_id"])],
            "is_default": True,
        }
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(
            model_dump=lambda: default_lib_with_grim
        )
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [grim_profile]

        result = await resolver.resolve_from_profile(None, fallback_tone="grim")
        assert "Terse, industrial instruction." in result

    @pytest.mark.asyncio
    async def test_resolve_custom_instructions_overrides_all(self, mock_mcp_tools):
        """If tone_instructions is set in profile, it replaces all ToneProfile logic."""
        resolver = ToneResolver(mock_mcp_tools)
        profile = {
            "tone_instructions": "Speak like a polite butler.",
            "tone_tags": ["grim"],  # Should be ignored
        }

        result = await resolver.resolve_from_profile(profile)

        assert result == "Speak like a polite butler."
        mock_mcp_tools.mongodb_get_tone_library.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_with_matching_profiles(self, mock_mcp_tools, sample_tone_profile, sample_library):
        """Test full flow: tags -> match -> merge instructions."""
        resolver = ToneResolver(mock_mcp_tools)

        # Setup mocks
        library_id = sample_library["library_id"]

        mock_mcp_tools.mongodb_get_tone_library.return_value = MagicMock(model_dump=lambda: sample_library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [sample_tone_profile]

        # GM Profile
        gm_profile = {
            "tone_library_id": str(library_id),
            "tone_tags": ["action"],
            "merge_with_default_library": False,
        }

        result = await resolver.resolve_from_profile(gm_profile)

        assert sample_tone_profile["instruction"] in result
        mock_mcp_tools.mongodb_get_tone_library.assert_called_with(library_id)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_merges_with_default_library(self, mock_mcp_tools, sample_tone_profile, sample_library):
        """Test merging specific library with default library."""
        resolver = ToneResolver(mock_mcp_tools)

        # Mocks
        default_profile = {
            "profile_id": uuid4(),
            "instruction": "Mysterious atmosphere.",
            "trigger_tags": ["mystery"],
        }
        default_library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(default_profile["profile_id"])],
            "priority": 50,
            "is_default": True,
        }

        mock_mcp_tools.mongodb_get_tone_library.return_value = MagicMock(model_dump=lambda: sample_library)
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: default_library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [
            sample_tone_profile,
            default_profile,
        ]

        gm_profile = {
            "tone_library_id": str(sample_library["library_id"]),
            "tone_tags": ["action", "mystery"],
            "merge_with_default_library": True,
        }

        result = await resolver.resolve_from_profile(gm_profile)

        assert sample_tone_profile["instruction"] in result
        assert default_profile["instruction"] in result

    @pytest.mark.asyncio
    async def test_resolve_fallback_to_builtin_if_no_matches(self, mock_mcp_tools):
        """If libraries are searched but no tags match, async fallback finds built-in profile.

        When no ToneProfile in the library has a matching trigger_tag, the async
        fallback queries the default library for built-in profiles matching the tag.
        """
        resolver = ToneResolver(mock_mcp_tools)

        # Library exists but has no profiles that match "horror" tag
        other_profile = {
            "profile_id": uuid4(),
            "instruction": "Some other instruction.",
            "trigger_tags": ["action"],  # doesn't match "horror"
        }
        empty_library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(other_profile["profile_id"])],
            "priority": 100,
        }
        mock_mcp_tools.mongodb_get_tone_library.return_value = MagicMock(model_dump=lambda: empty_library)

        # Default library HAS a built-in horror profile
        horror_profile = {
            "profile_id": uuid4(),
            "instruction": "Dread through omission instruction.",
            "trigger_tags": ["horror", "dread"],
        }
        default_lib = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(horror_profile["profile_id"])],
            "is_default": True,
        }
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: default_lib)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [
            other_profile,
            horror_profile,
        ]

        gm_profile = {
            "tone_library_id": str(empty_library["library_id"]),
            "tone_tags": ["horror"],
        }

        result = await resolver.resolve_from_profile(gm_profile)

        # Should contain the horror built-in profile instruction (from default library)
        assert "Dread through omission instruction." in result

    @pytest.mark.asyncio
    async def test_resolve_injects_theme_style_concept_tags(self, mock_mcp_tools):
        """Theme, style, and concept tags should be appended to the instruction."""
        resolver = ToneResolver(mock_mcp_tools)
        profile = {
            "tone_instructions": "Base.",
            "theme_tags": ["decay", "sacrifice"],
            "style_tags": ["poetic", "laconic"],
            "concept_tags": ["The cost of magic", "Entropy"],
        }

        result = await resolver.resolve_from_profile(profile)

        assert "Base." in result
        assert "Recurring themes: decay, sacrifice." in result
        assert "Prose style: poetic, laconic." in result
        assert "Guiding concepts: The cost of magic; Entropy." in result

    @pytest.mark.asyncio
    async def test_resolve_injects_constraints(self, mock_mcp_tools):
        """Narrator constraints should be appended at the end."""
        resolver = ToneResolver(mock_mcp_tools)
        profile = {
            "tone_instructions": "Base.",
            "narrator_constraints": "Never mention the color blue.",
        }

        result = await resolver.resolve_from_profile(profile)

        assert "Constraints: Never mention the color blue." in result

    @pytest.mark.asyncio
    async def test_caching_behavior(self, mock_mcp_tools, sample_library):
        """Verify libraries and default libraries are cached after first load."""
        resolver = ToneResolver(mock_mcp_tools)
        lib_id = sample_library["library_id"]

        # Setup mock return values explicitly
        mock_mcp_tools.mongodb_get_tone_library.return_value = MagicMock(model_dump=lambda: sample_library)
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = None

        gm_profile = {"tone_library_id": str(lib_id), "merge_with_default_library": False}

        # First call - should trigger tool call
        await resolver.resolve_from_profile(gm_profile)
        # Second call - should use cache
        await resolver.resolve_from_profile(gm_profile)

        # Tool should only be called once
        mock_mcp_tools.mongodb_get_tone_library.assert_called_once_with(lib_id)

    @pytest.mark.asyncio
    async def test_priority_ordering_in_merge(self, mock_mcp_tools):
        """Matched profiles should be merged in the order defined by library priorities."""
        resolver = ToneResolver(mock_mcp_tools)

        p1 = {"profile_id": uuid4(), "instruction": "High Priority.", "trigger_tags": ["t1"]}
        p2 = {"profile_id": uuid4(), "instruction": "Low Priority.", "trigger_tags": ["t2"]}

        # Library 1 (Priority 200)
        l1 = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(p1["profile_id"])],
            "priority": 200,
        }
        # Library 2 (Priority 50)
        l2 = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(p2["profile_id"])],
            "priority": 50,
        }

        mock_mcp_tools.mongodb_get_tone_library.return_value = MagicMock(model_dump=lambda: l1)
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: l2)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [p1, p2]

        gm_profile = {
            "tone_library_id": str(l1["library_id"]),
            "tone_tags": ["t1", "t2"],
            "merge_with_default_library": True,
        }

        result = await resolver.resolve_from_profile(gm_profile)

        # Instruction from P1 should come before P2
        assert result.find("High Priority.") < result.find("Low Priority.")

    @pytest.mark.asyncio
    async def test_case_insensitive_tag_matching(self, mock_mcp_tools):
        """Tags should match regardless of case or surrounding whitespace."""
        resolver = ToneResolver(mock_mcp_tools)

        profile = {
            "profile_id": uuid4(),
            "instruction": "Match found.",
            "trigger_tags": ["  Grim  ", "DARK"],
        }
        library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(profile["profile_id"])],
        }

        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [profile]

        # Test matching "grim" (lowercase) against "  Grim  "
        gm_profile = {"tone_tags": ["grim"]}
        result = await resolver.resolve_from_profile(gm_profile)
        assert "Match found." in result

        # Test matching " dark " against "DARK"
        gm_profile = {"tone_tags": [" dark "]}
        result = await resolver.resolve_from_profile(gm_profile)
        assert "Match found." in result

    @pytest.mark.asyncio
    async def test_empty_profile_dict_uses_fallback(self, mock_mcp_tools):
        """Empty profile dict is treated as no profile → effective_profile with fallback_tone."""
        resolver = ToneResolver(mock_mcp_tools)

        # Default library has a "grim" built-in profile
        grim_profile = {
            "profile_id": uuid4(),
            "instruction": "Terse, industrial instruction.",
            "trigger_tags": ["grim", "gritty"],
        }
        default_lib = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(grim_profile["profile_id"])],
            "is_default": True,
        }
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: default_lib)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [grim_profile]

        result = await resolver.resolve_from_profile({}, fallback_tone="grim")
        assert "Terse, industrial instruction." in result

    @pytest.mark.asyncio
    async def test_profile_with_only_tone_instructions(self, mock_mcp_tools):
        """If profile has only tone_instructions, return it directly."""
        resolver = ToneResolver(mock_mcp_tools)
        profile = {
            "tone_instructions": "Speak like a pirate.",
        }

        result = await resolver.resolve_from_profile(profile)

        assert result == "Speak like a pirate."
        mock_mcp_tools.mongodb_get_tone_library.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_tone_tags_list(self, mock_mcp_tools, sample_tone_profile):
        """If tone_tags is an empty list, fallback to builtin."""
        resolver = ToneResolver(mock_mcp_tools)

        library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(sample_tone_profile["profile_id"])],
        }
        mock_mcp_tools.mongodb_get_tone_library.return_value = MagicMock(model_dump=lambda: library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [sample_tone_profile]

        gm_profile = {
            "tone_library_id": str(library["library_id"]),
            "tone_tags": [],
        }

        result = await resolver.resolve_from_profile(gm_profile)
        # Should contain "Baroque" (default dramatic)
        assert "Baroque" in result

    @pytest.mark.asyncio
    async def test_profile_without_tone_library_id(self, mock_mcp_tools):
        """If profile has no tone_library_id, use default library."""
        resolver = ToneResolver(mock_mcp_tools)

        profile = {
            "profile_id": uuid4(),
            "instruction": "Default profile.",
            "trigger_tags": ["action"],
        }
        default_library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(profile["profile_id"])],
            "is_default": True,
        }

        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: default_library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [profile]

        gm_profile = {
            "tone_tags": ["action"],
            "merge_with_default_library": True,
        }

        result = await resolver.resolve_from_profile(gm_profile)
        assert "Default profile." in result

    @pytest.mark.asyncio
    async def test_merge_with_default_library_false(self, mock_mcp_tools, sample_tone_profile):
        """When merge_with_default_library is False, don't merge default."""
        resolver = ToneResolver(mock_mcp_tools)

        # Specific library
        specific_library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(sample_tone_profile["profile_id"])],
            "priority": 100,
            "is_default": False,
        }

        # Default library (should NOT be loaded)
        default_profile = {
            "profile_id": uuid4(),
            "instruction": "Default instruction.",
            "trigger_tags": ["mystery"],
        }
        default_library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(default_profile["profile_id"])],
            "is_default": True,
        }

        mock_mcp_tools.mongodb_get_tone_library.return_value = MagicMock(model_dump=lambda: specific_library)
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: default_library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [
            sample_tone_profile,
            default_profile,
        ]

        gm_profile = {
            "tone_library_id": str(specific_library["library_id"]),
            "tone_tags": ["action"],
            "merge_with_default_library": False,
        }

        result = await resolver.resolve_from_profile(gm_profile)

        assert sample_tone_profile["instruction"] in result
        assert default_profile["instruction"] not in result

    @pytest.mark.asyncio
    async def test_empty_tone_instructions_uses_normal_flow(self, mock_mcp_tools, sample_tone_profile):
        """If tone_instructions is empty string, proceed with normal resolution flow."""
        resolver = ToneResolver(mock_mcp_tools)

        library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(sample_tone_profile["profile_id"])],
        }
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [sample_tone_profile]

        gm_profile = {
            "tone_instructions": "",  # Empty string
            "tone_tags": ["action"],
        }

        result = await resolver.resolve_from_profile(gm_profile)
        # Should use profile, not empty instruction
        assert sample_tone_profile["instruction"] in result

    @pytest.mark.asyncio
    async def test_multiple_profiles_matching_same_tag(self, mock_mcp_tools):
        """When multiple profiles match the same tag, both should be included."""
        resolver = ToneResolver(mock_mcp_tools)

        p1 = {"profile_id": uuid4(), "instruction": "First match.", "trigger_tags": ["action"]}
        p2 = {"profile_id": uuid4(), "instruction": "Second match.", "trigger_tags": ["action"]}

        library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(p1["profile_id"]), str(p2["profile_id"])],
        }

        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [p1, p2]

        gm_profile = {"tone_tags": ["action"]}
        result = await resolver.resolve_from_profile(gm_profile)

        assert "First match." in result
        assert "Second match." in result

    @pytest.mark.asyncio
    async def test_no_matching_tags_in_libraries(self, mock_mcp_tools, sample_tone_profile):
        """If tags don't match any profiles in libraries, fallback to builtin."""
        resolver = ToneResolver(mock_mcp_tools)

        library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(sample_tone_profile["profile_id"])],
        }
        mock_mcp_tools.mongodb_get_tone_library.return_value = MagicMock(model_dump=lambda: library)
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = None
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [sample_tone_profile]

        gm_profile = {
            "tone_library_id": str(library["library_id"]),
            "tone_tags": ["nonexistent_tag"],
        }

        result = await resolver.resolve_from_profile(gm_profile)
        # No profiles match "nonexistent_tag", default lib is None → falls back to _SAFE_FALLBACK_INSTRUCTIONS["dramatic"]
        assert "Baroque" in result

    @pytest.mark.asyncio
    async def test_duplicate_tags_handled_correctly(self, mock_mcp_tools, sample_tone_profile):
        """Duplicate tags should not cause duplicate instructions."""
        resolver = ToneResolver(mock_mcp_tools)

        library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(sample_tone_profile["profile_id"])],
        }
        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [sample_tone_profile]

        gm_profile = {"tone_tags": ["action", "action", "action"]}
        result = await resolver.resolve_from_profile(gm_profile)

        # Instruction should appear only once
        count = result.count(sample_tone_profile["instruction"])
        assert count == 1

    @pytest.mark.asyncio
    async def test_tags_with_hyphens_and_underscores(self, mock_mcp_tools):
        """Tags with hyphens and underscores should match trigger tags correctly."""
        resolver = ToneResolver(mock_mcp_tools)

        profile = {
            "profile_id": uuid4(),
            "instruction": "Hyphen/underscore match.",
            "trigger_tags": ["action-packed", "dark_mystery"],
        }
        library = {
            "library_id": uuid4(),
            "tone_profile_ids": [str(profile["profile_id"])],
        }

        mock_mcp_tools.mongodb_get_default_tone_library.return_value = MagicMock(model_dump=lambda: library)
        mock_mcp_tools.mongodb_get_tone_profiles_batch.return_value = [profile]

        # Test with hyphen
        gm_profile = {"tone_tags": ["action-packed"]}
        result = await resolver.resolve_from_profile(gm_profile)
        assert "Hyphen/underscore match." in result

        # Test with underscore
        gm_profile = {"tone_tags": ["dark_mystery"]}
        result = await resolver.resolve_from_profile(gm_profile)
        assert "Hyphen/underscore match." in result
