"""
Pytest configuration for MONITOR Agents layer tests.

The hermetic environment (fake API keys, unroutable DB URIs, socket blocking)
is enforced by the repo-root conftest.py. This file adds agents-specific
isolation: global singletons are reset between tests so test order can never
change behavior.
"""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_env():
    """Set minimum env vars so pydantic-settings Settings can instantiate.

    setdefault only — the repo-root conftest already forced hermetic values
    for unit runs; these are a fallback for direct invocations.
    """
    os.environ.setdefault("NEO4J_PASSWORD", "test_password")
    os.environ.setdefault("MINIO_SECRET_KEY", "test_secret")
    os.environ.setdefault("POSTGRES_PASSWORD", "test_password")
    os.environ.setdefault("ANTHROPIC_API_KEY", "test_key")
    os.environ.setdefault("MONGODB_URI", "mongodb://127.0.0.1:1")
    os.environ.setdefault("NEO4J_URI", "bolt://127.0.0.1:1")


@pytest.fixture(autouse=True)
def isolate_agent_globals():
    """Reset process-wide agent state around every test (ordering-flake guard)."""
    from monitor_agents.agent_factory import reset_agent_factory

    reset_agent_factory()
    yield
    reset_agent_factory()
