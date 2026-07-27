# P-5: Handle Dialogue

**Actor:** User
**Trigger:** User speaks in-character or to NPC

**Flow:**
1. Identify speaker (PC) and target (NPC or narration)
2. IF targeting NPC:
   - Load NPC personality, memories, facts
   - Generate NPC response using context
   - Create memory for NPC (what was said)
   - May trigger: information exchange, relationship change, quest hook
3. IF narration (speaking aloud):
   - Record as turn
   - Other entities may react
4. Return to P-3

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_entity(npc_id)                  # Get NPC data
neo4j_list_facts(entity_id=npc_id)        # NPC's known facts
mongodb_get_memories(entity_id=npc_id)    # NPC's memories
qdrant_search_memories(npc_id, query)     # Semantic memory recall
mongodb_append_turn(scene_id, turn)       # Record dialogue
mongodb_create_memory(npc_id, memory)     # Store NPC memory of conversation
mongodb_create_proposal(...)              # If relationship change proposed
```

**Layer 2 (Agents / runtime):**
- `Narrator.handle_dialogue(speaker_id, target_id, text, context)` - Main handler
- `ContextAssembly.get_entity_context(npc_id)` - Assemble NPC context
- `NPCVoice` and the MongoDB/Qdrant-backed memory path provide targeted recall and response behavior when the dialogue is NPC-driven
- New or reinforced memories are persisted through the existing `mongodb_create_memory` / `qdrant_*` flow; there is no separate live `MemoryManager` agent

**NPC Response Generation:**
```python
async def generate_npc_response(
    npc_id: UUID,
    player_said: str,
    context: Context
) -> str:
    # 1. Get NPC personality and state
    npc = await neo4j_get_entity(npc_id)

    # 2. Get NPC's memories of this player/topic
    memories = await qdrant_search_memories(npc_id, player_said, limit=5)

    # 3. Get relevant facts NPC knows
    facts = await neo4j_list_facts(entity_id=npc_id, limit=10)

    # 4. Build prompt with NPC personality, knowledge, memories
    prompt = build_npc_prompt(npc, memories, facts, player_said)

    # 5. Generate response via LLM
    response = await llm_generate(prompt)

    # 6. Create memory for NPC about this conversation
    await mongodb_create_memory({
        "entity_id": npc_id,
        "text": f"Player said: {player_said}. I responded: {response}",
        "scene_id": context.scene_id,
        "importance": 0.6
    })

    return response
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `scenes.turns` | User dialogue turn |
| MongoDB | `scenes.turns` | NPC response turn (speaker: "entity", entity_id: npc_id) |
| MongoDB | `memories` | NPC's memory of conversation |

---
