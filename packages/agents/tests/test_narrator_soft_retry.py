"""Narrator soft-retry: a single transient failure should recover cleanly."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from monitor_agents.narrator.agent import Narrator


def _ok_result() -> tuple[str, list, int, list, Any]:
    return ("all good", [], 5, [], None)


def _degraded_result() -> tuple[str, list, int, list, Any]:
    return ("", [], 5, [], None)


@pytest.mark.asyncio
async def test_first_failure_retry_succeeds() -> None:
    narrator = Narrator()
    with patch.object(
        narrator,
        "_generate_once",
        new=AsyncMock(side_effect=[_degraded_result(), _ok_result()]),
    ) as m:
        narrative, props, mins, suggested, last = await narrator._generate_narrative_and_proposals(
            user_input=None,
            resolution=None,
            context={"entities": [], "memories": [], "turns": []},
        )
    assert narrative == "all good"
    assert last is None
    assert m.await_count == 2
    # The retry must have been called with trimmed=True.
    assert any(c.kwargs.get("trimmed") is True for c in m.await_args_list)


@pytest.mark.asyncio
async def test_both_failures_ship_empty_with_retried_marker() -> None:
    narrator = Narrator()
    with patch.object(
        narrator,
        "_generate_once",
        new=AsyncMock(side_effect=[_degraded_result(), _degraded_result()]),
    ) as m:
        narrative, props, mins, suggested, last = await narrator._generate_narrative_and_proposals(
            user_input=None,
            resolution=None,
            context={"entities": [], "memories": [], "turns": []},
        )
    assert narrative == ""
    assert m.await_count == 2
    assert isinstance(last, dict) and last.get("retried") is True


@pytest.mark.asyncio
async def test_no_retry_when_first_call_succeeds() -> None:
    narrator = Narrator()
    with patch.object(
        narrator,
        "_generate_once",
        new=AsyncMock(return_value=_ok_result()),
    ) as m:
        narrative, props, mins, suggested, last = await narrator._generate_narrative_and_proposals(
            user_input=None,
            resolution=None,
            context={"entities": [], "memories": [], "turns": []},
        )
    assert narrative == "all good"
    assert last is None
    assert m.await_count == 1  # no retry
