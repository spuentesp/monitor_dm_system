# GM table-test pre-flight — 2026-11-11

> **Method:** `scripts/gm_table_test_preflight.py` against a backend built from
> this worktree on `:8123` (`MONITOR_AUTH_DISABLED=true`, live Mongo/Neo4j/
> Postgres), run before the human table test (G11) so a broken build does not
> cost two hours of GM session.

The table test is a ≥2 h human session. This run checks every endpoint the
protocol touches (S1–S9 lookups, C1–C4 combat, plus the clock and share
surfaces) and reports what is ready and what is not — distinguishing **the
endpoint failed** from **the environment has nothing to check against**.

## Result

```
[ ok ] health   the backend answers
[ ok ] S1       Lookups → NPC (dossier with what the NPC wants)
[SKIP] S2       Lookups → Party knows      — no characters in this universe
[SKIP] S3       Lookups → Last session     — this universe has no story
[FAIL] S4       Lookups → Name (≤ ~30 s)   — 120.1s: the lookup exceeded the table budget
[ ok ] S5       Lookups → Complication (≤ ~30 s)
[ ok ] S6       Lookups → Rules (answer carries its source)
[ ok ] S7       Tonight → Extract for review (prep from notes)
[SKIP] S8       Session Log → Canon        — this universe has no story
[ ok ] C1       Combat → start (initiative order)
[ ok ] C1b      Combat → Set order (initiative)
[ ok ] C2       Combat → damage (HP drops, conditions stick)
[ ok ] C3       Combat → condition explanation
[SKIP] C4       Combat → end                — this universe has no story
[SKIP] CLOCK    World clock (CF-11)
[SKIP] SHARE    Share link (CF-14)
[ ok ] KNOWLEDGE Knowledge inspector (CF-15)
```

The six SKIPs are the *pre-flight* being honest: the run picked
"The Wreck of the Penitent Star" (a bound game system and four entities) for
the checks that need them, and that universe has no story and no characters,
so the story-scoped checks have nothing to run against. Those checks are
covered by the `tests/behavior` and `tests/api` suites against fixtures.

## Two real findings, both about the model behind a lookup

### 1. The Complication lookup returned 500 (found and fixed)

**S5** failed on the first run: `POST /gm/lookup/improvise` returned 500 with
`1 validation error for ComplicationSuggestions — complications: Input should
be a valid array, input_value='["The players are being ..."]'`.

The model (the LIGHT tier's `llama3.2:1b`) wrote its list as a **JSON string**
where an array belongs. Instructor's retry loop threw that answer away; the
retry returned prose; the whole lookup failed. At the table that is "the
assistant is broken", for a lookup the protocol allows 30 seconds.

**Fixed** in two places:

- `monitor_agents/lenient_parsing.py` — `recover_instructor_failure()` walks
  the attempts instructor recorded and validates each candidate through the
  existing `lenient_validate`. Two repair rules were added for the
  malformations the model actually produced: a value wrapped in its own
  schema (`{"type": "string", "value": "..."}` → the value) and a single
  string arriving as a one-item list. Both are explicit rules — a dict that
  means something else is still rejected.
- `BaseAgent.call_llm_structured` — the recovery runs first; when it cannot
  repair the answer and the failure is a *model-output* validation problem
  (the answers came back and none parsed), the call falls back to the
  default provider. A request that is itself invalid is not retried
  elsewhere; a model that cannot produce the structure is.

After the fix S5 answers in 2.5–28 s.

### 2. The lookups are as fast as the LIGHT tier (open, for the session)

**S4** (Name) took 120 s against the protocol's "≤ ~30 s" bar — the model
answered, slowly, after retries. **S6** (Rules) took 37 s in one run and 6 s
in another. The variance is the LIGHT-tier provider (`llama3.2:1b` on local
Ollama), not the endpoints.

This is a finding for the table test rather than a bug: the GM will feel it
as "the name took two minutes". Two ways to deal with it before the session:

- Give the improvise lookups a faster or stronger provider (a provider row
  with `role='light'` that is actually fast, or move them to `standard`).
- Accept the latency and record it in the lookup log — the protocol already
  asks for the seconds each lookup took, which is exactly this measurement.

## Reproducing

```bash
# backend from this worktree on :8123 (leave the owner's :8000 alone)
cd packages/ui/backend
set -a && . ../../../.env && set +a && export MONITOR_AUTH_DISABLED=true
uv run uvicorn monitor_ui.main:app --app-dir src --host 127.0.0.1 --port 8123 &

# then the pre-flight
uv run python scripts/gm_table_test_preflight.py \
    --base-url http://127.0.0.1:8123 \
    --universe-id <a universe with a story and characters> \
    --json-out /tmp/preflight.json
```

Exit code 0 when every check passes, 1 when any fails — so it can gate the
session.
