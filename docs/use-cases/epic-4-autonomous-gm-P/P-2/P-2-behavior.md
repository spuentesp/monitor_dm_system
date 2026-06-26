# P-2: Start Scene — Behavior Tests

> **Use Case:** P-2 (Start Scene)
> **Priority:** 2 (CORE FOUNDATION)
> **Phase:** Phase 2 — Behavior Testing

---

## Overview

**P-2: Start Scene** creates a new scene within a story. Scenes are narrative episodes with participating entities and location context.

**Behavior Specification Summary:**
- **Preconditions:** Story must exist in Neo4j, Universe must exist
- **Flow:**
  1. Validate story exists (via Neo4j)
  2. Validate participating entities exist (if provided)
  3. Validate location_ref exists (if provided)
  4. Create Scene document in MongoDB
  5. Opening narration turn is appended separately via `mongodb_append_turn`
- **Output:** scene_id, SceneResponse

---

## Test Scenarios

### Scenario 1: Basic Scene Creation (Happy Path)

**Given** a story exists in Neo4j
**And** a universe exists
**When** user creates a scene with title and valid story_id/universe_id
**Then** a Scene document is created in MongoDB
**And** scene_id is returned

```python
scene = mongodb_create_scene(SceneCreate(
    story_id=story-id,
    universe_id=universe-id,
    title="Tavern Encounter",
    purpose="Social interaction"
))
assert scene.id is not None
assert scene.title == "Tavern Encounter"
assert scene.story_id == story-id
```

### Scenario 2: Scene Creation Fails Without Story

**Given** no story exists with ID `nonexistent-story`
**When** user attempts to create a scene with that story
**Then** a `ValueError` is raised with message containing "Story"

```python
with pytest.raises(ValueError, match="Story"):
    mongodb_create_scene(SceneCreate(
        story_id=nonexistent-story,
        universe_id=universe-id,
        title="Orphaned Scene"
    ))
```

### Scenario 3: Scene Creation Fails Without Universe

**Given** no universe exists with ID `nonexistent-universe`
**When** user attempts to create a scene with that universe
**Then** a `ValueError` is raised with message containing "Universe"

```python
with pytest.raises(ValueError, match="Universe"):
    mongodb_create_scene(SceneCreate(
        story_id=story-id,
        universe_id=nonexistent-universe,
        title="Orphaned Scene"
    ))
```

### Scenario 4: Participating Entities Are Validated

**Given** a story and universe exist
**When** user creates a scene with valid participating entity IDs
**Then** the scene is created successfully
**When** user creates a scene with invalid entity ID
**Then** a `ValueError` is raised

```python
# Valid entities
scene = mongodb_create_scene(SceneCreate(
    story_id=story-id,
    universe_id=universe-id,
    title="Battle Scene",
    participating_entities=[character-id-1, character-id-2]
))
assert scene.id is not None

# Invalid entity
with pytest.raises(ValueError, match="Entity"):
    mongodb_create_scene(SceneCreate(
        story_id=story-id,
        universe_id=universe-id,
        title="Invalid Entity Scene",
        participating_entities=[nonexistent-entity]
    ))
```

### Scenario 5: Location Ref Is Validated

**Given** a story and universe exist
**When** user creates a scene with valid location_ref
**Then** the scene is created successfully
**When** user creates a scene with invalid location_ref
**Then** a `ValueError` is raised

```python
# Valid location
scene = mongodb_create_scene(SceneCreate(
    story_id=story-id,
    universe_id=universe-id,
    title="Tavern Scene",
    location_ref=location-id
))
assert scene.id is not None

# Invalid location
with pytest.raises(ValueError, match="Location"):
    mongodb_create_scene(SceneCreate(
        story_id=story-id,
        universe_id=universe-id,
        title="Invalid Location Scene",
        location_ref=nonexistent-location
    ))
```

### Scenario 6: Scene Title Is Required

**Given** a story and universe exist
**When** user attempts to create a scene without a title
**Then** a `ValidationError` is raised

```python
with pytest.raises(ValidationError, match="title"):
    mongodb_create_scene(SceneCreate(
        story_id=story-id,
        universe_id=universe-id,
        title=""
    ))
```

### Scenario 7: Scene Status Defaults to ACTIVE

**Given** a story and universe exist
**When** user creates a scene without specifying status
**Then** the scene status defaults to ACTIVE

```python
scene = mongodb_create_scene(SceneCreate(
    story_id=story-id,
    universe_id=universe-id,
    title="Default Status Scene"
))
assert scene.status == SceneStatus.ACTIVE
```

### Scenario 8: Temporal Context Is Stored

**Given** a story and universe exist
**When** user creates a scene with temporal context
**Then** those fields are stored in MongoDB

```python
scene = mongodb_create_scene(SceneCreate(
    story_id=story-id,
    universe_id=universe-id,
    title="Flashback Scene",
    temporal_mode=TemporalMode.FLASHBACK,
    time_description="10 years ago"
))
assert scene.temporal_mode == TemporalMode.FLASHBACK
assert scene.time_description == "10 years ago"
```

### Scenario 9: Participating Entities Are Stored

**Given** a story and universe exist with character entities
**When** user creates a scene with participating_entities
**Then** those entities are stored in the scene

```python
scene = mongodb_create_scene(SceneCreate(
    story_id=story-id,
    universe_id=universe-id,
    title="Party Scene",
    participating_entities=[pc1-id, pc2-id, npc1-id]
))
assert len(scene.participating_entities) == 3
```

### Scenario 10: Opening Turn Is Appended

**Given** a scene exists
**When** user appends opening narration turn
**Then** the turn is stored in the scene's turns array

```python
turn = mongodb_append_turn(scene-id, TurnCreate(
    speaker=Speaker.GM,
    text="The tavern is crowded tonight..."
))
assert turn.turn_id is not None
assert turn.speaker == Speaker.GM
```

---

## Acceptance Criteria

| ID | Criterion | Test Scenario |
|----|-----------|---------------|
| AC-1 | Story must exist before scene creation | Scenario 2 |
| AC-2 | Universe must exist before scene creation | Scenario 3 |
| AC-3 | Participating entities are validated | Scenario 4 |
| AC-4 | Location ref is validated when provided | Scenario 5 |
| AC-5 | Title is required | Scenario 6 |
| AC-6 | Status defaults to ACTIVE | Scenario 7 |
| AC-7 | Temporal context is stored | Scenario 8 |
| AC-8 | Participating entities are stored | Scenario 9 |
| AC-9 | Opening turn can be appended | Scenario 10 |
| AC-10 | Scene ID is returned for downstream use | Scenario 1 |