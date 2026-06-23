# Shutdown and Process Lifecycle Audit

**Status:** Audit updated after initial shutdown implementation (2026-04-08)  
**Scope:** MONITOR dev runtime, UI backend lifecycle, background ingest workers, and auxiliary processes.

> Cross-reference: `ARCHITECTURE.md` for repo boundaries and `docs/architecture/LLM_EXECUTION_RELIABILITY_PLAN.md` for the broader reliability roadmap.
>
> **Update (2026-04-08):** The UI backend now performs explicit ingest-runtime shutdown cleanup in `packages/ui/backend/src/monitor_ui/main.py`, the shared ingestion executor is torn down explicitly, and `./dev.sh shutdown` / `./dev.sh down` now stops the full local stack plus approved auxiliary services.

---

## 1. Executive Summary

MONITOR now has a **developer-facing unified stop path** for the main runtime stack and initial in-application shutdown cleanup for ingest work, but it still lacks a fully process-isolated cancellation model for heavy worker hangs.

### Current reality

- **Yes:** there are shell-level start/stop/restart commands for the dev stack.
- **Yes:** the backend now coordinates shutdown cleanup for queued/running ingest work.
- **Yes:** the shared ingestion executor is explicitly torn down on application shutdown.
- **Partial:** approved auxiliary processes are now covered by `./dev.sh shutdown`, but unregistered helper processes still need to opt in.

---

## 2. What Exists Today

## 2.1 `dev.sh` stop / shutdown path

The repo includes a root-level `dev.sh` script with:

```bash
./dev.sh stop
./dev.sh shutdown
./dev.sh down
./dev.sh restart
./dev.sh status
```

### Verified behavior

`./dev.sh shutdown` (and `stop`) now:

- stops the **tmux `monitor` session** if it is active,
- stops the **Next.js frontend** using its PID file,
- stops the **FastAPI backend** using its PID file,
- stops approved auxiliary services- stops the main **Docker services** via `docker compose stop`.

### Coverage

This now covers the standard local dev runtime:

- tmux session
- frontend
- backend
- approved auxiliary services
- database containers

---

## 2.2 `tmux-dev.sh` stop path

The repo also includes a `tmux-dev.sh` launcher with:

```bash
./tmux-dev.sh kill
./tmux-dev.sh stopall
```

### Verified behavior

- `kill` → stops the tmux session only
- `stopall` → stops the tmux session and the main Docker services

This is also a valid operator-facing stop path for the local development layout.

---

## 2.3 Startup recovery exists for stale jobs

In `packages/ui/backend/src/monitor_ui/main.py`, the FastAPI `lifespan()` handler calls `_recover_stale_jobs()` on startup.

### What this does

On backend restart, any ingest jobs still marked `pending` or `running` are flipped to `failed` with an interruption message.

### Why this matters

This prevents the UI from showing permanently stuck in-progress jobs after a crash or restart.

---

## 3. What Is Missing

## 3.1 FastAPI shutdown cleanup is now present

The backend `lifespan()` implementation now performs both startup recovery and shutdown cleanup.

### Current shutdown behaviors

- clear active and pending in-memory ingest state
- mark queued/running ingest jobs as interrupted during shutdown
- flush final job-state updates before exit
- close the shared ingest executor explicitly

This closes the biggest app-lifecycle gap identified in the original audit.

---

## 3.2 Explicit shutdown of the ingestion executor is now present

`packages/ui/backend/src/monitor_ui/routers/ingest.py` now owns the shared executor lifecycle explicitly.

### Current behavior

- the executor is recreated on startup/reload when needed,
- shutdown calls `executor.shutdown(wait=False, cancel_futures=True)`,
- lifecycle cleanup is centralized instead of being left entirely to process exit.

---

## 3.3 No unified cancellation model for in-flight ingest work

The ingest router keeps in-memory state for:

- active requests
- pending requests
- active job IDs

However, the shutdown model does not yet guarantee:

- cancellation propagation to the running LLM work,
- durable persistence of queued-but-unstarted work for replay,
- forced escalation behavior for unrecoverable stuck jobs.

This is especially important for long-running analyzer and DSPy extraction workloads.

---

## 3.4 No single supervisor for all auxiliary processes

### Implication

These helper services are **not automatically guaranteed** to be covered by `dev.sh stop`.

If they are started separately, they may require their own stop command.

---

## 3.5 No kill-safe worker boundary for unrecoverable hangs

The current heavy ingest execution model uses background thread/executor patterns.

### Limitation

A stuck Python thread is not a robust kill boundary.

This means there is not yet a full runtime mechanism for:

- detecting a worker heartbeat failure,
- escalating from cancel → terminate → kill,
- cleanly isolating a hung analyzer without risking broader backend disruption.

---

## 4. Risk Assessment

| Area | Current status | Risk |
|---|---|---|
| Dev stop script | Present | Low |
| Container stop | Present | Low |
| Startup stale-job recovery | Present | Medium-positive safeguard |
| FastAPI shutdown cleanup | Present | Low-medium |
| Background executor lifecycle | Present | Low-medium |
| Auxiliary service stop coverage | Present for approved services; partial for unregistered helpers | Medium |
| Kill-safe heavy worker isolation | Missing | High |

---

## 5. Recommended Next Steps

## 5.1 Backend shutdown handling ✅

Implemented in this pass via the FastAPI `lifespan()` shutdown path plus `ingest.shutdown_ingest_runtime()`.

### What it now does

- marks queued/running ingest jobs interrupted,
- clears pending/active in-memory queue state,
- flushes final job updates,
- closes executor resources explicitly.

## 5.2 Executor teardown ✅

The shared ingestion executor now shuts down explicitly on application exit using `shutdown(wait=False, cancel_futures=True)`.

## 5.3 Standardize runtime job termination

Implement a consistent cancellation/termination policy for long-running ingestion jobs:

- soft cancel first
- hard timeout if needed
- explicit job status update to `failed`, `killed`, or `interrupted`

## 5.4 Auxiliary service supervision ⚠️

This is partially addressed: `./dev.sh shutdown` now stops approved auxiliary services and the `monitor` tmux session.

Remaining work:

- define a registration rule for future helper daemons,
- document which services are officially covered by the unified stop path.

## 5.5 Introduce a kill-safe worker process for heavy LLM jobs

For reliability-critical ingestion work, move from a thread-only model to a subprocess worker model with:

- heartbeats
- timeout enforcement
- `SIGTERM` / `SIGKILL` escalation when required

This aligns with the broader execution reliability plan.

---

## 6. Bottom Line

MONITOR now has **shell-level and in-app shutdown handling** for the standard local stack, including explicit cleanup for queued/running ingest work and a unified `./dev.sh shutdown` command.

The remaining gap is the deeper reliability work: durable queued-job replay and a kill-safe subprocess boundary for unrecoverable hangs.
