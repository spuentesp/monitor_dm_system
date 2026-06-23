# Q-3: Browse Entities

**Actor:** User
**Trigger:** Query → Browse

**Flow:**
1. Select universe
2. Select entity type (or all)
3. Display paginated list
4. Filter: name, state, properties
5. Select for details → M-16

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_entities(universe_id, type=None, filters={}, offset=0, limit=20) -> list[Entity]
```

**Layer 3 (CLI):**
```bash
monitor query entities --universe <UUID>
monitor query entities --type character --filter "role=PC"
```

---
