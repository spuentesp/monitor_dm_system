"""Regression tests: build_gm_opening's module-intro branch
([G-2] 2026-07-23).

When a session's pack carries a substantive ``intro_text`` (>40 chars),
``build_gm_opening`` returns it VERBATIM — the highest-precedence
fresh-session path, ahead of resume-recap and the generated cold open.
See ``docs/architecture/GAP_REMEDIATION_PLAN.md`` G-2(c) and
``docs/STATUS.md``.

Three precedence rules to lock in here:

  - Fresh session, pack has substantive intro → return intro verbatim
    (meta ``{"type": "gm_opening", "module_intro": True}``).
  - Resume session, pack has intro → resume-recap branch STILL wins
    (case 1 is fresh sessions only per the plan).
  - Pack has no / short / broken intro → fall through to cold open
    (resume branch if applicable).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from monitor_ui.routers.chat_opening import build_gm_opening

PACK_ID = str(uuid4())
VALID_INTRO = (
    "A pale sun rose over the wreck of the Iolarite, its blue-white glow "
    "picking out the names scratched into the hull — yours among them. "
    "The last thing you remember is the gravimetric shear and the smell "
    "of burning coolant."
)
SHORT_INTRO = "Too short."  # 10 chars — below the 40-char floor


def _pack_with_intro(intro_text: str | None) -> SimpleNamespace:
    """Stub that matches the attributes ``_fetch_module_intro`` reads."""
    return SimpleNamespace(intro_text=intro_text)


@pytest.mark.asyncio
async def test_fresh_session_with_substantive_intro_returns_verbatim():
    """Authored intro wins over cold open for fresh sessions."""
    session = {
        "universe_id": str(uuid4()),
        "tone": "dramatic",
        "pack_id": PACK_ID,
    }

    with patch(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        return_value=_pack_with_intro(VALID_INTRO),
    ) as mock_get:
        text, meta = await build_gm_opening(
            "sess-intro",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=False,
        )

    assert text == VALID_INTRO  # VERBATIM, no LLM rewrite
    assert meta == {"type": "gm_opening", "module_intro": True}
    mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_resume_session_with_intro_lets_recap_win():
    """Resume branch outranks the module-intro branch (case 1 fresh-only)."""
    session = {
        "universe_id": str(uuid4()),
        "story_id": str(uuid4()),
        "tone": "grim",
        "pack_id": PACK_ID,
    }

    with (
        patch(
            "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
            return_value=_pack_with_intro(VALID_INTRO),
        ),
        patch("monitor_agents.recap.agent.RecapAgent") as MockRecap,
    ):
        instance = MockRecap.return_value
        instance.generate_recap = AsyncMock_NoOp()
        text, meta = await build_gm_opening(
            "sess-resume",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=True,
        )

    assert "module_intro" not in meta
    assert meta.get("resume") is True


def AsyncMock_NoOp():
    """An AsyncMock returning VALID_INTRO — recaps beat module intros for resumes."""
    from unittest.mock import AsyncMock

    return AsyncMock(return_value=("The crew barely escaped the collapsing station. Echo is still missing."))


@pytest.mark.asyncio
async def test_no_intro_text_falls_through_to_cold_open():
    """Pack has ``intro_text=None`` → cold-open path, no module_intro meta."""
    session = {
        "universe_id": str(uuid4()),
        "tone": "dramatic",
        "pack_id": PACK_ID,
    }

    with patch(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        return_value=_pack_with_intro(None),
    ):
        text, meta = await build_gm_opening(
            "sess-none",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=False,
        )

    assert "module_intro" not in meta
    assert isinstance(text, str) and text  # cold open produced something


@pytest.mark.asyncio
async def test_empty_intro_string_falls_through_to_cold_open():
    session = {"universe_id": str(uuid4()), "tone": "dramatic", "pack_id": PACK_ID}

    with patch(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        return_value=_pack_with_intro(""),
    ):
        text, meta = await build_gm_opening(
            "sess-empty",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=False,
        )

    assert "module_intro" not in meta


@pytest.mark.asyncio
async def test_short_intro_below_floor_falls_through_to_cold_open():
    """The 40-char floor prevents a one-line intro from short-circuiting the LLM."""
    session = {"universe_id": str(uuid4()), "tone": "dramatic", "pack_id": PACK_ID}

    with patch(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        return_value=_pack_with_intro(SHORT_INTRO),
    ):
        text, meta = await build_gm_opening(
            "sess-short",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=False,
        )

    assert "module_intro" not in meta


@pytest.mark.asyncio
async def test_tool_raising_falls_through_to_cold_open_no_exception():
    """A mongo failure must not crash the session-creation flow."""
    session = {"universe_id": str(uuid4()), "tone": "dramatic", "pack_id": PACK_ID}

    with patch(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        side_effect=RuntimeError("mongo down"),
    ):
        # No exception here — opening flow continues into the cold-open path.
        text, meta = await build_gm_opening(
            "sess-tool-fail",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=False,
        )

    assert "module_intro" not in meta
    assert isinstance(text, str)


@pytest.mark.asyncio
async def test_pack_not_found_falls_through_to_cold_open():
    """Mongo returns None for the pack_id → cold open, no crash."""
    session = {"universe_id": str(uuid4()), "tone": "dramatic", "pack_id": PACK_ID}

    with patch(
        "monitor_data.tools.mongodb_tools.mongodb_get_knowledge_pack",
        return_value=None,
    ):
        text, meta = await build_gm_opening(
            "sess-no-pack",
            session,
            session_game_system_doc=lambda _s: None,
            is_resume=False,
        )

    assert "module_intro" not in meta
