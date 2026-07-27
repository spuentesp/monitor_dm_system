# CF-8: Review Session Ingestion and CanonKeeper Queue

**Actor:** Human GM
**Trigger:** After assisted recording ends or a session transcript/text upload is processed

**Purpose:** Show, per scene, what MONITOR thinks happened, what will be added to the story/world, and what CanonKeeper is about to commit.

**Flow:**
1. System segments the captured session into draft scenes
2. For each scene, display:
   - scene summary
   - detected participants and locations
   - extracted facts, events, relationships, and state changes
3. Group proposed additions into a **CanonKeeper Review** panel:
   - new entities
   - new facts or axioms
   - relationship changes
   - state tag/resource changes
   - unresolved ambiguities or contradictions
4. Show the supporting evidence snippets from the transcript for each proposed change
5. GM chooses per item or per scene:
   - `Accept`
   - `Reject`
   - `Defer`
   - `Edit before accept`
6. Accepted items are passed to CanonKeeper for canonization and linked to the relevant scene/story/universe
7. The review result is stored so the GM can audit what was added later

**Output:** a scene-by-scene review queue showing exactly what MONITOR will add to the world and what CanonKeeper accepted or rejected

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_scene(scene_id)
mongodb_list_proposed_changes(scene_id=scene_id)
mongodb_update_proposed_change(change_id, status=...)
neo4j_create_fact(...)            # CanonKeeper only, after approval
neo4j_create_event(...)           # CanonKeeper only, after approval
neo4j_update_state_tags(...)      # CanonKeeper only, after approval
```

**Layer 2 (Agents):**
- `CanonKeeper.evaluate_proposals(scene_id, proposals)` — Produce verdicts per scene
- `CanonKeeper.explain_verdict(proposal)` — Explain why an item is accepted/rejected/deferred
- `Narrator.generate_scene_review_summary(scene_id)` — Human-readable summary for the GM

**UI expectations:**

| Panel | Purpose |
|-------|---------|
| Scene list | Review one recorded scene at a time |
| CanonKeeper queue | Show what will be added to the world |
| Evidence drawer | Show transcript lines supporting each change |
| Verdict badges | `accepted`, `rejected`, `deferred`, `needs review` |

---
