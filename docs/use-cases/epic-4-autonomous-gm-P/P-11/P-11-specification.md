# P-11: Conversation Mode

**Actor:** User
**Trigger:** Extended dialogue with NPC

**Flow:**
1. Enter focused dialogue with specific NPC
2. Load NPC context: personality, memories, goals, secrets
3. **Dialogue loop:**
   - User speaks
   - NPC responds (in character, using context)
   - Track conversation topics
   - May unlock: information, quests, relationship changes
4. Exit back to P-3

### Implementation

**Layer 1 (Data Layer):**
```python
# Tools called:
neo4j_get_entity(npc_id)                  # NPC data
neo4j_list_facts(entity_id=npc_id)        # Facts NPC knows
neo4j_get_relationships(npc_id)           # NPC's relationships
mongodb_get_memories(entity_id=npc_id)    # NPC's memories
mongodb_get_character_sheet(npc_id)       # NPC's personality/goals
qdrant_search_memories(npc_id, query)     # Semantic memory search
mongodb_append_turn(scene_id, turn)       # Log dialogue
mongodb_create_memory(npc_id, memory)     # Store new NPC memory
mongodb_create_proposal(scene_id, ...)    # Relationship/info proposals
```

**Layer 2 (Agents / runtime):**
- conversation bootstrap / `ConversationLoop` initializes the NPC-focused exchange
- `NPCVoice` or `Narrator.generate_npc_response(...)` handles the in-character dialogue
- `ContextAssembly.get_npc_full_context(npc_id)` - Deep NPC context
- Memory updates flow through the existing MongoDB/Qdrant-backed character-memory path

**Conversation State:**
```python
@dataclass
class ConversationState:
    scene_id: UUID
    npc_id: UUID
    npc_name: str
    topics_discussed: list[str] = field(default_factory=list)
    information_revealed: list[str] = field(default_factory=list)
    relationship_delta: int = 0  # -3 to +3 scale
    status: ConversationStatus = ConversationStatus.ACTIVE

class ConversationStatus(Enum):
    ACTIVE = "active"
    ENDING = "ending"
    ENDED = "ended"
```

**NPC Context Assembly:**
```python
async def get_npc_full_context(npc_id: UUID) -> NPCContext:
    """Assemble complete NPC context for conversation."""
    # Core entity data
    entity = await neo4j_get_entity(npc_id)
    sheet = await mongodb_get_character_sheet(npc_id)

    # Relationships
    relationships = await neo4j_get_relationships(npc_id)

    # Known facts
    facts = await neo4j_list_facts(entity_id=npc_id, limit=20)

    # Memories of player/current scene participants
    recent_memories = await mongodb_get_memories(
        entity_id=npc_id,
        sort_by="last_accessed",
        limit=10
    )

    return NPCContext(
        entity=entity,
        personality=sheet.properties.get("personality", {}),
        goals=sheet.properties.get("goals", []),
        secrets=sheet.properties.get("secrets", []),
        relationships=relationships,
        facts=facts,
        memories=recent_memories
    )

@dataclass
class NPCContext:
    entity: Entity
    personality: dict  # traits, quirks, speech patterns
    goals: list[str]   # what NPC wants
    secrets: list[str] # info NPC may reveal under conditions
    relationships: list[Relationship]
    facts: list[Fact]
    memories: list[Memory]
```

**Conversation Loop:**
```python
async def run_conversation_loop(
    conversation: ConversationState,
    context: Context
):
    """Main conversation loop with NPC."""
    # Get full NPC context once at start
    npc_context = await get_npc_full_context(conversation.npc_id)

    # Build system prompt for NPC persona
    npc_prompt = build_npc_persona_prompt(npc_context)

    while conversation.status == ConversationStatus.ACTIVE:
        # Display conversation prompt
        display_conversation_status(conversation)

        # Get player input
        user_input = await prompt_user(f"[To {conversation.npc_name}]> ")

        # Check for exit commands
        if user_input.lower() in ["/exit", "/leave", "/done"]:
            conversation.status = ConversationStatus.ENDING
            break

        # Search for relevant memories based on what player said
        relevant_memories = await qdrant_search_memories(
            conversation.npc_id,
            user_input,
            limit=3
        )

        # Generate NPC response
        response = await generate_npc_conversation_response(
            npc_prompt=npc_prompt,
            player_said=user_input,
            relevant_memories=relevant_memories,
            conversation_history=get_recent_turns(context.scene_id, limit=10)
        )

        # Check if NPC reveals information
        revealed = await check_information_reveal(
            npc_context.secrets,
            user_input,
            conversation
        )
        if revealed:
            conversation.information_revealed.append(revealed)

        # Track topic
        topic = extract_topic(user_input)
        if topic not in conversation.topics_discussed:
            conversation.topics_discussed.append(topic)

        # Log turns
        await mongodb_append_turn(context.scene_id, {
            "speaker": "user",
            "text": user_input
        })
        await mongodb_append_turn(context.scene_id, {
            "speaker": "entity",
            "entity_id": conversation.npc_id,
            "text": response
        })

    # Conversation ended - update NPC memory
    await end_conversation(conversation, context)

async def end_conversation(conversation: ConversationState, context: Context):
    """Finalize conversation and update NPC state."""
    # Create memory for NPC about the conversation
    summary = summarize_conversation(conversation)
    await mongodb_create_memory(conversation.npc_id, {
        "text": summary,
        "scene_id": context.scene_id,
        "importance": 0.7,
        "emotional_valence": conversation.relationship_delta * 0.2
    })

    # Create proposals for revealed information
    for info in conversation.information_revealed:
        await mongodb_create_proposal(context.scene_id, {
            "type": "fact",
            "content": {
                "statement": info,
                "authority": "player"  # Revealed through player action
            },
            "evidence": [context.scene_id],
            "confidence": 0.8
        })

    # Create proposal for relationship change if significant
    if abs(conversation.relationship_delta) >= 2:
        await mongodb_create_proposal(context.scene_id, {
            "type": "relationship",
            "content": {
                "from_entity": context.pc_id,
                "to_entity": conversation.npc_id,
                "type": "ALLY_OF" if conversation.relationship_delta > 0 else "ENEMY_OF"
            },
            "evidence": [context.scene_id],
            "authority": "system"
        })
```

**Information Reveal Logic:**
```python
async def check_information_reveal(
    secrets: list[str],
    player_input: str,
    conversation: ConversationState
) -> str | None:
    """Check if player input triggers secret reveal."""
    # Use LLM to evaluate if player has earned information
    for secret in secrets:
        # Check if topic relates to secret
        if not topic_matches(player_input, secret):
            continue

        # Check conversation conditions (trust, topics discussed, etc.)
        reveal_chance = calculate_reveal_chance(
            topics_discussed=conversation.topics_discussed,
            relationship_delta=conversation.relationship_delta
        )

        if random.random() < reveal_chance:
            return secret

    return None
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `scenes.turns` | Player and NPC dialogue turns |
| MongoDB | `memories` | NPC memory of conversation |
| MongoDB | `proposed_changes` | Revealed facts, relationship changes |

---
