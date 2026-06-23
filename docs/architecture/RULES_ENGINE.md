# Game System & Rules Engine

This document explains how MONITOR adjudicates RPG mechanics in a system-agnostic way, allowing it to support multiple game systems (like D&D 5e, Vampire: The Masquerade, or custom systems) without hard-coding rules.

---

## 1. The Schema-Driven Model

The core of the rules engine is the `GameSystem` schema. Instead of writing code for "how to roll an attack," we define the rules in a JSON/MongoDB document.

### Key Components of a Game System
- **Attributes:** The core stats (e.g., Strength, Dexterity, Blood, Humanity).
- **Derived Stats:** Formulas calculated from attributes (e.g., HP = Strength * 5).
- **Core Mechanic:** The fundamental rolling logic (e.g., "1d20 + modifier" vs "Dice Pool of d10s").
- **Difficulty Scales:** What constitutes a "Standard," "Hard," or "Impossible" task.

---

## 2. GameSystemRuntime (Layer 2)

The `GameSystemRuntime` utility (`packages/agents/src/monitor_agents/game_system.py`) is the "Execution Engine" for these schemas.

### What it does:
1. **Validation:** Ensures a character sheet matches the system requirements.
2. **Calculation:** Evaluates derived stats and temporary modifiers.
3. **Roll Translation:** Converts a high-level intent (e.g., "I try to pick the lock") into a specific dice formula based on the character's stats.

---

## 3. The Resolver Agent

The `Resolver` is the agent that actually performs the adjudication. It operates in three modes:

| Mode | Adjudication Pattern |
|------|-----------------------|
| **Narrative** | Pure storytelling. Player actions succeed/fail based on narrative weight. |
| **Dice Standard** | Simple d20 + generic modifier. Used for systems not yet fully ingested. |
| **Dice Game System** | Fully schema-driven. Uses the `GameSystemRuntime` for precise math. |

### Adjudication Flow:
1. **Intent Parsing:** LLM identifies the *mechanical goal* (e.g., "Attack") and the *target* (e.g., "Orc").
2. **Stat Mapping:** `GameSystemRuntime` finds the relevant stats (e.g., "Dexterity" + "Stealth").
3. **Randomization:** The system rolls the dice according to the `Core Mechanic`.
4. **Outcome Generation:** A structured `Resolution` object is created, detailing success, failure, or partial results.

---

## 4. Forced Narrative & Overrides

MONITOR respects player agency and GM fiat:
- **Forced Narrative:** If a player writes an action that *includes* the outcome (e.g., "I kick the door down and it shatters"), the system detects this and skips the dice roll to maintain narrative flow.
- **GM Override:** In Assisted GM mode, the human GM can override any mechanical outcome proposed by the system.

---

## 5. Working State (DL-26)

Mechanics often involve temporary changes (HP loss, spell duration). These are tracked in the **Working State** collection in MongoDB.
- **Persistence:** Working state is updated mid-turn but only "Canonized" (moved to Neo4j) at the end of a scene if it represents a permanent change.
- **Recovery:** If a game is resumed, the system reloads the character's working state to ensure they are still wounded/exhausted from the previous session.
- **System-derived state tags (no hardcoding):** When working state is persisted, `canonical_state_tags` derives Neo4j state tags **only** from the bound game system's track data — each track's `threshold_effects` (`value` / `direction` / `effect`) and `depleted_effect`, evaluated at the staged post-turn value via `GameSystemRuntime.evaluate_track_threshold`. Already system-derived condition tags pass straight through. There is **no** hardcoded HP≤0 → `unconscious`/`wounded` mapping and **no** alias table: e.g. Mistlands Core declares `Health` with `threshold_effects:[{value:5, direction:at_or_below, effect:"Wounded"}]` and `depleted_effect:"Unconscious"`, so a PC is tagged `wounded` at HP ≤ 5 and `unconscious` at HP 0 purely from data. Only short, tag-like effects become tags; full-sentence effects are left for the narrator. Add new state vocabulary by editing the system's track data (which re-seeds on startup), never Python literals.

---

## 6. Dynamic Scenery and Condition Evaluation

To support varying degrees of narrative and mechanical interactions natively, `GameSystemRuntime` parses dynamic **Scenery Rules** and **Condition Definitions** from the active schema document.

### How it works:
1. **Conditions:** The `Resolver` searches the active character's entity properties for conditions (e.g. `poisoned`, `wounded`, `blinded`). The runtime cross-references these with the `ConditionDefinition` schema to apply any `roll_modifier` or `roll_mode_override` (such as `advantage` or `disadvantage`).
2. **Scenery:** The `Resolver` scans the location entity's tags and description. If a tag matches a `SceneryRule` keyword (e.g., `slippery` or `high ground`), and the player's action uses a matching trigger verb (e.g. `run`, `shoot`), the scenery modifier and roll mode override are dynamically mixed into the final resolution mechanic.
3. **Fallback Synonym Resolution:** In `condition-weighted narrative` modes lacking a strict GameSystem schema, the Resolver falls back to an internal synonym mapping (e.g. mapping `dark`, `pitch black`, `dim` to the same penalties) ensuring the rules engine remains flexible without hardcoding strict strings.
