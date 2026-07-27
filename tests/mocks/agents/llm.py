"""
Fake LLM client, registry, and builder.

Replaces the 22+ inline FakeClient/FakeRegistry definitions in test_llm_routing.py
and other test files.

Usage::

    from tests.mocks.agents.llm import FakeLLMClientBuilder, FakeLLMRegistry

    # Build a client that returns a specific response
    client = FakeLLMClientBuilder().with_model("gpt-4o").with_response(ok=True).build()

    # Build a registry that returns specific clients per node
    registry = FakeLLMRegistry()
    registry.set_node_client("narrator", client)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Type, TypeVar

from monitor_data.schemas.llm_config import LLMProviderType, ModelRole
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# FakeLLMClient — mirrors LLMClient from llm_registry.py
# =============================================================================


@dataclass
class FakeLLMClient:
    """Fake LLM client that returns scripted responses.

    Mirrors the interface of monitor_agents.llm_registry.LLMClient.
    Supports create() (structured) and complete_text() (plain text).

    Attributes:
        model: Model name string.
        provider: LLMProviderType enum.
        params: Dict of sampling parameters (temperature, max_tokens, etc.).
        api_key: API key string.
        base_url: Optional base URL.
        prompt_version: Optional prompt version tag.
    """

    model: str = "fake/model"
    provider: LLMProviderType = LLMProviderType.OPENAI
    params: dict[str, Any] = field(default_factory=dict)
    api_key: str = ""
    base_url: str | None = None
    prompt_version: str | None = None

    # Internal state
    _create_responses: list[Any] = field(default_factory=list, repr=False)
    _complete_responses: list[str] = field(default_factory=list, repr=False)
    _create_side_effect: Any = field(default=None, repr=False)
    _call_count: int = field(default=0, repr=False)

    async def create(
        self,
        response_model: type[T],
        messages: list[dict[str, Any]],
        **override_params: Any,
    ) -> T:
        """Return a scripted response model instance."""
        self._call_count += 1
        if self._create_side_effect is not None:
            if callable(self._create_side_effect):
                return self._create_side_effect(
                    response_model, messages, **override_params
                )
            raise self._create_side_effect
        if self._create_responses:
            return self._create_responses.pop(0)
        # Default: instantiate the response model with defaults
        return response_model()

    async def complete_text(
        self,
        messages: list[dict[str, Any]],
        **override_params: Any,
    ) -> str:
        """Return a scripted text response."""
        if self._complete_responses:
            return self._complete_responses.pop(0)
        return "ok"


class FakeLLMClientBuilder:
    """Fluent builder for FakeLLMClient.

    Usage::

        client = (FakeLLMClientBuilder()
            .with_model("gpt-4o")
            .with_provider(LLMProviderType.OPENAI)
            .with_params(temperature=0.7, max_tokens=4096)
            .with_response(MyResponse(ok=True))
            .build())
    """

    def __init__(self) -> None:
        self._client = FakeLLMClient()

    def with_model(self, model: str) -> FakeLLMClientBuilder:
        self._client.model = model
        return self

    def with_provider(self, provider: LLMProviderType) -> FakeLLMClientBuilder:
        self._client.provider = provider
        return self

    def with_params(self, **params: Any) -> FakeLLMClientBuilder:
        self._client.params.update(params)
        return self

    def with_api_key(self, api_key: str) -> FakeLLMClientBuilder:
        self._client.api_key = api_key
        return self

    def with_base_url(self, base_url: str) -> FakeLLMClientBuilder:
        self._client.base_url = base_url
        return self

    def with_prompt_version(self, version: str) -> FakeLLMClientBuilder:
        self._client.prompt_version = version
        return self

    def with_response(self, response: Any) -> FakeLLMClientBuilder:
        """Add a response to the create() queue."""
        self._client._create_responses.append(response)
        return self

    def with_text_response(self, text: str) -> FakeLLMClientBuilder:
        """Add a response to the complete_text() queue."""
        self._client._complete_responses.append(text)
        return self

    def with_side_effect(self, exc: Exception) -> FakeLLMClientBuilder:
        """Make create() raise an exception."""
        self._client._create_side_effect = exc
        return self

    def build(self) -> FakeLLMClient:
        return self._client


# =============================================================================
# FakeLLMRegistry — mirrors LLMRegistry from llm_registry.py
# =============================================================================


class FakeLLMRegistry:
    """Fake LLM registry for unit tests.

    Mirrors the interface of monitor_agents.llm_registry.LLMRegistry.
    Returns pre-configured clients per node or role.

    Usage::

        registry = FakeLLMRegistry()
        registry.set_node_client("narrator", narrator_client)
        registry.set_role_client(ModelRole.LIGHT, light_client)
        registry.set_default_client(default_client)

        # In tests:
        client = await registry.for_node_or_role("narrator", ModelRole.HEAVY)
    """

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self._node_clients: dict[str, FakeLLMClient] = {}
        self._role_clients: dict[ModelRole, FakeLLMClient] = {}
        self._default_client: FakeLLMClient | None = None
        self._cache: dict[str, FakeLLMClient] = {}

    def set_node_client(self, node_name: str, client: FakeLLMClient) -> None:
        """Set the client for a specific node."""
        self._node_clients[node_name] = client

    def set_role_client(self, role: ModelRole, client: FakeLLMClient) -> None:
        """Set the client for a specific role."""
        self._role_clients[role] = client

    def set_default_client(self, client: FakeLLMClient | None) -> None:
        """Set the default fallback client."""
        self._default_client = client

    async def for_node(self, node_name: str) -> FakeLLMClient:
        """Return the client for a node, falling back to default."""
        if node_name in self._node_clients:
            return self._node_clients[node_name]
        if self._default_client is not None:
            return self._default_client
        raise ValueError(f"No client configured for node '{node_name}' and no default")

    async def for_role(self, role: ModelRole) -> FakeLLMClient:
        """Return the client for a role, falling back to default."""
        if role in self._role_clients:
            return self._role_clients[role]
        if self._default_client is not None:
            return self._default_client
        raise ValueError(f"No client configured for role '{role.value}' and no default")

    async def for_node_or_role(self, node_name: str, role: ModelRole) -> FakeLLMClient:
        """Use node assignment when present, otherwise fall back to role."""
        if node_name in self._node_clients:
            return self._node_clients[node_name]
        return await self.for_role(role)

    async def default_client(self) -> FakeLLMClient | None:
        """Return the default client."""
        return self._default_client

    def clear_cache(self) -> None:
        """Evict all cached clients."""
        self._cache.clear()


def make_mock_registry(
    default_model: str = "gpt-4o-mini",
    default_provider: LLMProviderType = LLMProviderType.OPENAI,
) -> FakeLLMRegistry:
    """Return a FakeLLMRegistry with a default client pre-configured."""
    registry = FakeLLMRegistry()
    client = (
        FakeLLMClientBuilder()
        .with_model(default_model)
        .with_provider(default_provider)
        .build()
    )
    registry.set_default_client(client)
    return registry
