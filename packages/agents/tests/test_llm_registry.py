"""
Tests for the LLMRegistry — provider resolution and client construction.

Covers:
- for_node: explicit assignment → default fallback
- for_role: role-based ranking with priority logic
- for_node_or_role: node-first, role-fallback
- default_client: is_default provider lookup
- _row_to_config: row → EffectiveLLMConfig conversion
- _is_provider_usable: status/api_key/provider-type checks
- _resolve_base_url: explicit → well-known fallback
- clear_cache: cache eviction
- prompt_version passthrough

Run:
    cd /path/to/monitor_dm_system && pytest packages/agents/tests/test_llm_registry.py -v
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from monitor_data.schemas.llm_config import (
    EffectiveLLMConfig,
    LLMProviderType,
    ModelRole,
)

from monitor_agents.llm_registry import LLMRegistry

pytestmark = pytest.mark.unit


# =============================================================================
# Helpers
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


def make_mock_postgres(
    effective_llm_for_node_ret: dict | None = None,
    providers_list_ret: list[dict] | None = None,
    node_assignment_get_ret: dict | None = None,
) -> MagicMock:
    pg = MagicMock()
    pg.effective_llm_for_node = AsyncMock(return_value=effective_llm_for_node_ret)
    pg.providers_list = AsyncMock(return_value=providers_list_ret or [])
    pg.node_assignment_get = AsyncMock(return_value=node_assignment_get_ret)
    return pg


# =============================================================================
# _row_to_config
# =============================================================================


class TestRowToConfig:
    def test_converts_full_row(self):
        row = make_provider_row(
            model_params={"temperature": 0.7, "max_tokens": 4096},
            prompt_version="v2",
        )
        row["effective_params"] = row["model_params"]

        config = LLMRegistry._row_to_config(row, node_name="narrator")

        assert config.id == "test-provider"
        assert config.provider == LLMProviderType.OPENAI
        assert config.model == "gpt-4o-mini"
        assert config.api_key == "test-key"
        assert config.role == ModelRole.STANDARD
        assert config.node_name == "narrator"
        assert config.prompt_version == "v2"
        assert config.effective_params["temperature"] == 0.7

    def test_parses_string_params(self):
        row = make_provider_row()
        row["effective_params"] = '{"temperature": 0.5}'

        config = LLMRegistry._row_to_config(row)

        assert config.effective_params["temperature"] == 0.5

    def test_handles_invalid_string_params(self):
        row = make_provider_row()
        row["effective_params"] = "not json"

        config = LLMRegistry._row_to_config(row)

        assert config.effective_params == {}

    def test_handles_non_dict_params(self):
        row = make_provider_row()
        row["effective_params"] = ["not", "a", "dict"]

        config = LLMRegistry._row_to_config(row)

        assert config.effective_params == {}

    def test_defaults_missing_fields(self):
        row = {"id": "p1", "name": "P1", "provider": "anthropic", "model": "claude-3"}

        config = LLMRegistry._row_to_config(row)

        assert config.api_key == ""
        assert config.base_url is None
        assert config.role == ModelRole.STANDARD
        assert config.prompt_version is None


# =============================================================================
# _is_provider_usable
# =============================================================================


class TestIsProviderUsable:
    def test_error_status_is_unusable(self):
        config = EffectiveLLMConfig(id="p", name="P", provider=LLMProviderType.OPENAI, model="m", api_key="key")
        assert LLMRegistry._is_provider_usable(config, "error") is False

    def test_ollama_always_usable(self):
        config = EffectiveLLMConfig(id="p", name="P", provider=LLMProviderType.OLLAMA, model="m", api_key="")
        assert LLMRegistry._is_provider_usable(config, "") is True

    def test_custom_always_usable(self):
        config = EffectiveLLMConfig(id="p", name="P", provider=LLMProviderType.CUSTOM, model="m", api_key="")
        assert LLMRegistry._is_provider_usable(config, "") is True

    def test_connected_is_usable(self):
        config = EffectiveLLMConfig(id="p", name="P", provider=LLMProviderType.OPENAI, model="m", api_key="")
        assert LLMRegistry._is_provider_usable(config, "connected") is True

    def test_no_key_no_status_is_unusable(self):
        config = EffectiveLLMConfig(id="p", name="P", provider=LLMProviderType.OPENAI, model="m", api_key="")
        assert LLMRegistry._is_provider_usable(config, "") is False

    def test_with_key_is_usable(self):
        config = EffectiveLLMConfig(id="p", name="P", provider=LLMProviderType.OPENAI, model="m", api_key="sk-xxx")
        assert LLMRegistry._is_provider_usable(config, "") is True


# =============================================================================
# for_node
# =============================================================================


class TestForNode:
    @pytest.mark.asyncio
    async def test_resolves_explicit_assignment(self):
        row = make_provider_row(id="narrator-prov", model="claude-3-opus", is_default=False)
        row["effective_params"] = {"temperature": 0.9, "max_tokens": 8192}
        pg = make_mock_postgres(effective_llm_for_node_ret=row)

        registry = LLMRegistry(pg)
        client = await registry.for_node("narrator")

        assert client.model == "claude-3-opus"
        assert client.params["temperature"] == 0.9
        pg.effective_llm_for_node.assert_called_once_with("narrator")

    @pytest.mark.asyncio
    async def test_caches_result(self):
        row = make_provider_row()
        row["effective_params"] = {}
        pg = make_mock_postgres(effective_llm_for_node_ret=row)

        registry = LLMRegistry(pg)
        c1 = await registry.for_node("narrator")
        c2 = await registry.for_node("narrator")

        assert c1 is c2  # same cached object
        pg.effective_llm_for_node.assert_called_once()

    @pytest.mark.asyncio
    async def test_prompt_version_passthrough(self):
        row = make_provider_row(prompt_version="narrator-v3")
        row["effective_params"] = {}
        pg = make_mock_postgres(effective_llm_for_node_ret=row)

        registry = LLMRegistry(pg)
        client = await registry.for_node("narrator")

        assert client.prompt_version == "narrator-v3"


# =============================================================================
# for_role
# =============================================================================


class TestForRole:
    @pytest.mark.asyncio
    async def test_prefers_role_match_connected_default(self):
        rows = [
            make_provider_row(id="light", role="light", status="connected", is_default=True),
            make_provider_row(id="heavy", role="heavy", status="connected"),
        ]
        for r in rows:
            r["effective_params"] = {}
        pg = make_mock_postgres(providers_list_ret=rows)

        registry = LLMRegistry(pg)
        client = await registry.for_role(ModelRole.LIGHT)

        assert client.model == "gpt-4o-mini"  # from the light provider

    @pytest.mark.asyncio
    async def test_falls_back_to_default_when_no_role_match(self):
        rows = [
            make_provider_row(id="heavy-only", role="heavy", status="connected"),
            make_provider_row(id="default", role="standard", status="connected", is_default=True),
        ]
        for r in rows:
            r["effective_params"] = {}
        pg = make_mock_postgres(providers_list_ret=rows)

        registry = LLMRegistry(pg)
        client = await registry.for_role(ModelRole.LIGHT)

        # Should fall back to default (priority 3)
        assert client is not None

    @pytest.mark.asyncio
    async def test_raises_when_no_usable_provider(self):
        rows = [
            make_provider_row(id="broken", status="error"),
        ]
        pg = make_mock_postgres(providers_list_ret=rows)

        registry = LLMRegistry(pg)
        with pytest.raises(ValueError, match="No usable LLM provider"):
            await registry.for_role(ModelRole.LIGHT)

    @pytest.mark.asyncio
    async def test_caches_role_lookup(self):
        rows = [make_provider_row(role="light", status="connected")]
        rows[0]["effective_params"] = {}
        pg = make_mock_postgres(providers_list_ret=rows)

        registry = LLMRegistry(pg)
        c1 = await registry.for_role(ModelRole.LIGHT)
        c2 = await registry.for_role(ModelRole.LIGHT)

        assert c1 is c2
        pg.providers_list.assert_called_once()


# =============================================================================
# for_node_or_role
# =============================================================================


class TestForNodeOrRole:
    @pytest.mark.asyncio
    async def test_uses_node_when_assignment_exists(self):
        row = make_provider_row(id="node-prov")
        row["effective_params"] = {}
        pg = make_mock_postgres(
            effective_llm_for_node_ret=row,
            node_assignment_get_ret={"provider_id": "node-prov"},
        )

        registry = LLMRegistry(pg)
        client = await registry.for_node_or_role("narrator", ModelRole.HEAVY)

        assert client is not None
        pg.node_assignment_get.assert_called_once_with("narrator")

    @pytest.mark.asyncio
    async def test_falls_back_to_role_when_no_assignment(self):
        rows = [make_provider_row(id="role-prov", role="heavy", status="connected")]
        rows[0]["effective_params"] = {}
        pg = make_mock_postgres(
            providers_list_ret=rows,
            node_assignment_get_ret=None,
        )

        registry = LLMRegistry(pg)
        client = await registry.for_node_or_role("narrator", ModelRole.HEAVY)

        assert client is not None


# =============================================================================
# default_client
# =============================================================================


class TestDefaultClient:
    @pytest.mark.asyncio
    async def test_returns_default_provider(self):
        rows = [
            make_provider_row(id="non-default", is_default=False),
            make_provider_row(id="default-prov", is_default=True, status="connected"),
        ]
        for r in rows:
            r["effective_params"] = {}
        pg = make_mock_postgres(providers_list_ret=rows)

        registry = LLMRegistry(pg)
        client = await registry.default_client()

        assert client is not None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_default(self):
        rows = [make_provider_row(is_default=False)]
        pg = make_mock_postgres(providers_list_ret=rows)

        registry = LLMRegistry(pg)
        client = await registry.default_client()

        assert client is None

    @pytest.mark.asyncio
    async def test_returns_none_when_default_has_error_status(self):
        rows = [make_provider_row(is_default=True, status="error")]
        pg = make_mock_postgres(providers_list_ret=rows)

        registry = LLMRegistry(pg)
        client = await registry.default_client()

        assert client is None


# =============================================================================
# clear_cache
# =============================================================================


class TestClearCache:
    @pytest.mark.asyncio
    async def test_clear_cache_forces_re_resolution(self):
        row = make_provider_row()
        row["effective_params"] = {}
        pg = make_mock_postgres(effective_llm_for_node_ret=row)

        registry = LLMRegistry(pg)
        await registry.for_node("narrator")
        assert len(registry._cache) == 1

        registry.clear_cache()
        assert len(registry._cache) == 0

        await registry.for_node("narrator")
        assert pg.effective_llm_for_node.call_count == 2
