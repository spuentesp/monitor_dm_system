# M-33: Manage Random Tables

**Actor:** User (GM/World Designer)
**Trigger:** Manage → Tables

**Purpose:** Create and manage random tables for procedural generation.

**Flow:**

1. **Create Table:**
   - Name and type (encounter, loot, name, trait, weather, etc.)
   - Dice formula (1d100, 2d6, etc.)
   - Entries with ranges or weights

2. **Use Table:**
   - Roll from template generation (M-31)
   - Roll from CLI (`/roll table "Rumors"`)
   - Roll from encounter generation

3. **Subtables:**
   - Entries can reference other tables
   - "Roll on subtable X"

#### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_random_table(universe_id, params) -> table_id
mongodb_get_random_table(table_id) -> RandomTable
mongodb_list_random_tables(universe_id, table_type=None)
mongodb_roll_on_table(table_id) -> RollResult
```

**Layer 3 (CLI):**
```bash
monitor manage table create --universe <UUID> --name "Random Rumors"
monitor manage table roll <TABLE_ID>

# In play REPL
> /roll table "Random Rumors"
```

---
