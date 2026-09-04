# Full Repo Code Triage — Audit (Design)

Date: 2026-09-04
Status: Awaiting user approval of written spec
Approach: 1 spec, 1 plan, 4 subagent-driven tasks (3 phases + 1 compile), single audit deliverable

## Problem

A previous Lain-driven sweep on 2026-09-03 shipped four low-risk fixes (orphan dead code removal, doc/config commit, Future tracking, FastAPI deprecation rename). It deferred several findings for a fuller triage:

- The residual `coroutine '_ingest_with_capture' was never awaited` RuntimeWarning — a separate bug from the discarded Future fixed in the previous sweep.
- 14 Lain indexing-gap files (mostly frontend `.tsx`, plus `packages/ui/backend/src/monitor_ui/watchdog.py` and `packages/agents/src/monitor_agents/loops/progression_loop.py`).
- 4 stray `print()` calls in production code (`ingestion/agent.py:45`, `schemas/rpg_ontology/topology.py:26,30`, `temporal_tools/scene_validation.py:33`).
- `scripts/lain-mcp-proxy.sh` and `scripts/lain-server-manager.sh` legacy scripts explicitly flagged in `AGENTS.md` as `git rm`-able.
- 8 additional Lain "no callers, no callees" symbols that the previous sweep deferred (test fixtures and entry points — likely false positives but worth confirming with broader context).

Beyond those deferred items, the previous sweep was narrowly scoped (4 specific fixes). The user has asked for a **full triage** that covers the whole repo with broader tool coverage.

## Goal

Produce a single read-only audit document at `docs/superpowers/specs/2026-09-04-full-triage-audit.md` cataloging every notable code-health issue in the repo with severity, location, and a one-line description. No code is modified.

The audit is the deliverable. Future fix cycles (potentially via spec→plan→subagent-driven-development, mirroring the previous sweep) will draw from this audit's findings list.

Non-goals:
- No fixes. The audit describes; the user decides what to fix later.
- No new tests.
- No dependency changes.
- No architectural rewrites; this is observation, not intervention.
- No coverage of the UI frontend beyond what Lain can statically extract. Lain's TS support is weak; the audit will note that explicitly where relevant.

## Architecture

- The audit is a single markdown file in `docs/superpowers/specs/` (co-located with the design spec).
- Three independent phases feed into a compile step:
  - **Phase 1 — Lain structural sweep.** All structural tools (`find_dead_code`, `find_untested_functions`, `get_coverage_summary`, `suggest_refactor_targets`, `find_anchors`, `compare_modules`, `get_blast_radius`, `explore_architecture`, `semantic_search`).
  - **Phase 2 — Security pass.** Grep patterns for hardcoded secrets, wildcard CORS, JWT/auth bypass, `eval`/`exec`, `shell=True` with user input, debug endpoints, unvalidated request input, path traversal.
  - **Phase 3 — Correctness pass.** Grep patterns for bare `except:`, swallowed exceptions, `print()` in production code, `TODO`/`FIXME`/`XXX` markers, unjustified `# type: ignore`, `assert` in production modules, `asyncio.run` inside async contexts, `global` keyword, mutable default arguments.
- Phase 4 — Compile + executive summary. Reads Phase 1/2/3 outputs, deduplicates, assigns T-NNN IDs, grades severity, writes the executive summary.

Each phase is a subagent-driven task with its own ledger entry and reviewer; this isolates per-phase output so a reviewer can judge without re-running the tools.

## Audit document structure

```markdown
# Full Repo Code Triage — <date>

## Executive summary
- Total findings count by severity (Critical / High / Medium / Low).
- Top 3-5 issues that warrant attention first.
- Systemic patterns noticed (e.g., "10 files have similar auth bypass patterns").

## Findings (sorted by severity, then category, then file)
For each finding:
- **ID:** T-001, T-002, ...
- **Severity:** Critical | High | Medium | Low
- **Category:** Dead code | Untested | Coupling hotspot | Refactor target | Blast radius | Security | Correctness | Style | Doc gap
- **Location:** file:line or file:symbol
- **Description:** 1-3 sentences
- **Evidence:** command output snippet that produced this finding
- **Recommended action:** (informational only — not committed to)

## Per-category appendix
Raw tool output, organized by category, for reproducibility. Lets the user re-run any tool and verify.

## Tool limitations
Notes on tools that returned empty, timed out, or are known-weak (e.g., Lain's TS support).

## Deferred / out-of-scope
Items noticed but explicitly not investigated (with rationale). Mirrors the previous sweep's deferred pattern.

## Out-of-scope findings
Items that surface but are clearly feature gaps rather than bugs (e.g., "no rate limiting on /api/login") — noted, not graded.
```

### Severity rubric

- **Critical:** security hole, data loss risk, correctness bug.
- **High:** significant blast radius, untested critical path, obvious dead code in hot path.
- **Medium:** refactor target, untested helper, coupling smell.
- **Low:** style nit, minor doc gap, cosmetic.

## Execution shape

Subagent-driven-development (same as the previous sweep on 2026-09-03):

| Task | Phase | Subagent role | Output |
|---|---|---|---|
| 1 | Phase 1 — Lain structural | implementer + reviewer | Phase 1 section appended to audit file |
| 2 | Phase 2 — Security grep | implementer + reviewer | Phase 2 section appended |
| 3 | Phase 3 — Correctness grep | implementer + reviewer | Phase 3 section appended |
| 4 | Compile + executive summary | implementer + reviewer | Final audit with T-NNN IDs, severity, exec summary |

Tasks 1–4 run sequentially (the subagent-driven-development skill forbids parallel implementer dispatches). The audit's append-only structure means each task writes into a different section, so sequential ordering doesn't lose information between phases.

Implementation plan lives at `docs/superpowers/plans/2026-09-04-full-triage.md`.

## Validation gates (per-task reviewer)

- Tool output is reproducible — implementer report shows the exact commands run.
- Findings are deduplicated — same issue found by two tools → one T-NNN.
- Severity grading matches the rubric.
- Executive summary doesn't contradict the findings list.

## Error handling

- If a Lain tool times out or returns empty (as `get_blast_radius` did on underscore-prefixed symbols in the previous sweep), the audit notes the limitation under "Tool limitations" rather than skipping silently.
- If grep returns 0 hits for a security pattern, the audit records "checked, no findings" rather than omitting the check.
- If a phase's subagent can't complete (infra unavailable, etc.), the audit records the partial result and the missing phases — no fabrication.

## Contingencies

- **Audit size cap:** if raw findings exceed ~150, the compile task splits Medium/Low into a "lower priority" appendix and keeps the top 50 in the main findings list. Prevents an unusable wall of text.
- **Re-running a phase:** each task's commit is atomic; if a user wants to redo Phase 2 with a tightened pattern list, it's a single new commit amending the audit. No replay of Phases 1 or 3 needed.
- **Out-of-scope findings:** see the "Out-of-scope findings" section in the audit structure — feature gaps are noted, not graded.

## Existing infrastructure to reuse (do not duplicate)

| Capability | Where | Notes |
|---|---|---|
| Lain MCP server config | `.claude/settings.json` | Already pins `--workspace` and `--embedding-model` directory; persistent server used by Phase 1 subagents that need `semantic_search`. |
| `oneshot` CLI for transient probes | `~/.local/lain/lain oneshot <tool>` | Used by all phases for fast invocations that don't need NLP model. |
| Test runners | `uv run pytest packages/<pkg> -q` | Not used by the audit itself (read-only). Task 4 runs the four package suites once at the end as a sanity check that the audit's documentation activity didn't accidentally affect anything (it shouldn't, but the check costs ~10 min). |
| `docs/superpowers/specs/` convention | Existing spec files | Audit lands here, co-located with the design spec. |

## Out of scope for this spec

- Fixing any findings. The audit is the deliverable.
- Coverage of test files (the correctness pass explicitly excludes tests/ from `print()` checks).
- Coverage of `docs/` directory content (out of scope for code health).
- Integration tests (`tests/` requires external services — Mongo/Neo4j/Qdrant — not currently running).

## Risks

- **Audit size explosion.** If the codebase has more findings than expected, the compile step's 150-finding cap keeps the main list usable but pushes Medium/Low to an appendix. Acceptable trade-off.
- **Lain tool flakiness.** `find_dead_code` and similar tools are heuristics; they flag false positives. The compile step must explicitly filter known false-positive categories (test symbols, serde attrs, entry points/callbacks).
- **Underwater repo state.** Some Lain findings depend on the persisted graph (`graph.bin`) being up to date. As of `032e466` (current HEAD), the graph is enriched against the correct commit. Phase 1 subagent must verify this and trigger `run_enrichment` if not.
