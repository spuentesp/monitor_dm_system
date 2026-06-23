# Phase 8B — Session Review Remediation Plan

> Created 2026-06-14 from a full review of this session's work. Closes the gaps
> found against four criteria: **docs updated · tests made · no hardcoding ·
> new data is seeded/ingested.** Every task lands only when its *Verify* passes.

## Conditions (apply to every task — non-negotiable)

- **C1 — Proof, not claims.** A task is done only when its `Verify` passes
  *live or by test*. No "done" without the command output that proves it.
- **C2 — No hardcoding.** Attributes, resource tracks, and modifier/resource
  equations load dynamically from MongoDB via `GameSystemRuntime` for the
  session's system — never Python literals. Per-character *chosen values* are
  data, not formulas, and are fine; *derived* values (HP from a formula) are not.
- **C3 — New data is seeded.** Anything new added to a data file
  (`builtin_systems.json`, etc.) must seed idempotently on app startup and be
  verified present on a fresh-ish DB — not rely on a lazy/incidental trigger.
- **C4 — No collision.** Do not edit files in the other party's uncommitted
  working tree. Coordinate or wait for a commit. Ownership is marked per task.
- **C5 — No background wait-loops.** Foreground commands only; leave no orphan
  shells. (This session created 15 stuck `until ! pgrep` loops — never again.)
- **C6 — Docs + tests ship with the fix**, in the same commit.

## Status legend
`[x]` done+proven · `[~]` in progress · `[ ]` todo · owner: **me** / **you** / **coord**

---

## A. Already fixed + proven (this review)

- [x] **R1 — Seed builtin game systems on startup** (own: me). `main.py` lifespan
  now calls `_ensure_builtin_systems_seeded()` (idempotent upsert) next to tone
  builtins. *Verified:* hook runs without raising; "Mistlands Core" present in DB.
- [x] **R2 — change_log tool tests** (own: me). 4 hermetic unit tests for
  append/list/builder (`test_change_log_tools.py`). *Verified:* 4 passed.
- [x] **R3 — plot-thread datetime regression test** (own: me). Uses a real
  `neo4j.time.DateTime`; fails without `_to_native_datetime`. *Verified:* passes.

## B. Hardcoding (C2) — coordinate, blocked on your rules-engine WIP

- [x] **R4 — De-hardcode the demo PC** (own: me). `_DEMO_PC_PROPS` removed;
  `_demo_pc_properties()` now derives resources from the bound system via
  `GameSystemRuntime.derive_resources` (`Health = 10 + Grit_modifier` → 11 for
  Grit 12). Attribute *values* stay as data. Also taught `_derive_resources` to
  resolve `<Attr>_modifier` tokens (previously dropped). *Verified:* `derive_resources`
  yields `{Health:11, Nerve:6}` live; `test_resource_derivation.py` (3) +
  `test_forge_demo_pc.py` (3) assert no literal resource dict and Health==11.
  Commit `653c0e45`.

- [x] **R10 — De-hardcode state tags** (own: me, new this pass). `canonical_state_tags`
  + canonkeeper no longer hardcode `HP<=0 → unconscious/wounded` or a tag alias
  table; tags derive from each track's `threshold_effects`/`depleted_effect` via
  `evaluate_track_threshold` (now reading the real `value/direction/effect` schema)
  plus pass-through of system-derived condition tags. Mistlands Health track seeded
  with `wounded(<=5)/unconscious(0)` so the vocabulary lives in data. *Verified:*
  `test_state_tag_derivation.py` (12); all 8 builtins validate. Commit `e3fa019f`.

## C. New data / schema (C3) — coordinate + me

- [x] **R5 — change_log MongoDB indexes** (own: me). Added to
  `MongoDBClient._create_indexes` (change_id unique, subject_id+timestamp,
  subject_type, transaction_id, author, timestamp). *Verified:* live
  `index_information()` shows all 6 + hermetic test passes.
- [x] **R6 — `rule_type='condition'` enum** (own: **you**). Resolved two ways:
  `CONDITION = "condition"` added to `GameRuleType` (your uncommitted WIP) **and**
  conditions moved into the dedicated `conditions: List[ConditionDefinition]`
  field — no builtin rule uses `rule_type='condition'` anymore. *Verified (parse,
  hermetic):* all 8 builtins parse through both `GameSystemCreate` and
  `GameSystemResponse` with **0** ValidationErrors; no rule carries an out-of-enum
  `rule_type`. Enum landed in commit `4f8513b5`. Live `/api/entities/systems` +
  `/api/llm/providers` 200-check still pending a running server.

## D. Test coverage (C6) — me

- [x] **R7 — Frontend test harness + component tests** (own: me). Stood up vitest;
  extracted the pure projections (CombatPanel `flattenStats`/`readProgression`,
  `workingStateChips`, HistoryTab `changeIcon`/`changeColor`) into `@/lib` modules
  and covered them. *Verified:* `npx vitest run` → **19** passed; `tsc --noEmit`
  clean. Commit `f5f9ac2b`.

## E. Carry-over Phase-8 tasks

- [x] **R8 / T-091 — Turn latency + narrator streaming** (own: concurrent session,
  landed + fixed by me). Parallelized the post-narrate extraction nodes (concurrent
  `extract_new_entities` + `extract_memories`), ChainOfThought→Predict on the
  extractors/narrator, Anthropic ephemeral prompt caching (`CachedDSPyLM`), real
  WebSocket narrator streaming, resolver pinned to `ModelRole.LIGHT`. I fixed the
  fan-out edge bug (`add_edge` rejects a list end_key) that broke `build_scene_graph`
  and cleared lint. *Verified (hermetic):* 810 agents + 23 ui-backend chat/streaming
  green; GM quality held 5/5. Commit `78549cae`. **Live gate still open:** 10-turn
  median total < 8 s / first-token < 3 s are observed over WebSocket, not unit-measured.
- [x] **R9 / T-098 — Ingestion embed-stage reliability** (own: me). Self-healing
  retry on `Event loop is closed`: `_upsert_points` resets the cached qdrant client
  and retries once (unrelated RuntimeErrors propagate); added `QdrantClient.reset_client`.
  *Verified:* 5 hermetic retry/reset tests. Commit `83ff485c`. **Live gate still open:**
  10 consecutive ingests → 0 unrecovered failures (needs a build-free window).

---

## Sequencing & coordination

1. **You:** R6 (enum) — unblocks system loading and the 500s. Then your
   GameSystemRuntime work unblocks R4.
2. **Me, independently now:** R5 (change_log indexes), R7 decision.
3. **Me, in a build-free window you grant:** R8 (latency), R9 (embed retry) —
   both need clean stress/measurement runs (no parallel rebuilds).
4. **Coord after your WIP commits:** R4 (de-hardcode demo PC), rebased on your
   GameSystemRuntime so resources derive from the system.

## Definition of "finished"
All of A–E `[x]` with passing Verify; STATUS.md updated; no hardcoded
system-derived values remain; a fresh-DB boot seeds every builtin system; the
full hermetic suite is green.
