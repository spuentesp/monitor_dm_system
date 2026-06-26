# P-3: Turn Loop — Behavior Tests

> **Use Case:** P-3 (Turn Loop)
> **Priority:** 3 (CORE FOUNDATION)
> **Phase:** Phase 2 — Behavior Testing

---

## Overview

**P-3: Turn Loop** is the core gameplay loop where players take turns within an active scene. It handles user input, routes to appropriate handlers, generates responses, and manages scene state.

**Behavior Specification Summary:**
- **Preconditions:** Active scene exists
- **Flow:**
  1. Display location, present entities, recent context
  2. Prompt for user input
  3. Parse input type (action, dialogue, question, meta-command)
  4. Process through appropriate handler
  5. Narrator generates response
  6. Append turns to MongoDB
  7. Check if scene should end
- **Output:** TurnResponse with speaker, text, resolution_ref (if applicable)

---

## Test Scenarios

### Scenario 1: Turn Loop Accepts User Input

**Given** an active scene exists with ID `scene-id`
**When** user provides action input
**Then** the input is recorded as a turn
**And** the scene state is updated

```python
turn = mongodb_append_turn(scene-id, TurnCreate(
    speaker=Speaker.USER,
    text="I attack the goblin with my sword"
))
assert turn.turn_id is not None
assert turn.speaker == Speaker.USER
```

### Scenario 2: Turn Loop Parses Input Types

**Given** an active scene exists
**When** user provides action input (no prefix)
**Then** input type is ACTION

```python
input_type = parse_input("I attack the goblin")
assert input_type == InputType.ACTION
```

**When** user provides dialogue input (quoted or "say")
**Then** input type is DIALOGUE

```python
input_type = parse_input('"Hello, friend," I say')
assert input_type == InputType.DIALOGUE
```

**When** user provides question (starts with what/who/where/how)
**Then** input type is QUESTION

```python
input_type = parse_input("What is that strange sound?")
assert input_type == InputType.QUESTION
```

**When** user provides meta-command (starts with /)
**Then** input type is META_COMMAND

```python
input_type = parse_input("/help")
assert input_type == InputType.META_COMMAND
```

### Scenario 3: Turn Loop Appends GM Response

**Given** user input has been recorded
**When** Narrator generates response
**Then** GM response is appended as a turn

```python
turn = mongodb_append_turn(scene-id, TurnCreate(
    speaker=Speaker.GM,
    text="You swing your sword at the goblin..."
))
assert turn.turn_id is not None
assert turn.speaker == Speaker.GM
```

### Scenario 4: Turn Loop Tracks Recent Context

**Given** a scene with existing turns
**When** user requests recent turns
**Then** the recent turns are returned

```python
turns = mongodb_get_recent_turns(scene-id, limit=10)
assert len(turns) >= 2  # At least user input + GM response
assert turns[0]["speaker"] == Speaker.USER
```

### Scenario 5: Turn Loop Checks Scene End

**Given** an active scene with turns
**When** scene has reached natural end point
**Then** scene status changes to COMPLETED

```python
scene = mongodb_get_scene(scene-id)
assert scene.status == SceneStatus.ACTIVE

# End scene
mongodb_update_scene(scene-id, SceneUpdate(status=SceneStatus.COMPLETED))

scene = mongodb_get_scene(scene-id)
assert scene.status == SceneStatus.COMPLETED
```

### Scenario 6: Turn Loop Creates Proposals on State Changes

**Given** user action implies canonical state change
**When** action is resolved
**Then** a ProposedChange is created

```python
proposal = mongodb_create_proposal(ProposalCreate(
    scene_id=scene-id,
    type="state_change",
    content={"entity_id": goblin-id, "tag": "hp", "delta": -5}
))
assert proposal is not None
```

### Scenario 7: Entity Speaker Turns

**Given** an NPC is participating in the scene
**When** NPC "speaks" (GM narrating for NPC)
**Then** entity_id is recorded with the turn

```python
turn = mongodb_append_turn(scene-id, TurnCreate(
    speaker=Speaker.ENTITY,
    entity_id=npc-id,
    text="The goblin growls at you."
))
assert turn.entity_id == npc-id
```

### Scenario 8: Resolution References

**Given** an action with dice roll was resolved
**When** GM response is generated
**Then** turn includes resolution_ref

```python
resolution = mongodb_create_resolution(ResolutionCreate(
    scene_id=scene-id,
    turn_id=user-turn-id,
    action="Attack goblin",
    formula="1d20+5",
    rolls=[15],
    total=20,
    outcome=Outcome.SUCCESS,
    dc=12
))

turn = mongodb_append_turn(scene-id, TurnCreate(
    speaker=Speaker.GM,
    text="Your attack hits!",
    resolution_ref=resolution.id
))
assert turn.resolution_ref == resolution.id
```

---

## Acceptance Criteria

| ID | Criterion | Test Scenario |
|----|-----------|---------------|
| AC-1 | User input is recorded as turn | Scenario 1 |
| AC-2 | Input types are correctly parsed | Scenario 2 |
| AC-3 | GM response is appended | Scenario 3 |
| AC-4 | Recent context is retrievable | Scenario 4 |
| AC-5 | Scene end is detected | Scenario 5 |
| AC-6 | State change proposals created | Scenario 6 |
| AC-7 | Entity speakers tracked | Scenario 7 |
| AC-8 | Resolution references stored | Scenario 8 |