# Q-2: Ask About Entity

**Actor:** User
**Trigger:** Query → Ask, or "Tell me about [X]"

**Flow:**
1. Identify entity by name or ID
2. Retrieve:
   - Entity properties
   - Related facts
   - Relationships
   - Memories (if character)
   - Recent events
3. Generate natural language summary
4. Display

**Examples:**
- "Tell me about Gandalf"
- "What do I know about Mordor?"
- "Who is Sauron?"

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_find_entity(name, universe_id) -> Entity | None
neo4j_get_entity(entity_id) -> Entity
neo4j_get_relationships(entity_id) -> list[Relationship]
neo4j_list_facts(entity_id=entity_id, limit=20) -> list[Fact]
neo4j_list_events(entity_id=entity_id, limit=10) -> list[Event]
mongodb_get_memories(entity_id, limit=10) -> list[Memory]
```

**Entity Summary Generation:**
```python
async def ask_about_entity(query: str, universe_id: UUID) -> str:
    # 1. Extract entity name from query
    entity_name = extract_entity_name(query)

    # 2. Find entity
    entity = await neo4j_find_entity(entity_name, universe_id)
    if not entity:
        return f"I don't know of any '{entity_name}' in this universe."

    # 3. Gather context
    relationships = await neo4j_get_relationships(entity.id)
    facts = await neo4j_list_facts(entity_id=entity.id, limit=20)
    events = await neo4j_list_events(entity_id=entity.id, limit=10)

    memories = []
    if entity.entity_type == "character":
        memories = await mongodb_get_memories(entity.id, limit=10)

    # 4. Generate summary with LLM
    summary = await llm_generate_entity_summary(
        entity=entity,
        relationships=relationships,
        facts=facts,
        events=events,
        memories=memories
    )

    return summary
```

**Layer 3 (CLI):**
```bash
monitor query ask "Tell me about Gandalf"
monitor query entity <UUID>
```

---
