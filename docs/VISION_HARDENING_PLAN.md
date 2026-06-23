# Phase 8 — Vision Hardening (quality & performance)

> **Created 2026-06-14** from the measured vision playtest in `docs/STATUS.md`
> ("Vision playtest (2026-06-14)"). Phase 7 proved the plumbing of all four
> pillars *runs* end-to-end. This phase closes the gap between "it runs" and
> "it's good", and every task is anchored to a **measured baseline → target**,
> not a vibe. Tasks are T-091..T-097 in `FINAL_FABLE_TASKS.md`.

**Why these and not more features:** the playtest showed the deltas to the
product vision are *quality, latency, and scoping*, not missing surfaces. So
this phase is deliberately small and measurable.

## Priority order (highest leverage first)

1. **T-091 turn latency** — the single biggest play-feel blocker.
2. **T-092 mechanical layer wired into play** — unlocks the whole combat/
   progression half of the GM vision that currently sits dormant.
3. **T-093 retrieval scoping** — a correctness bug (cross-universe bleed).
4. **T-094 co-pilot quality**, **T-095 GM eval harness**, **T-096 architect
   determinism**, **T-097 ingestion recall** — quality polish + measurement.

---

## T-091 — Turn latency: 27 s median → < 8 s

**Baseline (measured):** 15-turn playtest — median 27 s, mean 25 s, max 39 s
per turn. A turn is **two sequential LLM calls** (`resolver.resolve_turn` →
`narrator.narrate_turn` in `scene_loop.py`) plus a query embedding; context
fetches are already parallel (`context_assembly.py` `asyncio.gather`).

**Approach:**
1. **Profile first** — instrument the three spans (embed / resolve / narrate)
   and log per-turn timings; fix what the numbers show, not what we guess.
2. **Right-size the resolver model** — resolution is a *structured decision*,
   not prose. Run it on a fast/cheap model (e.g. flash/haiku tier) while the
   Narrator keeps the quality model. Wire via the existing node-assignment
   table (`/api/llm/assignments`).
3. **Prompt caching** — cache the static system prompt + world/source-profile
   block (Anthropic/Gemini cache) so only the turn delta is re-sent.
4. **Stream first token** — the WS path exists; stream the Narrator so
   *perceived* latency (first prose) drops under ~3 s even if total holds.
5. **Trim context** — cap entity/memory snippets sent to the Narrator.

**Verify:** 10-turn playtest median total < 8 s; perceived first-token < 3 s
(WS); recorded in `docs/STATUS.md`. No drop in continuity (keep the
14/15-keyword bar from the baseline run).

## T-092 — Wire the mechanical layer into default play (Modular Play Modes)

**Baseline (measured):** across all 15 demo turns `latest_working_state` was
**empty** — the demo session is pure narrative (no character sheet, no
`dice_game_system`), so HP/resources/conditions and the `CombatPanel`/HUD
(T-071/T-078) never populate. Combat happened in prose, never in mechanics.

**Play Mode Specifications (No Hardcoding):**
*   **Full Narrative Mode:** Bypasses mechanical rolls completely, granting full creative control to the player/narrator (diceless, narrative-only progress).
*   **Condition-Weighted Narrative Mode:** Evaluates player character characteristics (attributes, current resource pools, active status tags/conditions like `advantaged`, `fatigued`, `blinded`) and scenery context (location details, environment hazards, active threat levels) to calculate dynamic roll modifiers (e.g. +1/+2 bonuses, -1/-2 penalties, or setting advantage/disadvantage) applied to d20 rolls.
*   **Modularity Invariant:** All attribute, resource track, and modifier equations must be loaded dynamically from MongoDB via the `GameSystemRuntime` based on the active session's system mapping, rather than being hardcoded in Python.

**Approach:**
1.  `demo-world` / `quick-world` bootstrap a **PC character sheet** and bind a database-seeded generic `dice_game_system` so that the resolver can load rule definitions.
2.  Enable the `Resolver` to dynamically parse PC characteristics and scenery to compute bonuses/penalties during checks.
3.  Confirm the resolver/scene-loop **writes `working_state` deltas** each turn (HP, resources, conditions) and the consequence resolver fires.
4.  Confirm `CombatPanel` renders real deltas + XP from that state.

**Verify:** a demo playtest shows non-empty `working_state` with HP/resource
*changes* across turns; `CombatPanel` shows ≥1 delta and an XP value. Default play is wired to use the modular condition-weighted ruleset.

## T-093 — Retrieval scoping: stop cross-universe bleed

**Baseline (measured):** a **Millhaven** co-pilot reflection referenced "the
**Ashfall Reaches**" — a *different* ingested test universe. Narrator memory
search is `story_id`-scoped (`context_assembly._search_memories` filter
`{"story_id": ...}`), but knowledge-pack / co-pilot / architect retrieval is
**not** universe-scoped, so semantic search can return another world's content.

**Approach:**
1. Add a `universe_id` (and/or `multiverse_id`) filter to the qdrant filter on
   the knowledge-collection retrieval used by the co-pilot and architect paths.
2. Make universe scope a required parameter on those retrieval helpers.
3. **Regression test:** ingest two universes with distinctive proper nouns;
   assert retrieval for one never returns the other's tokens.

**Verify:** scoping test passes; a repeat Millhaven co-pilot reflection
contains zero foreign-universe names across 5 runs.

## T-094 — Co-pilot output quality: threads + hooks + contradictions

**Baseline (measured):** every CF surface returned 200, but `CF-3` story
threads = **0** for an active story; plot hooks were generic ("Welcome to
Millhaven"); `CF-5` contradictions returned 0 in 2.6 s (depth unverified).

**Approach:**
1. **Threads:** trace why `GET /stories/{id}/threads` is empty — is thread
   extraction wired into the scene/canonize path, and is it persisted? Fix the
   gap so played stories accumulate tracked threads.
2. **Hooks:** ground the hook prompt in specific canon (named entities, open
   threads, recent scenes) + few-shot; reject generic titles.
3. **Contradictions:** add a fixture with a planted contradiction and assert it
   is detected (proves the 0 is "none present", not "not analysed").

**Verify:** a story with ≥3 scenes yields ≥1 tracked thread; ≥3/4 hooks name a
real canon entity; the planted-contradiction fixture is caught.

## T-095 — GM quality eval harness (make "quality" a tracked number)

**Baseline:** quality is currently eyeballed (continuity 14/15 was a keyword
proxy, not a judgement of *good GMing*).

**Approach:** `scripts/eval_gm_playtest.py` — replay a fixed N-turn transcript
through an LLM-judge rubric scoring **canon-consistency, continuity,
contradiction-freeness, pacing, and player-agency respect** (0–5 each), output
a JSON report under `docs/testing/`. Run on demand; record a baseline.

**Verify:** the script produces a scored rubric for a real transcript; baseline
scores recorded in `docs/STATUS.md`. (This is the instrument that turns every
later quality change into a number.)

## T-096 — World Architect proposal determinism

**Baseline (measured):** an explicit "create a canon NPC named X" architect
request returned **`committed: 0`** (no structured proposals extracted), and
succeeded only on retry — non-deterministic for a core creation promise.

**Approach:** stricter proposal output schema + **retry-on-empty**; a
deterministic fallback that, when the user explicitly says "create/add/commit
<entity>", constructs the proposal directly rather than relying solely on the
DSPy extraction.

**Verify:** 5/5 explicit "create NPC named X" requests commit ≥1 entity and it
appears in the Worlds tree + change log.

## T-097 — Ingestion recall benchmark + huge-doc / OCR decision

**Baseline (measured):** ingestion works (tiny PDF → 14 entities) but *recall*
is unmeasured; >50 MB is rejected (not streamed); scanned PDFs have no OCR.

**Approach:** a labelled fixture PDF with a known entity/fact set → measure
precision/recall of extraction; make an explicit decision on huge-doc chunked
streaming vs. the current hard reject; OCR as an opt-in path.

**Verify:** recall ≥ an agreed bar on the fixture (record the number);
documented decision + ticket for huge-doc/OCR.

---

## Acceptance for "Vision-hardened"

1. Turn median < 8 s, first-token < 3 s, continuity held.
2. A default playtest exercises *mechanical* state (HP/combat/XP), not just prose.
3. No cross-universe retrieval bleed (regression-tested).
4. Co-pilot threads/hooks/contradictions produce grounded, non-empty output.
5. A repeatable GM-quality score exists and has a recorded baseline.
