# MONITOR — Library Evaluation & Dependency Plan

> **Document type:** architecture decision record + implementation plan
> **Date:** 2026-04-03
> **Scope:** All three layers — data-layer, agents, cli
>
> **Planning-note status:** dependency and library-evaluation reference. Verify the live dependency surface in `packages/*/pyproject.toml`, `ARCHITECTURE.md`, and the current code under `packages/` before treating any recommendation here as already implemented.

---

## 0. Current State (Summary)

| Layer | Package | Key Current Deps |
|-------|---------|-----------------|
| L1: data-layer | monitor-data-layer | neo4j, pymongo, qdrant-client, minio, opensearch-py, mcp, fastapi, pydantic |
| L2: agents | monitor-agents | anthropic, asyncio-throttle, structlog |
| L3: cli | monitor-cli | typer, rich, prompt-toolkit |

**Critical gaps identified:** async DB drivers, structured LLM output, document ingestion, embeddings, retry logic, observability.

---

## 1. Library Decisions (Evaluated)

### 1.1 LangGraph — ADOPT

**Verdict: Adopt. Implement the runtime loops as LangGraph StateGraphs.**

The nested loops (Main → Story → Scene → Turn) are state machines — LangGraph is literally
a state machine framework for multi-actor LLM applications. The loops directory is completely
unimplemented (all commented out), which means we build with LangGraph from scratch rather
than migrate.

Why this fits:
- The Scene Loop (load_context → resolve → narrate → canonize) maps directly to a `StateGraph` with typed state
- LangGraph's `MongoDBSaver` checkpointer persists graph state to MongoDB — which is exactly where the architecture already puts loop state
- Loop progress survives crashes and can be resumed mid-scene (critical for long sessions)
- LangGraph Studio provides visual inspection of loop execution — good for a public project
- Industry-standard graph orchestration that contributors will recognize

Key fit with MONITOR's architecture:
- LangGraph nodes are just async Python functions — they can call MCP tools, use DSPy modules, or call Anthropic directly, with no lock-in to LangChain chains
- You do NOT need `langchain-anthropic` — nodes use the raw `anthropic` SDK
- MongoDB checkpointing maps cleanly to the existing `scenes`/loop-state MongoDB role

**New dependencies in agents layer:**
```
langgraph>=0.2
langgraph-checkpoint-mongodb>=0.1
```

---

### 1.2 DSPy — ADOPT

**Verdict: Adopt. Implement agent prompt modules as DSPy Signatures.**

The `prompts/` directory is completely unimplemented (all commented out). DSPy Signatures
and Modules would be the implementation — not a migration, a fresh build.

Why this fits:
- DSPy `Signature` defines the typed interface of each agent call (inputs → outputs) declaratively — this is cleaner than raw string templates and documents agent intent precisely
- `dspy.ChainOfThought` adds structured reasoning before output — better for CanonKeeper's policy evaluation and Narrator's creative generation
- Works natively with Anthropic: `dspy.LM("anthropic/claude-opus-4-6")`
- When you have session data, DSPy's optimizers (MIPROv2, BootstrapFewShot) can improve prompt quality automatically — without rewriting code
- Public repos using DSPy signal ML sophistication to contributors

**DSPy vs instructor — they serve different needs, use both:**

| Need | Use |
|------|-----|
| Declarative prompt interface + reasoning chain | DSPy `ChainOfThought` |
| Strict Pydantic model enforcement (retry until valid) | `instructor` |
| Prompt optimization with session data | DSPy optimizers |

Split: Narrator and ContextAssembly use DSPy (creative/retrieval quality).
CanonVerdict and ResolverOutcome use `instructor` (strict schema enforcement, no partial results accepted).

**New dependency in agents layer:**
```
dspy-ai>=2.5
```

---

### 1.3 Async Database Drivers — CRITICAL, ADOPT NOW

**Verdict: Required. The current stack is blocking.**

`pymongo` is synchronous. The Scene Loop runs ≥ 1 DB read per turn; a blocking call kills the < 2s turn latency target. Every other driver already supports async — pymongo is the outlier.

| Driver | Current | Replace With | Notes |
|--------|---------|-------------|-------|
| MongoDB | `pymongo>=4.6` | `motor>=3.3` | Drop-in async pymongo, same API surface |
| Neo4j | `neo4j>=5.15` | same | Use `AsyncGraphDatabase.driver()` (built-in) |
| Qdrant | `qdrant-client>=1.7` | same | Use `AsyncQdrantClient` (built-in) |
| MinIO | `minio>=7.2` | `aiobotocore>=2.7` | MinIO SDK has no async; aiobotocore wraps S3-compatible APIs |
| OpenSearch | `opensearch-py>=2.4` | same | Has async transport; use `AsyncOpenSearch` client |

---

### 1.4 Structured LLM Output — CRITICAL, ADOPT NOW

**Verdict: Adopt `instructor`.**

CanonKeeper evaluates ProposedChange objects. Resolver outputs structured resolution records. Narrator optionally extracts proposals from narrative text. All of these require the LLM to return valid Pydantic models, not free text.

`instructor>=1.0` wraps the Anthropic (and OpenAI) client to enforce structured output via tool_use, with automatic retries on validation failure. It pairs directly with the Pydantic models already defined in data-layer.

```python
# Example (agents layer)
import instructor
from anthropic import Anthropic
from monitor_data.schemas.proposals import ProposedChange

client = instructor.from_anthropic(Anthropic())

proposals = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    response_model=list[ProposedChange],
    messages=[{"role": "user", "content": prompt}],
)
# proposals is already a list[ProposedChange] — validated, typed
```

**Lives in:** `packages/agents/` (Layer 2)

---

### 1.5 Retry Logic — ADOPT NOW

**Verdict: Adopt `tenacity>=8.2`.**

LLM calls can fail transiently (rate limits, network). DB writes can fail transiently (connection pool exhaustion). Rolling retry logic per-call is noisy. `tenacity` provides composable decorators:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(anthropic.RateLimitError),
)
async def call_llm(prompt: str) -> str: ...
```

`instructor` already includes some retry support for validation errors; `tenacity` covers the transport layer.

**Lives in:** both `packages/data-layer/` (DB ops) and `packages/agents/` (LLM calls)

---

### 1.6 Embeddings — ADOPT NOW

**Verdict: Add `litellm>=1.0` to data-layer.**

The current stack references "1536 dims, OpenAI" for Qdrant vectors but has no embedding library. The Indexer agent needs to generate these. `text-embedding-3-small` (1536 dims, OpenAI) is the default model via LiteLLM.

Using LiteLLM instead of the OpenAI SDK directly provides provider flexibility — embedding model can be swapped to Cohere, Mistral, or a local model by changing `EMBEDDING_MODEL` in `.env` only, with no code changes.

**Lives in:** `packages/data-layer/db/embeddings.py` — `embed_text()` and `embed_batch()` async helpers.

---

### 1.7 Document Ingestion — ADOPT NOW (for EPIC 2)

**Verdict: Add `pymupdf` + `tiktoken`.**

For ingesting PDFs and session transcripts (EPIC 2, I-1 to I-6):

| Library | Purpose | Verdict |
|---------|---------|---------|
| `pymupdf>=1.24` (fitz) | PDF text extraction | Adopt — fastest, handles complex layouts |
| `tiktoken>=0.7` | Token counting for chunking | Adopt — needed to split docs into Qdrant-sized chunks |
| `langchain-text-splitters` | Standalone text chunking | Optional — RecursiveCharacterTextSplitter is good, but you can implement simple chunking yourself |

**Lives in:** `packages/data-layer/` — ingest tools are data-layer MCP tools.

---

### 1.8 Configuration — ADOPT NOW

**Verdict: Replace `python-dotenv` with `pydantic-settings>=2.2`.**

`pydantic-settings` reads `.env` files AND environment variables, validates them as a Pydantic model, and provides type-safe access. It includes `python-dotenv` under the hood.

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_password: str
    mongodb_uri: str = "mongodb://localhost:27017"
    openai_api_key: str
    anthropic_api_key: str

    model_config = {"env_file": ".env"}

settings = Settings()
```

**Lives in:** `packages/data-layer/` — single settings module, re-exported upward.

---

### 1.9 Observability — ADOPT SOON

**Verdict: Add `logfire>=0.30` to agents layer.**

`logfire` is Pydantic's observability platform. It auto-instruments Pydantic models, asyncio, HTTPX, and has first-class support for LLM tracing. For a system with 7 agents, 4 nested loops, and 5 databases, you need distributed tracing to debug latency.

Alternative: `opentelemetry-sdk` if you need vendor-neutral OTEL traces. More setup, more portable.

`structlog` is already included — keep it for structured JSON logs in production. `logfire` handles span-level tracing.

**Lives in:** `packages/agents/` (instrumented at agent base class level).

---

### 1.10 Testing Infrastructure — ADOPT SOON

**Verdict: Add `pytest-mock` + `testcontainers`.**

| Library | Purpose |
|---------|---------|
| `pytest-mock>=3.12` | Mock MCP tool responses in agent unit tests |
| `testcontainers>=4.0` | Spin up real Neo4j/MongoDB/Qdrant in integration tests |

The ARCHITECTURE.md states each layer should be testable in isolation. `testcontainers` makes it possible to run real DB tests in CI without a persistent database.

---

## 2. Recommended Dependency Changes

### 2.1 packages/data-layer/pyproject.toml

```toml
dependencies = [
    # Database clients (ASYNC)
    "neo4j>=5.15",           # AsyncGraphDatabase built-in
    "motor>=3.3",            # REPLACES pymongo — async MongoDB driver
    "qdrant-client>=1.7",    # AsyncQdrantClient built-in
    "aiobotocore>=2.7",      # REPLACES minio SDK for async S3/MinIO
    "opensearch-py>=2.4",    # AsyncOpenSearch built-in

    # MCP and API
    "mcp[cli]>=1.2.0",
    "anthropic>=0.39",
    "fastapi>=0.108",
    "uvicorn>=0.25",

    # Data validation + config
    "pydantic>=2.5",
    "pydantic-settings>=2.2",  # NEW: type-safe settings

    # Embeddings (provider-agnostic via LiteLLM)
    "litellm>=1.0",            # text-embedding-3-small or any provider via EMBEDDING_MODEL env

    # Document ingestion
    "pymupdf>=1.24",           # NEW: PDF parsing (fitz)
    "tiktoken>=0.7",           # NEW: token counting for chunking

    # Reliability
    "tenacity>=8.2",           # NEW: retry logic for DB ops
]
```

### 2.2 packages/agents/pyproject.toml

```toml
dependencies = [
    "monitor-data-layer",

    # LLM
    "anthropic>=0.39",
    "instructor>=1.0",              # NEW: strict Pydantic output (CanonVerdict, ResolverOutcome)

    # Orchestration
    "langgraph>=0.2",               # NEW: loop state machines (Main/Story/Scene/Turn)
    "langgraph-checkpoint-mongodb>=0.1",  # NEW: MongoDB checkpointing for loop state

    # Prompt programming
    "dspy-ai>=2.5",                 # NEW: declarative agent signatures + prompt optimization

    # Async
    "anyio>=4.0",                   # NEW: better async primitives than raw asyncio
    "asyncio-throttle>=1.0",

    # Reliability
    "tenacity>=8.2",                # NEW: LLM call retry

    # Observability
    "structlog>=23.2",
    "logfire>=0.30",                # NEW: distributed tracing for agent loops
]
```

### 2.3 packages/cli/pyproject.toml

No changes needed. The CLI layer is already well-specified.

---

## 3. What NOT to Adopt (and Why)

| Library | Reason to Skip |
|---------|---------------|
| **LangChain** | Opinionated toolkit that duplicates MCP, Pydantic, and the custom loop model — use LangGraph standalone instead |
| **LlamaIndex** | Useful for RAG pipelines, but MONITOR's retrieval is Qdrant + Neo4j via MCP — no need for a third retrieval abstraction |
| **Celery** | Overkill for background Indexer tasks — asyncio task groups are sufficient |
| **Redis** | The AGENT_ORCHESTRATION.md lists event bus as "optional for loose coupling" — defer until you actually need distributed deployment |
| **SQLAlchemy** | No SQL databases in this stack |
| **Haystack** | Another full RAG framework — overlaps with the data-layer's responsibility |

---

## 4. Implementation Plan

### Phase 1 — Foundation (Do First)

These are blockers for correct async behavior. Do before writing any agent logic.

- [x] **DL-A1:** Replace `pymongo` with `motor` in data-layer DB client (`db/mongodb.py`)
- [x] **DL-A2:** Switch Neo4j client to `AsyncGraphDatabase` (`db/neo4j.py`)
- [x] **DL-A3:** Switch Qdrant client to `AsyncQdrantClient` (`db/qdrant.py`)
- [x] **DL-A4:** Replace minio SDK with `aiobotocore` (`db/minio.py`)
- [x] **DL-A5:** Add `pydantic-settings` — create `monitor_data/config.py` as single settings source
- [x] **DL-A6:** Add `tenacity` retry decorators to all DB client methods

### Phase 2 — Agent Quality (Do Second)

These enable correct structured output from LLM calls and the loop orchestration layer.

- [x] **AG-A1:** Add `instructor` to agents — wrap Anthropic client in `base.py`
- [x] **AG-A2:** Add `tenacity` to all `call_llm()` paths with exponential backoff
- [x] **AG-A3:** Define structured response models for each agent in `monitor_data/schemas/`
  - `NarratorResponse` (text + optional proposals)
  - `ResolverOutcome` (success, roll, effects, proposals)
  - `CanonKeeperVerdict` (accepted/rejected with reasoning)
- [x] **AG-A4:** Add `logfire` instrumentation to `BaseAgent` — trace every agent call
- [x] **AG-A5:** Implement all 4 loops as LangGraph `StateGraph` in `loops/`
- [x] **AG-A6:** Configure LangGraph `MongoDBSaver` checkpointer for loop state persistence
- [x] **AG-A7:** Implement DSPy modules in `prompts/` — Narrator, CanonKeeper, ContextAssembly signatures

### Phase 3 — Embeddings & Ingestion (Do Third)

These unlock EPIC 2 (Knowledge Ingestion) and the Indexer agent.

- [x] **DL-B1:** Add `litellm` to data-layer — create `db/embeddings.py` with `embed_text()`/`embed_batch()` (provider-agnostic)
- [x] **DL-B2:** Add `pymupdf` — create `tools/ingest_tools.py` with PDF-to-text extraction via `fitz`
- [x] **DL-B3:** Add `tiktoken` — implement chunking strategy (≤ 512 tokens, 10% overlap)
- [x] **DL-B4:** Wire Indexer agent to embeddings tool via MCP

### Phase 4 — Testing & Observability (Do Alongside)

- [x] **TEST-1:** Add `testcontainers` fixtures for Neo4j + MongoDB in `conftest.py`
- [x] **TEST-2:** Add `pytest-mock` to all layers dev deps
- [x] **TEST-3:** Write integration tests for the canonization gate (Scene finalize flow)
- [x] **OBS-1:** `logfire` instrumented in `BaseAgent` — spans on every `call_llm_structured()` and `call_tool()` call

---

## 5. Dependency Rationale Summary

| Need | Library | Why This One |
|------|---------|-------------|
| Async MongoDB | `motor` | Official async pymongo driver, same API, Motor 3.x is stable |
| Async Neo4j | built-in `AsyncGraphDatabase` | No extra dep, official driver |
| Structured LLM output | `instructor` | Native Pydantic, works with Anthropic tool_use, retries on validation failure |
| PDF parsing | `pymupdf` (fitz) | 10x faster than pypdf2, handles multi-column, tables, embedded images |
| Token chunking | `tiktoken` | Official OpenAI tokenizer — accurate for embedding model budget |
| Embeddings | `litellm` | Provider-agnostic; swap model via EMBEDDING_MODEL env var, no code changes |
| Settings | `pydantic-settings` | Validates env at startup instead of at runtime, eliminates KeyError bugs |
| Retries | `tenacity` | Composable decorators, handles both sync and async |
| Tracing | `logfire` | First-class Pydantic + asyncio + Anthropic integration |

---

## 6. Open Questions

All open questions are resolved and implemented:

1. **LiteLLM for embeddings** ✅ — `litellm>=1.0` adopted. `embed_text()` / `embed_batch()` in `db/embeddings.py`. Swap providers via `EMBEDDING_MODEL` env var only.

2. **Maintain OpenSearch** ✅ — Both Qdrant (semantic) and OpenSearch (keyword/BM25) retained. Dual-search provides hybrid retrieval for the ContextAssembly agent.

3. **aiobotocore for MinIO/S3** ✅ — `aiobotocore>=2.7` adopted in `db/minio.py`. Works unchanged on MinIO locally and S3 in production.

4. **anyio** ✅ — `anyio>=4.0` added to agents layer. Provides better task group primitives than raw asyncio and Trio compatibility.
