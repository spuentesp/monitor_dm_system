"""
Repo-root pytest configuration — HERMETIC TEST GUARD.

Loaded before every test conftest in both `packages/*/tests` and `tests/`.
Two jobs:

1. **Environment isolation.** Unit tests must never see real API keys or real
   database URIs (a real `.env` exists in dev checkouts and pydantic-settings
   reads it). We force fake values *before* any `monitor_data` import so the
   `Settings` singleton is born harmless. Integration/E2E runs (RUN_INTEGRATION
   / RUN_E2E) skip the override so real services can be reached.

2. **Network isolation.** Unit tests get their sockets disabled
   (pytest-socket); tests marked `integration`/`e2e` keep network access.
   Unix sockets stay allowed (asyncio event loops need socketpair()).

This is what turns "the full suite hangs for hours on LLM/DB retries" into
"misbehaving tests fail in milliseconds".
"""

from __future__ import annotations

import os

import pytest
from pytest_socket import disable_socket, enable_socket

_INTEGRATION_MODE = bool(os.getenv("RUN_INTEGRATION") or os.getenv("RUN_E2E"))

# ---------------------------------------------------------------------------
# 1. Environment isolation (must happen at import time, before test modules
#    import monitor_data and materialize the Settings singleton)
# ---------------------------------------------------------------------------
_HERMETIC_ENV = {
    # LLM providers — fake keys so no client can authenticate anywhere, and
    # unroutable base URLs so even socket-block escapes (e.g. litellm's aiodns
    # path) can't reach a real provider
    "ANTHROPIC_API_KEY": "test-anthropic-key",
    "OPENAI_API_KEY": "test-openai-key",
    "GOOGLE_API_KEY": "test-google-key",
    "GITHUB_MODELS_TOKEN": "test-github-token",
    "OPENAI_BASE_URL": "http://127.0.0.1:1",
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:1",
    # Databases — unroutable ports so accidental dials fail instantly
    "MONGODB_URI": "mongodb://127.0.0.1:1/monitor_test?serverSelectionTimeoutMS=100",
    "NEO4J_URI": "bolt://127.0.0.1:1",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "test-password",
    "QDRANT_URI": "http://127.0.0.1:1",
    "QDRANT_URL": "http://127.0.0.1:1",
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PORT": "1",
    "POSTGRES_PASSWORD": "test-password",
    "MINIO_ENDPOINT": "127.0.0.1:1",
    "MINIO_ACCESS_KEY": "test-access",
    "MINIO_SECRET_KEY": "test-secret",
    "OPENSEARCH_URI": "http://127.0.0.1:1",
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "REDIS_ENABLED": "false",
    # Keep unit tests off optional services
    "NLP_ENABLED": "false",
    "LOGFIRE_SEND_TO_LOGFIRE": "false",
    # Bound the sync→async DB bridge tightly so stalls surface as errors well
    # before the per-test timeout kills the whole process
    "DB_SYNC_TIMEOUT": "15",
}

if not _INTEGRATION_MODE:
    os.environ.update(_HERMETIC_ENV)


# ---------------------------------------------------------------------------
# 2. Network isolation per test
# ---------------------------------------------------------------------------
def _wants_network(item: pytest.Item) -> bool:
    return "integration" in item.keywords or "e2e" in item.keywords


def pytest_runtest_setup(item: pytest.Item) -> None:
    # Honor the gating promised by the marker docs (pytest.ini): integration/e2e
    # tests hit real services, so skip them unless their env flag is set.
    # Without this they run against the unroutable hermetic URIs above and fail
    # with a DB/connection timeout instead of skipping cleanly.
    if "e2e" in item.keywords and not os.getenv("RUN_E2E"):
        pytest.skip("e2e test — set RUN_E2E=1 to run")
    if "integration" in item.keywords and not _INTEGRATION_MODE:
        pytest.skip("integration test — set RUN_INTEGRATION=1 (or RUN_E2E=1) to run")

    if _INTEGRATION_MODE or _wants_network(item):
        enable_socket()
    else:
        disable_socket(allow_unix_socket=True)


def pytest_runtest_teardown(item: pytest.Item) -> None:
    # Leave the process usable for whatever runs after the suite.
    enable_socket()
