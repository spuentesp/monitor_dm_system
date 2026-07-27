# M-2: Create Multiverse

**Actor:** User
**Trigger:** Manage → Multiverse → Create

**Purpose:** Create the **setting/world layer** that serves as the canonical base for one or more playable universes.

**Flow:**
1. Prompt: Multiverse / setting name (e.g., "The Witcher", "Middle-earth", "Marvel")
2. Prompt: Default system/genre (e.g., "D&D 5e", "FATE")
3. Prompt: Description and baseline canon notes
4. Optionally seed it from an ingested knowledge pack or source set
5. Create Multiverse node in Neo4j
6. Link to Omniverse

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_omniverse() -> Omniverse                    # Get parent
neo4j_create_multiverse(omniverse_id, params) -> UUID # Create node + edge
```

**Layer 3 (CLI):**
```bash
monitor manage multiverse create --name "D&D Worlds" --system "D&D 5e"
# Or interactive: monitor manage multiverse create
```

**Database Writes:**

| Database | Node/Edge | Data |
|----------|-----------|------|
| Neo4j | `:Multiverse` | `{id, name, system_name, description, created_at}` |
| Neo4j | `(:Omniverse)-[:CONTAINS]->(:Multiverse)` | Edge |

---
