# ruff: noqa: E402
from typing import Any

"""
Pydantic schemas for generated NPC profiles and scene prompts.

These are the OUTPUT of the NPC/Scene Generator — not stored in KnowledgePack,
but returned to the caller for use in play sessions.

LAYER: 1 (data-layer)
"""

from pydantic import BaseModel, Field


class SceneBehavioralTrigger(BaseModel):
    """A hidden reaction a GM can use when certain topics arise."""

    trigger_topic: str = Field(max_length=200, description="Topic that activates this trigger")
    reaction: str = Field(max_length=500, description="How the NPC reacts emotionally/physically")
    gm_note: str | None = Field(None, max_length=300, description="Secret GM-only context")


class GeneratedNPCProfile(BaseModel):
    """
    A usable NPC profile derived from ExtractedAgenda and ExtractedRandomTable data.

    Produced by NPCSceneGeneratorSignature → NPCSceneGeneratorAgent.
    Not stored in KnowledgePack — returned directly to the caller.
    """

    name: str = Field(max_length=200)
    role: str = Field(max_length=200, description="Social role: tavern keeper, city guard, merchant")
    personality_summary: str = Field(max_length=500)
    current_goal: str = Field(max_length=500, description="Driven by an ExtractedAgenda")
    agenda_title: str | None = Field(None, max_length=200, description="Which agenda drives them")
    behavior_triggers: list[SceneBehavioralTrigger] = Field(default_factory=list)
    suggested_dialogue_hooks: list[str] = Field(
        default_factory=list,
        description="3-5 short lines the NPC might say to start a conversation",
    )
    suggested_scene_invitations: list[str] = Field(
        default_factory=list, description="How to invite the party into a scene with this NPC"
    )
    tags: list[str] = Field(default_factory=list)


class ScenePrompt(BaseModel):
    """
    A generated scene setup derived from ExtractedRandomTable and ExtractedAgenda data.

    Produced by NPCSceneGeneratorSignature → NPCSceneGeneratorAgent.
    Not stored in KnowledgePack — returned directly to the caller.
    """

    title: str = Field(max_length=200)
    setup: str = Field(max_length=1000, description="1-3 sentence scene setup")
    npcs_involved: list[str] = Field(
        default_factory=list, description="Names of GeneratedNPCProfile instances involved"
    )
    random_table_rolls: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The dice rolls made to generate this scene (table name + roll + result)",
    )
    agenda_clocks_active: list[str] = Field(
        default_factory=list, description="Agenda titles whose clocks are relevant to this scene"
    )
    suggested_conflict: str | None = Field(None, max_length=500, description="Core dramatic tension in this scene")
    tags: list[str] = Field(default_factory=list)


class NPCSceneGeneratorOutput(BaseModel):
    """Combined output from the NPC/Scene Generator."""

    npcs: list[GeneratedNPCProfile] = Field(default_factory=list)
    scenes: list[ScenePrompt] = Field(default_factory=list)
    generated_from_pack_id: str | None = Field(None, max_length=200)
