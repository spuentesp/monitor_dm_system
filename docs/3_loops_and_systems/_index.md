---
description: "Index for all dynamic execution loops and state machines."
tags: [loops, index, langgraph]
layer: 2
---

# 3. Loops & Systems

This directory documents the dynamic behaviors of MONITOR. Instead of a monolithic "Orchestrator," the system uses **LangGraph StateGraph** state machines to handle complex, multi-turn interactions.

## The Core Loops
- **[Scene Loop](./scene_loop.md)**: The primary unit of play. Manages turn-by-turn interaction.
- **[Story Loop](./story_loop.md)**: Manages high-level campaign progression and scene transitions.
- **[Conversation Loop](./conversation_loop.md)**: A specialized loop for deep, multi-turn NPC dialogue.
- **[World-Building Loop](./world_building_loop.md)**: A collaborative session for defining setting elements.

## Durability & State
All major loops use LangGraph Checkpointers (e.g., `MongoDBSaver`). This ensures:
- **Crash Recovery**: Mid-turn crashes can be resumed exactly where they left off.
- **Time Travel**: Supports `/backtrack` commands by walking back through the graph history.

## See Also
- [Layer 2: Agents](../2_architecture/layer2_agents.md)
