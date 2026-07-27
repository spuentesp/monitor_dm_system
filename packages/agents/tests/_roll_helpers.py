"""Shared test helper: pin the resolver's roll-necessity outcome.

Since the GMAgent is the roll authority (it emits ``roll_necessity`` directly)
and the standalone roll classifier was deleted, the resolver's only remaining
roll-necessity source in hermetic tests is its fallback
(``_fallback_roll_necessity``) — reached when the GM verdict isn't real, which
is the default in the hermetic env (no LLM, no embeddings).

``force_roll_necessity`` patches that fallback so tests can pin the resolution
outcome (trivial / propose_roll / contested) without an LLM.

The agents ``conftest.py`` installs :func:`force_roll_necessity` as an autouse
default (``contested``); individual tests wrap their call to assert a different
resolution.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def force_roll_necessity(necessity: str):
    """Pin the resolver's roll-necessity fallback for the duration.

    ``necessity`` is one of ``trivial`` / ``propose_roll`` / ``contested``.
    Real GM roll decisions are exercised end-to-end by the live e2e harness.
    """
    with patch(
        "monitor_agents.resolver._fallback_roll_necessity",
        return_value=necessity,
    ):
        yield
