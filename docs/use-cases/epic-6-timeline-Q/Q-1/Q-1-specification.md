# Q-1: Semantic Search

**Actor:** User
**Trigger:** Query → Search

**Flow:**
1. Prompt: Natural language query
2. Embed query → Qdrant search
3. Retrieve: entities, facts, scenes, snippets
4. Rank by relevance
5. Display results with context
6. Allow drill-down

**Examples:**
- "Where is the One Ring?"
- "What happened to Gandalf?"
- "Who are the enemies of the Fellowship?"

### Implementation

**Layer 1 (Data Layer):**
```python
qdrant_search(query, collection, universe_id, limit=10) -> list[SearchResult]
neo4j_get_entity(entity_id)           # Hydrate entity results
neo4j_get_fact(fact_id)               # Hydrate fact results
mongodb_get_scene(scene_id)           # Hydrate scene results
```

**Search Flow:**
```python
async def semantic_search(query: str, universe_id: UUID) -> SearchResults:
    # 1. Search across all collections
    entity_results = await qdrant_search(query, "entity_chunks", universe_id)
    scene_results = await qdrant_search(query, "scene_chunks", universe_id)
    snippet_results = await qdrant_search(query, "snippet_chunks", universe_id)

    # 2. Merge and rank by score
    all_results = merge_results(entity_results, scene_results, snippet_results)
    ranked = sorted(all_results, key=lambda r: r.score, reverse=True)[:10]

    # 3. Hydrate with full data
    hydrated = []
    for result in ranked:
        match result.type:
            case "entity":
                entity = await neo4j_get_entity(result.id)
                hydrated.append(EntityResult(entity, result.score))
            case "scene":
                scene = await mongodb_get_scene(result.id)
                hydrated.append(SceneResult(scene, result.score))
            case "snippet":
                snippet = await mongodb_get_snippet(result.id)
                hydrated.append(SnippetResult(snippet, result.score))

    return SearchResults(query=query, results=hydrated)
```

**Layer 3 (CLI):**
```bash
monitor query search "Where is the One Ring?"
monitor query search "What happened to Gandalf?" --universe <UUID>
```

---
