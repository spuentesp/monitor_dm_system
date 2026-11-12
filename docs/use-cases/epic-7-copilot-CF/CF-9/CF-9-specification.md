# CF-9: Run an Encounter at the Table

**Actor:** Human GM
**Trigger:** A fight starts during a session; the GM opens the **Combat** panel on `/gm`

**Purpose:** Track initiative, HP, and conditions for a live encounter without
leaving the GM page, and stage the encounter's permanent world effects for
CanonKeeper review — never writing the world graph directly.

**Flow:**
1. The GM selects a universe (and a story, for proposal scope) and starts an
   encounter with the night's combatants (name, side, HP/max HP)
2. Initiative is entered per combatant; the server computes a deterministic
   turn order (score → tie-break → name) and optionally narrates it
3. Round by round the GM applies damage/heal (dice expressions roll
   server-side through `POST /gm/roll`), adds/removes condition tags, and
   toggles unconscious/dead flags per combatant
4. Conditions are free-text tags; clicking a tag asks the agent what it does
   (structured definition from the bound game system when it has one,
   free-text guidance otherwise)
5. The GM advances rounds with one click and, when the fight is over, ends
   the encounter
6. Ending stages one FACT proposal per casualty ("X died in combat") plus one
   per GM-declared world effect (faction reactions, lore consequences) into
   the CF-8 Canon Review queue, and returns a best-effort LLM summary

**Output:** a live tracker state (round, ordered combatants, HP, conditions)
plus staged `ProposedChange` items in the CF-8 queue

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_combat_start(params)            # create/replace (universe, session) state
mongodb_combat_get(universe_id, session_id)
mongodb_combat_update_combatant(params) # HP math, conditions, flags
mongodb_combat_set_initiative(params)   # deterministic order with tie-breaks
mongodb_combat_next_round(params)
mongodb_combat_end(params)
# Permanent effects leave only as ProposedChange items (CF-8 path).
```

**Layer 2 (Agents):**
- `CombatAgent` (`monitor_agents/combat/`) — deterministic state ops over MCP;
  optional DSPy bits: initiative narration, condition explanation fallback,
  end-of-encounter summary. HP math and round advance are plain code.

**Layer 3 (UI):**
- Routes in `routers/gm_tools.py` behind the tenancy guard
  (`require_universe_owner` on every request):
  `POST /gm/combat/start`, `GET /gm/combat/{session_id}`,
  `POST /gm/combat/{session_id}/initiative`,
  `PATCH /gm/combat/{session_id}/combatant/{id}`,
  `POST /gm/combat/{session_id}/next-round`,
  `POST /gm/combat/{session_id}/end`, `POST /gm/combat/condition-explain`
- `components/gm/CombatPanel.tsx` in `GM_PANELS` on the `/gm` page

**Out of scope (v1):** automated enemy AI turns, map/grid positioning, spell
resource pools, loot distribution (loot stays on the session-log proposal
path).

**Open decisions (G01) — v1 choices:**
- Enemy stat blocks: read-only reference (canon entity links on combatants)
  plus the existing improvise/lookup endpoints; no ad-hoc persisted blocks.
- Condition effects: structured definitions from the bound game system when
  present, free-text tags otherwise.

---

**Status:** done — implemented 2026-11-11 (gap G01, plan
[docs/architecture/gm-assistant-gap-plans/G01-combat-tracker-CF-9.md](../../../architecture/gm-assistant-gap-plans/G01-combat-tracker-CF-9.md)).
