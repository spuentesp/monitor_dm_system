---
description: "Index for all dynamic execution loops and state machines."
tags: [loops, index, langgraph]
layer: 2
---

# 3. Loops & Systems

MONITOR's dynamic behaviors are **LangGraph `StateGraph`** state machines, not a
monolithic orchestrator. Each loop lives in
`packages/agents/src/monitor_agents/loops/`.

## Play loops
- **[Scene Loop](./scene_loop.md)** — the primary unit of play: turn-by-turn
  resolution under **GM-as-authority**. Start here.
- **[Combat Loop](./combat_loop.md)** — tactical encounter structure, entered
  from the Scene Loop.
- **[Story Loop](./story_loop.md)** — campaign/arc progression across scenes.
- **[Conversation Loop](./conversation_loop.md)** — deep multi-turn NPC dialogue.

## Setup & character loops
- **[Character Interview Loop](./character_interview_loop.md)** — story-first character interview (the *who* of the player character).
- **[Story Agreements Loop](./story_agreements_loop.md)** — three-question Session Zero agreement interview (premise, themes, lines, veils).
- **[Character Creation Loop](./character_creation_loop.md)** — schema-driven build.
- **[Progression Loop](./progression_loop.md)** — advancement / level-up.
- **[World-Building Loop](./world_building_loop.md)** — collaborative setting creation.

## Content loop
- **[Ingestion Loop](./ingestion_loop.md)** — multi-modal source → indexed knowledge.

## Interop & media
- **[Image Generation](./image_generation.md)** — canon-anchored image
  generation: asset lifecycle, budgets, moderation, loop suggestions.
- **[Ecosystem Interop](./ecosystem_interop.md)** — SillyTavern/RisuAI card
  import/export, lorebook runtime semantics, card macros, lorebook directives.

## How play actually works (read these)
- **[GM as Authority](../architecture/GM_AS_AUTHORITY.md)** — the GMAgent →
  Narrator → Resolver narration pipeline + `gm_tools` + `GMVerdict`.
- **[Retrieval Service](../architecture/RETRIEVAL_SERVICE.md)** — embeddings +
  RAG, the single owner.
- **[De-heuristic Principle](../architecture/DE_HEURISTIC_PRINCIPLE.md)** — why
  the GM decides semantically, never by keyword tables.

## Durability & State
All major loops use LangGraph checkpointers (`MongoDBSaver`): mid-turn crashes
resume where they left off, and `/backtrack` walks back through graph history.

## See Also
- [Layer 2: Agents](../2_architecture/layer2_agents.md)
