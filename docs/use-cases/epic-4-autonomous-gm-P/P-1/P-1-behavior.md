# P-1: Start New Story — Behavior Tests

> **Use Case:** P-1 (Start New Story)
> **Priority:** 1 (CORE FOUNDATION)
> **Phase:** Phase 2 — Behavior Testing

---

## Overview

**P-1: Start New Story** creates a new story within a universe. This is the entry point for gameplay sessions.

**Behavior Specification Summary:**
- **Preconditions:** Universe must exist
- **Flow:**
  1. Select universe (or provide via CLI flag)
  2. Prompt for story title (required)
  3. Prompt for story type (campaign, arc, episode, one-shot)
  4. Prompt for theme (optional)
  5. Prompt for premise (optional)
  6. Select/create participating PCs (optional, deferred to M-13)
  7. Create Story node in Neo4j
  8. Create story_outline in MongoDB
- **Output:** story_id (UUID), ready for P-2 (Start Scene)

---

## Test Scenarios

### Scenario 1: Basic Story Creation (Happy Path)

**Given** a universe exists with ID `universe-123`
**When** user creates a story with title "The Dragon's Lair"
**Then** a Story node is created in Neo4j
**And** a story_outline document is created in MongoDB
**And** the story ID is returned

```python
# Data Layer Test
story = neo4j_create_story(StoryCreate(
    id=uuid4(),
    universe_id=universe-123,
    title="The Dragon's Lair",
    story_type=StoryType.CAMPAIGN,
    theme="fantasy adventure",
    premise="Heroes must defeat a dragon",
    status=StoryStatus.ACTIVE
))
assert story.id is not None
assert story.title == "The Dragon's Lair"
assert story.universe_id == universe-123

outline = mongodb_create_story_outline(StoryOutlineCreate(
    story_id=story.id,
    beats=[],
    pc_ids=[]
))
assert outline.story_id == story.id
```

### Scenario 2: Story Creation Fails Without Universe

**Given** no universe exists with ID `nonexistent-universe`
**When** user attempts to create a story with that universe
**Then** a `ValueError` is raised with message "Universe not found"

```python
with pytest.raises(ValueError, match="Universe not found"):
    neo4j_create_story(StoryCreate(
        id=uuid4(),
        universe_id="nonexistent-universe",
        title="Orphaned Story",
        story_type=StoryType.CAMPAIGN,
        status=StoryStatus.ACTIVE
    ))
```

### Scenario 3: Story Types Are Validated

**Given** a universe exists
**When** user creates a story with type "campaign"
**Then** the story is created successfully
**When** user creates a story with type "arc"
**Then** the story is created successfully
**When** user creates a story with type "episode"
**Then** the story is created successfully
**When** user creates a story with type "one-shot"
**Then** the story is created successfully
**When** user creates a story with type "invalid_type"
**Then** a `ValidationError` is raised

```python
for valid_type in [StoryType.CAMPAIGN, StoryType.ARC, StoryType.EPISODE, StoryType.ONE_SHOT]:
    story = neo4j_create_story(StoryCreate(
        id=uuid4(),
        universe_id=universe-123,
        title=f"Test Story ({valid_type})",
        story_type=valid_type,
        status=StoryStatus.ACTIVE
    ))
    assert story.id is not None

with pytest.raises(ValidationError):
    neo4j_create_story(StoryCreate(
        id=uuid4(),
        universe_id=universe-123,
        title="Invalid Story",
        story_type="invalid_type",
        status=StoryStatus.ACTIVE
    ))
```

### Scenario 4: Story Title Is Required

**Given** a universe exists
**When** user attempts to create a story without a title
**Then** a `ValidationError` is raised

```python
with pytest.raises(ValidationError, match="title"):
    neo4j_create_story(StoryCreate(
        id=uuid4(),
        universe_id=universe-123,
        title="",  # Empty title
        story_type=StoryType.CAMPAIGN,
        status=StoryStatus.ACTIVE
    ))
```

### Scenario 5: Story Status Defaults to ACTIVE

**Given** a universe exists
**When** user creates a story without specifying status
**Then** the story status defaults to "active"

```python
story = neo4j_create_story(StoryCreate(
    id=uuid4(),
    universe_id=universe-123,
    title="Status Test Story",
    story_type=StoryType.CAMPAIGN
    # No status specified
))
assert story.status == StoryStatus.ACTIVE
```

### Scenario 6: Optional Fields Are Stored

**Given** a universe exists
**When** user creates a story with theme and premise
**Then** those fields are stored in Neo4j

```python
story = neo4j_create_story(StoryCreate(
    id=uuid4(),
    universe_id=universe-123,
    title="Theme Test Story",
    story_type=StoryType.CAMPAIGN,
    theme="epic fantasy",
    premise="A band of heroes must save the world",
    status=StoryStatus.ACTIVE
))
assert story.theme == "epic fantasy"
assert story.premise == "A band of heroes must save the world"
```

### Scenario 7: Story Is Linked to Universe

**Given** a universe exists
**When** user creates a story in that universe
**Then** the story is linked via `[:HAS_STORY]` relationship

```python
story = neo4j_create_story(StoryCreate(
    id=uuid4(),
    universe_id=universe-123,
    title="Link Test Story",
    story_type=StoryType.CAMPAIGN,
    status=StoryStatus.ACTIVE
))

# Verify relationship exists
relationships = neo4j_get_relationships(story.id)
assert any(r.type == "HAS_STORY" for r in relationships)
```

### Scenario 8: Story Outline Is Created with Empty Beats

**Given** a universe exists
**When** user creates a story
**Then** the story_outline is created with empty beats array

```python
story = neo4j_create_story(StoryCreate(
    id=uuid4(),
    universe_id=universe-123,
    title="Outline Test Story",
    story_type=StoryType.CAMPAIGN,
    status=StoryStatus.ACTIVE
))

outline = mongodb_get_story_outline(story.id)
assert outline is not None
assert outline.story_id == story.id
assert outline.beats == []
```

### Scenario 9: PC IDs Are Validated (When Provided)

**Given** a universe exists with a character entity
**When** user creates a story with valid pc_ids
**Then** the story is created successfully
**When** user creates a story with invalid pc_id
**Then** a `ValueError` is raised

```python
# Valid PC
story = neo4j_create_story(StoryCreate(
    id=uuid4(),
    universe_id=universe-123,
    title="PC Test Story",
    story_type=StoryType.CAMPAIGN,
    pc_ids=[character-id],  # Valid character
    status=StoryStatus.ACTIVE
))
assert story.id is not None

# Invalid PC
with pytest.raises(ValueError, match="not found"):
    neo4j_create_story(StoryCreate(
        id=uuid4(),
        universe_id=universe-123,
        title="Invalid PC Story",
        story_type=StoryType.CAMPAIGN,
        pc_ids=["nonexistent-character"],
        status=StoryStatus.ACTIVE
    ))
```

### Scenario 10: CLI New Story Command

**Given** a universe exists
**When** user runs `monitor play new --universe <uuid> --title "CLI Story"`
**Then** the story is created in Neo4j

```bash
$ monitor play new --universe <uuid> --title "CLI Story"
Story 'CLI Story' started!
```

---

## Acceptance Criteria

| ID | Criterion | Test Scenario |
|----|-----------|---------------|
| AC-1 | Universe must exist before story creation | Scenario 2 |
| AC-2 | Title is required and validated | Scenario 4 |
| AC-3 | Story type is validated against enum | Scenario 3 |
| AC-4 | Status defaults to ACTIVE | Scenario 5 |
| AC-5 | Optional fields (theme, premise) are stored | Scenario 6 |
| AC-6 | Story is linked to universe via HAS_STORY | Scenario 7 |
| AC-7 | Story outline is created in MongoDB | Scenario 8 |
| AC-8 | PC IDs are validated when provided | Scenario 9 |
| AC-9 | CLI command creates story successfully | Scenario 10 |
| AC-10 | Story ID is returned for downstream use | Scenario 1 |