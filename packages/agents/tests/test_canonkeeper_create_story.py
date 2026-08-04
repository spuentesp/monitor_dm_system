from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.asyncio
async def test_create_story_returns_dict_from_string(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    mock_call_tool = AsyncMock(return_value=json.dumps({"id": "foo", "title": "My Story"}))
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    story_id = uuid4()
    result = await keeper.create_story(story_id, uuid4(), "My Story")

    assert result == {"id": "foo", "title": "My Story"}


@pytest.mark.asyncio
async def test_create_story_returns_fallback_on_bad_json(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    mock_call_tool = AsyncMock(return_value="not valid json")
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    story_id = uuid4()
    result = await keeper.create_story(story_id, uuid4(), "My Story")

    assert result == {"id": str(story_id)}


@pytest.mark.asyncio
async def test_create_story_returns_fallback_on_json_not_dict(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    mock_call_tool = AsyncMock(return_value="[1, 2, 3]")
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    story_id = uuid4()
    result = await keeper.create_story(story_id, uuid4(), "My Story")

    assert result == {"id": str(story_id)}


@pytest.mark.asyncio
async def test_create_story_returns_dict_directly(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    mock_call_tool = AsyncMock(return_value={"id": "bar"})
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    story_id = uuid4()
    result = await keeper.create_story(story_id, uuid4(), "My Story")

    assert result == {"id": "bar"}


@pytest.mark.asyncio
async def test_create_story_returns_fallback_for_none(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()

    mock_call_tool = AsyncMock(return_value=None)
    monkeypatch.setattr(keeper, "call_tool", mock_call_tool)

    story_id = uuid4()
    result = await keeper.create_story(story_id, uuid4(), "My Story")

    assert result == {"id": str(story_id)}
