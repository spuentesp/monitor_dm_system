"""Shared test helper: stub the semantic action router.

The hermetic unit env has no embedding provider. The retrieval layer's
single Embedder fail-loud raises ``EmbedderProviderError`` (no fake
vectors) — the gatekeeper design. So any test whose ``resolve_turn``
reaches the new semantic router MUST stub it, otherwise the turn
correctly blows up with the provider error.

The agents ``conftest.py`` installs :func:`default_router_response` as an
autouse default (action = ``STR`` at DC 12, hint = ``social``); individual
tests wrap their call in :func:`force_action_routing(...)`` to override.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any
from unittest.mock import patch


async def _default_infer(sd, user_input, source_profile=None):
    return {
        "action_type": "action",
        "stat_name": "STR",
        "difficulty_class": 12,
        "subsystem_hint": "social",
    }


DEFAULT_RESPONSE: dict[str, Any] = {
    "action_type": "action",
    "stat_name": "STR",
    "difficulty_class": 12,
    "subsystem_hint": "social",
}


@contextmanager
def force_action_routing(response: dict[str, Any] | None = None):
    """Patch the resolver's semantic router to a fixed response.

    Defaults to :data:`DEFAULT_RESPONSE` (``action`` at ``STR`` DC 12).
    Real router accuracy is validated against live embeddings by
    ``scripts/router_eval.py`` (TODO).
    """
    payload = response if response is not None else DEFAULT_RESPONSE

    class _Stub:
        async def infer_action_context(self, sd, user_input, source_profile=None):
            return payload

    with patch(
        "monitor_agents.game_system._action_routing.infer_action_context",
        _Stub().infer_action_context,
    ):
        yield
