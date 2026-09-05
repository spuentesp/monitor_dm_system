# T-013 Bare `# type: ignore` Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `# reason: <text>` comment above each of the 253 bare `# type: ignore` comments in `packages/` and `scripts/`, classifying each into one of 6 buckets and narrowing to a specific mypy code where the bucket fits.

**Architecture:** 9 subagent-driven tasks (8 top-concentration ui-backend router files covering 197 of the 253 ignores; 1 long-tail task covering the remaining ~56). Each subagent reads its target file, classifies each bare ignore into a bucket, inserts the reason comment, narrows codes where appropriate, runs mypy + ruff + per-package tests, and commits. Per-task reviewer spot-checks 5-10 of the comments.

**Tech Stack:** Python 3.11, mypy (strict mode per package), ruff (check + format), pytest, `git`. No new dependencies. No new tooling. Existing project conventions only.

## Global Constraints

- Branch: `master`. Working tree is clean at `91b7218` (the spec commit). Tasks 1-9 land as 9 separate commits on `master`.
- The change is **comments only** — no source code is modified. mypy output, test counts, and runtime behavior must all be byte-identical to baseline.
- Baseline test counts (must hold post-task): `uv run pytest packages/data-layer -q` → 2110 passed, 14 skipped; `uv run pytest packages/agents -q` → 1889 passed, 2 skipped; `uv run pytest packages/cli -q` → 45 passed; `uv run pytest packages/ui/backend -q` → 793 passed, 2 skipped. **Total 4837 passed, 22 skipped.**
- Baseline mypy: `uv run mypy packages/*/src --cache-dir /tmp/mypy-cache` per AGENTS.md. Output must be byte-identical after each task.
- Standard format: `# reason: <bucket text>` immediately above the bare ignore. No blank line between the reason comment and the ignore. Reason text matches one of the 6 buckets from the spec.
- Narrowing: `# type: ignore` → `# type: ignore[<code>]` only when the bucket clearly identifies the code (e.g., `[attr-defined]`, `[assignment]`). Never narrow unless the bucket text implies the code.
- Per-task commit message: `chore(types): add reason comments to bare # type: ignore in <file>`.
- SDD skill forbids parallel implementer dispatches — Tasks 1-9 run sequentially.

---

## File Structure

| File | Created/Modified by | Responsibility |
|---|---|---|
| `docs/superpowers/plans/2026-09-05-t013-type-ignore-cleanup.md` | This plan (now) | Implementation plan. |
| `packages/ui/backend/src/monitor_ui/routers/pack_library.py` | Task 1 | 54 bare ignores |
| `packages/ui/backend/src/monitor_ui/routers/entities.py` | Task 2 | 32 bare ignores |
| `packages/ui/backend/src/monitor_ui/routers/ingest.py` | Task 3 | 26 bare ignores |
| `packages/ui/backend/src/monitor_ui/routers/graph.py` | Task 4 | 19 bare ignores |
| `packages/ui/backend/src/monitor_ui/routers/universes.py` | Task 5 | 17 bare ignores |
| `packages/ui/backend/src/monitor_ui/routers/chat.py` | Task 6 | 15 bare ignores |
| `packages/ui/backend/src/monitor_ui/routers/performance.py` | Task 7 | 13 bare ignores |
| `packages/ui/backend/src/monitor_ui/routers/forge.py` | Task 8 | 11 bare ignores |
| ~30+ smaller files (long-tail) | Task 9 | ~56 bare ignores across watchdog, main, jobs_health, databases, character_storage, game_systems, ingest_shared, agents/, data-layer/, scripts/ |

---

## Task 1: `pack_library.py` — 54 bare ignores

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/pack_library.py`

**Interfaces:**
- Consumes: 6-bucket reason taxonomy from spec §"Reason taxonomy". Bucket text is verbatim.
- Produces: A modified `pack_library.py` with each of the 54 bare `# type: ignore` lines preceded by `# reason: <bucket text>`. Where the bucket identifies a specific mypy code, the bare ignore is narrowed to `# type: ignore[<code>]`.

- [ ] **Step 1: Capture pre-change baselines**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD  # record the pre-task SHA for the mypy comparison
uv run ruff check packages/ui/backend/src/monitor_ui/routers/pack_library.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/pack_library.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/pack_library.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Save the ruff and mypy output to `/tmp/t013_baseline_pack_library.txt` for later comparison.

- [ ] **Step 2: Read the file and locate all bare ignores**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/pack_library.py
```

Expected: 54 lines, one per bare ignore. Read the file to understand context for each.

- [ ] **Step 3: Classify each bare ignore into one of the 6 buckets**

Read the file. For each bare ignore, look at the line in context and pick a bucket:
1. **DSPy signature** — `# type: ignore` on `dspy.Signature` subclasses or DSPy module forward overrides.
2. **FastAPI Pydantic-Any** — `# type: ignore` on Pydantic model attributes accessed via `request.<thing>` or anywhere the type comes back as `Any` from Pydantic v2.
3. **Third-party type stub gap** — `# type: ignore` on imports or attribute access from libraries lacking type stubs.
4. **Dynamic dispatch** — `# type: ignore` on `getattr`, `setattr`, `importlib.import_module`, etc.
5. **Test fixture / monkey-patch** — `# type: ignore` on `cls.x = y` assignments in test conftest or attribute overrides on mock objects.
6. **Genuine typing gap** — anything else. Write a bespoke one-liner.

If unsure between buckets, prefer the 6th (Genuine typing gap) and write a specific one-liner explaining the line. Never guess.

- [ ] **Step 4: For each bare ignore, add the reason comment**

For each classified bare ignore, insert a comment immediately above it. Use the bucket's exact reason text:

Bucket 1 — DSPy signature:
```python
    # reason: DSPy signature — dspy.Signature subclasses use dynamic field typing mypy can't model
    return result  # type: ignore
```

Bucket 2 — FastAPI Pydantic-Any:
```python
    # reason: FastAPI/Pydantic v2 returns Any for dynamic model attributes; mypy can't narrow without explicit Annotated[]
    return result  # type: ignore[return-value]
```

Bucket 3 — Third-party type stub gap (with library name):
```python
    # reason: <library> lacks type stubs; suppress until upstream adds py.typed
    import foo.bar  # type: ignore
```

Bucket 4 — Dynamic dispatch:
```python
    # reason: dynamic dispatch — type can't be inferred at static-analysis time
    val = getattr(obj, name)  # type: ignore
```

Bucket 5 — Test fixture / monkey-patch:
```python
    # reason: test fixture monkey-patch — type intentionally narrowed for the test scope
    cls.x = Mock()  # type: ignore
```

Bucket 6 — Genuine typing gap (bespoke):
```python
    # reason: <bespoke one-liner specific to this line>
    result  # type: ignore
```

Do not add a blank line between the reason comment and the ignore. Do not modify any other content.

- [ ] **Step 5: Narrow codes where the bucket implies them**

For each reason comment added, if the bucket identifies a specific mypy code, narrow the bare ignore. Examples:

- Bucket 2 (FastAPI Pydantic-Any) → narrow to `[return-value]` or `[assignment]` or `[no-any-return]` depending on the context.
- Bucket 3 (Third-party stub gap) → narrow to `[attr-defined]` or `[import]` or `[call-arg]` depending on the import.
- Bucket 4 (Dynamic dispatch) → narrow to `[attr-defined]` for `getattr`/`setattr` patterns.

Buckets 1, 5, and 6 generally don't imply a specific code — leave them bare.

If unsure whether to narrow, **leave bare**. A narrow-with-wrong-code triggers a mypy error that the original bare ignore suppressed. Better to leave bare than to surface a hidden error.

- [ ] **Step 6: Verify ruff + mypy + tests**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages/ui/backend/src/monitor_ui/routers/pack_library.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/pack_library.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/pack_library.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Expected:
- `ruff check`: passes (no changes to lint).
- `ruff format --check`: passes (the comment placement doesn't trigger formatting).
- `mypy`: byte-identical to baseline (only comments changed).

If mypy errors change (new errors appear or old ones disappear), revert the changes that triggered the diff. The most common cause is incorrect narrowing.

Run the test suite:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: `793 passed, 2 skipped` (matches baseline).

- [ ] **Step 7: Confirm 0 bare ignores remain**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/pack_library.py
```

Expected: no output. Every bare ignore now has a `# reason:` comment.

- [ ] **Step 8: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages/ui/backend/src/monitor_ui/routers/pack_library.py
git commit -m "chore(types): add reason comments to bare # type: ignore in pack_library.py

T-013 cleanup: 54 bare # type: ignore in this file now have a
# reason: comment classifying the suppression. Bucket distribution:
<insert actual counts>.

No code change; mypy output byte-identical to baseline. ruff check +
format clean. ui/backend test suite still 793 passed, 2 skipped."
```

The implementer replaces `<insert actual counts>` with the actual bucket distribution (e.g., `Bucket 1: 5, Bucket 2: 30, Bucket 3: 8, Bucket 4: 4, Bucket 5: 0, Bucket 6: 7`).

- [ ] **Step 9: Report to ledger**

Write a brief report to `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-1-report.md` with:
- Bucket distribution.
- Any bare ignores that couldn't be classified (logged for human review).
- Any mypy errors that appeared/disappeared vs baseline.
- Commit SHA.

---

## Task 2: `entities.py` — 32 bare ignores

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/entities.py`

**Interfaces:**
- Consumes: 6-bucket reason taxonomy from spec §"Reason taxonomy". Bucket text is verbatim.
- Produces: A modified `entities.py` with each of the 32 bare `# type: ignore` lines preceded by `# reason: <bucket text>`.

- [ ] **Step 1: Capture pre-change baselines**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD
uv run ruff check packages/ui/backend/src/monitor_ui/routers/entities.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/entities.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/entities.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Save output to `/tmp/t013_baseline_entities.txt`.

- [ ] **Step 2: Read the file and locate all bare ignores**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/entities.py
```

Expected: 32 lines. Read the file for context.

- [ ] **Step 3: Classify each bare ignore into one of the 6 buckets**

For each of the 32 bare ignores, classify per the 6-bucket taxonomy from Task 1 Step 3. Same decision rule: prefer Bucket 6 (bespoke) over guessing.

- [ ] **Step 4: For each bare ignore, add the reason comment**

Insert `# reason: <bucket text>` immediately above each bare ignore. Bucket text is verbatim from the taxonomy. No blank line between reason comment and ignore.

- [ ] **Step 5: Narrow codes where the bucket implies them**

Narrow only where the bucket text clearly identifies the code. If unsure, leave bare.

- [ ] **Step 6: Verify ruff + mypy + tests**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages/ui/backend/src/monitor_ui/routers/entities.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/entities.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/entities.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: ruff passes; ruff format no-op; mypy byte-identical; 793 passed, 2 skipped.

- [ ] **Step 7: Confirm 0 bare ignores remain**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/entities.py
```

Expected: no output.

- [ ] **Step 8: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages/ui/backend/src/monitor_ui/routers/entities.py
git commit -m "chore(types): add reason comments to bare # type: ignore in entities.py

T-013 cleanup: 32 bare # type: ignore in this file now have a
# reason: comment classifying the suppression. Bucket distribution:
<insert actual counts>.

No code change; mypy output byte-identical to baseline. ruff check +
format clean. ui/backend test suite still 793 passed, 2 skipped."
```

- [ ] **Step 9: Report to ledger**

Write `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-2-report.md` (bucket distribution, unclassified lines, mypy changes, commit SHA).

---

## Task 3: `ingest.py` — 26 bare ignores

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/ingest.py`

**Interfaces:**
- Consumes: 6-bucket reason taxonomy. Bucket text is verbatim.
- Produces: A modified `ingest.py` with each of the 26 bare `# type: ignore` lines preceded by `# reason: <bucket text>`.

- [ ] **Step 1: Capture pre-change baselines**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD
uv run ruff check packages/ui/backend/src/monitor_ui/routers/ingest.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/ingest.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/ingest.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Save to `/tmp/t013_baseline_ingest.txt`.

- [ ] **Step 2: Read the file and locate all bare ignores**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/ingest.py
```

Expected: 26 lines. Read for context.

- [ ] **Step 3: Classify each bare ignore into one of the 6 buckets**

Per the 6-bucket taxonomy. Same Bucket 6 preference.

- [ ] **Step 4: For each bare ignore, add the reason comment**

Insert `# reason: <bucket text>` immediately above each bare ignore.

- [ ] **Step 5: Narrow codes where the bucket implies them**

Narrow only where clearly indicated.

- [ ] **Step 6: Verify ruff + mypy + tests**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages/ui/backend/src/monitor_ui/routers/ingest.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/ingest.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/ingest.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: ruff passes; ruff format no-op; mypy byte-identical; 793 passed, 2 skipped.

- [ ] **Step 7: Confirm 0 bare ignores remain**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/ingest.py
```

Expected: no output.

- [ ] **Step 8: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages/ui/backend/src/monitor_ui/routers/ingest.py
git commit -m "chore(types): add reason comments to bare # type: ignore in ingest.py

T-013 cleanup: 26 bare # type: ignore in this file now have a
# reason: comment classifying the suppression. Bucket distribution:
<insert actual counts>.

No code change; mypy output byte-identical to baseline. ruff check +
format clean. ui/backend test suite still 793 passed, 2 skipped."
```

- [ ] **Step 9: Report to ledger**

Write `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-3-report.md`.

---

## Task 4: `graph.py` — 19 bare ignores

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/graph.py`

**Interfaces:**
- Consumes: 6-bucket reason taxonomy. Bucket text is verbatim.
- Produces: A modified `graph.py` with each of the 19 bare `# type: ignore` lines preceded by `# reason: <bucket text>`.

- [ ] **Step 1: Capture pre-change baselines**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD
uv run ruff check packages/ui/backend/src/monitor_ui/routers/graph.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/graph.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/graph.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Save to `/tmp/t013_baseline_graph.txt`.

- [ ] **Step 2: Read the file and locate all bare ignores**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/graph.py
```

Expected: 19 lines. Read for context.

- [ ] **Step 3: Classify each bare ignore into one of the 6 buckets**

Per the 6-bucket taxonomy.

- [ ] **Step 4: For each bare ignore, add the reason comment**

Insert `# reason: <bucket text>` immediately above each bare ignore.

- [ ] **Step 5: Narrow codes where the bucket implies them**

Narrow only where clearly indicated.

- [ ] **Step 6: Verify ruff + mypy + tests**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages/ui/backend/src/monitor_ui/routers/graph.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/graph.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/graph.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: ruff passes; ruff format no-op; mypy byte-identical; 793 passed, 2 skipped.

- [ ] **Step 7: Confirm 0 bare ignores remain**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/graph.py
```

Expected: no output.

- [ ] **Step 8: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages/ui/backend/src/monitor_ui/routers/graph.py
git commit -m "chore(types): add reason comments to bare # type: ignore in graph.py

T-013 cleanup: 19 bare # type: ignore in this file now have a
# reason: comment classifying the suppression. Bucket distribution:
<insert actual counts>.

No code change; mypy output byte-identical to baseline. ruff check +
format clean. ui/backend test suite still 793 passed, 2 skipped."
```

- [ ] **Step 9: Report to ledger**

Write `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-4-report.md`.

---

## Task 5: `universes.py` — 17 bare ignores

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/universes.py`

**Interfaces:**
- Consumes: 6-bucket reason taxonomy.
- Produces: A modified `universes.py` with each of the 17 bare `# type: ignore` lines preceded by `# reason: <bucket text>`.

- [ ] **Step 1: Capture pre-change baselines**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD
uv run ruff check packages/ui/backend/src/monitor_ui/routers/universes.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/universes.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/universes.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Save to `/tmp/t013_baseline_universes.txt`.

- [ ] **Step 2: Read the file and locate all bare ignores**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/universes.py
```

Expected: 17 lines. Read for context.

- [ ] **Step 3: Classify each bare ignore into one of the 6 buckets**

Per the 6-bucket taxonomy.

- [ ] **Step 4: For each bare ignore, add the reason comment**

Insert `# reason: <bucket text>` immediately above each bare ignore.

- [ ] **Step 5: Narrow codes where the bucket implies them**

Narrow only where clearly indicated.

- [ ] **Step 6: Verify ruff + mypy + tests**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages/ui/backend/src/monitor_ui/routers/universes.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/universes.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/universes.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: ruff passes; ruff format no-op; mypy byte-identical; 793 passed, 2 skipped.

- [ ] **Step 7: Confirm 0 bare ignores remain**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/universes.py
```

Expected: no output.

- [ ] **Step 8: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages/ui/backend/src/monitor_ui/routers/universes.py
git commit -m "chore(types): add reason comments to bare # type: ignore in universes.py

T-013 cleanup: 17 bare # type: ignore in this file now have a
# reason: comment classifying the suppression. Bucket distribution:
<insert actual counts>.

No code change; mypy output byte-identical to baseline. ruff check +
format clean. ui/backend test suite still 793 passed, 2 skipped."
```

- [ ] **Step 9: Report to ledger**

Write `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-5-report.md`.

---

## Task 6: `chat.py` — 15 bare ignores

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/chat.py`

**Interfaces:**
- Consumes: 6-bucket reason taxonomy.
- Produces: A modified `chat.py` with each of the 15 bare `# type: ignore` lines preceded by `# reason: <bucket text>`.

- [ ] **Step 1: Capture pre-change baselines**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD
uv run ruff check packages/ui/backend/src/monitor_ui/routers/chat.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/chat.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/chat.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Save to `/tmp/t013_baseline_chat.txt`.

- [ ] **Step 2: Read the file and locate all bare ignores**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/chat.py
```

Expected: 15 lines. Read for context.

- [ ] **Step 3: Classify each bare ignore into one of the 6 buckets**

Per the 6-bucket taxonomy.

- [ ] **Step 4: For each bare ignore, add the reason comment**

Insert `# reason: <bucket text>` immediately above each bare ignore.

- [ ] **Step 5: Narrow codes where the bucket implies them**

Narrow only where clearly indicated.

- [ ] **Step 6: Verify ruff + mypy + tests**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages/ui/backend/src/monitor_ui/routers/chat.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/chat.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/chat.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: ruff passes; ruff format no-op; mypy byte-identical; 793 passed, 2 skipped.

- [ ] **Step 7: Confirm 0 bare ignores remain**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/chat.py
```

Expected: no output.

- [ ] **Step 8: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages/ui/backend/src/monitor_ui/routers/chat.py
git commit -m "chore(types): add reason comments to bare # type: ignore in chat.py

T-013 cleanup: 15 bare # type: ignore in this file now have a
# reason: comment classifying the suppression. Bucket distribution:
<insert actual counts>.

No code change; mypy output byte-identical to baseline. ruff check +
format clean. ui/backend test suite still 793 passed, 2 skipped."
```

- [ ] **Step 9: Report to ledger**

Write `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-6-report.md`.

---

## Task 7: `performance.py` — 13 bare ignores

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/performance.py`

**Interfaces:**
- Consumes: 6-bucket reason taxonomy.
- Produces: A modified `performance.py` with each of the 13 bare `# type: ignore` lines preceded by `# reason: <bucket text>`.

- [ ] **Step 1: Capture pre-change baselines**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD
uv run ruff check packages/ui/backend/src/monitor_ui/routers/performance.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/performance.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/performance.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Save to `/tmp/t013_baseline_performance.txt`.

- [ ] **Step 2: Read the file and locate all bare ignores**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/performance.py
```

Expected: 13 lines. Read for context.

- [ ] **Step 3: Classify each bare ignore into one of the 6 buckets**

Per the 6-bucket taxonomy.

- [ ] **Step 4: For each bare ignore, add the reason comment**

Insert `# reason: <bucket text>` immediately above each bare ignore.

- [ ] **Step 5: Narrow codes where the bucket implies them**

Narrow only where clearly indicated.

- [ ] **Step 6: Verify ruff + mypy + tests**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages/ui/backend/src/monitor_ui/routers/performance.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/performance.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/performance.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: ruff passes; ruff format no-op; mypy byte-identical; 793 passed, 2 skipped.

- [ ] **Step 7: Confirm 0 bare ignores remain**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/performance.py
```

Expected: no output.

- [ ] **Step 8: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages/ui/backend/src/monitor_ui/routers/performance.py
git commit -m "chore(types): add reason comments to bare # type: ignore in performance.py

T-013 cleanup: 13 bare # type: ignore in this file now have a
# reason: comment classifying the suppression. Bucket distribution:
<insert actual counts>.

No code change; mypy output byte-identical to baseline. ruff check +
format clean. ui/backend test suite still 793 passed, 2 skipped."
```

- [ ] **Step 9: Report to ledger**

Write `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-7-report.md`.

---

## Task 8: `forge.py` — 11 bare ignores

**Files:**
- Modify: `packages/ui/backend/src/monitor_ui/routers/forge.py`

**Interfaces:**
- Consumes: 6-bucket reason taxonomy.
- Produces: A modified `forge.py` with each of the 11 bare `# type: ignore` lines preceded by `# reason: <bucket text>`.

- [ ] **Step 1: Capture pre-change baselines**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD
uv run ruff check packages/ui/backend/src/monitor_ui/routers/forge.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/forge.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/forge.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
```

Save to `/tmp/t013_baseline_forge.txt`.

- [ ] **Step 2: Read the file and locate all bare ignores**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/forge.py
```

Expected: 11 lines. Read for context.

- [ ] **Step 3: Classify each bare ignore into one of the 6 buckets**

Per the 6-bucket taxonomy.

- [ ] **Step 4: For each bare ignore, add the reason comment**

Insert `# reason: <bucket text>` immediately above each bare ignore.

- [ ] **Step 5: Narrow codes where the bucket implies them**

Narrow only where clearly indicated.

- [ ] **Step 6: Verify ruff + mypy + tests**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages/ui/backend/src/monitor_ui/routers/forge.py 2>&1 | tail -3
uv run ruff format --check packages/ui/backend/src/monitor_ui/routers/forge.py 2>&1 | tail -3
uv run mypy packages/ui/backend/src/monitor_ui/routers/forge.py --cache-dir /tmp/mypy-cache 2>&1 | tail -20
uv run pytest packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected: ruff passes; ruff format no-op; mypy byte-identical; 793 passed, 2 skipped.

- [ ] **Step 7: Confirm 0 bare ignores remain**

Run:
```bash
grep -nE "# type: ignore\s*$" /home/sebastian/orca/monitor_dm_system/packages/ui/backend/src/monitor_ui/routers/forge.py
```

Expected: no output.

- [ ] **Step 8: Commit**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages/ui/backend/src/monitor_ui/routers/forge.py
git commit -m "chore(types): add reason comments to bare # type: ignore in forge.py

T-013 cleanup: 11 bare # type: ignore in this file now have a
# reason: comment classifying the suppression. Bucket distribution:
<insert actual counts>.

No code change; mypy output byte-identical to baseline. ruff check +
format clean. ui/backend test suite still 793 passed, 2 skipped."
```

- [ ] **Step 9: Report to ledger**

Write `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-8-report.md`.

---

## Task 9: Long-tail — ~56 bare ignores across smaller files

**Files:**
- Modify: every other file under `packages/` and `scripts/` that has bare `# type: ignore` comments NOT touched by Tasks 1-8. Likely candidates (verify via grep):
  - `packages/ui/backend/src/monitor_ui/watchdog.py` (~4)
  - `packages/ui/backend/src/monitor_ui/main.py` (~5)
  - `packages/ui/backend/src/monitor_ui/routers/jobs_health.py` (~4)
  - `packages/ui/backend/src/monitor_ui/routers/databases.py` (~4)
  - `packages/ui/backend/src/monitor_ui/routers/character_storage.py` (~6)
  - `packages/ui/backend/src/monitor_ui/routers/game_systems.py` (~5)
  - `packages/ui/backend/src/monitor_ui/routers/ingest_shared.py` (~6)
  - Other ui-backend files (verify via grep)
  - agents/data-layer files (small counts)
  - scripts/ (~2)

**Interfaces:**
- Consumes: 6-bucket reason taxonomy.
- Produces: A modified set of files; every bare `# type: ignore` in `packages/` and `scripts/` now has a `# reason: <bucket text>` comment above it.

- [ ] **Step 1: Inventory remaining bare ignores**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
grep -rEn "# type: ignore\s*$" packages scripts --include="*.py" 2>/dev/null | grep -v __pycache__
```

Expected: ~56 lines across multiple files. Note any file that the long-tail subagent will handle.

- [ ] **Step 2: Capture pre-change baselines for affected packages**

For each package that has long-tail files (likely ui-backend + agents + data-layer + scripts), capture:

```bash
cd /home/sebastian/orca/monitor_dm_system
git rev-parse HEAD
uv run ruff check packages 2>&1 | tail -3
uv run ruff format --check packages 2>&1 | tail -3
uv run mypy packages --cache-dir /tmp/mypy-cache 2>&1 | tail -30
```

Save to `/tmp/t013_baseline_longtail.txt`.

- [ ] **Step 3: Process each long-tail file in turn**

For each file:
1. Read the file.
2. Locate bare `# type: ignore` (grep -nE "# type: ignore\s*$" <file>).
3. Classify each into one of the 6 buckets.
4. Insert `# reason: <bucket text>` immediately above each bare ignore.
5. Narrow codes where the bucket implies them.

Use the Edit tool for each comment insertion, preserving all other content. Do not modify any other line.

- [ ] **Step 4: Verify ruff + mypy + tests for the affected packages**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
uv run ruff check packages 2>&1 | tail -3
uv run ruff format --check packages 2>&1 | tail -3
uv run mypy packages --cache-dir /tmp/mypy-cache 2>&1 | tail -30
uv run pytest packages/data-layer packages/agents packages/cli packages/ui/backend -q --tb=line 2>&1 | tail -3
```

Expected:
- ruff check: passes.
- ruff format --check: no changes.
- mypy: byte-identical to baseline.
- pytest: 4837 passed, 22 skipped total (2110+1889+45+793).

If mypy errors change (new errors appear or old ones disappear), revert the changes that triggered the diff. Re-run, narrowing only when the bucket clearly identifies the code.

- [ ] **Step 5: Confirm 0 bare ignores remain anywhere**

Run:
```bash
grep -rEn "# type: ignore\s*$" packages scripts --include="*.py" 2>/dev/null | grep -v __pycache__
```

Expected: no output. The audit target is fully processed.

- [ ] **Step 6: Single commit covering all long-tail files**

Run:
```bash
cd /home/sebastian/orca/monitor_dm_system
git add packages scripts
git commit -m "chore(types): add reason comments to bare # type: ignore (long-tail)

T-013 cleanup: ~56 bare # type: ignore in smaller files (not in the
top-8 ui-backend routers) now have # reason: comments classifying
the suppression. Bucket distribution:
<insert actual counts>.

Affected files:
<list file: count pairs, e.g.,
  packages/ui/backend/src/monitor_ui/watchdog.py: 4
  packages/ui/backend/src/monitor_ui/main.py: 5
  ...

No code change; mypy output byte-identical to baseline. ruff check +
format clean. Full pytest suite still 4837 passed, 22 skipped."
```

- [ ] **Step 7: Report to ledger**

Write `.superpowers/sdd/2026-09-05-t013-type-ignore-cleanup/task-9-report.md` with:
- Full file inventory (file → bare-ignore-count).
- Bucket distribution across all long-tail files.
- Any unclassified bare ignores logged for human review.
- mypy diff (should be none).
- Commit SHA.

---

## Verification matrix (after all 9 tasks)

Run from `/home/sebastian/orca/monitor_dm_system`:

```bash
# 1. No bare # type: ignore remains anywhere in the codebase.
grep -rEn "# type: ignore\s*$" packages scripts --include="*.py" 2>/dev/null | grep -v __pycache__
# Expected: no output.

# 2. The 253 bare ignores have become 253 # reason: comments.
grep -rEn "# reason:" packages scripts --include="*.py" 2>/dev/null | grep -v __pycache__ | wc -l
# Expected: at least 253 (may be more if Bucket 6 lines add multiple reason comments).

# 3. mypy is byte-identical to baseline.
uv run mypy packages --cache-dir /tmp/mypy-cache 2>&1 | diff /tmp/t013_baseline_longtail.txt -
# Expected: no diff.

# 4. Test suite still at baseline.
uv run pytest packages/data-layer packages/agents packages/cli packages/ui/backend -q 2>&1 | tail -3
# Expected: 4837 passed, 22 skipped.

# 5. Lint clean.
uv run ruff check packages 2>&1 | tail -3
# Expected: All checks passed!

# 6. Format clean.
uv run ruff format --check packages 2>&1 | tail -3
# Expected: N files already formatted (no changes needed).

# 7. Nine commits on master, working tree clean.
git log --oneline -10 | head -10
git status --short
# Expected: 9 commits on top of 91b7218, working tree clean.
```

If any check fails, do not declare T-013 complete — investigate the failing task before proceeding.
