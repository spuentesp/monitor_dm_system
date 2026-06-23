"""
LLM Prompt Templates — DSPy Signatures & Modules.

LAYER: 2 (agents)

Each agent has its own DSPy Signature + Module.
- Narrator / ContextAssembly → NarratorModule, ContextAssemblyModule (ChainOfThought)
- CanonKeeper               → CanonKeeperReasoningModule, PolicyCheckModule
- ContextAssembly (queries) → QueryFormulationModule

Note: dspy.configure(lm=...) is called once in narrator.py at import time.
Subsequent imports of canonkeeper.py and context_assembly.py guard against
re-configuring via try/except on dspy.settings.lm.
"""

from monitor_agents.prompts.narrator import (
    NarratorModule,
    NarratorSignature,
    ContextAssemblyModule,
    ContextAssemblySignature,
)
from monitor_agents.prompts.canonkeeper import (
    CanonKeeperReasoningModule,
    CanonKeeperReasoningSignature,
    PolicyCheckModule,
    PolicyCheckSignature,
)
from monitor_agents.prompts.context_assembly import (
    QueryFormulationModule,
    QueryFormulationSignature,
)

# TurnIntentModule / TurnIntentSignature removed — deprecated. Resolver handles intent classification.
from monitor_agents.prompts.analyzer import (
    AxiomExtractionModule,
    AxiomExtractionSignature,
    EntityExtractionModule,
    EntityExtractionSignature,
    LoreFactExtractionModule,
    LoreFactExtractionSignature,
    GameSystemDetectionModule,
    GameSystemDetectionSignature,
    GameRuleExtractionModule,
    GameRuleExtractionSignature,
)
from monitor_agents.prompts.npc_voice import (
    NPCDirectVoiceSignature,
    NPCDirectVoiceModule,
    NPCActorSignature,
    NPCActorModule,
)
from monitor_agents.prompts.world_architect import (
    WorldArchitectModule,
    WorldArchitectSignature,
    WorldGapAnalysisModule,
    WorldGapAnalysisSignature,
)
from monitor_agents.prompts.recap import (
    RecapModule,
    RecapSignature,
)
from monitor_agents.prompts.story import (
    StoryPlannerModule,
    StoryPlannerSignature,
)
from monitor_agents.prompts.narrative_entity_extraction import (
    NarrativeEntityExtractionModule,
    NarrativeEntityExtractionSignature,
)

__all__ = [
    # Narrator
    "NarratorModule",
    "NarratorSignature",
    # Context assembly (summarisation)
    "ContextAssemblyModule",
    "ContextAssemblySignature",
    # CanonKeeper
    "CanonKeeperReasoningModule",
    "CanonKeeperReasoningSignature",
    "PolicyCheckModule",
    "PolicyCheckSignature",
    # Context assembly (query formulation)
    "QueryFormulationModule",
    "QueryFormulationSignature",
    # TurnIntentModule / TurnIntentSignature removed — deprecated. See context_assembly.py.
    # Analyzer
    "AxiomExtractionModule",
    "AxiomExtractionSignature",
    "EntityExtractionModule",
    "EntityExtractionSignature",
    "LoreFactExtractionModule",
    "LoreFactExtractionSignature",
    "GameSystemDetectionModule",
    "GameSystemDetectionSignature",
    "GameRuleExtractionModule",
    "GameRuleExtractionSignature",
    # NPC Voice
    "NPCDirectVoiceSignature",
    "NPCDirectVoiceModule",
    "NPCActorSignature",
    "NPCActorModule",
    # World Architect
    "WorldArchitectModule",
    "WorldArchitectSignature",
    "WorldGapAnalysisModule",
    "WorldGapAnalysisSignature",
    # Recap
    "RecapModule",
    "RecapSignature",
    # Story
    "StoryPlannerModule",
    "StoryPlannerSignature",
    # Narrative entity extraction (on-the-fly)
    "NarrativeEntityExtractionModule",
    "NarrativeEntityExtractionSignature",
]
