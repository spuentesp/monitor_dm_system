# Gap Analysis: What's Missing for the Full Software Experience

> **Created:** 2026-06-19. Traces the dependency chain from product vision
> through use cases to identify what's actually missing — not just "marked
> in-progress" but what breaks the experience if you try to play end-to-end.

## The Core Question

The use cases build on each other: you can't play (P-*) without a world (M-*),
which needs data layer (DL-*), which needs rules (RS-*). The question is: **if
a user sits down right now and tries the full experience, where does it break?**

## The Dependency Chain (what must work for the game loop)

```
World Creation ──→ Character Creation ──→ Start Session ──→ Play Loop ──→ End Scene
     │                    │                    │                │              │
     ▼                    ▼                    ▼                ▼              ▼
  M-4/M-5             M-12/M-13            P-15            P-1→P-8         P-8
  (universe)          (character)         (session)       (turn cycle)    (canonize)
     │                    │                    │                │
     ▼                    ▼                    ▼                ▼
  DL-1..DL-14        DL-20 (rules)       SYS-1..SYS-3     DL-24 (dice)
                                          DL-26 (state)
```

## What Actually Works (verified live, 2026-06-14 playtest)

| Step | Use Case | Status | Evidence |
|------|----------|--------|----------|
| 1. Create world | M-4/M-5, I-12 (quick-world) | ✅ **Works** | Quick-world seed → universe with entities in <40s |
| 2. Start session | P-15 | ✅ **Works** | Demo world → bound session → narrates turn 1 |
| 3. Play turns | P-1..P-4 | ✅ **Works** | 15-turn playtest: 15/15 succeeded, continuity held |
| 4. Resolve actions | P-9, DL-24 | ✅ **Works** | Resolver engaged (success levels alternated) |
| 5. Canonize | P-8 | ✅ **Works** | CanonKeeper commits proposals to Neo4j |
| 6. End scene | P-8 | ✅ **Works** | Scene-end choreography runs, story state advances |
| 7. Ingest PDF | I-1..I-6 | ✅ **Works** | Tiny PDF → completed job → ready pack (78s) |
| 8. Co-pilot | CF-1..CF-8 | ✅ **Works** | All surfaces 200 with real output |
| 9. Audit trail | Q-10 | ✅ **Works** | Change log captures committed proposals |

**The core game loop works end-to-end.** A user can create a world, start a
session, play 15+ turns with coherent narration, and end the scene. This is
the single most important fact.

## What's Missing — Ranked by Impact on the Experience

### 🔴 Critical: Breaks a core promise if absent

#### 1. Mechanical layer doesn't affect play (T-092 carryover)
**Vision:** O2 (Playable Narrative Experiences), O3 (Rules Handling)
**Use cases:** P-9 (dice), P-16 (combat), DL-24 (resolutions), DL-26 (state)
**What works:** The resolver runs, the game system loads, working_state seeds.
**What was broken:** Resources seed but **don't decrement from prose combat**.
The resolver emits no resource deltas without game-system damage rules. The
CombatPanel/HUD shows initial state but never changes. Combat happens in prose,
never in mechanics.
**Fix (committed `e19c10c`):** `_extract_combat_resource_deltas` now compares
each combatant's post-combat HP to their pre-combat HP and emits `resource_delta`
dicts for the PC. These are merged into `result['resource_deltas']` which
`persist_working_state` applies to the working state. 5 unit tests pass.
*Live verification pending (requires combat encounter on dockerized stack).*

#### 2. Turn latency: 25s median vs <3s target (T-091)
**Vision:** O2 (Playable Narrative Experiences) — "feels like a game, not a loading screen"
**What works:** T-091 committed: per-span timing, prompt caching, streaming,
resolver on fast model. Median cut from 27s.
**What's broken:** Still 8-13× the target. The <8s median verify gate hasn't
been confirmed green on the live stack.
**Fix needed:** Verify the T-091 perf gains on the live stack; if still >8s,
profile and optimize the remaining hot path.

#### 3. P-16 Combat Encounter Management — not implemented
**Vision:** O2, O3 — "full solo RPG gameplay"
**Use case:** P-16 (priority: **critical** in YAML, status: in-progress)
**What exists:** DL-25 (combat state) schema + tools, resolver supports
success levels, conditions.
**What's missing:** No initiative order, no round tracking, no tactical combat
flow. The resolver handles individual action resolution but there's no
"combat encounter" orchestrator that manages initiative, rounds, and
participant turns.
**Impact:** Combat is narrative-only. You can say "I attack" and the GM
narrates the outcome, but there's no structured combat with initiative,
rounds, HP tracking, or victory/defeat.

### 🟡 Important: Degrades the experience but doesn't break it

#### 4. P-6 Answer Question — partially implemented
**What exists:** Oracle question endpoint works (verified in playtest).
**What's missing:** The full perception/knowledge/lore question routing
described in P-6 is not fully wired — the oracle is a simpler path.

#### 5. P-7 Meta Commands — stub
**What exists:** OOC routing works (test_roleplay_ooc.py passes).
**What's missing:** P-7 YAML says "Automatically scaffolded from legacy
markdown extraction. Needs detailed summary." — acceptance criteria are TBD.

#### 6. P-21 Downtime & Character Progression — ✅ XP + level-up wired
**Vision:** O5 (World Evolution Over Time)
**What exists:** XP/level bar in CombatPanel (T-071), game system advancement
schema.
**Implemented (G-1 `cdea3c9`, G-2 `3dc647a`):** XP is now awarded each turn
based on success level + the advancement model. `POST /characters/{id}/level-up`
checks the progression table and applies level-up (features gained, resource
increases). `xp` and `level` fields added to `CharacterWorkingState`.
**Still missing:** No downtime *phase* (a dedicated rest/training mode between
story arcs). The level-up is player-initiated via API, not automatic.

#### 7. P-17 Social Encounter Management — partial
**What exists:** Social read (stance/trust/fear) persists across turns
(T-092 session persistence). CF-3 threads work (T-094 fixed).
**What's missing:** No structured social encounter flow (disposition tracking
as a game mechanic, not just narrative).

#### 8. P-20/P-19 — not verified
**P-19** (Scene transitions) and **P-20** (Story arc management) are
in-progress. The scene-end choreography works, but story arc progression
(moving from "active" to "resolution" to "completed") is not fully verified.

### 🟢 Nice-to-have: Completeness, not experience-breaking

#### 9. P-12 Flashback Mode — not implemented
#### 10. P-13 Party Management — ✅ API wired (G-4 `f71f428`)
Schema existed (DL-15/16). Now has full API: create party, list parties,
add/remove members, set active PC. Session creation already accepts
`controlled_character_ids`. *UI party switcher not yet built.*
#### 11. P-14 Flashback — not implemented
#### 12. RS-5 Card-Based Mechanics — schema exists (DL-22), no resolver path

## The "Does the Game Loop Work?" Answer

**Yes, the core game loop works.** Verified by:

1. **`tests/e2e/test_00_mvp_smoke.py`** — full playable loop: create turn →
   narrate → resolve → canonize → verify entity in Neo4j. Passes with
   `RUN_E2E=1`.

2. **`scripts/live_gameplay_smoke.py`** — drives a scripted session against
   the live stack: universe → character → story → 3 turns → end scene →
   assert Neo4j entities/facts + Mongo turns + Qdrant memories. Exit 0.

3. **15-turn live playtest (2026-06-14)** — fresh Millhaven session,
   scripted investigation → combat → climax → oracle. 15/15 turns succeeded,
   continuity held (14/15 echoed prior proper nouns), coherent mystery across
   the full arc.

4. **5,981 unit tests pass** — 0 failures, covering all layers.

**What doesn't work in the loop:** the *mechanical* layer (HP/combat/XP) is
built but not exercised by default play. The loop is narrative-only — you
play by talking, the GM narrates, and the system tracks canon. But dice,
HP, and combat mechanics don't actually affect the narrative.

## What Would Make It "Complete"

| Priority | Gap | Effort | Impact | Status |
|----------|-----|--------|--------|--------|
| 1 | Wire damage deltas (T-092 carryover) | Medium | HP drops in combat | ✅ **Done** (`e19c10c`) |
| 2 | XP awarding + level-up (P-21) | Medium | Characters grow from play | ✅ **Done** (G-1 `cdea3c9`, G-2 `3dc647a`) |
| 3 | Combat integration tests | Small | Verify HP delta wiring | ✅ **Done** (G-3 `7149b28`) |
| 4 | Party API (P-13) | Medium | Multi-character play | ✅ **Done** (G-4 `f71f428`) |
| 5 | Downtime phase trigger + API (P-21) | Small | Resolution arc unlocks progression | ✅ **Done** (G-5 `31536a49`) |
| 6 | Hook quality grounding (CF-4) | Small | Hooks reference real entities | ✅ **Done** (G-6 `e062656`) |
| 7 | Deeper contradiction detection (CF-5) | Small | Status/location contradictions caught | ✅ **Done** (G-7 `227047b`) |
| 8 | E2e test for mechanical layer | Small | Verify P-21/T-092 end-to-end | ✅ **Done** (G-8 `89c1422`) |
| 9 | Verify T-091 latency <8s on live stack | Small | Game feels responsive | ⏳ Live verify pending |
| 10 | P-16 Combat encounter orchestrator | Large | Structured tactical combat | 🟡 Loop exists, needs full integration |

## Use Case → Vision Alignment Summary

| Vision Objective | Use Cases | Coverage | Gap |
|------------------|-----------|----------|-----|
| O1 Persistent Worlds | M-1..M-35, DL-1..DL-26 | ✅ Complete | — |
| O2 Playable Narratives | P-1..P-8, P-15, P-21, P-13 | ✅ Core loop works | Combat HP deltas wired; XP awarding wired; downtime wired |
| O3 Rules Handling | RS-1..RS-7, DL-24, DL-20 | ✅ Schema + resolver + damage | P-16 combat orchestrator needs full integration |
| O4 Assisted GMing | CF-1..CF-8 | ✅ Complete | Hooks grounded to canon entities (G-6); contradictions detect status/location (G-7) |
| O5 World Evolution | P-8, Q-10, DL-18, DL-23, P-21 | ✅ Canon evolves + XP | Level-up API wired; downtime phase wired; e2e covered (G-8) |