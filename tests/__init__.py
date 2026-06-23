"""MONITOR test suite.

This module enables imports like `from tests.conftest import ...`.
"""

from tests.conftest import FakeMCPClient, FakeLLMClient

__all__ = ["FakeMCPClient", "FakeLLMClient"]