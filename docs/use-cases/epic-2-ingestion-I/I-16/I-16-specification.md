# I-16: Fact Versioning & Tombstoning

**Actor:** IngestionLoop / CanonKeeper
**Trigger:** Synthesis of a new KnowledgePack or committing a fact.

**Purpose:** Ensure the canon reflects the *current* state of the world by superseding old facts.

**Flow:**
1. System identifies a new fact that contradicts an existing one (e.g., "The King is dead" vs "The King is alive").
2. System checks the `time_ref` and `confidence`.
3. If new fact is valid, old fact is marked `status="superseded"`.
4. A `REPLACES` edge is created in Neo4j from new to old.
5. Old fact is hidden from standard RAG retrieval.

**Output:** Consistent, evolving knowledge graph.
