"""
GMAgent — the dedicated Game Master authority.

LAYER: 2 (agents)
IMPORTS FROM: data-layer (embed_text / embed_batch via tools), stdlib,
              monitor_agents.gm_awareness (seed), monitor_agents.gm_tools (registry)
CALLED BY: monitor_agents.resolver (orchestrates the GM loop)

ARCHITECTURE
------------
GMAgent owns the *ReAct* loop. It is the LM authority on every turn:
  - Reads the player input + scene context.
  - Calls gm_tools (semantic classifiers, scene-state, dice, oracle) as
    needed.
  - Composes a ``GMVerdict`` (intent / action / causality / routed stat /
    DC / subsystem / narrative draft) and returns it.

The Narrator downstream will refine ``narrative_draft``; the Resolver
shapes ``GMVerdict`` back into the legacy ``resolution`` dict.

FALLBACK CHAIN
--------------
The ReAct loop is bounded at ``max_tool_calls`` (default 5). If the loop
exhausts without converging, or any tool raises, GMAgent falls through to
the deterministic ``GMAwarenessModule.predict()`` (the seed) and produces
a verdict from there. We never raise out of ``decide()`` — the worst
case is a structured fallback verdict + observability flag.

ASYNC-SYNC BRIDGE
-----------------
``decide()`` runs the ReAct loop inside ``asyncio.to_thread`` (DSPy ReAct
is synchronous). Async tool functions submit to the running event loop
via the bridge installed at startup (``set_loop_bridge``).

TEST SURFACE
------------
``_FakeLM`` drives ReAct with canned tool-call decisions. Tests pin
``GMVerdict`` shape and tool-call counts.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import dspy
import structlog

from monitor_agents.base import BaseAgent
from monitor_agents.gm_awareness import (
    ActionType,
    CausalityAction,
    GMAwareness,
    IntentType,
    RollNecessity,
    check_gm_awareness,
)
from monitor_agents.gm_tools.contracts import GMVerdict
from monitor_agents.gm_tools.registry import (
    GM_TOOLS,
    build_loop_bridge_from_running_loop,
    reset_tools,
    set_loop_bridge,
)

log = structlog.get_logger(__name__)


# Default configuration --------------------------------------------------------

DEFAULT_MAX_TOOL_CALLS = 5


# DSPy signature for the GM's ReAct loop ----------------------------------------


class _GMReActSignature(dspy.Signature):  # type: ignore[misc]
    """Read the player's action + scene context. Decide the GM verdict.

    Tools are available — call them when uncertain rather than guessing.
    Once you have enough information, call ``finish`` and produce the
    final verdict.
    """

    # ── Inputs (caller-supplied) ──
    user_input: str = dspy.InputField(desc="The player's raw text for this turn.")
    character_name: str = dspy.InputField(desc="Player character name.")
    character_role: str = dspy.InputField(desc="Player character class / role.")
    play_mode: str = dspy.InputField(desc="narrative / dice_standard / dice_game_system.")
    roll_mode: str = dspy.InputField(desc="normal / advantage / disadvantage / auto.")
    established_facts: str = dspy.InputField(desc="Newline-separated established facts from earlier turns (last 20).")
    scene_entities: str = dspy.InputField(desc="Newline-separated scene entities: ``- <name> (<type>)``.")
    recent_turns: str = dspy.InputField(desc="Newline-separated recent turns: ``- <speaker>: <text>`` (last 3).")

    # ── Upstream-routed (resolver-injected) ──
    upstream_action_context: str = dspy.InputField(
        desc=(
            "JSON of the resolver's pre-routed action_context (stat, DC, subsystem_hint). "
            "Empty string when the resolver couldn't pre-route."
        )
    )
    upstream_pending_roll: str = dspy.InputField(
        desc=("JSON of any pending-roll spec the previous turn proposed. Empty string when there is no pending roll.")
    )
    table_agreements: str = dspy.InputField(
        desc=(
            "Player table agreements from Session Zero, formatted as a single block. "
            "List `lines` (subjects that must never be depicted or introduced) and "
            "`veils` (subjects that may exist but must fade to black without detail). "
            "Empty string when the player stated no agreements. These override your "
            "default tendency to depict dramatic or distressing content; reroute or "
            "acknowledge and skip such material rather than describing it."
        )
    )

    # ── Outputs ──
    intent_type: str = dspy.OutputField(desc="meta / ooc / query / dialogue / action. Choose one.")
    action_type: str = dspy.OutputField(
        desc=(
            "none / dialogue / combat / stealth / exploration / movement. Always 'none' when intent is meta/ooc/query."
        )
    )
    roll_necessity: str = dspy.OutputField(
        desc=(
            "trivial / propose_roll / contested / forced_narrative_pending. "
            "Use 'forced_narrative_pending' when the previous turn proposed "
            "a roll and the player is acknowledging it (rolling or letting "
            "it auto-resolve)."
        )
    )
    causality_action: str = dspy.OutputField(
        desc=(
            "ACCEPT / PUSH_BACK / REQUEST_CLARIFICATION / NARRATIVE_OVERRIDE. "
            "Accept means proceed normally; PUSH_BACK means ask the player "
            "to roll; REQUEST_CLARIFICATION means ask for missing info; "
            "NARRATIVE_OVERRIDE means we're in god mode and accept anyway."
        )
    )
    suggested_stat: str = dspy.OutputField(
        desc=(
            "If pushing back / offering a roll, the stat to roll. "
            "Otherwise the chosen stat for the roll. 'none' when no roll."
        )
    )
    suggested_dc: int = dspy.OutputField(
        desc=(
            "If pushing back / offering a roll, the difficulty class "
            "(10 easy, 12 standard, 15 hard, 18 very hard). 0 when no roll."
        )
    )
    subsystem_hint: str = dspy.OutputField(
        desc=(
            "Which world subsystem the action belongs to: combat / social / "
            "ship / exploration / None. Drives scene delegation (combat -> "
            "CombatLoop). 'none' when no subsystem fires."
        )
    )
    declares_outcome: bool = dspy.OutputField(
        desc=(
            "True if the player is asserting an outcome already happened "
            "(past tense, present perfect). False if attempting."
        )
    )
    pushback_prompt: str = dspy.OutputField(
        desc="If pushing back or clarifying, the message shown to the player. Empty string otherwise."
    )
    narrative_draft: str = dspy.OutputField(
        desc=(
            "First draft of the GM's narrative for this turn. The Narrator "
            "downstream will refine this for voice / pacing. Keep it short "
            "(2-4 paragraphs) and reactive to the player's specific action. "
            "Markup: wrap physical actions/narration beats in *single "
            "asterisks* (e.g. *the door creaks open*). Leave spoken dialogue "
            "and normal prose unmarked -- plain text is the default. If you "
            "must step outside the fiction (answering a rules/meta question, "
            "addressing the player directly rather than their character), "
            "wrap that entire aside in ((double parentheses)) -- never mix "
            "in-fiction prose and an OOC aside in the same sentence."
        )
    )
    reasoning: str = dspy.OutputField(desc="Free-form reasoning the GM used to reach this verdict.")


class _GMSignatureExtract(dspy.Signature):  # type: ignore[misc]
    """ReAct's extract step — coerce the trajectory into the final outputs."""

    user_input: str = dspy.InputField(desc="(passthrough)")
    character_name: str = dspy.InputField(desc="(passthrough)")
    character_role: str = dspy.InputField(desc="(passthrough)")
    play_mode: str = dspy.InputField(desc="(passthrough)")
    roll_mode: str = dspy.InputField(desc="(passthrough)")
    established_facts: str = dspy.InputField(desc="(passthrough)")
    scene_entities: str = dspy.InputField(desc="(passthrough)")
    recent_turns: str = dspy.InputField(desc="(passthrough)")
    upstream_action_context: str = dspy.InputField(desc="(passthrough)")
    upstream_pending_roll: str = dspy.InputField(desc="(passthrough)")
    trajectory: str = dspy.InputField(desc="The ReAct trajectory: thought / tool / args / observation.")

    intent_type: str = dspy.OutputField(desc="Final intent_type.")
    action_type: str = dspy.OutputField(desc="Final action_type.")
    roll_necessity: str = dspy.OutputField(desc="Final roll_necessity.")
    causality_action: str = dspy.OutputField(desc="Final causality_action.")
    suggested_stat: str = dspy.OutputField(desc="Final suggested_stat.")
    suggested_dc: int = dspy.OutputField(desc="Final suggested_dc.")
    subsystem_hint: str = dspy.OutputField(desc="Final subsystem_hint.")
    declares_outcome: bool = dspy.OutputField(desc="Final declares_outcome.")
    pushback_prompt: str = dspy.OutputField(desc="Final pushback_prompt.")
    narrative_draft: str = dspy.OutputField(
        desc=(
            "Final narrative_draft. Preserve markup from the trajectory: "
            "*single asterisks* for actions, plain text for dialogue/prose, "
            "((double parentheses)) for OOC asides."
        )
    )
    reasoning: str = dspy.OutputField(desc="Final reasoning.")


def _build_react_module(tools: list[Any], max_iters: int) -> dspy.ReAct:
    return dspy.ReAct(_GMReActSignature, tools=list(tools), max_iters=max_iters)


# Verdict construction ----------------------------------------------------------


def _parse_intent(value: str) -> IntentType:
    try:
        return IntentType(value.lower().strip())
    except ValueError:
        return IntentType.ACTION


def _parse_action_type(value: str) -> ActionType:
    try:
        return ActionType(value.lower().strip())
    except ValueError:
        return ActionType.NONE


def _parse_roll_necessity(value: str) -> RollNecessity:
    try:
        return RollNecessity(value.lower().strip())
    except ValueError:
        return RollNecessity.PROPOSE_ROLL


def _parse_causality_action(value: str) -> CausalityAction:
    try:
        return CausalityAction(value.lower().strip())
    except ValueError:
        return CausalityAction.ACCEPT


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower().strip() in ("true", "1", "yes", "y")
    return bool(value)


def _trajectory_tool_calls(trajectory: dict[str, Any]) -> tuple[list[str], int, list[str]]:
    """Walk the trajectory dict and extract tool-call names + failures."""
    calls: list[str] = []
    failures: list[str] = []
    count = 0
    for k, v in trajectory.items():
        if k.startswith("tool_name_"):
            count += 1
            name = str(v) if v is not None else ""
            calls.append(name)
            obs_key = k.replace("tool_name_", "observation_")
            obs = str(trajectory.get(obs_key, ""))
            if obs.startswith("Execution error in"):
                failures.append(obs)
    return calls, count, failures


def gmverdict_from_prediction(
    pred: Any,
    upstream_action_context: dict[str, Any] | None = None,
    upstream_pending_roll: dict[str, Any] | None = None,
    fallback_narrative: str = "",
) -> GMVerdict:
    """Build a GMVerdict from a DSPy Prediction (post-ReAct or fallback seed)."""
    trajectory = getattr(pred, "trajectory", {}) or {}

    # Subsystem hint: prefer the LLM's read; fall back to upstream routing.
    sub_hint = _coerce_str(getattr(pred, "subsystem_hint", None))
    if not sub_hint or sub_hint.lower() == "none":
        if upstream_action_context and isinstance(upstream_action_context, dict):
            sub_hint = upstream_action_context.get("subsystem_hint") or "none"

    return GMVerdict(
        intent_type=_parse_intent(getattr(pred, "intent_type", "action")),
        action_type=_parse_action_type(getattr(pred, "action_type", "exploration")),
        roll_necessity=_parse_roll_necessity(getattr(pred, "roll_necessity", "trivial")),
        causality_action=_parse_causality_action(getattr(pred, "causality_action", "ACCEPT")),
        suggested_stat=_coerce_str(getattr(pred, "suggested_stat", None)) or None,
        suggested_dc=_coerce_int(getattr(pred, "suggested_dc", None), 0) or None,
        declares_outcome=_coerce_bool(getattr(pred, "declares_outcome", None)),
        pushback_prompt=_coerce_str(getattr(pred, "pushback_prompt", None)) or None,
        subsystem_hint=sub_hint or None,
        action_route=upstream_action_context,
        narrative_draft=_coerce_str(getattr(pred, "narrative_draft", None)) or fallback_narrative,
        tool_calls_made=_trajectory_tool_calls(trajectory)[0],
        tool_call_count=_trajectory_tool_calls(trajectory)[1],
        tool_failures=_trajectory_tool_calls(trajectory)[2],
        reasoning=_coerce_str(getattr(pred, "reasoning", None)),
    )


def gmverdict_from_awareness(aw: GMAwareness, upstream_action_context: dict[str, Any] | None = None) -> GMVerdict:
    """Convert a GMAwarenessModule seed verdict into a GMVerdict."""
    sub_hint = None
    if upstream_action_context and isinstance(upstream_action_context, dict):
        sub_hint = upstream_action_context.get("subsystem_hint") or None
    severity_value = "none"
    if hasattr(aw, "severity"):
        sev = aw.severity
        severity_value = sev.value if hasattr(sev, "value") else str(sev)
    reasons = list(getattr(aw, "reasons", []) or [])
    return GMVerdict(
        intent_type=aw.intent_type,
        action_type=aw.action_type,
        roll_necessity=aw.roll_necessity,
        causality_action=aw.action,
        suggested_stat=aw.suggested_stat,
        suggested_dc=aw.suggested_dc,
        declares_outcome=aw.declares_outcome,
        violates_causality=bool(getattr(aw, "violates_causality", False)),
        pushback_prompt=aw.pushback_prompt,
        severity=severity_value,
        reasons=reasons,
        subsystem_hint=sub_hint,
        action_route=upstream_action_context,
        narrative_draft="",
        reasoning=aw.reasoning or "",
        tool_calls_made=[],
        tool_call_count=0,
    )


def gmverdict_from_resolution(resolution: dict[str, Any]) -> GMVerdict:
    """Reconstruct a GMVerdict from the legacy resolution dict.

    Used by callers (like the e2e harness) that drive the pipeline via
    Resolver.resolve_turn and want to feed the verdict into Narrator's
    refine path without calling gm_agent.decide() a second time.

    Best-effort — fields that aren't in the resolution dict fall back to
    safe defaults. This is observability-grade: the resolver's verdict
    is authoritative for the actual gameplay decision; this helper just
    bridges the dict back to the typed GMVerdict so the narrator's
    refinement signature stays consistent.
    """

    # Map resolution intent/action/roll strings to the typed enums.
    def _enum(enum_cls, raw, default):  # type: ignore[no-untyped-def]
        try:
            return enum_cls(str(raw).lower()) if raw else default
        except (ValueError, KeyError):
            return default

    intent_type = _enum(IntentType, resolution.get("intent_type"), IntentType.ACTION)  # type: ignore[no-untyped-call]
    action_type = _enum(ActionType, resolution.get("action_type"), ActionType.NONE)  # type: ignore[no-untyped-call]
    roll_necessity = _enum(  # type: ignore[no-untyped-call]
        RollNecessity, resolution.get("roll_necessity"), RollNecessity.PROPOSE_ROLL
    )
    causality_action = _enum(  # type: ignore[no-untyped-call]
        CausalityAction, resolution.get("causality_action"), CausalityAction.ACCEPT
    )

    suggested_stat = resolution.get("stat") or None
    suggested_dc = resolution.get("difficulty_class") or None

    return GMVerdict(
        intent_type=intent_type,
        action_type=action_type,
        roll_necessity=roll_necessity,
        causality_action=causality_action,
        suggested_stat=suggested_stat,
        suggested_dc=suggested_dc,
        declares_outcome=bool(resolution.get("declares_outcome", False)),
        violates_causality=bool(resolution.get("violates_causality", False)),
        pushback_prompt=resolution.get("pushback_prompt"),
        subsystem_hint=resolution.get("subsystem_hint"),
        action_route=None,
        narrative_draft="",
        reasoning=resolution.get("gm_reasoning", ""),
        tool_calls_made=[],
        tool_call_count=0,
    )


# GMAgent -----------------------------------------------------------------------


class GMAgent(BaseAgent):
    """The Game Master — ReAct over the gm_tools registry.

    Public entry point: :meth:`decide`. The agent constructs a ReAct module
    on first use (cached), installs the loop-bridge for async tool bridging,
    and runs the ReAct loop bounded at ``max_tool_calls``. Falls through to
    the deterministic GMAwareness seed on any failure.
    """

    agent_type = "GM"  # type: ignore[assignment, misc, unused-ignore]

    def __init__(
        self,
        agent_id: str = "gm-agent-1",
        model: str | None = None,
        max_tool_calls: int = DEFAULT_MAX_TOOL_CALLS,
    ) -> None:
        super().__init__(agent_type="GMAgent", agent_id=agent_id, model=model)
        self._max_tool_calls = max(1, max_tool_calls)
        self._react_module: dspy.ReAct | None = None

    async def run(self) -> None:
        """GMAgent is query-only; no autonomous loop. ``decide()`` is the entry point."""
        return None

    def _get_react_module(self, tools: list[Any]) -> dspy.ReAct:
        if self._react_module is None:
            self._react_module = _build_react_module(tools, max_iters=self._max_tool_calls)
        return self._react_module

    def _predict_react(self, react_module: Any, **kwargs: Any) -> Any:
        """Forward to the ReAct module; tests override this seam to capture kwargs.

        The base implementation runs the synchronous DSPy ReAct module.
        Tests override this seam to capture the kwargs the production code
        passes without spinning up DSPy.
        """
        if callable(react_module):
            return react_module(**kwargs)
        return None

    async def decide(
        self,
        scene_id: str,
        user_input: str,
        scene_context: dict[str, Any],
        source_profile: dict[str, Any] | None = None,
        game_context: dict[str, Any] | None = None,
        established_facts: list[str] | None = None,
        upstream_action_context: dict[str, Any] | None = None,
        upstream_pending_roll: dict[str, Any] | None = None,
        play_mode: str = "dice_game_system",
        roll_mode: str = "normal",
    ) -> GMVerdict:
        """Run the GM ReAct loop and return a structured GMVerdict.

        Args:
            scene_id: The active scene UUID (for observability + tool args).
            user_input: The player's raw text.
            scene_context: Dict with ``entities``, ``turns``, ``source_profile``.
            source_profile: Optional source-profile dict (Vampire canon terms etc.).
            game_context: The game system MongoDB doc — propagated to the
                GMAgent so the scene-state tools can build a GSR.
            established_facts: Accumulated facts from the session.
            upstream_action_context: Optional pre-routed action context from
                the resolver. Forwarded as a DSPy input field, used as fallback
                for subsystem_hint.
            upstream_pending_roll: Optional pending-roll spec from a prior
                propose_roll turn. Forwarded to the LLM so it can choose
                ``forced_narrative_pending`` roll necessity.
            play_mode: Freeform mode flag.
            roll_mode: normal/advantage/disadvantage/auto.

        Returns:
            A ``GMVerdict``. Never raises.
        """
        established = list(established_facts or [])[-20:]
        entities_text = "\n".join(
            f"- {e.get('name', '?')} ({e.get('entity_type', '?')})" for e in (scene_context.get("entities") or [])
        )
        recent_turns_text = "\n".join(
            f"- {t.get('speaker', '?')}: {str(t.get('text', ''))[:200]}"
            for t in (scene_context.get("turns") or [])[-3:]
        )

        character_name = (
            scene_context.get("character_name")
            or (source_profile or {}).get("character_name")
            or (source_profile or {}).get("name")
            or "the player"
        )
        character_role = (
            scene_context.get("character_role")
            or (source_profile or {}).get("class")
            or (source_profile or {}).get("role")
            or "adventurer"
        )

        upstream_action_json = json.dumps(upstream_action_context or {})
        upstream_pending_json = json.dumps(upstream_pending_roll or {})

        # Render the Session-Zero table agreements (lines/veils) into a
        # prompt block the GM ReAct loop must respect. Empty lists collapse
        # to an empty string so the signature field stays optional.
        agreements_block = ""
        if isinstance(scene_context, dict):
            agreements = scene_context.get("agreements") or {}
            if isinstance(agreements, dict):
                lines = [
                    str(item).strip()
                    for item in (agreements.get("lines") or [])
                    if str(item).strip()
                ]
                veils = [
                    str(item).strip()
                    for item in (agreements.get("veils") or [])
                    if str(item).strip()
                ]
                if lines or veils:
                    block_parts: list[str] = []
                    if lines:
                        block_parts.append("Lines: " + "; ".join(lines))
                    if veils:
                        block_parts.append("Veils: " + "; ".join(veils))
                    agreements_block = "\n".join(block_parts)

        # Install the loop-bridge so async tools can resolve.
        set_loop_bridge(build_loop_bridge_from_running_loop())

        try:
            tools = GM_TOOLS()
            react_module = self._get_react_module(tools)

            def _predict() -> Any:
                # DSPy ReAct runs synchronously inside asyncio.to_thread.
                # We install the dspy context for the GMAgent's role.
                from monitor_data.schemas.llm_config import ModelRole

                from monitor_agents.dspy_runtime import dspy_context_for

                with dspy_context_for("gm_agent", ModelRole.STANDARD):
                    return self._predict_react(
                        react_module,
                        user_input=user_input or "",
                        character_name=character_name,
                        character_role=character_role,
                        play_mode=play_mode or "dice_game_system",
                        roll_mode=roll_mode or "normal",
                        established_facts="\n".join(f"- {f}" for f in established) or "(none yet)",
                        scene_entities=entities_text or "(none)",
                        recent_turns=recent_turns_text or "(none)",
                        upstream_action_context=upstream_action_json,
                        upstream_pending_roll=upstream_pending_json,
                        table_agreements=agreements_block,
                    )

            try:
                pred = await asyncio.to_thread(_predict)
                verdict = gmverdict_from_prediction(
                    pred,
                    upstream_action_context=upstream_action_context,
                    upstream_pending_roll=upstream_pending_roll,
                )
                # Stamp metadata so the Resolver can attribute tool calls.
                log.info(
                    "gm_agent.react.complete",
                    scene_id=str(scene_id),
                    tool_call_count=verdict.tool_call_count,
                    tool_failures=len(verdict.tool_failures),
                )
                return verdict
            except Exception as exc:
                log.warning(
                    "gm_agent.react.failed",
                    scene_id=str(scene_id),
                    error=str(exc),
                    fallback="gm_awareness_seed",
                )
                # Fall through to GMAwareness seed.
                return await self._fallback_via_seed(
                    user_input=user_input,
                    scene_context=scene_context,
                    source_profile=source_profile,
                    play_mode=play_mode,
                    roll_mode=roll_mode,
                    established_facts=established,
                    upstream_action_context=upstream_action_context,
                )
        except Exception as exc:
            log.error("gm_agent.decide.failed", scene_id=str(scene_id), error=str(exc))
            # Last-resort fallback. Never raise.
            return GMVerdict(
                intent_type=IntentType.ACTION,
                action_type=ActionType.NONE,
                roll_necessity=RollNecessity.PROPOSE_ROLL,
                causality_action=CausalityAction.ACCEPT,
                reasoning=f"GMAgent unreachable: {exc}",
            )

    async def _fallback_via_seed(
        self,
        user_input: str,
        scene_context: dict[str, Any],
        source_profile: dict[str, Any] | None,
        play_mode: str,
        roll_mode: str,
        established_facts: list[str],
        upstream_action_context: dict[str, Any] | None,
    ) -> GMVerdict:
        """Fall back to the deterministic GMAwarenessModule when ReAct fails."""
        try:
            awareness = await check_gm_awareness(
                agent=self,
                user_input=user_input,
                scene_context=scene_context,
                play_mode=play_mode,
                established_facts=established_facts,
                roll_mode=roll_mode,
            )
            return gmverdict_from_awareness(awareness, upstream_action_context=upstream_action_context)
        except Exception as exc:
            log.error("gm_agent.fallback.failed", error=str(exc))
            return GMVerdict(
                intent_type=IntentType.ACTION,
                action_type=ActionType.NONE,
                roll_necessity=RollNecessity.PROPOSE_ROLL,
                causality_action=CausalityAction.ACCEPT,
                reasoning=f"GMAgent fallback failed: {exc}",
            )


# Public factory ----------------------------------------------------------------


def default_gm_agent() -> GMAgent:
    """Process-wide singleton GMAgent."""
    global _GMAgentSingleton
    if _GMAgentSingleton is None:
        _GMAgentSingleton = GMAgent()
    return _GMAgentSingleton


def reset_gm_agent() -> None:
    """Reset the GMAgent singleton (test isolation)."""
    global _GMAgentSingleton
    _GMAgentSingleton = None
    reset_tools()


_GMAgentSingleton: GMAgent | None = None
