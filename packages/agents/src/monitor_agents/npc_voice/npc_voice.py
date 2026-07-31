"""
DSPy Signatures and Modules for the NPCVoice agent.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_data schemas

NPCVoice has two active modes — each gets its own Signature + Module:

  NPCDirectVoiceModule   — In-character real-time dialogue (DIRECT mode).
                           Uses ModelRole.LIGHT (fast, cheap: Haiku / Flash).
                           NPC speaks directly to the player, no GM wrapper.

  NPCActorModule         — Out-of-character actor reflection (ACTOR mode).
                           Uses ModelRole.LIGHT (small context, no premium needed).
                           NPC speaks AS an actor analysing their role.

The in-scene narration mode (SCENE) is handled by the Narrator via its own
NarratorModule — no separate DSPy module needed here.
"""

import dspy
from monitor_data.schemas.llm_config import ModelRole

from monitor_agents.dspy_runtime import dspy_context_for

# =============================================================================
# SIGNATURES
# =============================================================================


class NPCDirectVoiceSignature(dspy.Signature):  # type: ignore[misc]
    """
    Speak directly AS an NPC in a real-time dialogue exchange.

    You ARE this character. Respond only with the NPC's words and minimal
    action beats (e.g., *looks away*). Do not include GM narration or
    scene description. Stay strictly in character.

    Use the NPC's personality profile, current emotional state, memories,
    and known facts to produce an authentic, consistent response.
    """

    # ── Inputs ──────────────────────────────────────────────────────────────
    npc_name: str = dspy.InputField(desc="NPC's name")
    npc_role: str = dspy.InputField(
        desc="NPC's role/occupation in the world (e.g., 'tavern keeper', 'city guard captain')"
    )
    personality_summary: str = dspy.InputField(
        desc=("Personality profile: traits, values, speech style, fears, desires. Governs voice and behavior.")
    )
    current_emotional_state: str = dspy.InputField(
        desc="NPC's dominant emotion right now (e.g., 'suspicious', 'nervous', 'guarded')"
    )
    relevant_memories: str = dspy.InputField(desc="JSON array of NPC's memories relevant to this conversation")
    known_facts: str = dspy.InputField(desc="JSON array of canonical facts this NPC knows (their knowledge boundary)")
    active_triggers: str = dspy.InputField(
        desc=(
            "JSON array of behavioral triggers currently active. "
            "Each: {condition, reaction, intensity}. Override default behavior if matched."
        )
    )
    conversation_history: str = dspy.InputField(desc="Recent conversation turns (last N exchanges) for continuity")
    profile_context: str = dspy.InputField(
        desc=(
            "Bounded cultural vocabulary, ranks, institutions, and forms of address "
            "derived from the source profile. Use only when it fits the fiction."
        )
    )
    lorebook_context: str = dspy.InputField(
        desc=(
            "Lorebook/world-info entries triggered by the current conversation. "
            "Established facts of the world — weave them in naturally when relevant, "
            "never recite them verbatim. Empty when nothing triggered."
        )
    )
    player_said: str = dspy.InputField(desc="What the player character just said or did towards this NPC")

    # ── Outputs ─────────────────────────────────────────────────────────────
    npc_response: str = dspy.OutputField(
        desc=(
            "The NPC's direct response — their words and brief action beats only. "
            "Stay in character. Match speech style from personality. "
            "1-4 sentences unless the character would naturally go longer."
        )
    )
    emotional_state_after: str = dspy.OutputField(
        desc=(
            "NPC's dominant emotional state AFTER this exchange. "
            "May differ from current_emotional_state if the conversation shifted it. "
            "Single word or short phrase."
        )
    )
    relationship_delta: str = dspy.OutputField(
        desc=(
            "How this exchange affected the NPC's feeling towards the player. "
            "Format: 'trust:+0.1' or 'hostility:+0.2' or 'none' if unchanged. "
            "Drives ProposedChange for relationship update."
        )
    )


class NPCActorSignature(dspy.Signature):  # type: ignore[misc]
    """
    Respond as an ACTOR who plays this NPC and is now reflecting on their role.

    The fourth wall is down. You know you are a character in a story.
    Speak analytically and thoughtfully about your character's motivations,
    secrets, and how you would behave in hypothetical situations.

    Use first person 'I' but always refer to yourself as playing this character.
    Example: 'As Aldric, I would react with hostility here because...'
    """

    # ── Inputs ──────────────────────────────────────────────────────────────
    npc_name: str = dspy.InputField(desc="Character name this actor plays")
    full_profile: str = dspy.InputField(
        desc=(
            "Complete NPC profile: personality, backstory, secrets, motivations, "
            "relationships, and GM notes. Actor has access to GM-side info."
        )
    )
    story_context: str = dspy.InputField(
        desc="Where the story currently stands — what has happened to this character so far"
    )
    profile_context: str = dspy.InputField(
        desc=(
            "Bounded setting vocabulary, ranks, and institutions from the source profile. "
            "Use it to stay culturally native without inventing unsupported canon."
        )
    )
    conversation_history: str = dspy.InputField(desc="Prior turns in this actor-mode session")
    gm_question: str = dspy.InputField(desc="The GM's question or prompt addressed to the actor")

    # ── Outputs ─────────────────────────────────────────────────────────────
    actor_response: str = dspy.OutputField(
        desc=(
            "Actor's reflective response about their character. "
            "Analytical, insightful. May reveal secrets the character would not. "
            "2-6 sentences."
        )
    )
    canon_insight: str = dspy.OutputField(
        desc=(
            "Optional insight that should update the NPC's profile or facts. "
            "Format: 'update_profile:<field>=<value>' or 'new_fact:<statement>' or 'none'. "
            "Used to trigger ProposedChange if GM confirms."
        )
    )


# =============================================================================
# MODULES
# =============================================================================


class NPCDirectVoiceModule(dspy.Module):  # type: ignore[misc]
    """
    Predict (not ChainOfThought) — speed over reasoning depth for dialogue.

    Rationale: NPC speech is short-form, highly constrained by personality
    and context. Predict is fast and sufficient; CoT would waste tokens.
    Running under ModelRole.LIGHT (Haiku / Gemini Flash class).
    """

    def __init__(self) -> None:
        super().__init__()
        self.speak = dspy.Predict(NPCDirectVoiceSignature)

    def forward(
        self,
        npc_name: str,
        npc_role: str,
        personality_summary: str,
        current_emotional_state: str,
        relevant_memories: str,
        known_facts: str,
        active_triggers: str,
        conversation_history: str,
        profile_context: str,
        player_said: str,
        lorebook_context: str = "",
    ) -> dspy.Prediction:
        with dspy_context_for("npc_voice", ModelRole.LIGHT):
            return self.speak(
                npc_name=npc_name,
                npc_role=npc_role,
                personality_summary=personality_summary,
                current_emotional_state=current_emotional_state,
                relevant_memories=relevant_memories,
                known_facts=known_facts,
                active_triggers=active_triggers,
                conversation_history=conversation_history,
                profile_context=profile_context,
                lorebook_context=lorebook_context,
                player_said=player_said,
            )


class NPCActorModule(dspy.Module):  # type: ignore[misc]
    """
    ChainOfThought actor — reasons through character psychology before responding.

    Actor mode is used for GM prep, not live play, so latency is not critical.
    Running under ModelRole.LIGHT still (context is small).
    """

    def __init__(self) -> None:
        super().__init__()
        self.reflect = dspy.ChainOfThought(NPCActorSignature)

    def forward(
        self,
        npc_name: str,
        full_profile: str,
        story_context: str,
        profile_context: str,
        conversation_history: str,
        gm_question: str,
    ) -> dspy.Prediction:
        with dspy_context_for("npc_actor", ModelRole.LIGHT):
            return self.reflect(
                npc_name=npc_name,
                full_profile=full_profile,
                story_context=story_context,
                profile_context=profile_context,
                conversation_history=conversation_history,
                gm_question=gm_question,
            )
