# System Lifecycle & Durability

This document describes how MONITOR manages the execution lifecycle of its agents and ensures that narrative state and long-running background tasks are durable across process restarts and system failures.

---

## 1. The Double-Checkpointed State Model

MONITOR uses two independent but complementary checkpointing mechanisms to ensure that no gameplay progress or world data is lost.

### 1.1 Execution State (LangGraph + MongoDBSaver)
The **execution flow** of a Scene or Story is managed by LangGraph. Each step (node) in the graph is a discrete unit of work.
- **Mechanism:** `MongoDBSaver` checkpointer.
- **What it saves:** The current node in the state machine, internal variables (like `turn_number`), and transient results.
- **Recovery:** Upon restart, the `SceneLoop` or `StoryLoop` rehydrates from the last successful checkpoint based on the `thread_id` (Scene/Story UUID).
- **Time Travel:** This allows for the `/backtrack` command by reverting the graph to a previous successful checkpoint ID.

### 1.2 Narrative State (MongoDB Canonical Store)
The **story content** is persisted immediately as it is generated.
- **Mechanism:** Direct MongoDB writes at the end of each turn (within the `persist_turn_artifacts` node).
- **What it saves:** Turn transcripts, resolution records (dice rolls), and `ProposedChange` documents.
- **Recovery:** The `ContextAssembly` agent rebuilds the "visible" history for the AI GM by querying these records.

---

## 2. Ingestion Job Lifecycle

Document ingestion (PDFs, URLs) is a multi-stage process that can take minutes to complete. We use a job-tracking pattern to ensure reliability.

### Stages of Ingestion
1. **PENDING:** Job record created in MongoDB.
2. **EXTRACTING:** Text being pulled from raw binary via `IngestionPipeline`.
3. **EMBEDDING:** Chunks being converted to vectors by `Indexer`.
4. **ANALYZING:** Knowledge extraction being performed by `Analyzer`.
5. **COMPLETED / FAILED:** Final terminal states.

### Shutdown & Recovery (P-23)
- **Graceful Shutdown:** The UI backend (`packages/ui/backend/src/monitor_ui/main.py`) captures SIGTERM/SIGINT and attempts to mark active jobs as `KILLED` or `CANCELLED`.
- **Startup Audit:** On boot, the system identifies any jobs left in `RUNNING` or `EXTRACTING` states (stale jobs) and marks them as `FAILED` with a "System Interrupted" reason, allowing the user to restart them.

---

## 3. Play Session Rehydration

Web-based play sessions are durable and survive browser refreshes or server restarts.
- **Mechanism:** `chat_sessions` collection in MongoDB.
- **Rehydration:** When a user reconnects, the backend fetches the `chat_session` record, re-instantiates the `SceneLoop` with the saved `thread_id`, and resumes the LangGraph flow from the latest checkpoint.

---

## 4. Durability Matrix

| Component | Primary Store | Durability Boundary | Recovery Mechanism |
|-----------|---------------|---------------------|-------------------|
| **Graph Logic** | Neo4j | Immediate (Write-Through) | ACID Transactions |
| **Play Loop** | MongoDB | Per-Node (Checkpoint) | `MongoDBSaver.rehydrate()` |
| **Narrative** | MongoDB | Per-Turn | Query-based reconstruction |
| **Lore Recal** | Qdrant | Per-Batch | Automatic Re-indexing task |
| **Binary Files** | MinIO | Immediate | Object Versioning (optional) |
| **Config** | PostgreSQL | Immediate | Relational Integrity |

---

## 5. Failure Handling Patterns

- **Agent Failure:** LangGraph nodes catch exceptions. If a node fails, the graph stops, and the error is persisted to the checkpoint. The next run attempt starts from the failed node.
- **Database Connection Loss:** Agents use `tenacity` retries with exponential backoff for database-dependent tool calls.
- **LLM Timeout:** LLM calls are wrapped in retries and circuit breakers to prevent one slow call from hanging the entire loop.
