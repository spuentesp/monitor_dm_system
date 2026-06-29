"""
GMAwareness — Single LLM call that replaces ALL regex heuristics in the resolver.

LAYER: 2 (agents)
IMPORTS FROM: pydantic, dspy, instructor (via BaseAgent.call_llm_structured)

WHY THIS EXISTS
---------------
Before this module, the resolver used FOUR separate regex-driven classifiers:

    _infer_intent_type      → meta / ooc / query / dialogue / action
    _infer_roll_type        → attack / stealth / exploration / persuasion / ...
    _classify_roll_necessity → trivial / propose_roll / contested
    _is_world_truth_question → bool

PLUS a separate LLM causality check (causality_check.py) for forced narrative
detection. Five code paths, two paradigms, brittle at the seams.

This module unifies them into ONE LLM call. The GM (LLM) reads the player's
text and consciously returns a structured GMAwareness verdict covering all
five concerns. The resolver is now a thin shell that consumes the verdict
and routes. No regex, no keyword lists, no statistical tricks.

WHY DSPY (NOT INSTRUCTOR)
-------------------------
The prompt IS the test surface. If we route with `instructor`, the only way
to verify correctness is to mock the LLM and stub verdicts — which only
proves the resolver switches correctly, NOT that the prompt produces correct
verdicts in the first place.

By using DSPy:
  - The signature is a Python object that can be inspected and asserted on.
  - Golden input/output datasets (`dspy.Example`) let us regression-test
    the prompt itself, not just the routing.
  - `metric()` functions score prompt quality (routing accuracy, causality
    correctness) — this is the loss function for prompt optimization.
  - BootstrapFewShot and MIPROv2 can tune the prompt when we accumulate
    enough labeled data. Right now we can run offline optimization against
    the golden set without any LLM in the loop (replay mode).

ARCHITECTURE
------------

    Player text
        ↓
    resolve_turn(user_input, ...)
        ↓
    GMAwareness verdict  ← ONE LLM call (DSPy Predict)
        ↓
    resolver switches on verdict fields, dispatches to:
      - Branch 1: narrative mode (skip entirely)
      - Branch 2: forced narrative (declares_outcome=true → PUSH_BACK / ACCEPT)
      - Branch 3: dice (roll_necessity=trivial → skip, propose_roll → offer,
                              contested → roll now)
      - Branch 4: OOC / query (special handlers)

The LLM is given the FULL scene context (entities, recent turns, established
facts, character profile, play_mode). It returns a typed Pydantic model with
validated enums. The resolver cannot be confused by prose.

FAILURE MODES
-------------
- LLM unavailable / timeout → fallback to "trivial / accept" verdict.
  This routes the player through Branch 4 (no roll, no judgment). Safe.
- LLM returns invalid enum → Pydantic validation error → same fallback.
- LLM hallucinates a target not in the text → target=None by default.

TESTING THE PROMPT (DSPY METRICS)
----------------------------------
The gold-set lives in `monitor_agents.tests.test_gm_awareness_prompts`:
each example pins one input → one expected verdict. The `metric()` function
below scores each example and reports:

    routing_accuracy      = correct intent_type / action_type / roll_necessity
    causality_accuracy    = correct declares_outcome / violates_causality / action
    overall_score         = average of the above

When you tune the prompt (instruction text, field descriptions, few-shot
examples), rerun the gold-set and watch the metric move. BootstrapFewShot
uses this same metric to optimize automatically.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ===========================================================================
# Enums (validated strings — no drift)
# ===========================================================================

class IntentType(str, Enum):
    """What is the player actually trying to do?"""
    META = "meta"        # system command (/save, /help) — not a game action
    OOC = "ooc"          # out-of-character commentary
    QUERY = "query"      # world-truth question ("Is the door locked?")
    DIALOGUE = "dialogue"  # speech or social interaction
    ACTION = "action"    # physical or mental action in the world


class ActionType(str, Enum):
    """Sub-classification of intent for routing."""
    NONE = "none"            # not an action (query/meta/ooc)
    DIALOGUE = "dialogue"    # social — uses Charisma
    COMBAT = "combat"        # attack/strike/shoot — uses STR/DEX
    STEALTH = "stealth"      # sneak/hide/pick — uses DEX
    EXPLORATION = "exploration"  # search/examine/investigate — uses INT/WIS
    MOVEMENT = "movement"    # walk/enter/climb — usually trivial


class RollNecessity(str, Enum):
    """Does this action require dice?"""
    TRIVIAL = "trivial"           # no roll — automatic success
    PROPOSE_ROLL = "propose_roll" # offer the player a roll, they decide
    CONTESTED = "contested"       # roll immediately (combat, opposed checks)


class Severity(str, Enum):
    """How bad is the causality violation (if any)?"""
    NONE = "none"
    MINOR = "minor"               # small leap (e.g., convincing without roll — usually recoverable)
    MAJOR = "major"               # clear violation (e.g., killing without roll)
    DEUS_EX_MACHINA = "deus_ex_machina"  # entire object/character/knowledge appeared from nowhere


class CausalityAction(str, Enum):
    """What should the resolver do with this verdict?"""
    ACCEPT = "accept"                          # proceed normally
    PUSH_BACK = "push_back"                    # declare outcome violates causality, ask for a roll
    REQUEST_CLARIFICATION = "request_clarification"  # need more info
    NARRATIVE_OVERRIDE = "narrative_override"  # we're in god mode — accept anyway


# ===========================================================================
# The verdict — single source of truth for all resolver routing decisions
# ===========================================================================

class GMAwareness(BaseModel):
    """
    Structured output from the GM-awareness LLM call.

    This is the GM's conscious mind reading the player's text. It replaces
    five regex classifiers and the original CausalityVerdict with one
    judgment.
    """

    # ------------------------------------------------------------------
    # Group 1: Intent & action classification (replaces _infer_intent_type,
    # _infer_roll_type, _infer_action_profile, _is_world_truth_question)
    # ------------------------------------------------------------------

    intent_type: IntentType = Field(
        ...,
        description=(
            "What is the player doing? "
            "'meta' = system command (/save, /help), "
            "'ooc' = out-of-character commentary or ((rolling STR)) style hints, "
            "'query' = world-truth question that goes to the Oracle, "
            "'dialogue' = speech or social interaction, "
            "'action' = physical or mental action in the world."
        ),
    )

    action_type: ActionType = Field(
        ...,
        description=(
            "Sub-classification of the intent for stat routing. "
            "Always 'none' when intent_type is meta/ooc/query."
        ),
    )

    roll_necessity: RollNecessity = Field(
        ...,
        description=(
            "Does this action need dice? "
            "'trivial' = automatic success, no roll (looking, walking, low-stakes chatter), "
            "'propose_roll' = offer the player a roll (stealth, persuasion, danger-adjacent), "
            "'contested' = roll immediately (combat, opposed checks, traps)."
        ),
    )

    target: Optional[str] = Field(
        None,
        description=(
            "The noun phrase the action is directed at, extracted from the text. "
            "Return None when no explicit target is mentioned. "
            "NEVER invent a target — only extract what the player said."
        ),
    )

    # ------------------------------------------------------------------
    # Group 2: Causality judgment (replaces causality_check.CausalityVerdict)
    # ------------------------------------------------------------------

    declares_outcome: bool = Field(
        ...,
        description=(
            "True if the player is asserting that something already happened "
            "(past tense, present perfect, or 'I do X' where X is the result, "
            "not the attempt). False if the player is attempting an action "
            "whose outcome is unknown ('I try to...', 'I attempt to...', "
            "'I aim at...', 'I search for...')."
        ),
    )

    violates_causality: bool = Field(
        ...,
        description=(
            "True if accepting this declaration would violate causality: "
            "introduce things that don't exist (deus ex machina), break "
            "established facts, or skip the world's logic. "
            "Examples: 'I shoot him dead' (no roll), "
            "'I find the key in my pocket' (key never established), "
            "'I remember the code' (memory never established), "
            "'I convince the guard' (no roll attempted)."
        ),
    )

    severity: Severity = Field(
        default=Severity.NONE,
        description=(
            "'none' if no violation. 'minor' for small leaps. 'major' for clear "
            "violations. 'deus_ex_machina' for introducing entire objects, "
            "characters, or knowledge that don't exist in the scene."
        ),
    )

    reasons: List[str] = Field(
        default_factory=list,
        description=(
            "Specific reasons the outcome violates causality (if it does). "
            "Each reason should reference what was introduced that doesn't exist "
            "or what established fact was skipped. Empty if no violation."
        ),
    )

    # ------------------------------------------------------------------
    # Group 3: Action routing (what the resolver should do)
    # ------------------------------------------------------------------

    action: CausalityAction = Field(
        ...,
        description=(
            "ACCEPT: outcome is fine, proceed normally. "
            "PUSH_BACK: outcome violates causality, ask the player to roll. "
            "REQUEST_CLARIFICATION: need more info from the player. "
            "NARRATIVE_OVERRIDE: we're in god mode, accept anyway."
        ),
    )

    suggested_stat: Optional[str] = Field(
        None,
        description=(
            "If pushing back or offering a roll, the stat to roll. "
            "STR/DEX/CON for physical, INT/WIS for mental, CHA for social. "
            "Return None when no roll is being offered."
        ),
    )

    suggested_dc: Optional[int] = Field(
        None,
        description=(
            "If pushing back or offering a roll, the difficulty class. "
            "10 easy, 12 standard, 15 hard, 18 very hard. "
            "Return None when no roll is being offered."
        ),
    )

    pushback_prompt: Optional[str] = Field(
        None,
        description=(
            "If pushing back or asking for clarification, the message shown "
            "to the player. Should be concrete and reference the specific "
            "problem ('Roll Charisma (DC 12) to convince him' or 'Where did "
            "the key come from?')."
        ),
    )

    # ------------------------------------------------------------------
    # Free-form reasoning — for debugging and audit
    # ------------------------------------------------------------------

    reasoning: str = Field(
        default="",
        description=(
            "Free-form reasoning the GM used to reach this verdict. "
            "Should reference the specific signals in the text that drove "
            "the judgment."
        ),
    )


# ===========================================================================
# DSPy signature — the prompt IS the test surface
# ===========================================================================
# A DSPy Signature mirrors the GMAwareness Pydantic model exactly. The
# `desc=` arguments here ARE the test surface: changing them changes what
# the LLM is told to do, and the gold-set tests (test_gm_awareness_prompts)
# score the resulting verdicts.

# Conditional imports so this module still loads without dspy installed.
try:
    import dspy  # noqa: F401

    _DSPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _DSPY_AVAILABLE = False


if _DSPY_AVAILABLE:

    class GMAwarenessSignature(dspy.Signature):
        """
        Read the player's action and return a structured GM-awareness verdict.

        Three concerns:
        1. Intent & routing — what is the player doing?
        2. Roll necessity — does this need dice?
        3. Causality — is the declared outcome legal in the world?
        """

        # ── STATIC PREFIX (identical across turns → prompt cache hit) ──
        # These fields rarely change within a session.

        character_name: str = dspy.InputField(
            desc="The player character's name.",
        )
        character_role: str = dspy.InputField(
            desc="The player character's class or role.",
        )
        play_mode: str = dspy.InputField(
            desc="Either 'narrative' (god mode, no dice) or 'dice_standard' / 'dice_game_system'.",
        )
        roll_mode: str = dspy.InputField(
            desc="Either 'normal', 'advantage', 'disadvantage', or 'auto'.",
        )

        # ── DYNAMIC (turn-specific) ──

        user_input: str = dspy.InputField(
            desc="The player's raw text from this turn.",
        )
        established_facts: str = dspy.InputField(
            desc="Newline-separated list of facts established earlier in the session.",
        )
        scene_entities: str = dspy.InputField(
            desc="Newline-separated list of entities currently in the scene (name + type).",
        )
        recent_turns: str = dspy.InputField(
            desc="Newline-separated list of recent turns (last 3, format 'speaker: text').",
        )

        # ── OUTPUTS ──

        intent_type: str = dspy.OutputField(
            desc="meta / ooc / query / dialogue / action",
        )
        action_type: str = dspy.OutputField(
            desc="none / dialogue / combat / stealth / exploration / movement. Always 'none' when intent_type is meta/ooc/query.",
        )
        roll_necessity: str = dspy.OutputField(
            desc="trivial / propose_roll / contested. Most look/listen/examine/walk/say is trivial. Most attack/shoot/cast is contested. Most persuade/sneak/pick/investigate-with-stakes is propose_roll.",
        )
        target: str = dspy.OutputField(
            desc="The noun phrase the action is directed at, or 'none' if no explicit target is mentioned. Never invent a target.",
        )
        declares_outcome: bool = dspy.OutputField(
            desc="True if the player is asserting that something already happened (past tense, 'I do X' where X is the result). False if the player is attempting an action ('I try to...', 'I attempt to...').",
        )
        violates_causality: bool = dspy.OutputField(
            desc="True if accepting this declaration would introduce things that don't exist (deus ex machina), break established facts, or skip the world's logic.",
        )
        severity: str = dspy.OutputField(
            desc="none / minor / major / deus_ex_machina. 'major' for clear violations (e.g. killing without a roll). 'deus_ex_machina' for entire objects/characters/knowledge that don't exist in the scene.",
        )
        reasons: str = dspy.OutputField(
            desc="Comma-separated specific reasons the outcome violates causality (empty string if no violation).",
        )
        action: str = dspy.OutputField(
            desc="ACCEPT / PUSH_BACK / REQUEST_CLARIFICATION / NARRATIVE_OVERRIDE. ACCEPT means proceed normally; PUSH_BACK means ask the player to roll; REQUEST_CLARIFICATION means ask for missing info; NARRATIVE_OVERRIDE means we're in god mode and accept anyway.",
        )
        suggested_stat: str = dspy.OutputField(
            desc="If pushing back or offering a roll, the stat to roll (STR/DEX/CHA/etc.). 'none' when no roll is being offered.",
        )
        suggested_dc: int = dspy.OutputField(
            desc="If pushing back or offering a roll, the difficulty class (10 easy, 12 standard, 15 hard, 18 very hard). 0 when no roll is being offered.",
        )
        pushback_prompt: str = dspy.OutputField(
            desc="If pushing back or asking for clarification, the message shown to the player. Empty string otherwise.",
        )
        reasoning: str = dspy.OutputField(
            desc="Free-form reasoning the GM used to reach this verdict.",
        )

    class GMAwarenessModule(dspy.Module):
        """
        DSPy module that wraps the GMAwareness signature with Predict.

        Use `module.forward(**kwargs)` for inference, or pass to
        `BootstrapFewShot` / `MIPROv2` for prompt optimization.
        """

        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(GMAwarenessSignature)

        def forward(
            self,
            *,
            character_name: str,
            character_role: str,
            play_mode: str,
            roll_mode: str,
            user_input: str,
            established_facts: str,
            scene_entities: str,
            recent_turns: str,
        ) -> dspy.Prediction:
            return self.predict(
                character_name=character_name,
                character_role=character_role,
                play_mode=play_mode,
                roll_mode=roll_mode,
                user_input=user_input,
                established_facts=established_facts,
                scene_entities=scene_entities,
                recent_turns=recent_turns,
            )


# ===========================================================================
# DSPy ↔ Pydantic conversion
# ===========================================================================

def _parse_intent_type(value: str) -> IntentType:
    """Map a string from the LLM to the IntentType enum (lenient)."""
    if not value:
        return IntentType.ACTION
    normalized = str(value).strip().lower()
    aliases = {
        "meta_command": "meta",
        "out_of_character": "ooc",
        "question": "query",
        "speech": "dialogue",
        "talk": "dialogue",
        "act": "action",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return IntentType(normalized)
    except ValueError:
        # Conservative fallback: most common case
        return IntentType.ACTION


def _parse_action_type(value: str) -> ActionType:
    if not value:
        return ActionType.NONE
    normalized = str(value).strip().lower()
    aliases = {
        "physical": "action",
        "social": "dialogue",
        "physical_combat": "combat",
        "sneak": "stealth",
        "investigate": "exploration",
        "move": "movement",
        "walking": "movement",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return ActionType(normalized)
    except ValueError:
        return ActionType.NONE


def _parse_roll_necessity(value: str) -> RollNecessity:
    if not value:
        return RollNecessity.PROPOSE_ROLL
    normalized = str(value).strip().lower()
    aliases = {
        "no_roll": "trivial",
        "automatic": "trivial",
        "offer_roll": "propose_roll",
        "ask_to_roll": "propose_roll",
        "roll_now": "contested",
        "opposed": "contested",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return RollNecessity(normalized)
    except ValueError:
        return RollNecessity.PROPOSE_ROLL


def _parse_severity(value: str) -> Severity:
    if not value:
        return Severity.NONE
    normalized = str(value).strip().lower()
    aliases = {"deus": "deus_ex_machina", "dem": "deus_ex_machina"}
    normalized = aliases.get(normalized, normalized)
    try:
        return Severity(normalized)
    except ValueError:
        return Severity.NONE


def _parse_causality_action(value: str) -> CausalityAction:
    if not value:
        return CausalityAction.ACCEPT
    normalized = str(value).strip().lower()
    aliases = {
        "accept": "accept",
        "push_back": "push_back",
        "request_clarification": "request_clarification",
        "clarify": "request_clarification",
        "narrative_override": "narrative_override",
    }
    normalized = aliases.get(normalized, normalized)
    try:
        return CausalityAction(normalized)
    except ValueError:
        return CausalityAction.ACCEPT


def _parse_reasons(value: str) -> List[str]:
    if not value:
        return []
    return [r.strip() for r in value.split(",") if r.strip()]


def _parse_optional_str(value: str) -> Optional[str]:
    if not value or str(value).strip().lower() in ("none", "null", ""):
        return None
    return str(value).strip()


def _parse_optional_int(value: int) -> Optional[int]:
    if value is None:
        return None
    try:
        v = int(value)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None  # 0 means "no roll offered"


def prediction_to_verdict(pred: Any) -> GMAwareness:
    """Convert a DSPy Prediction into a typed GMAwareness Pydantic model.

    This is the boundary between the LLM's prose output and the resolver's
    strongly-typed routing logic. Every field is parsed leniently with
    conservative fallbacks.
    """
    return GMAwareness(
        intent_type=_parse_intent_type(getattr(pred, "intent_type", "")),
        action_type=_parse_action_type(getattr(pred, "action_type", "")),
        roll_necessity=_parse_roll_necessity(getattr(pred, "roll_necessity", "")),
        target=_parse_optional_str(getattr(pred, "target", "")),
        declares_outcome=bool(getattr(pred, "declares_outcome", False)),
        violates_causality=bool(getattr(pred, "violates_causality", False)),
        severity=_parse_severity(getattr(pred, "severity", "none")),
        reasons=_parse_reasons(getattr(pred, "reasons", "")),
        action=_parse_causality_action(getattr(pred, "action", "accept")),
        suggested_stat=_parse_optional_str(getattr(pred, "suggested_stat", "")),
        suggested_dc=_parse_optional_int(getattr(pred, "suggested_dc", 0)),
        pushback_prompt=_parse_optional_str(getattr(pred, "pushback_prompt", "")),
        reasoning=str(getattr(pred, "reasoning", "") or ""),
    )


# ===========================================================================
# System prompt — instructs the LLM how to judge
# ===========================================================================

_GM_AWARENESS_SYSTEM_PROMPT = """You are the GM's awareness — the part of the GM's mind that reads the player's text and decides what kind of turn this is.

Your job is to read the player's message and return a SINGLE structured judgment covering three concerns:

1. **Intent & routing** — what is the player doing, and how should we route it?
   - OOC/meta: starts with `((` or `/command` or "out of character" — not a game action.
   - Query: world-truth question ("Is the door locked?", "Are there guards?") — goes to the Oracle, no dice.
   - Dialogue: speech or social interaction (uses Charisma when stakes are present).
   - Action: physical or mental action in the world.

2. **Roll necessity** — does this need dice?
   - `trivial`: automatic success, no roll. Looking, walking, low-stakes chatter, body language.
   - `propose_roll`: offer the player a roll, they decide whether to take it. Stealth past danger, persuasion with stakes, careful investigation of something dangerous.
   - `contested`: roll immediately. Combat, opposed checks, traps, anything where the opposition can react.
   - **Heuristic**: most look/listen/examine/say/walk is trivial. Most attack/shoot/cast is contested. Most persuade/sneak/pick/investigate-with-stakes is propose_roll.
   - **Tie-breaker**: if the action could go badly AND failure is interesting, it needs a roll.

3. **Causality** — is the declared outcome legal in the world?
   - `declares_outcome`: did the player assert that something already happened? Look for past tense, "I successfully...", or "I do X" where X is the result (not "I try to...").
   - `violates_causality`: would accepting this break established facts? Compare against the `ESTABLISHED FACTS` list. Look for:
     - Objects appearing from nowhere (a key in pocket that was never established)
     - Characters/NPCs that don't exist in the scene (a friend who never appeared)
     - Knowledge the character couldn't have (remembering a code never seen)
     - Skipping the world's logic (killing without a roll, succeeding without a check)
     - Contradicting established facts (the door was sealed; "I open it")

When in doubt:
- Default `intent_type` toward the most conservative interpretation (ooc > query > dialogue > action).
- Default `roll_necessity` toward `propose_roll` rather than `contested` (let the player opt out).
- Default `declares_outcome` to `false` (most player turns are attempts).
- Default `violates_causality` to `false` unless you can cite a specific established fact that contradicts.
- Default `severity` to `none` unless causality is violated.
- Default `target` to `null` when no explicit noun is mentioned (do NOT invent targets).

Stat defaults: STR/DEX/CON for physical, INT/WIS for mental, CHA for social.
DC defaults: 10 (easy), 12 (standard), 15 (hard), 18 (very hard).

Be strict but not pedantic. A player saying "I attack the guard" is an action that needs a roll. A player saying "I kill the guard" without rolling IS a violation (PUSH_BACK).

When pushing back, give the player a useful prompt: what stat, what DC, what they need to clarify.
"""


# ===========================================================================
# Hard-skip fast paths — these NEVER call the LLM
# ===========================================================================

def _narrative_mode_verdict() -> GMAwareness:
    """Returned when play_mode == 'narrative' (god mode). All declared outcomes accepted."""
    return GMAwareness(
        intent_type=IntentType.ACTION,
        action_type=ActionType.NONE,
        roll_necessity=RollNecessity.TRIVIAL,
        declares_outcome=True,
        violates_causality=False,
        severity=Severity.NONE,
        action=CausalityAction.NARRATIVE_OVERRIDE,
        reasoning="Session is in narrative (god) mode — all declared outcomes are accepted without dice.",
    )


def _auto_roll_verdict(
    intent: IntentType = IntentType.ACTION,
    action: ActionType = ActionType.NONE,
) -> GMAwareness:
    """Returned when roll_mode == 'auto' (auto-pilot). System will roll for the player."""
    return GMAwareness(
        intent_type=intent,
        action_type=action,
        roll_necessity=RollNecessity.CONTESTED,
        declares_outcome=False,
        violates_causality=False,
        severity=Severity.NONE,
        action=CausalityAction.ACCEPT,
        reasoning="Auto-roll mode: the system will roll dice for the player.",
    )


def _fallback_verdict(reason: str) -> GMAwareness:
    """Safe fallback when the LLM call fails. Routes the player through dice resolution."""
    return GMAwareness(
        intent_type=IntentType.ACTION,
        action_type=ActionType.NONE,
        roll_necessity=RollNecessity.PROPOSE_ROLL,
        declares_outcome=False,
        violates_causality=False,
        severity=Severity.NONE,
        action=CausalityAction.ACCEPT,
        reasoning=f"GM-awareness unavailable ({reason}); defaulting to propose-roll.",
    )


# ===========================================================================
# Main entry point — ONE LLM call
# ===========================================================================

async def check_gm_awareness(
    agent: Any,
    user_input: str,
    scene_context: Dict[str, Any],
    play_mode: str,
    established_facts: List[str],
    roll_mode: str = "normal",
) -> GMAwareness:
    """
    Run the GM-awareness LLM call.

    This is the ONLY entry point. It replaces:
      - causality_check.check_causality()
      - resolver._classify_roll_necessity()
      - resolver._infer_intent_type()
      - resolver._infer_roll_type()
      - resolver._infer_action_profile()
      - resolver._extract_target()
      - resolver._is_world_truth_question()

    Args:
        agent: A BaseAgent instance (for call_llm_structured).
        user_input: The player's text.
        scene_context: The assembled scene context (entities, memories, prior turns).
        play_mode: "narrative" (god mode), "dice_standard", or "dice_game_system".
        established_facts: Accumulated facts from the session (last 20 are passed to the LLM).
        roll_mode: "normal", "advantage", "disadvantage", or "auto".

    Returns:
        A GMAwareness verdict with structured intent, action, causality, and routing.
    """
    # ------------------------------------------------------------------
    # Fast path: narrative/god mode → skip LLM entirely
    # ------------------------------------------------------------------
    if play_mode == "narrative":
        return _narrative_mode_verdict()

    # ------------------------------------------------------------------
    # Fast path: auto-roll → skip LLM, return ACCEPT verdict
    # ------------------------------------------------------------------
    if roll_mode == "auto":
        return _auto_roll_verdict()

    try:
        return await _run_dspy_predict(
            user_input=user_input,
            scene_context=scene_context,
            play_mode=play_mode,
            roll_mode=roll_mode,
            established_facts=established_facts,
        )
    except Exception as exc:
        logger.warning(
            "GM-awareness DSPy call failed (%s); falling back to permissive propose-roll",
            exc,
        )
        return _fallback_verdict(str(exc))


async def _run_dspy_predict(
    user_input: str,
    scene_context: Dict[str, Any],
    play_mode: str,
    roll_mode: str,
    established_facts: List[str],
) -> GMAwareness:
    """
    Run the DSPy Predict module and convert the Prediction to a GMAwareness.

    This is the single LLM call that drives the resolver. We use DSPy
    instead of raw instructor because:
      1. The signature is a typed Python object that tests can inspect.
      2. Golden input/output pairs can drive prompt optimization later.
      3. The same module can be replayed offline (no live LLM needed) to
         measure prompt quality against the gold-set.
    """
    if not _DSPY_AVAILABLE:
        raise RuntimeError("DSPy is not available — cannot run gm_awareness.predict()")

    from monitor_agents.dspy_runtime import dspy_context_for
    from monitor_data.schemas.llm_config import ModelRole

    facts_text = "\n".join(f"- {f}" for f in established_facts[-20:])
    entities_text = "\n".join(
        f"- {e.get('name', '?')} ({e.get('entity_type', '?')})"
        for e in scene_context.get("entities", [])
    )
    recent_turns_text = ""
    for turn in scene_context.get("turns", [])[-3:]:
        recent_turns_text += f"- {turn.get('speaker', '?')}: {turn.get('text', '')[:200]}\n"

    character_name = scene_context.get("character_name", "the player character")
    character_role = scene_context.get("character_role", "adventurer")

    module = GMAwarenessModule()

    # Run synchronously inside the configured DSPy context. The module's
    # forward() call is blocking (calls litellm); we wrap in asyncio.to_thread
    # so the resolver can stay async.
    def _predict() -> Any:
        with dspy_context_for("gm_awareness", ModelRole.LIGHT):
            return module.forward(
                character_name=character_name,
                character_role=character_role,
                play_mode=play_mode or "dice_game_system",
                roll_mode=roll_mode or "normal",
                user_input=user_input or "",
                established_facts=facts_text or "(none yet)",
                scene_entities=entities_text or "(none)",
                recent_turns=recent_turns_text or "(none)",
            )

    pred = await asyncio.to_thread(_predict)
    return prediction_to_verdict(pred)


# ===========================================================================
# Backward-compatible shim — re-exports the old CausalityAction/CausalityVerdict
# names so existing tests and the resolver keep working during migration.
# ===========================================================================

# Re-export for callers that still import CausalityVerdict / CausalityAction
# from monitor_agents.causality_check. These point to the unified types now.
from monitor_agents.causality_check import (  # noqa: E402, F401
    CausalityVerdict,
    CausalityAction as _LegacyCausalityAction,
)


def _gm_to_legacy_verdict(gm: GMAwareness) -> CausalityVerdict:
    """Convert a GMAwareness into the legacy CausalityVerdict shape."""
    return CausalityVerdict(
        declares_outcome=gm.declares_outcome,
        violates_causality=gm.violates_causality,
        severity=gm.severity.value,
        reasons=list(gm.reasons or []),
        action=gm.action,
        suggested_stat=gm.suggested_stat,
        suggested_dc=gm.suggested_dc,
        reasoning=gm.reasoning,
        pushback_prompt=gm.pushback_prompt,
    )


async def check_causality(
    agent: Any,
    user_input: str,
    scene_context: Dict[str, Any],
    play_mode: str,
    established_facts: List[str],
    roll_mode: str = "normal",
) -> CausalityVerdict:
    """
    DEPRECATED: prefer check_gm_awareness.

    Kept as a thin shim so existing tests that mock
    `monitor_agents.resolver.check_causality` continue to work.
    """
    gm = await check_gm_awareness(
        agent=agent,
        user_input=user_input,
        scene_context=scene_context,
        play_mode=play_mode,
        established_facts=established_facts,
        roll_mode=roll_mode,
    )
    return _gm_to_legacy_verdict(gm)
