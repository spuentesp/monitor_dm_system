# Q-7: Ask Question (Natural Language)

**Actor:** User
**Trigger:** Query → Ask (free-form)

**Flow:**
1. User asks natural language question
2. Parse intent:
   - Entity lookup
   - Fact search
   - Relationship query
   - Timeline query
3. Execute appropriate query
4. Generate natural language answer
5. Display with sources

**Examples:**
- "What happened in the last session?"
- "Who killed the dragon?"
- "Where did we find the artifact?"
- "What are the rules for magic in this world?"

### Implementation

**Layer 1 (Data Layer):**
```python
# Uses multiple tools based on intent
qdrant_search(query, collections, universe_id)
neo4j_list_facts(filters)
neo4j_list_entities(filters)
neo4j_list_axioms(filters)
mongodb_get_scenes(story_id)
```

**Layer 2 (Agents):**
- `ContextAssembly.answer_question(question, universe_id)` - Main handler

**Question Answering Flow:**
```python
async def answer_question(question: str, universe_id: UUID) -> Answer:
    # 1. Classify question intent
    intent = await classify_question_intent(question)

    # 2. Gather relevant context based on intent
    context = []

    if intent.needs_semantic_search:
        results = await qdrant_search(question, ["scene_chunks", "snippet_chunks"], universe_id)
        context.extend(results)

    if intent.entity_name:
        entity = await neo4j_find_entity(intent.entity_name, universe_id)
        if entity:
            facts = await neo4j_list_facts(entity_id=entity.id)
            context.extend(facts)

    if intent.is_rules_question:
        axioms = await neo4j_list_axioms(universe_id)
        context.extend(axioms)

    if intent.is_timeline_question:
        events = await neo4j_list_events(universe_id=universe_id, limit=20)
        context.extend(events)

    # 3. Generate answer with LLM
    answer = await llm_generate_answer(
        question=question,
        context=context
    )

    # 4. Include sources
    sources = extract_sources(context)

    return Answer(text=answer, sources=sources)
```

**Layer 3 (CLI):**
```bash
monitor query ask "What happened in the last session?"
monitor query ask "What are the rules for magic?"
```

---
