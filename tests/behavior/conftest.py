"""Fixtures for the behavior tests.

The hermetic stack is the workhorse: it runs the *real* data-layer tools
against fake databases so a behavior test exercises the shipped path rather
than a stack of doubles.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.behavior._hermetic_stack import HermeticStack


@pytest.fixture
def hermetic(monkeypatch: pytest.MonkeyPatch) -> Iterator[HermeticStack]:
    """A hermetic stack: real MCP tool path over mongomock Mongo."""
    stack = HermeticStack()
    stack.install(monkeypatch)
    try:
        yield stack
    finally:
        stack.uninstall()
