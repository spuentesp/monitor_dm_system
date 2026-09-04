# Lain Sweep Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land four low-risk fixes from the Lain-driven sweep — remove orphan dead code, commit uncommitted docs/config, fix the discarded-Future bug in the ingest router, migrate a FastAPI deprecation.

**Architecture:** Local changes only. One file deleted, one doc-and-config pair committed, two ui-backend routers modified. No new modules, no API changes, no new dependencies, no new tests. Existing test suites are the verification gate — 4837 unit tests across `data-layer`, `agents`, `cli`, and `ui/backend` must remain green.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, `concurrent.futures`, `structlog` (already in the project). Existing project tooling: `uv`, `ruff`, `mypy`, `pytest`.

## Global Constraints

- Three-layer dependency rule: CLI (3) → agents (2) → data-layer (1), never import upward. This plan removes one file from layer 2 and modifies layer 1-adjacent ui-backend code; no new cross-layer imports.
- Line-length 100, Python 3.11, mypy strict (`uv run mypy packages/*/src --cache-dir /tmp/mypy-cache`).
- Lint/format before commit: `uv run ruff check packages/ui/backend` + `uv run ruff format packages/ui/backend`.
- Test commands used in this plan:
  - Agents: `uv run pytest packages/agents -q` (baseline: 1889 passed, 2 skipped)
  - UI backend: `uv run pytest packages/ui/backend -q` (baseline: 793 passed, 2 skipped)
- No new tests are written — the spec explicitly says existing tests must stay green.
- Only CanonKeeper writes to Neo4j — this plan touches no Neo4j writes.
- Per-task commit steps are kept; the executing skill's review gates handle confirmation.

---

## File Structure

**Deleted:**
- `packages/agents/src/monitor_agents/tools/lain_integration.py` — 176 lines, zero callers.

**Modified (content already in working tree, just needs commit):**
- `AGENTS.md` — Lain MCP docs aligned with new config.
- `.claude/settings.json` — `lain mcp` invocation paths made accurate.

**Modified (code changes):**
- `packages/ui/backend/src/monitor_ui/routers/ingest.py` — add `_ingest_futures` registry, modify 2 call sites, add shutdown handler.
- `packages/ui/backend/src/monitor_ui/routers/performance.py` — rename `regex=` to `pattern=` on 2 lines.

**No new files.** No new tests. No new dependencies.

---

## Task 1: Remove orphan `lain_integration.py`

**Files:**
- Delete: `packages/agents/src/monitor_agents/tools/lain_integration.py`

**Interfaces:**
- Consumes: nothing (deletion only).
- Produces: a smaller `packages/agents/src/monitor_agents/tools/` directory. No symbol disappears that any other code references — verified by grep.

- [ ] **Step 1: Verify zero callers in `packages/` and `tests/`**

Run:
```bash
grep -rn "lain_integration\|from monitor_agents\.tools import lain_integration\|tools\.lain_integration" \
  /home/sebastian/orca/monitor_dm_system/packages /home/sebastian/orca/monitor_dm_system/tests \
  2>&1 | grep -v __pycache__
```

Expected: only one match — the docstring at `packages/agents/src/monitor_agents/tools/lain_integration.py:12` (the file documenting itself).

- [ ] **Step 2: Delete the file**

Run:
```bash
rm /home/sebastian/orca/monitor_dm_system/packages/agents/src/monitor_agents/tools/lain_integration.py
```

- [ ] **Step 3: Run agents test suite to verify still green**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/agents -q --tb=short 2>&1 | tail -5
```

Expected: `1889 passed, 2 skipped` (same baseline as before deletion). Any failure is a missed caller — investigate and add back what was needed (very unlikely given Step 1's grep).

- [ ] **Step 4: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  git add -u packages/agents/src/monitor_agents/tools/lain_integration.py && \
  git commit -m "chore(agents): remove orphan tools/lain_integration.py

176 lines wrapping Lain MCP tools (search_code, analyze_impact, etc.)
plus a singleton and async context manager. Zero callers across
packages/ and tests/ — Lain's find_dead_code and a manual grep both
confirm. monitor_data.tools.lain_tools.LainClient remains available
for any future agent that wants Lain."
```

---

## Task 2: Commit uncommitted AGENTS.md + .claude/settings.json

**Files:**
- Modify: `AGENTS.md` (already in working tree, ~50 lines)
- Modify: `.claude/settings.json` (already in working tree, 1 substantive line)

**Interfaces:**
- Consumes: the working-tree state of both files (do not edit — already correct).
- Produces: a single commit landing both files together so docs match config.

- [ ] **Step 1: Verify both files are modified in working tree**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && git status --short AGENTS.md .claude/settings.json
```

Expected output (one line each, both with ` M` prefix):
```
 M .claude/settings.json
 M AGENTS.md
```

If either shows `??` (untracked), the file was never modified — abort and ask the user; do not invent a change.

- [ ] **Step 2: Show the substantive diff for review**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  git diff AGENTS.md .claude/settings.json | head -80
```

Expected: shows the Lain MCP section update in `AGENTS.md` (paths, stdio mode, `lain mcp` invocation) and the `--embedding-model` arg change in `.claude/settings.json` (file path → directory path).

- [ ] **Step 3: Stage both files**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  git add AGENTS.md .claude/settings.json
```

- [ ] **Step 4: Commit with the agreed message**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  git commit -m "chore: align AGENTS.md MCP docs with new .claude/settings.json

- AGENTS.md: Lain MCP section rewritten for the stdio 'lain mcp'
  invocation, removing the legacy scripts/lain-mcp-proxy.sh pattern
  (Lain 0.6+ dropped combined stdio+http mode).
- .claude/settings.json: paths rewritten for this machine's install;
  --embedding-model now points to the .lain/models directory
  (Lain expects a directory containing model.onnx + tokenizer.json,
  not a single file)."
```

---

## Task 3: Track `_run_ingest_in_thread` Futures in `ingest.py`

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/ingest.py`

**Interfaces:**
- Consumes: existing `_run_ingest_in_thread(...)` sync function (already calls `asyncio.run(_run())` internally), existing `_ingest_lock`, `_ingest_pending_requests`, `_ingest_active_requests`, `_JOB_TIMEOUT_SECS` module-level state. Existing FastAPI app instance (likely imported or referenced via `app`).
- Produces: a new module-level `_ingest_futures: dict[str, concurrent.futures.Future] = {}` keyed by `queue_token`. Two modified call sites register the Future. A new shutdown handler iterates the dict and calls `.cancel()` on each Future.

- [ ] **Step 1: Confirm ui-backend test suite is green as a baseline**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/ui/backend -q --tb=short 2>&1 | tail -5
```

Expected: `793 passed, 2 skipped`. If different, abort and investigate.

- [ ] **Step 2: Read the surrounding state-holder region and the two call sites**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -n "_ingest_pending_requests\|_ingest_active_requests\|_run_ingest_in_thread\|loop\.run_in_executor" \
  packages/ui/backend/src/monitor_ui/routers/ingest.py
```

Expected output (line numbers will be in this vicinity — adjust subsequent steps to your actual file):
```
   N: _ingest_pending_requests: dict[str, ...] = {}
   N: _ingest_active_requests: dict[str, ...] = {}
 267: def _run_ingest_in_thread(
  ~782: loop.run_in_executor(executor, lambda: _run_ingest_in_thread(...))
  ~785: except Exception as exc:
  ...
 1065: loop.run_in_executor(executor, lambda: _run_ingest_in_thread(...))
```

Record the exact line numbers you find — they drive Steps 4–6.

- [ ] **Step 3: Add the `_ingest_futures` registry next to the other state holders**

Find the line where `_ingest_pending_requests` or `_ingest_active_requests` is declared (whichever comes first). Immediately after that block, add:

```python
_ingest_futures: dict[str, concurrent.futures.Future] = {}
```

The `concurrent` module needs to be imported — check the top of `ingest.py`. If `import concurrent.futures` is already there, do nothing. Otherwise add the import alphabetically with the other stdlib imports at the top of the file.

- [ ] **Step 4: Modify the first `run_in_executor` call site (around line 782)**

Find the block:
```python
loop.run_in_executor(
    executor,
    lambda: _run_ingest_in_thread(
        queue_token=queue_token,  # type: ignore
        file_bytes=file_bytes,
        ...
    ),
)
```

Replace it with:
```python
fut = loop.run_in_executor(
    executor,
    lambda: _run_ingest_in_thread(
        queue_token=queue_token,  # type: ignore
        file_bytes=file_bytes,
        ...
    ),
)
fut.add_done_callback(lambda f: _ingest_futures.pop(queue_token, None))
_ingest_futures[queue_token] = fut
```

Preserve every existing kwarg verbatim — only the assignment and the trailing two lines are added.

- [ ] **Step 5: Modify the second `run_in_executor` call site (around line 1065)**

Same transformation as Step 4. The block looks like:
```python
loop.run_in_executor(
    executor,
    lambda: _run_ingest_in_thread(
        queue_token=queue_token,
        file_bytes=file_bytes,
        filename=filename,
        ...
        reuse_doc_id=doc.doc_id,
    ),
)
```

Replace with:
```python
fut = loop.run_in_executor(
    executor,
    lambda: _run_ingest_in_thread(
        queue_token=queue_token,
        file_bytes=file_bytes,
        filename=filename,
        ...
        reuse_doc_id=doc.doc_id,
    ),
)
fut.add_done_callback(lambda f: _ingest_futures.pop(queue_token, None))
_ingest_futures[queue_token] = fut
```

- [ ] **Step 6: Add the shutdown handler**

First check whether a shutdown handler already exists for ingest state elsewhere in this file:

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  grep -n "on_event\|shutdown\|lifespan" packages/ui/backend/src/monitor_ui/routers/ingest.py \
  packages/ui/backend/src/monitor_ui/main.py 2>&1 | head -20
```

If a shutdown handler already iterates over `_ingest_pending_requests` / `_ingest_active_requests`, extend it to also iterate `_ingest_futures`:

```python
for fut in _ingest_futures.values():
    fut.cancel()
_ingest_futures.clear()
```

If no shutdown handler exists, register one at the bottom of `ingest.py`:

```python
try:
    from monitor_ui.main import app  # type: ignore

    @app.on_event("shutdown")
    def _cancel_ingest_futures_on_shutdown() -> None:
        for fut in _ingest_futures.values():
            fut.cancel()
        _ingest_futures.clear()
except ImportError:
    pass  # module imported standalone (e.g., from tests); no app to register on
```

The `try/except ImportError` makes the module importable from tests (where there's no `app`).

- [ ] **Step 7: Run ui-backend tests to verify still green**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/ui/backend -q --tb=short 2>&1 | tail -10
```

Expected: `793 passed, 2 skipped` — same as baseline. Any new failure means the lambda's queue-token capture is wrong (most common mistake: forgetting the `lambda f:` wrapper that delays lookup until the future actually completes).

- [ ] **Step 8: Confirm the RuntimeWarning is gone**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/ui/backend/tests/test_llm_mgmt.py::test_list_providers_seed_full -v 2>&1 | \
  grep -E "RuntimeWarning|never awaited|passed|failed" | head -10
```

Expected: no "never awaited" RuntimeWarning. Test still passes. (The warning was incidental to this test, not from this test's code; it surfaces because the request lifecycle exercised the ingest router at some point. With the Future now stored, the warning shouldn't trigger.)

- [ ] **Step 9: Smoke-test the shutdown path manually**

Boot the server in a separate terminal and confirm clean exit:

Run in terminal A:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run monitor-ui-backend  # or: uv run python -m monitor_ui
```

In terminal B, kick off any request that touches the ingest router (or just `curl http://localhost:8000/api/health` to confirm it's up), then in terminal A send `Ctrl-C` or `kill -TERM <pid>`.

Expected: the server exits within 5 seconds. If it hangs, the shutdown handler didn't register — re-check Step 6.

- [ ] **Step 10: Lint + format + commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run ruff check packages/ui/backend/src/monitor_ui/routers/ingest.py && \
  uv run ruff format packages/ui/backend/src/monitor_ui/routers/ingest.py && \
  git add packages/ui/backend/src/monitor_ui/routers/ingest.py && \
  git commit -m "fix(ui-backend): track _run_ingest_in_thread Futures

loop.run_in_executor() was called at two sites and the returned Future
was discarded — the pipeline still ran (asyncio.run inside the lambda)
but there was no cancellation hook, no error tracking, and the discarded
Future was the source of the 'coroutine never awaited' RuntimeWarning
observed during ui-backend tests.

Register each Future in a module-level dict keyed by queue_token,
drain on completion via a done-callback, and cancel all in-flight
ingests on FastAPI shutdown. The thread-executor + asyncio.run model
is preserved — only observability is added."
```

---

## Task 4: Migrate `regex=` → `pattern=` in `performance.py`

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/performance.py` (lines 137 and 410)

**Interfaces:**
- Consumes: FastAPI's `Query(...)` validator. Pydantic v2 renamed `regex` → `pattern`; same regex syntax, same validation.
- Produces: same API surface, same validation behavior, no deprecation warning.

- [ ] **Step 1: Confirm baseline tests pass AND capture the deprecation warning**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/ui/backend/tests/test_performance.py -v 2>&1 | \
  grep -E "FastAPIDeprecationWarning|passed|failed" | head -10
```

If `tests/test_performance.py` doesn't exist, run the broader ui-backend tests and filter:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/ui/backend -q 2>&1 | grep -E "FastAPIDeprecationWarning.*performance|passed" | head -5
```

Expected: tests pass and at least one `FastAPIDeprecationWarning: ... regex ... has been deprecated, please use pattern instead` line is visible (originating from `performance.py`).

- [ ] **Step 2: Edit line 137**

Open `packages/ui/backend/src/monitor_ui/routers/performance.py`, find the line containing `regex="^(count|avg_time|max_time|slow_count)$"` (it's a `Query(...)` argument inside a route signature). Change `regex=` to `pattern=`. Nothing else on that line changes.

- [ ] **Step 3: Edit line 410**

Same file. Find `regex="^(info|warning|error|critical)$"` and change `regex=` to `pattern=`. Nothing else changes.

- [ ] **Step 4: Confirm tests still pass and the deprecation warning is gone**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/ui/backend -q --tb=short 2>&1 | tail -5
```

Then check for the warning:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run pytest packages/ui/backend -q 2>&1 | grep -c "performance.py.*regex"
```

Expected: `793 passed, 2 skipped` (same baseline) and the warning grep returns `0`.

- [ ] **Step 5: Lint + format + commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system && \
  uv run ruff check packages/ui/backend/src/monitor_ui/routers/performance.py && \
  uv run ruff format packages/ui/backend/src/monitor_ui/routers/performance.py && \
  git add packages/ui/backend/src/monitor_ui/routers/performance.py && \
  git commit -m "fix(ui-backend): migrate regex= to pattern= in performance.py

FastAPI's Query validator deprecated regex= in favor of pattern=
(Pydantic v2). Two call sites affected — sort_by and severity
parameters. Identical validation semantics; no API change."
```

---

## Verification matrix (after all 4 tasks)

Run from `/home/sebastian/orca/monitor_dm_system`:

```bash
# 1. The four targeted suites must match baseline counts.
uv run pytest packages/data-layer -q   # expect 2110 passed, 14 skipped
uv run pytest packages/agents -q       # expect 1889 passed, 2 skipped
uv run pytest packages/cli -q          # expect 45 passed
uv run pytest packages/ui/backend -q   # expect 793 passed, 2 skipped

# 2. Lint + format clean.
uv run ruff check packages

# 3. No layer-violations introduced.
python scripts/check_layer_dependencies.py

# 4. The orphan is truly gone, and no Future was missed.
grep -rn "_run_ingest_in_thread" packages/ui/backend/src/monitor_ui/routers/ingest.py | grep -c run_in_executor  # expect 2
grep -c "lain_integration" packages/agents/src/monitor_agents/tools/__init__.py 2>/dev/null  # expect 0 or file absent
```

If any check fails, do not merge — investigate the failing task before moving on.
