"""
Tests for the Narrator's GMVerdict refinement path (T4).

When the narrator receives a pre-computed GMVerdict (with narrative_draft),
it should:
- Use the draft as the starting point.
- Avoid the legacy ChainOfThought creative gen (saves an LLM call).
- Fall back to legacy path only when the draft is empty.
- Surface the verdict's intent / roll_necessity / subsystem_hint in the
  resolution_summary passed to the underlying ChainOfThought (so the
  polish step can adjust voice accordingly).

The Narrator's existing tests cover the legacy path; this file covers the
new gm_verdict path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from monitor_agents.gm_awareness import (
    ActionType,
    CausalityAction,
    IntentType,
    RollNecessity,
)
from monitor_agents.gm_tools.contracts import GMVerdict
from monitor_agents.narrator.agent import Narrator


def _make_gm_verdict(
    narrative_draft: str = "You swing at the goblin.",
    intent: IntentType = IntentType.ACTION,
    action: ActionType = ActionType.COMBAT,
    roll: RollNecessity = RollNecessity.CONTESTED,
    causality: CausalityAction = CausalityAction.ACCEPT,
    subsystem_hint: str = "combat",
    suggested_stat: str = "STR",
    suggested_dc: int = 12,
    reasoning: str = "fast reflexes",
) -> GMVerdict:
    return GMVerdict(
        intent_type=intent,
        action_type=action,
        roll_necessity=roll,
        causality_action=causality,
        suggested_stat=suggested_stat,
        suggested_dc=suggested_dc,
        subsystem_hint=subsystem_hint,
        declares_outcome=False,
        pushback_prompt=None,
        action_route={
            "stat_name": suggested_stat,
            "difficulty_class": suggested_dc,
            "subsystem_hint": subsystem_hint,
        },
        narrative_draft=narrative_draft,
        tool_calls_made=["roll_dice"],
        tool_call_count=1,
        reasoning=reasoning,
    )


def _make_narrator(*, gm_refine_text: str = "Refined prose.") -> Narrator:
    narrator = Narrator.__new__(Narrator)
    narrator.agent_type = "Narrator"
    narrator.agent_id = "narrator-1"
    # The narrator delegates refinement to _generate_narrative_text which
    # calls _narrator_module. We mock the *whole* generate path.
    narrator._generate_narrative_text = AsyncMock(return_value=gm_refine_text)
    narrator._persist_turn = AsyncMock(return_value="turn-refined-001")
    narrator._tone_resolver = MagicMock()
    narrator._tone_resolver.resolve_from_profile = AsyncMock(return_value="Dramatic.")
    return narrator


# ============================================================================
# Refinement path
# ============================================================================


@pytest.mark.asyncio
async def test_narrate_turn_with_gm_verdict_uses_refinement() -> None:
    """When gm_verdict is provided, the narrator refines rather than creates from scratch."""
    narrator = _make_narrator()
    verdict = _make_gm_verdict()

    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="I attack the goblin",
        resolution={"success_level": "pending"},  # legacy field — ignored when gm_verdict set
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )
    assert result["narrative_text"] == "Refined prose."
    # Refinement used the existing generate path with a resolution_summary
    # built from the verdict — verify it was called.
    assert narrator._generate_narrative_text.called
    call_kwargs = narrator._generate_narrative_text.call_args.kwargs
    rs = call_kwargs["resolution"]
    assert rs["intent_type"] == "action"
    assert rs["action_type"] == "combat"
    assert rs["roll_necessity"] == "contested"
    assert rs["subsystem_hint"] == "combat"
    assert rs["gm_draft"] == "You swing at the goblin."
    assert rs["gm_reasoning"] == "fast reflexes"


@pytest.mark.asyncio
async def test_narrate_turn_with_empty_draft_falls_back_to_legacy() -> None:
    """When gm_verdict.narrative_draft is empty, narrator falls back to the legacy _generate path."""
    narrator = _make_narrator()
    verdict = _make_gm_verdict(narrative_draft="")  # empty → fallback

    # Mock the legacy generate path explicitly.
    async def _legacy_gen(**_kwargs):
        return "Legacy prose."

    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Legacy prose.", [], 1, [], None))
    # _generate_narrative_text shouldn't be called in the fallback path.
    narrator._generate_narrative_text = AsyncMock()

    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="anything",
        resolution=None,
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )
    assert result["narrative_text"] == "Legacy prose."
    narrator._generate_narrative_and_proposals.assert_called_once()
    narrator._generate_narrative_text.assert_not_called()


@pytest.mark.asyncio
async def test_narrate_turn_with_gm_verdict_persists_refined_text() -> None:
    narrator = _make_narrator()
    verdict = _make_gm_verdict()

    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="anything",
        resolution=None,
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )
    # The refined text (not the GM draft) is what gets persisted.
    assert narrator._persist_turn.called
    persist_kwargs = narrator._persist_turn.call_args.kwargs
    assert persist_kwargs["narrative_text"] == "Refined prose."
    assert result["turn_id"] == "turn-refined-001"


@pytest.mark.asyncio
async def test_refinement_falls_back_to_gm_draft_on_refine_failure() -> None:
    """If the refinement pass raises, narrator uses the GM's draft verbatim."""
    narrator = _make_narrator()

    # Make _generate_narrative_text raise.
    async def _boom(**_kwargs):
        raise RuntimeError("refine failed")

    narrator._generate_narrative_text = AsyncMock(side_effect=_boom)
    verdict = _make_gm_verdict(narrative_draft="Original draft, please.")

    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="anything",
        resolution=None,
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )
    # Falls back to GM draft.
    assert result["narrative_text"] == "Original draft, please."


@pytest.mark.asyncio
async def test_refinement_failure_surfaces_degraded_info() -> None:
    """The fallback-to-draft path must attach a player-facing 'degraded'
    marker to the result — not just silently swap the text — so the
    frontend can tell the player their turn used a simplified response.
    """
    narrator = _make_narrator()

    async def _boom(**_kwargs):
        raise RuntimeError("rate limit: too many requests")

    narrator._generate_narrative_text = AsyncMock(side_effect=_boom)
    verdict = _make_gm_verdict(narrative_draft="Original draft, please.")

    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="anything",
        resolution=None,
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )
    assert result["narrative_text"] == "Original draft, please."
    assert result["degraded"] is not None
    assert result["degraded"]["error_class"] == "rate_limit"
    assert "usage limit" in result["degraded"]["message"].lower()


@pytest.mark.asyncio
async def test_refinement_success_has_no_degraded_marker() -> None:
    """The happy path must not carry a stale/false degraded marker."""
    narrator = _make_narrator()
    verdict = _make_gm_verdict()

    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="anything",
        resolution=None,
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )
    assert result["degraded"] is None


# ============================================================================
# Resolution summary shape
# ============================================================================


@pytest.mark.asyncio
async def test_refinement_passes_structural_fields_to_underlying_module() -> None:
    """The summary passed to the underlying module should include roll_necessity, subsystem, etc."""
    narrator = _make_narrator()
    verdict = _make_gm_verdict(
        intent=IntentType.DIALOGUE,
        action=ActionType.DIALOGUE,
        roll=RollNecessity.PROPOSE_ROLL,
        causality=CausalityAction.PUSH_BACK,
        subsystem_hint="social",
        suggested_stat="CHA",
        suggested_dc=15,
    )

    await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="I try to convince the guard",
        resolution=None,
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )
    rs = narrator._generate_narrative_text.call_args.kwargs["resolution"]
    assert rs["intent_type"] == "dialogue"
    assert rs["action_type"] == "dialogue"
    assert rs["roll_necessity"] == "propose_roll"
    # CausalityAction.value is lower-cased: "push_back" not "PUSH_BACK".
    assert rs["causality_action"] == "push_back"
    assert rs["subsystem_hint"] == "social"
    assert rs["success_level"] == "pending"


# ============================================================================
# No-gm_verdict path (legacy)
# ============================================================================


@pytest.mark.asyncio
async def test_narrate_turn_without_gm_verdict_uses_legacy_path() -> None:
    """When gm_verdict is None, the narrator falls back to legacy _generate_narrative_and_proposals."""
    narrator = _make_narrator()
    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Legacy prose.", [], 1, [], None))

    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="anything",
        resolution={"success_level": "success"},
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=None,
    )
    narrator._generate_narrative_and_proposals.assert_called_once()
    assert result["narrative_text"] == "Legacy prose."


# ============================================================================
# Phase B — 3-step reconcile (compat check + anchored refine)
# ============================================================================
# The reconcile path classifies draft<->outcome into COMPATIBLE / DIVERGES /
# INCOMPATIBLE via a small dspy.Predict, then dispatches: refine with anchor
# (DIVERGES), refine clean (COMPATIBLE), regenerate from outcome (INCOMPATIBLE).
# For non-rolled turns there's no outcome to contradict the draft, so the
# compat check is skipped entirely (path = no-roll refine).
#
# The tests below stub _compat_check (no real LLM) and _generate_narrative_text
# (the prose polish step) so we can assert which path the dispatcher took.
# ============================================================================


def _make_gm_verdict_with_draft(draft: str):
    """Same as _make_gm_verdict but lets the caller pick the draft text."""
    from monitor_agents.gm_awareness import (
        ActionType,
        CausalityAction,
        IntentType,
        RollNecessity,
    )
    from monitor_agents.gm_tools.contracts import GMVerdict

    return GMVerdict(
        intent_type=IntentType.ACTION,
        action_type=ActionType.COMBAT,
        roll_necessity=RollNecessity.CONTESTED,
        causality_action=CausalityAction.ACCEPT,
        suggested_stat="STR",
        suggested_dc=12,
        subsystem_hint="combat",
        declares_outcome=False,
        pushback_prompt=None,
        action_route={"stat_name": "STR", "difficulty_class": 12, "subsystem_hint": "combat"},
        narrative_draft=draft,
        tool_calls_made=[],
        tool_call_count=0,
        reasoning="the GM anticipated the action",
    )


def _rolled_resolution(success_level: str = "success") -> dict:
    return {
        "scene_id": "scene-x",
        "resolution_type": "dice",
        "success_level": success_level,
        "roll_breakdown": "1d20(15) + 2 = 17 vs DC 12",
        "effects": ["fiction_advances"],
        "proposals": [],
    }


def _no_roll_resolution() -> dict:
    return {
        "scene_id": "scene-x",
        "resolution_type": "trivial",
        "success_level": "success",
        "proposals": [],
    }


@pytest.mark.asyncio
async def test_reconcile_compatible_skips_anchor_and_keeps_refine_path():
    """A draft that agrees with the outcome (COMPATIBLE) refines without anchor."""

    narrator = Narrator.__new__(Narrator)
    narrator.agent_type = "Narrator"
    narrator.agent_id = "narrator-1"
    narrator._generate_narrative_text = AsyncMock(return_value="Refined.")
    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Should not run.", [], 1, [], None))
    narrator._persist_turn = AsyncMock(return_value="turn-1")
    narrator._tone_resolver = MagicMock()
    narrator._tone_resolver.resolve_from_profile = AsyncMock(return_value="Dramatic.")

    fake_compat = MagicMock()
    fake_compat.verdict = "COMPATIBLE"
    narrator._compat_check = MagicMock(return_value=fake_compat)

    verdict = _make_gm_verdict_with_draft("You swing at the goblin and connect.")
    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="attack",
        resolution=_rolled_resolution("success"),
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )

    # Refine path (no anchor injected) ran.
    assert result["narrative_text"] == "Refined."
    narrator._generate_narrative_text.assert_called_once()
    narrator._generate_narrative_and_proposals.assert_not_called()
    # The refine prompt did NOT include outcome_anchor.
    call_kwargs = narrator._generate_narrative_text.await_args.kwargs
    assert "outcome_anchor" not in call_kwargs["resolution"]


@pytest.mark.asyncio
async def test_reconcile_diverges_injects_outcome_anchor():
    """A draft that contradicts the outcome (DIVERGES) refines WITH anchor."""

    narrator = Narrator.__new__(Narrator)
    narrator.agent_type = "Narrator"
    narrator.agent_id = "narrator-1"
    narrator._generate_narrative_text = AsyncMock(return_value="Refined with anchor.")
    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Should not run.", [], 1, [], None))
    narrator._persist_turn = AsyncMock(return_value="turn-1")
    narrator._tone_resolver = MagicMock()
    narrator._tone_resolver.resolve_from_profile = AsyncMock(return_value="Dramatic.")

    fake_compat = MagicMock()
    fake_compat.verdict = "DIVERGES"
    narrator._compat_check = MagicMock(return_value=fake_compat)

    verdict = _make_gm_verdict_with_draft("You confidently persuade the guard.")
    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="persuade",
        resolution=_rolled_resolution("critical_failure"),
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )

    # Refine path ran, WITH outcome anchor so the polish step reconciles.
    assert result["narrative_text"] == "Refined with anchor."
    call_kwargs = narrator._generate_narrative_text.await_args.kwargs
    assert "outcome_anchor" in call_kwargs["resolution"]
    narrator._generate_narrative_and_proposals.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_incompatible_drops_draft_and_regenerates():
    """A draft that asserts the opposite of the outcome (INCOMPATIBLE)
    drops the draft and regenerates from the outcome."""

    narrator = Narrator.__new__(Narrator)
    narrator.agent_type = "Narrator"
    narrator.agent_id = "narrator-1"
    narrator._generate_narrative_text = AsyncMock(return_value="Should NOT run.")
    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Regenerated from outcome.", [], 1, [], None))
    narrator._persist_turn = AsyncMock(return_value="turn-1")

    fake_compat = MagicMock()
    fake_compat.verdict = "INCOMPATIBLE"
    narrator._compat_check = MagicMock(return_value=fake_compat)

    verdict = _make_gm_verdict_with_draft("You overpower the dragon.")
    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="attack dragon",
        resolution=_rolled_resolution("critical_failure"),
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )

    # Legacy regen path ran; refine path did NOT.
    assert result["narrative_text"] == "Regenerated from outcome."
    narrator._generate_narrative_text.assert_not_called()
    narrator._generate_narrative_and_proposals.assert_called_once()


@pytest.mark.asyncio
async def test_reconcile_no_roll_skips_compat_check():
    """Non-rolled turns (trivial / forced_narrative / propose_roll) have no
    outcome to contradict the draft → the draft IS the story → refine
    without a compat check."""

    narrator = Narrator.__new__(Narrator)
    narrator.agent_type = "Narrator"
    narrator.agent_id = "narrator-1"
    narrator._generate_narrative_text = AsyncMock(return_value="Polished.")
    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Should not run.", [], 1, [], None))
    narrator._persist_turn = AsyncMock(return_value="turn-1")
    narrator._tone_resolver = MagicMock()
    narrator._tone_resolver.resolve_from_profile = AsyncMock(return_value="Dramatic.")
    narrator._compat_check = MagicMock(
        side_effect=AssertionError("compat_check should NOT be called for no-roll turns")
    )

    verdict = _make_gm_verdict_with_draft("You look around the room.")
    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="look around",
        resolution=_no_roll_resolution(),
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )

    assert result["narrative_text"] == "Polished."
    narrator._generate_narrative_text.assert_called_once()
    call_kwargs = narrator._generate_narrative_text.await_args.kwargs
    # No outcome anchor on a no-roll turn.
    assert "outcome_anchor" not in call_kwargs["resolution"]


@pytest.mark.asyncio
async def test_reconcile_compat_check_failure_defaults_to_diverges():
    """If the compat-check LLM errors out, default to DIVERGES (safe middle)."""

    narrator = Narrator.__new__(Narrator)
    narrator.agent_type = "Narrator"
    narrator.agent_id = "narrator-1"
    narrator._generate_narrative_text = AsyncMock(return_value="Refined with anchor.")
    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Should not run.", [], 1, [], None))
    narrator._persist_turn = AsyncMock(return_value="turn-1")
    narrator._tone_resolver = MagicMock()
    narrator._tone_resolver.resolve_from_profile = AsyncMock(return_value="Dramatic.")

    # Compat check raises → fail-soft to DIVERGES.
    narrator._compat_check = MagicMock(side_effect=RuntimeError("provider down"))

    verdict = _make_gm_verdict_with_draft("You swing and hit.")
    await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="attack",
        resolution=_rolled_resolution("success"),
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )

    # Outcome anchor present (DIVERGES was the default).
    call_kwargs = narrator._generate_narrative_text.await_args.kwargs
    assert "outcome_anchor" in call_kwargs["resolution"]


@pytest.mark.asyncio
async def test_reconcile_empty_draft_falls_back_to_legacy():
    """Empty draft skips reconcile entirely (compat check would have no
    input) and falls back to legacy _generate — same as before Phase B."""
    from monitor_agents.gm_awareness import (
        ActionType,
        CausalityAction,
        IntentType,
        RollNecessity,
    )
    from monitor_agents.gm_tools.contracts import GMVerdict

    narrator = Narrator.__new__(Narrator)
    narrator.agent_type = "Narrator"
    narrator.agent_id = "narrator-1"
    narrator._generate_narrative_text = AsyncMock(return_value="Should NOT run.")
    narrator._generate_narrative_and_proposals = AsyncMock(return_value=("Legacy.", [], 1, [], None))
    narrator._persist_turn = AsyncMock(return_value="turn-1")
    narrator._compat_check = MagicMock(side_effect=AssertionError("compat_check should NOT run on empty draft"))

    verdict = GMVerdict(
        intent_type=IntentType.ACTION,
        action_type=ActionType.COMBAT,
        roll_necessity=RollNecessity.CONTESTED,
        causality_action=CausalityAction.ACCEPT,
        suggested_stat="STR",
        suggested_dc=12,
        subsystem_hint="combat",
        declares_outcome=False,
        pushback_prompt=None,
        action_route=None,
        narrative_draft="",  # empty!
        tool_calls_made=[],
        tool_call_count=0,
        reasoning="",
    )
    result = await narrator.narrate_turn(
        scene_id=uuid4(),
        user_input="attack",
        resolution=_rolled_resolution("success"),
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        gm_verdict=verdict,
    )
    assert result["narrative_text"] == "Legacy."
    narrator._generate_narrative_and_proposals.assert_called_once()


def test_normalize_compat_maps_known_labels():
    from monitor_agents.narrator.agent import Narrator

    assert Narrator._normalize_compat("COMPATIBLE") == "COMPATIBLE"


# ============================================================================
# _generate_narrative_and_proposals — retry vs raise split
#
# The retry loop must NOT treat every failure the same way:
# - An unrecognized/parse-shaped failure (DSPy AdapterParseError and
#   friends) is the historically-known MiniMax JSON-adapter hiccup —
#   silently retry, degrade to empty text if retries are exhausted.
# - A provider-level failure (rate limit, quota, auth) should raise
#   LLMProviderUnavailable instead of silently returning empty text,
#   so callers can fall back to the GM's draft and/or surface a clear
#   message to the player.
# ============================================================================


def _make_bare_narrator() -> Narrator:
    from monitor_agents.narrator.agent import Narrator

    narrator = Narrator.__new__(Narrator)
    narrator.agent_type = "Narrator"
    narrator.agent_id = "narrator-1"
    narrator._tone_resolver = MagicMock()
    narrator._tone_resolver.resolve_from_profile = AsyncMock(return_value="Dramatic.")
    return narrator


@pytest.mark.asyncio
async def test_unknown_shaped_failure_retries_then_degrades_silently() -> None:
    """A DSPy AdapterParseError-shaped failure (no provider markers) keeps
    the original resilience behavior: retry, then degrade to empty text
    WITHOUT raising."""
    narrator = _make_bare_narrator()
    narrator._narrator_module = MagicMock(side_effect=ValueError("could not parse JSON"))

    (
        narrative_text,
        proposals,
        minutes,
        suggested,
        degraded,
    ) = await narrator._generate_narrative_and_proposals(
        user_input="anything",
        resolution=None,
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
    )
    assert narrative_text == ""
    # After the soft-retry (Task 1): the outer retry also failed, so the
    # surface degraded dict is populated with retried=True.
    assert isinstance(degraded, dict)
    assert degraded.get("retried") is True
    # 4 = 2 inner attempts in the first _generate_once + 2 inner attempts in
    # the trimmed retry.
    assert narrator._narrator_module.call_count == 4


@pytest.mark.asyncio
async def test_rate_limit_failure_raises_llm_provider_unavailable() -> None:
    """A rate-limit-shaped failure must raise instead of silently
    returning empty text — the caller needs to know to fall back."""
    from monitor_agents.llm_errors import LLMProviderUnavailable

    narrator = _make_bare_narrator()
    narrator._narrator_module = MagicMock(side_effect=RuntimeError("Token Plan usage limit reached (rate_limit_error)"))

    with pytest.raises(LLMProviderUnavailable) as exc_info:
        await narrator._generate_narrative_and_proposals(
            user_input="anything",
            resolution=None,
            context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
        )
    assert exc_info.value.info.error_class.value == "rate_limit"
    assert narrator._narrator_module.call_count == 2  # both retry attempts used, then raise


@pytest.mark.asyncio
async def test_success_after_one_retry_clears_pending_provider_error() -> None:
    """If attempt 1 fails with a provider error but attempt 2 succeeds,
    the success must win — no stale error should be raised."""
    good_prediction = MagicMock()
    good_prediction.narrative_text = "It worked on the second try."
    good_prediction.proposed_changes = "[]"
    good_prediction.narrative_time_elapsed = "1"
    good_prediction.suggested_actions = "[]"

    narrator = _make_bare_narrator()
    narrator._narrator_module = MagicMock(side_effect=[RuntimeError("rate limit exceeded"), good_prediction])

    (
        narrative_text,
        proposals,
        minutes,
        suggested,
        degraded,
    ) = await narrator._generate_narrative_and_proposals(
        user_input="anything",
        resolution=None,
        context={"entities": [], "memories": [], "turns": [], "source_profile": {}},
    )
    assert narrative_text == "It worked on the second try."
    assert degraded is None
    assert Narrator._normalize_compat("compatible") == "COMPATIBLE"
    assert Narrator._normalize_compat("INCOMPATIBLE") == "INCOMPATIBLE"
    assert Narrator._normalize_compat("DIVERGES") == "DIVERGES"
    # Unknown / malformed → safe middle (DIVERGES)
    assert Narrator._normalize_compat("maybe") == "DIVERGES"
    assert Narrator._normalize_compat("") == "DIVERGES"
    assert Narrator._normalize_compat(None) == "DIVERGES"
