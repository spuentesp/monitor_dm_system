import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from monitor_ui.main import app
import dspy

client = TestClient(app)

class DummySignature(dspy.Signature):
    """Test instruction."""
    input_text: str = dspy.InputField(desc="The input")
    output_text: str = dspy.OutputField(desc="The output")

DUMMY_REGISTRY = [
    {
        "module_id": "test.dummy",
        "agent": "TestAgent",
        "label": "Dummy Module",
        "description": "For testing",
        "signature": DummySignature,
        "predictor_type": "Predict",
        "llm_node": "test_node",
        "llm_role": "standard",
    }
]

@pytest.fixture(autouse=True)
def setup_mocks():
    with patch("monitor_ui.routers.prompts._AGENTS_AVAILABLE", True), \
         patch("monitor_ui.routers.prompts._REGISTRY", DUMMY_REGISTRY), \
         patch("monitor_ui.routers.prompts.get_postgres_client") as mock_get_pg:
        mock_pg = MagicMock()
        mock_pg.config_get = AsyncMock()
        mock_pg.config_set = AsyncMock()
        mock_get_pg.return_value = mock_pg
        yield mock_pg

def test_agents_status():
    response = client.get("/api/prompts/status")
    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["module_count"] == 1

def test_list_modules(setup_mocks):
    mock_pg = setup_mocks
    mock_pg.config_get.return_value = '{"instructions": "custom"}'
    
    response = client.get("/api/prompts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["module_id"] == "test.dummy"
    assert data[0]["has_override"] is True

def test_get_module(setup_mocks):
    mock_pg = setup_mocks
    mock_pg.config_get.return_value = '{"instructions": "custom"}'
    
    response = client.get("/api/prompts/test.dummy")
    assert response.status_code == 200
    data = response.json()
    assert data["module_id"] == "test.dummy"
    assert data["has_override"] is True
    assert data["current_instructions"] == "custom"
    assert data["default_instructions"] == "Test instruction."
    assert len(data["input_fields"]) == 1
    assert data["input_fields"][0]["name"] == "input_text"

def test_get_module_not_found(setup_mocks):
    response = client.get("/api/prompts/invalid.module")
    assert response.status_code == 404

def test_update_module_instructions(setup_mocks):
    mock_pg = setup_mocks
    mock_pg.config_get.return_value = None
    
    response = client.put("/api/prompts/test.dummy", json={"instructions": "new instructions"})
    assert response.status_code == 200
    mock_pg.config_set.assert_called_once()
    
    # Test reset
    mock_pg.config_set.reset_mock()
    response = client.put("/api/prompts/test.dummy", json={"instructions": "Test instruction."})
    assert response.status_code == 200
    mock_pg.config_set.assert_called_once_with("prompt_override:test.dummy", "{}")

def test_reset_module_instructions(setup_mocks):
    mock_pg = setup_mocks
    response = client.delete("/api/prompts/test.dummy/overrides")
    assert response.status_code == 204
    mock_pg.config_set.assert_called_once_with("prompt_override:test.dummy", "{}")

def test_test_module(setup_mocks):
    mock_pg = setup_mocks
    mock_pg.config_get.return_value = None
    
    class MockLM:
        def __init__(self):
            self.history = [{"messages": [{"role": "user", "content": "prompt text"}], "response": "resp text"}]
        def __call__(self, *args, **kwargs):
            return ["dummy_completion"]
    
    with patch("monitor_ui.routers.prompts.get_dspy_lm", return_value=MockLM()), \
         patch("dspy.Predict.__call__", return_value=MagicMock(output_text="test out")):
        response = client.post("/api/prompts/test.dummy/test", json={
            "inputs": {"input_text": "hello"},
            "use_override": True
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["outputs"]["output_text"] == "test out"
        assert "prompt text" in data["raw_prompt"]

def test_test_module_error(setup_mocks):
    mock_pg = setup_mocks
    mock_pg.config_get.return_value = None
    
    with patch("monitor_ui.routers.prompts.get_dspy_lm", side_effect=Exception("Test error")):
        response = client.post("/api/prompts/test.dummy/test", json={
            "inputs": {"input_text": "hello"}
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["error"] == "Test error"

def test_not_available():
    with patch("monitor_ui.routers.prompts._AGENTS_AVAILABLE", False):
        assert client.get("/api/prompts").json() == []
        assert client.get("/api/prompts/test.dummy").status_code == 503
        assert client.put("/api/prompts/test.dummy", json={"instructions": "x"}).status_code == 503
        assert client.delete("/api/prompts/test.dummy/overrides").status_code == 503
        assert client.post("/api/prompts/test.dummy/test", json={"inputs": {}}).status_code == 503
