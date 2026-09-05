# T-013 — Bare `# type: ignore` Cleanup (Design)

Date: 2026-09-05
Status: Awaiting user approval of written spec
Approach: Per-file subagent dispatches + per-task review

## Problem

The 2026-09-04 full-repo audit (T-013) flagged 549 `# type: ignore` comments in `packages/`. 253 of them are bare (no specific mypy code, no justification comment) — they suppress type checking without explaining why. The volume signals real type-coverage gaps, especially in ui-backend routers (where 197 of the 549 are concentrated) and DSPy signatures.

A bare ignore is worse than one with a code: it tells the reader "something is wrong here, ignore it" without explaining the wrong thing. Future maintainers can't tell whether the ignore is still needed or whether the type system has improved enough to remove it.

## Goal

Process the **253 bare `# type: ignore` comments** in `packages/` and `scripts/`. For each, add a one-line `# reason: <text>` comment immediately above the ignore. Where the ignore can be narrowed to a specific mypy code (`[attr-defined]`, `[assignment]`, etc.), narrow it. Where the reason is unclear, log the line for human review rather than guessing.

Non-goals:
- No new mypy strict mode.
- No fixing of the underlying type issues that the ignores bypass — that's a separate effort.
- No touching of the 296 with-codes ignores — separate sweep.
- No automation / pre-commit hook to enforce future bare-ignore discipline.

## Architecture

**Distribution of the 253 bare ignores across files** (from grep `rEn "# type: ignore\s*$"`):

| File | Bare count |
|---|---:|
| `packages/ui/backend/src/monitor_ui/routers/pack_library.py` | 54 |
| `packages/ui/backend/src/monitor_ui/routers/entities.py` | 32 |
| `packages/ui/backend/src/monitor_ui/routers/ingest.py` | 26 |
| `packages/ui/backend/src/monitor_ui/routers/graph.py` | 19 |
| `packages/ui/backend/src/monitor_ui/routers/universes.py` | 17 |
| `packages/ui/backend/src/monitor_ui/routers/chat.py` | 15 |
| `packages/ui/backend/src/monitor_ui/routers/performance.py` | 13 |
| `packages/ui/backend/src/monitor_ui/routers/forge.py` | 11 |
| Other ui-backend files (watchdog, main, jobs_health, databases, character_storage, game_systems, ingest_shared) | ~36 |
| Other (data-layer, agents, scripts, etc.) | ~30 |
| **Total** | **~253** |

**Execution shape:** 9 subagent dispatches. Tasks 1-8 each cover one of the 8 top-concentration files (covering 197 of the 253 ignores). Task 9 covers the long tail (~56 ignores scattered across smaller files).

Each subagent:
1. Reads the file's bare ignores in context.
2. Classifies each into one of the 6 buckets (see "Reason taxonomy" below).
3. Inserts `# reason: <bucket-specific text or bespoke one-liner>` on the line above each bare ignore.
4. Where the ignore can be narrowed to a specific mypy code, narrows it.
5. Self-reviews before reporting.
6. Commits with `chore(types): add reason comments to bare # type: ignore in <file>`.

Per-task reviewer: opens the diff, spot-checks 5-10 reason comments for correctness, confirms bucket assignments are plausible, runs mypy + ruff + per-package tests.

## Reason taxonomy

The 253 bare ignores cluster into 6 buckets. Each bucket has a fixed reason text — consistent within bucket, but the subagent must look at the actual line to confirm the bucket fits before applying.

| Bucket | Why | Reason text |
|---|---|---|
| **DSPy signature** | `# type: ignore` on `dspy.Signature` subclasses or DSPy module forward overrides | `# reason: DSPy signature — dspy.Signature subclasses use dynamic field typing mypy can't model` |
| **FastAPI Pydantic-Any** | `# type: ignore` on Pydantic model attributes accessed via `request.<thing>`, or anywhere the type comes back as `Any` from Pydantic v2 | `# reason: FastAPI/Pydantic v2 returns Any for dynamic model attributes; mypy can't narrow without explicit Annotated[]` |
| **Third-party type stub gap** | `# type: ignore` on imports or attribute access from libraries lacking type stubs (`instructor`, `litellm`, etc.) | `# reason: <library> lacks type stubs; suppress until upstream adds py.typed` (where `<library>` is named) |
| **Dynamic dispatch** | `# type: ignore` on `getattr`, `setattr`, `importlib.import_module`, or similar | `# reason: dynamic dispatch — type can't be inferred at static-analysis time` |
| **Test fixture / monkey-patch** | `# type: ignore` on `cls.x = y` assignments in test conftest, or attribute overrides on mock objects | `# reason: test fixture monkey-patch — type intentionally narrowed for the test scope` |
| **Genuine typing gap** | Doesn't fit any bucket above | `# reason: <bespoke one-liner specific to the line>` |

Subagent instruction: classify each bare ignore into one of these 6 buckets. If the 6th bucket applies, write a bespoke one-liner. If the subagent is unsure, log the line for human review rather than guessing.

Each subagent reports its bucket distribution so the audit trail shows how the 253 breaks down across buckets.

## Format

Before:
```python
def some_function() -> dict[str, Any]:
    result = client.fetch(...)
    return result  # type: ignore
```

After:
```python
def some_function() -> dict[str, Any]:
    result = client.fetch(...)
    # reason: <bucket-specific text or bespoke one-liner>
    return result  # type: ignore
```

When the bucket fits a specific mypy code:
```python
    # reason: FastAPI/Pydantic v2 returns Any for dynamic model attributes
    return result  # type: ignore[return-value]
```

When the bucket is unclear (6th) — leave the bare ignore, but flag the line in the subagent's report for human review.

## Validation gates (per-task reviewer)

1. **`ruff check` on each modified file** — must pass; comment-only change, no semantic change.
2. **`ruff format`** — must be no-op on the comment placement; if format changes anything, subagent re-runs and re-commits.
3. **`uv run mypy packages/<pkg> --cache-dir /tmp/mypy-cache`** — run on each affected package after edits. mypy output must be byte-identical to the pre-change baseline (the only changes are comments, no semantics change). If mypy produces a different error, the subagent reverts the specific change.
4. **Per-package test suite** — `uv run pytest packages/<pkg> -q` for each modified package. Baseline counts must hold (data-layer 2110, agents 1889, cli 45, ui-backend 793). The 4837-test total must remain unchanged.
5. **Per-task reviewer** — opens the diff, spot-checks 5-10 of the reason comments for correctness, confirms bucket assignments are plausible.

## Error handling

- **Wrong reason text** — if a per-task reviewer finds >1 in 10 misclassified, that subagent's commit is reverted and re-dispatched with explicit guidance.
- **mypy baseline drift** — if the mypy run after a subagent's edits shows new errors vs the pre-change baseline, that subagent's commit is reverted; the subagent re-dispatches and only processes comments whose classification doesn't trigger new errors.
- **Long-tail subagent finds too few** — if Task 9 finds <20 ignores, fold it into Tasks 1-8 (subagents handle multiple files). Saves a task dispatch.
- **File has more ignores than expected** — subagent processes them all in one task; no scope change.

## Risks

1. **Wrong reason text** — subagent misclassification. Mitigation: per-task reviewer spot-check.
2. **mypy baseline drift** — narrowing a bare ignore to a wrong code might surface a previously-suppressed error. Mitigation: mypy run as a hard gate; revert any change that produces new errors.
3. **Test count regression** — comment-only change shouldn't affect tests, but a misplaced comment could break syntax. Mitigation: per-package test suite as a hard gate.
4. **Code-narrowing mistake** — narrowing to the wrong `[code]` triggers a different mypy error than the bare ignore suppressed. Mitigation: revert the narrowing (keep bare + reason comment) if mypy errors change.

## Out of scope for this spec

- Fixing the underlying type issues (separate effort).
- Touching the 296 with-codes ignores (separate sweep if desired).
- Adding automation / pre-commit hook to enforce future bare-ignore discipline (separate decision).
- Running mypy in stricter mode (separate config change).
- Touching `.pyi` stub files.

## Existing infrastructure to reuse (do not duplicate)

| Capability | Where | Notes |
|---|---|---|
| mypy config | `pyproject.toml` per package | Strict mode enabled; `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache` per AGENTS.md |
| ruff check + format | `uv run ruff check packages` + `uv run ruff format packages` | Standard lint/format |
| Per-package test runner | `uv run pytest packages/<pkg> -q` | Baseline counts documented in AGENTS.md |
| SDD workflow | superpowers:subagent-driven-development | Per-task review + ledger |
