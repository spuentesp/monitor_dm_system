# Q-9: Keyword Search (OpenSearch)

**Actor:** User
**Trigger:** Query → Keyword search

**Flow:**
1. Enter keyword query with optional filters (universe, entity type, date range).
2. Search OpenSearch index for entities/facts/documents.
3. Return ranked results with snippets and links to canonical records.

**Output:** Ranked results with context snippets.

**Implementation**
- Data Layer: OpenSearch client query endpoints.
- Agents: ContextAssembly formats and enriches results.
- CLI: `monitor query --keyword "ancient dragon" --universe <UUID>`.

---
