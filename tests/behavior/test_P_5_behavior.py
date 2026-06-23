"""
Behavior tests for P-5: Narrator prose generation.

Tests the Narrator's prose generation and tone management without LLM calls.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

from monitor_agents.narrator import Narrator, AgentToolAdapter
from monitor_agents.utils.tone_resolver import BUILTIN_TONE_PROFILES
from monitor_data.schemas.base import Speaker


class TestNarratorToneProfiles:
    def test_default_tone_profiles_exist(self):
        """Narrator has built-in tone profiles for common tones."""
        assert "dramatic" in BUILTIN_TONE_PROFILES
        assert "grim" in BUILTIN_TONE_PROFILES
        assert "heroic" in BUILTIN_TONE_PROFILES
        assert "horror" in BUILTIN_TONE_PROFILES
        assert "mystery" in BUILTIN_TONE_PROFILES
        assert "adventure" in BUILTIN_TONE_PROFILES

    def test_tone_profiles_are_non_empty(self):
        """Each tone profile has descriptive text."""
        for tone, description in BUILTIN_TONE_PROFILES.items():
            assert len(description) > 20, f"Tone '{tone}' has too-short description"

    def test_parse_minutes_default(self):
        """Non-numeric input defaults to 1."""
        result = Narrator._parse_minutes("unknown")
        assert result == 1

    def test_parse_minutes_numeric(self):
        """Numeric input is correctly parsed."""
        result = Narrator._parse_minutes("30 minutes")
        assert result == 30

    def test_parse_minutes_zero(self):
        """Zero is clamped to 1."""
        result = Narrator._parse_minutes("0")
        assert result == 1


class TestAgentToolAdapter:
    def test_adapter_creation(self):
        """Adapter can be created with a Narrator."""
        n = Narrator()
        adapter = AgentToolAdapter(n)
        assert adapter.agent == n


class TestNarratorConstructor:
    def test_creates_with_defaults(self):
        """Narrator can be created with default agent_id."""
        n = Narrator()
        assert n.agent_type == "Narrator"
        assert n.agent_id == "narrator-1"

    def test_creates_with_custom_id(self):
        """Narrator accepts custom agent_id."""
        n = Narrator(agent_id="custom-narrator")
        assert n.agent_id == "custom-narrator"
