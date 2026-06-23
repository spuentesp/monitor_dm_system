# P-13: Party Management

**Actor:** User
**Trigger:** During story creation (P-1), scene setup (P-2), or mid-scene via meta-command

**Purpose:** Manage a party of PCs/NPCs that travel and act together, supporting solo play with multiple characters.

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

| Command | Description |
|---------|-------------|
| `/party` | Show party status |
| `/party add <name>` | Add entity to party |
| `/party remove <name>` | Remove from party |
| `/switch <name>` | Change active PC |
| `/inventory` | Show party inventory |
| `/split <group1> <group2>` | Split party into groups |
| `/rejoin` | Reunite split party |

### Implementation

**Layer 1 (Data Layer):**
```python
# Party CRUD (Neo4j)
neo4j_create_party(story_id, name, members) -> party_id
neo4j_get_party(party_id) -> Party
neo4j_add_party_member(party_id, entity_id, role, position)
neo4j_remove_party_member(party_id, entity_id)
neo4j_set_active_pc(party_id, entity_id)
neo4j_update_party(party_id, params)

# Inventory & Splits (MongoDB)
mongodb_get_party_inventory(party_id) -> Inventory
mongodb_update_party_inventory(party_id, changes)
mongodb_create_party_split(party_id, groups) -> split_id
mongodb_update_party_split(split_id, active_group)
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

**Party Schema:**
```python
@dataclass
class Party:
    id: UUID
    story_id: UUID
    name: str

    members: list[PartyMember]
    active_pc_id: UUID

    formation: list[UUID] | None
    status: PartyStatus  # traveling, camping, in_scene, combat, split, resting

    created_at: datetime
    updated_at: datetime

@dataclass
class PartyMember:
    entity_id: UUID
    name: str
    role: PartyRole  # pc, companion, hireling, mount, prisoner
    position: str | None  # front, middle, rear
    joined_at: datetime
    left_at: datetime | None
```

**Database Writes:**

| Database | Node/Collection | Data |
|----------|-----------------|------|
| Neo4j | `:Party` | `{id, story_id, name, status, created_at}` |
| Neo4j | `[:MEMBER_OF]` | Edge: Entity → Party with role/position |
| Neo4j | `[:ACTIVE_PC]` | Edge: Party → current active EntityInstance |
| MongoDB | `party_inventories` | `{party_id, items, gold, encumbrance}` |
| MongoDB | `party_splits` | `{party_id, groups, active_group_index}` |

---
