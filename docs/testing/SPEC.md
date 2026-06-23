# MONITOR Contract Testing & Formal Verification Specification

> **Purpose**: Define concrete contracts, invariants, and test strategies for MONITOR using Design by Contract, Property-Based Testing, and API Contract Testing.

---

## 1. Critical System Invariants

These MUST hold at all times:

| ID | Invariant | Description | Enforcement |
|----|-----------|-------------|-------------|
| **INV-1** | CanonKeeper Exclusivity | Only CanonKeeper agent can write to Neo4j | `AUTHORITY_MATRIX` in `auth.py` |
| **INV-2** | Scene Atomicity | Scene is the atomic canonization boundary | SceneLoop flow control |
| **INV-3** | Layer Direction | Dependencies flow: CLI → Agents → DataLayer | `check_layer_dependencies.py` |
| **INV-4** | Turn Flow | Turns always go: User → Resolve → Narrate | LangGraph state machine |
| **INV-5** | Status Transitions | Scene status follows valid state machine | Pydantic + transitions table |
| **INV-6** | Proposed Change Workflow | Changes go: Proposed → CanonKeeper → Neo4j | MCP tool chain |

---

## 2. MCP Tool Contracts

### 2.1 Neo4j Tools (CanonKeeper Write Operations)

#### `neo4j_create_fact`
```
PRE:
  - universe_id exists in Neo4j
  - entity_ids (if provided) exist in Neo4j
  - source_ids (if provided) exist in Neo4j
  - scene_ids (if provided) exist in Neo4j
  - caller agent_type == "CanonKeeper"

POST:
  - Returns FactResponse with valid UUID
  - Fact linked to universe via HAS_FACT
  - Fact linked to entities via ATTRIBUTED_TO (if entity_ids provided)
  - Fact linked to sources via SUPPORTED_BY (if source_ids provided)

INV:
  - canon_level ∈ {PROPOSED, CANON, RUMOR, CHARACTER_BELIEF, PLAYER_KNOWLEDGE, RETCONNED, SUPERSEDED}
```

#### `neo4j_create_entity`
```
PRE:
  - universe_id exists
  - entity_type ∈ {CHARACTER, FACTION, LOCATION, OBJECT, CONCEPT, ORGANIZATION}
  - caller == "CanonKeeper"

POST:
  - Returns EntityResponse with valid UUID
  - Entity linked to universe
```

### 2.2 MongoDB Tools (Narrator/CanonKeeper Write Operations)

#### `mongodb_create_scene`
```
PRE:
  - story_id exists in Neo4j
  - universe_id exists in Neo4j
  - participating_entities (if provided) exist in Neo4j
  - location_ref (if provided) exists and is a LOCATION entity
  - caller ∈ {"CanonKeeper", "Narrator"}

POST:
  - Returns SceneResponse with scene_id
  - status = ACTIVE
  - created_at = now()

INV:
  - status ∈ {ACTIVE, FINALIZING, COMPLETED}
  - temporal_mode ∈ {PRESENT, FLASHBACK, FLASH_FORWARD, DREAM}
```

#### `mongodb_append_turn`
```
PRE:
  - scene_id exists
  - scene.status == ACTIVE
  - speaker ∈ {USER, ENTITY, GM, SYSTEM}
  - entity_id required when speaker == ENTITY
  - caller ∈ {"Narrator", "CanonKeeper"}

POST:
  - Returns TurnResponse with turn_id
  - Turn appended to scene.turns[-1]
  - scene.updated_at = now()

INV:
  - scene.status == ACTIVE throughout
```

### 2.3 Qdrant Tools (Indexer Write Operations)

#### `qdrant_upsert`
```
PRE:
  - collection exists
  - payload contains required fields per collection type
  - caller == "Indexer"

POST:
  - Returns upserted point ID
```

---

## 3. Scene Loop State Machine

```
┌─────────────┐
│ load_context│
└──────┬──────┘
       ▼
┌─────────────┐
│ await_user   │◄─────────────────┐
└──────┬──────┘                  │
       ▼                         │
┌─────────────┐                 │
│  resolve     │                 │
└──────┬──────┘                 │
       ▼                         │
┌─────────────┐                 │
│persist_narr │                 │
└──────┬──────┘                 │
       ▼                         │
┌─────────────┐                 │
│canonize_or_ │─────────────────┘
│  continue   │
└─────────────┘
```

### Valid State Transitions

| From | To | Trigger |
|------|-----|---------|
| ACTIVE | FINALIZING | user pauses / checkpoint |
| ACTIVE | COMPLETED | scene ends naturally |
| FINALIZING | ACTIVE | user resumes |
| FINALIZING | COMPLETED | user ends |

---

## 4. Dice Resolution Contracts

### ResolutionMechanic Interface

```python
@dataclass
class ResolutionRequest:
    action_type: ActionType
    difficulty: int  # 1-20 scale
    actor_id: UUID
    modifiers: list[Modifier]
    roll_mode: RollMode  # NORMAL, ADVANTAGE, DISADVANTAGE

@dataclass  
class ResolutionResult:
    success: bool
    roll: int
    difficulty: int
    final_target: int
    margin: int
    complications: list[Complication]
```

### Invariants
- `roll ∈ [1, 20]` (d20 system)
- `difficulty ∈ [1, 20]`
- `final_target = difficulty + sum(modifiers)`
- `margin = roll - final_target`
- `success = margin >= 0`

---

## 5. Test Strategy

### 5.1 Property-Based Tests (Hypothesis)

| Property | Test |
|----------|------|
| Dice roll | `roll ∈ [1, 20]` always |
| Modifier application | `final_target = difficulty + sum(modifiers)` |
| Scene status transitions | Only valid transitions allowed |
| UUID generation | Non-null, valid UUID format |
| Turn ordering | `turns[i].timestamp < turns[i+1].timestamp` |

### 5.2 Contract Tests (deal)

```python
@deal.pre(lambda params: params.universe_id exists)
@deal.post(lambda result: result is FactResponse)
@deal.raises(ValueError if invalid)
def neo4j_create_fact(params: FactCreate) -> FactResponse:
    ...
```

### 5.3 API Contract Tests (Schemathesis)

- Generate test cases from MCP tool schemas
- Test invalid inputs are rejected
- Test authorization is enforced
- Test response matches schema

---

## 6. Implementation Files

```
tests/
├── contracts/
│   ├── __init__.py
│   ├── test_mongodb_contracts.py    # Scene/Turn contracts
│   ├── test_neo4j_contracts.py      # Fact/Entity contracts
│   ├── test_invariants.py           # Critical system invariants
│   └── test_resolution_contracts.py # Dice mechanics contracts
├── property/
│   ├── __init__.py
│   ├── test_dice_properties.py      # Dice roll properties
│   ├── test_scene_state_machine.py  # Scene status transitions
│   └── test_uuid_generation.py      # UUID properties
├── api/
│   ├── __init__.py
│   └── test_mcp_contracts.py       # MCP server contract tests
└── conftest.py                      # Shared fixtures

packages/data-layer/src/monitor_data/
├── contracts/
│   ├── __init__.py
│   ├── scene_contracts.py           # Scene pre/post conditions
│   ├── fact_contracts.py            # Fact pre/post conditions
│   └── resolution_contracts.py     # Resolution contracts
└── invariants/
    ├── __init__.py
    ├── canon_keeper.py              # INV-1: CanonKeeper exclusivity
    ├── scene_atomicity.py           # INV-2: Scene atomicity
    └── layer_direction.py          # INV-3: Layer dependencies
```

---

## 7. Tool Configuration

### pyproject.toml additions

```toml
[tool.hypothesis]
profile = "MONITOR"
deadline = 1000  # 1 second per example

[tool.deal]
z3 = true  # Enable Z3 verification
```

### Dependencies

```
deal>=24.0.0
hypothesis>=6.0.0
schemathesis>=0.30.0
```

---

## 8. Acceptance Criteria

1. **All MCP tools have pre/post conditions documented**
2. **Property-based tests cover dice mechanics (100% coverage of ResolutionRequest paths)**
3. **Scene status transitions have formal state machine tests**
4. **CanonKeeper exclusivity is enforced by test (not just middleware)**
5. **API contract tests run against MCP server (can detect schema violations)**
6. **All tests are traceable to use case IDs (DL-*, P-*, etc.)**