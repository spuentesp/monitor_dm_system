# MONITOR Documentation Map

This directory is organized around a **small set of canonical sources** plus supporting design references.

---

## Canonical Sources of Truth

| Document | Owns |
|----------|------|
| [`../SYSTEM.md`](../SYSTEM.md) | Product vision, modes, objectives, epics |
| [`../STRUCTURE.md`](../STRUCTURE.md) | Repo layout and folder ownership |
| [`../ARCHITECTURE.md`](../ARCHITECTURE.md) | Layer boundaries and dependency rules |
| [`USE_CASES.md`](USE_CASES.md) | Use-case catalog and workflow targets |
| [`AI_DOCS.md`](AI_DOCS.md) | Contributor and agent quick navigation |

> Prefer linking to these documents instead of repeating the same explanation in multiple places.

---

## `docs/` Layout

| Area | Purpose | Status |
|------|---------|--------|
| [`architecture/`](architecture/) | Current design references and subsystem contracts | Active |
| [`architecture/futures/`](architecture/futures/) | RAG research plans (MiA-RAG, SitEmb, CatRAG) | Active — Phase 1 partially implemented |
| [`superpowers/`](superpowers/) | Implementation plans and design specs for major features | Active |
| [`ontology/`](ontology/) | Data model and taxonomy definitions | Active |
| [`use-cases/`](use-cases/) | Structured YAML use-case definitions used by automation | Supporting source |
| [`gameplay-examples/`](gameplay-examples/) | Example play patterns and inspiration | Reference only |
| [`archive/`](archive/) | Historical plans, audits, and superseded writeups | Non-canonical |

---

## Where New Docs Should Go

| If the document is about... | Put it in... |
|-----------------------------|--------------|
| Product goals or modes | `SYSTEM.md` |
| Repo/folder ownership | `STRUCTURE.md` |
| Cross-layer rules or runtime boundaries | `ARCHITECTURE.md` or `docs/architecture/` |
| Future RAG/retrieval research plans | `docs/architecture/futures/` |
| Implementation plans and design specs | `docs/superpowers/plans/` and `docs/superpowers/specs/` |
| Data model or schema meaning | `docs/ontology/` |
| Use-case definitions for humans | `docs/USE_CASES.md` |
| Structured use-case metadata for automation | `docs/use-cases/` |
| Historical planning or audits | `docs/archive/` |

---

## Useful Standalone References

| Document | Purpose |
|----------|---------|
| [`data-layer-details.md`](use-cases/data-layer-details.md) | Storage-focused DL appendix |
| [`GM_CRAFT.md`](GM_CRAFT.md) | Play-surface tone, pacing, and GM-style guidance |
| [`architecture/futures/HYBRID_MINDSCAPE_AND_TRAVERSAL_PLAN.md`](architecture/futures/HYBRID_MINDSCAPE_AND_TRAVERSAL_PLAN.md) | Master plan combining three RAG retrieval strategies |
| [`architecture/futures/INGESTION_FIRST_CONTEXTUAL_RETRIEVAL_PLAN.md`](architecture/futures/INGESTION_FIRST_CONTEXTUAL_RETRIEVAL_PLAN.md) | Recommended rollout order for contextual retrieval |
| [`architecture/futures/MINDSCAPE_AWARE_INGESTION_IMPLEMENTATION_PLAN.md`](architecture/futures/MINDSCAPE_AWARE_INGESTION_IMPLEMENTATION_PLAN.md) | Mindscape-aware long-text ingestion (✅ partially implemented) |
| [`architecture/futures/SITUATED_CONVERSATIONAL_RETRIEVAL_IMPLEMENTATION_PLAN.md`](architecture/futures/SITUATED_CONVERSATIONAL_RETRIEVAL_IMPLEMENTATION_PLAN.md) | Situated conversational and transcript retrieval (not started) |
| [`architecture/futures/QUERY_AWARE_TRAVERSAL_IMPLEMENTATION_PLAN.md`](architecture/futures/QUERY_AWARE_TRAVERSAL_IMPLEMENTATION_PLAN.md) | Typed, query-aware graph traversal (not started) |

---

## Documentation Hygiene Rules

- Keep **runtime reality** separate from **target UX**.
- Prefer **short summaries + links** over duplicate long explanations.
- If a doc becomes obsolete but still has historical value, move it to `docs/archive/`.
- If a file is redundant and adds no value, delete it.
- Update this index when the documentation structure changes.
