---
description: Implement agent functionality (Layer 2)
---

# Implement Agent Feature

Step-by-step guide for implementing features in Layer 2 (agents).

## What Goes in Agents Layer

- AI agent implementations (7 agents)
- Loop logic (Main, Story, Scene, Turn)
- LLM prompt templates
- Agent coordination logic
- Response parsing

## What Does NOT Go Here

- Database access code (use data-layer tools via MCP)
- User interface code (that's Layer 3: cli)
- Raw database queries

## The 7 Agents

| Agent | Responsibility | Can Write to Neo4j? |
|-------|----------------|---------------------|
| **Orchestrator** | Loop management, coordination | Limited (Story only) |
| **ContextAssembly** | Context retrieval from databases | No (read-only) |
| **Narrator** | Narrative generation, GM turns | No |
| **Resolver** | Rules/dice resolution | No |
| **CanonKeeper** | Canonization, Neo4j writes | **YES (exclusive)** |
| **MemoryManager** | Character memories | No |
| **Indexer** | Background indexing | No |

## Steps

### 1. Review Agent Documentation

Read:
- `docs/architecture/AGENT_ORCHESTRATION.md` - Agent roles and coordination
- `docs/architecture/CONVERSATIONAL_LOOPS.md` - Loop structure
- `.agent/rules.md` - Critical: CanonKeeper authority rule

### 2. Verify Authority

**CRITICAL QUESTION**: Does this feature need to write to Neo4j?

- **YES** → Must be implemented in **CanonKeeper** (or Orchestrator for Story nodes)
- **NO** → Can be in any appropriate agent

**Neo4j write operations include**:
- Creating entities, facts, events
- Updating entity state
- Creating/modifying relationships
- Any `neo4j_create_*` or `neo4j_update_*` tool

### 3. Choose the Correct Agent

Based on responsibility:

- **Creating canonical data** → CanonKeeper
- **Generating narrative** → Narrator
- **Resolving player actions** → Resolver
- **Retrieving context** → ContextAssembly
- **Managing memories** → MemoryManager
- **Coordinating loops** → Orchestrator
- **Background tasks** → Indexer

### 4. Implement Agent Method

Location: `packages/agents/src/monitor_agents/<agent>.py`

Example (CanonKeeper):
```python
# packages/agents/src/monitor_agents/canonkeeper.py
from monitor_data.tools import neo4j_create_fact
from monitor_data.schemas import FactCreate

class CanonKeeper(BaseAgent):
    async def canonize_proposal(self, proposal_id: str) -> FactResponse:
        """
        Evaluate and canonize a proposal.
        
        Only CanonKeeper can write to Neo4j!
        """
        # 1. Get proposal from MongoDB
        proposal = await self.data_layer.mongodb_get_proposal(proposal_id)
        
        # 2. Evaluate authority and confidence
        if not self._should_canonize(proposal):
            await self.data_layer.mongodb_update_proposal(
                proposal_id, status="rejected"
            )
            return None
        
        # 3. Write to Neo4j (CanonKeeper exclusive!)
        fact = FactCreate(
            statement=proposal.statement,
            authority=proposal.authority,
            evidence_refs=proposal.evidence_refs  # Required!
        )
        result = await self.data_layer.neo4j_create_fact(fact)
        
        # 4. Update proposal status
        await self.data_layer.mongodb_update_proposal(
            proposal_id, status="accepted", fact_id=result.id
        )
        
        return result
```

Example (Narrator - read-only):
```python
# packages/agents/src/monitor_agents/narrator.py
from monitor_data.tools import mongodb_get_scene, neo4j_get_entity

class Narrator(BaseAgent):
    async def generate_gm_turn(self, scene_id: str, user_input: str) -> str:
        """
        Generate GM narrative response.
        
        Narrator does NOT write to Neo4j!
        """
        # 1. Get context (read-only)
        scene = await self.data_layer.mongodb_get_scene(scene_id)
        entities = await self.data_layer.neo4j_query_entities(
            universe_id=scene.universe_id
        )
        
        # 2. Build LLM prompt
        prompt = self._build_narrator_prompt(scene, entities, user_input)
        
        # 3. Call LLM
        response = await self.llm.generate(prompt)
        
        # 4. Parse and save turn (MongoDB only, not Neo4j!)
        turn = self._parse_turn(response)
        await self.data_layer.mongodb_append_turn(scene_id, turn)
        
        # 5. Create proposals (not canon yet!)
        for change in turn.proposed_changes:
            await self.data_layer.mongodb_create_proposal(change)
        
        return turn.narrative
```

### 5. Create LLM Prompts (if needed)

Location: `packages/agents/src/monitor_agents/prompts/`

Example:
```python
# packages/agents/src/monitor_agents/prompts/narrator.py
NARRATOR_SYSTEM_PROMPT = """
You are the Game Master for a {genre} campaign.
Generate engaging narrative responses based on:
- Current scene context
- Player input
- World canon
...
"""

def build_narrator_prompt(scene, entities, user_input):
    return f"""
    {NARRATOR_SYSTEM_PROMPT}
    
    Current Scene: {scene.title}
    Entities: {entities}
    Player Input: {user_input}
    
    Generate GM response:
    """
```

### 6. Write Tests with Mocked MCP Client

Location: `packages/agents/tests/`

Example:
```python
# packages/agents/tests/test_canonkeeper.py
import pytest
from unittest.mock import AsyncMock
from monitor_agents.canonkeeper import CanonKeeper

@pytest.mark.unit
async def test_canonize_proposal_success(mock_mcp_client):
    """Test successful proposal canonization."""
    # Setup mock
    mock_mcp_client.mongodb_get_proposal.return_value = {
        "id": "proposal-1",
        "statement": "Gandalf was wounded",
        "authority": "gm",
        "evidence_refs": ["scene-123"]
    }
    mock_mcp_client.neo4j_create_fact.return_value = {
        "id": "fact-1",
        "statement": "Gandalf was wounded"
    }
    
    # Execute
    keeper = CanonKeeper(data_layer=mock_mcp_client)
    result = await keeper.canonize_proposal("proposal-1")
    
    # Verify
    assert result.id == "fact-1"
    mock_mcp_client.neo4j_create_fact.assert_called_once()
```

### 7. Update Documentation

After implementation, update:
- `docs/architecture/AGENT_ORCHESTRATION.md` - If adding new agent capability
- `packages/agents/README.md` - Document new methods

## Testing Requirements

**Unit tests** (required):
- Agent methods with mocked MCP client
- LLM prompt generation
- Response parsing logic

**Integration tests** (optional):
- End-to-end with real data-layer
- Mark with `@pytest.mark.integration`

## Critical Rules for Agents

### ✅ DO

- Use data-layer tools via MCP client
- Create proposals in MongoDB
- Read from any database
- Call LLM for AI logic
- Coordinate with other agents

### ❌ DON'T

- Direct database connections (use data-layer!)
- Write to Neo4j (unless you're CanonKeeper)
- Import from CLI layer
- Skip data-layer and query DB directly

## CanonKeeper Special Responsibilities

If implementing in CanonKeeper:

1. **Evaluate proposals** - Check authority and confidence
2. **Write to Neo4j** - Create facts, entities, events
3. **Ensure evidence** - All facts must have `evidence_refs`
4. **Update proposals** - Mark as accepted/rejected
5. **Batch operations** - Canonize at scene end, not per-turn

## Common Patterns

**Read-only agent** (Narrator, Resolver, ContextAssembly):
```python
async def process(self):
    # Read from databases
    data = await self.data_layer.neo4j_get_entity(id)
    
    # Process with LLM
    result = await self.llm.generate(prompt)
    
    # Write to MongoDB only (proposals)
    await self.data_layer.mongodb_create_proposal(result)
```

**Canonization agent** (CanonKeeper):
```python
async def canonize(self, proposal_id):
    # Evaluate
    proposal = await self.data_layer.mongodb_get_proposal(proposal_id)
    
    if self._should_canonize(proposal):
        # Write to Neo4j (CanonKeeper exclusive!)
        await self.data_layer.neo4j_create_fact(...)
        
        # Update proposal
        await self.data_layer.mongodb_update_proposal(...)
```

## Before Committing

Run checks:
```bash
# Layer dependency check
python scripts/check_layer_dependencies.py

# Tests
cd packages/agents && pytest

# Linting
ruff check packages/agents
black --check packages/agents
mypy packages/agents
```

## Next Steps

After agent implementation:
1. Implement CLI: `/implement-cli`
2. Run full test suite: `/run-tests`
3. Pre-commit checks: `/pre-commit-checks`
