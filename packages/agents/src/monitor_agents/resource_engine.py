"""
ResourceEngine — multi-track character state engine.

LAYER: 2 (agents)
Authority: READS game_context + CharacterWorkingState; WRITES via ProposedChange.

Handles all resource/track lifecycle:
  - Spend:    detect spend intent → validate availability → return RollModifier
  - Earn:      infer from resolution outcome + game_context rules
  - Thresholds: evaluate threshold_effects after each state change
  - Recovery:  apply recovery_model events (rest, breather, etc.)

Zero system-specific code.  Every behaviour is derived from game_context JSON.

Use Cases: P-3, P-9, DL-26
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SpendAttempt:
    """A parsed attempt to spend a resource."""

    resource_key: str  # normalised key in resources dict
    resource_name: str  # display name from schema
    amount: int  # positive integer
    intent: str  # "advantage" | "reroll" | "override" | etc.
    can_afford: bool
    spend_effect: Optional[str] = None  # e.g. "advantage_2d20kh1"


@dataclass
class RollModifier:
    """Returned when a spend is valid and should modify a dice roll."""

    resource_key: str
    resource_name: str
    amount: int
    modifier_type: str  # "advantage" | "reroll" | "target_bonus" | "override"
    spec: str  # dice notation: "2d20kh1", "+2", etc.
    description: str  # human-readable


@dataclass
class ResourceDelta:
    """A single resource value change."""

    resource_key: str
    resource_name: str
    delta: int  # positive = gain, negative = loss
    source: str  # "earn_on_failure" | "session_start" | "recovery" | "threshold"
    reason: str


@dataclass
class ThresholdEvent:
    """Fired when a track crosses a threshold."""

    resource_key: str
    resource_name: str
    threshold_value: int
    direction: str  # "at_or_below" | "at_or_above"
    effect: str  # narrative effect description
    new_value: int


# ---------------------------------------------------------------------------
# Keyword tables (system-agnostic)
# ---------------------------------------------------------------------------

# Intent → canonical spend intent label
_SPEND_INTENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(advantage|adv)\b", re.I), "advantage"),
    (re.compile(r"\b(disadvantage|dis)\b", re.I), "disadvantage"),
    (re.compile(r"\b(reroll|reroll\s+the|use\s+the\s+reroll)\b", re.I), "reroll"),
    (re.compile(r"\b(inspiration|inspire)\b", re.I), "inspiration"),
    (re.compile(r"\b(fate\s+point|fate)\b", re.I), "fate_point"),
    (re.compile(r"\b(void\s+point|void|luck)\b", re.I), "void_point"),
    (re.compile(r"\b(willpower|will\s+power|wp)\b", re.I), "willpower"),
    (re.compile(r"\b(will\s+use|use\s+will)\b", re.I), "willpower"),
    (re.compile(r"\b(hunger|blood\s+pool)\b", re.I), "hunger"),
    (re.compile(r"\b(blood\s+potency|blood)\b", re.I), "blood_potency"),
    (re.compile(r"\b(humanity)\b", re.I), "humanity"),
    (re.compile(r"\b(stress|stressed)\b", re.I), "stress"),
    (re.compile(r"\b(momentum|mom)\b", re.I), "momentum"),
    (re.compile(r"\b(spell\s+slot|spell\s+slot\s+burn|use\s+spell)\b", re.I), "spell_slot"),
    (re.compile(r"\b(resolve)\b", re.I), "resolve"),
    (re.compile(r"\b(o2|oxygen)\b", re.I), "oxygen"),
    (re.compile(r"\b(debt)\b", re.I), "debt"),
    (re.compile(r"\b(ship\s+hull|hull)\b", re.I), "ship_hull"),
    (re.compile(r"\b(break\s+down|breaking\s+down|irration)\b", re.I), "breakdown"),
    (re.compile(r"\b(frenzy)\b", re.I), "frenzy"),
    (re.compile(r"\b(superior\s+position|position|superior)\b", re.I), "superior_position"),
]

# Spend intent → dice notation
_INTENT_SPEC_MAP: dict[str, tuple[str, str]] = {
    "advantage": ("2d20kh1", "Roll with advantage (2d20 keep highest)"),
    "disadvantage": ("2d20kl1", "Roll with disadvantage (2d20 keep lowest)"),
    "reroll": ("1d20", "Reroll the die (keep new result)"),
    "inspiration": ("+1d4", "Roll an extra d4 and add to total"),
    "fate_point": ("+1d6", "Add a FATE die (+1d6)"),
    "void_point": ("+1d4", "Add a void die (+1d4)"),
    "willpower": ("+1d4", "Add a willpower die (+1d4)"),
    "hunger": ("+1d6", "Add a hunger die (+1d6)"),
    "blood_potency": ("+1d4", "Add a blood potency die (+1d4)"),
    "humanity": ("+1d4", "Add a humanity die (+1d4)"),
    "stress": ("-1d4", "Roll with stress penalty (-1d4)"),
    "momentum": ("+1", "Gain +1 momentum bonus"),
    "spell_slot": ("spell_burn", "Burn a spell slot to cast at higher level"),
    "resolve": ("override", "Override a consequence using resolve"),
    "superior_position": ("+2", "Superior position grants +2 bonus"),
}


def _normalize_key(text: str) -> str:
    """Collapse whitespace and lowercase for matching."""
    return re.sub(r"\s+", "", text.strip().lower())


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class ResourceEngine:
    """
    Multi-track character state engine.  Zero system-specific code.

    All behaviour is derived from the ``game_context`` dict (loaded from
    ``builtin_systems.json`` entry) and the character ``working_state``.

    Parameters
    ----------
    game_context : dict
        Full game-system document from MongoDB (resources[], tracks[],
        core_mechanic, recovery_model).
    working_state : dict
        Current character working state (resources dict with current/max values).
    """

    def __init__(
        self,
        game_context: dict[str, Any],
        working_state: dict[str, Any],
    ) -> None:
        self.game_context = game_context
        self.working_state = working_state
        self._resources = _build_resource_index(game_context)
        self._tracks = _build_track_index(game_context)
        self._mechanic_type = _infer_mechanic_type(game_context)
        self._recovery = list(game_context.get("recovery_model", {}).get("events", []))
        # Index WS keys in a case-insensitive map for fast lookup
        self._ws_key_map: dict[str, str] = {}
        for ws_key in working_state:
            self._ws_key_map[ws_key.lower()] = ws_key

    # -------------------------------------------------------------------------
    # Spend detection
    # -------------------------------------------------------------------------

    def detect_spend(self, user_input: str) -> list[SpendAttempt]:
        """
        Parse ``user_input`` for resource-spend intent.

        Returns a list of ``SpendAttempt`` objects — one per distinct spend
        keyword found.  An empty list means no spend was requested.

        The method is purely analytical; it never checks affordability here.
        Use ``apply_spend`` to validate and convert to a ``RollModifier``.
        """
        if not user_input:
            return []
        attempts: list[SpendAttempt] = []
        seen: set[str] = set()
        lower = user_input.lower()

        for pattern, intent in _SPEND_INTENT_PATTERNS:
            if not pattern.search(lower):
                continue
            # Find the matching resource in our index
            resource_key = self._match_resource(intent)
            if resource_key is None:
                continue
            if resource_key in seen:
                continue
            seen.add(resource_key)

            res_def = self._resources.get(resource_key, {})
            spend_effect = res_def.get("spend_effect")

            # Extract amount if explicitly quantified
            amount = 1
            amount_match = re.search(r"\b(\d+)\s+(?:point|die|slot)s?\b", lower)
            if amount_match:
                amount = int(amount_match.group(1))

            attempt = SpendAttempt(
                resource_key=resource_key,
                resource_name=res_def.get("name", resource_key) or resource_key,
                amount=amount,
                intent=intent,
                can_afford=self._can_spend(resource_key, amount),
                spend_effect=spend_effect,
            )
            attempts.append(attempt)

        return attempts

    def _match_resource(self, intent: str) -> Optional[str]:
        """Map a spend intent to a resource key in working_state.

        Returns a key if one is found in working_state, otherwise returns
        the intent itself as a fallback key (ResourceEngine always creates
        a SpendAttempt for recognised intents; apply_spend handles affordability).
        """
        # Direct intent → resource key mapping
        intent_map: dict[str, list[str]] = {
            "advantage": ["adv", "advantage"],
            "disadvantage": ["dis", "disadvantage"],
            "reroll": ["reroll", "reroll_used"],
            "inspiration": ["ins", "inspiration", "in"],
            "fate_point": ["fp", "fate", "fate_point", "fate_points"],
            "void_point": ["void", "void_point", "void_points", "luck"],
            "willpower": ["wp", "willpower", "will_power"],
            "hunger": ["hunger", "blood_pool", "bp"],
            "blood_potency": ["blood_potency", "bp", "potency"],
            "humanity": ["humanity", "hum"],
            "stress": ["stress", "str", "stresse"],
            "momentum": ["mom", "momentum"],
            "spell_slot": ["spell_slot", "spell_slots", "slot"],
            "resolve": ["res", "resolve"],
            "oxygen": ["o2", "oxygen", "air"],
            "debt": ["debt"],
            "ship_hull": ["ship_hull", "hull"],
            "breakdown": ["stress"],
            "frenzy": ["hunger"],
            "superior_position": ["position", "superior", "superior_position"],
        }
        candidates = intent_map.get(intent, [intent])
        # Search working_state keys (preserving case) for a candidate match
        for ws_key in self.working_state:
            for cand in candidates:
                if cand.lower() in ws_key.lower() or ws_key.lower() in cand.lower():
                    return ws_key  # Return actual case-preserved key
        # Fall back: search by resource name from schema (return normalized key)
        for res_key, res_def in self._resources.items():
            name = res_def.get("name", "").lower()
            abbr = res_def.get("abbreviation", "").lower()
            if intent in name or intent in abbr:
                return res_key  # normalized key from schema
        # Fall back to the intent string itself so detect_spend always creates an attempt
        return intent

    def _can_spend(self, resource_key: str, amount: int) -> bool:
        """Check if working_state has enough of the resource (case-insensitive key match).

        For intent-strings (no resource) OR unrecognized keys: always return True
        (the spend is recognised; affordability is a system-level call, not a resource check).
        """
        # Intents that didn't match any resource fall back to their own name
        # Treat them as always-affordable (e.g. "advantage" in d20 systems)
        if resource_key not in self.working_state and resource_key.lower() not in self._ws_key_map:
            return True
        actual_key = self._ws_key_map.get(resource_key.lower(), resource_key)
        snap: dict[str, Any] | int | None = self.working_state.get(actual_key)
        if snap is None:
            return False
        if isinstance(snap, dict):
            current: int | Any = snap.get("current", 0)
        else:
            current = int(snap)
        return bool(current >= amount)

    # -------------------------------------------------------------------------
    # Spend application
    # -------------------------------------------------------------------------

    def apply_spend(
        self,
        spend: SpendAttempt,
        roll_context: dict[str, Any] | None = None,
    ) -> Optional[RollModifier]:
        """
        Validate a ``SpendAttempt`` and return a ``RollModifier`` if valid.

        Returns None if the resource cannot be afforded or the spend is
        not applicable to the current mechanic type.

        The caller (Resolver) is responsible for applying the modifier to the
        roll and for deducting the resource from working_state.
        """
        if not spend.can_afford:
            logger.debug("ResourceEngine: cannot afford %s x%d", spend.resource_key, spend.amount)
            return None

        # Infer dice spec from spend effect hint OR mechanic type
        spec_type, description = self._resolve_spec(spend)

        return RollModifier(
            resource_key=spend.resource_key,
            resource_name=spend.resource_name,
            amount=spend.amount,
            modifier_type=spend.intent,
            spec=spec_type,
            description=description,
        )

    def _resolve_spec(self, spend: SpendAttempt) -> tuple[str, str]:
        """Derive the dice notation for a spend from hints or inference."""
        # Explicit spend_effect in schema takes priority
        if spend.spend_effect:
            return _INTENT_SPEC_MAP.get(
                spend.spend_effect,
                (spend.spend_effect, f"Spend {spend.resource_name}"),
            )

        # Core mechanic inference (table from plan)
        mechanic = self._mechanic_type

        if spend.intent in _INTENT_SPEC_MAP:
            return _INTENT_SPEC_MAP[spend.intent]

        # Fallback inference from mechanic type
        if mechanic == "d20":
            if "meet_or_beat" in str(
                self.game_context.get("core_mechanic", {}).get("success_type", "")
            ):
                return ("2d20kh1", f"Spend {spend.resource_name} for advantage")
            return ("+2", f"Spend {spend.resource_name} for +2 bonus")
        elif mechanic == "dice_pool":
            if spend.intent in ("advantage", "inspiration", "fate_point", "void_point"):
                return ("+1d4", f"Spend {spend.resource_name} for +1d4")
            return ("+1", f"Spend {spend.resource_name} for +1 bonus")
        else:
            return ("override", f"Spend {spend.resource_name} to override a consequence")

    # -------------------------------------------------------------------------
    # Earn inference
    # -------------------------------------------------------------------------

    def apply_earn(
        self,
        resolution: dict[str, Any],
        scene_context: dict[str, Any] | None = None,
    ) -> list[ResourceDelta]:
        """
        Infer resource gains from a turn resolution outcome.

        Reads ``success_level``, ``resolution_type``, and ``effects`` from
        the resolution dict and matches them against the game_context's
        earn-on-* rules for each resource.

        Parameters
        ----------
        resolution : dict
            The full resolution dict returned by ``Resolver.resolve_turn()``.
        scene_context : dict, optional
            Additional scene metadata (session_start, trigger keywords).

        Returns
        -------
        list[ResourceDelta]
            One entry per resource that should change.  The caller is
            responsible for applying these to working_state.
        """
        if not resolution:
            return []
        scene_context = scene_context or {}
        deltas: list[ResourceDelta] = []
        success_level = str(resolution.get("success_level", ""))
        res_type = str(resolution.get("resolution_type", ""))
        effects = [str(e) for e in resolution.get("effects", [])]

        # Handle session-start refresh (before iterating earn_conditions)
        if scene_context.get("turns_count", -1) == 0:
            seen_session_refresh: set[str] = set()
            for res_key, res_def in self._resources.items():
                # Deduplicate: skip if we already processed this resource (by normalized key)
                norm_key = _normalize_key(res_key)
                if norm_key in seen_session_refresh:
                    continue
                recovers_on = str(res_def.get("recovers_on", "")).lower()
                if recovers_on in ("session start", "session_start"):
                    seen_session_refresh.add(norm_key)
                    max_val = self._get_max(res_key)
                    deltas.append(
                        ResourceDelta(
                            resource_key=res_key,
                            resource_name=res_def.get("name", res_key),
                            delta=max_val,
                            source="session_start",
                            reason=f"{res_def.get('name', res_key)} restored to {max_val} at session start",
                        )
                    )

        for res_key, res_def in self._resources.items():
            earn_triggers = res_def.get("earn_conditions", [])
            for trigger_str in earn_triggers:
                delta = self._match_earn_trigger(
                    trigger_str, success_level, res_type, effects, scene_context, res_key, res_def
                )
                if delta:
                    deltas.append(delta)

        return deltas

    def apply_action_economy(
        self,
        user_input: str,
        resolution: dict[str, Any],
    ) -> list[ResourceDelta]:
        """
        Data-driven per-resource action economy (e.g. VtM's blood economy).

        Each resource in the game system may declare ``action_rules``::

            "action_rules": [
              {"keywords": ["feed","drain","bite"], "delta": -2, "requires": "success",
               "reason": "Slaked Hunger by feeding"},
              {"keywords": ["discipline","celerity","rouse"], "delta": 1,
               "reason": "Roused the Blood for a Discipline"},
              {"keywords": ["punch","strike","wound"], "delta": -1, "requires": "harm",
               "reason": "Took damage"}
            ]

        A rule fires when one of its keywords appears in the player's action and
        its ``requires`` gate (``success`` / ``harm`` / none) is satisfied. This
        keeps the blood/damage economy in *data* (the game system), not in code.
        """
        if not user_input:
            return []
        low = user_input.lower()
        success_level = str(resolution.get("success_level", ""))
        is_success = success_level in ("success", "critical_success", "partial_success")
        is_harm = bool(resolution.get("has_harm")) or success_level in ("failure", "critical_failure")

        deltas: list[ResourceDelta] = []
        seen: set[str] = set()
        for res_key, res_def in self._resources.items():
            # Dedup by resource NAME — the index keys each resource under both
            # its abbreviation and its name, so the same resource appears twice.
            norm = _normalize_key(res_def.get("name") or res_key)
            if norm in seen:
                continue
            for rule in res_def.get("action_rules", []) or []:
                keywords = [str(k).lower() for k in (rule.get("keywords") or [])]
                if not any(k in low for k in keywords):
                    continue
                requires = (rule.get("requires") or "").lower()
                if requires == "success" and not is_success:
                    continue
                if requires == "harm" and not is_harm:
                    continue
                delta = int(rule.get("delta", 0))
                if delta == 0:
                    continue
                seen.add(norm)
                deltas.append(
                    ResourceDelta(
                        resource_key=res_key,
                        resource_name=res_def.get("name", res_key),
                        delta=delta,
                        source="action_economy",
                        reason=str(rule.get("reason", f"{res_def.get('name', res_key)} {delta:+d}")),
                    )
                )
                break
        return deltas

    def _match_earn_trigger(
        self,
        trigger_str: str,
        success_level: str,
        res_type: str,
        effects: list[str],
        scene_context: dict[str, Any],
        res_key: str,
        res_def: dict[str, Any],
    ) -> Optional[ResourceDelta]:
        """Evaluate a single earn condition string."""
        trigger = trigger_str.strip().lower()
        res_name = res_def.get("name", res_key)

        # System-level earn rules from builtin_systems.json
        # These are matched case-insensitively against the trigger string

        if trigger in ("failure", "on failure", "fail"):
            if success_level in ("failure", "critical_failure"):
                return ResourceDelta(
                    resource_key=res_key,
                    resource_name=res_name,
                    delta=1,
                    source="earn_on_failure",
                    reason=f"Earned 1 {res_name} on failed roll",
                )

        if trigger in ("session_start", "session start", "on session start"):
            # Check if this is the first turn of the session
            if scene_context.get("turns_count", 0) == 0:
                max_val = self._get_max(res_key)
                return ResourceDelta(
                    resource_key=res_key,
                    resource_name=res_name,
                    delta=max_val,  # Refresh to full
                    source="session_start",
                    reason=f"{res_name} restored to {max_val} at session start",
                )

        if trigger in ("scene_end", "scene end", "on scene end"):
            if scene_context.get("scene_ending", False):
                max_val = self._get_max(res_key)
                return ResourceDelta(
                    resource_key=res_key,
                    resource_name=res_name,
                    delta=max_val,
                    source="scene_end",
                    reason=f"{res_name} restored at scene end",
                )

        if trigger in ("breather", "short rest"):
            if "breather" in effects or "mixed_outcome" in effects:
                # Restore some stress / HP
                return ResourceDelta(
                    resource_key=res_key,
                    resource_name=res_name,
                    delta=-1,  # Stress decreases
                    source="breather",
                    reason=f"{res_name} decreased after breather",
                )

        if trigger in ("compel", "concede", "on compel", "on concede"):
            if "compel" in effects or "concede" in effects:
                return ResourceDelta(
                    resource_key=res_key,
                    resource_name=res_name,
                    delta=1,
                    source="compel",
                    reason=f"Earned 1 {res_name} from compel",
                )

        # Fallback: generic stress-on-failure
        if success_level in ("failure", "critical_failure") and "stress" in res_key.lower():
            return ResourceDelta(
                resource_key=res_key,
                resource_name=res_name,
                delta=1,
                source="earn_on_failure",
                reason="Stress gained on failed roll",
            )

        return None

    def _get_max(self, resource_key: str) -> int:
        """Get the max value for a resource (case-insensitive key match)."""
        # Try exact key first, then normalized map, then search values
        if resource_key in self.working_state:
            snap = self.working_state[resource_key]
        else:
            actual_key = self._ws_key_map.get(resource_key.lower())
            if actual_key is None:
                # Key not in map either — search values of ws_key_map for a match
                norm = resource_key.lower()
                for lower_key, actual in self._ws_key_map.items():
                    if lower_key == norm or norm in lower_key or lower_key in norm:
                        actual_key = actual
                        break
            snap = self.working_state.get(actual_key) if actual_key else None
        if snap is None:
            return 0
        if isinstance(snap, dict):
            val = snap.get("max")
            if val is not None:
                return int(val)
            return int(snap.get("current", 0))
        return int(snap) if snap else 0

    # -------------------------------------------------------------------------
    # Threshold checking
    # -------------------------------------------------------------------------

    def check_thresholds(self) -> list[ThresholdEvent]:
        """
        Evaluate all track threshold_effects against current working_state.

        Called after each state change (spend, earn, or damage application).
        Returns a list of ``ThresholdEvent`` — one per threshold crossed.
        An empty list means no thresholds were crossed.

        Caller should surface the ``effect`` field as narrative and apply
        any mechanical consequences.
        """
        events: list[ThresholdEvent] = []
        for res_key, track_def in self._tracks.items():
            # Find the actual working_state key for this track.
            # Strategy: try (1) ws_key_map exact match, (2) normalize + search,
            # (3) look up via resource index (which has abbreviated keys).
            actual_key: Optional[str] = self._ws_key_map.get(res_key.lower())
            if actual_key is None:
                # Try normalized comparison of track key vs all WS keys
                norm_track = res_key.lower().replace(" ", "").replace("_", "")
                for ws_key in self.working_state:
                    norm_ws = ws_key.lower().replace(" ", "").replace("_", "")
                    if norm_track == norm_ws:
                        actual_key = ws_key
                        break
            # Also try: for each resource entry, check if the track key matches the
            # resource name (normalized) and if so, use the resource's abbreviation
            # to find the actual WS key (covers "hunger" → "HNGR" case).
            if actual_key is None:
                track_norm = res_key.lower()
                for res_key_idx, res_def in self._resources.items():
                    res_name_norm = (
                        res_def.get("name", "").lower().replace(" ", "").replace("_", "")
                    )
                    if res_name_norm and track_norm == res_name_norm:
                        abbr_norm = (
                            res_def.get("abbreviation", "")
                            .lower()
                            .replace(" ", "")
                            .replace("_", "")
                        )
                        actual_key = self._ws_key_map.get(abbr_norm)
                        if actual_key:
                            break
            snap = self.working_state.get(actual_key, {}) if actual_key else {}
            if not isinstance(snap, dict) or "current" not in snap:
                continue
            current = snap.get("current", 0)
            for threshold in track_def.get("threshold_effects", []):
                t_value = int(threshold.get("value", 0))
                direction = str(threshold.get("direction", "at_or_below"))
                effect = str(threshold.get("effect", ""))
                crossed = False
                if direction == "at_or_below" and current <= t_value:
                    crossed = True
                elif direction == "at_or_above" and current >= t_value:
                    crossed = True
                if crossed:
                    events.append(
                        ThresholdEvent(
                            resource_key=res_key,
                            resource_name=track_def.get("name", res_key),
                            threshold_value=t_value,
                            direction=direction,
                            effect=effect,
                            new_value=current,
                        )
                    )
        return events

    # -------------------------------------------------------------------------
    # Recovery
    # -------------------------------------------------------------------------

    def apply_recovery(self, trigger: str) -> list[ResourceDelta]:
        """
        Apply recovery events matching ``trigger``.

        Parameters
        ----------
        trigger : str
            Recovery trigger name, e.g. ``"Long Rest"``, ``"Breather"``,
            ``"Full Rest"``.  Matched case-insensitively against
            ``recovery_model.events[].name`` in game_context.

        Returns
        -------
        list[ResourceDelta]
            One entry per resource restored.  The caller applies these to
            working_state.  Returns an empty list if the trigger is unknown.
        """
        deltas: list[ResourceDelta] = []
        trigger_lower = trigger.lower()
        for event in self._recovery:
            if trigger_lower not in event.get("name", "").lower():
                continue
            restores = event.get("restores", [])
            for restore_spec in restores:
                delta = self._parse_restore_spec(restore_spec)
                if delta:
                    deltas.append(delta)
        return deltas

    def _parse_restore_spec(self, spec: str) -> Optional[ResourceDelta]:
        """Parse a 'ResourceName: amount_or_full' restore string."""
        # e.g. "Hit Points: full" | "Stress: 2" | "Hit Dice: half_max"
        parts = re.split(r":\s*", spec, maxsplit=1)
        if len(parts) != 2:
            return None
        res_name = parts[0].strip()
        amount_str = parts[1].strip()

        # Find matching resource key (case-insensitive match against ws keys and schema)
        res_key = None
        norm_res = res_name.lower().replace(" ", "").replace("_", "")
        for key in self.working_state:
            norm_key = key.lower().replace(" ", "").replace("_", "")
            if norm_res in norm_key or norm_key in norm_res:
                res_key = key
                break
        # Also try to match via resource schema abbreviations
        if res_key is None:
            for res_key_schema, res_def in self._resources.items():
                abbr = res_def.get("abbreviation", "").lower().replace(" ", "").replace("_", "")
                name = res_def.get("name", "").lower().replace(" ", "").replace("_", "")
                if norm_res == abbr or norm_res == name or norm_res in name:
                    # Found in schema — map to actual ws key
                    for ws_key in self.working_state:
                        if (
                            ws_key.lower() == res_key_schema.lower()
                            or ws_key.lower().replace(" ", "").replace("_", "")
                            == res_key_schema.lower()
                        ):
                            res_key = ws_key
                            break
                    break
        if res_key is None:
            return None

        if amount_str == "full":
            delta = self._get_max(res_key)
        elif amount_str == "half_max":
            delta = self._get_max(res_key) // 2
        elif amount_str.startswith("hit_dice"):
            delta = self._get_max(res_key) // 2
        else:
            try:
                delta = int(amount_str)
            except ValueError:
                return None

        return ResourceDelta(
            resource_key=res_key,
            resource_name=res_name,
            delta=delta,
            source="recovery",
            reason=f"Recovered {delta} {res_name} from rest",
        )


# ---------------------------------------------------------------------------
# Helper: build indexes from game_context
# ---------------------------------------------------------------------------


def _build_resource_index(game_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index resources[] by normalised key for fast lookup.

    Each resource gets one canonical entry keyed by its abbreviation (or name if
    no abbreviation is given).  A secondary name-key entry is only added if it
    differs meaningfully from the canonical key (prevents duplicate iterations).
    """
    index: dict[str, dict[str, Any]] = {}
    for res in game_context.get("resources", []):
        name = str(res.get("name", ""))
        abbr = str(res.get("abbreviation", ""))
        canonical_key = _normalize_key(abbr) or _normalize_key(name)
        if canonical_key:
            index[canonical_key] = res
        name_key = _normalize_key(name)
        if name_key and name_key != canonical_key:
            # Skip if abbreviation is a prefix of the name (same resource)
            abbr_norm = _normalize_key(abbr)
            if abbr_norm and name_key.startswith(abbr_norm):
                continue
            index[name_key] = res
    return index


def _build_track_index(game_context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index tracks[] by normalised key for fast lookup.

    Each track gets its abbreviation as the canonical key (or name if no
    abbreviation).  A name-key entry is only added as a secondary alias when
    the name is genuinely a different normalized form from the abbreviation.

    Special case: if both name and abbreviation are present and the abbreviation
    is a prefix of the normalized name (e.g. "STR" → "stress"), the abbreviation
    is ALSO added as a secondary entry so that check_thresholds can match WS keys
    that use the abbreviation form directly.
    """
    index: dict[str, dict[str, Any]] = {}
    for track in game_context.get("tracks", []):
        name = str(track.get("name", ""))
        abbr = str(track.get("abbreviation", ""))
        canonical_key = _normalize_key(abbr) or _normalize_key(name)
        if canonical_key:
            index[canonical_key] = track
        name_key = _normalize_key(name)
        if name_key and name_key != canonical_key:
            abbr_norm = _normalize_key(abbr)
            # Add name key if genuinely different AND not a prefix collision
            if abbr_norm and name_key.startswith(abbr_norm):
                # Skip the name-based entry, but ensure abbreviation IS in the index
                if abbr_norm and abbr_norm != canonical_key:
                    index[abbr_norm] = track
            else:
                index[name_key] = track
    return index


def _infer_mechanic_type(game_context: dict[str, Any]) -> str:
    """Infer core mechanic type from game_context.core_mechanic."""
    core = game_context.get("core_mechanic", {})
    return str(core.get("type", "narrative")).lower()
