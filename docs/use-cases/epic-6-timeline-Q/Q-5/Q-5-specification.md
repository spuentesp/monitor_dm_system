# Q-5: View Timeline

**Actor:** User
**Trigger:** Query → Timeline

**Flow:**
1. Select scope (story or universe)
2. Display chronological events
3. Filter by: entity, event type, severity
4. Click event for details

### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_events(
    story_id=None,
    universe_id=None,
    entity_id=None,
    order_by="time_ref"
) -> list[Event]
```

**Layer 3 (CLI):**
```bash
monitor query timeline --story <UUID>
monitor query timeline --universe <UUID> --entity <UUID>
```

---
