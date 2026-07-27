# Changelog

## v1.0.0 — 2026-06-12

First working release. The FINAL_FABLE effort (see `FINAL_FABLE_PLAN.md` /
`FINAL_FABLE_TASKS.md`) took the project from non-functional to verified:

### Fixed (the big ones)
- **Dev stack**: ui-backend image (editable-install path bug) and Neo4j
  (stale pidfile loop, fake healthcheck, password mismatch) no longer
  crash-loop; all nine containers healthy.
- **Test suite**: hermetic by default (fake keys, socket block, timeouts,
  deadlock-guarded `run_sync`) — from "hangs forever" to 5,904 green tests
  in ~5 minutes; e2e suite (147 tests incl. three mode walkthroughs) green
  against the live stack.
- **Core play loop**: MCP serializer corrupted every `List[Model]` tool
  result; datetimes crashed prompt assembly; `GameSystemRuntime` lost its
  compat aliases; tone resolver crashed on Mongo UUIDs; provider auth
  failures now fall back to the default LLM provider.
- **Canon plumbing**: `neo4j_get_universe_state` queried a graph shape that
  was never written (state/snapshots were always empty); pack apply/canonize
  crashed on a nonexistent enum member; PlotHookAgent called every tool with
  the wrong envelope; CanonKeeper's scene-end fact write was malformed;
  contradiction detection flagged "Elves are immortal" vs "Dwarves are
  mortal" (substring antonyms, no subject check); Neo4j schema bootstrap was
  invalid Cypher so no constraints/indexes had ever been created.
- **Dedup**: dead shadow copy of the facts tool family removed; six schema
  name collisions resolved; shared helper module; five overlapping status
  docs consolidated into `docs/STATUS.md`; use-case taxonomy repaired.

### Added
- Hermetic CI + nightly integration workflows (lint, layers, suite, build,
  Playwright).
- Frontend bridges for previously dark routers: semantic search page, mode
  switcher, tone manager, performance dashboard, lorebook editor wiring,
  fork-universe and end-scene actions.
- Mode walkthrough e2e tests + hand-runnable UI scripts; live gameplay smoke
  via `monitor playtest live`.
- `scripts/demo_millhaven.py` — one command to a playable demo world.
- Aggregated `/api/health?deep=true`; OTLP/logfire export passthrough.

### Known deferrals
See `docs/STATUS.md` (P-21 autonomous PC, mutation testing, remaining pack-ops
UI, latency targets vs measured baselines).
