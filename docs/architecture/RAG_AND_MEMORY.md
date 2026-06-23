# Tri-Modal RAG Architecture

This document details how MONITOR combines three distinct retrieval strategies to ground its AI agents in the world's canonical truth while maintaining narrative flow and deep history.

---

## 1. The Tri-Modal Memory Model

Traditional RAG (Retrieval Augmented Generation) uses only Vector search. MONITOR uses a "Tri-Modal" approach to prevent AI hallucinations and provide structural consistency.

### 1.1 Structural Memory (Graph - Neo4j)
- **Strategy:** Graph Traversal.
- **Why:** Real-world entities have relationships that don't always appear in text. To know who an NPC's enemy is, or what town is nearby, we traverse the graph.
- **Execution:** `ContextAssembly` identifies entities in the current scene and performs 1-2 hop neighborhood fetches to discover surrounding facts and relationships.

### 1.2 Semantic Memory (Vector - Qdrant)
- **Strategy:** Similarity Search.
- **Why:** To recall "similar moments" or specific lore buried in massive manuals.
- **Execution:** User actions are embedded as vectors. We query Qdrant for top-K matches across lore snippets and character-specific memories.

### 1.3 Narrative Memory (Document - MongoDB)
- **Strategy:** Temporal/Sequential Fetching.
- **Why:** To maintain conversational coherence. The AI needs to "read back" the last few turns exactly as they were written.
- **Execution:** Fetches the last 10-20 turns from the `scenes` and `turns` collections, providing the immediate conversational context.

---

## 2. The Context Package

The `ContextAssembly` agent aggregates results from all three modes into a unified **Context Package**. This package is what is actually injected into the LLM prompts.

### Package Structure (Simplified)
```json
{
  "entities": [...],    // Structural: from Neo4j
  "facts": [...],       // Structural: from Neo4j
  "memories": [...],    // Semantic: from Qdrant/MongoDB
  "turns": [...],       // Narrative: from MongoDB
  "game_system": {...}, // Rules: from MongoDB
  "summary": "..."      // Recap: from MongoDB
}
```

---

## 3. Dealing with Scale (Token Budgets)

Because the Tri-Modal search can return vast amounts of data, the system implements a **Token Budgeting** strategy:

1. **Ranking:** Context items are scored based on their semantic relevance to the *specific* player action.
2. **Prioritization:** 
   - 1st: Immediate turn history (Conversational flow).
   - 2nd: Active plot threads (Story focus).
   - 3rd: Direct entity facts (Logic consistency).
   - 4th: Distant lore/memories (World flavor).
3. **Truncation:** If the budget is exceeded (e.g., 2048 tokens), lower-priority items are dropped or summarized.

---

## 4. Continuity Guards

The Tri-Modal system prevents common AI pitfalls:
- **Hallucination Prevention:** If an AI tries to invent a fact, the `CanonKeeper` can check the Structural Memory (Neo4j) to see if it contradicts existing truth.
- **Relationship Persistence:** By always pulling structural relationships, the AI won't "forget" that two characters hate each other just because it wasn't mentioned in the last 10 turns.
- **Lore Adherence:** Rule-book snippets are injected when the player attempts a mechanical action, ensuring the `Resolver` acts like a fair Game Master.
