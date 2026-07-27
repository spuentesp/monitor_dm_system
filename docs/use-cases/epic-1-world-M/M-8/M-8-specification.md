# M-8: Delete Universe

**Actor:** User
**Trigger:** Universe → Delete

**Flow:**
1. Warning: "This will affect X stories, Y entities, Z facts"
2. Require confirmation (type name)
3. Soft delete: set canon_level = "retconned" on all nodes
4. Confirm deletion

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_universe_stats(universe_id) -> UniverseStats  # For warning
neo4j_soft_delete_universe(universe_id)                 # Soft delete
```

**Soft Delete Logic:**
```python
async def soft_delete_universe(universe_id: UUID) -> DeletionResult:
    """Soft delete a universe and all its contents."""
    # Get counts for confirmation
    stats = await neo4j_get_universe_stats(universe_id)

    # Mark all related nodes as retconned
    # Uses a transaction to ensure atomicity
    await neo4j_run_transaction("""
        MATCH (u:Universe {id: $universe_id})
        SET u.canon_level = 'retconned', u.deleted_at = datetime()

        WITH u
        OPTIONAL MATCH (u)-[:HAS_STORY]->(s:Story)
        SET s.canon_level = 'retconned', s.deleted_at = datetime()

        WITH u
        OPTIONAL MATCH (u)-[:HAS_ENTITY]->(e)
        SET e.canon_level = 'retconned', e.deleted_at = datetime()

        WITH u
        OPTIONAL MATCH (u)-[:HAS_AXIOM]->(a:Axiom)
        SET a.canon_level = 'retconned', a.deleted_at = datetime()
    """, {"universe_id": str(universe_id)})

    return DeletionResult(
        stories_affected=stats.story_count,
        entities_affected=stats.entity_count
    )
```

**Layer 3 (CLI):**
```bash
monitor manage universe delete <UUID>
# Requires confirmation: "Type 'Middle-earth' to confirm deletion"
```

**Important:** Soft delete preserves data. Use `--hard` flag for permanent deletion (admin only).

---
