# M-32: Manage Archetypes

**Actor:** User (GM/World Designer)
**Trigger:** Manage → Archetypes

**Purpose:** CRUD operations for EntityArchetype nodes (species, classes, concepts).

**Flow:**

1. **List Archetypes:**
   - Filter by entity_type (character, faction, location, etc.)
   - Show usage count (how many instances derive from each)

2. **Create Archetype:**
   - Define type-specific properties
   - Optionally link to source (rulebook reference)
   - Set canon_level (proposed, canon)

3. **Edit Archetype:**
   - Update properties
   - Changes don't cascade to instances (instances copy at creation time)

4. **View Archetype Usage:**
   - List all EntityInstances that DERIVES_FROM this archetype
   - Show property inheritance

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_create_archetype(universe_id, entity_type, params) -> archetype_id
neo4j_get_archetype(archetype_id) -> EntityArchetype
neo4j_list_archetypes(universe_id, entity_type=None) -> list[EntityArchetype]
neo4j_update_archetype(archetype_id, params)
neo4j_delete_archetype(archetype_id)  # Only if no instances derive from it
neo4j_list_archetype_instances(archetype_id) -> list[EntityInstance]
```

**Layer 2 (Agents):**
- `Orchestrator.create_archetype(universe_id, params)` — Create archetype
- `Orchestrator.list_archetypes(universe_id, filters)` — List with usage stats

**Layer 3 (CLI):**
```bash
monitor manage archetype create --universe <UUID> --type character --name "Wizard"
monitor manage archetype list --universe <UUID>
monitor manage archetype view <ARCHETYPE_ID>
monitor manage archetype instances <ARCHETYPE_ID>  # Show derived entities
```

**Database Writes:**

| Database | Node | Data |
|----------|------|------|
| Neo4j | `:EntityArchetype` | `{id, universe_id, name, entity_type, properties, canon_level}` |

---
