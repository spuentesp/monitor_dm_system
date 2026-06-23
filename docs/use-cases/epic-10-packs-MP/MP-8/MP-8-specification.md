# MP-8: Apply Pack → Existing World

**Actor:** User
**Trigger:** Packs → [Pack] → Apply → Existing World

**Purpose:** Import pack contents into an existing Multiverse/Universe. Supports selective import (user picks items first) or full apply with conflict detection and resolution.

**Re-apply behaviour:** Full conflict detection on every apply — no diffing against prior applications.

### Mode A: Selective Import

1. Open pack in Pack Editor (MP-4)
2. Select desired items (entity checkboxes, axiom checkboxes, etc.)
3. Choose target universe
4. Apply selection → CanonKeeper writes only selected items
5. No conflict detection (subset was chosen by user)

### Mode B: Full Apply + Conflict Resolution

1. Choose target universe
2. Choose auto-commit setting (see below)
3. System runs conflict detection → produces `PackApplySession` with one `PackConflict` per matching item
4. User resolves each conflict (or LLM handles per setting)
5. Commit: CanonKeeper writes all resolved items
6. Apply record appended to pack's `apply_history`

**Conflict resolution strategies (per item, any mix):**

| Strategy | Description |
|----------|-------------|
| `pack_wins` | Pack value overwrites world value |
| `world_wins` | World value kept; pack item ignored |
| `llm_merged` | LLM generates merged description/statement |
| `human_picked` | User sees both values side-by-side, selects one |

**Auto-commit setting (per apply session):**

| Setting | Behaviour |
|---------|-----------|
| Review mode | LLM resolutions are presented for user confirmation before any write |
| Auto-commit mode | LLM resolutions are written immediately; user reviews apply log after |

### Data Model

```python
@dataclass
class PackConflict:
    item_type: Literal["entity", "axiom", "lore_fact"]
    item_name: str             # conflicting name or statement key
    pack_value: dict           # what the pack has
    world_value: dict          # what is already in canon
    resolution: Literal["pending", "pack_wins", "world_wins", "llm_merged", "human_picked"]
    resolved_value: dict | None
    llm_suggestion: dict | None
    resolved_by: Literal["llm", "user"] | None
    auto_committed: bool

@dataclass
class PackApplySession:
    id: UUID
    pack_id: str
    target_universe_id: str
    mode: Literal["selective", "full"]
    auto_commit_llm: bool
    conflicts: list[PackConflict]
    status: Literal["pending", "resolving", "committed", "aborted"]
    applied_at: datetime | None
    items_written: int
```

### Implementation

**Layer 2 (Agents):**
```python
PackApplicator.detect_conflicts(pack_id, universe_id) -> list[PackConflict]
PackApplicator.resolve_with_llm(conflict) -> PackConflict   # fills llm_suggestion
PackApplicator.commit_session(session_id) -> ApplyResult    # CanonKeeper writes
```

---
