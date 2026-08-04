import pytest
from monitor_agents.ingestion.triage import TriageAgent
from monitor_agents.ingestion.mechanics_architect import MechanicsArchitect
import dspy

class MockTriageResult:
    def __init__(self, tags: str):
        self.tags = tags

class MockMechanicsResult:
    def __init__(self, json_output: str):
        self.json_output = json_output

import contextlib

@pytest.fixture(autouse=True)
def mock_dspy_context(monkeypatch):
    @contextlib.contextmanager
    def mock_context(*args, **kwargs):
        yield

    monkeypatch.setattr("monitor_agents.dspy_runtime.dspy_context_for", mock_context)
    yield

@pytest.mark.unit
def test_triage_agent_parses_tags(monkeypatch):
    agent = TriageAgent()
    
    def mock_predict(self, *args, **kwargs):
        return MockTriageResult("#mechanics, #hybrid")
        
    monkeypatch.setattr(dspy.Predict, "__call__", mock_predict)
    
    tags = agent.triage("some combat rules")
    assert tags == ["#mechanics", "#hybrid"]

@pytest.mark.unit
def test_triage_agent_defaults_to_lore_if_empty(monkeypatch):
    agent = TriageAgent()
    
    def mock_predict(self, *args, **kwargs):
        return MockTriageResult("nonsense")
        
    monkeypatch.setattr(dspy.Predict, "__call__", mock_predict)
    
    tags = agent.triage("some lore")
    assert tags == ["#lore"]

@pytest.mark.unit
def test_mechanics_architect_extracts_json(monkeypatch):
    agent = MechanicsArchitect()
    
    def mock_predict(self, *args, **kwargs):
        return MockMechanicsResult('```json\n{"name": "Vampire System", "rules": []}\n```')
        
    monkeypatch.setattr(dspy.Predict, "__call__", mock_predict)
    
    data = agent.extract("some text")
    assert data["name"] == "Vampire System"
    assert "rules" in data

@pytest.mark.unit
def test_mechanics_architect_generates_id_for_hybrid(monkeypatch):
    agent = MechanicsArchitect()
    
    def mock_predict(self, *args, **kwargs):
        return MockMechanicsResult('{"name": "Dominate"}')
        
    monkeypatch.setattr(dspy.Predict, "__call__", mock_predict)
    
    data = agent.extract("some text")
    assert data["name"] == "Dominate"
    assert "id" in data
    assert data["id"].startswith("power_dominate_")
