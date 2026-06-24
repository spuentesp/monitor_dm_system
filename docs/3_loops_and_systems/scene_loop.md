---
description: "Details the execution steps of the LangGraph Scene Loop for turn-by-turn gameplay."
tags: [loop, langgraph, scene-loop]
layer: 2
---

# Scene Loop (Core Play)

**Intent:** Provide a durable, checkpointed state machine to handle a single turn of gameplay, ensuring the player's action is resolved, narrated, and safely persisted.

## Flow Diagram
```mermaid
stateDiagram-v2
    [*] --> load_context
    load_context --> resolve: S1→S3
    resolve --> narrate: S3→S4/S5
    narrate --> persist_turn_artifacts
    persist_turn_artifacts --> canonize: scene_complete or max_turns
    persist_turn_artifacts --> [*]: continue (await next run)
    canonize --> [*]: scene finalized
```

## Node Explanations
- **`load_context`**: Calls `ContextAssembly` agent to gather entities, facts, and memories relevant to the scene and action.
- **`resolve`**: Calls the `Resolver` agent to adjudicate rules and dice. Outputs `ProposedChange` documents.
- **`narrate`**: Calls the `Narrator` agent to generate immersive GM prose based on the context and resolution.
- **`persist_turn_artifacts`**: Saves the generated turn and resolution state to MongoDB.
- **`canonize`**: (Runs at end of scene) Calls the `CanonKeeper` to evaluate all staged `ProposedChange` documents and commit accepted ones to Neo4j.

## See Also
- [Loops Index](./_index.md)
- [The Proposed Change Pattern](../2_architecture/the_proposed_change_pattern.md)
