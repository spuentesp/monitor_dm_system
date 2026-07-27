"""
Condition tools — list and check conditions against scene events.

Conditions are the persistent state-tags that ride on characters (e.g.
"poisoned", "blessed", "bloodied"). The GM uses these tools to:
- Recall what's already on the player / NPCs.
- Evaluate whether an in-fiction event should fire a new condition.

T1 scaffolds the tools; T3 (with GMAgent) wires them to the existing
``check_condition_triggers`` semantic matcher.
"""

from __future__ import annotations

import json
from typing import Any

import dspy


def gm_tool_check_conditions() -> Any:
    """Return a ``dspy.Tool`` that fires new conditions off an event string."""

    def check_conditions(event: str, context: str = "{}") -> str:
        """Return conditions whose triggers fire against ``event``.

        ``context`` is a JSON blob with ``track_values``, ``active_conditions``,
        etc. The current implementation is a scaffold; T3 wires the real
        semantic matcher.
        """
        try:
            import json as _json

            ctx = _json.loads(context) if context else {}
        except Exception:
            ctx = {}
        payload: dict[str, Any] = {
            "event": event,
            "status": "scaffold_only",
            "triggered": [],
            "context_received": ctx,
            "note": "T3 wires the real semantic matcher (check_condition_triggers).",
        }
        return json.dumps(payload)

    return dspy.Tool(
        check_conditions,
        name="check_conditions",
        desc=(
            "Check which conditions in the schema should fire given an event "
            "(e.g. 'character takes damage' might fire 'bloodied'). Returns a "
            "list of triggered conditions. Use when an event happens in-fiction "
            "and you want to know which persistent tags should now apply."
        ),
        args={
            "event": {"type": "string", "description": "The event description."},
            "context": {
                "type": "string",
                "description": "JSON blob with track_values, active_conditions, etc.",
                "default": "{}",
            },
        },
    )


def gm_tool_list_active_conditions() -> Any:
    """Return a ``dspy.Tool`` that lists the conditions currently active."""

    def list_active_conditions(scene_id: str, character_id: str = "") -> str:
        """Return the list of conditions currently active on a character (or the player by default).

        Scaffold — T3 wires the real MongoDB lookup.
        """
        payload: dict[str, Any] = {
            "scene_id": scene_id,
            "character_id": character_id,
            "status": "scaffold_only",
            "active_conditions": [],
        }
        return json.dumps(payload)

    return dspy.Tool(
        list_active_conditions,
        name="list_active_conditions",
        desc=(
            "Return the conditions currently active on the given character (or "
            "the player's character by default). Use this before narrating to "
            "remember what's already tagged on the player."
        ),
        args={
            "scene_id": {"type": "string", "description": "The active scene's UUID."},
            "character_id": {
                "type": "string",
                "description": "Optional character ID; default is the player's PC.",
                "default": "",
            },
        },
    )
