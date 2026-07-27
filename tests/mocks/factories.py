"""
Factory functions for common test data.

Provides builder functions for Pydantic models used across tests,
replacing the inline _make_* helpers scattered across test files.

Usage::

    from tests.mocks.factories import make_scene_state, make_fact_create, make_entity_create

    scene = make_scene_state(status="active")
    fact = make_fact_create(statement="Dragons exist", confidence=0.9)
"""

from __future__ import annotations

from datetime import datetime, timezone, UTC
from typing import Any
from uuid import uuid4

# =============================================================================
# Scene / Turn factories
# =============================================================================


def make_scene_id() -> str:
    return str(uuid4())


def make_story_id() -> str:
    return str(uuid4())


def make_universe_id() -> str:
    return str(uuid4())


def make_scene_state(
    scene_id: str | None = None,
    story_id: str | None = None,
    universe_id: str | None = None,
    status: str = "active",
    title: str = "Test Scene",
    turns: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a scene state dict for testing."""
    return {
        "scene_id": scene_id or make_scene_id(),
        "story_id": story_id or make_story_id(),
        "universe_id": universe_id or make_universe_id(),
        "status": status,
        "title": title,
        "turns": turns or [],
        "created_at": datetime.now(UTC).isoformat(),
        **extra,
    }


def make_turn(
    turn_id: str | None = None,
    scene_id: str | None = None,
    speaker: str = "user",
    text: str = "I enter the tavern.",
    **extra: Any,
) -> dict[str, Any]:
    """Build a turn dict for testing."""
    return {
        "turn_id": turn_id or str(uuid4()),
        "scene_id": scene_id or make_scene_id(),
        "speaker": speaker,
        "text": text,
        "timestamp": datetime.now(UTC).isoformat(),
        **extra,
    }


# =============================================================================
# Schema factories
# =============================================================================


def make_fact_create(
    statement: str = "Test fact",
    fact_type: str = "world_rule",
    magnitude: int = 5,
    confidence: float = 0.8,
    canon_level: str = "proposed",
    authority: str = "gm",
    universe_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a FactCreate-compatible dict."""
    return {
        "universe_id": universe_id or make_universe_id(),
        "statement": statement,
        "fact_type": fact_type,
        "magnitude": magnitude,
        "scope": "regional",
        "confidence": confidence,
        "authority": authority,
        "canon_level": canon_level,
        "status": "active",
        **extra,
    }


def make_entity_create(
    name: str = "Test Entity",
    entity_type: str = "character",
    description: str = "A test entity",
    universe_id: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build an EntityCreate-compatible dict."""
    return {
        "name": name,
        "entity_type": entity_type,
        "description": description,
        "universe_id": universe_id or make_universe_id(),
        "state_tags": [],
        "properties": {},
        "confidence": 0.8,
        **extra,
    }


# =============================================================================
# LLM config factories
# =============================================================================


def make_provider_row(
    id: str = "test-provider",
    name: str = "Test Provider",
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    api_key: str = "test-key",
    base_url: str | None = None,
    model_params: dict | None = None,
    role: str = "standard",
    status: str = "connected",
    is_default: bool = False,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    """Build a provider row dict (as returned by PostgresClient)."""
    return {
        "id": id,
        "name": name,
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "model_params": model_params or {},
        "role": role,
        "status": status,
        "is_default": is_default,
        "prompt_version": prompt_version,
    }


def make_node_assignment(
    node_name: str = "narrator",
    provider_id: str = "test-provider",
    param_overrides: dict | None = None,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    """Build a node assignment dict."""
    return {
        "node_name": node_name,
        "provider_id": provider_id,
        "param_overrides": param_overrides or {},
        "prompt_version": prompt_version,
    }


# =============================================================================
# Lorebook factories
# =============================================================================


def make_lorebook_entry(
    id: str = "lb-1",
    character_id: str = "universe:universe-123",
    keywords: list[str] | None = None,
    content: str = "Dragons are real.",
    priority: int = 50,
    tags: list[str] | None = None,
    confidence: float = 0.8,
    is_active: bool = True,
) -> dict[str, Any]:
    """Build a lorebook entry dict."""
    return {
        "id": id,
        "character_id": character_id,
        "keywords": keywords or ["dragon"],
        "content": content,
        "priority": priority,
        "tags": tags or [],
        "confidence": confidence,
        "is_active": is_active,
    }


def make_lorebook_entry_draft(
    keywords: list[str] | None = None,
    content: str = "Test lore entry",
    priority: int = 50,
    tags: list[str] | None = None,
    confidence: float = 0.7,
) -> dict[str, Any]:
    """Build a LorebookEntryDraft-compatible dict."""
    return {
        "keywords": keywords or ["test"],
        "content": content,
        "priority": priority,
        "tags": tags or [],
        "confidence": confidence,
    }
