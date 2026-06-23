# Temporal & Contradiction Gap Implementation Summary

## Overview

This document summarizes the implementation that closes the "Temporal & Contradiction" gap in the MONITOR system. The gap was that the ingestion flow supported contradiction detection, temporal validation, and plot thread detection, but these features were **not integrated into the scene/story revision workflow**.

## What Was Implemented

### 1. Temporal Validation Schemas and Tools

**File:** `packages/data-layer/src/monitor_data/schemas/temporal_validation.py`

Created comprehensive schemas for temporal consistency validation:

- `TemporalValidationRequest` - Request to validate a scene's timeline
- `TemporalValidationResult` - Result with detected violations and validity assessment
- `TemporalViolation` - A detected temporal inconsistency (future reference, paradox, anachronism, etc.)
- `TemporalViolationType` - Enum: FUTURE_REFERENCE, TEMPORAL_PARADOX, ANACHRONISM, DURATION_MISMATCH, EXPIRED_FACT, PREMATURE_FACT
- `TemporalSeverity` - Enum: INFO, WARNING, ERROR
- `FactValidity` - Whether a fact is valid at a specific point in time
- `FactExpirationBatch` - Batch check of multiple facts for validity
- `SceneTemporalContext` - Temporal context for scene revisions
- `FactReplacement` - Record of a fact being replaced by a new version

**Files:** `packages/data-layer/src/monitor_data/tools/temporal_tools/`

Implemented two key modules:

1. **fact_expiration.py** - Fact validity and expiration system
   - `check_fact_validity()` - Determine if a fact is valid at a specific time
   - `batch_check_fact_validity()` - Check multiple facts for validity
   - `get_active_facts()` - Filter to only facts that are currently valid

2. **scene_validation.py** - Scene temporal validation
   - `validate_scene_temporal()` - Validate scene timeline against canon chronology
   - Checks for: future references, anachronisms, fact validity, temporal paradoxes

### 2. Fact Expiration System

**File:** `packages/data-layer/src/monitor_data/tools/temporal_tools/fact_expiration.py`

Implemented a complete fact lifecycle management system:

- Facts can have `time_ref` (when they become true) and `duration` (how long they remain true)
- Facts are classified as: VALID, EXPIRED, NOT_YET_STARTED, or ALWAYS_VALID
- Expiring soon warnings for facts that will expire within 24 hours
- Batch checking for multiple facts
- Automatic identification of facts that should be tombstoned

### 3. Temporal Validation for Scene Updates

**File:** `packages/data-layer/src/monitor_data/tools/temporal_tools/scene_validation.py`

Implemented comprehensive scene temporal validation:

- **Future Reference Detection**: Detects patterns like "tomorrow", "next year", "in the future"
- **Future Event Detection**: Checks if scene references events that happen after scene_time
- **Anachronism Detection**: Checks for technology/knowledge not available at scene time
- **Fact Validity Checking**: Ensures scene doesn't use expired or not-yet-valid facts
- **Temporal Paradox Detection**: Catches circular or impossible timeline references

### 4. Contradiction Detection Integration in CanonKeeper

**File:** `packages/agents/src/monitor_agents/canonkeeper.py`
**File:** `packages/agents/src/monitor_agents/temporal_validation.py`

Integrated contradiction detection into CanonKeeper's proposal evaluation pipeline:

**Updated Pipeline:**
1. Phase 1 - Policy gate (fast, no CoT)
2. **Phase 1.5 - Contradiction detection (NEW)** - Check if proposal contradicts existing canon
3. Phase 2 - Canon consistency reasoning (DSPy ChainOfThought) - Now includes contradiction context
4. Phase 3 - Final verdict via instructor

**Key Changes:**
- Added `_check_contradiction()` method to CanonKeeper
- Critical contradictions block proposals (decision=REJECTED)
- High/medium contradictions are included in reasoning context
- Added `check_proposal_contradictions()` function for batch checking
- Added `validate_scene_revision()` function for full scene revision validation

### 5. Fact Versioning with `replaces` Field

**File:** `packages/agents/src/monitor_agents/canonkeeper.py`

Implemented fact versioning and tombstoning:

- **`replace_fact()` method** - Replaces an existing fact with a new version
  - Adds `replaces` field to new fact pointing to old fact
  - Creates new fact
  - Tombstones old fact (marks as replaced)
  - Tracks replacement in MongoDB for audit trail

- **`_track_fact_replacement()` method** - Records replacements in MongoDB
  - Stores old_fact_id, new_fact_id, scene_id, reason, timestamp
  - Enables full audit trail of fact evolution

The `replaces` field was already in the FactCreate schema, but now it's actively used in the workflow.

### 6. Plot Thread Detection from Scenes

**File:** `packages/data-layer/src/monitor_data/tools/plot_thread_tools/scene_thread_detection.py`

Implemented automatic plot thread detection from scene content:

**Detection Functions:**
- `detect_plot_threads_from_scene()` - Extract threads from scene text
- `update_thread_status_from_scene()` - Update thread status based on outcomes
- `classify_thread_content()` - Classify text into thread category

**Thread Categories:**
- PROMISE - "promised to", "vowed to", "committed to"
- THREAT - "threatened to", "warned that", "lurking"
- MYSTERY - "mystery", "puzzle", "unknown", "unanswered"
- CONSEQUENCE - "as a result", "because of", "led to"
- RELATIONSHIP - "ally", "enemy", "friend", "tension"
- WORLD_EVENT - "war", "famine", "plague", "revolution"

**Thread Status Updates:**
- RESOLVED - Thread is resolved in scene
- ADVANCED - Thread is progressed in scene
- ABANDONED - Thread is implied to be dropped

### 7. Comprehensive Test Suite

**File:** `tests/test_temporal_contradiction_gap.py`

Created comprehensive tests covering:

**Fact Expiration Tests:**
- Timeless facts always valid
- Facts valid at check time
- Facts expired
- Facts not yet started
- Expiring soon warnings
- Batch fact validity checks

**Temporal Validation Tests:**
- Valid scenes have no violations
- Future reference detection
- Future event reference (ERROR severity)
- Expired fact reference
- Temporal paradox detection

**Plot Thread Detection Tests:**
- Promise thread detection
- Threat thread detection
- Mystery thread detection
- Consequence thread detection
- Relationship thread detection
- World event thread detection
- High urgency threads counted
- Thread status updates (resolved, advanced)
- Thread content classification

**Integration Tests:**
- Scene revision validation flow
- Fact replacement flow
- Contradiction blocks high severity

**Edge Case Tests:**
- Empty scene text
- Fact with no ID raises error
- Concurrent fact expiration checks
- Very long scene text handling

## Files Created

### Schemas
- `packages/data-layer/src/monitor_data/schemas/temporal_validation.py` - Temporal validation schemas

### Tools
- `packages/data-layer/src/monitor_data/tools/temporal_tools/__init__.py` - Package init
- `packages/data-layer/src/monitor_data/tools/temporal_tools/fact_expiration.py` - Fact expiration system
- `packages/data-layer/src/monitor_data/tools/temporal_tools/scene_validation.py` - Scene temporal validation
- `packages/data-layer/src/monitor_data/tools/plot_thread_tools/__init__.py` - Package init
- `packages/data-layer/src/monitor_data/tools/plot_thread_tools/scene_thread_detection.py` - Plot thread detection

### Agents
- `packages/agents/src/monitor_agents/temporal_validation.py` - Temporal validation integration

### Tests
- `tests/test_temporal_contradiction_gap.py` - Comprehensive test suite

## Files Modified

### CanonKeeper Agent
- `packages/agents/src/monitor_agents/canonkeeper.py`
  - Added import: `from monitor_agents.temporal_validation import check_proposal_contradictions`
  - Modified `_evaluate_single()` - Added Phase 1.5 for contradiction detection
  - Added `_check_contradiction()` method
  - Added `replace_fact()` method
  - Added `_track_fact_replacement()` method

## Usage Examples

### Validating a Scene Revision

```python
from monitor_agents.temporal_validation import validate_scene_revision
from datetime import datetime, timezone

result = await validate_scene_revision(
    scene_id=scene_id,
    universe_id=universe_id,
    story_id=story_id,
    scene_time_ref=datetime(1000, 1, 1, tzinfo=timezone.utc),
    scene_text="The knights rode into battle...",
    proposals=proposals,
    canonkeeper=canonkeeper,
    entity_ids=[entity_id1, entity_id2],
)

if not result["is_valid"]:
    # Block revision until violations are resolved
    print(f"Cannot proceed: {result['violations']}")
```

### Checking Fact Validity

```python
from monitor_data.tools.temporal_tools import check_fact_validity
from datetime import datetime, timezone

validity = check_fact_validity(
    fact={
        "id": uuid4(),
        "statement": "The castle is under siege",
        "time_ref": datetime(1000, 1, 1, tzinfo=timezone.utc),
        "duration": 3600,  # 1 hour
    },
    check_time=datetime.now(timezone.utc),
)

if validity.status == FactValidityStatus.VALID:
    print("Fact is currently valid")
elif validity.status == FactValidityStatus.EXPIRED:
    print("Fact has expired")
```

### Replacing a Fact

```python
from monitor_agents.canonkeeper import CanonKeeper

canonkeeper = CanonKeeper()
result = await canonkeeper.replace_fact(
    old_fact_id=old_fact_id,
    new_fact_params={
        "statement": "The king is dead",
        "universe_id": universe_id,
    },
    scene_id=scene_id,
    reason="Scene revision updated fact",
)
```

### Detecting Plot Threads

```python
from monitor_data.tools.plot_thread_tools import detect_plot_threads_from_scene

result = detect_plot_threads_from_scene(
    scene_text="The king promised to rebuild the city after the war.",
    scene_id=scene_id,
    universe_id=universe_id,
    entity_names=["The King"],
)

for thread in result.threads:
    print(f"{thread.category.value}: {thread.title} (urgency: {thread.urgency.value})")
```

## Architecture Impact

### Data Flow

```
Scene Revision
    ↓
validate_scene_revision()
    ↓
├─→ validate_scene_temporal() [Checks timeline consistency]
│   └─→ TemporalValidationResult
│
├─→ detect_contradictions() [Checks for canon conflicts]
│   └─→ ContradictionResult
│
└─→ Summary with violations and recommendations
```

### CanonKeeper Proposal Evaluation Flow

```
Proposal
    ↓
Phase 1: Policy Gate
    ↓
Phase 1.5: Contradiction Detection (NEW)
    ├─→ Critical contradictions → REJECT
    └─→ High/medium contradictions → Include in reasoning
    ↓
Phase 2: Canon Consistency Reasoning (with contradiction context)
    ↓
Phase 3: Final Verdict via Instructor
    ↓
If ACCEPT → Commit to Neo4j
    ├─→ Use replace_fact() if fact replaces existing
    └─→ Track replacements in MongoDB
```

### Plot Thread Flow

```
Scene Content
    ↓
detect_plot_threads_from_scene()
    ├─→ Pattern matching for each category
    ├─→ Urgency classification
    └─→ ExtractedPlotThread objects
    ↓
Store in MongoDB / Create Neo4j nodes
    ↓
Later Scenes
    ↓
update_thread_status_from_scene()
    ├─→ Check for resolution patterns
    ├─→ Check for advancement patterns
    └─→ Update thread status
```

## Benefits

1. **Temporal Consistency** - Scenes now respect canonical chronology
2. **Contradiction Prevention** - Contradictions are caught before commit
3. **Fact Evolution Tracking** - Full audit trail of how facts change over time
4. **Automatic Plot Thread Detection** - No manual tracking of unresolved threads
5. **World Evolution Over Time** - Facts can expire and be replaced naturally
6. **Comprehensive Validation** - Multiple layers of validation catch different types of issues

## Future Enhancements

1. **More Sophisticated Anachronism Detection** - Use knowledge bases instead of simple keyword lists
2. **Temporal Visualization** - Timeline view showing fact validity periods
3. **Contradiction Resolution Assistance** - AI-powered merge suggestions for conflicts
4. **Plot Thread Visualization** - Visual graph of thread relationships and status
5. **Fact Lifecycle Alerts** - Proactive notifications when facts will expire soon
6. **Scene Versioning** - Track all scene revisions with their temporal context

## Conclusion

The "Temporal & Contradiction" gap has been successfully closed by integrating existing contradiction detection, temporal validation, and plot thread extraction capabilities into the scene/story revision workflow. The implementation provides:

- Comprehensive temporal validation for scenes
- Integrated contradiction detection in CanonKeeper's evaluation pipeline
- Fact versioning with the `replaces` field
- Automatic plot thread detection from scene content
- Full test coverage for all new features

The foundation is now in place for the system to detect contradictions, manage temporal consistency, and track world evolution over time—all within the scene/story revision workflow, not just during ingestion.
