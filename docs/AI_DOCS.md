# MONITOR - AI Agent Reference

*Concise reference for AI agents working on the MONITOR codebase.*

> **FIRST:** Read `SYSTEM.md`, `STRUCTURE.md`, `ARCHITECTURE.md`, and `CLAUDE.md` at the repo root.

---

## Monorepo Structure (CRITICAL)

```text
<repo-root>/
├── SYSTEM.md            ← Product vision and goals
├── STRUCTURE.md         ← Folder ownership and layout
├── ARCHITECTURE.md      ← Layer rules
├── CLAUDE.md            ← AI instructions
├── docs/                # Canonical documentation
├── infra/               # Docker infrastructure
├── packages/            # Core layers + user-facing surfaces
│   ├── data-layer/      # Layer 1: MCP Server + DB clients
│   ├── agents/          # Layer 2: AI Agents
│   ├── cli/             # Layer 3: Terminal interface
│   └── ui/              # Browser-facing backend/frontend
└── scripts/             # Dev utilities
```

### Layer Dependency Rules

```
┌─────────────────────────────┐
│  Layer 3: CLI               │  packages/cli/
│  Depends on: agents ONLY    │
└──────────────┬──────────────┘
               │ imports
               ▼
┌─────────────────────────────┐
│  Layer 2: AGENTS            │  packages/agents/
│  Depends on: data-layer     │
└──────────────┬──────────────┘
               │ imports
               ▼
┌─────────────────────────────┐
│  Layer 1: DATA-LAYER        │  packages/data-layer/
│  Depends on: external only  │
└─────────────────────────────┘
```

**RULES:**
1. Dependencies flow DOWNWARD only
2. No skip-layer imports (CLI cannot import data-layer directly)
3. Each layer has its own `pyproject.toml`

---

## Purpose of This File

This is a **quick navigation reference** for contributors and AI agents. It is not the full system specification.

---

## Canonical Docs to Trust

| Document | Use it for |
|----------|------------|
| `SYSTEM.md` | Product vision, modes, objectives |
| `STRUCTURE.md` | Repo layout and folder ownership |
| `ARCHITECTURE.md` | Layer boundaries and allowed dependencies |
| `docs/README.md` | Documentation map and placement rules |
| `docs/USE_CASES.md` | Current use-case catalog and target UX |
| `docs/architecture/*` | Active subsystem design references |
| `docs/ontology/*` | Data model and taxonomy definitions |

---

## Verified Runtime Surfaces (April 2026)

- **Interactive play:** `packages/ui/backend/src/monitor_ui/routers/chat.py`
- **Current CLI commands:** `state`, `rules`, `mechanics`, `ingest`, `playtest`
- **Live MCP registry:** `monitor_data.server` auto-discovers `neo4j_*`, `mongodb_*`, `qdrant_*`, and `ingest_*`

> `packages/cli/src/monitor_cli/main.py` is the source of truth for the currently wired CLI surface.

---

## Critical Invariants

1. **CanonKeeper is the only Neo4j writer** — including thin mechanic reference nodes (`:AbilitySystem`, `:Track`, `:Condition`)
2. **Scenes are the primary canonization boundary**
3. **Qdrant is derived index data, never the source of truth**
4. **Layer boundaries are strict:** `cli → agents → data-layer`
5. **Historical planning notes belong in `docs/archive/` and are non-canonical**
6. **DSPy 3.1.3:** `TypedChainOfThought` does not exist; standard `ChainOfThought` handles typed list output fields natively
7. **Ingestion uses three passes:** PDF structure extraction → LLM section categorization + mindscape synthesis → typed DSPy extraction

---

## Ingestion Pipeline (post-revamp, April 2026)

The pipeline is implemented across three layers:

| Stage | Layer | Key files |
|-------|-------|-----------|
| PDF structure extraction | data-layer | `ingest_tools.py` (`extract_pdf_structure()`, `SectionBlock`) |
| 1024-token chunking (rulebooks) | data-layer | `ingest_tools.py` (`chunk_text(is_rulebook=True)`) |
| Section categorization | agents | `prompts/analyzer.py` (`SectionCategorizationSignature`) |
| Section + source mindscape synthesis | agents | `prompts/analyzer.py` + `utils/analyzer_support.py` |
| Typed extraction (entities, rules, mechanics) | agents | `prompts/analyzer.py` (all signatures use typed Pydantic output fields) |
| Mechanic schemas | data-layer | `schemas/game_systems.py` (`TrackDefinition`, `TieredAbilitySystem`, `ResolutionMechanic`, etc.) |
| Mindscape artifacts | data-layer | `schemas/knowledge_packs.py` (`ChunkSummaryArtifact`, `SectionSummaryArtifact`, `SourceMindscapeArtifact`) |
| Thin mechanic nodes in Neo4j | data-layer | `tools/neo4j_tools/mechanics.py` |
| CanonKeeper mechanic writes | agents | `canonkeeper.py` (`apply_pack_to_universe()`) |

> Design spec: `docs/superpowers/specs/2026-04-13-ingestion-revamp-design.md`
> Future retrieval plans: `docs/architecture/futures/`

---

## Common Change Locations

| If you need to change... | Start here |
|--------------------------|------------|
| Data-layer tools or schemas | `packages/data-layer/src/monitor_data/` |
| Agent logic or loops | `packages/agents/src/monitor_agents/` |
| CLI command wiring | `packages/cli/src/monitor_cli/` |
| Web play/chat behavior | `packages/ui/backend/src/monitor_ui/routers/chat.py` |
| Documentation structure | `docs/README.md` + the canonical root docs |

---

## Documentation Hygiene

- Prefer **linking** to canonical docs over copying the same explanation.
- Keep **target workflows** and **live repo reality** clearly separated.
- Archive stale planning snapshots under `docs/archive/`.
- Delete docs that are redundant and add no useful context.

---

## Fast Reading Order

1. `SYSTEM.md`
2. `STRUCTURE.md`
3. `ARCHITECTURE.md`
4. `docs/README.md`
5. The specific subsystem doc you are modifying

