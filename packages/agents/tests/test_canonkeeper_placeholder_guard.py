"""Regression tests: canonize must reject placeholder entity/relation names.

Live bug (2026-07-22, Fallout 2d20 Settlers Supplement ingest): garbled source
text made the extractor emit "none" as a parent name, and CanonKeeper happily
resolved/created it and drew SUBTYPE_OF edges from three real archetypes into
a literal "none" entity. These tests pin the guard that rejects that class of
proposal before it reaches Neo4j.
"""

from __future__ import annotations

import pytest

from monitor_agents.canonkeeper.agent import CanonKeeper


@pytest.mark.parametrize(
    "name",
    ["none", "None", "  NONE  ", "unknown", "n/a", "N/A", "unspecified", "", "   ", None],
)
def test_is_placeholder_name_rejects_known_junk(name):
    assert CanonKeeper._is_placeholder_name(name) is True


@pytest.mark.parametrize("name", ["Railroad", "Institute Scientist", "Fens Phantom", "X"])
def test_is_placeholder_name_accepts_real_names(name):
    assert CanonKeeper._is_placeholder_name(name) is False


class _FakeProposalsColl:
    def update_one(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
async def test_commit_entity_skips_placeholder_name(monkeypatch):
    keeper = CanonKeeper.__new__(CanonKeeper)
    calls: list[str] = []

    async def _fake_call_tool(tool_name, _arguments):
        calls.append(tool_name)
        return "{}"

    keeper.call_tool = _fake_call_tool  # type: ignore[method-assign]
    proposal = {"universe_id": "u1", "payload": {"name": "none"}}

    await CanonKeeper._commit_entity(keeper, _FakeProposalsColl(), "p1", proposal, [], verdict=None)

    assert calls == []


@pytest.mark.asyncio
async def test_commit_entity_relationship_skips_placeholder_target(monkeypatch):
    keeper = CanonKeeper.__new__(CanonKeeper)
    calls: list[str] = []

    async def _fake_call_tool(tool_name, _arguments):
        calls.append(tool_name)
        return "{}"

    keeper.call_tool = _fake_call_tool  # type: ignore[method-assign]
    proposal = {
        "universe_id": "u1",
        "payload": {"from_entity": "Strong", "to_entity": "none", "rel_type": "subtype_of"},
    }

    await CanonKeeper._commit_entity_relationship(keeper, _FakeProposalsColl(), "p1", proposal, [], verdict=None)

    assert calls == []
