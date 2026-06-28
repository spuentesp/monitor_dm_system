"""
DSPy Signatures and Modules for the Narrator agent.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_data schemas

Narrator uses DSPy ChainOfThought for creative prose generation.
This allows prompt optimization via MIPROv2/BootstrapFewShot once
session data is available, without touching the agent logic.

Split (per LIBRARY_PLAN §1.2):
- Narrator, ContextAssembly → DSPy (creative quality, reasoning chain)
- CanonKeeper, Resolver     → instructor (strict schema enforcement)
"""

from typing import Optional

import dspy

from monitor_agents.dspy_runtime import dspy_context_for
from monitor_data.schemas.llm_config import ModelRole


# =============================================================================
# SIGNATURES
# =============================================================================


class NarratorSignature(dspy.Signature):
    """
    You are a skilled tabletop RPG Game Master. Write immersive, reactive GM prose.

    Core GM craft rules that must never be violated:
    - Stay fully in-world. Never mention the game system, engine, or rules by name.
    - React to what the PLAYER did — do not write their next action for them.
    - Vary your length: simple actions get 1-2 sentences; dramatic moments get 2-3 paragraphs.
    - Failure and partial success are as interesting as victory — lean into consequences.
    - Ask one question at the end only when the situation is genuinely open; otherwise let
      the fiction breathe and wait for the player's move.
    - Show, don't tell. Describe sensory detail, not emotional labels.
    """

    # ── STATIC PREFIX (identical across turns → prompt cache hit) ──
    # These fields rarely change within a session.  Placing them first
    # enables Anthropic / OpenAI prefix caching so the LLM provider
    # re-uses the cached KV for the static portion on every turn.

    tone_context: str = dspy.InputField(
        desc=(
            "GM persona and voice guidance for this session. Sets narrative register, "
            "sentence rhythm, and thematic feel. "
            "Example: 'Terse, industrial, cosmic-dread. Short declarative sentences. "
            "Second-person present tense. Death is ordinary. The void is patient. "
            "Never reassure the player.' "
            "Match this voice precisely throughout the entire response."
        )
    )
    game_system_context: str = dspy.InputField(
        desc=(
            "JSON object describing the active game system: name, attributes (abbreviation + purpose), "
            "core mechanic, and key rules. Use this to keep narration true to the setting, "
            "reference the correct stat names from the 'stats' list, and match the system's tone. "
            "Do NOT name the system in prose — absorb its feel instead."
        )
    )
    profile_context: str = dspy.InputField(
        desc=(
            "Compact source-profile guidance: genre/tone cues, narrative frame, social hierarchy hints, "
            "and lexicon aliases that make the response feel native to the setting. Use this to absorb voice, "
            "forms of address, and institution-aware phrasing without exposing schema labels directly in prose."
        )
    )

    # ── SEMI-STATIC (changes slowly — scene entities, memories) ──
    scene_context: str = dspy.InputField(
        desc="JSON summary of entities, location, and active conditions in the scene"
    )
    memory_context: str = dspy.InputField(
        desc="Relevant character memories and past narrative excerpts"
    )
    prior_turns: str = dspy.InputField(
        desc="Recent turn history (last N turns) for conversational continuity"
    )

    # ── DYNAMIC (changes every turn) ──
    player_action: str = dspy.InputField(
        desc="The player's declared action or dialogue for this turn"
    )
    resolution_summary: str = dspy.InputField(
        desc=(
            "Mechanical outcome: 'critical_success | success | partial_success | failure | "
            "critical_failure | narrative | propose_roll:<STAT>:<DC>'. "
            "For propose_roll: describe the stakes and end with 'Roll your <stat> for me.' "
            "For narrative: no dice context — write freely. "
            "For others: the outcome is already determined — narrate its consequences."
        )
    )
    setting_anchor: str = dspy.InputField(
        desc=(
            "CRITICAL — Genre, setting, and character identity that must never change mid-session. "
            "Example: 'GENRE: SCI-FI | SETTING: A derelict salvage station | CHARACTER: Kael Draven | ROLE: void-born salvage engineer'. "
            "Never describe technology as magic, never introduce medieval elements, "
            "never change the character's name or species. This is the ground truth for setting consistency."
        )
    )
    context_summary: str = dspy.InputField(
        desc=(
            "Relevance-ranked context summary from ContextAssembly. Contains entities, memories, "
            "and plot threads most relevant to the current action. Use this to ground narration "
            "in established facts and avoid contradicting prior turns."
        )
    )

    # Outputs
    narrative_text: str = dspy.OutputField(
        desc=(
            "GM prose in the voice set by tone_context. "
            "Length: 1-2 sentences for trivial/reaction beats; 1-2 short paragraphs for "
            "standard turns; 2-3 paragraphs for dramatic turning points. "
            "Never tell the player what their character thinks/feels — describe what they "
            "perceive and what the world does next."
        )
    )
    proposed_changes: str = dspy.OutputField(
        desc=(
            "JSON array of proposed world-state changes implicit in the narration. "
            "Each item: {change_type, summary, content}. Empty array [] if none."
        )
    )
    narrative_time_elapsed: str = dspy.OutputField(
        desc=(
            "The estimated number of IN-GAME minutes that passed during this turn. "
            "A dialogue beat might be '2', a short walk '15', a long rest '480'. "
            "Return a single integer string (e.g., '10')."
        )
    )


class ContextAssemblySignature(dspy.Signature):
    """
    Rank and summarise scene context for relevance to the current player action.

    Takes raw context dumps from multiple sources and produces a compressed,
    relevance-ranked summary suitable for injection into the Narrator prompt.
    """

    player_action: str = dspy.InputField(desc="The player's current action or question")
    raw_entities: str = dspy.InputField(desc="JSON array of Neo4j entities present in the scene")
    raw_memories: str = dspy.InputField(
        desc="JSON array of character/agent memory entries from Qdrant"
    )
    raw_snippets: str = dspy.InputField(
        desc="JSON array of relevant document snippets from Qdrant semantic search"
    )
    profile_context: str = dspy.InputField(
        desc="Optional compact source-profile hints (system name, taxonomy containers, alias lexicon, canon signal terms). Use these to prefer native terminology when ranking context."
    )

    summary: str = dspy.OutputField(
        desc=(
            "Concise, relevance-ranked context summary. "
            "Include only details that directly affect the current action response. "
            "Max 600 tokens."
        )
    )


# =============================================================================
# MODULES
# =============================================================================


class NarratorModule(dspy.Module):
    """
    Narrator — writes prose.
    """

    def __init__(self) -> None:
        super().__init__()
        self.generate = dspy.Predict(NarratorSignature)

    def forward(
        self,
        tone_context: str,
        game_system_context: str,
        scene_context: str,
        profile_context: str,
        memory_context: str,
        prior_turns: str,
        player_action: str,
        resolution_summary: str,
        setting_anchor: str = "",
        context_summary: str = "",
        role: Optional[ModelRole] = None,
    ) -> dspy.Prediction:
        with dspy_context_for("narrator", role or ModelRole.HEAVY):
            # Field order matches NarratorSignature: static prefix first for caching.
            return self.generate(
                tone_context=tone_context,
                game_system_context=game_system_context,
                profile_context=profile_context,
                scene_context=scene_context,
                memory_context=memory_context,
                prior_turns=prior_turns,
                player_action=player_action,
                resolution_summary=resolution_summary,
                setting_anchor=setting_anchor,
                context_summary=context_summary,
            )


class ContextAssemblyModule(dspy.Module):
    """
    ChainOfThought context ranker — reasons about relevance before summarising.
    """

    def __init__(self) -> None:
        super().__init__()
        self.summarise = dspy.ChainOfThought(ContextAssemblySignature)

    def forward(
        self,
        player_action: str,
        raw_entities: str,
        raw_memories: str,
        raw_snippets: str,
        profile_context: str = "",
    ) -> dspy.Prediction:
        with dspy_context_for("context_assembly", ModelRole.STANDARD):
            return self.summarise(
                player_action=player_action,
                raw_entities=raw_entities,
                raw_memories=raw_memories,
                raw_snippets=raw_snippets,
                profile_context=profile_context,
            )
