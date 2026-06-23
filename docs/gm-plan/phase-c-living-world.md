## Phase C — Living World (2 weeks)

> **Delivers:** World that evolves between sessions. Relationships between entities. Autonomous events.

### C.1 World Architect Relationship Extraction

**Why:** WorldArchitect extracts entities and facts but not relationships BETWEEN them. "The King" and "The Princess" are both entities, but "The King is the Princess's father" is a relationship that currently gets lost.

| Task | File(s) | Details |
|------|---------|---------|
| Relationship extraction | `world_architect.py` | New DSPy module `RelationshipExtractionModule` that runs after entity extraction. Input: extracted entities + user text. Output: `List[Relationship]` where `Relationship = (source_id, target_id, rel_type, description, confidence)` |
| Relationship proposal format | `schemas/facts.py` | Extend `ProposedChange` to support `change_type: "create_relationship"` with fields: `source_entity, target_entity, relationship_type, description` |
| CanonKeeper relationship commit | `canonkeeper.py` | Handle `create_relationship` proposals. Create Neo4j edge between entities: `(:Entity)-[:RELATES_TO {type, description}]->(:Entity)` |
| Semantic conflict detection | `world_architect.py` | Before proposing new entity, check if similar entity exists via Qdrant embedding search. If similarity > 0.85, ask user for disambiguation. Prevents "Dragon" and "Drake" being separate when user means the same thing |

**Success criteria:**
- [ ] "The King rules the Kingdom" creates Entity(King) RELATES_TO Entity(Kingdom) with type="rules"
- [ ] Duplicate entities detected and flagged before creation
- [ ] Relationships are queryable in Neo4j for context assembly

### C.2 Autonomous World Evolution

**Why:** Between sessions, the world should evolve. Factions act, NPCs pursue goals, consequences cascade.

| Task | File(s) | Details |
|------|---------|---------|
| World tick system | `agents/world_tick.py` (NEW) | `WorldTick` agent that runs between sessions. Input: current world state (entities, relationships, unresolved threads). Output: proposed changes (NPC moved, faction gained power, rumor spread) |
| Faction AI | `agents/faction_ai.py` (NEW) | Simple faction behavior model. Each faction has: goals, resources, disposition toward other factions. Per tick: evaluate goals, execute one action toward highest-priority goal, update resources |
| Cascading consequences | `world_tick.py` | When a world event fires (e.g., "Kingdom attacks border"), check consequences: affected factions, displaced NPCs, new rumors. Generate downstream proposals |
| Tick scheduler | CLI or cron | Command `monitor world-tick` that runs WorldTick for a given universe. Or: UI endpoint that triggers tick on demand |
| Tick integration with CanonKeeper | `world_tick.py` | WorldTick proposals go through CanonKeeper same as session proposals. Ensures consistency |

**Success criteria:**
- [ ] `monitor world-tick` generates world events between sessions
- [ ] Factions pursue goals autonomously
- [ ] Consequences cascade (war → refugees → faction change)
- [ ] All changes go through CanonKeeper validation

### C.3 Ingestion → Auto World Building

**Why:** After ingesting a source PDF, entities and facts exist but aren't connected into a coherent world.

| Task | File(s) | Details |
|------|---------|---------|
| Post-ingest world assembly | `ingestion_pipeline.py` | After indexing, run WorldArchitect to: (1) group entities by domain, (2) extract relationships, (3) propose initial axioms, (4) create world profile |
| Auto-canonization hook | `ingestion_pipeline.py` | After world assembly, CanonKeeper auto-commits. Flag `AUTO_CANONIZE=true` in config |
| World template system | `agents/world_templates.py` (NEW) | Pre-built world skeletons: `high_fantasy`, `space_opera`, `urban_horror`, `post_apocalyptic`. Each template defines: typical entity types, common relationships, starting axioms, tone. Used as scaffold for new universes |

**Success criteria:**
- [ ] Ingesting a source PDF → auto-generates connected world graph
- [ ] World templates provide instant starting points for common genres
- [ ] Auto-canonization creates queryable Neo4j graph without manual review

---

