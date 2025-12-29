# Proposed Additional Use Cases

> **Status: INTEGRATED**
>
> The main use cases (P-13, P-14, M-31, M-32, M-33, Q-10) have been integrated into `docs/USE_CASES.md`.
> The data layer use cases (DL-15 to DL-21) have been integrated into `docs/DATA_LAYER_USE_CASES.md`.
> The ontology has been updated in `docs/ontology/ONTOLOGY.md`.
>
> This document is retained for reference and contains additional implementation details.

---

## P-13: Party Management

**Actor:** User
**Trigger:** During story creation (P-1), scene setup (P-2), or mid-scene via meta-command

**Purpose:** Manage a party of PCs/NPCs that travel and act together, supporting solo play with multiple characters.

**Motivation:** Solo RPG play typically involves managing a party of 3-6 characters. The system must track which characters are "active" (player-controlled) vs "supporting" (AI-assisted), handle party inventory, and manage split-party scenarios.

**Flow:**

1. **Party Setup (during P-1 or M-*):**
   - Create party entity (group type)
   - Add initial members (PCs and companion NPCs)
   - Designate "active PC" (primary player focus)
   - Set party formation/marching order (optional)

2. **During Play (P-3):**
   - Switch active PC perspective (`/switch <character>`)
   - View party status (`/party`)
   - Manage party inventory (`/inventory`)
   - Handle party-wide checks (e.g., group stealth)

3. **Split Party:**
   - Designate groups when party splits
   - Scene focuses on one group at a time
   - System tracks what "off-screen" group is doing
   - Rejoin triggers when groups reunite

4. **Party Actions:**
   - Collective actions (travel, rest, camp)
   - Resource sharing (gold, supplies)
   - Formation-based combat bonuses

**Meta Commands:**

| Command | Description | Example |
|---------|-------------|---------|
| `/party` | Show party status | `/party` |
| `/party add <name>` | Add entity to party | `/party add "Legolas"` |
| `/party remove <name>` | Remove from party | `/party remove "Boromir"` |
| `/switch <name>` | Change active PC | `/switch "Gimli"` |
| `/inventory` | Show party inventory | `/inventory` |
| `/split <group1> <group2>` | Split party into groups | `/split "Frodo,Sam" "Aragorn,Legolas,Gimli"` |
| `/rejoin` | Reunite split party | `/rejoin` |

### Implementation

**Layer 1 (Data Layer):**

```python
# New tools needed:
neo4j_create_party(story_id, params) -> party_id
neo4j_get_party(party_id) -> Party
neo4j_add_party_member(party_id, entity_id, role)
neo4j_remove_party_member(party_id, entity_id)
neo4j_update_party(party_id, params)

mongodb_get_party_inventory(party_id) -> Inventory
mongodb_update_party_inventory(party_id, changes)
mongodb_create_party_split(party_id, groups) -> split_id
mongodb_resolve_party_split(split_id)
```

**Layer 2 (Agents):**
- `Orchestrator.create_party(story_id, members)` — Initialize party
- `Orchestrator.switch_active_pc(party_id, entity_id)` — Change focus
- `Orchestrator.split_party(party_id, groups)` — Handle party split
- `Narrator.generate_offscreen_summary(group, duration)` — What happened to other group
- `ContextAssembly.get_party_context(party_id)` — Full party state for prompts

**Layer 3 (CLI):**
```bash
# During story creation
monitor play new --party "Aragorn,Legolas,Gimli,Frodo,Sam"

# Meta commands in REPL
> /party
> /switch Frodo
> /inventory
```

**Database Writes:**

| Database | Node/Collection | Data |
|----------|-----------------|------|
| Neo4j | `:Party` | `{id, story_id, name, formation, created_at}` |
| Neo4j | `[:MEMBER_OF {role, position, joined_at}]` | Edge: Entity → Party |
| Neo4j | `[:ACTIVE_PC]` | Edge: Party → current active EntityInstance |
| MongoDB | `party_inventories` | `{party_id, items: [...], gold, encumbrance}` |
| MongoDB | `party_splits` | `{id, party_id, groups: [{members, location, status}], active_group}` |

**Party Schema:**

```python
@dataclass
class Party:
    id: UUID
    story_id: UUID
    name: str                          # "The Fellowship"

    members: list[PartyMember]
    active_pc_id: UUID                 # Current player focus

    formation: list[UUID] | None       # Marching order
    status: PartyStatus                # traveling, camping, combat, split

    created_at: datetime
    updated_at: datetime

@dataclass
class PartyMember:
    entity_id: UUID
    name: str
    role: PartyRole                    # pc, companion, hireling, mount
    position: str | None               # front, middle, rear
    joined_at: datetime
    left_at: datetime | None

class PartyRole(Enum):
    PC = "pc"                          # Player character (user controls)
    COMPANION = "companion"            # AI-controlled ally
    HIRELING = "hireling"              # Temporary help
    MOUNT = "mount"                    # Animal/vehicle
    PRISONER = "prisoner"              # Captive traveling with party

class PartyStatus(Enum):
    TRAVELING = "traveling"
    CAMPING = "camping"
    IN_SCENE = "in_scene"
    COMBAT = "combat"
    SPLIT = "split"
    RESTING = "resting"
```

**Party-Wide Actions:**

```python
async def handle_party_action(action: str, party: Party, context: Context) -> Resolution:
    """Handle actions that affect the whole party."""

    match action:
        case "travel":
            # Calculate travel time based on slowest member
            slowest = min(party.members, key=lambda m: get_speed(m.entity_id))
            distance = context.destination_distance
            duration = calculate_travel_time(distance, slowest.speed)

            # Advance world time
            await orchestrator.advance_time(context.universe_id, duration, "travel")

            # Check for random encounters
            if await check_random_encounter(context):
                return Resolution(trigger_encounter=True)

            # Update party location
            await neo4j_update_party(party.id, {"location_id": context.destination_id})

            return Resolution(success=True, narration=f"After {duration}, the party arrives at {context.destination}.")

        case "rest_short":
            # 1 hour rest - recover resources
            for member in party.members:
                await apply_short_rest(member.entity_id)
            await orchestrator.advance_time(context.universe_id, "1 hour", "short rest")
            return Resolution(success=True, narration="The party takes a short rest...")

        case "rest_long":
            # 8 hour rest - full recovery
            for member in party.members:
                await apply_long_rest(member.entity_id)
            await orchestrator.advance_time(context.universe_id, "8 hours", "long rest")
            return Resolution(success=True, narration="The party rests through the night...")

        case "group_check":
            # Everyone rolls, use best result
            rolls = []
            for member in party.members:
                roll = await resolver.roll_check(member.entity_id, context.skill)
                rolls.append((member, roll))
            best = max(rolls, key=lambda r: r[1].total)
            return Resolution(
                success=best[1].total >= context.dc,
                narration=f"{best[0].name} notices something..."
            )
```

**Split Party Handling:**

```python
@dataclass
class PartySplit:
    id: UUID
    party_id: UUID
    groups: list[SplitGroup]
    active_group_index: int           # Which group player is following
    split_at: datetime
    reunited_at: datetime | None

@dataclass
class SplitGroup:
    members: list[UUID]
    location_id: UUID | None
    status: str                        # active, offscreen, waiting
    offscreen_summary: str | None      # What they did while player was away

async def split_party(party_id: UUID, group_definitions: list[list[str]]) -> PartySplit:
    """Split party into separate groups."""
    party = await neo4j_get_party(party_id)

    groups = []
    for i, member_names in enumerate(group_definitions):
        member_ids = [m.entity_id for m in party.members if m.name in member_names]
        groups.append(SplitGroup(
            members=member_ids,
            location_id=party.location_id,
            status="active" if i == 0 else "offscreen"
        ))

    split = await mongodb_create_party_split(party_id, groups)
    await neo4j_update_party(party_id, {"status": "split"})

    return split

async def switch_to_group(split_id: UUID, group_index: int):
    """Switch focus to different group in a split party."""
    split = await mongodb_get_party_split(split_id)

    # Generate summary of what current group did while we switch away
    current_group = split.groups[split.active_group_index]
    if current_group.status == "active":
        summary = await narrator.generate_offscreen_summary(current_group)
        current_group.offscreen_summary = summary
        current_group.status = "offscreen"

    # Activate new group
    new_group = split.groups[group_index]

    # If they were offscreen, narrate what they did
    if new_group.offscreen_summary:
        await display_offscreen_summary(new_group.offscreen_summary)

    new_group.status = "active"
    split.active_group_index = group_index

    await mongodb_update_party_split(split_id, split)

async def rejoin_party(split_id: UUID, reunion_location_id: UUID):
    """Reunite split party."""
    split = await mongodb_get_party_split(split_id)

    # Generate summaries for all offscreen groups
    for group in split.groups:
        if group.status == "offscreen" and not group.offscreen_summary:
            group.offscreen_summary = await narrator.generate_offscreen_summary(group)

    # Display what each group did
    await display_reunion_summary(split)

    # Mark split as resolved
    await mongodb_resolve_party_split(split_id)
    await neo4j_update_party(split.party_id, {
        "status": "in_scene",
        "location_id": reunion_location_id
    })
```

**Dependencies Identified:**

1. **DL-15: Party Management (Neo4j)** — New data-layer use case needed
   - CRUD for Party nodes
   - Party membership edges with roles
   - Active PC tracking

2. **DL-16: Party Inventory (MongoDB)** — New data-layer use case needed
   - Shared inventory collection
   - Item ownership within party
   - Encumbrance calculation

3. **Ontology Update:** Add `:Party` node type and `:MEMBER_OF` edge properties

---

## P-14: Flashback Mode

**Actor:** User or Narrator (AI-triggered)
**Trigger:** User command `/flashback`, narrative prompt, or backstory exploration

**Purpose:** Play scenes from the past to establish character history, reveal information, or resolve mysteries.

**Motivation:** Good storytelling often involves flashbacks. Characters have pasts that inform their present. Mysteries may require playing out "what really happened."

**Flow:**

1. **Trigger Flashback:**
   - User requests: `/flashback "How did Gandalf first meet Bilbo?"`
   - Narrator suggests: "Do you want to play out this memory?"
   - System detects backstory hook

2. **Set Temporal Context:**
   - When: "50 years before the current story"
   - Where: Select or create location
   - Who: Select participating entities (may include younger versions)

3. **Enter Flashback Scene:**
   - Create scene with `temporal_mode: "flashback"`
   - Narrator sets the stage in past tense
   - Player actions are in past tense ("You approached the door")

4. **Play Flashback:**
   - Normal turn loop (P-3) with modified context
   - Proposals marked with `authority: "historical"`
   - Facts created are backdated to flashback time_ref

5. **Flashback Resolution:**
   - Scene ends naturally or via `/end flashback`
   - Narrator transitions back to present
   - Relevant information now available in character memories

6. **Canonization:**
   - Facts from flashback become canon with historical timestamps
   - Character memories updated with flashback content
   - NPCs met in flashback may appear in present

**Meta Commands:**

| Command | Description | Example |
|---------|-------------|---------|
| `/flashback "<prompt>"` | Initiate flashback | `/flashback "How we met"` |
| `/flashback end` | End flashback, return to present | `/flashback end` |
| `/flashback abort` | Cancel flashback without canonizing | `/flashback abort` |
| `/when` | Check current temporal context | `/when` → "Flashback: 50 years ago" |

### Implementation

**Layer 1 (Data Layer):**

```python
# Modified scene creation:
mongodb_create_scene(story_id, params, temporal_mode="flashback", time_ref=past_date)

# Flashback-specific queries:
neo4j_get_entity_at_time(entity_id, time_ref) -> Entity  # Entity state at past time
neo4j_list_facts_at_time(universe_id, time_ref) -> list[Fact]  # What was true then

# Backdated fact creation:
neo4j_create_fact(params, time_ref=past_date, authority="historical")
```

**Layer 2 (Agents):**
- `Orchestrator.enter_flashback(story_id, prompt, time_ref)` — Initialize flashback
- `Orchestrator.exit_flashback(scene_id, canonize=True)` — Return to present
- `ContextAssembly.get_historical_context(universe_id, time_ref)` — World state at past time
- `Narrator.generate_flashback_opening(prompt, context)` — Set the past scene
- `Narrator.generate_flashback_transition(direction)` — "The memory fades..." / "You remember..."
- `MemoryManager.create_memories_from_flashback(scene_id, entities)` — Convert to memories

**Layer 3 (CLI):**
```bash
# In REPL
> /flashback "The day I found the sword"

# System responds:
# 🕐 Entering flashback...
# The memory takes shape. It was fifteen years ago, in the depths of winter...
#
# [FLASHBACK: Winter, 15 years ago - The Ruins of Kazad-dum]
#
# You are younger, less weathered. Your hands are steady as you descend...
```

**Database Writes:**

| Database | Collection/Node | Data |
|----------|-----------------|------|
| MongoDB | `scenes` | `{..., temporal_mode: "flashback", time_ref: <past_date>, parent_scene_id: <present_scene>}` |
| MongoDB | `scenes.turns` | Turns with `tense: "past"` marker |
| Neo4j | `:Fact` | Facts with `time_ref` set to flashback time, `authority: "historical"` |
| MongoDB | `memories` | Memories created from flashback for participating characters |

**Flashback Schema:**

```python
@dataclass
class FlashbackContext:
    id: UUID
    story_id: UUID
    parent_scene_id: UUID              # Scene we return to after

    prompt: str                        # What triggered/describes the flashback
    time_ref: WorldDate                # When in the past
    time_description: str              # "15 years ago", "The day you met"

    location_id: UUID
    participating_entities: list[UUID]

    status: FlashbackStatus

    # What we learned
    facts_established: list[UUID]
    memories_created: list[UUID]

class FlashbackStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"            # Canonized and returned to present
    ABORTED = "aborted"                # Cancelled without canonizing

class TemporalMode(Enum):
    PRESENT = "present"                # Normal play
    FLASHBACK = "flashback"            # Playing the past
    FLASH_FORWARD = "flash_forward"    # Playing possible future (non-canonical)
    DREAM = "dream"                    # Non-canonical dream sequence
```

**Flashback Flow:**

```python
async def enter_flashback(
    story_id: UUID,
    prompt: str,
    time_description: str,
    time_ref: WorldDate | None = None
) -> FlashbackContext:
    """Enter a flashback scene."""

    # 1. Pause current scene
    current_scene = await mongodb_get_active_scene(story_id)
    if current_scene:
        await mongodb_update_scene(current_scene.id, {"status": "paused"})

    # 2. Calculate time_ref if not provided
    if not time_ref:
        time_ref = await parse_time_description(time_description, story_id)

    # 3. Determine location and participants from prompt
    context_hints = await narrator.parse_flashback_prompt(prompt)

    # 4. Get historical state of entities
    historical_entities = []
    for entity_id in context_hints.participants:
        entity = await neo4j_get_entity_at_time(entity_id, time_ref)
        historical_entities.append(entity)

    # 5. Create flashback scene
    flashback_scene = await mongodb_create_scene(story_id, {
        "title": f"Flashback: {prompt[:50]}",
        "temporal_mode": "flashback",
        "time_ref": time_ref,
        "time_description": time_description,
        "parent_scene_id": current_scene.id if current_scene else None,
        "location_ref": context_hints.location_id,
        "participating_entities": [e.id for e in historical_entities],
        "status": "active"
    })

    # 6. Generate opening narration
    opening = await narrator.generate_flashback_opening(
        prompt=prompt,
        time_description=time_description,
        location=context_hints.location,
        entities=historical_entities
    )

    await mongodb_append_turn(flashback_scene.id, {
        "speaker": "gm",
        "text": opening,
        "tense": "past"
    })

    # 7. Create flashback context
    flashback = FlashbackContext(
        id=uuid4(),
        story_id=story_id,
        parent_scene_id=current_scene.id if current_scene else None,
        prompt=prompt,
        time_ref=time_ref,
        time_description=time_description,
        location_id=context_hints.location_id,
        participating_entities=[e.id for e in historical_entities],
        status=FlashbackStatus.ACTIVE,
        facts_established=[],
        memories_created=[]
    )

    return flashback

async def exit_flashback(flashback_id: UUID, canonize: bool = True) -> None:
    """Exit flashback and return to present."""
    flashback = await get_flashback_context(flashback_id)
    flashback_scene = await mongodb_get_scene(flashback.scene_id)

    if canonize:
        # 1. Process proposals from flashback with historical authority
        proposals = await mongodb_list_proposals(flashback_scene.id, status="pending")
        for proposal in proposals:
            proposal.authority = "historical"
            proposal.time_ref = flashback.time_ref

        # 2. Canonize (CanonKeeper handles historical facts)
        await canonkeeper.canonize_scene(flashback_scene.id)

        # 3. Create memories for participating characters
        for entity_id in flashback.participating_entities:
            memory_text = await narrator.summarize_flashback_for_entity(
                flashback_scene.id,
                entity_id
            )
            memory_id = await mongodb_create_memory(entity_id, {
                "text": memory_text,
                "scene_id": flashback_scene.id,
                "importance": 0.8,
                "certainty": 1.0,  # They lived it
                "created_at": flashback.time_ref  # Memory is from the past
            })
            flashback.memories_created.append(memory_id)

        flashback.status = FlashbackStatus.COMPLETED
    else:
        # Abort - don't canonize
        await mongodb_update_scene(flashback_scene.id, {"status": "aborted"})
        flashback.status = FlashbackStatus.ABORTED

    # 4. Generate transition back to present
    transition = await narrator.generate_flashback_transition("exit")

    # 5. Resume parent scene
    if flashback.parent_scene_id:
        await mongodb_update_scene(flashback.parent_scene_id, {"status": "active"})
        await mongodb_append_turn(flashback.parent_scene_id, {
            "speaker": "gm",
            "text": transition
        })

    # 6. Display what was learned
    if canonize and flashback.facts_established:
        summary = await narrator.summarize_flashback_revelations(flashback)
        await display(summary)
```

**Historical Entity State:**

```python
async def get_entity_at_time(entity_id: UUID, time_ref: WorldDate) -> Entity:
    """
    Reconstruct entity state at a past point in time.

    This involves:
    1. Getting current entity
    2. Finding all state_change facts after time_ref
    3. Reversing those changes to get historical state
    """
    current = await neo4j_get_entity(entity_id)

    # Find state changes between time_ref and now
    changes = await neo4j_list_facts(
        entity_id=entity_id,
        type="state_change",
        after=time_ref,
        order="time_ref ASC"
    )

    # Build historical state by reversing changes
    historical_state_tags = list(current.state_tags)

    for change in reversed(changes):
        if change.content.get("action") == "add":
            # This tag was added after time_ref, remove it
            tag = change.content.get("tag")
            if tag in historical_state_tags:
                historical_state_tags.remove(tag)
        elif change.content.get("action") == "remove":
            # This tag was removed after time_ref, restore it
            tag = change.content.get("tag")
            if tag not in historical_state_tags:
                historical_state_tags.append(tag)

    return Entity(
        **current.__dict__,
        state_tags=historical_state_tags,
        _is_historical=True,
        _as_of=time_ref
    )
```

**Dependencies Identified:**

1. **neo4j_get_entity_at_time** — New query capability to reconstruct historical state
2. **Temporal fact ordering** — Facts need `time_ref` populated consistently
3. **Flashback-aware narrator prompts** — LLM needs past-tense generation mode
4. **Parent/child scene relationships** — Scenes need `parent_scene_id` field

---

## M-31: Entity Templates (Prefabs)

**Actor:** User (GM/World Designer)
**Trigger:** Manage → Templates, or during entity creation

**Purpose:** Create reusable entity templates for efficient world-building and consistent entity generation.

**Motivation:** GMs frequently need to create similar entities (guards, orcs, taverns). Templates allow:
- One-click generation of common entity types
- Consistency across similar entities
- Randomization within defined parameters
- Bulk entity creation

**Flow:**

1. **Create Template:**
   - Base on existing entity OR create from scratch
   - Define fixed properties (type, base description)
   - Define variable properties (name patterns, stat ranges)
   - Define randomization rules

2. **Configure Template:**
   - Property overrides
   - Naming patterns ("$ADJECTIVE Guard", "Orc #$N")
   - Stat generation rules ("3d6 for STR", "roll on table")
   - Equipment loadout options
   - State tag defaults

3. **Use Template:**
   - Instantiate single entity
   - Bulk generate N entities
   - Quick-spawn during scene (NPC appears)

4. **Template Inheritance:**
   - Templates can derive from other templates
   - Override specific properties
   - Chain: "Elite Orc" → "Orc Warrior" → "Orc" → "Humanoid"

### Implementation

**Layer 1 (Data Layer):**

```python
# Template CRUD (MongoDB - templates are documents with complex structure)
mongodb_create_entity_template(universe_id, params) -> template_id
mongodb_get_entity_template(template_id) -> EntityTemplate
mongodb_list_entity_templates(universe_id, type=None) -> list[TemplateSummary]
mongodb_update_entity_template(template_id, params)
mongodb_delete_entity_template(template_id)

# Template instantiation
mongodb_instantiate_template(template_id, overrides={}) -> entity_params
mongodb_bulk_instantiate_template(template_id, count, overrides={}) -> list[entity_params]

# The actual entity creation still uses:
neo4j_create_entity(universe_id, entity_type, params)
```

**Layer 2 (Agents):**
- `Orchestrator.create_template_from_entity(entity_id)` — Generate template from existing
- `Orchestrator.instantiate_template(template_id, overrides)` — Create entity from template
- `Orchestrator.bulk_spawn(template_id, count, location_id)` — Mass creation
- `Narrator.generate_template_variation(template, seed)` — Add unique flavor

**Layer 3 (CLI):**
```bash
# Template management
monitor manage template create --from-entity <UUID> --name "Generic Guard"
monitor manage template list --universe <UUID>
monitor manage template view <TEMPLATE_ID>
monitor manage template edit <TEMPLATE_ID>

# Template instantiation
monitor manage entity create --template "Generic Guard" --name "Bob"
monitor manage entity spawn --template "Orc Warrior" --count 5 --location <UUID>

# Quick spawn during play (meta command)
> /spawn "Orc Warrior" 3
```

**Database Writes:**

| Database | Collection | Data |
|----------|------------|------|
| MongoDB | `entity_templates` | Full template definition |
| Neo4j | `:EntityInstance` | Instantiated entities (normal entity creation) |
| Neo4j | `[:INSTANTIATED_FROM]` | Optional edge linking entity to template |

**Template Schema:**

```python
@dataclass
class EntityTemplate:
    id: UUID
    universe_id: UUID
    name: str                          # "Generic Guard", "Orc Warrior"
    description: str

    # Base entity properties
    entity_type: EntityType            # character, location, object, etc.
    base_properties: dict              # Fixed properties

    # Variable properties with generation rules
    variable_properties: list[VariableProperty]

    # Naming
    naming_pattern: NamingPattern

    # For characters: stat generation
    stat_generation: StatGeneration | None

    # Default state tags
    default_state_tags: list[str]

    # Equipment/inventory for characters
    equipment_options: list[EquipmentOption] | None

    # Inheritance
    parent_template_id: UUID | None

    # Metadata
    created_at: datetime
    updated_at: datetime
    usage_count: int                   # How many times instantiated

@dataclass
class VariableProperty:
    property_path: str                 # "properties.personality" or "description"
    generation_type: GenerationType
    options: list[str] | None          # For choice type
    range: tuple[int, int] | None      # For numeric type
    pattern: str | None                # For text generation
    table_id: UUID | None              # For table lookup

class GenerationType(Enum):
    FIXED = "fixed"                    # Always the same value
    CHOICE = "choice"                  # Random from list
    RANGE = "range"                    # Random number in range
    PATTERN = "pattern"                # Text pattern with substitution
    TABLE = "table"                    # Roll on random table
    LLM = "llm"                        # Generate with LLM

@dataclass
class NamingPattern:
    type: NamingType
    pattern: str | None                # "$ADJECTIVE $NOUN" or "Orc #$N"
    adjectives: list[str] | None       # ["Fierce", "Cunning", "Brutal"]
    nouns: list[str] | None            # ["Warrior", "Scout", "Shaman"]
    name_list: list[str] | None        # Specific names to draw from

class NamingType(Enum):
    PATTERN = "pattern"                # "Fierce Orc Warrior"
    NUMBERED = "numbered"              # "Orc #1", "Orc #2"
    LIST = "list"                      # Draw from name list
    LLM = "llm"                        # Generate name with LLM
    USER = "user"                      # Always prompt user

@dataclass
class StatGeneration:
    method: str                        # "standard_array", "point_buy", "roll"
    formulas: dict[str, str]           # {"STR": "3d6", "DEX": "4d6kh3"}
    constraints: dict | None           # {"total_min": 70, "no_stat_below": 8}

@dataclass
class EquipmentOption:
    category: str                      # "weapon", "armor", "supplies"
    choices: list[str]                 # ["sword", "axe", "mace"]
    quantity: str | int                # "1d4" or 1
    required: bool                     # Must have at least one
```

**Template Instantiation:**

```python
async def instantiate_template(
    template_id: UUID,
    overrides: dict = {},
    location_id: UUID | None = None
) -> UUID:
    """Create a new entity from a template."""
    template = await mongodb_get_entity_template(template_id)

    # 1. Start with base properties
    params = dict(template.base_properties)

    # 2. Generate variable properties
    for var_prop in template.variable_properties:
        value = await generate_property_value(var_prop)
        set_nested(params, var_prop.property_path, value)

    # 3. Generate name
    name = await generate_name(template.naming_pattern, template)
    params["name"] = overrides.get("name", name)

    # 4. Generate stats if applicable
    if template.stat_generation and template.entity_type == "character":
        stats = await generate_stats(template.stat_generation)
        params["stats"] = stats

    # 5. Apply state tags
    params["state_tags"] = list(template.default_state_tags)

    # 6. Apply equipment
    if template.equipment_options:
        equipment = await generate_equipment(template.equipment_options)
        params["equipment"] = equipment

    # 7. Apply user overrides
    params.update(overrides)

    # 8. Handle inheritance (resolve parent template first)
    if template.parent_template_id:
        parent_params = await get_inherited_properties(template.parent_template_id)
        params = merge_with_parent(parent_params, params)

    # 9. Create the actual entity
    entity_id = await neo4j_create_entity(
        template.universe_id,
        template.entity_type,
        params
    )

    # 10. Set location if provided
    if location_id:
        await neo4j_create_relationship(entity_id, location_id, "LOCATED_IN")

    # 11. Create character sheet if applicable
    if template.entity_type == "character" and params.get("stats"):
        await mongodb_create_character_sheet(entity_id, {
            "stats": params["stats"],
            "equipment": params.get("equipment", [])
        })

    # 12. Track usage
    await mongodb_increment_template_usage(template_id)

    return entity_id

async def bulk_instantiate(
    template_id: UUID,
    count: int,
    location_id: UUID | None = None,
    variation_level: str = "moderate"  # none, minimal, moderate, high
) -> list[UUID]:
    """Create multiple entities from a template."""
    entity_ids = []

    for i in range(count):
        # Each entity gets unique rolls/variations
        entity_id = await instantiate_template(
            template_id,
            overrides={"_instance_number": i + 1},
            location_id=location_id
        )
        entity_ids.append(entity_id)

    return entity_ids
```

**Create Template from Entity:**

```python
async def create_template_from_entity(
    entity_id: UUID,
    template_name: str,
    variable_properties: list[str] = []
) -> UUID:
    """Generate a template based on an existing entity."""
    entity = await neo4j_get_entity(entity_id)

    # Separate fixed from variable properties
    base_props = dict(entity.properties)
    var_props = []

    for prop_path in variable_properties:
        value = get_nested(base_props, prop_path)
        del_nested(base_props, prop_path)

        # Infer generation type from value
        var_props.append(VariableProperty(
            property_path=prop_path,
            generation_type=infer_generation_type(value),
            options=[value] if isinstance(value, str) else None,
            range=(value - 2, value + 2) if isinstance(value, int) else None
        ))

    template = EntityTemplate(
        id=uuid4(),
        universe_id=entity.universe_id,
        name=template_name,
        description=f"Template based on {entity.name}",
        entity_type=entity.entity_type,
        base_properties=base_props,
        variable_properties=var_props,
        naming_pattern=NamingPattern(type=NamingType.USER, pattern=None),
        default_state_tags=list(entity.state_tags),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        usage_count=0
    )

    return await mongodb_create_entity_template(template.universe_id, template)
```

**Dependencies Identified:**

1. **Random tables system** — For table-based generation
2. **LLM property generation** — For creative variation
3. **Template versioning** — Track template changes, handle entities from old versions
4. **Template marketplace/sharing** — Future: share templates between universes

---

## Q-10: Audit Trail / History View

**Actor:** User (GM, Admin)
**Trigger:** Query → History, Entity → History, or troubleshooting

**Purpose:** View the complete history of changes to any entity, fact, or story element.

**Motivation:**
- Debugging contradictions requires knowing what changed and when
- Understanding character evolution over a campaign
- Identifying when/how facts were introduced
- Rollback capability for mistakes
- Compliance/transparency for shared campaigns

**Flow:**

1. **Select Subject:**
   - Entity, Fact, Story, Scene, or Universe
   - Or view global recent changes

2. **View History:**
   - Chronological list of all changes
   - Filter by: time range, author, change type
   - Show: what changed, who changed it, when, why (evidence)

3. **Drill Down:**
   - Click change to see full details
   - View before/after state
   - View related changes (cascading effects)

4. **Actions:**
   - Compare versions
   - Revert to previous state (with new fact as explanation)
   - Export history

### Implementation

**Layer 1 (Data Layer):**

```python
# History queries
neo4j_get_entity_history(entity_id, limit=50) -> list[ChangeRecord]
neo4j_get_fact_history(fact_id) -> list[ChangeRecord]
neo4j_get_story_history(story_id, include_scenes=True) -> list[ChangeRecord]
neo4j_get_universe_history(universe_id, limit=100) -> list[ChangeRecord]

# Global recent changes
neo4j_get_recent_changes(universe_id=None, limit=50, filters={}) -> list[ChangeRecord]

# Comparison
neo4j_compare_entity_versions(entity_id, time_a, time_b) -> Comparison
neo4j_get_entity_at_time(entity_id, timestamp) -> Entity

# Revert (creates new change, doesn't delete)
neo4j_revert_to_version(entity_id, timestamp, reason) -> ChangeRecord
```

**Layer 2 (Agents):**
- `ContextAssembly.get_entity_history(entity_id)` — Compile full history
- `ContextAssembly.compare_versions(entity_id, time_a, time_b)` — Diff two states
- `CanonKeeper.revert_entity(entity_id, timestamp, reason)` — Create reverting fact
- `Narrator.explain_history(history)` — Generate human-readable summary

**Layer 3 (CLI):**
```bash
# View entity history
monitor query history --entity <UUID>
monitor query history --entity <UUID> --since "2025-01-01"

# View fact history
monitor query history --fact <UUID>

# View story/scene history
monitor query history --story <UUID>
monitor query history --scene <UUID>

# View universe-wide recent changes
monitor query history --universe <UUID> --limit 100

# Compare versions
monitor query compare --entity <UUID> --time-a "2025-01-01" --time-b "2025-06-01"

# Revert
monitor manage entity revert <UUID> --to "2025-01-01" --reason "Incorrect data"
```

**Database Writes (for revert):**

| Database | Node/Collection | Data |
|----------|-----------------|------|
| Neo4j | `:Fact` | Revert fact: `{statement: "Reverted to state as of <timestamp>", authority: "gm"}` |
| Neo4j | Entity properties | Updated to historical values |
| MongoDB | `change_log` | Record of revert action |

**History Schema:**

```python
@dataclass
class ChangeRecord:
    id: UUID
    subject_type: SubjectType          # entity, fact, story, scene, relationship
    subject_id: UUID

    change_type: ChangeType
    timestamp: datetime

    # What changed
    field_path: str | None             # e.g., "state_tags", "properties.hp"
    old_value: Any
    new_value: Any

    # Full state snapshots (for complex changes)
    state_before: dict | None
    state_after: dict | None

    # Who/what made the change
    author: str                        # "CanonKeeper", "User:123", "System"
    authority: str                     # "gm", "player", "system"

    # Evidence
    evidence_type: str | None          # "scene", "turn", "proposal", "manual"
    evidence_id: UUID | None
    reason: str | None                 # Human-readable explanation

    # For grouped changes
    transaction_id: UUID | None        # Groups related changes together

class SubjectType(Enum):
    ENTITY = "entity"
    FACT = "fact"
    EVENT = "event"
    STORY = "story"
    SCENE = "scene"
    RELATIONSHIP = "relationship"
    AXIOM = "axiom"

class ChangeType(Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"                # Soft delete (retconned)
    STATE_TAG_ADDED = "state_tag_added"
    STATE_TAG_REMOVED = "state_tag_removed"
    RELATIONSHIP_ADDED = "relationship_added"
    RELATIONSHIP_REMOVED = "relationship_removed"
    REVERTED = "reverted"
```

**History Collection:**

The history can be stored in two ways:

**Option A: Event Sourcing in MongoDB (Recommended)**
```javascript
Collection: change_log

{
  _id: ObjectId,
  change_id: UUID,
  subject_type: "entity",
  subject_id: UUID,

  change_type: "updated",
  timestamp: ISODate,

  field_path: "state_tags",
  old_value: ["alive", "healthy"],
  new_value: ["alive", "wounded"],

  author: "CanonKeeper",
  authority: "system",

  evidence_type: "scene",
  evidence_id: UUID,
  reason: "Character took 15 damage from orc attack",

  transaction_id: UUID
}

Index: { subject_type: 1, subject_id: 1, timestamp: -1 }
Index: { timestamp: -1 }
Index: { transaction_id: 1 }
```

**Option B: Neo4j Temporal Properties**
```cypher
// Use Neo4j temporal types for version history
(:EntityInstance)-[:HAS_VERSION {valid_from, valid_to}]->(:EntityVersion)
```

**History Query Implementation:**

```python
async def get_entity_history(
    entity_id: UUID,
    since: datetime | None = None,
    until: datetime | None = None,
    change_types: list[ChangeType] | None = None,
    limit: int = 50
) -> list[ChangeRecord]:
    """Get complete change history for an entity."""

    query = {
        "subject_type": "entity",
        "subject_id": str(entity_id)
    }

    if since:
        query["timestamp"] = {"$gte": since}
    if until:
        query.setdefault("timestamp", {})["$lte"] = until
    if change_types:
        query["change_type"] = {"$in": [ct.value for ct in change_types]}

    changes = await mongodb.change_log.find(query)\
        .sort("timestamp", -1)\
        .limit(limit)\
        .to_list(limit)

    return [ChangeRecord(**c) for c in changes]

async def compare_versions(
    entity_id: UUID,
    time_a: datetime,
    time_b: datetime
) -> VersionComparison:
    """Compare entity state at two points in time."""

    # Reconstruct state at each time point
    state_a = await get_entity_at_time(entity_id, time_a)
    state_b = await get_entity_at_time(entity_id, time_b)

    # Compute diff
    diff = compute_entity_diff(state_a, state_b)

    # Get changes between times
    changes = await get_entity_history(
        entity_id,
        since=time_a,
        until=time_b
    )

    return VersionComparison(
        entity_id=entity_id,
        time_a=time_a,
        time_b=time_b,
        state_a=state_a,
        state_b=state_b,
        differences=diff,
        changes=changes
    )

async def revert_entity_to_time(
    entity_id: UUID,
    target_time: datetime,
    reason: str
) -> UUID:
    """Revert entity to state at target_time."""

    # 1. Get historical state
    historical_state = await get_entity_at_time(entity_id, target_time)
    current_state = await neo4j_get_entity(entity_id)

    # 2. Compute what needs to change
    changes_needed = compute_entity_diff(current_state, historical_state)

    # 3. Create revert fact
    revert_fact_id = await neo4j_create_fact({
        "universe_id": current_state.universe_id,
        "statement": f"{current_state.name} reverted to state as of {target_time}",
        "authority": "gm",
        "canon_level": "canon"
    })

    # 4. Apply changes
    await neo4j_update_entity(entity_id, {
        "state_tags": historical_state.state_tags,
        "properties": historical_state.properties
    })

    # 5. Log revert in change_log
    await mongodb.change_log.insert_one({
        "change_id": str(uuid4()),
        "subject_type": "entity",
        "subject_id": str(entity_id),
        "change_type": "reverted",
        "timestamp": datetime.utcnow(),
        "old_value": current_state.to_dict(),
        "new_value": historical_state.to_dict(),
        "author": "User",
        "authority": "gm",
        "evidence_type": "fact",
        "evidence_id": str(revert_fact_id),
        "reason": reason
    })

    return revert_fact_id
```

**Timeline Visualization:**

```python
async def generate_timeline_view(
    subject_id: UUID,
    subject_type: SubjectType
) -> TimelineView:
    """Generate visual timeline of changes."""

    history = await get_history(subject_id, subject_type)

    events = []
    for change in history:
        events.append(TimelineEvent(
            timestamp=change.timestamp,
            label=format_change_label(change),
            description=format_change_description(change),
            category=categorize_change(change),
            evidence_link=change.evidence_id
        ))

    return TimelineView(
        subject_id=subject_id,
        subject_type=subject_type,
        events=events,
        first_event=events[-1].timestamp if events else None,
        last_event=events[0].timestamp if events else None
    )
```

**Dependencies Identified:**

1. **Change logging integration** — All write operations must log to change_log
2. **Middleware for change capture** — Data layer needs write hooks
3. **Transaction grouping** — Related changes need transaction_id correlation
4. **State reconstruction** — Efficient replay of changes to reconstruct past states
5. **Storage considerations** — Change log can grow large; need archival strategy

---

## Additional Dependencies Summary

Based on the four use cases above, the following foundational work is required:

### New Data Layer Use Cases

| ID | Name | Description |
|----|------|-------------|
| DL-15 | Party Management | CRUD for Party nodes, membership edges |
| DL-16 | Party Inventory | Shared inventory collection in MongoDB |
| DL-17 | Entity Templates | Template CRUD and instantiation in MongoDB |
| DL-18 | Change Log | Event sourcing for audit trail |
| DL-19 | Historical Queries | Time-travel queries for entity state |

### Ontology Updates

1. **New Node: `:Party`**
   ```cypher
   (:Party {
     id: UUID,
     story_id: UUID,
     name: string,
     status: enum,
     created_at: timestamp
   })
   ```

2. **New Edge Properties: `[:MEMBER_OF]`**
   ```cypher
   [:MEMBER_OF {
     role: enum,        // pc, companion, hireling
     position: string,  // front, middle, rear
     joined_at: timestamp,
     left_at: timestamp
   }]
   ```

3. **New Edge: `[:ACTIVE_PC]`**
   - `(:Party)-[:ACTIVE_PC]->(:EntityInstance)`

4. **Scene temporal_mode field**
   - Add `temporal_mode: enum` to Scene documents
   - Values: `present`, `flashback`, `flash_forward`, `dream`

5. **Scene parent_scene_id field**
   - Link flashback scenes to their parent present scene

### MongoDB Collections

1. **`party_inventories`** — Shared party inventory
2. **`party_splits`** — Track split party state
3. **`entity_templates`** — Template definitions
4. **`change_log`** — Audit trail events (event sourcing)

### Agent Capabilities

1. **Narrator:** Past-tense generation for flashbacks
2. **Narrator:** Off-screen summary generation for split parties
3. **ContextAssembly:** Historical context assembly
4. **CanonKeeper:** Historical fact handling

---

## Integration Notes

### With Existing Use Cases

| New UC | Integrates With | How |
|--------|-----------------|-----|
| P-13 | P-1, P-2, P-3 | Party context in all play flows |
| P-13 | P-10 | Party combat with turn order |
| P-14 | P-3, P-8 | Flashback is special scene type |
| P-14 | M-22 | Memories created from flashbacks |
| M-31 | M-12-M-18 | Templates feed entity creation |
| M-31 | DL-2 | Templates reference archetypes |
| Q-10 | All writes | Everything must log changes |
| Q-10 | CF-5 | History helps debug contradictions |

### Phase Recommendations

| Use Case | Recommended Phase | Rationale |
|----------|-------------------|-----------|
| P-13 | Phase 1 (MVP) | Critical for solo play with party |
| M-31 | Phase 1 (MVP) | Major productivity improvement |
| Q-10 | Phase 2 | Important but not blocking |
| P-14 | Phase 2 | Enriches narrative but not essential |

---

# Remaining Gaps & Future Considerations

## Not Yet Addressed (Lower Priority)

### Operational Use Cases

| ID | Name | Description | Priority |
|----|------|-------------|----------|
| SYS-11 | Error Recovery | Handle DB failures, LLM rate limits, corrupted data | Medium |
| SYS-12 | Multi-User Access | User accounts, permissions, shared campaigns | Low |
| I-7 | Session Transcript Import | Import audio/text session logs | Low |

### Advanced Play Features

| ID | Name | Description | Priority |
|----|------|-------------|----------|
| P-15 | Dream Sequences | Non-canonical dream scenes (like flashbacks but fictional) | Low |
| P-16 | Parallel Timelines | Fork story at decision points, explore alternatives | Low |
| ST-6 | Random Encounter Generator | Procedural encounter generation using tables | Medium |

### World Management

| ID | Name | Description | Priority |
|----|------|-------------|----------|
| M-34 | World Snapshots | Save/restore complete universe state | Medium |
| M-35 | Universe Fork | Clone universe for "what-if" exploration | Low |
| M-36 | Scheduled Events | Events that trigger automatically at world times | Medium |

### Co-Pilot Extensions

| ID | Name | Description | Priority |
|----|------|-------------|----------|
| CF-6 | Player Handouts | Generate summaries/handouts for players | Low |
| CF-7 | Session Prep Assistant | Pre-session briefing and prep checklist | Medium |

## Architectural Clarifications Needed

### GM Authority vs Proposal Flow

**Issue:** M-* (MANAGE) use cases show direct Neo4j writes, but the architecture says only CanonKeeper writes to Neo4j.

**Resolution:** Document that M-* commands are **GM authority paths** that bypass the proposal/canonization flow. This is intentional:
- GM explicitly managing the world = direct authority
- Narrative-derived changes (from play) = proposal flow

**Recommendation:** Add a note to ARCHITECTURE.md clarifying this distinction.

### Indexer Agent Responsibilities

**Issue:** The Indexer agent appears in multiple contexts (ingestion, canonization, embedding) but its exact boundaries are unclear.

**Recommendation:** Create explicit agent responsibility matrix:

| Agent | Primary Responsibility | Writes To |
|-------|----------------------|-----------|
| CanonKeeper | Evaluate proposals, commit to Neo4j | Neo4j (Facts, Entities, Events) |
| Indexer | Text extraction, embedding, search indexing | Qdrant, OpenSearch, MongoDB (snippets) |
| Narrator | Generate narrative text, NPC dialogue | MongoDB (turns) |
| Resolver | Dice mechanics, action resolution | MongoDB (resolutions, proposals) |
| Orchestrator | Coordinate agents, manage scene flow | MongoDB (scenes), Neo4j (Party) |

### Card-Based Mechanics

**Issue:** SYSTEM.md mentions card-based game systems, but RS-* use cases only detail dice mechanics.

**Recommendation:** Add RS-5 or extend RS-1 to cover:
- Card deck management
- Hand drawing mechanics
- Discard and shuffle
- Card-based resolution (e.g., Savage Worlds, Deadlands)

## Schema Version Notes

The following changes constitute **v2.1** of the data model:

### New Neo4j Nodes
- `:Party` — Adventuring party tracking

### New Neo4j Edge Properties
- `[:MEMBER_OF {role, position, joined_at, left_at}]`
- `[:ACTIVE_PC]` — One-to-one from Party to EntityInstance

### New MongoDB Collections
- `party_inventories`
- `party_splits`
- `entity_templates`
- `change_log`
- `game_systems`
- `rule_overrides`
- `random_tables`

### Modified MongoDB Collections
- `scenes` — Added: `temporal_mode`, `time_ref`, `time_description`, `parent_scene_id`

### Migration Notes
- Existing data is forward-compatible (new fields are optional)
- No breaking changes to existing schemas
- `change_log` should be seeded with initial state for existing entities

---

# Summary

This gap analysis added **21 new use cases** to MONITOR:

| Category | Count | IDs |
|----------|-------|-----|
| PLAY | 2 | P-13, P-14 |
| MANAGE | 3 | M-31, M-32, M-33 |
| QUERY | 1 | Q-10 |
| DATA LAYER | 7 | DL-15 to DL-21 |

**Total use cases:** 117 (previously 96)

The system is now better equipped for:
- Solo play with multiple characters (party management)
- Historical exploration (flashbacks)
- Efficient world-building (templates)
- Debugging and transparency (audit trail)
- System-agnostic play (game systems in data layer)
