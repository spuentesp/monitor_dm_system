"""GMAgent cast input wiring (Phase 4 Tasks 1/2).

Asserts the real callee — the ReAct module invocation seam
(``GMAgent._predict_react``) — receives the cast block with the agency rule.
The LM-resolution context (``dspy_context_for``) is stubbed: under the
hermetic suite it dials the provider registry over a blocked socket before
the seam runs.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from monitor_agents.cast import AGENCY_RULE, build_cast
from monitor_agents.gm_agent import GMAgent


def _fake_prediction() -> Any:
    return SimpleNamespace(
        intent_type="action",
        action_type="exploration",
        roll_necessity="trivial",
        causality_action="ACCEPT",
        suggested_stat="WIT",
        suggested_dc=10,
        subsystem_hint="none",
        declares_outcome=False,
        pushback_prompt="",
        narrative_draft="draft",
        reasoning="r",
        trajectory={},
    )


def _no_lm_context(*_args: Any, **_kwargs: Any) -> Any:
    return contextlib.nullcontext()


def _capture_into(captured: dict[str, Any]):
    def _capture(react_module: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return _fake_prediction()

    return _capture


class TestGMAgentCastInput:
    @pytest.mark.asyncio
    async def test_decide_passes_scene_context_cast_block_to_the_react_module(self):
        scene_id = str(uuid4())
        cast = build_cast(
            controlled_ids=["pc1", "pc2"],
            speaker_id="pc1",
            actor_context={"id": "pc1", "name": "Ana"},
            entity_context=[{"id": "n1", "name": "Vex", "entity_type": "character"}],
            scene_id=scene_id,
        )

        agent = GMAgent()
        agent._react_module = MagicMock()
        captured: dict[str, Any] = {}
        agent._predict_react = _capture_into(captured)  # type: ignore[method-assign]
        with (
            patch("monitor_agents.gm_agent.GM_TOOLS", lambda: []),
            patch("monitor_agents.dspy_runtime.dspy_context_for", _no_lm_context),
        ):
            verdict = await agent.decide(
                scene_id=scene_id,
                user_input="I ask about the ledger",
                scene_context={"entities": [], "turns": [], "cast": cast.model_dump(mode="json")},
            )

        # The real callee (ReAct seam) received the cast block with the rule.
        assert "[PLAYER-CONTROLLED] Ana" in captured["cast_context"]
        assert "[PLAYER-CONTROLLED] pc2" in captured["cast_context"]
        assert "[GM-CONTROLLED] Vex" in captured["cast_context"]
        assert AGENCY_RULE in captured["cast_context"]
        assert verdict.narrative_draft == "draft"

    @pytest.mark.asyncio
    async def test_decide_malformed_cast_degrades_to_no_cast_block(self):
        scene_id = str(uuid4())

        agent = GMAgent()
        agent._react_module = MagicMock()
        captured: dict[str, Any] = {}
        agent._predict_react = _capture_into(captured)  # type: ignore[method-assign]
        with (
            patch("monitor_agents.gm_agent.GM_TOOLS", lambda: []),
            patch("monitor_agents.dspy_runtime.dspy_context_for", _no_lm_context),
        ):
            await agent.decide(
                scene_id=scene_id,
                user_input="hi",
                scene_context={
                    "entities": [],
                    "turns": [],
                    "cast": {"members": [{"entity_id": 42, "controller": "nobody"}]},
                },
            )

        assert captured.get("cast_context") == ""

    @pytest.mark.asyncio
    async def test_decide_without_cast_sends_empty_cast_context(self):
        agent = GMAgent()
        agent._react_module = MagicMock()
        captured: dict[str, Any] = {}
        agent._predict_react = _capture_into(captured)  # type: ignore[method-assign]

        with (
            patch("monitor_agents.gm_agent.GM_TOOLS", lambda: []),
            patch("monitor_agents.dspy_runtime.dspy_context_for", _no_lm_context),
        ):
            await agent.decide(
                scene_id=str(uuid4()),
                user_input="hi",
                scene_context={"entities": [], "turns": []},
            )

        assert captured.get("cast_context") == ""
