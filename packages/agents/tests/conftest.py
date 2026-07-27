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
    from monitor_agents.gm_tools.registry import reset_loop_bridge

    reset_agent_factory()
    # A GMAgent decide() may install a live loop bridge; if a test crashes
    # before its own teardown, that bridge (bound to a now-dead loop) leaks
    # into later tests. Reset it unconditionally around every test.
    reset_loop_bridge()
    yield
    reset_agent_factory()
    reset_loop_bridge()


@pytest.fixture(autouse=True)
def default_roll_classifier_stub():
    """Stub both semantic classifiers to fixed responses for every agents test.

    The hermetic env has no embeddings provider and ``embed_text`` now raises
    by design (fail loud, never fake). Any ``resolve_turn`` that reaches the
    roll classifier OR the semantic action router would otherwise crash with
    ``EmbeddingProviderError``. Most dice tests just need to reach the roll
    path, so the defaults are ``contested`` for dice and a neutral action
    profile (``STR``/DC 12 / ``social``) for routing; tests asserting a
    different behavior wrap their call in ``force_roll_necessity(...)`` (from
    ``_roll_helpers``) or ``force_action_routing(...)`` (from
    ``_router_helpers``), which re-patch on top of this fixture.
    """
    from _roll_helpers import force_roll_necessity
    from _router_helpers import force_action_routing

    with force_roll_necessity("contested"), force_action_routing():
        yield


@pytest.fixture
def stub_document_lookups(monkeypatch):
    """Stub mongodb document lookups (filename + content-hash) to None by default.

    IngestionPipeline calls both lookups before any test can predict what
    Mongo would return. Returning ``None`` from both means "no existing
    document", which is the most common test scenario. Tests that need a
    specific lookup result re-patch on top of this fixture.
    """
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_find_document_by_filename",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "monitor_agents.ingestion.agent.mongodb_find_document_by_content_hash",
        lambda *_args, **_kwargs: None,
    )
    yield monkeypatch
