from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.asyncio
async def test_create_entity_success(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call = AsyncMock(return_value={"id": "foo", "name": "bar"})
    monkeypatch.setattr(keeper, "call_tool", mock_call)
    
    class MockEnum:
        def __init__(self, val):
            self.value = val
            
    class MockCreate:
        universe_id = uuid4()
        id = uuid4()
        name = "bar"
        entity_type = MockEnum("Character")
        sub_type = None
        is_archetype = False
        description = "test"
        properties = {}
        state_tags = []
        archetype_id = None
        authority = MockEnum("canon_keeper")
        canon_level = MockEnum("canon")
        confidence = 1.0
        detail_level = MockEnum("low")
        
    result = await keeper.create_entity(MockCreate())
    
    assert result == {"id": "foo", "name": "bar"}
    mock_call.assert_called_once()
    
@pytest.mark.asyncio
async def test_create_entity_string_response(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call = AsyncMock(return_value=json.dumps({"id": "foo"}))
    monkeypatch.setattr(keeper, "call_tool", mock_call)
    
    class MockEnum:
        def __init__(self, val):
            self.value = val
            
    class MockCreate:
        universe_id = uuid4()
        id = None
        name = "bar"
        entity_type = MockEnum("Character")
        sub_type = None
        is_archetype = False
        description = "test"
        properties = {}
        state_tags = []
        archetype_id = None
        authority = MockEnum("canon_keeper")
        canon_level = MockEnum("canon")
        confidence = 1.0
        detail_level = MockEnum("low")
        
    result = await keeper.create_entity(MockCreate())
    assert result == {"id": "foo"}

@pytest.mark.asyncio
async def test_create_entity_bad_json_response(monkeypatch: pytest.MonkeyPatch):
    keeper = CanonKeeper()
    
    mock_call = AsyncMock(return_value="bad json")
    monkeypatch.setattr(keeper, "call_tool", mock_call)
    
    class MockEnum:
        def __init__(self, val):
            self.value = val
            
    class MockCreate:
        universe_id = uuid4()
        id = uuid4()
        name = "bar"
        entity_type = MockEnum("Character")
        sub_type = None
        is_archetype = False
        description = "test"
        properties = {}
        state_tags = []
        archetype_id = None
        authority = MockEnum("canon_keeper")
        canon_level = MockEnum("canon")
        confidence = 1.0
        detail_level = MockEnum("low")
        
    ent = MockCreate()
    result = await keeper.create_entity(ent)
    assert result == {"id": str(ent.id)}
