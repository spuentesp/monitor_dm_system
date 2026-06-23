# P-6: Answer Question

**Actor:** User
**Trigger:** User asks about environment, entities, situation

**Examples:** "What do I see?", "Who is in the room?", "What do I know about orcs?"

**Flow:**
1. Parse question type:
   - **Perception:** What's observable (environment, entities)
   - **Knowledge:** What PC knows (facts, memories)
   - **Lore:** What exists in universe (axioms, canon)
2. Query appropriate sources:
   - Scene context (current location, entities)
   - Character memories (what they remember)
   - Canon facts (what's true)
3. Narrator describes based on PC's perspective
4. May reveal or withhold information based on checks
5. Return to P-3

### Implementation

**Layer 1 (Data Layer):**
```python
# By question type:

# Perception questions:
mongodb_get_scene(scene_id)               # Current scene state
neo4j_list_entities(location_id)          # Entities at location

# Knowledge questions:
mongodb_get_memories(entity_id=pc_id)     # PC's memories
qdrant_search_memories(pc_id, query)      # Semantic memory search
neo4j_list_facts(entity_id=pc_id)         # Facts involving PC

# Lore questions:
neo4j_list_axioms(universe_id)            # World rules
qdrant_search(query, "snippet_chunks")    # Search source materials
neo4j_list_facts(universe_id)             # Canon facts
```

**Layer 2 (Agents):**
- `Narrator.answer_question(question, context)` - Main handler
- `ContextAssembly.get_scene_context(scene_id)` - For perception
- `ContextAssembly.get_entity_context(pc_id)` - For knowledge
- `ContextAssembly.semantic_search(query, universe_id)` - For lore

**Question Classification:**
```python
class QuestionType(Enum):
    PERCEPTION = "perception"  # Observable environment
    KNOWLEDGE = "knowledge"    # What PC knows
    LORE = "lore"             # Universe facts/rules

def classify_question(text: str) -> QuestionType:
    text_lower = text.lower()

    # Perception indicators
    if any(word in text_lower for word in ["see", "hear", "smell", "look", "around", "room"]):
        return QuestionType.PERCEPTION

    # Knowledge indicators
    if any(word in text_lower for word in ["know", "remember", "recall", "heard about"]):
        return QuestionType.KNOWLEDGE

    # Lore/general questions
    return QuestionType.LORE

async def answer_question(question: str, context: Context) -> str:
    q_type = classify_question(question)

    match q_type:
        case QuestionType.PERCEPTION:
            # What's observable now
            scene = await mongodb_get_scene(context.scene_id)
            entities = await neo4j_list_entities(scene.location_ref)
            return generate_perception_response(scene, entities)

        case QuestionType.KNOWLEDGE:
            # What PC remembers/knows
            memories = await qdrant_search_memories(context.pc_id, question)
            facts = await neo4j_list_facts(entity_id=context.pc_id)
            return generate_knowledge_response(memories, facts)

        case QuestionType.LORE:
            # Universe facts
            results = await qdrant_search(question, "snippet_chunks")
            axioms = await neo4j_list_axioms(context.universe_id)
            return generate_lore_response(results, axioms)
```

**Information Gating:**
```python
# Some information may require checks to reveal
async def gate_information(info: str, pc: Entity, context: Context) -> str:
    # Check if perception requires roll
    if requires_perception_check(info):
        roll = await dice_roll("1d20")
        dc = get_perception_dc(info)
        if roll.total < dc:
            return "You don't notice anything unusual."

    return info
```

---
