# M-7: Edit Universe

**Actor:** User
**Trigger:** Universe → Edit

**Flow:**
1. Display current values
2. Edit: name, genre, tone, tech_level, description
3. Validate
4. Update Neo4j
5. Confirm

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_universe(universe_id) -> Universe  # Current state
neo4j_update_universe(universe_id, params)   # Apply changes
```

**Layer 3 (CLI):**
```bash
monitor manage universe edit <UUID> --name "New Name"
monitor manage universe edit <UUID>  # Interactive edit
```

---
