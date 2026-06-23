### 1. ContextAssembly Agent

> **Implementation:** `packages/agents/src/monitor_agents/context_assembly.py`

**Responsibility:** Retrieve and package relevant context for narrative generation

**Authority:**
- Read: all databases
- Write: none (read-only agent)
- Canonize: no

**What it does:**
- Query Neo4j for canonical state (entities, facts, relations)
- Query MongoDB for narrative context (prior turns, memories)
- Query Qdrant for semantic recall (similar scenes, memories)
- Compose context package with IDs + texts
- Apply filtering by universe/story/scene scope

**What it does NOT do:**
- Generate narrative
- Decide what's relevant (uses heuristics/retrieval)
- Modify data

**Context Package Structure:**
```javascript
{
  canonical: {
    entities: [Entity],       // from Neo4j
    facts: [Fact],            // from Neo4j
    relations: [Relation]     // from Neo4j
  },
  narrative: {
    prior_turns: [Turn],      // from MongoDB
    scene_summary: "...",     // from MongoDB
    gm_notes: "..."           // from MongoDB
  },
  recalled: {
    similar_scenes: [Scene],  // from Qdrant
    character_memories: [Memory],  // from Qdrant → MongoDB
    rule_excerpts: [Snippet]  // from Qdrant → MongoDB
  },
  metadata: {
    universe_id: "...",
    story_id: "...",
    scene_id: "...",
    timestamp: "..."
  }
}
```

**Retrieval strategies:**
- **Canonical:** Graph traversal from scene entities (1-2 hops)
- **Narrative:** Temporal window (last N turns, last M scenes)
- **Recalled:** Vector similarity (top-K with metadata filters)

---

### 2. Narrator Agent

> **Implementation:** `packages/agents/src/monitor_agents/narrator.py`

**Responsibility:** Generate narrative content (GM responses, descriptions)

**Two-phase approach:**
- Phase 1: DSPy `NarratorModule` — creative reasoning chain that writes the prose
- Phase 2: instructor `NarratorResponse` — extracts structured proposals from the prose

**Authority:**
- Read: context package (provided by ContextAssembly)
- Write: MongoDB (turn text only)
- Canonize: no

**What it does:**
- Generate GM dialogue/responses
- Create scene descriptions
- Narrate NPC actions
- Maintain tone/style consistency
- Extract implicit proposals (optional)

**What it does NOT do:**
- Decide canonical truth
- Resolve rules/dice
- Modify graph state
- Assemble context (receives it)

**Input:**
- Context package (from ContextAssembly)
- User action (from Turn)
- Resolution outcome (from Resolver, if applicable)

**Output:**
- Narrative text (GM turn)
- Optional: ProposedChanges (extracted from narrative)

**Example:**
```python
def generate(context, user_action, resolution):
    prompt = compose_prompt(
        canonical=context.canonical,
        narrative=context.narrative,
        user_action=user_action,
        resolution=resolution
    )

    response = llm.generate(prompt)

    # Optional: extract proposals from narrative
    proposals = extract_canonical_deltas(response)

    return {
        "text": response,
        "proposals": proposals
    }
```

---

### 3. Resolver Agent

> **Implementation:** `packages/agents/src/monitor_agents/resolver.py`

**Responsibility:** Resolve rules, dice, randomization for outcomes

**Play modes** (set per session in `SceneState.play_mode`):
- `"narrative"` — pure fiction, no dice ever
- `"dice_standard"` — 1d20 + modifier, generic fallback
- `"dice_game_system"` — schema-driven dice via `GameSystemRuntime`

Also detects **forced narrative** (player asserts outcome instead of attempting) via regex heuristics.

**Authority:**
- Read: rule system (MongoDB), context
- Write: MongoDB (resolution records, proposals)
- Canonize: no (proposes outcomes)

**What it does:**
- Apply game rules (if rules-based)
- Roll dice / randomize outcomes
- Determine success/failure/partial
- Generate structured outcome (not narrative)
- Create evidence-linked proposals

**What it does NOT do:**
- Generate narrative text (that's Narrator)
- Decide canonical truth (that's CanonKeeper)
- Modify graph directly

**Input:**
- User action (intent)
- Context (character stats, environmental factors)
- Rule system schema

**Output:**
- Resolution record (success/fail, rolls, mechanics)
- ProposedChanges (structured deltas)

**Example:**
```python
def resolve_action(action, context, rules):
    # Interpret action
    intent = parse_intent(action)  # e.g., "attack orc"

    # Apply rules
    if rules.type == "dice":
        roll = dice.roll(rules.formula)
        success = roll >= rules.difficulty
    elif rules.type == "narrative":
        success = randomizer.choose(["success", "partial", "fail"])

    # Generate outcome structure
    outcome = {
        "action": intent,
        "success": success,
        "mechanics": {"roll": roll, "target": rules.difficulty},
        "effects": determine_effects(intent, success)
    }

    # Create proposals
    proposals = []
    for effect in outcome.effects:
        proposals.append(ProposedChange(
            type="state_change",
            content=effect,
            evidence=[f"roll:{roll}", f"action:{intent}"]
        ))

    return outcome, proposals
```

---

