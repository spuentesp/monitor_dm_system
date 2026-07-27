---
description: "The Ingestion Loop — multi-modal source ingestion into the knowledge base."
tags: [loop, langgraph, ingestion]
layer: 2
---

# Ingestion Loop

**Intent:** Turn a source (text, image, or a live session transcript) into
indexed, analyzed knowledge — chunks in Qdrant + extracted entities/facts as
`ProposedChange`s.

**Source:** `packages/agents/src/monitor_agents/loops/ingestion_loop.py`
(`build_ingestion_graph`). Uses `monitor_agents.indexer` +
`monitor_agents.analyzer`.

## Flow

```
detect_modality → { process_text | process_vision | process_live_session } → …analyze/index
```

- `detect_modality` — route the source to the right processor.
- `process_text` / `process_vision` / `process_live_session` — extract text,
  chunk it, and embed via the
  [RetrievalService](../architecture/RETRIEVAL_SERVICE.md) (the single embed
  owner — index-time and query-time models stay consistent).
- Downstream, the `Analyzer` extracts entities/axioms/lore as `ProposedChange`s
  for CanonKeeper.

## See Also
- [Retrieval Service](../architecture/RETRIEVAL_SERVICE.md) · [Loops Index](./_index.md)
