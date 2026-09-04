# Lain Sweep Fixes (Design)

Date: 2026-09-03
Status: Awaiting user approval of written spec
Approach: 4 work items — 1 deletion, 1 commit, 1 bug fix, 1 mechanical rename

## Problem

A Lain-driven exploratory sweep of `/home/sebastian/orca/monitor_dm_system` surfaced four discrete issues across the three-layer monorepo:

1. **`packages/agents/src/monitor_agents/tools/lain_integration.py` is fully orphan.** 176 lines wrapping Lain MCP tools (`search_code`, `analyze_impact`, `trace_symbol`, `get_function_chain`, `detect_dead_code`, `explore_arch`, `run_project_build`, `run_project_tests`) plus a `get_lain_client()` singleton, `lain_session()` async context manager, and a `LainTools` constants class. Lain's `find_dead_code` flagged all eight wrappers as having no callers. Grep across `packages/` and `tests/` confirmed zero imports outside the module's own docstring example. The underlying `monitor_data.tools.lain_tools.LainClient` is what should be used directly if anyone needs Lain from an agent — and currently no agent does.

2. **Two uncommitted files document the new MCP setup but don't ship it.** `AGENTS.md` (50 lines) updates the Lain MCP section to match the new `.claude/settings.json` format (stdio, no proxy script, `lain mcp` invocation, explicit `--embedding-model` directory). `.claude/settings.json` itself was rewritten to point to the actual install paths and the directory form of `--embedding-model` (Lain expects a directory containing `model.onnx` + `tokenizer.json`, not a file path). Both changes belong together.

3. **`packages/ui/backend/src/monitor_ui/routers/ingest.py` discards the Future returned by `loop.run_in_executor`.** Two call sites (around lines 782 and 1065) schedule `_run_ingest_in_thread` via the FastAPI event loop's executor and immediately drop the returned Future. The pipeline still runs because the lambda internally calls `asyncio.run(_run())` on a dedicated thread, but: no cancellation hook, no error tracking, and this pattern is the source of the "coroutine never awaited" RuntimeWarning observed during the ui-backend test run. The fix is to register the Future so the existing cancel endpoint (or a shutdown handler) can see and act on it.

4. **FastAPI deprecation warnings in `packages/ui/backend/src/monitor_ui/routers/performance.py`.** Two `Query(...)` declarations use `regex="..."`, which Pydantic v2 deprecated in favor of `pattern="..."`. Mechanical rename; same validation semantics.

## Goal

Land four small, low-risk fixes that improve observability, remove dead code, and silence deprecation warnings — without changing any public API or test behavior.

Non-goals:
- No API changes (no new endpoints, no breaking signatures).
- No new dependencies.
- No rewrite of the ingest pipeline threading model — the executor + dedicated-thread-with-its-own-loop design is intentional (it keeps a long-running sync+async ingest from blocking uvicorn). The fix is *additive tracking*, not a redesign.
- No investigation of the 14 Lain indexing-gap files (deferred — mostly frontend `.tsx` outside Lain's strong languages, plus `watchdog.py` and `progression_loop.py` which warrant their own pass).
- No migration of the 4 legitimate-but-violating `print()` calls in production code (deferred — separate concern from this sweep).

## Architecture

- All changes are local. No new layers, no new modules.
- The Future registry is a module-level `dict[str, Future]` in `ingest.py`, drained on completion via a done-callback. The existing `_JOB_TIMEOUT_SECS` + `asyncio.wait_for` inside `_run()` is unchanged.
- The Lain integration deletion removes `tools/lain_integration.py` only. `monitor_data.tools.lain_tools.LainClient` is untouched; any future agent that wants Lain should import `LainClient` directly from the data-layer (the correct direction per AGENTS.md's "agents → data-layer only" rule).

## Existing infrastructure to reuse (do not duplicate)

| Capability | File / line | Notes |
|---|---|---|
| `monitor_data.tools.lain_tools.LainClient` | `packages/data-layer/src/monitor_data/tools/lain_tools.py` | The actual client. Untouched by this change; available for any future agent that wants Lain. |
| `_JOB_TIMEOUT_SECS`, `_ingest_lock`, `_ingest_pending_requests`, `_ingest_active_requests` | `packages/ui/backend/src/monitor_ui/routers/ingest.py` (top of file) | Existing state holders; the new `_ingest_futures` registry sits alongside these. |
| FastAPI shutdown handler pattern | `packages/ui/backend/src/monitor_ui/main.py` or similar | Where the future-cancellation pass goes, if the cancel endpoint doesn't exist yet. |

## Work items

### W1 — Remove orphan `lain_integration.py`

Delete `packages/agents/src/monitor_agents/tools/lain_integration.py`. No callers; no documentation reference outside the file itself; no tests reference it.

Verify post-delete:
- `grep -rn "lain_integration" packages/ tests/` returns nothing.
- `uv run pytest packages/agents -q` still green (1889 passed today, must remain green).

### W2 — Commit uncommitted docs + config

One commit: `chore: align AGENTS.md MCP docs with new .claude/settings.json`.

Files touched:
- `AGENTS.md` (already modified in working tree, ~50 lines)
- `.claude/settings.json` (already modified in working tree, 1 substantive line: `--embedding-model` path now points to the directory)

No content change to either file beyond what's already in the working tree. The commit message should reference both files and the reason: the docs update was started before the config fix landed; both are correct now and need to ship together.

### W3 — Track `_run_ingest_in_thread` Futures in `ingest.py`

Change pattern at both call sites (lines ~782 and ~1065):

**Before:**
```python
loop.run_in_executor(
    executor,
    lambda: _run_ingest_in_thread(...)
)
```

**After:**
```python
fut = loop.run_in_executor(
    executor,
    lambda: _run_ingest_in_thread(...)
)
fut.add_done_callback(lambda f: _ingest_futures.pop(queue_token, None))
_ingest_futures[queue_token] = fut
```

Plus module-level near the existing `_ingest_pending_requests` / `_ingest_active_requests` state holders:

```python
_ingest_futures: dict[str, concurrent.futures.Future] = {}
```

A FastAPI shutdown handler **is** required because the FastAPI app's lifespan is what bounds the executor. Register it at module import time using the standard `@asynccontextmanager` lifespan pattern if one exists in this app, otherwise via `app.on_event("shutdown")` — and only if not already registered elsewhere. The handler iterates `_ingest_futures` and calls `.cancel()` on each Future. Cancellation is best-effort: if a thread is already mid-`asyncio.run(_run())`, the Future's underlying thread cannot be interrupted from outside (Python limitation), but `.cancel()` is a no-op for already-running work and succeeds for not-yet-started work — both safe outcomes.

Error handling: `_run_ingest_in_thread`'s internal `try/except TimeoutError` and `try/except Exception` stay; the lambda still calls `asyncio.run(_run())` and the existing logging paths are unchanged. The Future being tracked is a `concurrent.futures.Future`, not a coroutine — `fut.exception()` returns the inner exception if any, but we don't await it inline (fire-and-forget by design). The done-callback above pops the entry on completion so the registry stays bounded.

Verification:
- `uv run pytest packages/ui/backend -q` still green (793 passed today).
- The "coroutine never awaited" RuntimeWarning from `test_list_providers_seed_full` no longer appears in test output.
- Manual smoke: boot the FastAPI server (`uv run monitor-ui-backend`), POST to the ingest endpoint, immediately send SIGTERM, confirm the process exits within 5s (proves the shutdown handler runs and completes).

### W4 — Migrate `regex=` → `pattern=` in `performance.py`

Two lines:
- `packages/ui/backend/src/monitor_ui/routers/performance.py:137` — `regex="^(count|avg_time|max_time|slow_count)$"`
- `packages/ui/backend/src/monitor_ui/routers/performance.py:410` — `regex="^(info|warning|error|critical)$"`

Mechanical: rename the kwarg to `pattern`. Pydantic v2 deprecated `regex` and accepts `pattern` as the replacement with identical semantics.

Verification:
- `uv run pytest packages/ui/backend -q` still green (793 passed today).
- No more `FastAPIDeprecationWarning` from `performance.py` in test output.

## Testing strategy

No new tests. All changes are either:
- Deletions of code with no callers (W1)
- Documentation/config changes with no runtime impact (W2)
- Additive observability for existing behavior (W3)
- Mechanical renames with identical semantics (W4)

The existing 4837 unit tests across `data-layer`, `agents`, `cli`, and `ui-backend` must all remain green. Integration tests under `tests/` are not part of this sweep (they require external services).

## Rollout

Single PR. No migrations, no feature flags, no staged rollout — each item is independently small enough to revert in isolation if needed.

## Risks

- **W3** is the only behavior-changing item. The risk is that adding Future tracking changes shutdown behavior in a way the existing tests don't cover. Mitigation: keep the existing `asyncio.run(_run())` model unchanged, only register the Future; if the cancel path is added, scope it to the existing cancel endpoint or a guarded shutdown handler.
- All other items are zero-runtime-risk.
