# P-20: Audit, Recap, and Canon Review

**Actor:** User / GM Assistant / System
**Trigger:** Scene end, story resume, manual open of the audit drawer, or request for recap

**Purpose:** Make every session reviewable by showing what happened, what was rolled, what was proposed, and what became canon.

**Flow:**
1. Gather the latest scene turns, rolls, resolution metadata, proposals, and accepted/rejected canon changes
2. Present an **Audit Drawer** with:
   - turn-by-turn transcript
   - dice/check breakdowns
   - proposed changes and CanonKeeper verdicts
   - unresolved plot threads
3. Present a **Recap Card** for quick continuation:
   - what just happened
   - current stakes
   - who is present
   - what changed in the universe
4. Allow export or copy of the recap/audit summary for later review
5. When a story is resumed later, reuse this summary before entering P-12

**Output:** transparent, auditable scene and story summaries that preserve trust in the DM loop

### Implementation

**Data sources:**

| Source | Used for |
|--------|----------|
| MongoDB `scenes.turns` | transcript and recent context |
| MongoDB `proposed_changes` | staged and resolved canon proposals |
| Neo4j facts/events | accepted canon outcomes |
| Character working state | resource and condition changes |

---
