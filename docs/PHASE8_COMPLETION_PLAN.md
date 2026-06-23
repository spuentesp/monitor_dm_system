# Phase 8 Completion Plan — Vision Hardening & Gap Closure

> **Created:** 2026-06-19. Closes the remaining open tasks in
> `FINAL_FABLE_TASKS.md` Phase 8 (T-092, T-093, T-098) and aligns the full
> use-case catalog to the product vision in `SYSTEM.md`.
>
> **Execution rules:** one commit per task; unit + e2e coverage for each;
> docs updated as we go; `check_layer_dependencies.py` green before every
> commit.

## Product Vision → Use Case Alignment

| Vision Objective (SYSTEM.md) | Epic | Key Use Cases | Status | What's needed to realize it |
|---|---|---|---|---|
| **O1 — Persistent Fictional Worlds** | EPIC 1 (World & Multiverse) | M-1..M-35 (CRUD), DL-1..DL-14 (data layer) | ✅ Implemented | Quick-world (T-087) + ingestion (T-082) now create worlds from seeds/PDFs; fork/snapshot/merge all wired |
| **O1 — Persistent Fictional Worlds** | EPIC 2 (Knowledge Ingestion) | I-1..I-13 | ✅ Implemented | PDF ingestion end-to-end (T-082–T-086); edge-case matrix closed; recall benchmark 100% (T-097); embed reliability T-098 open |
| **O2 — Playable Narrative Experiences** | EPIC 4 (Autonomous GM) | P-1..P-21 | ✅ Implemented | Play loop runs 15-turn arcs; latency cut (T-091 done); mechanical layer wiring T-092 open (HUD empty in default play) |
| **O3 — System-Agnostic Rules Handling** | EPIC 5 (Rules Engine) | RS-1..RS-8 | ✅ Schema + resolver | GameSystemRuntime loads from MongoDB; condition-weighted narrative (T-043b); T-092 wires it into default demo/quick-world |
| **O4 — Assisted Human GMing** | EPIC 7 (GM Co-Pilot) | CF-1..CF-8 | ✅ Implemented | Recorder, reflections, recap, threads (T-094), hooks, contradictions, handouts, session prep, canon review all wired |
| **O5 — World Evolution Over Time** | EPIC 6 (Session Tracking) | P-15 (resume), Q-10 (audit) | ✅ Implemented | Session list/resume (T-040); audit trail (T-064); snapshots (DL-23); change log indexed (R5) |
| **Cross-cutting — Character Identity** | EPIC 3 (Identity) | Q-1..Q-11 | ✅ Implemented | Character cards import/export (T-088); standalone characters playable |
| **Cross-cutting — Multiverse Packs** | EPIC 10 (Packs) | MP-1..MP-9 | ✅ Implemented | Pack ops UI (T-061); apply/merge/export/import/clone/slice |
| **Cross-cutting — Quality** | Vision Hardening | T-091..T-098 | 🟡 5/8 done | T-092 (mechanical layer), T-093 (retrieval scoping), T-098 (embed reliability) remain |

## Remaining Open Tasks (execution order)

### 1. T-093 — Retrieval scoping: stop cross-universe bleed
**Baseline:** Millhaven co-pilot reflection cited "Ashfall Reaches" (another universe).
**Root cause:** Memory/knowledge retrieval not universe-scoped in Qdrant.
**Fix (in progress, uncommitted):** Add `universe_id` to `MemoryCreate`, `MemoryFilter`,
`MemoryEmbedRequest`, `MemorySearchRequest`, Qdrant payload + filter; thread `universe_id`
through `persist_memories` in scene_loop/scene_support.
**Verify:** two-universe regression test — retrieval for one never returns the other's tokens.

### 2. T-092 — Wire mechanical layer into default play
**Baseline:** `working_state` empty across 15 demo turns; CombatPanel/HUD never populate.
**Fix (in progress, uncommitted):** `quick-world` with `start_playing` now bootstraps a PC
via `_ensure_demo_pc` and binds `character_id`/`speaker_character_id`/`controlled_character_ids`;
chat router persists `latest_working_state`/`latest_scene_checkpoint`/etc. in session state.
**Verify:** demo playtest shows non-empty `working_state` with HP/resource changes + CombatPanel delta.

### 3. T-098 — Ingestion embed-stage reliability
**Baseline:** Intermittent `RuntimeError: Event loop is closed` at embed stage; ~3-4/5 sequential
ingests fail (job 1 always passes).
**Fix (committed, UNPROVEN):** Per-job Qdrant client + self-healing retry on closed event loop.
**Verify:** 5 sequential ingests all complete; retry logic fires on "Event loop is closed".

## Test Coverage Requirements

| Task | Unit tests | E2E tests | Contract tests | Mutation |
|---|---|---|---|---|
| T-093 | `test_memory_tools.py` universe_id filter + `test_qdrant_tools.py` universe filter | Two-universe regression (live) | Memory schema contract | N/A (mutation removed T-017) |
| T-092 | `test_scene_loop.py` working_state persist | Demo playtest working_state non-empty | Session state contract | N/A |
| T-098 | `test_ingestion_pipeline.py` embed retry | 5 sequential ingests (live) | N/A | N/A |

## Use Case Alignment Verification

After all tasks complete:
- `scripts/check_layer_dependencies.py` — layer boundaries enforced
- `scripts/check_use_case_implementation.py` — use cases referenced in commits
- `scripts/check_ontology_use_cases.py` — taxonomy consistent
- `uv run pytest packages tests -q -m "not integration and not e2e"` — hermetic suite green
- `RUN_E2E=1 uv run pytest tests/e2e -q` — e2e suite green (live stack)
- `uv run ruff check packages` — lint clean
- `npx tsc --noEmit` — frontend type-check clean