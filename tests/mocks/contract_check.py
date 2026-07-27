"""
Contract check — verifies that fakes match real interfaces 1:1.

This test runs in CI and fails when a real class's public interface changes
but the corresponding fake hasn't been updated.

Run:
    pytest tests/mocks/contract_check.py -v
"""

from __future__ import annotations

import inspect

import pytest

# =============================================================================
# Pairs of (real_class, fake_class) to verify
# =============================================================================

CONTRACT_PAIRS: list[tuple[type, type, str]] = []


def _register(real: type, fake: type, name: str = "") -> None:
    CONTRACT_PAIRS.append((real, fake, name or f"{real.__name__} → {fake.__name__}"))


# Register pairs (imported lazily to avoid import errors in CI)
def _register_all() -> None:
    if CONTRACT_PAIRS:
        return

    # LLM client
    try:
        from monitor_agents.llm_registry import LLMClient

        from tests.mocks.agents.llm import FakeLLMClient

        _register(LLMClient, FakeLLMClient, "LLMClient")
    except ImportError:
        pass

    # LLM registry
    try:
        from monitor_agents.llm_registry import LLMRegistry

        from tests.mocks.agents.llm import FakeLLMRegistry

        _register(LLMRegistry, FakeLLMRegistry, "LLMRegistry")
    except ImportError:
        pass

    # MCP client
    try:
        from tests.conftest import FakeMCPClient as ConftestFakeMCPClient
        from tests.mocks.agents.mcp import FakeMCPClient

        # Verify the mocks package version matches conftest version
        _register(ConftestFakeMCPClient, FakeMCPClient, "MCPClient (conftest → mocks)")
    except ImportError:
        pass

    # DSPy
    try:
        from tests.conftest import (
            FakeDSPyLM as ConftestLM,
        )
        from tests.conftest import (
            FakeDSPyPrediction as ConftestPred,
        )
        from tests.mocks.agents.dspy import FakeDSPyLM, FakeDSPyPrediction

        _register(ConftestPred, FakeDSPyPrediction, "DSPyPrediction (conftest → mocks)")
        _register(ConftestLM, FakeDSPyLM, "DSPyLM (conftest → mocks)")
    except ImportError:
        pass


# =============================================================================
# Tests
# =============================================================================


class TestContractCompliance:
    """Verify that every fake has the same public methods as its real counterpart."""

    @classmethod
    def setup_class(cls) -> None:
        _register_all()

    def test_contract_pairs_registered(self):
        """At least some contract pairs should be registered."""
        _register_all()
        assert len(CONTRACT_PAIRS) > 0, "No contract pairs registered — check imports"

    def test_llm_client_contract(self):
        """FakeLLMClient must have all public methods of LLMClient."""
        try:
            from monitor_agents.llm_registry import LLMClient

            from tests.mocks.agents.llm import FakeLLMClient
        except ImportError:
            pytest.skip("LLMClient not importable")

        real_methods = {
            name
            for name, member in inspect.getmembers(
                LLMClient, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name, member in inspect.getmembers(
                FakeLLMClient, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        missing = real_methods - fake_methods
        assert not missing, f"FakeLLMClient missing methods: {missing}"

    def test_llm_registry_contract(self):
        """FakeLLMRegistry must have all public methods of LLMRegistry."""
        try:
            from monitor_agents.llm_registry import LLMRegistry

            from tests.mocks.agents.llm import FakeLLMRegistry
        except ImportError:
            pytest.skip("LLMRegistry not importable")

        real_methods = {
            name
            for name, member in inspect.getmembers(
                LLMRegistry, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name, member in inspect.getmembers(
                FakeLLMRegistry, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        missing = real_methods - fake_methods
        assert not missing, f"FakeLLMRegistry missing methods: {missing}"

    def test_mcp_client_contract(self):
        """FakeMCPClient in mocks must match conftest version."""
        try:
            from tests.conftest import FakeMCPClient as ConftestMCP
            from tests.mocks.agents.mcp import FakeMCPClient as MocksMCP
        except ImportError:
            pytest.skip("FakeMCPClient not importable")

        real_methods = {
            name
            for name, member in inspect.getmembers(
                ConftestMCP, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name, member in inspect.getmembers(
                MocksMCP, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        missing = real_methods - fake_methods
        assert not missing, f"MocksMCP missing methods: {missing}"

    def test_dspy_prediction_contract(self):
        """FakeDSPyPrediction in mocks must match conftest version."""
        try:
            from tests.conftest import FakeDSPyPrediction as ConftestPred
            from tests.mocks.agents.dspy import FakeDSPyPrediction as MocksPred
        except ImportError:
            pytest.skip("FakeDSPyPrediction not importable")

        real_methods = {
            name
            for name, member in inspect.getmembers(
                ConftestPred, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name, member in inspect.getmembers(
                MocksPred, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        missing = real_methods - fake_methods
        assert not missing, f"MocksPred missing methods: {missing}"

    def test_dspy_lm_contract(self):
        """FakeDSPyLM in mocks must match conftest version."""
        try:
            from tests.conftest import FakeDSPyLM as ConftestLM
            from tests.mocks.agents.dspy import FakeDSPyLM as MocksLM
        except ImportError:
            pytest.skip("FakeDSPyLM not importable")

        real_methods = {
            name
            for name, member in inspect.getmembers(
                ConftestLM, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        fake_methods = {
            name
            for name, member in inspect.getmembers(
                MocksLM, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        missing = real_methods - fake_methods
        assert not missing, f"MocksLM missing methods: {missing}"

    def test_postgres_client_contract(self):
        """FakePostgresClient must have key methods of PostgresClient."""
        try:
            from monitor_data.db.postgres import PostgresClient

            from tests.mocks.db.postgres import FakePostgresClient
        except ImportError:
            pytest.skip("PostgresClient not importable")

        # Check key methods that LLMRegistry uses
        key_methods = [
            "providers_list",
            "effective_llm_for_node",
            "node_assignment_get",
        ]
        for method in key_methods:
            assert hasattr(FakePostgresClient, method), (
                f"FakePostgresClient missing {method}"
            )
