"""
Resolver Agent implementation.

LAYER: 2 (agents)
Authority: MongoDB (resolutions, proposals), Character State
"""

import json
import logging
import re
from contextlib import suppress
from typing import Any, Dict, Tuple, Optional

from monitor_data.utils.dice import calculate_modifier, roll_dice

from monitor_agents.base import BaseAgent
from monitor_agents.game_system import GameSystemRuntime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword → action-profile routing (used when no GameSystemRuntime is available)
# ---------------------------------------------------------------------------

_ACTION_PROFILE_MAP: list[tuple[tuple[str, ...], str, str, int]] = [
    (
        ("ask", "say", "tell", "persuade", "convince", "threaten", "speak"),
        "dialogue",
        "Charisma",
        12,
    ),
    (
        ("search", "notice", "inspect", "track", "listen", "sense"),
        "action",
        "Wisdom",
        13,
    ),
    (("sneak", "hide", "dodge", "climb", "pick", "steal"), "action", "Dexterity", 14),
    (
        ("recall", "analyze", "analyse", "study", "decipher", "investigate"),
        "action",
        "Intelligence",
        13,
    ),
]

# Default D&D-style modifier formula used when no game-system schema is loaded
_DEFAULT_MODIFIER_FORMULA = "(VALUE - 10) // 2"

# ---------------------------------------------------------------------------
# Forced-narrative detection
# ---------------------------------------------------------------------------
# When a session is in a dice mode the player can still declare an outcome
# directly.  We look for linguistic patterns that assert success or describe
# a completed action rather than an attempt.
# Examples that trigger:  "I kill him"  "I slice through the lock and enter"
#                         "I successfully hack the terminal"  "I stab him dead"
# Examples that do NOT:  "I try to kill him"  "I attempt to sneak past"
#                        "I attack"  "I shoot at the guard"
# ---------------------------------------------------------------------------

_FORCED_NARRATIVE_RE = re.compile(
    r"""
    # Direct outcome assertion verbs
    \b(kill|killed|murder|slay|slew|destroy|destroys|destroy|
       slice|slash|cleave|stab|impale|decapitate|
       hack\s+(?:the|into|through)|break\s+(?:the|through|open)|
       pick\s+the\s+lock|open\s+the\s+(?:door|lock|safe|chest)|
       enter|walk\s+(?:in|through|past)|step\s+(?:through|over|past)|
       escape|flee\s+successfully|get\s+away)\b
    |
    # "I successfully …" pattern
    \bsuccessfully\b
    |
    # "and X dies / falls / is dead" patterns
    \b(?:he|she|it|they)\s+(?:dies|die|falls|fall|collapses|is\s+dead|are\s+dead)\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_ATTEMPT_RE = re.compile(
    r"\b(try|tries|attempt|attempts|try\s+to|attempt\s+to|go\s+to|aim\s+to|hope\s+to)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Intent classification patterns (from TurnLoop)
# ---------------------------------------------------------------------------

# OOC (Out of Character) block detection
_OOC_BLOCK_RE = re.compile(r"^\s*\(\((?P<content>.*?)\)\)\s*$", re.IGNORECASE | re.DOTALL)

# Meta command detection (starts with /)
_META_COMMAND_RE = re.compile(r"^\s*/[a-z_\-]+", re.IGNORECASE)

# Query detection (questions)
_QUERY_OPEN_RE = re.compile(
    r"^\s*(what|how|why|where|when|who|do|does|is|are|can|could|would|should)\b",
    re.IGNORECASE,
)

# Dialogue detection (direct speech or dialogue verbs)
_DIALOGUE_RE = re.compile(
    r'"[^"]+"|\b(say|ask|tell|persuade|convince|threaten|plead|negotiate|bargain)\b',
    re.IGNORECASE,
)

# Action sub-type detection
_COMBAT_RE = re.compile(
    r"\b(attack|strike|shoot|stab|slash|fight|rush|charge|punch|kick)\b", re.IGNORECASE
)
_STEALTH_RE = re.compile(r"\b(sneak|hide|slip|creep|stealth|pickpocket)\b", re.IGNORECASE)
_EXPLORE_RE = re.compile(
    r"\b(search|scan|inspect|study|notice|look|listen|investigate|track|hotwire|repair|force)\b",
    re.IGNORECASE,
)
_SOCIAL_RE = re.compile(
    r"\b(convince|persuade|threaten|charm|negotiate|ask|tell|plead|deceive|bluff)\b",
    re.IGNORECASE,
)


def _detect_forced_narrative(text: str) -> bool:
    """
    Return True when the player's input looks like a declared outcome
    rather than an attempt.

    Heuristic: matches the forced-narrative pattern AND does not contain
    an attempt qualifier (try/attempt/etc.).
    """
    if _ATTEMPT_RE.search(text):
        return False
    return bool(_FORCED_NARRATIVE_RE.search(text))


def _is_narrative_core(gsr: GameSystemRuntime | None) -> bool:
    """Return True when the loaded game system is explicitly pure narrative."""
    if gsr is None:
        return False
    return str(gsr._sd.core.get("type", "")).lower() == "narrative"


def _classify_roll_necessity(user_input: str, action_type: str, intent_type: str) -> str:
    """
    Classify whether a dice roll is needed for this action.

    Returns one of:
      "trivial"       — automatic success, no roll needed (looking, walking, talking)
      "propose_roll"  — GM should offer a roll, player chooses
      "contested"     — roll immediately (combat, traps, opposed checks)

    TTRPG craft principle (DiS, VtM20, PbtA):
    - Only roll when failure would be interesting AND outcome is uncertain
    - Never roll for info the character would automatically have
    - Never roll for low-stakes social interaction
    """
    text = (user_input or "").strip().lower()

    # OOC / queries never need dice
    if intent_type == "query":
        return "trivial"

    # Dialogue without stakes is trivial
    _STAKES_KEYWORDS = (
        "convince",
        "persuade",
        "threaten",
        "intimidate",
        "lie",
        "deceive",
        "bluff",
        "manipulate",
        "charm",
        "taunt",
        "provoke",
    )
    if action_type == "dialogue":
        if any(kw in text for kw in _STAKES_KEYWORDS):
            return "propose_roll"
        return "trivial"

    # Passive / low-stakes actions are trivial
    _TRIVIAL_PATTERNS = (
        r"\b(look|look around|examine|observe|listen|smell|feel|check|inspect|"
        r"read|search|scan|watch|notice|sense)\b",
        r"\b(walk|go|move|enter|leave|open|close|sit|stand)\b",
        r"\b(say|tell|ask|answer|respond|nod|shake)\b",
        r"\b(wait|rest|think|consider|ponder|recall|remember)\b",
    )
    for pattern in _TRIVIAL_PATTERNS:
        if re.search(pattern, text):
            # But if combined with danger, upgrade to propose_roll
            _DANGER_KEYWORDS = (
                "guard",
                "trap",
                "enemy",
                "danger",
                "risk",
                "trap",
                "combat",
                "fight",
                "battle",
                "chase",
                "pursue",
                "sneak",
                "hide",
                "steal",
                "pickpocket",
                "lock",
            )
            if any(dk in text for dk in _DANGER_KEYWORDS):
                return "propose_roll"
            return "trivial"

    # Combat / contested / high-stakes actions are contested
    _CONTESTED_PATTERNS = (
        r"\b(attack|strike|hit|shoot|stab|slash|kick|punch|cast)\b",
        r"\b(block|parry|dodge|deflect|counter)\b",
        r"\b(race|compete|arm wrestle)\b",
    )
    for pattern in _CONTESTED_PATTERNS:
        if re.search(pattern, text):
            return "contested"

    # Default: propose a roll (let the player decide)
    return "propose_roll"


def _uses_roll_under(gsr: GameSystemRuntime | None) -> bool:
    """Detect roll-under d20 systems from the stored core mechanic text."""
    if gsr is None:
        return False
    core = gsr._sd.core
    text = " ".join(
        str(core.get(key, "")) for key in ("formula", "success_threshold", "critical_success")
    ).lower()
    return "roll under" in text or "under or equal" in text or "<=" in text


def _resolve_base_dc(gsr: GameSystemRuntime | None, fallback_dc: int) -> int:
    """Prefer the system's declared base target when one is embedded in the mechanic text."""
    if gsr is None:
        return fallback_dc
    core = gsr._sd.core
    text = " ".join(str(core.get(key, "")) for key in ("formula", "success_threshold")).lower()
    if not text:
        return fallback_dc

    # Ignore dice notation like 1d20 so we can pick out the real target number.
    text = re.sub(r"\b\d*d\d+\b", " ", text)
    match = re.search(r"\b(\d{1,2})\b", text)
    if not match:
        return fallback_dc

    try:
        target = int(match.group(1))
    except ValueError:
        return fallback_dc

    return target if 2 <= target <= 20 else fallback_dc


def _strip_ooc_wrappers(text: str) -> str:
    """Remove OOC block wrappers ((...)) from text."""
    raw = (text or "").strip()
    match = _OOC_BLOCK_RE.match(raw)
    return (match.group("content") if match else raw).strip()


def _extract_target(text: str) -> str:
    """Extract the target of an action from user input."""
    lowered = _strip_ooc_wrappers(text).lower()
    for pattern in (
        r"\b(?:the|at|toward|towards|to|from)\s+([a-z][a-z0-9_\-']{2,})",
        r"\bwith\s+([a-z][a-z0-9_\-']{2,})",
    ):
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    if "?" in lowered:
        if "duke" in lowered:
            return "duke"
        if "guard" in lowered:
            return "guard"
        if "hatch" in lowered:
            return "hatch"
        return "environment"
    return "none"


def _infer_roll_type(text: str, action_type: str, intent_type: str) -> str:
    """
    Determine the specific roll type for an action.

    Returns one of: attack, stealth, exploration, persuasion, dialogue, information, action, none
    """
    stripped = _strip_ooc_wrappers(text).lower()

    # Meta and OOC never need rolls
    if intent_type in ("meta", "ooc"):
        return "none"

    # Query rolls are information-gathering
    if intent_type == "query":
        if _SOCIAL_RE.search(stripped):
            return "persuasion"
        if _EXPLORE_RE.search(stripped):
            return "exploration"
        return "information"

    # Dialogue actions use persuasion or dialogue
    if action_type == "dialogue":
        return "persuasion"

    # Combat actions
    if _COMBAT_RE.search(stripped):
        return "attack"

    # Stealth actions
    if _STEALTH_RE.search(stripped):
        return "stealth"

    # Exploration actions
    if _EXPLORE_RE.search(stripped):
        return "exploration"

    # Default: generic action
    return "action"


def _is_world_truth_question(text: str) -> bool:
    """
    Return True if the text is a binary world-truth question.
    (e.g., "Is the door locked?", "Are there guards?")
    """
    # Strip OOC markers like ((Likely)) for the check
    clean_text = re.sub(r"\(\(.*\)\)", "", text).strip().lower()
    if not clean_text.endswith("?"):
        return False

    # Binary question starters
    starters = ("is ", "are ", "do ", "does ", "was ", "were ", "can ", "could ", "has ", "have ")
    return any(clean_text.startswith(s) for s in starters)


def _infer_likelihood(text: str):
    """
    Infer likelihood from OOC markers like ((Likely)).
    Defaults to FIFTY_FIFTY.
    """
    from monitor_agents.oracle import Likelihood

    mapping = {
        "certain": Likelihood.CERTAIN,
        "nearly certain": Likelihood.NEARLY_CERTAIN,
        "very likely": Likelihood.VERY_LIKELY,
        "likely": Likelihood.LIKELY,
        "50/50": Likelihood.FIFTY_FIFTY,
        "unlikely": Likelihood.UNLIKELY,
        "very unlikely": Likelihood.VERY_UNLIKELY,
        "nearly impossible": Likelihood.NEARLY_IMPOSSIBLE,
        "impossible": Likelihood.IMPOSSIBLE,
    }

    match = re.search(r"\(\((.*?)\)\)", text)
    if match:
        val = match.group(1).lower().strip()
        if val in mapping:
            return mapping[val]

    return Likelihood.FIFTY_FIFTY


def _infer_intent_type(text: str, action_type: str) -> str:
    """
    Infer the intent type for a user input.

    Returns one of: meta, ooc, query, dialogue, action
    """
    text = (text or "").strip()
    normalized = _strip_ooc_wrappers(text)
    lowered = normalized.lower()

    # Empty input
    if not lowered:
        return "meta"

    # Meta commands (start with /)
    if _META_COMMAND_RE.match(lowered):
        return "meta"

    # OOC blocks
    if _OOC_BLOCK_RE.match(text) or "out of character" in lowered or lowered.startswith("ooc"):
        return "ooc"

    # Queries (questions)
    if text.endswith("?") or _QUERY_OPEN_RE.match(lowered):
        return "query"

    # Dialogue
    if action_type == "dialogue" or _DIALOGUE_RE.search(lowered):
        return "dialogue"

    # Default: action
    return "action"


def _build_risk_preview(action_type: str, stat_name: str | None, dc: int | None) -> str:
    """Return a short player-facing summary of what is at stake for this move."""
    stat_label = stat_name or "the relevant approach"
    dc_hint = f" around DC {dc}" if dc is not None else ""

    if action_type == "dialogue":
        return (
            f"Social pressure is in play here: pushing with {stat_label} can win leverage, "
            f"but it can also expose motives or harden the other side{dc_hint}."
        )
    if action_type == "query":
        return (
            "This is a clarification beat: the main risk is acting on incomplete information. "
            "Use the answer to decide whether to commit, retreat, or change approach."
        )
    return (
        f"This move carries concrete danger: failure can cost position, time, or resources, "
        f"and the check is likely to hinge on {stat_label}{dc_hint}."
    )


def _build_consequence_options(action_type: str, success_level: str) -> list[str]:
    """Offer player-facing consequence choices for mixed or pressured outcomes."""
    if success_level == "partial_success":
        if action_type == "dialogue":
            return [
                "Get the answer, but reveal a vulnerability.",
                "Hold your ground, but raise the NPC's suspicion.",
                "Keep the exchange calm, but lose momentum or leverage.",
            ]
        return [
            "Succeed, but spend extra time or a limited resource.",
            "Succeed, but attract danger or unwanted attention.",
            "Pull back to stay safe and give up immediate momentum.",
        ]

    if success_level in {"failure", "critical_failure"}:
        return [
            "Push through and accept a sharper setback.",
            "Back off, regroup, and try a different approach.",
            "Ask for more information before escalating the risk.",
        ]

    if success_level == "critical_success":
        return [
            "Press the advantage for extra information or position.",
            "Take the clean win and keep the scene stable.",
        ]

    return []


class Resolver(BaseAgent):
    """
    Agent responsible for resolving rules, mechanic checks, and character state changes.
    """

    def __init__(self, agent_id: str = "resolver-cli-1") -> None:
        super().__init__(agent_type="Resolver", agent_id=agent_id)

    async def run(self) -> None:
        pass

    def _infer_action_profile(self, user_input: str) -> Tuple[str, str, int]:
        """
        Route action text to (action_type, stat_name, dc) without a game-system schema.

        Used as the fallback for ``dice_standard`` mode (no GameSystemRuntime loaded).
        Returns ``("action", "Strength", 12)`` when no keyword matches.
        """
        text = user_input.lower()
        for keywords, action_type, stat, dc in _ACTION_PROFILE_MAP:
            if any(kw in text for kw in keywords):
                return action_type, stat, dc
        return "action", "Strength", 12

    def _evaluate_scenery_and_conditions(
        self,
        context: Dict[str, Any] | None,
        user_input: str,
        roll_mode: str = "normal",
        gsr: Optional["GameSystemRuntime"] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate actor conditions and active location scenery in the scene context.
        Calculates dynamic roll modifiers and resolves the actual roll mode.
        If a GameSystemRuntime is provided, delegates to it for system-specific logic.
        """
        if gsr:
            return gsr.evaluate_scenery_and_conditions(context, user_input, roll_mode)

        # Base case (no modifiers) when no GameSystemRuntime is available
        return {
            "total_modifier": 0,
            "cond_modifier": 0,
            "scenery_modifier": 0,
            "roll_mode": roll_mode,
            "has_advantage": roll_mode == "advantage",
            "has_disadvantage": roll_mode == "disadvantage",
            "reasons": [],
            "conditions": [],
        }

    async def resolve_turn(
        self,
        scene_id: str,
        user_input: str,
        context: Dict[str, Any] | None = None,
        game_context: Dict[str, Any] | None = None,
        play_mode: str = "dice_game_system",
        roll_mode: str = "normal",
        tension_score: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Resolve a full player turn for the SceneLoop.

        ``play_mode`` controls resolution behaviour:
        - ``"narrative"``        — pure fiction, no dice ever
        - ``"dice_standard"``    — d20 + modifier, no game-system schema
        - ``"dice_game_system"`` — schema-driven dice via GameSystemRuntime

        ``roll_mode`` controls advantage/disadvantage:
        - ``"normal"``       — standard 1d20 roll
        - ``"advantage"``    — roll 2d20, keep highest
        - ``"disadvantage"`` — roll 2d20, keep lowest

        In both dice modes the player can assert a narrative outcome directly
        (forced narrative); those turns are flagged so the GM can review them.
        """
        context = context or {}
        source_profile = context.get("source_profile", {}) if isinstance(context, dict) else {}

        # Auto-roll mode (solo / automated play): instead of pausing to ask the
        # player to roll (propose_roll → "pending"), the resolver rolls the dice
        # itself and returns a real outcome. Downstream advantage logic still
        # expects normal/advantage/disadvantage, so normalise roll_mode here.
        auto_roll = roll_mode == "auto"
        if auto_roll:
            roll_mode = "normal"

        # Infer intent type first (needed for all branches)
        # Get initial action_type for intent inference (will be refined later for dice branches)
        initial_action_type = "action"
        intent_type = _infer_intent_type(user_input or "", initial_action_type)

        # P-18: Oracle check for world-truth questions
        if intent_type == "query" and _is_world_truth_question(user_input or ""):
            from monitor_agents.oracle import Oracle

            oracle = Oracle()
            likelihood = _infer_likelihood(user_input or "")
            oracle_res = oracle.resolve_question(
                question=user_input or "", likelihood=likelihood, tension_score=tension_score
            )
            return {
                "scene_id": scene_id,
                "action_type": "query",
                "intent_type": "query",
                "resolution_type": "oracle",
                "oracle_result": oracle_res,
                "success": oracle_res["is_yes"],
                "success_level": oracle_res["outcome"],
                "narrative_pressure": "increased" if oracle_res["is_exceptional"] else "stable",
                "proposals": [],
            }

        # Calculate roll_type, intent_target, and requires_clarification
        roll_type = _infer_roll_type(user_input or "", initial_action_type, intent_type)
        intent_target = _extract_target(user_input or "")
        requires_clarification = intent_type in ("meta", "ooc", "query")

        # ------------------------------------------------------------------
        # Branch 1 — Pure narrative mode: never roll dice
        # ------------------------------------------------------------------
        if play_mode == "narrative":
            return {
                "scene_id": scene_id,
                "action_type": "action",
                "intent_type": intent_type,
                "roll_type": roll_type,
                "intent_target": intent_target,
                "requires_clarification": requires_clarification,
                "stat": None,
                "difficulty_class": None,
                "attribute_value": None,
                "modifier": None,
                "roll_total": None,
                "roll_breakdown": "narrative — no roll",
                "resolution_type": "narrative",
                "forced_narrative": False,
                "success": True,
                "success_level": "success",
                "effects": ["fiction_advances"],
                "risk_preview": _build_risk_preview(intent_type, None, None),
                "consequence_options": [],
                "requires_player_choice": False,
                "narrative_pressure": "steady",
                "proposals": [],
            }

        # ------------------------------------------------------------------
        # Branch 2 — Forced narrative (dice mode, player declares outcome)
        # ------------------------------------------------------------------
        if _detect_forced_narrative(user_input or ""):
            # P-20: Forced Narrative Pushback
            # If stakes are high, we might want to push back and ask for a roll.
            # Heuristic: if action_type is dialogue with stakes or combat, it's high stakes.
            initial_action_type, _, _ = self._infer_action_profile(user_input or "")

            # Use same logic as _classify_roll_necessity but for forced narrative
            necessity = _classify_roll_necessity(user_input or "", initial_action_type, intent_type)

            if necessity in ("contested", "propose_roll") and not auto_roll:
                # Push back!
                return {
                    "scene_id": scene_id,
                    "action_type": initial_action_type,
                    "intent_type": intent_type,
                    "roll_type": roll_type,
                    "intent_target": intent_target,
                    "requires_clarification": False,
                    "stat": None,
                    "difficulty_class": None,
                    "resolution_type": "forced_narrative_pushback",
                    "forced_narrative": True,
                    "success": None,
                    "success_level": "pending",
                    "pushback_prompt": (
                        "That's a bold claim! The stakes are high here—would you like to "
                        "roll for it, or are you sure you want to bypass the dice?"
                    ),
                    "requires_player_choice": True,
                    "narrative_pressure": "spiking",
                    "proposals": [],
                }

            return {
                "scene_id": scene_id,
                "action_type": "action",
                "intent_type": intent_type,
                "roll_type": roll_type,
                "intent_target": intent_target,
                "requires_clarification": requires_clarification,
                "stat": None,
                "difficulty_class": None,
                "attribute_value": None,
                "modifier": None,
                "roll_total": None,
                "roll_breakdown": "forced narrative — player declared outcome",
                "resolution_type": "forced_narrative",
                "forced_narrative": True,
                "success": True,
                "success_level": "success",
                "effects": ["fiction_advances"],
                "risk_preview": _build_risk_preview(intent_type, None, None),
                "consequence_options": [],
                "requires_player_choice": False,
                "narrative_pressure": "surging",
                "proposals": [],
            }

        # ------------------------------------------------------------------
        # Branch 3 — Dice resolution (dice_standard or dice_game_system)
        # ------------------------------------------------------------------
        gsr: GameSystemRuntime | None = None
        if play_mode == "dice_game_system" and game_context:
            with suppress(Exception):
                gsr = GameSystemRuntime(game_context)

        # Action routing and modifier calculation via schema (dice_game_system)
        # or simple generic fallback (dice_standard)
        if _is_narrative_core(gsr):
            return {
                "scene_id": scene_id,
                "action_type": "action",
                "intent_type": intent_type,
                "roll_type": roll_type,
                "intent_target": intent_target,
                "requires_clarification": requires_clarification,
                "stat": None,
                "difficulty_class": None,
                "attribute_value": None,
                "modifier": None,
                "roll_total": None,
                "roll_breakdown": "narrative system — no roll",
                "resolution_type": "narrative",
                "forced_narrative": False,
                "success": True,
                "success_level": "success",
                "effects": ["fiction_advances"],
                "risk_preview": _build_risk_preview(intent_type, None, None),
                "consequence_options": [],
                "requires_player_choice": False,
                "narrative_pressure": "steady",
                "proposals": [],
                "subsystem_hint": None,
            }

        subsystem_hint = None
        if gsr:
            routed = gsr.infer_action_context(user_input, source_profile=source_profile)
            action_type = str(routed.get("action_type", "action"))
            stat_name = str(routed.get("stat_name", "STR"))
            dc = _resolve_base_dc(gsr, int(routed.get("difficulty_class", 12)))
            subsystem_hint = routed.get("subsystem_hint")
        else:
            action_type, stat_name, dc = self._infer_action_profile(user_input or "")
            subsystem_hint = "social" if action_type == "dialogue" else None

        # ------------------------------------------------------------------
        # Roll necessity classification (UC-GM-6)
        # Only roll when failure would be interesting and outcome uncertain.
        # A selected dice-backed system controls *how* to roll, not whether
        # ordinary risky actions bypass player consent.
        # ------------------------------------------------------------------
        intent_type = _infer_intent_type(user_input or "", action_type)
        roll_necessity = _classify_roll_necessity(user_input or "", action_type, intent_type)
        if roll_necessity == "trivial":
            return {
                "scene_id": scene_id,
                "action_type": action_type,
                "intent_type": intent_type,
                "roll_type": roll_type,
                "intent_target": intent_target,
                "requires_clarification": requires_clarification,
                "stat": stat_name,
                "difficulty_class": dc,
                "attribute_value": None,
                "modifier": None,
                "roll_total": None,
                "roll_breakdown": "trivial — no roll needed",
                "resolution_type": "trivial",
                "forced_narrative": False,
                "success": True,
                "success_level": "success",
                "effects": ["fiction_advances"],
                "risk_preview": "This is a routine action — no stakes beyond the narrative.",
                "consequence_options": [],
                "requires_player_choice": False,
                "narrative_pressure": "steady",
                "proposals": [],
                "subsystem_hint": subsystem_hint,
                "roll_necessity": roll_necessity,
            }

        if roll_necessity == "propose_roll" and not auto_roll:
            # Compute the stat context but do NOT roll dice.
            # The Narrator will frame the invitation for the player to accept.
            attributes = self._extract_attributes(context, gsr)
            stat_value = 0
            candidate_keys = [stat_name]
            if gsr:
                attr_def = gsr._attr_by_abbr.get(stat_name.upper(), {})
                candidate_keys.extend(
                    [
                        str(attr_def.get("name") or ""),
                        str(attr_def.get("abbreviation") or ""),
                    ]
                )
            for key in candidate_keys:
                if key and key in attributes:
                    stat_value = int(attributes.get(key, 0))
                    break
            modifier = (
                gsr.calc_modifier(stat_name, stat_value)
                if gsr
                else calculate_modifier(stat_value, _DEFAULT_MODIFIER_FORMULA)
            )

            return {
                "scene_id": scene_id,
                "action_type": action_type,
                "intent_type": intent_type,
                "roll_type": roll_type,
                "intent_target": intent_target,
                "requires_clarification": requires_clarification,
                "stat": stat_name,
                "difficulty_class": dc,
                "attribute_value": stat_value,
                "modifier": modifier,
                "roll_total": None,
                "roll_breakdown": f"propose_roll — {stat_name} check (DC {dc})",
                "resolution_type": "propose_roll",
                "forced_narrative": False,
                "success": None,
                "success_level": "pending",
                "effects": [],
                "risk_preview": _build_risk_preview(intent_type, stat_name, dc),
                "consequence_options": [],
                "requires_player_choice": True,
                "narrative_pressure": "rising",
                "proposals": [],
                "subsystem_hint": subsystem_hint,
                "roll_necessity": roll_necessity,
                "roll_under": _uses_roll_under(gsr),
                "roll_invitation": (
                    f"That sounds risky — roll your {stat_name} for me."
                    if dc is not None
                    else f"That could go wrong — shall I roll {stat_name}?"
                ),
            }

        # roll_necessity == "contested" → proceed with dice
        attributes = self._extract_attributes(context, gsr)
        stat_value = 0
        candidate_keys = [stat_name]
        if gsr:
            attr_def = gsr._attr_by_abbr.get(stat_name.upper(), {})
            candidate_keys.extend(
                [
                    str(attr_def.get("name") or ""),
                    str(attr_def.get("abbreviation") or ""),
                ]
            )
        for key in candidate_keys:
            if key and key in attributes:
                stat_value = int(attributes.get(key, 0))
                break
        base_modifier = (
            gsr.calc_modifier(stat_name, stat_value)
            if gsr
            else calculate_modifier(stat_value, _DEFAULT_MODIFIER_FORMULA)
        )

        # Evaluate scenery and conditions for dynamic adjustments
        sc_eval = self._evaluate_scenery_and_conditions(context, user_input or "", roll_mode, gsr)
        dynamic_mod = sc_eval["total_modifier"]
        actual_roll_mode = sc_eval["roll_mode"]
        modifier = base_modifier + dynamic_mod

        # Select roll formula based on actual_roll_mode
        if actual_roll_mode == "advantage":
            roll_formula = "2d20kh1"
            mode_label = "advantage"
        elif actual_roll_mode == "disadvantage":
            roll_formula = "2d20kl1"
            mode_label = "disadvantage"
        else:
            roll_formula = "1d20"
            mode_label = "normal"

        roll = roll_dice(roll_formula)
        natural = (
            roll.kept_rolls[0] if roll.kept_rolls else (roll.rolls[0] if roll.rolls else roll.total)
        )
        total = roll.total + modifier

        if _uses_roll_under(gsr):
            target = dc + modifier
            if natural == 1:
                success_level = "critical_success"
            elif natural == 20:
                success_level = "critical_failure"
            elif natural <= target:
                success_level = "success"
            elif natural <= target + 2:
                success_level = "partial_success"
            else:
                success_level = "failure"
        else:
            if natural == 20:
                success_level = "critical_success"
            elif natural == 1:
                success_level = "critical_failure"
            elif total >= dc:
                success_level = "success"
            elif total >= dc - 2:
                success_level = "partial_success"
            else:
                success_level = "failure"

        effects = []
        if success_level in {"success", "critical_success"}:
            effects.append("momentum_gained")
        elif success_level == "partial_success":
            effects.append("mixed_outcome")
        else:
            effects.append("setback")

        if action_type == "dialogue":
            effects.append("npc_reacts")
        else:
            effects.append("fiction_advances")

        spec = f"1d20+{modifier}" if modifier >= 0 else f"1d20{modifier}"
        if actual_roll_mode != "normal":
            spec = f"{roll_formula}+{modifier}" if modifier >= 0 else f"{roll_formula}{modifier}"

        # Build explanation of modifiers
        explain_parts = []
        if sc_eval["cond_modifier"] != 0:
            explain_parts.append(f"conditions: {sc_eval['cond_modifier']}")
        if sc_eval["scenery_modifier"] != 0:
            reasons_str = f" ({', '.join(sc_eval['reasons'])})" if sc_eval["reasons"] else ""
            explain_parts.append(f"scenery: {sc_eval['scenery_modifier']}{reasons_str}")

        explain_str = ""
        if explain_parts:
            explain_str = f" [base: {base_modifier}, " + ", ".join(explain_parts) + "]"

        if _uses_roll_under(gsr):
            target = dc + modifier
            roll_breakdown = (
                f"{roll_formula}({natural}) <= {dc} + {modifier} = {target}{explain_str}"
            )
            roll_reason = (
                f"{stat_name} check (target {target}, roll-under, {mode_label}){explain_str}"
            )
        else:
            roll_breakdown = (
                f"{roll_formula}({natural}) + {modifier} = {total} vs DC {dc}{explain_str}"
            )
            roll_reason = f"{stat_name} check (DC {dc}, {mode_label}){explain_str}"

        intent_type = _infer_intent_type(user_input or "", action_type)
        consequence_options = _build_consequence_options(
            intent_type if intent_type != "action" else action_type, success_level
        )
        requires_player_choice = success_level == "partial_success" and bool(consequence_options)
        narrative_pressure = {
            "critical_success": "surging",
            "success": "steady",
            "partial_success": "rising",
            "failure": "high",
            "critical_failure": "spiking",
        }.get(success_level, "steady")

        return {
            "scene_id": scene_id,
            "action_type": action_type,
            "intent_type": intent_type,
            "roll_type": roll_type,
            "intent_target": intent_target,
            "requires_clarification": requires_clarification,
            "stat": stat_name,
            "difficulty_class": dc,
            "attribute_value": stat_value,
            "modifier": modifier,
            "roll_total": total,
            "roll_breakdown": roll_breakdown,
            "roll_detail": {
                "spec": spec,
                "total": total,
                "rolls": roll.rolls,
                "kept_rolls": roll.kept_rolls if roll.kept_rolls else roll.rolls,
                "reason": roll_reason,
                "roll_mode": actual_roll_mode,
            },
            "resolution_type": "dice",
            "forced_narrative": False,
            "success": success_level in {"success", "critical_success"},
            "success_level": success_level,
            "effects": effects,
            "risk_preview": _build_risk_preview(
                intent_type if intent_type != "action" else action_type, stat_name, dc
            ),
            "consequence_options": consequence_options,
            "requires_player_choice": requires_player_choice,
            "narrative_pressure": narrative_pressure,
            "proposals": [],
            "subsystem_hint": subsystem_hint,
            "roll_necessity": roll_necessity,
            "roll_mode": actual_roll_mode,
            "opposed_target": None,
            "opposed_target_roll": None,
            "opposed_margin": None,
        }

    async def resolve_opposed_check(
        self,
        actor_id: str,
        target_id: str,
        stat_name: str,
        context: Dict[str, Any],
        gsr: GameSystemRuntime | None = None,
        roll_mode: str = "normal",
    ) -> Dict[str, Any]:
        """
        Resolve an opposed check between two entities.

        Both roll 1d20 + modifier. Higher total wins.
        Returns the winner, margin, and both roll details.

        Used for combat (attack vs defense), contested social checks,
        and any situation where two actors directly oppose each other.
        """
        # 1. Extract attributes for both actors
        actor_attrs = {}
        target_attrs = {}
        for entity in context.get("entities", []):
            props = entity.get("properties", {}) if isinstance(entity, dict) else {}
            eid = str(entity.get("id", ""))
            if eid == str(actor_id):
                if isinstance(props, dict):
                    nested = props.get("attributes", {})
                    if isinstance(nested, dict) and nested:
                        actor_attrs = {
                            k: int(v) for k, v in nested.items() if isinstance(v, (int, float))
                        }
                    else:
                        actor_attrs = {
                            k: int(v) for k, v in props.items() if isinstance(v, (int, float))
                        }
            elif eid == str(target_id):
                if isinstance(props, dict):
                    nested = props.get("attributes", {})
                    if isinstance(nested, dict) and nested:
                        target_attrs = {
                            k: int(v) for k, v in nested.items() if isinstance(v, (int, float))
                        }
                    else:
                        target_attrs = {
                            k: int(v) for k, v in props.items() if isinstance(v, (int, float))
                        }

        # 2. Calculate modifiers
        actor_stat = 0
        for key in (stat_name, stat_name.upper(), stat_name.lower(), stat_name.title()):
            if key in actor_attrs:
                actor_stat = int(actor_attrs[key])
                break

        target_stat = 0
        for key in (stat_name, stat_name.upper(), stat_name.lower(), stat_name.title()):
            if key in target_attrs:
                target_stat = int(target_attrs[key])
                break

        actor_mod = (
            gsr.calc_modifier(stat_name, actor_stat)
            if gsr
            else calculate_modifier(actor_stat, _DEFAULT_MODIFIER_FORMULA)
        )
        target_mod = (
            gsr.calc_modifier(stat_name, target_stat)
            if gsr
            else calculate_modifier(target_stat, _DEFAULT_MODIFIER_FORMULA)
        )

        # 3. Select roll formulas based on system type
        m_type = "d20"
        if gsr and gsr._sd.core:
            m_type = gsr._sd.core.get("type", "d20").lower()

        if "d20" in m_type:
            if roll_mode == "advantage":
                formula = "2d20kh1"
            elif roll_mode == "disadvantage":
                formula = "2d20kl1"
            else:
                formula = "1d20"

            # 4. Roll for both
            actor_roll = roll_dice(formula)
            target_roll = roll_dice(formula)

            actor_total = actor_roll.total + actor_mod
            target_total = target_roll.total + target_mod

            actor_natural = (
                actor_roll.kept_rolls[0]
                if actor_roll.kept_rolls
                else (actor_roll.rolls[0] if actor_roll.rolls else 0)
            )
            target_natural = (
                target_roll.kept_rolls[0]
                if target_roll.kept_rolls
                else (target_roll.rolls[0] if target_roll.rolls else 0)
            )

        elif "dice_pool" in m_type:
            # Assume attribute = number of dice, d10s
            # Successes are compared
            actor_pool = actor_stat
            target_pool = target_stat

            threshold = 6
            if gsr and gsr._sd.core:
                threshold_val = gsr._sd.core.get("success_threshold", 6)
                try:
                    if isinstance(threshold_val, str):
                        threshold = int("".join(filter(str.isdigit, threshold_val)) or 6)
                    else:
                        threshold = int(threshold_val)
                except (ValueError, TypeError):
                    threshold = 6

            actor_roll = roll_dice(f"{actor_pool}d10")
            target_roll = roll_dice(f"{target_pool}d10")

            actor_total = sum(1 for d in actor_roll.rolls if d >= threshold)
            target_total = sum(1 for d in target_roll.rolls if d >= threshold)

            actor_natural = actor_total
            target_natural = target_total

            # For dice pools, success level is based on number of successes
            actor_mod = 0  # Not used for pools
            target_mod = 0
        else:
            # Fallback to d20
            formula = "1d20"
            actor_roll = roll_dice(formula)
            target_roll = roll_dice(formula)
            actor_total = actor_roll.total + actor_mod
            target_total = target_roll.total + target_mod
            actor_natural = actor_roll.rolls[0] if actor_roll.rolls else 0
            target_natural = target_roll.rolls[0] if target_roll.rolls else 0

        # 5. Determine winner
        margin = actor_total - target_total
        if margin > 0:
            winner = "actor"
            success_level = "success"
        elif margin < 0:
            winner = "target"
            margin = abs(margin)
            success_level = "failure"
        else:
            winner = "tie"
            success_level = "partial_success"

        return {
            "winner": winner,
            "margin": margin,
            "actor_roll": {
                "total": actor_total,
                "natural": actor_natural,
                "modifier": actor_mod,
                "rolls": actor_roll.rolls,
                "kept_rolls": actor_roll.kept_rolls if actor_roll.kept_rolls else actor_roll.rolls,
            },
            "target_roll": {
                "total": target_total,
                "natural": target_natural,
                "modifier": target_mod,
                "rolls": target_roll.rolls,
                "kept_rolls": target_roll.kept_rolls
                if target_roll.kept_rolls
                else target_roll.rolls,
            },
            "opposed_stat": stat_name,
            "success_level": success_level,
        }

    def _extract_attributes(
        self,
        context: Dict[str, Any],
        gsr: GameSystemRuntime | None = None,
    ) -> Dict[str, int]:
        """
        Pull the first available attribute map from the assembled scene context.

        Recognises stat keys by comparing against the attribute abbreviations
        defined in the game system schema (via ``gsr``).  Falls back to any
        nested ``attributes`` dict when no runtime is available.
        """
        # Collect known stat abbreviations from the schema
        known_abbrs: set[str] = set()
        if gsr:
            known_abbrs = {abbr.upper() for abbr in gsr._attr_by_abbr}

        for entity in context.get("entities", []):
            props = entity.get("properties", {}) if isinstance(entity, dict) else {}
            if isinstance(props, dict):
                # Nested attributes dict (common in D&D-style schemas)
                attributes = props.get("attributes")
                if isinstance(attributes, dict) and attributes:
                    return {k: int(v) for k, v in attributes.items() if isinstance(v, (int, float))}
                # Flat stat keys matched against the active system's abbreviations
                if known_abbrs:
                    matched = {
                        k: int(v)
                        for k, v in props.items()
                        if k.upper() in known_abbrs and isinstance(v, (int, float))
                    }
                    if matched:
                        return matched
        return {}

    async def resolve_check(
        self,
        entity_id: str,
        stat_name: str,
        dc: int = 15,
        roll_mode: str = "normal",
    ) -> Dict[str, Any]:
        """
        Resolve a statistic check (Attribute/Skill) for an entity.

        Workflow:
        1. Get Entity -> Universe -> Multiverse -> System Name.
        2. Get Game System rules.
        3. Get Entity working state (not strictly needed for basic attrib check, but good for context).
        4. Get Entity properties (attributes).
        5. Calculate modifier.
        6. Roll dice.
        7. Determine outcome.
        """
        try:
            # 1. Get Entity to find Universe/System
            # We need to parse the JSON result from call_tool
            entity_json = await self.call_tool("neo4j_get_entity", {"entity_id": entity_id})
            if not entity_json:
                return {"error": "Entity not found"}

            entity_data = json.loads(entity_json)
            # entity_data is { ... } response model

            universe_id = entity_data.get("universe_id")

            # 2. Get Universe to find Multiverse
            universe_json = await self.call_tool(
                "neo4j_get_universe", {"universe_id": str(universe_id)}
            )
            if not universe_json:
                return {"error": "Universe not found"}
            universe_data = json.loads(universe_json)
            multiverse_id = universe_data.get("multiverse_id")

            # 3. Get Multiverse to find System Name
            multiverse_json = await self.call_tool(
                "neo4j_get_multiverse", {"multiverse_id": str(multiverse_id)}
            )
            if not multiverse_json:
                # Fallback: cannot determine system — return error
                system_name = None
            else:
                multiverse_data = json.loads(multiverse_json)
                system_name = multiverse_data.get("system_name")

            # 4. Get Game System
            # list systems and filter by name (since we don't have get_by_name yet, or we simulate it)
            # For now, we grab the first matching one
            systems_json = await self.call_tool(
                "mongodb_list_game_systems",
                {"limit": 100, "include_builtin": True, "offset": 0},
            )
            systems_data = json.loads(systems_json)

            if not system_name:
                # Multiverse record missing — fall back to the first available game system
                systems_list = systems_data.get("systems", [])
                if systems_list:
                    system_name = systems_list[0]["name"]
                else:
                    return {"error": "Could not determine game system for multiverse"}

            system = None
            for sys in systems_data.get("systems", []):
                if sys["name"] == system_name:
                    system = sys
                    break

            if not system:
                return {"error": f"Game system '{system_name}' not found"}

            # 5. Get Entity Attributes (Properties)
            # Assuming 'properties' field in Entity contains attributes map: {"Strength": 16, ...}
            # Or formatted as {"attributes": {"Strength": 16}}
            props = entity_data.get("properties", {})
            attributes = props.get("attributes", {})

            # Handle case where props form is flat {"Strength": 16}
            if not attributes:
                attributes = props

            # Find attribute definition in system
            target_attr_def = next(
                (a for a in system["attributes"] if a["name"].lower() == stat_name.lower()),
                None,
            )

            if not target_attr_def:
                # Is it a skill?
                target_skill_def = next(
                    (s for s in system["skills"] if s["name"].lower() == stat_name.lower()),
                    None,
                )
                if target_skill_def:
                    # It's a skill check - use linked attribute for modifier
                    linked_attr = target_skill_def["linked_attribute"]
                    # Find the linked attribute definition
                    linked_attr_def = next(
                        (a for a in system["attributes"] if a["name"] == linked_attr),
                        None,
                    )
                    if not linked_attr_def:
                        return {
                            "error": f"Linked attribute '{linked_attr}' not found for skill '{stat_name}'"
                        }

                    stat_value = attributes.get(
                        linked_attr, linked_attr_def.get("default_value", 10)
                    )

                    # Calculate modifier using linked attribute's formula
                    mod_formula = linked_attr_def.get("modifier_formula")
                    modifier = calculate_modifier(stat_value, mod_formula) if mod_formula else 0
                    # Could add proficiency bonus here in future
                else:
                    return {"error": f"Stat '{stat_name}' not found in system '{system_name}'"}
            else:
                # It's an attribute
                stat_value = attributes.get(
                    target_attr_def["name"], target_attr_def.get("default_value", 10)
                )

                # 6. Calculate Modifier
                mod_formula = target_attr_def.get("modifier_formula")
                modifier = calculate_modifier(stat_value, mod_formula) if mod_formula else 0

            # 7. Roll Dice
            core_mechanic = system["core_mechanic"]
            m_type = core_mechanic["type"]

            # Simple implementation for D20 and Dice Pool
            if "d20" in m_type:
                if roll_mode == "advantage":
                    formula = "2d20kh1"
                elif roll_mode == "disadvantage":
                    formula = "2d20kl1"
                else:
                    formula = "1d20"
                base_roll = roll_dice(formula)
                total = base_roll.total + modifier
                success = total >= dc
                details = (
                    f"Rolled {formula} ({base_roll.rolls}) + Mod {modifier} = {total} (DC {dc})"
                )

            elif "dice_pool" in m_type:
                # Assume attribute = number of dice
                pool_size = stat_value  # + skill if applicable
                dice_res = roll_dice(f"{pool_size}d10")  # Vampire uses d10s
                # Count successes >= threshold
                threshold_val = core_mechanic.get("success_threshold", 6)
                # Handle string thresholds like "7+" or descriptive strings
                try:
                    if isinstance(threshold_val, str):
                        # Extract numeric value from strings like "7+"
                        threshold = int("".join(filter(str.isdigit, threshold_val)) or 6)
                    else:
                        threshold = int(threshold_val)
                except (ValueError, TypeError):
                    threshold = 6  # Safe default
                successes = sum(1 for d in dice_res.rolls if d >= threshold)
                total = successes
                success = successes > 0  # Simple success
                details = f"Rolled {pool_size}d10: {dice_res.rolls} -> {successes} successes"

            else:
                return {"error": f"Unsupported mechanic type: {core_mechanic['type']}"}

            return {
                "success": success,
                "total": total,
                "details": details,
                "system": system_name,
                "stat": stat_name,
                "modifier": modifier,
            }

        except Exception as e:
            logger.exception("Error resolving check")
            return {"error": str(e)}
