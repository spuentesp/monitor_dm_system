---
description: "The Conversation Loop — deep, multi-turn NPC dialogue."
tags: [loop, langgraph, conversation, npc]
layer: 2
---

# Conversation Loop

**Intent:** A dedicated flow for social interaction — dialogue and relationship
shifts rather than physical-action adjudication.

**Source:** `packages/agents/src/monitor_agents/loops/conversation_loop.py`
(`build_conversation_graph`). Driven by the CLI / backend, which injects player
input between graph runs.

## Nodes

- `open_session` → `load_npc_context` — bootstrap who's present, dispositions,
  and recent memories (retrieved via the
  [RetrievalService](../architecture/RETRIEVAL_SERVICE.md)); then pause for input.
- `process_player_turn` — take the player's dialogue.
- `generate_npc_responses` — the `NPCVoice` agent produces in-character replies
  per NPC personality profile; loops back for more or routes to close.
- `close_session` — summarize, extract facts, stage relationship-update
  `ProposedChange`s.

## See Also
- [Session Zero Loop](./session_zero_loop.md) · [Loops Index](./_index.md)
