# MONITOR - AI Agent Rules

> **These rules are MANDATORY for all AI agents working on MONITOR.**

---

## 🔥 CRITICAL PHASE: RESOLUTION MECHANICS (Phase 1)

**Mission**: Unblock "Autonomous Gamemaster" mode by implementing action resolution.
**Status**: DL-20 (Game Systems) Complete. Focus shifting to DL-24 & P-4.

### The 5 Critical Blockers
1. **DL-24 (Turn Resolutions)**: Schema for actions/dice outcomes (MongoDB).
2. **DL-25 (Combat State)**: Schema for combat loops (MongoDB).
3. **P-15 (Autonomous PC)**: Agent logic for PC decisions.
4. **P-16 (Combat Loop)**: Full encounter management workflow.
5. **DL-26 (Character Stats)**: Define hybrid state storage.

### "Stateless Mechanics" Rule
**Game Logic belongs in Agents, Definitions in Data Layer.**
- **Layer 1 (Data)**: Stores *Definitions* (DL-20) and *State* (Entities).
- **Layer 2 (Agents)**: Executes *Logic* (Dice rolling, math, effects).
- **Resolver Agent**: The explicit owner of mechanical resolution.

---

## Table of Contents

1. [Critical Invariants](#critical-invariants) - MUST/NEVER rules
2. [Layer Architecture](#layer-architecture) - 3-layer dependency rules
3. [Development Workflow](#development-workflow) - Use cases, branches, PRs
4. [Code Quality Standards](#code-quality-standards) - Linting, formatting, coverage
5. [Database Constraints](#database-constraints) - DB-specific rules
6. [Testing Requirements](#testing-requirements) - Unit, integration, E2E
7. [Canonization Rules](#canonization-rules) - When and how
8. [Data Model Rules](#data-model-rules) - Entities, state, authority
9. [Documentation Maintenance](#documentation-maintenance) - What to update
10. [Common Patterns](#common-patterns) - Implementation recipes
11. [Pre-Commit Checklist](#pre-commit-checklist) - Validation commands
12. [Quick Decision Tree](#quick-decision-tree) - Visual guide

---

## Critical Invariants

### What You MUST Do

1. **Evidence for All Facts**: Every canonical fact MUST have evidence via `SUPPORTED_BY` edges or `evidence_refs` property
2. **Agent Identity**: Every MCP request MUST include agent identity (agent_type, agent_id)
3. **Validate All Boundaries**: All data crossing layer boundaries MUST be validated with Pydantic
4. **UUIDs Only in Neo4j**: Neo4j MUST only use UUIDs for IDs (never MongoDB ObjectIds or external keys)
5. **Bottom-Up Implementation**: Implement from Layer 1 → Layer 2 → Layer 3 (never skip layers)
6. **Single Use Case Scope**: Each PR MUST address exactly one use case
7. **Test All Changes**: Every code change MUST add or update tests

### What You MUST NEVER Do

1. **Delete Canonical Facts**: NEVER delete from Neo4j; mark as `retconned` instead
2. **Delete Entities**: NEVER delete entities; mark `canon_level: retconned`
3. **Direct DB Access**: NEVER connect directly to databases; use MCP tools only
4. **Reference External Keys**: NEVER store MongoDB ObjectIds or external keys in Neo4j
5. **Qdrant as Authority**: NEVER treat Qdrant as authoritative; it's derived/rebuildable
6. **Per-Turn Canonization**: NEVER canonize per-turn; only at scene end (batch)
7. **Reverse Data Flow**: NEVER flow data Neo4j → MongoDB; only MongoDB → Neo4j → Qdrant
8. **Upper Layer Dependency**: NEVER import from upper layers (no upward imports)
9. **Skip-Layer Import**: NEVER skip layers (CLI cannot import data-layer)

---

## Layer Architecture

### Rule 1: Layer Dependencies Flow Downward ONLY

```
✅ ALLOWED:
   cli → agents → data-layer → external

❌ FORBIDDEN:
   data-layer → agents
   data-layer → cli
   agents → cli
   cli → data-layer (skip-layer import)
```

**Enforcement:**
- Each layer has its own `pyproject.toml`
- Run `python scripts/check_layer_dependencies.py` to validate
- CI will fail on violations

### Rule 2: CanonKeeper Has Exclusive Neo4j Write Access

```python
# ✅ CORRECT: Only CanonKeeper writes to Neo4j
# File: packages/agents/src/monitor_agents/canonkeeper.py
await self.data_layer.neo4j_create_fact(fact_data)

# ❌ FORBIDDEN: Narrator cannot write to Neo4j
# File: packages/agents/src/monitor_agents/narrator.py
await self.data_layer.neo4j_create_fact(fact_data)  # WRONG!

# ✅ CORRECT: Other agents create proposals
await self.data_layer.mongodb_create_proposal(proposal_data)
```

**Exception:** Orchestrator can create `Story` nodes in Neo4j.

### Rule 3: Implementation Order (Bottom-Up)

**Always implement: Layer 1 → Layer 2 → Layer 3**

#### Correct Order

1. **Layer 1 (Data Layer)**:
   - Create Pydantic schemas
   - Implement DB client methods
   - Create MCP tools
   - Add authority checks
   - Write tests

2. **Layer 2 (Agents)**:
   - Implement agent logic using Layer 1 MCP tools
   - Create LLM prompts
   - Write tests with mocked MCP client

3. **Layer 3 (CLI)**:
   - Create commands that call Layer 2 agents
   - Add Rich formatting
   - Write tests

#### Why This Order?

- Upper layers depend on lower layers
- You can't test agents without data-layer tools
- You can't test CLI without agents
- Building bottom-up ensures all dependencies exist

### Package Import Patterns

#### Layer 1: data-layer

```python
# ✅ ALLOWED
from neo4j import GraphDatabase
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient

# ❌ FORBIDDEN
from monitor_agents import CanonKeeper
from monitor_cli import app
```

#### Layer 2: agents

```python
# ✅ ALLOWED
from monitor_data.tools import neo4j_create_entity
from monitor_data.schemas import EntityCreate
from anthropic import Anthropic

# ❌ FORBIDDEN
from monitor_cli import commands
```

#### Layer 3: cli

```python
# ✅ ALLOWED
from monitor_agents import Orchestrator, Narrator
from typer import Typer
from rich.console import Console

# ❌ FORBIDDEN
from monitor_data.db import Neo4jClient  # Skip-layer import!
```

---

## Development Workflow

### Use Case References (Mandatory)

Every branch, commit, and PR must reference a use case ID:

- **Data Layer**: `DL-1` through `DL-14`
- **Play**: `P-1` through `P-12`
- **Manage**: `M-1` through `M-30`
- **Query**: `Q-1` through `Q-9`
- **Ingest**: `I-1` through `I-6`
- **System**: `SYS-1` through `SYS-10`
- **Co-Pilot**: `CF-1` through `CF-5`
- **Story**: `ST-1` through `ST-5`
- **Rules**: `RS-1` through `RS-4`
- **Docs**: `DOC-1`

**Branch naming:** `feature/P-6-answer-question` or `bugfix/DL-3-fix-entity-query`

**Enforcement:** Run `python scripts/require_use_case_reference.py --base <base_sha>`

### Single-Responsibility Rule

Each PR must address **exactly one use case**:

✅ **Good**:
- PR for `P-6`: Implements question answering (data-layer + agent + CLI)
- PR for `DL-3`: Adds entity query with filters (data-layer only)

❌ **Bad**:
- PR for `P-6` + `P-7` + `M-15` (multiple use cases)
- PR for "refactoring and bug fixes" (unclear scope)

**Why?**
1. Easier to review
2. Clearer git history
3. Safer to revert if needed
4. Better test isolation

### PR Template

Use `.github/pull_request_template.md`:
- State use case ID clearly
- Describe changes concisely
- List tests added
- Reference documentation updates

---

## Code Quality Standards

### Formatters and Linters

**Ruff** (linter):
```bash
ruff check .
ruff check --fix .  # Auto-fix issues
```

**Black** (formatter):
```bash
black --check .
black .  # Auto-format
```

**MyPy** (type checker):
```bash
mypy packages
```

### Coverage Requirements

Minimum coverage: **70%** for all layers (80% preferred)

```bash
pytest --cov=packages/data-layer --cov-fail-under=70
pytest --cov=packages/agents --cov-fail-under=70
pytest --cov=packages/cli --cov-fail-under=70
```

### Pre-Commit Hooks

Install pre-commit hooks to run checks automatically:

```bash
pre-commit install
```

This runs ruff, black, mypy, and pytest-unit on every commit.

---

## Database Constraints

### Neo4j Constraints

1. **UUIDs Only**: All IDs must be UUIDs (never MongoDB ObjectIds)
2. **No Deletions**: Mark nodes as `retconned`, never delete
3. **Evidence Required**: All Facts/Events must have `SUPPORTED_BY` edges
4. **Acyclic Graphs**: `CAUSES` relationships must not create cycles

Example:
```python
# ✅ CORRECT: Using UUID
entity_data = {
    "id": str(uuid4()),  # UUID
    "universe_id": str(uuid4())  # UUID
}

# ❌ FORBIDDEN: Using MongoDB ObjectId
entity_data = {
    "id": str(ObjectId()),  # WRONG!
    "scene_ref": str(ObjectId())  # WRONG!
}
```

### MongoDB Constraints

1. **Append-Only Collections**: `change_log` is append-only (never update/delete)
2. **Scene Status**: Scenes progress: `active` → `completed` → never back
3. **Proposal Status**: Proposals: `proposed` → `accepted`/`rejected`

### Qdrant Constraints

1. **Never Authoritative**: Qdrant is derived data (can be rebuilt)
2. **ID References**: All IDs point to Neo4j or MongoDB, never standalone
3. **Rebuild Strategy**: Can delete and rebuild from Neo4j + MongoDB

### Data Flow Direction

```
MongoDB (proposals) → Neo4j (canon) → Qdrant (embeddings)

❌ NEVER flow backward: Neo4j ✗→ MongoDB
```

**Why?**
- MongoDB stages proposals
- Neo4j is canonical truth
- Qdrant indexes canon for search
- Reverse flow breaks canonization model

---

## Testing Requirements

### Unit Tests

```python
# Test individual functions/methods
@pytest.mark.unit
def test_create_entity():
    entity = EntityCreate(name="Test", entity_type="character")
    assert entity.name == "Test"
```

**Required for:**
- Schema validation
- Database client methods
- MCP tools
- Agent logic
- CLI commands

### Integration Tests

```python
# Test cross-layer interactions (skipped unless RUN_INTEGRATION=1)
@pytest.mark.integration
async def test_full_canonization_flow():
    # Tests data-layer + agents working together
    pass
```

**Required for:**
- Complete use case flows
- Cross-layer operations
- Database interactions

### E2E Tests

```python
# Test full workflows (skipped unless RUN_E2E=1)
@pytest.mark.e2e
async def test_complete_scene():
    # Tests data-layer + agents + cli
    pass
```

**Required for:**
- User-facing workflows
- End-to-end scenarios

### Test Markers

- `@pytest.mark.unit` - Fast unit tests (default, always run)
- `@pytest.mark.integration` - Cross-layer tests (skipped unless `RUN_INTEGRATION=1`)
- `@pytest.mark.e2e` - Full workflow tests (skipped unless `RUN_E2E=1`)

**Enforcement:** Run `python scripts/require_tests_for_code_changes.py --base <base_sha>`

---

## Canonization Rules

### When Does Canonization Happen?

- **Primary:** End of scene (batch all proposals)
- **Optional:** Mid-scene for critical events
- **Never:** Per-turn (too expensive!)

### What Gets Canonized?

✅ Facts and Events  
✅ Entity creation  
✅ Relationship changes  
✅ State transitions  

❌ Turn transcripts (stay in MongoDB)  
❌ GM/player notes (narrative only)  
❌ Rejected proposals  

### Canonization Workflow

```
1. Player action → Turn (MongoDB)
2. Narrator generates → Proposals (MongoDB, status: proposed)
3. Scene ends → CanonKeeper evaluates proposals
4. Accepted → Facts (Neo4j, status: canon)
5. Rejected → Proposals updated (MongoDB, status: rejected)
6. Scene finalized → Indexer embeds summary (Qdrant)
```

---

## Data Model Rules

### Two-Tier Entities

- **EntityArchetype**: Archetypes, concepts (e.g., "Wizard", "Lightsaber")
  - Has: name, entity_type, properties
  - Does NOT have: state_tags (timeless!)

- **EntityInstance**: Specific instances (e.g., "Gandalf", "Luke's Lightsaber")
  - Has: name, entity_type, properties, **state_tags**
  - Can derive from EntityArchetype via `DERIVES_FROM` relationship

### State Tags (EntityInstance only!)

- **Life**: alive, dead, unconscious, dying
- **Health**: healthy, wounded, poisoned
- **Position**: standing, prone, flying, hidden
- **Social**: hostile, friendly, allied, enemy

### Authority Hierarchy

| Authority | Weight | Examples |
|-----------|--------|----------|
| `source` | Highest | D&D PHB, official lore documents |
| `gm` | High | GM explicit declarations |
| `player` | Medium | Player actions after resolution |
| `system` | Lowest | System inferences, derived facts |

---

## Documentation Maintenance

### When to Update Docs

| Code Change | Documentation to Update |
|-------------|------------------------|
| New MCP tool | `docs/architecture/MCP_TRANSPORT.md`, `docs/architecture/DATA_LAYER_API.md` |
| New Pydantic schema | `docs/architecture/VALIDATION_SCHEMAS.md` |
| New agent capability | `docs/architecture/AGENT_ORCHESTRATION.md` |
| New use case | `docs/USE_CASES.md` |
| New loop logic | `docs/architecture/CONVERSATIONAL_LOOPS.md` |
| Data model change | `docs/ontology/ONTOLOGY.md`, `docs/ontology/ERD_DIAGRAM.md` |
| Entity type added | `docs/ontology/ENTITY_TAXONOMY.md` |

### Sync to Wiki

After significant doc changes:
```bash
bash scripts/sync_docs_to_wiki.sh
```

Requires authenticated `gh` CLI.

---

## Common Patterns

### Adding a New MCP Tool

1. Add Pydantic schema to `packages/data-layer/src/monitor_data/schemas/`
2. Implement tool in `packages/data-layer/src/monitor_data/tools/`
3. Add authority check in `packages/data-layer/src/monitor_data/middleware/auth.py`
4. Write tests in `packages/data-layer/tests/test_tools/`
5. Update `docs/architecture/MCP_TRANSPORT.md`
6. Update `docs/architecture/DATA_LAYER_API.md`

### Adding Agent Functionality

1. Implement in `packages/agents/src/monitor_agents/<agent>.py`
2. Agent calls data-layer tools via MCP client
3. Write tests with mocked MCP client
4. Update `docs/architecture/AGENT_ORCHESTRATION.md`

### Adding CLI Command

1. Create command in `packages/cli/src/monitor_cli/commands/<command>.py`
2. Command calls agents (never data-layer directly!)
3. Register in `packages/cli/src/monitor_cli/main.py`
4. Write tests
5. Update help text and README

---

## File Location Guide

| To modify... | Edit files in... | Package |
|--------------|------------------|---------|
| Neo4j client | `packages/data-layer/src/monitor_data/db/neo4j.py` | monitor-data-layer |
| MongoDB client | `packages/data-layer/src/monitor_data/db/mongodb.py` | monitor-data-layer |
| Qdrant client | `packages/data-layer/src/monitor_data/db/qdrant.py` | monitor-data-layer |
| Neo4j MCP tools | `packages/data-layer/src/monitor_data/tools/neo4j_tools.py` | monitor-data-layer |
| Entity schemas | `packages/data-layer/src/monitor_data/schemas/entities.py` | monitor-data-layer |
| Authority rules | `packages/data-layer/src/monitor_data/middleware/auth.py` | monitor-data-layer |
| Orchestrator | `packages/agents/src/monitor_agents/orchestrator.py` | monitor-agents |
| CanonKeeper | `packages/agents/src/monitor_agents/canonkeeper.py` | monitor-agents |
| Narrator | `packages/agents/src/monitor_agents/narrator.py` | monitor-agents |
| Scene loop | `packages/agents/src/monitor_agents/loops/scene_loop.py` | monitor-agents |
| Play command | `packages/cli/src/monitor_cli/commands/play.py` | monitor-cli |
| Query command | `packages/cli/src/monitor_cli/commands/query.py` | monitor-cli |
| REPL | `packages/cli/src/monitor_cli/repl/session.py` | monitor-cli |

---

## Before Starting Work

**Step 1: Read Documentation**

Required reading (in order):
1. `SYSTEM.md` - Product vision and epics
2. `STRUCTURE.md` - Complete folder definitions
3. `ARCHITECTURE.md` - Layer rules and dependency diagram
4. `docs/USE_CASES.md` - All use cases
5. `docs/AI_DOCS.md` - Quick reference
6. `.agent/rules.md` - **This file!**

**Step 2: Identify the Layer**

Ask yourself:
- Is this user-facing? → Layer 3 (CLI)
- Is this AI/LLM logic? → Layer 2 (Agents)
- Is this data access? → Layer 1 (Data-layer)

**Step 3: Verify Authority**

- Does this need to write to Neo4j? → **Must use CanonKeeper**
- Is this a read-only operation? → Any agent can do this
- Does this modify entities? → CanonKeeper only

**Step 4: Check Existing Patterns**

Before writing new code, look at similar existing code in the same layer.

---

## Pre-Commit Checklist

Before submitting a PR, run:

```bash
# Layer dependency check
python scripts/check_layer_dependencies.py

# Use case reference check
python scripts/require_use_case_reference.py --base <base_sha>

# Test requirement check
python scripts/require_tests_for_code_changes.py --base <base_sha>

# Code quality
ruff check .
black --check .
mypy packages

# Tests
pytest packages/data-layer --cov=packages/data-layer --cov-fail-under=70
pytest packages/agents --cov=packages/agents --cov-fail-under=70
pytest packages/cli --cov=packages/cli --cov-fail-under=70

# Optional: Integration/E2E
RUN_INTEGRATION=1 pytest -m integration
RUN_E2E=1 pytest -m e2e
```

Or use the workflow: `/pre-commit-checks`

---

## Quick Decision Tree

```
Need to add code?
├─ Is it user-facing?
│  └─ YES → Layer 3 (CLI)
│
├─ Is it AI/LLM logic?
│  └─ YES → Layer 2 (Agents)
│     ├─ Does it write to Neo4j?
│     │  └─ YES → Must be in CanonKeeper
│     └─ NO → Any agent
│
└─ Is it data access?
   └─ YES → Layer 1 (Data-layer)
      ├─ Add schema first
      ├─ Then DB client method
      ├─ Then MCP tool
      └─ Then authority check
```

---

## Summary

**The 7 Golden Rules:**
1. **Layer boundaries are sacred** - Never import upward
2. **CanonKeeper owns Neo4j writes** - All others use proposals
3. **Use case IDs are mandatory** - Every change references one
4. **Tests are required** - No code without tests
5. **Evidence is mandatory** - No canonical facts without provenance
6. **Canonization at scene end** - Batch, not per-turn
7. **Follow existing patterns** - Look at similar code first

**Remember:**
- UUIDs only in Neo4j (never external keys)
- Never delete from Neo4j (mark `retconned`)
- Never treat Qdrant as authoritative (derived index)
- Implement bottom-up (Layer 1 → 2 → 3)
- One use case per PR
- Update docs alongside code

---

**These rules ensure MONITOR maintains its canonical integrity and architectural consistency. Follow them strictly!**
