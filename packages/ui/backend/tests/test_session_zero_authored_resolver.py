"""Tests for resolve_authored_session_zero_questions (Phase 2 wiring).

Verifies that a curated session_zero prompt_collection is resolved for a
session (by explicit id, universe binding, or system binding) and serialized
into the authored-questions shape the SessionZeroLoop consumes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

from monitor_data.schemas.prompt_collections import (
    PromptCollectionListResponse,
    PromptCollectionResponse,
    PromptEntry,
)
from monitor_agents.loops.preplay_support import resolve_authored_session_zero_questions

# resolve_authored_session_zero_questions imports the mongodb tools lazily from
# monitor_data.tools.mongodb_tools inside the function body, so patch there.
_MODULE = "monitor_data.tools.mongodb_tools"


def _collection(**overrides) -> PromptCollectionResponse:
    base = {
        "collection_id": uuid4(),
        "name": "V5 Session Zero",
        "category": "session_zero",
        "tags": [],
        "entries": [
            PromptEntry(order=1, category="loss", question_text="Whose blood do you regret?", is_final=True),
            PromptEntry(order=0, category="name", question_text="What are you called?"),
        ],
        "is_builtin": False,
        "hand_authored": True,
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return PromptCollectionResponse(**base)


def _fake_doc(system_id):
    return lambda session: {"system_id": str(system_id)}


def test_returns_empty_when_no_binding():
    session = {"universe_id": str(uuid4())}
    with (
        patch(f"{_MODULE}.mongodb_list_prompt_collections") as m_list,
        patch(f"{_MODULE}.mongodb_get_prompt_collection") as m_get,
    ):
        m_list.return_value = PromptCollectionListResponse(collections=[], total=0, limit=50, offset=0)
        m_get.return_value = None
        result = resolve_authored_session_zero_questions(session, lambda s: None)
    assert result == []


def test_explicit_binding_wins_and_is_ordered():
    coll = _collection()
    session = {"authored_prompt_collection_id": str(coll.collection_id)}
    with (
        patch(f"{_MODULE}.mongodb_get_prompt_collection", return_value=coll) as m_get,
        patch(f"{_MODULE}.mongodb_list_prompt_collections") as m_list,
    ):
        result = resolve_authored_session_zero_questions(session, lambda s: None)

    m_get.assert_called_once()
    m_list.assert_not_called()  # explicit binding short-circuits
    # Sorted by entry.order → name (0) before loss (1).
    assert [q["question_text"] for q in result] == ["What are you called?", "Whose blood do you regret?"]
    assert result[0]["category"] == "name"
    assert result[1]["is_final"] is True


def test_universe_binding_preferred_over_system():
    universe_coll = _collection(name="Universe SZ")
    system_id = uuid4()
    session = {"universe_id": str(uuid4())}

    def fake_list(filt):
        # Universe query returns a hit; system query would too, but universe wins.
        if filt.universe_id is not None:
            return PromptCollectionListResponse(collections=[universe_coll], total=1, limit=50, offset=0)
        return PromptCollectionListResponse(collections=[_collection(name="System SZ")], total=1, limit=50, offset=0)

    with (
        patch(f"{_MODULE}.mongodb_list_prompt_collections", side_effect=fake_list),
        patch(f"{_MODULE}.mongodb_get_prompt_collection", return_value=None),
    ):
        result = resolve_authored_session_zero_questions(session, _fake_doc(system_id))

    assert len(result) == 2
    assert result[0]["question_text"] == "What are you called?"


def test_system_binding_when_no_universe_match():
    system_id = uuid4()
    session = {"universe_id": str(uuid4())}

    def fake_list(filt):
        if filt.system_id is not None:
            return PromptCollectionListResponse(collections=[_collection(name="System SZ")], total=1, limit=50, offset=0)
        return PromptCollectionListResponse(collections=[], total=0, limit=50, offset=0)

    with (
        patch(f"{_MODULE}.mongodb_list_prompt_collections", side_effect=fake_list),
        patch(f"{_MODULE}.mongodb_get_prompt_collection", return_value=None),
    ):
        result = resolve_authored_session_zero_questions(session, _fake_doc(system_id))

    assert len(result) == 2
