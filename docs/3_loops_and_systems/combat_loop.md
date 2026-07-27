---
description: "The Combat Loop — tactical encounter state machine, entered from the Scene Loop."
tags: [loop, langgraph, combat]
layer: 2
---

# Combat Loop

**Intent:** Run a tactical combat encounter turn structure (initiative order,
per-combatant actions, victory check) when a scene escalates to combat.

**Source:** `packages/agents/src/monitor_agents/loops/combat_loop.py`.
**Entered from:** the Scene Loop's `resolve` step routes into combat when the
GM's `subsystem_hint` is combat.

## Flow

```
roll_initiative → choose_combatant → resolve_action → narrate_combat → check_victory
```

- `roll_initiative` — order the combatants for the round.
- `choose_combatant` — advance to the next actor (player or NPC).
- `resolve_action` — adjudicate the chosen action's mechanics (uses the same
  schema-driven stat/DC routing as the Scene Loop, via
  [RetrievalService.nearest](../architecture/RETRIEVAL_SERVICE.md)).
- `narrate_combat` — GM prose for the exchange.
- `check_victory` — loop to the next combatant, or exit when the encounter ends.

## See Also
- [Scene Loop](./scene_loop.md) · [GM as Authority](../architecture/GM_AS_AUTHORITY.md)
