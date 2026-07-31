"""
Conversational Loop Implementations.

MONITOR uses 4 nested loops:
1. Main Loop   - Session management (start story, continue, ingest, etc.)
2. Story Loop  - Campaign/story progression
3. Scene Loop  - Interactive scene with turns
4. Turn Logic  - Embedded in SceneLoop (user input → resolution → GM response)

See: docs/architecture/CONVERSATIONAL_LOOPS.md

LAYER: 2 (agents)
"""

from monitor_agents.loops.character_interview_loop import (
    CharacterInterviewLoop,
    CharacterInterviewState,
    build_character_interview_graph,
)
from monitor_agents.loops.character_creation_loop import (
    CharacterCreationLoop,
    CharacterCreationState,
    build_character_creation_graph,
)
from monitor_agents.loops.conversation_loop import (
    ConversationLoop,
    ConversationState,
    build_conversation_graph,
)
from monitor_agents.loops.scene_loop import SceneLoop, SceneState, build_scene_graph

# TurnLoop removed — dead code. SceneLoop handles turn-level logic directly.
from monitor_agents.loops.story_loop import StoryLoop, StoryState, build_story_graph
from monitor_agents.loops.world_building_loop import (
    WorldBuildingLoop,
    WorldBuildingState,
    build_world_building_graph,
)

__all__ = [
    "CharacterCreationLoop",
    "CharacterCreationState",
    "CharacterInterviewLoop",
    "CharacterInterviewState",
    "ConversationLoop",
    "ConversationState",
    "SceneLoop",
    "SceneState",
    "StoryLoop",
    "StoryState",
    "WorldBuildingLoop",
    "WorldBuildingState",
    "build_character_creation_graph",
    "build_character_interview_graph",
    "build_conversation_graph",
    "build_scene_graph",
    "build_story_graph",
    "build_world_building_graph",
]
