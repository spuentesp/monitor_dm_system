"""
Fake PostgreSQL client for unit tests.

Mirrors the async interface of monitor_data.db.postgres.PostgresClient.
Uses an in-memory dict to store table rows, supporting the SQL query
patterns used by MONITOR's LLM provider config and settings.

Usage::

    from tests.mocks.db.postgres import FakePostgresClient

    pg = FakePostgresClient()
    pg.seed_providers([
        {"id": "openai-1", "name": "OpenAI", "provider": "openai", "model": "gpt-4o", ...},
    ])
    rows = await pg.providers_list()
"""

from __future__ import annotations

from typing import Any


class FakePostgresClient:
    """In-memory PostgreSQL client for unit tests.

    Stores rows as dicts keyed by table name. Supports the async methods
    used by LLMRegistry and the settings system.
    """

    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {
            "llm_providers": [],
            "llm_node_assignments": [],
            "system_config": [],
            "worlds": [],
            "connection_settings": [],
        }
        self._pool = MagicMock()

    # ------------------------------------------------------------------
    # Seeding helpers
    # ------------------------------------------------------------------

    def seed_providers(self, providers: list[dict[str, Any]]) -> None:
        """Seed the llm_providers table."""
        self._tables["llm_providers"] = list(providers)

    def seed_node_assignments(self, assignments: list[dict[str, Any]]) -> None:
        """Seed the llm_node_assignments table."""
        self._tables["llm_node_assignments"] = list(assignments)

    def add_provider(self, **fields: Any) -> dict[str, Any]:
        """Add a single provider row."""
        row = {
            "id": fields.get("id", "test-provider"),
            "name": fields.get("name", "Test Provider"),
            "provider": fields.get("provider", "openai"),
            "model": fields.get("model", "gpt-4o-mini"),
            "api_key": fields.get("api_key", "test-key"),
            "base_url": fields.get("base_url"),
            "model_params": fields.get("model_params", {}),
            "role": fields.get("role", "standard"),
            "status": fields.get("status", "connected"),
            "is_default": fields.get("is_default", False),
            "prompt_version": fields.get("prompt_version"),
        }
        self._tables["llm_providers"].append(row)
        return row

    def add_node_assignment(
        self, node_name: str, provider_id: str, **overrides: Any
    ) -> dict[str, Any]:
        """Add a node → provider assignment."""
        row = {
            "node_name": node_name,
            "provider_id": provider_id,
            "param_overrides": overrides.get("param_overrides", {}),
            "prompt_version": overrides.get("prompt_version"),
        }
        self._tables["llm_node_assignments"].append(row)
        return row

    # ------------------------------------------------------------------
    # Async API (mirrors PostgresClient)
    # ------------------------------------------------------------------

    async def _get_pool(self) -> Any:
        return self._pool

    async def providers_list(self) -> list[dict[str, Any]]:
        """Return all provider rows."""
        return list(self._tables["llm_providers"])

    async def effective_llm_for_node(self, node_name: str) -> dict[str, Any]:
        """Return the effective LLM config for a node.

        Merges provider params with node overrides, falling back to default.
        """
        # Check for explicit assignment
        for assignment in self._tables["llm_node_assignments"]:
            if assignment["node_name"] == node_name:
                provider_id = assignment["provider_id"]
                for provider in self._tables["llm_providers"]:
                    if provider["id"] == provider_id:
                        merged = dict(provider)
                        merged["param_overrides"] = assignment.get(
                            "param_overrides", {}
                        )
                        merged["prompt_version"] = assignment.get("prompt_version")
                        params = {
                            **(merged.get("model_params") or {}),
                            **(merged.get("param_overrides") or {}),
                        }
                        merged["effective_params"] = params
                        return merged
                raise ValueError(
                    f"Provider '{provider_id}' not found for node '{node_name}'"
                )

        # Fall back to default provider
        for provider in self._tables["llm_providers"]:
            if provider.get("is_default"):
                merged = dict(provider)
                merged["effective_params"] = merged.get("model_params", {})
                return merged

        raise ValueError(
            f"No LLM provider configured (no assignment for '{node_name}' and no default)"
        )

    async def node_assignment_get(self, node_name: str) -> dict[str, Any] | None:
        """Return the node assignment if it exists."""
        for assignment in self._tables["llm_node_assignments"]:
            if assignment["node_name"] == node_name:
                return assignment
        return None

    async def provider_get(self, provider_id: str) -> dict[str, Any] | None:
        """Return a single provider by ID."""
        for provider in self._tables["llm_providers"]:
            if provider["id"] == provider_id:
                return provider
        return None

    async def provider_upsert(self, provider: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a provider."""
        for i, existing in enumerate(self._tables["llm_providers"]):
            if existing["id"] == provider["id"]:
                self._tables["llm_providers"][i] = provider
                return provider
        self._tables["llm_providers"].append(provider)
        return provider

    async def node_assignment_upsert(
        self, assignment: dict[str, Any]
    ) -> dict[str, Any]:
        """Insert or update a node assignment."""
        for i, existing in enumerate(self._tables["llm_node_assignments"]):
            if existing["node_name"] == assignment["node_name"]:
                self._tables["llm_node_assignments"][i] = assignment
                return assignment
        self._tables["llm_node_assignments"].append(assignment)
        return assignment

    async def setting_get(self, key: str) -> str | None:
        """Get a system config value."""
        for row in self._tables["system_config"]:
            if row.get("key") == key:
                return row.get("value")
        return None

    async def setting_set(self, key: str, value: str) -> None:
        """Set a system config value."""
        for row in self._tables["system_config"]:
            if row.get("key") == key:
                row["value"] = value
                return
        self._tables["system_config"].append({"key": key, "value": value})

    def reset(self) -> None:
        """Clear all tables."""
        for table in self._tables.values():
            table.clear()


def make_mock_postgres_client() -> FakePostgresClient:
    """Return a FakePostgresClient with a default provider pre-seeded."""
    pg = FakePostgresClient()
    pg.add_provider(
        id="default-openai",
        name="Default OpenAI",
        provider="openai",
        model="gpt-4o-mini",
        api_key="test-key",
        model_params={"temperature": 0.7, "max_tokens": 4096},
        role="standard",
        status="connected",
        is_default=True,
    )
    return pg


from unittest.mock import MagicMock
