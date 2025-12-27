"""
================================================================================
MONITOR Agents Layer (Layer 2 of 3)
================================================================================

This is the MIDDLE layer of the MONITOR stack. It provides:
- Stateless AI agents for narrative intelligence
- Loop management (Main, Story, Scene, Turn)
- LLM interactions via Anthropic Claude
- Agent coordination patterns

ARCHITECTURE RULES:
==================
1. This package depends ONLY on monitor-data-layer (Layer 1)
2. This package does NOT import from monitor-cli (Layer 3)
3. CLI (Layer 3) imports from this package
4. Agents are STATELESS - all state lives in databases

IMPORT HIERARCHY:
================
    cli (Layer 3)
         ↓ imports
    agents (Layer 2)  ← YOU ARE HERE
         ↓ imports
    data-layer (Layer 1)
         ↓ imports
    external libraries + databases

THE 7 AGENTS:
============
1. Orchestrator     - Loop controller, coordinates agents
                      Authority: MongoDB (loop state), Neo4j (Story only)

2. ContextAssembly  - Retrieves context from all DBs
                      Authority: READ-ONLY (no writes)

3. Narrator         - Generates narrative content (GM responses)
                      Authority: MongoDB (turns only)

4. Resolver         - Resolves rules, dice, outcomes
                      Authority: MongoDB (resolutions, proposals)

5. CanonKeeper      - Evaluates proposals, writes to Neo4j
                      Authority: Neo4j (EXCLUSIVE), MongoDB (proposal status)

6. MemoryManager    - Manages character memories
                      Authority: MongoDB (memories), Qdrant (embeddings)

7. Indexer          - Background embedding/indexing
                      Authority: Qdrant (EXCLUSIVE), OpenSearch

CRITICAL INVARIANT:
==================
CanonKeeper is the ONLY agent that can write to Neo4j.
All other agents propose changes via MongoDB ProposedChange documents.

================================================================================
"""

__version__ = "0.1.0"
__layer__ = 2
__layer_name__ = "agents"

# Re-export key components (to be implemented)
# from monitor_agents.base import BaseAgent
# from monitor_agents.orchestrator import Orchestrator
# from monitor_agents.narrator import Narrator
# from monitor_agents.canonkeeper import CanonKeeper
# from monitor_agents.resolver import Resolver
# from monitor_agents.context_assembly import ContextAssembly
# from monitor_agents.memory_manager import MemoryManager
# from monitor_agents.indexer import Indexer
