# M-29: View Scene

**Actor:** User
**Trigger:** Select scene

**Output:**
- Title, purpose, location
- Participants
- Turn transcript
- Proposals (accepted/rejected)
- Summary

#### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_scene(scene_id) -> Scene
mongodb_get_turns(scene_id) -> list[Turn]
mongodb_get_proposals(scene_id) -> list[ProposedChange]
neo4j_get_entity(location_ref) -> Entity  # Location details
```

---
