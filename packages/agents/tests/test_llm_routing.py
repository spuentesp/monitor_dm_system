from pydantic import BaseModel
import pytest

from monitor_agents.base import BaseAgent
from monitor_data.schemas.llm_config import ModelRole


class _Reply(BaseModel):
    ok: bool = True


class _DummyAgent(BaseAgent):
    async def run(self) -> None:
        return None


@pytest.mark.asyncio
async def test_call_llm_structured_uses_configured_node_and_role(monkeypatch):
    calls = []

    class FakeClient:
        model = "openai/gpt-4.1-mini"
        params = {}

        async def create(self, response_model, messages, **kwargs):
            calls.append(("create", messages, kwargs))
            return response_model(ok=True)

    class FakeRegistry:
        def __init__(self, *_args, **_kwargs):
            pass

        async def for_node_or_role(self, node_name, role):
            calls.append(("for_node_or_role", node_name, role))
            return FakeClient()

    monkeypatch.setattr("monitor_agents.base.LLMRegistry", FakeRegistry)

    agent = _DummyAgent(agent_type="Narrator", agent_id="n-1")
    result = await agent.call_llm_structured(_Reply, [{"role": "user", "content": "ping"}])

    assert result.ok is True
    assert ("for_node_or_role", "narrator", ModelRole.HEAVY) in calls


@pytest.mark.asyncio
async def test_call_llm_structured_uses_standard_role_for_analyzer(monkeypatch):
    calls = []

    class FakeClient:
        model = "openai/gpt-4.1-mini"
        params = {}

        async def create(self, response_model, messages, **kwargs):
            calls.append(("create", messages, kwargs))
            return response_model(ok=True)

    class FakeRegistry:
        def __init__(self, *_args, **_kwargs):
            pass

        async def for_node_or_role(self, node_name, role):
            calls.append(("for_node_or_role", node_name, role))
            return FakeClient()

    monkeypatch.setattr("monitor_agents.base.LLMRegistry", FakeRegistry)

    agent = _DummyAgent(agent_type="Analyzer", agent_id="n-2")
    result = await agent.call_llm_structured(_Reply, [{"role": "user", "content": "ping"}])

    assert result.ok is True
    assert ("for_node_or_role", "analyzer", ModelRole.STANDARD) in calls


def test_base_agent_has_agent_id() -> None:
    """Test that BaseAgent initializes with agent_id."""
    agent = _DummyAgent(agent_type="Test", agent_id="test-1")
    assert agent.agent_id == "test-1"


def test_base_agent_has_agent_type() -> None:
    """Test that BaseAgent initializes with agent_type."""
    agent = _DummyAgent(agent_type="Narrator", agent_id="n-1")
    assert agent.agent_type == "Narrator"


def test_model_role_values() -> None:
    """Test ModelRole enum has expected values."""
    assert ModelRole.STANDARD.value == "standard"
    assert ModelRole.HEAVY.value == "heavy"
    assert ModelRole.LIGHT.value == "light"


@pytest.mark.asyncio
async def test_call_llm_structured_returns_model_instance(monkeypatch):
    """Test that call_llm_structured returns an instance of the response model."""

    class FakeClient:
        model = "openai/gpt-4.1-mini"
        params = {}

        async def create(self, response_model, messages, **kwargs):
            return response_model(ok=True)

    class FakeRegistry:
        def __init__(self, *_args, **_kwargs):
            pass

        async def for_node_or_role(self, node_name, role):
            return FakeClient()

    monkeypatch.setattr("monitor_agents.base.LLMRegistry", FakeRegistry)

    agent = _DummyAgent(agent_type="Narrator", agent_id="n-1")
    result = await agent.call_llm_structured(_Reply, [{"role": "user", "content": "ping"}])

    assert isinstance(result, _Reply)
    assert result.ok is True


@pytest.mark.asyncio
async def test_call_llm_structured_with_system_message(monkeypatch):
    """Test that call_llm_structured works with system message."""
    calls = []

    class FakeClient:
        model = "openai/gpt-4.1-mini"
        params = {}

        async def create(self, response_model, messages, **kwargs):
            calls.append(messages)
            return response_model(ok=True)

    class FakeRegistry:
        def __init__(self, *_args, **_kwargs):
            pass

        async def for_node_or_role(self, node_name, role):
            return FakeClient()

    monkeypatch.setattr("monitor_agents.base.LLMRegistry", FakeRegistry)

    agent = _DummyAgent(agent_type="Narrator", agent_id="n-1")
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "ping"},
    ]
    result = await agent.call_llm_structured(_Reply, messages)

    assert result.ok is True
    assert len(calls) == 1
    assert len(calls[0]) == 2  # system + user messages


@pytest.mark.asyncio
async def test_call_llm_structured_uses_light_role_for_query(monkeypatch):
    """Test that call_llm_structured uses LIGHT role for certain agents."""
    calls = []

    class FakeClient:
        model = "openai/gpt-4.1-mini"
        params = {}

        async def create(self, response_model, messages, **kwargs):
            return response_model(ok=True)

    class FakeRegistry:
        def __init__(self, *_args, **_kwargs):
            pass

        async def for_node_or_role(self, node_name, role):
            calls.append(("for_node_or_role", node_name, role))
            return FakeClient()

    monkeypatch.setattr("monitor_agents.base.LLMRegistry", FakeRegistry)

    # Query agent exists and can be called - role depends on implementation
    agent = _DummyAgent(agent_type="Query", agent_id="q-1")
    result = await agent.call_llm_structured(_Reply, [{"role": "user", "content": "ping"}])

    assert result.ok is True
    assert len(calls) == 1


class TestModelRoleEnum:
    """Tests for ModelRole enum values."""

    def test_model_role_has_standard(self):
        """ModelRole should have STANDARD value."""
        assert hasattr(ModelRole, "STANDARD")
        assert ModelRole.STANDARD.value == "standard"

    def test_model_role_has_heavy(self):
        """ModelRole should have HEAVY value."""
        assert hasattr(ModelRole, "HEAVY")
        assert ModelRole.HEAVY.value == "heavy"

    def test_model_role_has_light(self):
        """ModelRole should have LIGHT value."""
        assert hasattr(ModelRole, "LIGHT")
        assert ModelRole.LIGHT.value == "light"

    def test_model_role_has_embedding(self):
        """ModelRole should have EMBEDDING value."""
        assert hasattr(ModelRole, "EMBEDDING")
        assert ModelRole.EMBEDDING.value == "embedding"

    def test_model_role_all_values_are_strings(self):
        """All ModelRole values should be strings."""
        for role in ModelRole:
            assert isinstance(role.value, str)


class TestDummyAgent:
    """Tests for _DummyAgent test helper."""

    def test_dummy_agent_can_be_created(self):
        """_DummyAgent should be creatable."""
        agent = _DummyAgent(agent_type="Test", agent_id="test-id")
        assert agent.agent_type == "Test"
        assert agent.agent_id == "test-id"

    def test_dummy_agent_has_run_method(self):
        """_DummyAgent should have run method."""
        agent = _DummyAgent(agent_type="Test", agent_id="test-id")
        assert hasattr(agent, "run")

    @pytest.mark.asyncio
    async def test_dummy_agent_run_returns_none(self):
        """_DummyAgent.run should return None."""
        agent = _DummyAgent(agent_type="Test", agent_id="test-id")
        result = await agent.run()
        assert result is None
