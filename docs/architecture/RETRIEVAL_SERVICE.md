# RetrievalService — one owner for embeddings, Qdrant, and retrieval

> Status: living document. Last updated 2026-07-17.
> Module: `packages/data-layer/src/monitor_data/retrieval/`

## Why this exists

Embeddings were being called directly from ~12 modules. That caused two
concrete problems:

1. **A live correctness bug.** Every Qdrant collection is 768-dim (built with
   `ollama/nomic-embed-text`). But the active embedding provider (the
   PostgreSQL `llm_providers` row, role `embedding`) had drifted to
   `gemini/gemini-embedding-001`. Querying a nomic index with gemini vectors
   returns garbage — and nothing recorded *which* model built a collection, so
   nothing caught it.
2. **Model choice couldn't be enforced.** With many direct callers, index-time
   and query-time model could silently diverge. A global "pinned model"
   setting everyone reads is fragile; the only way to *guarantee* consistency
   is a single owner that does both index and query.

The fix: an in-process `RetrievalService` in the **data-layer** owns
embeddings + Qdrant + collection lifecycle. Nothing else imports `embed_text`
for retrieval. The embedding model is configurable but pinned; consistency is
by construction.

This also closed the "embeddings have two jobs" problem — see
``docs/architecture/DE_HEURISTIC_PRINCIPLE.md``. Retrieval is the legitimate
job; classification (roll/intent) was deleted, and the remaining schema/
condition matching was demoted onto `RetrievalService.nearest`.

## The boundary

```
   agents/ callers ─────► monitor_data.retrieval.RetrievalService
   (context_assembly,       .index(collection, docs)
    indexer, analyzer,       .retrieve(collection, query, …) ─┐
    action_routing,          .nearest(query, candidates)      │
    tracks_conditions,       .embed_query / .embed_docs        │
    qdrant_tools)                                              ▼
                        HyDE rewrite (LLM) → embed(pinned) →
                        Qdrant vector search → LLM rerank → hits

                        owns: embedding model (configurable, pinned)
                              Qdrant collection lifecycle + dim
                              model/dim guard (fail loud)
                              HyDE + rerank LLM (from llm_providers)
```

Layer-clean: it lives in the data-layer (where embeddings + Qdrant already
live) and calls `litellm` directly for embed + HyDE + rerank — the same way
`db/embeddings.py` already does. No upward import into agents.

## Interface

`monitor_data.retrieval.RetrievalService` (get the singleton via
`default_retrieval_service()`):

| Method | What it does |
|---|---|
| `async embed_query(text) -> list[float]` | Single embed with the pinned model. Fails loud. |
| `async embed_docs(texts) -> list[list[float]]` | Batch embed. Fails loud. |
| `async ensure_collection(collection)` | Create if missing; **hard-fail** on dim mismatch or recorded-model mismatch; warn on missing meta. |
| `async index(collection, docs)` | Embed + upsert + record the model in meta. |
| `async retrieve(collection, query, *, filters, limit, rewrite, rerank) -> list[Hit]` | HyDE → embed → Qdrant nearest → rerank. |
| `async nearest(query, candidates, *, top_k) -> list[Scored]` | In-process cosine over an ad-hoc candidate list (no Qdrant). |
| `async model() -> str` / `async dimension() -> int` | The pinned model + its vector dim. |

Contracts (`retrieval/contracts.py`): `Document(id, text, payload)`,
`Hit(id, score, payload, text)`, `Scored(candidate, index, score)`, and
`EmbeddingModelMismatchError`.

### `retrieve()` vs `nearest()`

- **`retrieve()`** is RAG over a Qdrant collection: (optional HyDE rewrite via
  LLM) → `embed_query` with the pinned model → Qdrant nearest-by-vector →
  (optional LLM rerank) → hits. `rewrite`/`rerank` default to config; pass
  `False` per call on latency-sensitive paths.
- **`nearest()`** is the demoted-classifier primitive: "find the schema skill
  / scenery rule / condition trigger nearest this action", scored in-process
  by cosine over a candidate list. Same pinned model, same space, no Qdrant.
  It preserves original candidate indices so duplicate candidate texts each
  map back to their own slot.

## Configuration & the pin

`RetrievalConfig.resolve()` (`retrieval/config.py`) resolves the embedding
model with this precedence (first wins):

1. `RETRIEVAL_EMBEDDING_MODEL` env var — an explicit override/pin.
2. PostgreSQL `llm_providers` row, role `embedding` (the mechanism
   `embeddings._resolve_embedding_config` already uses).
3. `settings.embedding_model` (env `EMBEDDING_MODEL` / default).

The **dimension** is always `settings.embedding_dimension` (env
`EMBEDDING_DIMENSION`) — the same value that drives `COLLECTION_CONFIGS` in
`db/qdrant.py`, so the collection dimension and the config dimension are
consistent by construction.

HyDE and rerank LLMs are resolved from `llm_providers` by role (default
`light`), overridable via `RETRIEVAL_HYDE_MODEL` / `RETRIEVAL_RERANK_MODEL`.
Toggles: `RETRIEVAL_ENABLE_HYDE`, `RETRIEVAL_ENABLE_RERANK` (both default on).

## Fail-loud vs fail-soft

| Step | Policy | Why |
|---|---|---|
| Embedding (`embed_query`/`embed_docs`) | **Fail loud** (`EmbeddingProviderError`) | A fake/zero vector silently corrupts the index and every downstream query. |
| Model/dim guard (`ensure_collection`) | **Fail loud** (`EmbeddingModelMismatchError`) | This is the guardrail that catches the live gemini-vs-nomic bug. |
| HyDE rewrite | Fail soft → use the raw query | It's a quality enhancement; plain vector search is still correct. |
| LLM rerank | Fail soft → keep vector order | Same — enhancement, not correctness. |

## The model/dim guard

`ensure_collection` enforces three things:

- **(a)** live Qdrant vector size == config dimension → else hard-fail.
- **(b)** a recorded model exists and differs from the active model → hard-fail
  with `EmbeddingModelMismatchError` (the live-bug case).
- **(c)** no recorded model (legacy collection built before this service) →
  warn loudly; the model is recorded on the next deliberate `index()`/reindex.
  We never silently adopt a legacy collection into a model label.

The per-collection meta is stored in `system_config` under
`retrieval_meta:<collection>` as `{"model", "dimension"}`.

## Migrating / fixing the live bug

The guard hard-fails on a model mismatch by design, which forces the fix:

1. Repoint the DB provider row to the model the index was built with (or the
   one you want): `scripts/seed_ollama_embedding_provider.py` sets the
   `llm_providers` role=`embedding` row to `ollama/nomic-embed-text` (768-dim,
   local, unlimited). **Shared-DB write — run by an operator.**
2. Re-embed everything with the pinned model:
   `scripts/reindex_embeddings.py --dry-run` to preview, then `--yes` to
   drop+rebuild each collection and record its model in meta. **Destructive —
   operator-run.**

Do these together: the reindex re-embeds with whatever the pin currently
resolves to, so the provider row must already point at the intended model.

## Consumers

Retrieval + indexing (route through the service):
`context_assembly`, `qdrant_tools` (embed branches), `indexer`,
`analyzer/_core` + `analyzer/_mindscape_projection`, UI `search` router.

Demoted classifiers (`nearest`):
`game_system/_action_routing` (stat/action_type/subsystem),
`game_system/_tracks_conditions` (scenery modifiers + condition triggers).

## Tests

- `packages/data-layer/tests/test_retrieval_service.py` — config precedence,
  guard fail-loud on model + dim mismatch, `nearest` ranking, meta record.
- `packages/data-layer/tests/test_retrieval_retrieve.py` — HyDE → embed →
  search → rerank wiring, per-call toggles (hermetic: embed + LLM mocked).

All hermetic — no live provider. Consumers stub `default_retrieval_service`
(or its `embed_query`/`embed_docs`) in their own tests.
