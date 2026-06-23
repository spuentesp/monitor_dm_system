"""
================================================================================
MONITOR Agents Layer (Layer 2 of 3)
================================================================================

This is the MIDDLE layer of the MONITOR stack. It provides:
- Stateless AI agents for narrative intelligence
- Loop orchestration via LangGraph StateGraph (Story, Scene, Turn, Conversation, WorldBuilding)
- LLM interactions via DSPy + instructor
- Agent coordination through loop node sequencing

ARCHITECTURE RULES:
==================
1. This package depends ONLY on monitor-data-layer (Layer 1)
2. This package does NOT import from monitor-cli (Layer 3)
3. CLI (Layer 3) imports from this package
4. Agents are STATELESS - all state lives in databases
5. There is NO monolithic Orchestrator — loops (LangGraph StateGraph) handle control flow

IMPORT HIERARCHY:
================
    cli (Layer 3)
         ↓ imports
    agents (Layer 2)  ← YOU ARE HERE
         ↓ imports
    data-layer (Layer 1)
         ↓ imports
    external libraries + databases

THE 9 AGENTS + 1 UTILITY:
=========================
1. ContextAssembly   - Retrieves context from all DBs (Neo4j, Qdrant, MongoDB)
                       Authority: READ-ONLY (no writes)

2. Narrator          - Generates narrative content (GM responses) via DSPy
                       Authority: MongoDB (turns, scenes, story outlines)

3. Resolver          - Resolves rules, dice, outcomes for all play modes
                       Authority: MongoDB (resolutions, proposals, combat)

4. CanonKeeper       - Evaluates proposals, commits canon to Neo4j (EXCLUSIVE Neo4j writer)
                       Authority: Neo4j (ALL writes), MongoDB (verdicts, proposals)

5. Indexer           - Background embedding/indexing agent
                       Authority: Qdrant (upsert/delete), OpenSearch

6. Analyzer          - Analyzes ingested content, extracts entities/facts
                       Authority: MongoDB (knowledge packs)

7. IngestionPipeline - Coordinates document ingestion end-to-end
                       Authority: MongoDB (jobs, documents), Neo4j (sources)

8. WorldArchitect    - Generates world-building content, stories, NPCs
                       Authority: MongoDB (story outlines)

9. NPCVoice          - Generates in-character NPC dialogue via DSPy
                       Authority: MongoDB (conversations)

10. GameSystemRuntime - Schema-driven game system interpreter (BaseAgent subclass)
                        Authority: READ-ONLY (no writes)

CRITICAL INVARIANT:
==================
CanonKeeper is the ONLY agent that can write to Neo4j.
All other agents propose changes via MongoDB ProposedChange documents.

================================================================================
"""

__version__ = "0.1.0"
__layer__ = 2
__layer_name__ = "agents"

from monitor_agents.base import BaseAgent
from monitor_agents.resolver import Resolver
from monitor_agents.context_assembly import ContextAssembly
from monitor_agents.narrator import Narrator
from monitor_agents.recap_agent import RecapAgent
from monitor_agents.canonkeeper import CanonKeeper
from monitor_agents.indexer import Indexer
from monitor_agents.analyzer import Analyzer
from monitor_agents.ingestion_pipeline import IngestionPipeline
from monitor_agents.npc_voice import NPCVoice
from monitor_agents.world_architect import WorldArchitect
from monitor_agents.game_system import GameSystemRuntime
from monitor_agents.plot_hooks import PlotHookAgent
from monitor_agents.llm_registry import LLMRegistry, LLMClient
from monitor_agents.app_initializer import AppInitializer
from monitor_agents.config_loader import ConfigLoader, ConfigurationError
from monitor_agents.main_menu_processor import MainMenuProcessor, MenuChoice
from monitor_agents.application_exit_handler import ApplicationExitHandler
from monitor_agents.character_creator import (
    CharacterCreator,
    ValidationError as CharacterValidationError,
)

__all__ = [
    "BaseAgent",
    "Resolver",
    "ContextAssembly",
    "Narrator",
    "RecapAgent",
    "CanonKeeper",
    "Indexer",
    "Analyzer",
    "IngestionPipeline",
    "NPCVoice",
    "WorldArchitect",
    "GameSystemRuntime",
    "PlotHookAgent",
    "LLMRegistry",
    "LLMClient",
    "AppInitializer",
    "ConfigLoader",
    "ConfigurationError",
    "MainMenuProcessor",
    "MenuChoice",
    "ApplicationExitHandler",
    "CharacterCreator",
    "CharacterValidationError",
]
