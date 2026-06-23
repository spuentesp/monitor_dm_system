# LLM Execution Reliability Plan

**Status:** Proposed implementation plan  
**Scope:** Ingestion and other agent-driven LLM execution paths  
**Primary goal:** Make LLM work in MONITOR transparent, visible, auditable, retry-safe, and kill-safe.

> Cross-reference: `ARCHITECTURE.md` for layer boundaries, `SYSTEM.md` for product goals, and `docs/architecture/DATABASE_INTEGRATION.md` for persistence responsibilities.

---

## 1. Problem Statement

The current MONITOR stack has partial retry support for some LLM calls, but heavy DSPy-driven ingestion work can still:

- skip failed batches without replay,
- mark jobs as completed even when work was omitted,
- hide which provider/model/attempt produced a failure,
- continue without a visible partial-failure state,
- leave operators without a reliable way to kill or recover a stuck job.

This plan standardizes LLM execution so that failure handling is explicit and observable.

---

## 2. Objectives

### Required outcomes

1. **No silent loss of LLM work** — failed batches must never disappear without a recorded status.
2. **Retry only retryable failures** — rate limits and transient upstream errors back off and retry; quota/auth/config errors fail fast.
3. **Full auditability** — every LLM attempt is persisted with provider, model, stage, batch, timing, and outcome.
4. **Truthful job states** — jobs must surface `retrying`, `partial`, `blocked_provider`, `failed`, and `killed` states clearly.
5. **Kill-safe operation** — unrecoverable or stuck jobs can be terminated without killing the API server.
6. **Operator visibility** — UI, logs, and APIs must show what is happening now and what happened previously.

### Non-goals

- Replacing DSPy or LiteLLM immediately.
- Introducing a new distributed workflow engine before the current stack is hardened.
- Rewriting ingestion architecture outside the established layer boundaries.

---

## 3. Current Stack to Keep

The current MONITOR stack is sufficient for the next reliability phase:

| Layer | Current tool | Role in the plan |
|---|---|---|
| Agents | `DSPy` | Prompt modules and structured extraction |
| Agents | `LiteLLM` | Provider abstraction and model routing |
| Data-layer | `PostgreSQL` | LLM config, retry policy, audit ledger |
| Data-layer | `MongoDB` | Ingestion job state and UI-facing progress |
| Data-layer | `Qdrant`, `MinIO` | Snippet persistence and source artifact retention |
| UI/backend | FastAPI/Uvicorn | Job orchestration and SSE status streaming |
| Observability | `logfire` + structured logs | Local tracing and diagnostics |

### Helpful additions

These tools are useful but optional for the first implementation wave:

- `aiolimiter` — provider-aware request throttling
- `Prometheus` + `Grafana` — metrics and dashboards
- `Sentry` — exception aggregation and alerting
- `Langfuse` or `LangSmith` — LLM trace inspection
- `Temporal` — long-term durable workflow engine if ingest volume or complexity grows significantly

---

## 4. Target Architecture

## 4.1 Single LLM execution layer

Create a dedicated execution subsystem in `packages/agents/src/monitor_agents/`:

- `llm_execution.py` — task runner, retry policy, timeout policy, attempt recording
- `llm_errors.py` — normalized error taxonomy and retryability classification
- `llm_rate_limits.py` — provider-aware concurrency and backoff coordination

**Rule:** ingestion/analyzer code should not call DSPy modules directly without passing through this execution layer.

## 4.2 Standard attempt envelope

Every LLM call should execute with a common envelope containing:

- `job_id`
- `source_id`
- `stage` (`game_detection`, `batched_extraction`, `relationship_inference`, etc.)
- `batch_id`
- `provider_id`
- `model`
- `role`
- `attempt_no`
- `started_at` / `ended_at`
- `status`
- `retryable`
- `error_class`
- `error_message`

This creates a durable audit trail for each attempt.

---

## 5. Failure Handling Model

## 5.1 Error taxonomy

Normalize provider/runtime errors into the following classes.

### Retryable

- rate limiting / `429`
- transient `5xx` upstream errors
- temporary network failures
- request timeouts
- temporary connection resets

### Non-retryable

- quota or budget exhausted
- invalid API key / auth failure
- unsupported model or provider misconfiguration
- invalid request schema
- deterministic validation failures

### Degraded-but-acceptable

- DSPy structured output fallback to JSON mode

This should be recorded as a degraded execution mode, not as a fatal error by itself.

## 5.2 Backoff policy

Use **exponential backoff with jitter** for retryable failures.

Recommended defaults:

- `max_attempts = 5`
- base delay `2s`
- cap at `30s`
- full jitter on each wait
- honor provider `Retry-After` headers when available

## 5.3 Provider circuit breaker

If a provider begins returning non-retryable failures for a job (for example, budget exhausted), open a circuit for that provider and stop sending more work to it for that job.

Possible outcomes:

- route to an allowed fallback provider, or
- mark the job as `blocked_provider` / `failed_non_retryable`

---

## 6. Durable Job Semantics

## 6.1 Required job states

Expand the ingestion state model to include:

- `RUNNING`
- `RETRYING`
- `BACKING_OFF`
- `PARTIAL`
- `BLOCKED_PROVIDER`
- `FAILED_NON_RETRYABLE`
- `KILLED`
- `CANCELLED`
- `COMPLETED`

## 6.2 Partial completion rules

A job must **not** be marked as a clean success if essential LLM batches were skipped or exhausted.

Use:

- `PARTIAL` when some useful output exists but one or more batches failed permanently
- `FAILED_NON_RETRYABLE` when the pipeline cannot continue with the selected provider set
- `COMPLETED` only when all required batches succeeded or were intentionally bypassed by policy

## 6.3 Replayable failed batches

Persist enough metadata to retry only failed work:

- batch index / stage
- source references / section range
- last failure class and message
- number of attempts used
- next retry time if scheduled

No batch should be silently discarded.

---

## 7. Kill-Safe Execution Model

## 7.1 Problem

`asyncio.to_thread(...)` is not a sufficient kill boundary for unrecoverable LLM work. A stuck Python thread cannot be forcefully terminated safely.

## 7.2 Recommended solution

Run heavy ingestion/analyzer execution in a **worker subprocess** rather than only inside the API process.

### Required behavior

1. backend enqueues a job
2. worker process claims the job
3. worker emits periodic heartbeats
4. monitor detects timeout / fatal stuck state
5. system escalates:
   - graceful cancel
   - `SIGTERM`
   - `SIGKILL` after grace timeout if still hung
6. job is marked `KILLED` with a recorded reason

**Important:** kill the worker process, not `uvicorn`.

---

## 8. Observability and Audit Trail

## 8.1 PostgreSQL audit ledger

Add an `llm_task_attempts` table for durable attempt-level tracking.

Suggested fields:

- `id`
- `job_id`
- `source_id`
- `stage`
- `batch_id`
- `provider_id`
- `model`
- `attempt_no`
- `status`
- `retryable`
- `error_class`
- `error_message`
- `backoff_ms`
- `started_at`
- `ended_at`
- `request_id`
- `prompt_hash`
- `input_size`
- `output_size`

## 8.2 MongoDB job timeline

Expose UI-friendly progress details in the ingestion job document:

- total batches
- succeeded batches
- failed batches
- retried batches
- current provider/model
- last error
- next retry time
- partial flag
- kill reason if applicable

## 8.3 UI and SSE visibility

The frontend should see clear states such as:

- `Retrying batch 23/28 after rate limit`
- `Provider blocked: budget exhausted`
- `Partial pack generated; 6 extraction batches failed`
- `Worker killed after heartbeat timeout`

---

## 9. Repo-Level Change Map

| Area | Files / modules | Expected change |
|---|---|---|
| Agents | `monitor_agents/analyzer.py` | Route DSPy module calls through the new execution layer; stop silent batch skipping |
| Agents | `monitor_agents/base.py` | Reuse retry policy definitions and align semantics with the execution layer |
| Agents | `monitor_agents/dspy_runtime.py` | Keep provider resolution centralized; surface provider metadata needed by audit records |
| Agents | `monitor_agents/llm_registry.py` | Support provider circuit-breaker decisions and controlled fallback |
| Agents | `monitor_agents/llm_execution.py` | New durable task runner and policy engine |
| Data-layer | PostgreSQL migration | Add attempt ledger and optional provider circuit state |
| Data-layer | MongoDB job update helpers | Persist partial/retrying/killed state details |
| UI/backend | `monitor_ui/routers/ingest.py` | Surface truthful status and retry timeline to the frontend |

---

## 10. Implementation Phases

| Phase | Goal | Deliverables |
|---|---|---|
| 0 | Stop silent corruption | retry classifier, batch persistence, truthful partial status, reduced concurrency |
| 1 | Centralize LLM execution | `LLMTaskRunner`, attempt ledger, unified retry/backoff policy |
| 2 | Add kill safety | subprocess worker boundary, heartbeat monitor, timeout escalation |
| 3 | Provider resilience | circuit breaker, controlled fallback routing, provider-specific throttling |
| 4 | Operations | dashboards, alerts, replay tooling, audit exports |

### Phase 0 — Immediate hardening

This is the first priority because it addresses correctness:

- add retry/backoff around analyzer DSPy calls
- stop returning `None` / `[]` without persisting batch failure state
- mark jobs `PARTIAL` when work was omitted
- lower concurrency for external providers during heavy extraction

### Phase 1 — Durable execution layer

- implement the shared LLM runner and error classifier
- persist every attempt to PostgreSQL
- enrich MongoDB job status for SSE/UI visibility

### Phase 2 — Kill-safe workers

- move heavy analysis to a subprocess worker boundary
- add heartbeat monitoring and kill escalation
- mark `KILLED` jobs explicitly with cause and timestamp

### Phase 3 — Provider resilience

- add provider circuit breakers
- separate retryable and non-retryable failures cleanly
- allow controlled fallback only when policy permits it

### Phase 4 — Operational visibility

- add metrics dashboards and alerting
- support “retry failed batches only” from an operator workflow
- enable trace inspection for incidents and regressions

---

## 11. Acceptance Criteria

This initiative is complete only when all of the following are true:

1. failed LLM batches are never silently skipped without a durable record;
2. retryable failures back off and retry automatically;
3. non-retryable failures stop promptly and truthfully;
4. ingestion jobs cannot report a clean success if required batches were lost;
5. operators can inspect every attempt by job, stage, provider, and batch;
6. stuck heavy jobs can be cancelled or killed without taking down the backend;
7. failed batches can be replayed without rerunning the entire source ingest.

---

## 12. Recommended Delivery Order

### Week 1

- Phase 0 hardening
- attempt ledger schema
- truthful partial status

### Week 2

- centralized execution layer
- provider throttling
- UI/SSE visibility improvements

### Week 3

- subprocess worker boundary
- kill escalation policy
- operational dashboards and replay tooling

---

## 13. Final Recommendation

MONITOR should treat LLM execution as a first-class runtime subsystem rather than as scattered library calls.

The professional path is to:

- centralize execution policy,
- classify failures correctly,
- persist every attempt,
- expose truthful status to operators,
- and isolate heavy jobs in killable worker processes.

That approach fits the current MONITOR stack and closes the verified reliability gaps without violating the existing layer architecture.
