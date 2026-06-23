## By Epic

| Epic | Use Cases | Priority |
|------|-----------|----------|
| DATA LAYER | DL-1 to DL-26 | Phase 0 (Foundational) |
| PLAY | P-1 to P-17 | Phase 1 (MVP) |
| MANAGE | M-1 to M-35 | Phase 1-2 |
| QUERY | Q-1 to Q-11 | Phase 2 |
| INGEST | I-1 to I-13 | Phase 3 |
| CO-PILOT | CF-1 to CF-8 | Phase 2 |
| STORY | ST-1 to ST-8 | Phase 2-3 |
| RULES | RS-1 to RS-7 | Phase 2 |
| PACKS | MP-1 to MP-9 | Phase 3 |
| SYSTEM | SYS-1 to SYS-12 | Phase 1 |
| DOCS | DOC-1 | Phase 1 |

**Total: 165 use cases** (up from 137)

## New Use Cases (v2.1)

| ID | Name | Description |
|----|------|-------------|
| P-13 | Party Management | Multi-character party with switching, inventory, splits |
| P-14 | Flashback Mode | Play scenes in the past, create historical facts |
| M-31 | Entity Templates | Reusable templates for bulk entity creation |
| M-32 | Manage Archetypes | CRUD for EntityArchetype nodes |
| M-33 | Manage Random Tables | Random table creation and rolling |
| M-34 | World Snapshots | Point-in-time state capture, comparison, restore |
| M-35 | Universe Fork | Create alternate timeline branches from snapshots |
| Q-10 | Audit Trail | Change history, version comparison, revert |
| CF-6 | Generate Player Handouts | Create distributable handouts from world data |
| CF-7 | Session Prep Assistant | Generate prep materials and suggestions for GMs |
| ST-6 | Generate Random Encounters | Context-aware procedural encounter generation |
| ST-7 | Scheduled World Events | Automatic event triggers on time advancement |
| RS-5 | Card-Based Mechanics | Support for card-based RPG resolution systems |
| SYS-11 | Error Recovery | Graceful degradation and service failure handling |
| SYS-12 | Logging & Observability | Structured logging, metrics, and diagnostics |
| Q-11 | World Graph Explorer | Interactive entity-relationship graph for a universe |
| I-7 | Source Library | Browse all uploaded source documents and their pack provenance |
| I-8 | Delete or Reingest Source | Remove a source and derived data, or re-run ingestion |
| I-9 | Curate Pack Items | Reclassify, promote, demote, delete items within a pack |
| I-10 | Link Pack ↔ Source | Associate/disassociate a pack and a source document |
| I-11 | Link Pack ↔ Game System | Explicitly set or change the game system linked to a pack |
| I-12 | Delete Ingest Job | Remove stale, failed, or duplicate ingest job records |
| I-9a | Curate Pack Relationships | Edit, delete, or create relationships between entities within a pack |
| I-13 | Cross-Source Synthesis | Merge duplicate entities from multiple sources into single high-confidence entity |
| RS-6 | Navigate to System from Pack | Deep-link from pack game system chip to /systems |
| RS-7 | System Source Provenance | Show which source PDFs a system was extracted from |
| MP-1 | Create Pack Manually | Author a pack from scratch without a PDF |
| MP-2 | Import Pack from File | Load a shared .monitorpack file into the library |
| MP-3 | Export Pack to File | Serialize a pack to a portable .monitorpack file |
| MP-4 | Pack Editor | Free-form editor for pack contents with World Graph panel |
| MP-5 | Save Pack with Lineage | Save editor state recording parent pack IDs |
| MP-6 | Save as New Pack | Save editor state as fully independent pack |
| MP-7 | Apply Pack → New World | Create Multiverse + Universe from pack contents |
| MP-8 | Apply Pack → Existing World | Selective import or full apply with conflict resolution |
| MP-9 | Delete / Archive Pack | Soft-archive or permanently delete a pack |
| DL-15 | Manage Parties | Neo4j party nodes and membership edges |
| DL-16 | Party Inventory & Splits | MongoDB inventory and split tracking |
| DL-17 | Entity Templates | MongoDB template storage and instantiation |
| DL-18 | Change Log | Event sourcing for audit trail |
| DL-19 | Historical Queries | State reconstruction at any point in time |
| DL-20 | Game Systems & Rules | MongoDB game system definitions |
| DL-21 | Random Tables | MongoDB random table storage |
| DL-22 | Card Deck State | MongoDB card deck state and hand tracking |
| DL-23 | World Snapshots | MongoDB snapshot capture, comparison, restore |
| DL-24 | Turn Resolutions | **CRITICAL** - Dice/card resolution mechanics |
| DL-25 | Combat State | Combat encounter tracking and turn management |
| DL-26 | Character Working State | Scene-scoped stat/resource tracking |
| P-15 | Start Play Session | Play Home flow, PlaySession CRUD, resume recent story |
| P-21 | Autonomous PC Actions | PC-Agent generates character actions (deferred from old P-15; not yet implemented) |
| P-16 | Combat Encounter Management | Full combat loop with initiative and rounds |
| P-17 | Social Encounter Management | NPC interaction with disposition tracking |
| ST-8 | Automatic Story Planning | Story Planner generates outline and beats |

## MVP (Phase 1)

Core gameplay loop:
- SYS-1, SYS-2, SYS-3 (app lifecycle)
- M-4, M-5 (create/list universe)
- P-1, P-2, P-3, P-4, P-8 (story, scene, turn, action, canonize)
- P-9 (dice rolls)
- **P-13 (party management)** ← NEW: Critical for solo play
- M-12, M-13 (create entities, characters)
- **M-31 (entity templates)** ← NEW: Major productivity gain

## Phase 0

Data layer foundation:
- DL-1 to DL-14 (core data access MCP tools, auth/validation, indices)
- **DL-15 to DL-26** ← NEW: Party, templates, audit trail, game systems, cards, snapshots, **resolutions, combat, working state**
- Tasks:
  - Create Pydantic schemas for all DL objects (universes, entities, axioms, facts/events, relationships/state tags, stories/scenes/turns, proposed changes, story outlines/plot threads, memories, sources/documents/snippets/ingest proposals, binaries, embeddings, search docs, **parties, templates, change_log, game_systems, random_tables, card_decks, deck_states, world_snapshots, resolutions, combat_encounters, character_working_state**).
  - Implement DB clients (Neo4j, MongoDB, Qdrant, MinIO, OpenSearch) and health checks.
  - Implement MCP tools for each DL use case with auth/validation middleware.
  - **Implement change_log middleware for automatic audit capture.**
  - Docker/dev setup: ensure infra/docker-compose is runnable; add sample .env for services.
  - Provide template/parent files agents can copy (one schema/tool pattern per store) to accelerate implementation.
  - Data-layer perspectives are detailed in [data-layer-details.md](data-layer-details.md).

## Phase 2

Management, query, and rules:
- M-* (all entity CRUD)
- **M-32, M-33** ← NEW: Archetypes, random tables
- **M-34, M-35** ← NEW: World snapshots, universe fork
- Q-1 to Q-11 (search, exploration, history, **world graph**)
- P-10, P-11 (combat, conversation modes)
- **P-14** ← NEW: Flashback mode
- CF-1 to CF-5 (co-pilot features)
- **CF-6, CF-7** ← NEW: Player handouts, session prep
- RS-1 to RS-7 (rules systems, **system navigation**)
- **RS-5** ← NEW: Card-based mechanics

## Phase 3

Ingestion, source management, and packs:
- I-1 to I-13 (full ingestion pipeline + source library + pack curation + cross-source synthesis)
- MP-1 to MP-9 (multiverse packs — compose, apply, share)
- ST-1 to ST-5 (story planning tools)
- **ST-6, ST-7** ← NEW: Random encounters, scheduled events

## Phase 4

Polish & observability:
- SYS-7, SYS-8, SYS-9, SYS-10 (export/import, backup verify, retention)
- **SYS-11, SYS-12** ← NEW: Error recovery, logging/observability
- Advanced gameplay features

---

# Layer Mapping

| Use Case | CLI (L3) | Agents (L2) | Data (L1) |
|----------|----------|-------------|-----------|
| P-3 Turn | web chat / future repl | SceneLoop, Narrator, Resolver | all tools |
| P-4 Action | handlers | Resolver | mongodb, neo4j |
| P-8 Canonize | handlers | CanonKeeper, Indexer | neo4j, qdrant |
| P-9 Dice | handlers | Resolver | - |
| **P-13 Party** | session setup / meta-controls | session bootstrap + SceneLoop context | neo4j, mongodb |
| **P-14 Flashback** | repl/meta-commands | Story/Scene orchestration, Narrator | neo4j, mongodb |
| M-4 Create Universe | commands/manage | - | neo4j_tools |
| M-13 Create Character | commands/manage | - | neo4j, mongodb |
| **M-31 Templates** | commands/manage | planned manage flow (no live monolithic orchestrator) | mongodb, neo4j |
| **M-32 Archetypes** | commands/manage | - | neo4j |
| **M-34 Snapshots** | commands/manage | CanonKeeper | mongodb, neo4j |
| **M-35 Fork** | commands/manage | CanonKeeper | neo4j |
| Q-1 Search | commands/query | ContextAssembly | qdrant, neo4j |
| **Q-10 History** | commands/query | ContextAssembly | mongodb (change_log) |
| I-1 Upload | commands/ingest | Indexer | minio, mongodb, qdrant |
| **CF-6 Handouts** | commands/copilot | Narrator | mongodb, neo4j |
| **CF-7 Session Prep** | commands/copilot | Narrator, ContextAssembly | all tools |
| **ST-6 Encounters** | commands/story, repl | Narrator, Resolver | mongodb, neo4j |
| **ST-7 Scheduled Events** | automatic, commands/story | story/scene orchestration + CanonKeeper | neo4j |
| **RS-5 Cards** | repl, commands/rules | Resolver | mongodb |
| **RS-6 System Link** | ui only | — | — |
| **RS-7 Provenance** | ui + commands/query | ContextAssembly | mongodb, neo4j |
| **Q-11 World Graph** | commands/query, ui | ContextAssembly | neo4j |
| **MP-4 Pack Editor** | ui | — | mongodb |
| **MP-7 Apply New World** | commands/packs | PackApplicator, CanonKeeper | neo4j, mongodb |
| **MP-8 Apply Existing** | commands/packs, ui | PackApplicator, CanonKeeper | neo4j, mongodb |
| **SYS-11 Recovery** | automatic | all agents | all tools |
| **SYS-12 Logging** | automatic | all agents | — |

---

# References

- **Architecture:** `ARCHITECTURE.md`
- **Data Model:** `docs/ontology/ONTOLOGY.md`
- **Agents:** `docs/architecture/AGENT_ORCHESTRATION.md`
- **Loops:** `docs/architecture/CONVERSATIONAL_LOOPS.md`
- **Implementation:** `packages/*/IMPLEMENTATION.md`
