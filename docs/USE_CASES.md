# MONITOR Use Cases

> Complete use case catalog organized by functional category. **Now split into digestible files by epic.**
>
> For product vision, objectives, and epic definitions, see [`SYSTEM.md`](../SYSTEM.md).

---

## System Overview

**MONITOR** is a narrative intelligence system that operates in three modes:

| Mode | Description |
|------|-------------|
| **World Architect** | Build and maintain fictional worlds from structured/unstructured sources |
| **Autonomous GM** | Run full solo RPG experiences with turn-by-turn narration |
| **GM Assistant** | Support human-led campaigns by recording, tracking, and analyzing |

See [SYSTEM.md](../SYSTEM.md) for core objectives (O1-O5) and epics (EPIC 0-9).

> **Note:** The CLI examples in this file describe the intended user-facing workflow surface. The currently wired command set in the repo may be smaller; `packages/cli/src/monitor_cli/main.py` is the implementation source of truth for what is live today.
>
> **Implementation reality (April 2026):** the live play surface is the web chat API in `packages/ui/backend/src/monitor_ui/routers/chat.py`, which bootstraps sessions and dispatches into `SceneLoop` / `WorldBuildingLoop`. Historical implementation notes that mention an `Orchestrator` should be read as **session bootstrap + LangGraph loops**, not as a monolithic agent class. `monitor play` remains the target CLI UX; `monitor playtest` is the current CLI path for end-to-end autonomous-GM validation.

---

## Use Case Categories

| Category | Code Range | Description | File |
|----------|------------|-------------|------|
| **DATA LAYER** | `DL-1` to `DL-26` | Canonical data access and MCP interfaces | [epic-0-data-layer-DL/](use-cases/epic-0-data-layer-DL/) (YAML definitions) |
| **PLAY** | `P-1` to `P-20` | Core gameplay loop — narration, scenes, actions | [epic-1-world-M/](use-cases/epic-1-world-M/) (YAML definitions) |
| **MANAGE** | `M-1` to `M-35` | World administration — CRUD for all entities | [epic-1-world-M/](use-cases/epic-1-world-M/) (YAML definitions) |
| **QUERY** | `Q-1` to `Q-11` | Canon exploration — search, browse, ask | [epic-3-identity-M/](use-cases/epic-3-identity-M/) (YAML definitions) |
| **INGEST** | `I-1` to `I-13` | Knowledge import — documents, extraction, curation, synthesis | [epic-2-ingestion-I/](use-cases/epic-2-ingestion-I/) (YAML definitions) |
| **SYSTEM** | `SYS-1` to `SYS-12` | App lifecycle, config, session | [epic-11-system.md](use-cases/epic-11-system.md) |
| **CO-PILOT** | `CF-1` to `CF-8` | Human GM assistant features | [epic-7-copilot.md](use-cases/epic-7-copilot.md) |
| **STORY** | `ST-1` to `ST-8` | Planning & meta-narrative tools | [epic-8-story.md](use-cases/epic-8-story.md) |
| **RULES** | `RS-1` to `RS-7` | Game system definition — stats, skills, mechanics | [epic-5-rules.md](use-cases/epic-5-rules.md) |
| **PACKS** | `MP-1` to `MP-9` | Multiverse Packs — compose, apply, share worlds | [epic-10-packs-MP/](use-cases/epic-10-packs-MP/) (YAML definitions) |
| **DOCS** | `DOC-1` | Documentation publishing & governance | [epic-9-docs.md](use-cases/epic-9-docs.md) |

> The catalog evolves over time; see the [rollout plan](use-cases/rollout-plan.md) for the best quick snapshot of current phase planning.

## Testing Expectations

- Every use case implementation must add or update unit tests that cover success and failure paths.
- End-to-end or integration tests should exercise the full flow for cross-layer interactions (e.g., CLI → agents → data-layer) where applicable.
- Pull requests that change code without touching tests should be rejected by automation (see `scripts/require_tests_for_code_changes.py` and CI gate).
- Each change must reference at least one use-case ID (DL-, P-, M-, Q-, I-, SYS-, CF-, ST-, RS-, DOC-) in commits/PR body; CI enforces this.

---

## Quick Navigation

### By Epic

| Epic | Use Cases | File |
|------|-----------|------|
| **Epic 0** — Data Layer | DL-1 to DL-14 | [epic-0-data-layer-DL/](use-cases/epic-0-data-layer-DL/) (YAML definitions) |
| **Epic 1** — Play | P-1 to P-21 | [epic-1-world-M/](use-cases/epic-1-world-M/) (YAML definitions) |
| **Epic 2** — Manage | M-1 to M-35 | [epic-1-world-M/](use-cases/epic-1-world-M/) (YAML definitions) |
| **Epic 3** — Query | Q-1 to Q-11 | [epic-3-identity-M/](use-cases/epic-3-identity-M/) (YAML definitions) |
| **Epic 4** — Ingest | I-1 to I-13 | [epic-2-ingestion-I/](use-cases/epic-2-ingestion-I/) (YAML definitions) |
| **Epic 5** — System | SYS-1 to SYS-12 | [epic-11-system.md](use-cases/epic-11-system.md) |
| **Epic 6** — Co-Pilot | CF-1 to CF-8 | [epic-7-copilot.md](use-cases/epic-7-copilot.md) |
| **Epic 7** — Story | ST-1 to ST-8 | [epic-8-story.md](use-cases/epic-8-story.md) |
| **Epic 8** — Rules | RS-1 to RS-8 | [epic-5-rules.md](use-cases/epic-5-rules.md) |
| **Epic 9** — Docs | DOC-1 | [epic-9-docs.md](use-cases/epic-9-docs.md) |
| **Epic 10** — Packs | MP-1 to MP-9 | [epic-10-packs-MP/](use-cases/epic-10-packs-MP/) (YAML definitions) |

### Companion Documents

- [Data Layer Details](use-cases/data-layer-details.md) — DL-focused companion with inputs/behavior/outputs

### Planning

- [Rollout Plan](use-cases/rollout-plan.md) — MVP, phases, and implementation status
