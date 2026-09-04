# Full Repo Code Triage — Audit Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a single read-only audit document (`docs/superpowers/specs/2026-09-04-full-triage-audit.md`) cataloging every notable code-health issue across the whole repo with severity, location, and one-line description. No code modified.

**Architecture:** Three sequential information-gathering phases (Lain structural, security grep, correctness grep) feed a fourth compile step that deduplicates, assigns T-NNN IDs, grades severity, and writes the executive summary. Each phase writes into a separate section of the audit; the audit is append-only across Tasks 1-3, then finalized in Task 4.

**Tech Stack:** Lain MCP server (already configured in `.claude/settings.json`, persistent server for `semantic_search`; transient via `oneshot` for everything else), `uv run` for test sanity, `git` for commits, `grep`/`Grep` for security + correctness patterns.

## Global Constraints

- Branch: `master`. Working tree is currently clean at `032e466`. Tasks 1-4 land as 4 separate commits on `master`.
- The audit lives at `docs/superpowers/specs/2026-09-04-full-triage-audit.md` — co-located with the design spec at `docs/superpowers/specs/2026-09-04-full-triage-design.md`.
- No code files modified, no tests added, no dependencies installed.
- Each task ends with a single commit. Commit messages reference the task number.
- Per-task reviewers (subagent-driven-development) verify tool-output reproducibility, finding dedup, severity grading, and exec-summary accuracy.
- SDD skill forbids parallel implementer dispatches — Tasks 1-4 run sequentially.
- Severity rubric (Critical / High / Medium / Low) is defined in the spec §"Severity rubric" and used uniformly across all four tasks.
- The four-package test suite (`uv run pytest packages/{data-layer,agents,cli,ui/backend} -q`) is run exactly once at the end of Task 4 as a sanity check that documentation activity didn't break anything. Not run during Tasks 1-3.

---

## File Structure

| File | Created/Modified by | Responsibility |
|---|---|---|
| `docs/superpowers/plans/2026-09-04-full-triage.md` | This plan (now) | Implementation plan. |
| `docs/superpowers/specs/2026-09-04-full-triage-audit.md` | Task 1 (create); Tasks 2-3 (append); Task 4 (finalize) | The audit deliverable. |

No other files in the repo are touched.

---

## Task 1: Phase 1 — Lain structural sweep

**Files:**
- Create: `docs/superpowers/specs/2026-09-04-full-triage-audit.md` (with header, exec-summary stub, Phase 1 section)

**Interfaces:**
- Consumes: Lain MCP tools (`get_health`, `find_anchors`, `find_dead_code`, `find_untested_functions`, `get_coverage_summary`, `suggest_refactor_targets`, `compare_modules`, `get_blast_radius`, `explore_architecture`, `semantic_search`). Persistent Lain server (configured in `.claude/settings.json`) is required for `semantic_search`; transient `oneshot` is sufficient for everything else.
- Produces: A new file at `docs/superpowers/specs/2026-09-04-full-triage-audit.md` with the markdown header (per the spec §"Audit document structure"), an `## Executive summary` stub (filled by Task 4), and a `## Phase 1 — Lain structural findings` section listing every raw finding with location, category, and one-line description. The per-category appendix at the end of the file holds the raw tool output for reproducibility.

- [ ] **Step 1: Verify the persisted Lain graph is at the current HEAD**

Run:
```bash
git rev-parse HEAD
~/.local/lain/lain oneshot get_health --workspace /home/sebastian/orca/monitor_dm_system \
  | grep -E "Last Enriched Commit|Status"
```

Expected: `Last Enriched Commit: 1dae3ceec73979915425339d0701fcb6c3622a17 (current)` and `Status: Operational ✅`. If the graph is stale (commit SHA differs from current HEAD), trigger enrichment:

```bash
~/.local/lain/lain oneshot run_enrichment --workspace /home/sebastian/orca/monitor_dm_system
```

then re-check `get_health`. Enrichment is async — wait ~60s and re-check.

- [ ] **Step 2: Capture graph baseline**

Run:
```bash
~/.local/lain/lain oneshot get_health --workspace /home/sebastian/orca/monitor_dm_system
```

Expected: a JSON response with node counts, edge counts by type, NLP model status, language support matrix. Save the full output verbatim to `/tmp/lain_phase1_health.txt` (this file is temporary, not committed; the audit file's appendix is the persistent record).

- [ ] **Step 3: Run `find_anchors`**

Run:
```bash
~/.local/lain/lain oneshot find_anchors --workspace /home/sebastian/orca/monitor_dm_system
```

Expected: top-10 architectural pillars (most-called symbols) with anchor scores. Save to `/tmp/lain_phase1_anchors.txt`. Capture the top 10 symbols — these are the inputs to Step 8.

- [ ] **Step 4: Run `find_dead_code`**

Run:
```bash
~/.local/lain/lain oneshot find_dead_code --workspace /home/sebastian/orca/monitor_dm_system
```

Expected: list of unreferenced symbols with the standard Lain preamble (1536 test symbols excluded, 541 serde-style duplicates excluded, 14 indexing-gap files listed at the bottom). Save to `/tmp/lain_phase1_dead.txt`. **Important:** the raw output's "17 unreferenced symbols" includes 8 from `tools/lain_integration.py` which Task 1 of the previous sweep deleted; those should not appear in the post-sweep graph. If they do, the graph is stale — go back to Step 1.

- [ ] **Step 5: Run `find_untested_functions`**

Run:
```bash
~/.local/lain/lain oneshot find_untested_functions --workspace /home/sebastian/orca/monitor_dm_system
```

Expected: either "All functions appear to have callers or tests" (clean) or a list of untested functions. Save to `/tmp/lain_phase1_untested.txt`.

- [ ] **Step 6: Run `get_coverage_summary` and `suggest_refactor_targets`**

Run:
```bash
~/.local/lain/lain oneshot get_coverage_summary --workspace /home/sebastian/orca/monitor_dm_system
~/.local/lain/lain oneshot suggest_refactor_targets --workspace /home/sebastian/orca/monitor_dm_system
```

Expected: per-module coverage estimates and god-object / high-coupling candidates. Save both outputs to `/tmp/lain_phase1_coverage.txt` and `/tmp/lain_phase1_refactor.txt`.

- [ ] **Step 7: Run `compare_modules` on the top coupling pair**

Pick the two modules with the highest coupling from Step 6's refactor-target output (or any two adjacent-by-RPC modules). Default: `compare_modules` on `packages/data-layer/src/monitor_data/db/neo4j.py` and `packages/data-layer/src/monitor_data/db/mongodb.py` (the top two anchors from the previous sweep, both data-layer clients).

Run:
```bash
~/.local/lain/lain oneshot compare_modules \
  '{"module_a":"packages/data-layer/src/monitor_data/db/mongodb.py","module_b":"packages/data-layer/src/monitor_data/db/neo4j.py"}'
```

Expected: stability and coupling metrics for the two modules. Save to `/tmp/lain_phase1_compare.txt`.

- [ ] **Step 8: Run `get_blast_radius` on the top 10 anchors**

Use the top 10 symbols from Step 3's `find_anchors` output. For each, run:

```bash
~/.local/lain/lain oneshot get_blast_radius --workspace /home/sebastian/orca/monitor_dm_system \
  '{"symbol":"<SYMBOL>"}'
```

Note: Lain only indexes non-underscore-prefixed symbols. If `<SYMBOL>` returns "Node not found", that itself is a finding (note under "Tool limitations" — underscore-prefixed methods aren't indexed, consistent with the previous sweep).

Save all 10 outputs to `/tmp/lain_phase1_blast_<N>.txt`. Concatenate into a single file `/tmp/lain_phase1_blast_all.txt` for the appendix.

- [ ] **Step 9: Run `explore_architecture`**

Run:
```bash
~/.local/lain/lain oneshot explore_architecture --workspace /home/sebastian/orca/monitor_dm_system
```

Expected: module-level dependency tree (depth 2 default; if `depth_from_main` is unset, the response will say "run run_enrichment first" — note this under Tool limitations). Save to `/tmp/lain_phase1_arch.txt`.

- [ ] **Step 10: Run `semantic_search` for known concern areas**

`semantic_search` requires the persistent Lain server (not `oneshot`). Use the persistent MCP server (started by Claude Code) via direct JSON-RPC, or skip if unavailable. Probe queries:

```bash
cat > /tmp/lain_semantic.sh <<'EOF'
#!/bin/bash
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"audit","version":"0"}}}'
NOTIFY='{"jsonrpc":"2.0","method":"notifications/initialized"}'
for q in "ingest pipeline threading" "CanonKeeper commit proposal" "scene loop state machine" "resolving contradiction"; do
  CALL=$(printf '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"semantic_search","arguments":{"query":"%s","limit":5}}}' "$q")
  { printf '%s\n%s\n%s\n' "$INIT" "$NOTIFY" "$CALL"; sleep 20; } | \
    ~/.local/lain/lain mcp --workspace /home/sebastian/orca/monitor_dm_system \
      --embedding-model /home/sebastian/orca/monitor_dm_system/.lain/models 2>/dev/null
done
EOF
chmod +x /tmp/lain_semantic.sh
/tmp/lain_semantic.sh > /tmp/lain_phase1_semantic.txt
```

If `semantic_search` returns empty (likely if model isn't loaded by the persistent server yet), note under "Tool limitations" and proceed without — the structural tools from Steps 3-9 already cover structural concerns; semantic search is a quality-of-life addition, not a gate.

- [ ] **Step 11: Filter known false positives**

From the raw output of `find_dead_code` (Step 4), Lain already excludes test symbols, serde attrs, and entry points/callbacks. Manually filter the remaining 17-or-fewer unreferenced symbols by inspecting each:

For each unreferenced symbol:
- `grep -rn "<symbol>" packages/ tests/ scripts/` to verify zero callers anywhere.
- If grep finds a caller (e.g., a string match in a config file, a `__all__` export, a `TYPE_CHECKING` import), exclude from findings — Lain's static analysis missed it.
- Symbols whose only match is the file's own docstring/example are confirmed-dead (these are the actual findings).

Save the filtered list to `/tmp/lain_phase1_dead_filtered.txt`.

- [ ] **Step 12: Write the audit file (Phase 1 section)**

Create `docs/superpowers/specs/2026-09-04-full-triage-audit.md` with this structure:

```markdown
# Full Repo Code Triage — 2026-09-04

## Executive summary
*(Filled by Task 4.)*

## Findings

*(Filled by Task 4 after all phases complete.)*

## Phase 1 — Lain structural findings

*(See below.)*

## Per-category appendix

### A.1 — get_health baseline
\`\`\`
<contents of /tmp/lain_phase1_health.txt>
\`\`\`

### A.2 — find_anchors
\`\`\`
<contents of /tmp/lain_phase1_anchors.txt>
\`\`\`

### A.3 — find_dead_code
\`\`\`
<contents of /tmp/lain_phase1_dead.txt>
\`\`\`

### A.4 — find_untested_functions
\`\`\`
<contents of /tmp/lain_phase1_untested.txt>
\`\`\`

### A.5 — get_coverage_summary
\`\`\`
<contents of /tmp/lain_phase1_coverage.txt>
\`\`\`

### A.6 — suggest_refactor_targets
\`\`\`
<contents of /tmp/lain_phase1_refactor.txt>
\`\`\`

### A.7 — compare_modules (mongodb vs neo4j)
\`\`\`
<contents of /tmp/lain_phase1_compare.txt>
\`\`\`

### A.8 — get_blast_radius (top 10 anchors)
\`\`\`
<contents of /tmp/lain_phase1_blast_all.txt>
\`\`\`

### A.9 — explore_architecture
\`\`\`
<contents of /tmp/lain_phase1_arch.txt>
\`\`\`

### A.10 — semantic_search (probe queries)
\`\`\`
<contents of /tmp/lain_phase1_semantic.txt>
\`\`\`

## Tool limitations
*(Filled by Task 4.)*

## Deferred / out-of-scope
*(Filled by Task 4.)*

## Out-of-scope findings
*(Filled by Task 4.)*
```

For the Phase 1 section content, write each finding as:

```markdown
### <Category>: <one-line description>
- **Location:** <file:line> or <file:symbol>
- **Severity (provisional):** <Critical|High|Medium|Low>
- **Evidence:** <one-line excerpt from the tool output>
```

Use these categories: Dead code, Untested, Coupling hotspot, Refactor target, Blast radius, Architecture.

Final T-NNN IDs and severity grades are assigned by Task 4. For now, use a "provisional" severity based on the rubric in the spec.

- [ ] **Step 13: Commit**

```bash
cd /home/sebastian/orca/monitor_dm_system && \
  git add docs/superpowers/specs/2026-09-04-full-triage-audit.md && \
  git commit -m "docs(audit): Phase 1 — Lain structural findings + raw tool output"
```

---

## Task 2: Phase 2 — Security pass

**Files:**
- Modify: `docs/superpowers/specs/2026-09-04-full-triage-audit.md` (append `## Phase 2 — Security findings` section and per-pattern appendix)

**Interfaces:**
- Consumes: Audit file from Task 1 (its `## Per-category appendix` lists Phase 1's raw output; this task extends the appendix with Phase 2's grep output and adds the `## Phase 2 — Security findings` section above the appendix).
- Produces: A new `## Phase 2 — Security findings` section listing every grep hit with file:line, category, and one-line description, plus a per-pattern appendix block.

- [ ] **Step 1: Hardcoded secrets**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "api_key\s*=\s*['\"][a-zA-Z0-9_\-]{16,}['\"]" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | grep -v "test_" | grep -v "conftest.py"
```

Expected: either empty (clean) or a list of file:line hits. Save to `/tmp/lain_phase2_secrets.txt`. Skip the false-positive category: docstring examples using `api_key="sk-ant-..."` placeholder (e.g., `packages/agents/src/monitor_agents/wizard/providers.py:112` from the previous sweep).

- [ ] **Step 2: Wildcard CORS**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "allow_origins\s*=\s*\[?\s*['\"]?\*['\"]?" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__
```

Expected: empty (the previous sweep found zero). Save empty output (or hits) to `/tmp/lain_phase2_cors.txt`.

- [ ] **Step 3: JWT/auth bypass**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "verify\s*=\s*False|verify_signature\s*=\s*False|options\s*=\s*\{[^}]*verify" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | head -20
```

Save to `/tmp/lain_phase2_auth.txt`.

- [ ] **Step 4: `eval(` / `exec(`**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "\beval\s*\(|\bexec\s*\(" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | grep -v "test_" | head -20
```

Save to `/tmp/lain_phase2_eval.txt`.

- [ ] **Step 5: `shell=True` with user input**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "shell\s*=\s*True" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | grep -v "test_" | head -20
```

Save to `/tmp/lain_phase2_shell.txt`.

- [ ] **Step 6: Debug endpoints**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "@router\.(get|post|put|delete)\(\s*['\"](/debug|/admin|/test)" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__
```

Save to `/tmp/lain_phase2_debug.txt`.

- [ ] **Step 7: Unvalidated request input**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "request\.(GET|POST|query_params|json)\[" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | head -30
```

Expected: many hits — most are FastAPI request handlers that DO validate via Pydantic models. The audit notes this as a coverage check; specific findings are limited to direct index access without Pydantic validation.

Save to `/tmp/lain_phase2_request.txt`.

- [ ] **Step 8: Path traversal**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "os\.path\.join.*request\.|open\(.*request\.|Path\(.*request\." packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | head -20
```

Save to `/tmp/lain_phase2_path.txt`.

- [ ] **Step 9: Filter and write Phase 2 section**

For each grep output file with hits, manually inspect each hit:
- Skip docstring/comment matches.
- Skip test files (`tests/`, `conftest.py`, `test_*.py`).
- Skip placeholder/parameter names that look like assignments but are actually string literals.

Append to `docs/superpowers/specs/2026-09-04-full-triage-audit.md` immediately after the existing `## Phase 1 — Lain structural findings` section:

```markdown
## Phase 2 — Security findings

*(Per-pattern findings; final T-NNN IDs assigned by Task 4.)*

### Hardcoded secrets
- **Location:** <file:line>
- **Severity (provisional):** <Critical if real; High if suspicious>
- **Evidence:** <grep excerpt>

### Wildcard CORS
*(No findings — see appendix A.2.2.)*

### JWT / auth bypass
- **Location:** <file:line>
- **Severity (provisional):** <Critical>
- **Evidence:** <grep excerpt>

### eval / exec
*(...)*

### shell=True
*(...)*

### Debug endpoints
*(...)*

### Unvalidated request input
*(...)*

### Path traversal
*(...)*

## Per-category appendix (continued)

### A.2.1 — Hardcoded secrets grep
\`\`\`
<contents of /tmp/lain_phase2_secrets.txt>
\`\`\`

### A.2.2 — Wildcard CORS grep
\`\`\`
<contents of /tmp/lain_phase2_cors.txt>
\`\`\`

### A.2.3 — JWT / auth bypass grep
\`\`\`
<contents of /tmp/lain_phase2_auth.txt>
\`\`\`

### A.2.4 — eval / exec grep
\`\`\`
<contents of /tmp/lain_phase2_eval.txt>
\`\`\`

### A.2.5 — shell=True grep
\`\`\`
<contents of /tmp/lain_phase2_shell.txt>
\`\`\`

### A.2.6 — Debug endpoints grep
\`\`\`
<contents of /tmp/lain_phase2_debug.txt>
\`\`\`

### A.2.7 — Unvalidated request input grep
\`\`\`
<contents of /tmp/lain_phase2_request.txt>
\`\`\`

### A.2.8 — Path traversal grep
\`\`\`
<contents of /tmp/lain_phase2_path.txt>
\`\`\`
```

(Replace "No findings — see appendix A.2.2" pattern with the actual hits if any; omit sub-section entirely if grep returned zero hits.)

- [ ] **Step 10: Commit**

```bash
cd /home/sebastian/orca/monitor_dm_system && \
  git add docs/superpowers/specs/2026-09-04-full-triage-audit.md && \
  git commit -m "docs(audit): Phase 2 — Security findings + per-pattern grep output"
```

---

## Task 3: Phase 3 — Correctness pass

**Files:**
- Modify: `docs/superpowers/specs/2026-09-04-full-triage-audit.md` (append `## Phase 3 — Correctness findings` section and per-pattern appendix)

**Interfaces:**
- Consumes: Audit file from Task 2 (its appendix already lists Phase 1 and Phase 2 raw output; this task adds Phase 3's grep output and findings section above the appendix).
- Produces: A new `## Phase 3 — Correctness findings` section listing every grep hit with file:line, category, one-line description, plus a per-pattern appendix block.

- [ ] **Step 1: Bare `except:` clauses**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "^\s*except\s*:" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__
```

Expected: empty (the previous sweep found zero). Save to `/tmp/lain_phase3_bare_except.txt`.

- [ ] **Step 2: Swallowed exceptions**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "except\s+\w+.*:\s*(pass|\.\.\.)\s*$" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__
```

Save to `/tmp/lain_phase3_swallowed.txt`.

- [ ] **Step 3: `print()` in production code**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "^\s*print\s*\(" packages/*/src/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__
```

Expected: 4 hits from the previous sweep — `ingestion/agent.py:45`, `schemas/rpg_ontology/topology.py:26,30`, `temporal_tools/scene_validation.py:33`. Plus any others. Save to `/tmp/lain_phase3_print.txt`.

- [ ] **Step 4: `TODO` / `FIXME` / `XXX` markers**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "TODO|FIXME|XXX" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | head -40
```

Save to `/tmp/lain_phase3_markers.txt`.

- [ ] **Step 5: Unjustified `# type: ignore`**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "# type: ignore" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | wc -l
```

Then dump the file:line list with surrounding context:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "# type: ignore" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__
```

For each hit, check whether the next line above is a justification comment. If not, it's a finding.

Save filtered list to `/tmp/lain_phase3_typeignore.txt`.

- [ ] **Step 6: `assert` in production modules**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "^\s*assert\s+" packages/*/src/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | head -30
```

Save to `/tmp/lain_phase3_assert.txt`.

- [ ] **Step 7: `asyncio.run` inside async contexts**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "asyncio\.run\s*\(" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__
```

Expected: one hit at `packages/ui/backend/src/monitor_ui/routers/ingest.py` (the `_run_ingest_in_thread` from the previous sweep). Save to `/tmp/lain_phase3_asyncio.txt`.

- [ ] **Step 8: `global` keyword**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "^\s*global\s+" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__
```

Save to `/tmp/lain_phase3_global.txt`.

- [ ] **Step 9: Mutable default arguments**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -rEn "def\s+\w+\([^)]*=\s*(\[\]|\{\}|\(\))" packages/ --include="*.py" 2>/dev/null | \
    grep -v __pycache__ | head -20
```

Save to `/tmp/lain_phase3_mutable.txt`.

- [ ] **Step 10: Filter and write Phase 3 section**

For each grep output file with hits, manually inspect each hit:
- Skip docstring/comment matches.
- Skip test files.
- Skip CLI interactive prompts (legitimate `print()` use in `commands/` directory).
- For `print()` in production: the previous sweep flagged 4; check those still exist post-sweep.

Append to `docs/superpowers/specs/2026-09-04-full-triage-audit.md` immediately after the existing `## Phase 2 — Security findings` section:

```markdown
## Phase 3 — Correctness findings

*(Per-pattern findings; final T-NNN IDs assigned by Task 4.)*

### Bare `except:`
*(No findings — see appendix A.3.1.)*

### Swallowed exceptions
- **Location:** <file:line>
- **Severity (provisional):** <Medium>
- **Evidence:** <grep excerpt>

### print() in production code
*(...)*

### TODO / FIXME / XXX markers
*(...)*

### Unjustified # type: ignore
*(...)*

### assert in production modules
*(...)*

### asyncio.run inside async contexts
*(...)*

### global keyword
*(...)*

### Mutable default arguments
*(...)*

## Per-category appendix (continued)

### A.3.1 — Bare except grep
\`\`\`
<contents of /tmp/lain_phase3_bare_except.txt>
\`\`\`

### A.3.2 — Swallowed exceptions grep
\`\`\`
<contents of /tmp/lain_phase3_swallowed.txt>
\`\`\`

### A.3.3 — print() in production grep
\`\`\`
<contents of /tmp/lain_phase3_print.txt>
\`\`\`

### A.3.4 — TODO/FIXME/XXX grep
\`\`\`
<contents of /tmp/lain_phase3_markers.txt>
\`\`\`

### A.3.5 — Unjustified # type: ignore grep
\`\`\`
<contents of /tmp/lain_phase3_typeignore.txt>
\`\`\`

### A.3.6 — assert in production grep
\`\`\`
<contents of /tmp/lain_phase3_assert.txt>
\`\`\`

### A.3.7 — asyncio.run grep
\`\`\`
<contents of /tmp/lain_phase3_asyncio.txt>
\`\`\`

### A.3.8 — global keyword grep
\`\`\`
<contents of /tmp/lain_phase3_global.txt>
\`\`\`

### A.3.9 — Mutable default args grep
\`\`\`
<contents of /tmp/lain_phase3_mutable.txt>
\`\`\`
```

(Adjust "No findings" pattern per actual results.)

- [ ] **Step 11: Commit**

```bash
cd /home/sebastian/orca/monitor_dm_system && \
  git add docs/superpowers/specs/2026-09-04-full-triage-audit.md && \
  git commit -m "docs(audit): Phase 3 — Correctness findings + per-pattern grep output"
```

---

## Task 4: Compile + executive summary + sanity check

**Files:**
- Modify: `docs/superpowers/specs/2026-09-04-full-triage-audit.md` (replace `## Findings` and `## Executive summary` stubs with finalized content; populate `## Tool limitations`, `## Deferred / out-of-scope`, `## Out-of-scope findings`)

**Interfaces:**
- Consumes: Audit file from Tasks 1-3 (Phase 1/2/3 sections + raw output appendices).
- Produces: Final audit with T-NNN IDs, severity grades (Critical / High / Medium / Low), executive summary, tool limitations, deferred items, out-of-scope items.

- [ ] **Step 1: Read the audit file's Phase 1, 2, 3 sections**

Read `docs/superpowers/specs/2026-09-04-full-triage-audit.md` and extract every finding's location, provisional category, provisional severity, and one-line description.

- [ ] **Step 2: Deduplicate findings**

Same location + same root cause → one T-NNN. Example: if `find_dead_code` and a Phase 2 grep both flag the same line, collapse to one finding with the higher severity.

Build a deduplicated list with these fields per finding:
- `temp_id`: P<n>.<m> (Phase N, finding m within that phase)
- `location`: file:line or file:symbol
- `category`: from {Dead code, Untested, Coupling hotspot, Refactor target, Blast radius, Architecture, Security, Correctness, Style, Doc gap}
- `description`: one line
- `provisional_severity`: from {Critical, High, Medium, Low}
- `evidence`: short excerpt
- `dedup_winner`: which finding absorbed the others (if any)

- [ ] **Step 3: Assign T-NNN IDs and final severity**

Sort by severity (Critical first), then category, then file. Assign T-001, T-002, ... in that order.

Apply severity rubric (per spec §"Severity rubric"):
- **Critical:** security hole, data loss risk, correctness bug.
- **High:** significant blast radius, untested critical path, obvious dead code in hot path.
- **Medium:** refactor target, untested helper, coupling smell.
- **Low:** style nit, minor doc gap, cosmetic.

Adjust provisional severities that don't match the rubric. Document any downgrades (e.g., "provisional High → final Medium: pattern was theoretical, no real exploit path").

- [ ] **Step 4: Check for size explosion**

If the deduplicated finding count > 150, split Medium and Low into a `## Lower-priority findings (appendix)` section. Keep the top 50 by severity in the main `## Findings` section. Document the split under "Tool limitations" or "Deferred / out-of-scope".

- [ ] **Step 5: Write the `## Findings` section**

Replace the stub in the audit file with the finalized list:

```markdown
## Findings

Total: <N> findings — <C> Critical, <H> High, <M> Medium, <L> Low.

### T-001 — <description>
- **Severity:** Critical
- **Category:** Security
- **Location:** <file:line>
- **Evidence:** <excerpt>
- **Recommended action:** *(informational — not committed to)*

### T-002 — <description>
*(...)*

### T-003 — <description>
*(...)*
```

- [ ] **Step 6: Write the `## Executive summary` section**

Replace the stub with:

```markdown
## Executive summary

**Total findings:** <N> — <C> Critical, <H> High, <M> Medium, <L> Low.

### Top issues warranting attention first

1. **T-NNN — <description>** (Critical) — <one-line why it matters>
2. **T-NNN — <description>** (Critical/High) — <...>
3. **T-NNN — <description>** (High) — <...>
4. ...
5. ...

### Systemic patterns

- <e.g., "10 files have similar auth bypass patterns — consider a project-wide check">
- <e.g., "Coverage drops sharply in the `loops/` directory — likely due to test design, not missing tests">
- <e.g., "Refactor targets cluster in the data-layer — consistent with recent coverage-and-shape refactor (commit 38e684b)">
```

Keep the executive summary under 30 lines.

- [ ] **Step 7: Fill in `## Tool limitations`**

Based on what didn't work during Phases 1-3:

```markdown
## Tool limitations

- **Lain's TS support:** Weak. Frontend `.tsx` files mostly failed call-graph extraction; the 14 indexing-gap files flagged in the 2026-09-03 sweep remain in that state.
- **Lain underscore-prefixed symbols:** Not indexed. `get_blast_radius` on `_commit_fact` etc. returns "Node not found" — private methods are excluded from the public symbol index.
- **`oneshot` NLP model:** Each `oneshot` invocation boots a transient Lain server without loading the embedding model. Only the persistent Lain server (started by Claude Code) has the model loaded.
- **Integration tests:** `tests/` requires external services (Mongo/Neo4j/Qdrant); not running in this environment. The audit's correctness pass did not run the integration suite.
- **(any other limitations discovered during phases)**
```

- [ ] **Step 8: Fill in `## Deferred / out-of-scope`**

List items noticed but explicitly not investigated:

```markdown
## Deferred / out-of-scope

- **Frontend coverage:** The UI frontend (`packages/ui/frontend/`) is mostly outside Lain's reach. Not investigated.
- **Documentation drift:** Stale claims in `docs/` were not cross-checked against current code.
- **(any specific items deferred during phases — e.g., the residual `_ingest_with_capture` RuntimeWarning, which the 2026-09-03 sweep's final review flagged as a separate bug)**
```

- [ ] **Step 9: Fill in `## Out-of-scope findings`**

List feature-gap items that surfaced but aren't bugs:

```markdown
## Out-of-scope findings

*(Items noticed that are feature decisions rather than bugs — noted but not graded.)*

- **No rate limiting on /api/login:** surfaced during Phase 2 grep; feature decision, not a bug.
- **(any others)**
```

- [ ] **Step 10: Run the four-package test suite as a sanity check**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/data-layer -q --tb=line 2>&1 | tail -3 && \
  uv run pytest packages/agents -q --tb=line 2>&1 | tail -3 && \
  uv run pytest packages/cli -q --tb=line 2>&1 | tail -3 && \
  uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: same as the 2026-09-03 sweep baseline (4837 passed, 22 skipped across the four suites). The audit is read-only so nothing should have changed, but the check costs ~10 min and confirms it.

If a test count has changed, **stop and investigate** — something in Phases 1-3 may have had an unintended side effect (e.g., a test file inadvertently modified). This is the audit's only safety net.

- [ ] **Step 11: Commit**

```bash
cd /home/sebastian/orca/monitor_dm_system && \
  git add docs/superpowers/specs/2026-09-04-full-triage-audit.md && \
  git commit -m "docs(audit): finalize — T-NNN IDs, severity grades, exec summary, sanity check"
```

---

## Verification matrix (after all 4 tasks)

Run from `/home/sebastian/orca/monitor_dm_system`:

```bash
# 1. Audit file exists and is well-formed.
wc -l docs/superpowers/specs/2026-09-04-full-triage-audit.md  # expect >500 lines (rich audit)
head -50 docs/superpowers/specs/2026-09-04-full-triage-audit.md  # check header + exec summary

# 2. Each T-NNN ID is unique.
grep -oE "T-[0-9]{3}" docs/superpowers/specs/2026-09-04-full-triage-audit.md | sort | uniq -d  # expect empty

# 3. Severity grades follow the rubric.
grep -E "^- \*\*Severity:\*\*" docs/superpowers/specs/2026-09-04-full-triage-audit.md | sort | uniq -c

# 4. Phase 1/2/3 sections + appendix all present.
grep -E "^## (Phase|Findings|Executive summary|Tool limitations|Deferred|Out-of-scope|Per-category)" \
  docs/superpowers/specs/2026-09-04-full-triage-audit.md

# 5. Four commits on master, working tree clean.
git log --oneline -4  # expect 4 new commits on top of 032e466
git status --short     # expect empty

# 6. Tests still pass (re-run if not done in Task 4).
uv run pytest packages/data-layer packages/agents packages/cli packages/ui/backend -q 2>&1 | tail -3
```

If any check fails, do not declare the audit complete — investigate the failing task before proceeding.
