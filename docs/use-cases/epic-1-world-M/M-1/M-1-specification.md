# M-1: Manage Omniverse

**Actor:** Admin
**Trigger:** Settings → Omniverse (rare)

**Flow:**
1. View omniverse info (usually just one)
2. Edit name, description
3. View multiverse list

**Note:** Usually auto-created. Most users won't touch this.

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_get_omniverse() -> Omniverse           # Get (or create) singleton
neo4j_update_omniverse(id, params)           # Update name/description
neo4j_list_multiverses(omniverse_id)         # List children
```

**Layer 3 (CLI):**
```bash
monitor manage omniverse        # View/edit omniverse
```

**Note:** Omniverse is auto-created on first run if none exists.

---
