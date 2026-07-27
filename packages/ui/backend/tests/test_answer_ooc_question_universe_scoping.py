"""Regression test: answer_ooc_question must never leak archetypes from a
different universe.

Live bug (2026-07-23): reproduced via the real production chat API
(POST /api/chat/{id}/send, driven by scripts/live_llm_gm_vs_player_test.py
against a freshly-created "Death in Space" universe). The archetype-lookup
Cypher query used "e.universe_id = $uid OR 1=1" -- an always-true
tautology that returned character archetypes from ANY universe in the
database, not just the session's own. The GM's OOC answer named NPCs
("Old Tomas", "Millhaven") from a completely unrelated dark-fantasy world.
"""

from __future__ import annotations

import inspect

from monitor_agents.loops import preplay_support


def test_archetype_query_has_no_universe_bypass():
    """The tautology must be gone from the Cypher query string, and the
    universe_id parameter must be the sole scoping condition.

    Checks the specific buggy code shape ("$uid or 1=1", case-insensitive,
    contiguous) rather than a bare "OR 1=1" substring, since this file's
    own explanatory comment about the fix legitimately quotes that phrase
    as prose.
    """
    source = inspect.getsource(preplay_support.answer_ooc_question)
    normalized = " ".join(source.lower().split())

    assert "uid or 1=1" not in normalized
    assert "e.universe_id = $uid" in source
