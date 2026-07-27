"""
DSPy Signatures and Modules for the Analyzer agent.

LAYER: 2 (agents)
IMPORTS FROM: dspy, monitor_data schemas

The Analyzer reads ingested text chunks from Qdrant and extracts structured
information from them using a series of ChainOfThought modules.

Extraction taxonomy:
  Axiom      — Ontological world truth: "Magic exists", "Gods are real"
  Entity     — Type/archetype template: "Wizard", "Dragon", "The Merchant Guild"
  LoreFact   — Canonical narrative fact: "The Sundering happened 1000 years ago"
  GameSystem — Mechanical rules system: found if the source is a rulebook

The two-step pattern used here (same as CanonKeeper):
  reasoning = AnalyzerModule()(chunks)
  structured_result = call_llm_structured(ResultSchema, reasoning_messages)

Module outputs are assembled into KnowledgePack entries by the Analyzer agent.
"""

import dspy
from monitor_data.schemas.game_systems import (
    AttributeDefinition,
    ConditionDefinition,
    CoreMechanic,
    CreationLogicStep,
    CreationStep,
    GameRule,
    NPCCreationRules,
    NPCStatBlock,
    ResolutionMechanic,
    ResourceDefinition,
    SceneryRule,
    SkillDefinition,
)
from monitor_data.schemas.knowledge_packs import (
    ExtractedAxiom,
    ExtractedCharacterProfile,
    ExtractedEntityArchetype,
    ExtractedGenerationTemplate,
    ExtractedLoreFact,
    ExtractedRandomTable,
    ExtractedRelationship,
    ExtractedToneProfile,
    ExtractedTopology,
)
from monitor_data.schemas.agendas import ExtractedAgenda
from monitor_data.schemas.plot_threads import ExtractedPlotThread
from monitor_data.schemas.llm_config import ModelRole
from typing import Any

from monitor_agents.dspy_runtime import dspy_context_for

# =============================================================================
# SIGNATURES
# =============================================================================


class AxiomExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Identify ontological world truths from source text.

    An AXIOM is something that is fundamentally true about this fictional world
    as a whole — not a mechanic or a specific historical event, but a permanent
    feature of reality in that world.

    Examples of AXIOMS:
      - "Magic exists and can be learned by any sentient being"
      - "The gods are real and occasionally intervene in mortal affairs"
      - "Faster-than-light travel is possible via jump drives"
      - "The dead cannot return to life without divine magic"

    Examples of NON-AXIOMS (do not include):
      - Game mechanics: "A character has 6 ability scores" → GameRule
      - Historical events: "The Battle of the Five Armies happened" → LoreFact
      - Entity descriptions: "Elves have pointed ears" → EntityArchetype
    """

    section_context: str = dspy.InputField(
        desc=(
            "A single coherent section of the source document. "
            "Format: '# Section: <heading path>\n\n<body text>'. "
            "The heading path shows the nesting, e.g. 'Chapter 4 > Disciplines > Animalism'."
        )
    )
    source_name: str = dspy.InputField(
        desc="Name of the source document (e.g. 'D&D 5e Player's Handbook', 'Dune novel')"
    )

    axioms_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step reasoning: "
            "(1) Which world-level truths can be inferred from these passages? "
            "(2) For each candidate, confirm it is ontological (describes reality) "
            "not mechanical (describes rules) or narrative (describes events). "
            "List each axiom with: statement, domain (magic/physics/society/religion/etc), "
            "confidence (0.0-1.0), and source_ref (page or section if visible). "
            "Format each as: AXIOM | <statement> | <domain> | <confidence> | <source_ref> | <evidence_refs_json>"
        )
    )


class EntityExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Identify entity types/archetypes from source text.

    An ENTITY ARCHETYPE is a named type or template that population members
    of a world can instantiate.  It represents a category, not an individual.

    Examples of ENTITY ARCHETYPES:
      - "Wizard" (character class / type)
      - "Dragon" (creature type)
      - "The Thieves' Guild" (faction)
      - "Tavern" (location type)
      - "Ring of Protection" (magic item type)

    Examples of NON-ARCHETYPES (do not include):
      - Specific individuals: "Gandalf" → use LoreFact for named characters
      - Pure mechanics: "Spell slots" → GameRule
      - World truths: "Magic exists" → Axiom
    """

    section_context: str = dspy.InputField(
        desc=(
            "A single coherent section of the source document. "
            "Format: '# Section: <heading path>\n\n<body text>'. "
            "The heading describes the topic; the body defines the entity in full."
        )
    )
    source_name: str = dspy.InputField(desc="Name of the source document")

    entities_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step reasoning: "
            "(1) List all named types, classes, species, factions, location types, "
            "and object categories mentioned. "
            "(2) For each, determine entity_type: "
            "character | faction | location | object | concept | organization. "
            "(3) Write a brief description and any key properties. "
            "IMPORTANT: You MUST output each entity on its own line using EXACTLY this format: "
            "ENTITY | <name> | <entity_type> | <description> | <confidence 0.0-1.0> | <source_ref> | <evidence_refs_json>"
            "Example: ENTITY | Void Monk | character | Ancient ascetics wandering the Dead Universe | 0.9 | p.16 | []"
            "Example: ENTITY | The Merchant Guild | faction | Trading organization controlling supply routes | 0.8 | ch.3 "
            "Every entity line MUST start with the word ENTITY followed by a pipe character."
        )
    )


class SourceProfileSynthesisSignature(dspy.Signature):  # type: ignore[misc]
    """
    Synthesize a structured profile of what a source appears to be before extraction.

    IMPORTANT:
    - Return structured JSON only, never prose or rewritten prompts.
    - Use TOC/index/glossary/appendix material as framing support, not as direct canon proof.
    - Confidence must be field-level so downstream consumers can ignore weak guesses.
    """

    representative_sections: str = dspy.InputField(
        desc="Representative body-text sections from the source, separated by markers."
    )
    heading_paths: str = dspy.InputField(
        desc="Heading-path outline distilled from the source's structure and section titles."
    )
    reference_signals: str = dspy.InputField(
        desc="Selected TOC/index/glossary/appendix snippets used only as support signals."
    )
    source_name: str = dspy.InputField(desc="Name of the source document")
    draft_profile_context: str = dspy.InputField(
        desc="Heuristic draft JSON built from headings/reference signals. Refine it where evidence supports changes."
    )

    profile_json: str = dspy.OutputField(
        desc=(
            "Return ONLY one JSON object, with no markdown fences or prose. "
            "Allowed keys: source_kind, world_kind, system_name, edition, family, genre_tone, narrative_frame, "
            "lore_domains, taxonomy_containers, institution_model, relationship_patterns, term_lexicon, aliases, "
            "canon_signal_terms, important_named_sets, coverage_summary, known_open_questions, confidence_by_field, "
            "evidence_refs, profile_version, prompt_version, model_used. "
            "confidence_by_field values must be 0.0-1.0. evidence_refs must be a list of objects like "
            "{ref, section_path, page_hint, note}."
        )
    )


class LoreFactExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Identify canonical lore facts from source text.

    A LORE FACT is a specific piece of established canon — a historical event,
    a relationship between entities, an ongoing state of affairs, or a named
    characteristic of a specific person/place/thing.

    Examples of LORE FACTS:
      - "The Sundering shattered the world 1000 years before the current era"
      - "Elves and Dwarves have maintained an uneasy truce since the War of Iron"
      - "The city of Waterdeep is ruled by the Lords of Waterdeep, a secret council"
      - "Arya Stark is the youngest daughter of Lord Eddard Stark"

    Examples of NON-LORE-FACTS (do not include):
      - Generic entity descriptions without specificity → EntityArchetype
      - Universal world truths → Axiom
      - Game mechanics → GameRule
    """

    section_context: str = dspy.InputField(
        desc=(
            "A single coherent section of the source document. "
            "Format: '# Section: <heading path>\n\n<body text>'. "
            "The section should contain narrative, historical, or relational content."
        )
    )
    source_name: str = dspy.InputField(desc="Name of the source document")

    lore_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step reasoning: "
            "(1) List specific historical events, named relationships, and established "
            "canonical states described in these passages. "
            "(2) For each, determine fact_type: "
            "state | relationship | attribute | occurrence. "
            "(3) List entity names referenced. "
            "IMPORTANT: You MUST output each lore fact on its own line using EXACTLY this format: "
            "LORE | <statement> | <fact_type> | <entity_names_csv> | <confidence 0.0-1.0> | <source_ref> | <evidence_refs_json> | <canon_level> | <knowledge_scope>"
            "Example: LORE | Void Monks have renounced material possessions | state | Void Monks | 0.9 | p.16 | [] | canon | world"
            "Example: LORE | The Dead Star exploded 1000 years ago | occurrence | Dead Star | 0.85 | ch.1 | [] | canon | world"
            "canon_level: proposed | canon | rumor | character_belief | player_knowledge"
            "knowledge_scope: world | character | player | rumor"
        )
    )


class GameSystemDetectionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Detect whether the source text contains RPG game system mechanics.

    A GAME SYSTEM defines the mechanical procedures of a ruleset: how dice work,
    what attributes characters have, how combat resolves, what resources exist.

    This is separate from world-lore: a rulebook contains BOTH mechanics (GameSystem)
    AND lore (Axioms + EntityArchetypes + LoreFacts).

    Indicators this is a game system source:
      - Mentions dice (d4, d6, d8, d10, d12, d20, d100)
      - Defines ability scores (Strength, Dexterity, Constitution, etc.)
      - Describes turn-based combat or action economy
      - Lists classes, levels, or advancement tables
      - Defines hit points, saving throws, armor class, or similar mechanics
    """

    source_chunks: str = dspy.InputField(
        desc=("Representative text passages from the source document. Each passage is separated by '---'.")
    )
    source_name: str = dspy.InputField(desc="Name of the source document")
    source_profile_context: str = dspy.InputField(
        desc="Optional high-confidence profile hints (taxonomy containers, lexicon, tone). Use only as framing, never as proof of unsupported mechanics."
    )

    game_system_reasoning: str = dspy.OutputField(
        desc=(
            "Reasoning: "
            "(1) Does this source describe game mechanics (YES/NO)? "
            "(2) If YES, what is the system name (e.g. 'D&D 5e', 'Pathfinder 2e', "
            "'Call of Cthulhu 7e', 'custom homebrew')? "
            "(3) What is the primary dice mechanic (e.g. 'd20 + modifier vs DC', "
            "'2d6 + stat', 'dice pool', 'percentile')? "
            "(4) What are the core attributes/ability scores? "
            "(5) Does it define character advancement (levels, XP, milestones)? "
            "(6) Describe the action economy (turns/rounds? action types?). "
            "Conclude: IS_GAME_SYSTEM:<YES|NO> | SYSTEM_NAME:<name> | DICE_MECHANIC:<description>"
        )
    )


class GameRuleExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract specific mechanical rules from game system source text.

    A GAME RULE is a concrete mechanical procedure: how something works in the
    system, how numbers are calculated, what is permitted on a turn, etc.

    Examples:
      - "Spell Slots: A wizard has 2 first-level spell slots at level 1"
      - "Armor Class: AC = 10 + Dexterity modifier (unarmored)"
      - "Attacks of Opportunity: triggered when a creature leaves a threatened square"
      - "Death Saves: On your turn while dying, roll d20. 10+ = success, 3 failures = dead"

    This is called ONLY when the source is confirmed to contain game mechanics.
    """

    section_context: str = dspy.InputField(
        desc=(
            "A single coherent section of the source document. "
            "Format: '# Section: <heading path>\n\n<body text>'. "
            "The section should contain mechanical rules or procedural descriptions."
        )
    )
    system_name: str = dspy.InputField(desc="Confirmed game system name (e.g. 'D&D 5e')")
    source_profile_context: str = dspy.InputField(
        desc="Optional high-confidence profile hints (taxonomy families, lexicon, subsystem clues). Use only as interpretation support."
    )

    rules_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step reasoning about each distinct mechanical rule. "
            "Briefly identify which rules exist before outputting structured data."
        )
    )
    rules: list[GameRule] = dspy.OutputField(desc="Structured game rules extracted from this section")


class PlotThreadExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Detect dangling plot threads — unresolved promises, threats, mysteries,
    and open narrative questions from the source text.

    A DANGLING PLOT THREAD is an open narrative hook that has NOT been resolved
    in the source text. These are promises the author made to the reader that
    still need payoff.

    Categories:
      promise      — A character promised to do something (unfulfilled)
      threat       — A looming danger that hasn't materialized yet
      mystery      — An open question or unsolved puzzle
      consequence  — An action whose outcome hasn't been determined
      relationship — A tension or bond between characters that's unresolved
      world_event  — A timeline event set up but not resolved

    Look for:
      - Foreshadowing: "Little did they know..." / "This would prove costly..."
      - Open questions: "Who murdered the Duke?" / "What lies beyond the Veil?"
      - Unfulfilled promises: "Aragorn swore he would return" (and hasn't yet)
      - Looming threats: "The Dark Lord's armies gather in the East"
      - Unresolved relationships: tension between characters
      - Incomplete quests or journeys

    Do NOT include:
      - Already resolved events (the mystery was solved, the war was won)
      - Generic setting background without narrative hooks
      - Game mechanics (those are GameRules)

    Output format (one per line):
      THREAD | <title> | <category> | <urgency:low|medium|high|critical> | <description> | <entity_names_csv> | <source_hint> | <confidence> | <evidence_refs_json>
    """

    section_context: str = dspy.InputField(
        desc=(
            "A section of the source document containing narrative content, "
            "plot hooks, character arcs, or setting events. "
            "Format: '# Section: <heading path>\n\n<body text>'."
        )
    )
    source_name: str = dspy.InputField(desc="Name of the source document")

    thread_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step reasoning: "
            "(1) Identify narrative hooks, unresolved questions, and open threads. "
            "(2) For each, classify the category and urgency. "
            "(3) List entity names involved. "
            "IMPORTANT: Output each thread on its own line: "
            "THREAD | <title> | <category> | <urgency> | <description> | <entity_names_csv> | <source_hint> | <confidence>"
        )
    )
    plot_threads: list[ExtractedPlotThread] = dspy.OutputField(
        desc="Extracted dangling plot threads. Ensure evidence_refs are included."
    )


class ToneExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract narrative style, mood, and global tone instructions from source text.

    Look for:
      - Mood/Tone/Theme chapters or sidebars.
      - Narrative style guides for the GM.
      - Descriptive prose that establishes a specific "voice" for the setting.

    Output format:
      TONE | <name> | <category> | <description> | <instruction> | <trigger_tags_csv> | <confidence>
    """

    section_context: str = dspy.InputField(desc="Section text describing mood or style")
    source_name: str = dspy.InputField(desc="Name of the source document")

    tone_reasoning: str = dspy.OutputField(desc="Reasoning about the narrative style found")
    tone_profiles: list[ExtractedToneProfile] = dspy.OutputField(desc="Extracted narrative tone profiles")


class CharacterProfileExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract narrative and psychological profiles for characters or archetypes.

    Look for:
      - Character descriptions, "How to play" guides, or NPC bios.
      - Trait lists, values, fears, and desires.
      - Speech patterns, mannerisms, and physical tics.

    Output format:
      PROFILE | <name> | <is_template:true|false> | <speech_style> | <traits_csv> | <values_csv> | <fears_csv> | <desires_csv> | <mannerisms_csv> | <confidence>
    """

    section_context: str = dspy.InputField(desc="Section text describing a character or archetype")
    source_name: str = dspy.InputField(desc="Name of the source document")

    profile_reasoning: str = dspy.OutputField(desc="Reasoning about the character's psychology")
    character_profiles: list[ExtractedCharacterProfile] = dspy.OutputField(desc="Extracted psychological profiles")


class GenerationTemplateExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract 'Recipes' for spawning NPCs on the fly.

    A Generation Template links an archetype (e.g. 'Brujah') to:
      - A mechanical Stat Block (e.g. 'Street Thug')
      - A psychological Profile (e.g. 'Angry Enforcer')
      - Random Tables (e.g. 'Biker Names', 'Melee Weapons')

    Look for:
      - GM advice on creating antagonists.
      - "Typical [Archetype]" sidebars.
      - Lists of gear or names associated with a specific group.

    Output format:
      TEMPLATE | <name> | <archetype_name> | <stat_block_name> | <profile_name> | <tables_csv> | <tier_override> | <confidence>
    """

    section_context: str = dspy.InputField(desc="Section text describing NPC variants or groups")
    source_name: str = dspy.InputField(desc="Name of the source document")
    known_entities: str = dspy.InputField(desc="Names of archetypes, stat blocks, and profiles already extracted.")

    template_reasoning: str = dspy.OutputField(desc="Reasoning about how to spawn these NPCs")
    generation_templates: list[ExtractedGenerationTemplate] = dspy.OutputField(desc="Extracted generation recipes")


class CreationLogicSynthesizerSignature(dspy.Signature):  # type: ignore[misc]
    """
    Transform text-heavy character creation steps into actionable logic steps.

    Given a list of creation steps and a known entity roster, map each step
    to a concrete generation action (e.g. choice, random_roll, formula, narrative_prompt)
    and point it to the relevant data source.

    Look for:
      - How to pick a race/class (e.g. 'choice' from 'archetype:Class').
      - How to generate stats (e.g. 'random_roll' with '4d6k3').
      - How to calculate HP/AC (e.g. 'formula' using '10 + DEX').

    Output format:
      LOGIC | <step_number> | <type> | <data_source> | <target_field> | <prompt_template> | <is_automated>
    """

    creation_steps: str = dspy.InputField(desc="The extracted text steps for character creation")
    known_entities: str = dspy.InputField(desc="List of known archetypes, stats, and random tables")

    logic_reasoning: str = dspy.OutputField(desc="Step-by-step reasoning about how to make each step actionable")
    logic_steps: list[CreationLogicStep] = dspy.OutputField(desc="The synthesized actionable logic")


# =============================================================================
# MODULE FACTORY
# =============================================================================


# =============================================================================
# MODULE FACTORY — builds all extraction modules from _MODULE_META
# =============================================================================
# Signature → (role, max_tokens_or_None, docstring)
# max_tokens=None means use the provider default (no _max_tokens override).
_MODULE_META = {
    # --- LIGHT role ---
    "EntityExtractionModule": (
        ModelRole.LIGHT,
        None,
        "Extract entity archetypes from a batch of text chunks.",
    ),
    "GameRuleExtractionModule": (
        ModelRole.LIGHT,
        16384,
        "Extract individual game rules from confirmed game system text.",
    ),
    "SectionClassifierModule": (
        ModelRole.LIGHT,
        None,
        "Classify sections as game content vs metadata — single call for all sections.",
    ),
    "SectionCategorizationModule": (
        ModelRole.LIGHT,
        None,
        "Lightweight TTRPG section categorizer using a fast local model.",
    ),
    "SectionSummaryModule": (
        ModelRole.LIGHT,
        None,
        "Summarize a single TTRPG document section — cheap/fast model.",
    ),
    # --- HEAVY role ---
    "AxiomExtractionModule": (
        ModelRole.HEAVY,
        16384,
        "Extract world axioms from a batch of text chunks.",
    ),
    "LoreFactExtractionModule": (
        ModelRole.HEAVY,
        16384,
        "Extract lore facts from a batch of text chunks.",
    ),
    "SourceProfileSynthesisModule": (
        ModelRole.HEAVY,
        8192,
        "Synthesize a structured source profile from representative content and reference signals.",
    ),
    "GameSystemDetectionModule": (
        ModelRole.HEAVY,
        None,
        "Detect whether a source contains game system mechanics.",
    ),
    "CharacterSheetExtractionModule": (
        ModelRole.HEAVY,
        16384,
        "Extract character sheet structure from confirmed game system text.",
    ),
    "CreationProcedureExtractionModule": (
        ModelRole.HEAVY,
        16384,
        "Extract character creation procedure from game system text.",
    ),
    "NPCExtractionModule": (
        ModelRole.HEAVY,
        16384,
        "Extract NPC stat blocks and NPC creation rules from game text.",
    ),
    "RandomTableExtractionModule": (
        ModelRole.HEAVY,
        16384,
        "Extract structured random tables from game text.",
    ),
    "AgendaExtractionModule": (
        ModelRole.HEAVY,
        None,
        "Extract faction agendas and clocks.",
    ),
    "TopologyExtractionModule": (
        ModelRole.HEAVY,
        None,
        "Extract spatial topology.",
    ),
    "RelationshipInferenceModule": (
        ModelRole.HEAVY,
        None,
        "Infer entity-to-entity relationships from a full entity roster (one call per source).",
    ),
    "ToneExtractionModule": (
        ModelRole.HEAVY,
        8192,
        "Extract narrative tone profiles from mood/style sections.",
    ),
    "PlotThreadExtractionModule": (
        ModelRole.HEAVY,
        8192,
        "Extract dangling plot threads — unresolved promises, threats, mysteries.",
    ),
    "CharacterProfileExtractionModule": (
        ModelRole.HEAVY,
        16384,
        "Extract character/archetype narrative profiles.",
    ),
    "GenerationTemplateExtractionModule": (
        ModelRole.HEAVY,
        8192,
        "Extract NPC generation recipes.",
    ),
    "CreationLogicSynthesizerModule": (
        ModelRole.HEAVY,
        8192,
        "Synthesize actionable logic from text creation steps.",
    ),
    "SourceMindscapeSynthesisModule": (
        ModelRole.HEAVY,
        None,
        "Synthesize a source-level semantic frame from section summaries — needs strong reasoning.",
    ),
    # --- HEAVY + custom forward ---
    "BatchedExtractionModule": (
        ModelRole.HEAVY,
        16384,
        "Extract axioms, entities, and lore from multiple sections in one call.",
    ),
}


def _make_analyzer_module(name: str, sig_name: str) -> type:
    """Dynamically manufacture a module class matching the _AnalyzerModule pattern."""
    role, max_tokens, doc = _MODULE_META[name]
    sig_cls = globals()[sig_name]

    namespace: dict[str, object] = {
        "_signature": sig_cls,
        "_role": role,
        "__doc__": doc,
    }
    if max_tokens is not None:
        namespace["_max_tokens"] = max_tokens

    cls: type = type(name, (), namespace)
    # BatchedExtractionModule shares _AnalyzerModule.forward — look it up by
    # name so the reference resolves at class-creation time (after _AnalyzerModule
    # is defined in globals), not at factory-loop time.
    if name == "BatchedExtractionModule":
        cls.forward = globals()["_AnalyzerModule"].forward  # type: ignore[method-assign, union-attr, unused-ignore, attr-defined]
    return cls


# Build the module namespace by populating it with factory-created classes.
# Runs in two stages because some signatures (SectionClassifier, SectionSummary)
# are defined much later in the file alongside their modules.
# The factory eliminates 21 near-identical class definitions while preserving
# identical runtime behavior.
_module_ns = globals()

_EARLY_MODULES = [
    "AxiomExtractionModule",
    "EntityExtractionModule",
    "LoreFactExtractionModule",
    "SourceProfileSynthesisModule",
    "GameSystemDetectionModule",
    "GameRuleExtractionModule",
]
for name in _EARLY_MODULES:
    sig_name = name.replace("Module", "Signature")
    _module_ns[name] = _make_analyzer_module(name, sig_name)

del _make_analyzer_module, _module_ns


# =============================================================================
# SECTION CLASSIFIER — filters metadata sections before extraction
# =============================================================================


class _AnalyzerModule(dspy.Module):  # type: ignore[misc]
    """
    Base class for all analyzer extraction modules.

    Subclasses declare two or three class attributes:
      _signature  — the dspy.Signature subclass to wrap
      _role       — the ModelRole tier used to select the LLM
      _max_tokens — (optional) override the provider's default max_tokens
                    for modules whose pipe-delimited output often exceeds
                    the provider default (character-sheet, NPC, rules, etc.)

    The forward method dispatches all kwargs directly to the ChainOfThought chain
    inside a role-scoped dspy context.  Subclasses that need a default kwarg
    (e.g. BatchedExtractionModule) override forward explicitly.
    """

    _signature: type
    _role: ModelRole
    _max_tokens: int | None = None

    def __init__(self) -> None:
        super().__init__()
        self._chain = dspy.ChainOfThought(self._signature)

    def forward(self, **kwargs: Any) -> dspy.Prediction:
        with dspy_context_for("analyzer", self._role, max_tokens=self._max_tokens):
            return self._chain(**kwargs)


class AxiomExtractionModule(_AnalyzerModule):
    """Extract world axioms from a batch of text chunks."""

    _signature = AxiomExtractionSignature
    _role = ModelRole.HEAVY  # Gemini Flash — axiom quality benefits from strong reasoning
    _max_tokens = 16384  # axiom batches across large sourcebooks


class EntityExtractionModule(_AnalyzerModule):
    """Extract entity archetypes from a batch of text chunks."""

    _signature = EntityExtractionSignature
    _role = ModelRole.HEAVY  # 2026-07-22: promote to HEAVY for ingestion robustness.
    # The classifier prompt returns structured output across large chunk batches;
    # quality matters more than throughput here. Routes to MiniMax-M3.


class LoreFactExtractionModule(_AnalyzerModule):
    """Extract lore facts from a batch of text chunks."""

    _signature = LoreFactExtractionSignature
    _role = ModelRole.HEAVY  # Gemini Flash — lore needs nuanced reading
    _max_tokens = 16384  # lore-dense sourcebooks produce many fact lines


class SourceProfileSynthesisModule(_AnalyzerModule):
    """Synthesize a structured source profile from representative content and reference signals."""

    _signature = SourceProfileSynthesisSignature
    _role = ModelRole.HEAVY
    _max_tokens = 8192


class GameSystemDetectionModule(_AnalyzerModule):
    """Detect whether a source contains game system mechanics."""

    _signature = GameSystemDetectionSignature
    _role = ModelRole.HEAVY  # Raised from LIGHT — benefits from strong reasoning with 48-chunk sample


class GameRuleExtractionModule(_AnalyzerModule):
    """Extract individual game rules from confirmed game system text."""

    _signature = GameRuleExtractionSignature
    # Raised from LIGHT 2026-07-21: Ollama qwen2.5 emitted rule dicts with
    # wrong key names ('name:' with trailing colon) and missing rule_type,
    # producing silent per-section extraction failures on the VtM 20th corebook.
    # MiniMax-M3 (HEAVY) emits schema-conformant JSON reliably.
    _role = ModelRole.HEAVY
    _max_tokens = 16384  # rule-dense sections can produce hundreds of RULE lines


class CharacterSheetExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract the PLAYER CHARACTER sheet / system schema from game-system text.

    *** CRITICAL RULES ***
    - Extract ONLY fields that appear on a PLAYER CHARACTER sheet.
    - Do NOT extract NPC stat blocks, monster entries, creature stat lines,
      or enemy profiles (e.g. "Gravity Biodrone", "Attack Bonus", "Morale Rating").
      NPC data is extracted separately — skip it here entirely.
    - Do NOT extract CATEGORY HEADERS as attributes. "Physical Attributes",
      "Social Attributes", "Mental Attributes", "Talents", "Skills", "Knowledges"
      are HEADINGS that group real attributes/skills — they are NOT attributes or
      skills themselves.
    - If the system has NO formal skill list (e.g. Death in Space uses only
      raw ability checks), output: SKILL | NONE
    - BACKGROUNDS (e.g. Allies, Contacts, Mentor, Retainers, Generation, Fame,
      Herd, Status) are a SEPARATE category — output them as BACKGROUND lines,
      NOT as RESOURCE or ATTR lines.

    *** ATTRIBUTE RANGES ***
    - Set min/max/default to the ACTUAL values from the source text.
    - Dice pool systems (VtM, 7th Sea, etc.): attributes are typically 1-5 (start ~2).
    - d20 systems (D&D, Fallout): attributes are typically 1-20 (start 10).
    - Small-modifier systems (Death in Space): attributes can be -3 to +3 (start 0).
    - 2d20 systems (Fallout 2d20): SPECIAL attributes are 4-12 (start 5).
    - Do NOT default to 1-20 for every system.

    *** SUCCESS TYPES ***
    - meet_or_beat: roll ≥ target number (D&D, Death in Space, Fallout 2d20)
    - count_successes: roll a pool, count dice ≥ threshold (VtM, WoD, Shadowrun)
    - highest_wins: build sets of 10 from your pool, count Raises (7th Sea 2e)

    A TTRPG system map usually includes ALL of these categories:
    - ATTRIBUTES / TRAITS / APPROACHES: Strength, Dexterity, Resolve, Panache, Wits, etc.
    - SKILLS / KNACKS / COMPETENCIES: Stealth, Athletics, Convince, Piloting, etc.
    - RESOURCES / TRACKS: Hit Points, Stress, Hero Points, Sorcery Points, Wounds, Reputation, etc.
    - BACKGROUNDS: Allies, Contacts, Mentor, Generation, Resources, Retainers, etc.
    - POWERS / OPTIONS / FAMILIES: Disciplines, Arcana, Schools, Edges, Feats, Maneuvers, Advantages, Dueling Schools, etc.
    - CONDITIONS: status effects that modify rolls (poisoned, blinded, stunned)
    - SCENERY: tags on locations that modify actions (slippery, high ground)
    - SUBSYSTEMS: ship combat, duels, social conflicts, sorcery, downtime, mass combat, investigation, etc.
    - CORE MECHANIC: the dice/cards/resolution formula and success method.

    You may be given one or MORE relevant sections pulled from character creation,
    chapter headers, appendices, glossaries, tables of contents, or indices.
    Use them together to reconstruct the full schema. If a glossary or contents page
    lists a family of terms, expand it as exhaustively as the text supports — do not
    stop after the first example.

    Extract ONLY mechanical character-facing/system-facing fields — not lore or flavor text.
    Even if fields have unfamiliar names in this system, map them into the categories below.

    Output format for each field:
      ATTR | <name> | <abbreviation> | <min> | <max> | <default> | <modifier_formula_if_any>
      SKILL | <name> | <linked_attribute_if_any> | <description>
      RESOURCE | <name> | <abbreviation> | <min> | <recovers_on> | <depleted_effect> | <calculation_if_any>
      BACKGROUND | <name> | <description>
      POWER | <name> | <category> | <description>
      CONDITION | <name> | <roll_modifier> | <roll_mode_override:advantage|disadvantage|none>
      SCENERY | <keyword> | <trigger_verbs_csv> | <roll_modifier> | <roll_mode_override:advantage|disadvantage|none>
      SUBSYSTEM | <name> | <scope> | <description>
      MECHANIC | <type:d20|dice_pool|percentile|narrative|card> | <formula> | <success_type:meet_or_beat|count_successes|highest_wins>

    Examples (d20 system — D&D):
      ATTR | Strength | STR | 1 | 20 | 10 | (VALUE-10)/2
      ATTR | Dexterity | DEX | 1 | 20 | 10 | (VALUE-10)/2
      SKILL | Stealth | Dexterity | Hiding and moving silently
      RESOURCE | Hit Points | HP | 0 | long rest | unconscious | CON*level
      CONDITION | poisoned | -2 | disadvantage
      SCENERY | high ground | attack, shoot | 2 | advantage
      MECHANIC | d20 | 1d20+modifier vs DC | meet_or_beat

    Examples (dice pool — VtM V20):
      ATTR | Strength | STR | 1 | 5 | 2 |
      ATTR | Charisma | CHA | 1 | 5 | 2 |
      SKILL | Alertness | Perception | Noticing threats and details
      SKILL | Brawl | Strength | Hand-to-hand combat
      RESOURCE | Blood Pool | BP | 0 | feeding | torpor | varies by Generation
      RESOURCE | Willpower | WP | 0 | rest or roleplay reward | vulnerable |
      BACKGROUND | Generation | How far removed from Caine; affects blood pool max
      BACKGROUND | Allies | Mortal friends who provide aid
      BACKGROUND | Retainers | Ghouls or servants bound to the vampire
      POWER | Animalism | discipline | Vampire power tree focused on beasts and instinct
      MECHANIC | dice_pool | roll Attribute+Ability in d10s, difficulty 6+ | count_successes

    Examples (raise-based — 7th Sea 2e):
      ATTR | Brawn | BRN | 1 | 5 | 2 |
      ATTR | Finesse | FIN | 1 | 5 | 2 |
      ATTR | Panache | PAN | 1 | 5 | 2 |
      SKILL | Athletics | | Physical feats and acrobatic movement
      SKILL | Weaponry | | Skill with melee weapons
      RESOURCE | Hero Points | HP | 0 | each session | lose narrative edge |
      RESOURCE | Wounds | WND | 0 | healer or rest | dramatic wound / death |
      POWER | Aldana Style | dueling_school | Castillian fencing school with bonus to Finesse attacks
      SUBSYSTEM | Ship Combat | ship | Separate ship-to-ship combat rules and crew roles
      MECHANIC | dice_pool | roll Trait + Skill d10s, build sets that sum to 10 (Raises) | highest_wins

    Examples (small-modifier d20 — Death in Space):
      ATTR | Body | BDY | -3 | 3 | 0 |
      ATTR | Dexterity | DEX | -3 | 3 | 0 |
      ATTR | Savvy | SVY | -3 | 3 | 0 |
      ATTR | Tech | TEC | -3 | 3 | 0 |
      SKILL | NONE
      RESOURCE | Hit Points | HP | 0 | rest | death |
      RESOURCE | Void Points | VP | 0 | | cosmic corruption |
      SUBSYSTEM | Ship Combat | ship | Spacecraft confrontation rules with distances and crew roles
      MECHANIC | d20 | 1d20 + ability vs DR 12 | meet_or_beat

    Examples (2d20 — Fallout):
      ATTR | Strength | S | 4 | 12 | 5 |
      ATTR | Perception | P | 4 | 12 | 5 |
      SKILL | Small Guns | Perception | Using pistols, rifles, SMGs
      RESOURCE | Hit Points | HP | 0 | rest | death | END based
      RESOURCE | Action Points | AP | 0 | each turn | no actions |
      MECHANIC | d20 | roll 2d20 under Attribute+Skill target | meet_or_beat
    """

    section_context: str = dspy.InputField(
        desc=(
            "One or more coherent sections of the source document. "
            "Format: '# Section: <heading path>\n\n<body text>' with optional '---SECTION---' separators. "
            "Focus on character creation, ability scores, skills, powers, glossary/index references, and mechanical summaries."
        )
    )
    system_name: str = dspy.InputField(desc="Confirmed game system name (e.g. 'Death in Space', 'D&D 5e')")
    source_profile_context: str = dspy.InputField(
        desc="Optional high-confidence source profile hints, especially taxonomy containers and unusual system vocabulary."
    )

    charsheet_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step reasoning about the character sheet structure: "
            "attributes, skills, resources, backgrounds, powers, subsystems, core and specialized resolution mechanics."
        )
    )
    attributes: list[AttributeDefinition] = dspy.OutputField(
        desc="Character attributes/ability scores. Ensure evidence_refs are included."
    )
    skills: list[SkillDefinition] = dspy.OutputField(desc="Character skills. Ensure evidence_refs are included.")
    resources: list[ResourceDefinition] = dspy.OutputField(desc="Tracked resources. Ensure evidence_refs are included.")
    conditions: list[ConditionDefinition] = dspy.OutputField(
        desc="Character status effects and conditions. Ensure evidence_refs are included."
    )
    scenery_rules: list[SceneryRule] = dspy.OutputField(
        desc="Location tags and scenery rules. Ensure evidence_refs are included."
    )
    core_mechanic: CoreMechanic | None = dspy.OutputField(
        desc="The primary dice/card resolution mechanic (e.g. 1d20+MOD), or null if not identifiable"
    )
    resolution_mechanics: list[ResolutionMechanic] = dspy.OutputField(
        desc="Detailed resolution mechanics beyond the core mechanic (e.g. opposed rolls, raises, degrees of success)"
    )


class CharacterSheetExtractionModule(_AnalyzerModule):
    """Extract character sheet structure from confirmed game system text."""

    _signature = CharacterSheetExtractionSignature
    _role = ModelRole.HEAVY  # richer schema mapping needs stronger reasoning across aliases/tables
    _max_tokens = 16384  # charsheet output with dozens of ATTR/SKILL/RESOURCE lines


class CreationProcedureExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract the step-by-step character creation procedure from game-system text.

    Given sections describing how to create a character in a TTRPG, extract:
    1. The ordered creation STEPS a player follows
    2. How ability scores / core attributes are generated
    3. Available backgrounds or origins (if any)
    4. Starting equipment packages (if any)
    5. Advancement / leveling rules (if any)

    Output format — one line per item, pipe-delimited:

      STEP | <number> | <type> | <title> | <instructions> | <optional:true/false> | <options_comma_separated>
      ABILITYGEN | <method> | <roll_formula> | <roll_count> | <point_budget> | <standard_array_csv> | <min_score> | <max_score>
      BACKGROUND | <name> | <description> | <skill_proficiencies_csv> | <equipment_csv>
      STARTPKG | <name> | <class_or_archetype> | <items_csv> | <gold> | <notes>
      ADVANCEMENT | <method> | <max_level> | <description>

    Step types: choose_species, choose_class, choose_background, generate_attributes,
    choose_skills, choose_equipment, choose_spells, choose_feats, calculate_derived,
    write_backstory, custom

    Ability gen methods: random_roll, point_buy, standard_array, fixed, free_assign
    Advancement methods: xp, milestone, session, story_beat, custom

    Examples:
      STEP | 1 | choose_class | Choose a Clan | Pick your vampire clan which determines Disciplines | false | Brujah, Gangrel, Malkavian, Nosferatu, Toreador, Tremere, Ventrue
      STEP | 2 | generate_attributes | Assign Attributes | Prioritize Physical/Social/Mental, distribute 7/5/3 dots | false |
      STEP | 3 | choose_skills | Choose Abilities | Distribute 13/9/5 dots among Talents/Skills/Knowledges | false |
      STEP | 4 | custom | Choose Disciplines | Select 3 dots in clan Disciplines | false |
      STEP | 5 | choose_background | Choose Backgrounds | Select 5 dots in Backgrounds | false | Allies, Contacts, Fame, Generation, Herd, Influence, Mentor, Resources, Retainers, Status
      STEP | 6 | custom | Finishing Touches | Record Humanity (7), Willpower (clan-based), blood pool | false |
      ABILITYGEN | free_assign | | | | | 1 | 5

      STEP | 1 | generate_attributes | Roll Abilities | Roll 2d4-d4 for BDY, DEX, SVY, TEC | false |
      STEP | 2 | custom | Choose Origin | Roll or pick origin giving starting gear and a bonus | false |
      STEP | 3 | choose_equipment | Starting Gear | Get equipment from origin table | false |
      STEP | 4 | custom | Determine Hit Points | Start with 1d8 HP | false |
      STEP | 5 | custom | Pick Cosmic Mutation | Roll or choose one mutation from the Void | true |
      ABILITYGEN | random_roll | 2d4-d4 | 4 | | | -3 | 3
      ADVANCEMENT | custom | | Characters gain Void Points and mutations; no traditional leveling

      7th Sea 2e (raise-based, no ability scores rolled):
      STEP | 1 | custom | Concept | Decide your Hero's high concept and goals | false |
      STEP | 2 | custom | Choose Nation | Pick nationality which sets cultural context | false | Avalon, Castille, Eisen, Montaigne, Sarmatia, Ussura, Vestenmennavenjar, Vodacce
      STEP | 3 | generate_attributes | Assign Traits | Distribute 2 points among Brawn/Finesse/Resolve/Wits/Panache (all start at 2) | false |
      STEP | 4 | choose_background | Choose Backgrounds | Select two Backgrounds that provide Skills and Advantages | false |
      STEP | 5 | choose_skills | Choose Skills | Gain skills from Backgrounds (each Background grants specific skills) | false |
      STEP | 6 | custom | Choose Advantages | Spend advantage points from Backgrounds on special abilities | false |
      STEP | 7 | custom | Arcana & Stories | Optionally choose an Arcana and set a personal Story | true |
      ABILITYGEN | free_assign | | | | | 2 | 5

      Fallout 2d20 (SPECIAL attributes):
      STEP | 1 | generate_attributes | Assign SPECIAL | Distribute points among Strength/Perception/Endurance/Charisma/Intelligence/Agility/Luck | false |
      STEP | 2 | custom | Choose Origin | Select an origin defining your pre-war or wasteland background | false | Vault Dweller, Wasteland Survivor, Brotherhood Initiate, Super Mutant, Ghoul, Mr. Handy
      STEP | 3 | choose_skills | Tag Skills | Choose 3 tag skills to gain bonus ranks | false |
      STEP | 4 | choose_feats | Choose Perks | Select starting perks based on level and SPECIAL requirements | false |
      STEP | 5 | choose_equipment | Starting Gear | Receive equipment based on origin | false |
      STEP | 6 | custom | Derived Stats | Calculate HP, Initiative, Carry Weight, Defense, Melee Damage | false |
      ABILITYGEN | point_buy | | | 5 | | 4 | 12
      ADVANCEMENT | xp | 30 | Earn XP to level up, gaining perks and skill points
    """

    section_context: str = dspy.InputField(
        desc=(
            "One or more sections from the source document covering character creation, "
            "advancement, backgrounds/origins, starting equipment, and ability generation. "
            "Format: '# Section: <heading path>\\n\\n<body text>' with '---SECTION---' separators."
        )
    )
    system_name: str = dspy.InputField(
        desc="Confirmed game system name (e.g. 'Death in Space', 'Vampire: The Masquerade')"
    )
    source_profile_context: str = dspy.InputField(
        desc="Optional high-confidence profile hints about the source's vocabulary, taxonomy containers, and subsystem boundaries."
    )

    creation_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step reasoning about the creation procedure: "
            "ordered steps, ability score generation method, backgrounds, equipment, advancement."
        )
    )
    steps: list[CreationStep] = dspy.OutputField(
        desc="Ordered character creation steps. Ensure evidence_refs are included."
    )


class CreationProcedureExtractionModule(_AnalyzerModule):
    """Extract character creation procedure from game system text."""

    _signature = CreationProcedureExtractionSignature
    _role = ModelRole.HEAVY
    _max_tokens = 16384  # creation procedure with many steps, backgrounds, equipment


class NPCExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """Extract NPC stat blocks and NPC creation rules from TTRPG text.

    You are a TTRPG game-system analyst. Extract NPC / monster / antagonist
    stat blocks and any NPC creation guidelines from the provided text.

    ── OUTPUT FORMAT ──────────────────────────────────────────────────────

    Return ONE line per extracted item using a pipe-delimited format.

    NPC stat block:
        NPC | name | tier | hp | defense | attacks_csv | specials_csv | source_ref | <evidence_refs_json>
    Where:
        tier    = minion | standard | elite | boss | brute | villain
        hp      = integer hit points / wound boxes / health levels (use 0 if N/A)
        defense = primary defense score (AC, Defence, soak, etc.)  (use 0 if N/A)
        attacks_csv = semicolon-separated "attack_name:damage" (e.g. "Claw:2d6;Bite:3d6")
        specials_csv = semicolon-separated special abilities (e.g. "Regeneration 5;Fear Aura")
        source_ref = page or section reference in the book

    NPC creation rule:
        NPCRULE | tier_name | description | stat_method
    Where:
        tier_name   = name, e.g. "Minion", "Mook", "Boss", "Extra"
        description = what this tier means in the fiction
        stat_method = how to create stats for this tier

    ── EXAMPLES ───────────────────────────────────────────────────────────

    Vampire: The Masquerade (NPCs often have condensed stat blocks):
        NPC | Street Thug | minion | 7 | 3 | Knife:2;Pistol:4 | Tough | p.352
        NPC | Archon | elite | 10 | 6 | Sword:5;Celerity Strike:8 | Celerity 3;Auspex 2 | p.413

    Death in Space (enemies are simple, few stats):
        NPC | Void Cultist | standard | 4 | 12 | Improvised Weapon:1d6 | Void-touched | p.78
        NPC | Gravity Biodrone | elite | 8 | 14 | Claw:1d8;Acid Spit:1d10 | Regeneration 1 | p.82

    7th Sea 2e (Villains/Brutes/Monsters):
        NPC | Brute Squad | brute | 0 | 0 | Group Attack:1 Wound per Brute | Act as a group | p.193
        NPC | Villain Rank 5 | villain | 0 | 0 | Scheme:varies | 5 Danger Points;Influence 3 | p.195
        NPCRULE | Brute | Faceless goons that fight in groups | 1 Strength per Brute, dissolved when Strength = 0
        NPCRULE | Villain | Named antagonists with Villainy Rank | Full stat block like a Hero, Villainy Rank = power level

    Fallout 2d20:
        NPC | Raider | standard | 8 | 1 | Pipe Pistol:4+2CD;Baseball Bat:3+2CD | | p.362
        NPC | Deathclaw | boss | 18 | 4 | Claw:8+4CD;Bite:10+5CD | Terrifying;Thick Hide 2 | p.372
        NPCRULE | Normal | Standard enemies | Full stat block with SPECIAL + skills
        NPCRULE | Notable | Tougher foes, mini-bosses | +2 HP, +1 to key skills
        NPCRULE | Major | Boss-level threats | +4 HP, +2 to key skills, extra actions

    ── RULES ──────────────────────────────────────────────────────────────

    1. Only extract ENEMY / NPC stat blocks, NOT player character examples.
    2. If the game has NPC tier/rank rules, emit NPCRULE lines for each tier.
    3. Use 0 for hp/defense when the system doesn't track those for NPCs.
    4. Prefer concrete page references.
    5. If no NPCs or NPC creation rules are found, output exactly: NONE
    """

    system_name: str = dspy.InputField(desc="Name of the game system")
    system_context: str = dspy.InputField(desc="Detected core mechanic context")
    text_chunks: str = dspy.InputField(desc="Concatenated text from bestiary, antagonist, and NPC sections")
    source_profile_context: str = dspy.InputField(
        desc="Optional high-confidence profile hints: taxonomy containers, NPC tier naming, and subsystem boundaries. Use only as framing, not as proof of unsupported stats."
    )

    npc_reasoning: str = dspy.OutputField(desc="Brief reasoning about which NPCs and NPC rules were found")
    stat_blocks: list[NPCStatBlock] = dspy.OutputField(
        desc="Extracted NPC/creature stat blocks. Ensure evidence_refs are included."
    )
    creation_rules: NPCCreationRules | None = dspy.OutputField(
        desc="NPC creation/scaling rules if found, or null. Ensure evidence_refs are included."
    )


class NPCExtractionModule(_AnalyzerModule):
    """Extract NPC stat blocks and NPC creation rules from game text."""

    _signature = NPCExtractionSignature
    _role = ModelRole.HEAVY
    _max_tokens = 16384  # bestiaries can produce dozens of NPC stat block lines


class RandomTableExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract structured random tables from TTRPG source text.

    A RANDOM TABLE is a numbered list of outcomes that a player or GM rolls on
    to determine a result. Common examples include encounter tables, loot tables,
    NPC name lists, or character background events.

    Indicators:
      - A list of numbers/ranges (e.g. "1-5", "20", "86-90")
      - A dice formula (e.g. "Roll 1d20", "2d6", "d100")
      - Column headers like "Roll", "Result", "Encounter", "Item"

    ── OUTPUT FORMAT ──────────────────────────────────────────────────────

    Return a JSON object with the random_tables field set to a list of
    ExtractedRandomTable objects. Each table has:
      - name: string
      - dice_formula: string (e.g. "1d20", "d100")
      - table_type: "encounter" | "loot" | "names" | "misc"
      - description: string
      - source_ref: string (page/reference)
      - entries: list of ExtractedTableEntry objects

    Each entry has:
      - min_roll: integer (inclusive lower bound)
      - max_roll: integer (inclusive upper bound)
      - value: string (the outcome text)
      - subtable_name: string or null (if this entry references a subtable)

    ── EXAMPLES ───────────────────────────────────────────────────────────

    Example Encounter Table:
    {
      "name": "Sewer Encounters",
      "dice_formula": "1d20",
      "table_type": "encounter",
      "description": "Random threats found in the city sewers",
      "source_ref": "p.82",
      "entries": [
        {"min_roll": 1, "max_roll": 5, "value": "1d6 Giant Rats", "subtable_name": null},
        {"min_roll": 6, "max_roll": 10, "value": "1 Otyugh", "subtable_name": null},
        {"min_roll": 11, "max_roll": 15, "value": "2d4 Cultists", "subtable_name": null},
        {"min_roll": 16, "max_roll": 20, "value": "Roll on 'Major Boss' table", "subtable_name": "Major Boss"}
      ]
    }

    Example Loot Table:
    {
      "name": "Minor Treasure",
      "dice_formula": "d100",
      "table_type": "loot",
      "description": "Small items found in pouches or crates",
      "source_ref": "ch.5",
      "entries": [
        {"min_roll": 1, "max_roll": 50, "value": "2d6 Silver Pieces", "subtable_name": null},
        {"min_roll": 51, "max_roll": 80, "value": "1 Gold Piece", "subtable_name": null},
        {"min_roll": 81, "max_roll": 95, "value": "A small sapphire worth 10gp", "subtable_name": null},
        {"min_roll": 96, "max_roll": 100, "value": "Roll on 'Uncommon Magic' table", "subtable_name": "Uncommon Magic"}
      ]
    }
    """

    section_context: str = dspy.InputField(
        desc="A single coherent section of the source document containing a random table."
    )
    source_name: str = dspy.InputField(desc="Name of the source document")

    tables_reasoning: str = dspy.OutputField(
        desc="Reasoning about the tables found in this section, their dice formulas and types."
    )
    random_tables: list[ExtractedRandomTable] = dspy.OutputField(
        desc="Structured random tables extracted from this section. Ensure evidence_refs are included."
    )


class RandomTableExtractionModule(_AnalyzerModule):
    """Extract structured random tables from game text."""

    _signature = RandomTableExtractionSignature
    _role = ModelRole.HEAVY
    _max_tokens = 16384


class AgendaExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract active faction agendas, NPC goals, and looming threats (Clocks).

    Look for:
      - Organizations working toward a specific objective.
      - Impending disasters or world-shaping events.
      - NPC personal motivations and current schemes.
      - "Fronts", "Drives", "Instincts", or "Clocks".

    ── OUTPUT FORMAT ──────────────────────────────────────────────────────
    Return ONE line per agenda using pipe-delimited format:
        AGENDA | <owner_name> | <title> | <type:faction_goal|personal_drive|world_event|threat> | <suggested_segments:4-12> | <description>
    """

    section_context: str = dspy.InputField(desc="Text section potentially containing agendas")
    source_name: str = dspy.InputField(desc="Name of the source document")

    agendas_reasoning: str = dspy.OutputField(desc="Reasoning about the drives found")
    agendas: list[ExtractedAgenda] = dspy.OutputField(desc="Structured agendas. Ensure evidence_refs are included.")


class AgendaExtractionModule(_AnalyzerModule):
    """Extract faction agendas and clocks."""

    _signature = AgendaExtractionSignature
    _role = ModelRole.HEAVY


class TopologyExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Infer spatial topology and connections between locations.

    Look for:
      - "The Great Hall leads to the Kitchen."
      - "Beneath the City lies the Sewers."
      - "A portal connects the Spire to the Void."
      - Adjacency, containment, or vertical relationships.

    ── OUTPUT FORMAT ──────────────────────────────────────────────────────
    Return ONE line per connection:
        MAP | <from_location> | <to_location> | <type:adjacent|beneath|above|portal> | <description>
    """

    section_context: str = dspy.InputField(desc="Text section containing location descriptions")
    source_name: str = dspy.InputField(desc="Name of the source document")

    topology_reasoning: str = dspy.OutputField(desc="Reasoning about the spatial layout")
    topologies: list[ExtractedTopology] = dspy.OutputField(
        desc="Spatial connections. Ensure evidence_refs are included."
    )


class TopologyExtractionModule(_AnalyzerModule):
    """Extract spatial topology."""

    _signature = TopologyExtractionSignature
    _role = ModelRole.HEAVY


class RelationshipInferenceSignature(dspy.Signature):  # type: ignore[misc]
    """
    Infer entity-to-entity relationships from a list of extracted entities.

    Given all entities extracted from a source document, identify which pairs
    are meaningfully related and how.  Only include relationships clearly
    evidenced in the source text.  Quality over quantity — skip speculative
    or trivially obvious relationships.

    Examples of relationships across different game systems:
      - "Gangrel" member_of "Camarilla" (VtM: clan belonging to a sect)
      - "Everest" subtype_of "Frame" (Lancer: mech chassis is a frame type)
      - "The Chosen" subtype_of "Playbook" (MotW: playbook is a character type)
      - "Act Under Pressure" subtype_of "Basic Move" (PbtA: move category)
      - "IPS-N" created_by "Union" (Lancer: manufacturer origin)
      - "Tenebris" located_in "The Iron Ring" (Death in Space: sector location)
      - "Aldana Style" subtype_of "Dueling School" (7th Sea: swordplay school)
    """

    entity_roster: str = dspy.InputField(
        desc=(
            "Newline-separated entity list. Each line has format: "
            "'<name> (<entity_type>[/<sub_type>][, parent=<parent>])[: <description>][ | <key>:<val>, ...]'. "
            "Use the description and property traits as evidence when inferring relationships. "
            "Example:\n"
            "Gangrel (character/clan, parent=Vampire): Feral vampires who commune with beasts "
            "| sect:Camarilla, disciplines:Protean Animalism Fortitude\n"
            "Everest (object/frame): Standard-issue GMS mech frame for all licensed pilots "
            "| manufacturer:GMS, size:1, armor:0\n"
            "The Chosen (character/playbook): A hunter destined to fight the big bad "
            "| moves:Destiny_Fulfilled+The_Big_Entrance\n"
            "Tenebris (location/sector): A dark region of space in the Iron Ring "
            "| hazard:void_corruption, population:sparse"
        )
    )
    source_name: str = dspy.InputField(desc="Name of the source document these entities came from")
    source_profile_context: str = dspy.InputField(
        desc="Optional high-confidence taxonomy/institution hints. Use them to disambiguate taxonomy vs social relationships, but never to invent unsupported edges."
    )

    relationships_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step reasoning: "
            "(1) Review entity types — factions may have members, locations may be controlled, "
            "character types may serve organizations. "
            "(2) For each candidate relationship, verify it is supported by the source material. "
            "Do NOT re-emit relationships already listed in the Known structure block. "
            "(3) List the relationships you will emit, with justification for each."
        )
    )
    relationships: list[ExtractedRelationship] = dspy.OutputField(
        desc="Inferred entity-to-entity relationships supported by the source text"
    )


class RelationshipInferenceModule(_AnalyzerModule):
    """Infer entity-to-entity relationships from a full entity roster (one call per source)."""

    _signature = RelationshipInferenceSignature
    _role = ModelRole.HEAVY


# =============================================================================
# SECTION CLASSIFIER — filters metadata sections before extraction
# =============================================================================


class SectionClassifierSignature(dspy.Signature):  # type: ignore[misc]
    """
    Classify sections of a document as game content or non-game metadata.

    You are given a list of section headings (with short previews) from a
    tabletop RPG source book.  For EACH section, decide whether it contains
    actual game content (lore, rules, character options, world-building) or
    non-game metadata (credits, legal notices, table of contents, indices,
    ISBN, author bios, advertisements, purchase watermarks, DRM text).

    Output ONE line per section using EXACTLY this format:
      SECTION | <section_number> | <classification> | <reason>

    Where <classification> is one of:
      game_content   — Lore, rules, world-building, character options, equipment, bestiary
      metadata       — Credits, copyright, legal, author bios, ads, acknowledgements
      index          — Table of contents, index, page references
      front_matter   — Title page, dedication, epigraph, foreword (not game content)
    """

    section_list: str = dspy.InputField(
        desc=(
            "Numbered list of section headings with short text previews. "
            "Format: '<N>. [<heading_path>] <first 100 chars of body>...'"
        )
    )
    source_name: str = dspy.InputField(desc="Name of the source document")

    classification_reasoning: str = dspy.OutputField(
        desc=(
            "For each section, output a classification line: "
            "SECTION | <section_number> | <classification> | <reason> "
            "classification must be one of: game_content | metadata | index | front_matter "
            "Example: SECTION | 1 | game_content | Describes character archetypes and powers "
            "Example: SECTION | 7 | metadata | Lists book illustrators and writers "
            "Example: SECTION | 3 | index | Table of contents with page numbers "
            "Every line MUST start with SECTION followed by a pipe character."
        )
    )


class SectionClassifierModule(_AnalyzerModule):
    """Classify sections as game content vs metadata — single call for all sections."""

    _signature = SectionClassifierSignature
    _role = ModelRole.HEAVY  # 2026-07-22: ingestion-stage classification must use HEAVY.
    # Per-section inputs can be very large on big PDFs (295 MB Fallout → 421 qwen
    # calls in 35 min before promotion). Routing this stage to local ollama
    # qwen2.5 makes the analyzer unrunnable on real rulebooks. HEAVY routes to
    # the connected MiniMax-M3 (or gemini-2.5-flash) provider.


# =============================================================================
# BATCHED EXTRACTION — process multiple sections in one LLM call
# =============================================================================


class BatchedExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract ALL structured knowledge from multiple document sections in one pass.

    You are given several sections of a tabletop RPG source book, separated by
    '---SECTION---' markers.  For EACH section that contains relevant content,
    extract axioms, entity archetypes, and lore facts.

    IMPORTANT EXCLUSIONS — Do NOT extract:
      - Real-world people: book authors, illustrators, editors, playtesters
      - DRM/watermark text: "John Smith (Order #12345)" is a purchase watermark
      - Publishing metadata: ISBN, copyright notices, printer information
      - Table of contents entries or index page references
      - Advertisements for other products

    OUTPUT FORMAT — Use pipe-delimited lines with these prefixes:

    For world truths (permanent features of the fictional reality):
      AXIOM | <statement> | <domain> | <confidence 0.0-1.0> | <source_ref> | <evidence_refs_json>

    For named entity categories, templates, or archetypes:
      ENTITY | <name> | <entity_type> | <sub_type> | <description> | <traits> | <confidence 0.0-1.0> | <source_ref> | <parent_entity> | <evidence_refs_json>

      entity_type (pick one): character | faction | location | object | concept | organization

      sub_type: A short (1-3 word) fine-grained classification WITHIN that entity_type.
        Examples by game system (use whatever fits the source material):
          character  + sub_type=clan         (VtM: Nosferatu, Gangrel — vampire bloodlines)
          character  + sub_type=class        (D&D: Fighter, Wizard — character classes)
          character  + sub_type=species      (D&D: Elf, Dwarf — racial archetypes)
          character  + sub_type=playbook     (PbtA: The Chosen, The Spooky — Monster of the Week playbooks)
          concept    + sub_type=discipline   (VtM: Animalism, Dominate — vampire powers)
          concept    + sub_type=spell_school (D&D: Evocation, Necromancy — arcane schools)
          concept    + sub_type=move         (PbtA: Act Under Pressure, Kick Some Ass — basic moves)
          concept    + sub_type=talent       (Lancer: Ace, Hacker, Leader — pilot talents)
          concept    + sub_type=license      (Lancer: IPS-N Blackbeard, SSC Mourning Cloak — frame licenses)
          concept    + sub_type=advantage    (7th Sea: Duelist Academy, Sorcery — character advantages)
          concept    + sub_type=trait        (Death in Space: Void corruption effects)
          object     + sub_type=frame        (Lancer: Everest, Blackbeard — mech chassis)
          object     + sub_type=ship         (Death in Space: spacecraft types)
          location   + sub_type=plane        (D&D: Underdark, Astral Sea — planar regions)
          location   + sub_type=sector       (Death in Space: The Iron Ring, Tenebris — space regions)
          location   + sub_type=city         (Any: Waterdeep, Chicago, Theah — named settlements)
          faction    + sub_type=sect         (VtM: Camarilla, Sabbat — mega-factions)
          faction    + sub_type=corp         (Lancer: IPS-N, SSC, HORUS — mech manufacturers)
          organization + sub_type=guild      (Any: Thieves' Guild, Merchant's Guild)
          organization + sub_type=crew       (Death in Space: player crew types)
        If no meaningful sub-classification applies, write "none".

      traits: Comma-separated key:value pairs capturing the 2-5 most defining attributes.
        Use ONLY alphanumeric characters, underscores, colons, and commas — no pipes, quotes, or brackets.
        Examples:
          sect:Camarilla,weakness:permanent_disfigurement,disciplines:Obfuscate+Animalism+Potence
          hit_die:d10,armor:all,saving_throws:Strength+Constitution
          plane:Underdark,population:drow+deep_dwarves+mind_flayers
          deity:Lolth,alignment:chaotic_evil,portfolio:spiders+darkness+chaos
        Leave empty ("") if no key attributes are readily extractable.

      description: ONE SENTENCE (max 160 characters) — what this entity IS, not its entire backstory.
        Good: "Feral vampire clan who master beast-communion and shapeshifting."
        Bad:  "The Gangrel are one of the thirteen clans of Cainites. They wander the wilderness..."
        If the section is long philosophy, distill it to a single defining sentence.

      parent_entity: The name of the broader category this belongs to, or "none".
        Examples: Brujah→Clan, Animalism→Discipline, Laser Pistol→Weapon,
        Blackbeard→Frame, Kick Some Ass→Basic Move, Aldana Style→Dueling School.
        Use the section heading path as a clue: "Clans > Nosferatu" → parent="Clan".
        IMPORTANT: if the broader category is itself mechanically meaningful
        (e.g. Clan, Discipline, Class, Playbook, Frame, License, Move, Dueling School,
        Spell School, Feat, Advantage), emit the child with that parent name even if
        the container is generic.

      Distinguish TAXONOMY vs SOCIAL institutions:
        - taxonomy/container examples: Clan, Discipline, Class, Weapon, Spell School,
          Playbook, Frame, License, Move Type, Dueling School, Feat Category
        - social/institution examples: Camarilla, The Church, Harpers, Union Administrative,
          IPS-N, Harrison Armory, HORUS, Scrapper Union
        - if a concept is genuinely multi-role, keep the entity socially meaningful and
          capture the overlap in traits such as roles:taxonomy_member+organization.

    For canonical lore facts (specific events, relationships, states):
      LORE | <statement> | <fact_type> | <entity_names_csv> | <confidence 0.0-1.0> | <source_ref> | <evidence_refs_json> | <canon_level> | <knowledge_scope>
      fact_type: state | relationship | attribute | occurrence
      canon_level: proposed | canon | rumor | character_belief | player_knowledge
      knowledge_scope: world | character | player | rumor

    evidence_refs_json: A JSON-formatted list of objects like [{"ref": "p.42", "section_path": "Chapter 1", "note": "Explicitly stated"}].
    Every extracted item MUST include evidence_refs containing at least the current page/section reference.

    Confidence guide:
      0.9-1.0 — Explicitly stated, unambiguous
      0.7-0.8 — Clearly implied by context
      0.5-0.6 — Reasonable inference, less certain
      Below 0.5 — Do not include
    """

    sections_context: str = dspy.InputField(
        desc=(
            "Multiple sections separated by '---SECTION---' markers. "
            "Each section starts with '# Section: <heading path>' followed by body text."
        )
    )
    source_name: str = dspy.InputField(desc="Name of the source document")
    known_graph_context: str = dspy.InputField(
        desc=(
            "Compact Cypher-style snapshot of entities and relationships already extracted "
            "from earlier sections of this document. Empty string on the first batch. "
            "Format:\n"
            "  Entities: Name:type[parent=ParentName], ...\n"
            "  Structure:\n"
            "  (Child)-[:subtype_of]->(Parent)\n"
            "  (Member)-[:member_of]->(Group)\n"
            "Use this to:\n"
            "  1. Avoid re-emitting entities already listed (output them only if you have "
            "     NEW properties, a richer description, or a newly discovered parent).\n"
            "  2. Correctly situate new entities in the known hierarchy — if the graph shows "
            "     (Clan:concept) and you find a 'Ventrue' chapter, emit Ventrue with parent=Clan.\n"
            "  3. Avoid emitting relationships already shown in the Structure block."
        )
    )
    source_profile_context: str = dspy.InputField(
        desc="Optional high-confidence profile context summarizing lore domains, taxonomy containers, institution models, relationship patterns, and canon signal terms. Use it as framing only."
    )

    extraction_reasoning: str = dspy.OutputField(
        desc=(
            "Step-by-step analysis of all sections. "
            "Briefly note which sections contain game content and which are metadata/credits. "
            "If known_graph_context is non-empty, note which already-known entities appear and whether "
            "new sections add information."
        )
    )
    axioms: list[ExtractedAxiom] = dspy.OutputField(
        desc="World truths: facts that are always true in this setting. Ensure evidence_refs are included."
    )
    entities: list[ExtractedEntityArchetype] = dspy.OutputField(
        desc="Entity archetypes: races, classes, factions, creature types. Ensure evidence_refs are included."
    )
    lore_facts: list[ExtractedLoreFact] = dspy.OutputField(
        desc="Specific lore facts tied to named entities or places. Include evidence_refs, canon_level, and knowledge_scope."
    )


class SectionCategorizationSignature(dspy.Signature):  # type: ignore[misc]
    """Classify a document section into one universal semantic category for a TTRPG sourcebook."""

    heading_path: str = dspy.InputField(desc="Section heading path, e.g. 'Chapter 3 > Clans > Nosferatu'")
    section_excerpt: str = dspy.InputField(desc="First ~200 characters of section body text")
    category: str = dspy.OutputField(
        desc="One of: power_system, lineage, character_archetype, items_equipment, combat_rules, social_moral, factions, lore_history, creatures_npc, game_mechanics, narrative_style, general"
    )


class SectionCategorizationModule(_AnalyzerModule):
    """Lightweight TTRPG section categorizer — HEAVY for ingestion (was LIGHT)."""

    _signature = SectionCategorizationSignature
    _role = ModelRole.HEAVY  # 2026-07-22: promote to HEAVY for ingestion robustness.
    # See SectionClassifierModule for the reasoning.


class SectionSummarySignature(dspy.Signature):  # type: ignore[misc]
    """Summarize what a single TTRPG document section is about."""

    heading_path: str = dspy.InputField(desc="Section heading path, e.g. 'Chapter 3 > Clans > Nosferatu'")
    section_text: str = dspy.InputField(desc="Full text of the section, up to 2000 characters")
    summary: str = dspy.OutputField(desc="1–3 sentences, factual, no inference or extrapolation")
    themes: list[str] = dspy.OutputField(desc="Up to 5 keywords capturing the section's topics")


class SectionSummaryModule(_AnalyzerModule):
    """Summarize a single TTRPG document section — HEAVY for ingestion (was LIGHT)."""

    _signature = SectionSummarySignature
    _role = ModelRole.HEAVY  # 2026-07-22: promote to HEAVY for ingestion robustness.
    # SectionSummary is called once per section in synthesize_mindscape. On a
    # 295 MB PDF this is hundreds of calls; routing to local qwen made it
    # unrunnable. HEAVY routes to MiniMax-M3 (or gemini-2.5-flash).


class ModuleIntroExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """[G-2] Detect the verbatim read-aloud intro of an authored adventure module.

    Given the first chunk of an adventure module's sections (page-ordered),
    identify the read-aloud prose the GM speaks to open the session. If the
    opening section is genuinely an authored intro (e.g. a Call of Cthulhu
    scenario opener or a 5e module's "Running the Module" preface), quote it
    verbatim. Otherwise return an empty string — we don't want a synthesized
    cold open to replace a missing authored one.
    """

    sections_context: str = dspy.InputField(
        desc=(
            "First ≤6 page-ordered sections from the adventure module, each "
            "labeled with heading path and full text. Trust the actual content "
            "— never invent text. Empty sections are valid (return empty)."
        )
    )
    source_name: str = dspy.InputField(desc="The title of the source document (e.g. 'Dead Gods', 'Curse of Strahd').")
    intro_text: str = dspy.OutputField(
        desc=(
            "Verbatim authored read-aloud intro prose the GM speaks at session "
            "open. Quote exactly as written (preserve paragraph breaks). "
            "Return an empty string if no authored intro is present — do NOT "
            "compose or paraphrase one."
        )
    )


class ModuleIntroExtractionModule(_AnalyzerModule):
    """[G-2] Module-intro extractor — HEAVY.

    Cost: one HEAVY call per adventure-module ingest. Called only when
    ``pack_type == ADVENTURE_MODULE`` (per the plan's gating); the helper
    in ``Analyzer._extract_module_intro`` enforces the gate + the 40-char
    floor so rulebooks/sources short-circuit cheaply.
    """

    _signature = ModuleIntroExtractionSignature
    _role = ModelRole.HEAVY


class SourceMindscapeSynthesisSignature(dspy.Signature):  # type: ignore[misc]
    """
    Synthesize a source-level semantic frame from all section summaries.
    The output will guide all extraction prompts for this source.
    """

    section_summaries: str = dspy.InputField(desc="Formatted list of (heading_path, summary) pairs for all sections")
    source_name: str = dspy.InputField(desc="The title of the source document")
    global_summary: str = dspy.OutputField(
        desc="3–5 sentences describing what this source is about, its genre, and primary focus"
    )
    themes: list[str] = dspy.OutputField(desc="Up to 10 overarching themes for this source")
    taxonomy_hints: list[str] = dspy.OutputField(
        desc="Key domain-specific terms that a reader would use to navigate this source (Clan, Discipline, Hubris, etc.)"
    )
    system_name: str = dspy.OutputField(
        desc="The TTRPG system this source is for, if identifiable; otherwise 'unknown'"
    )


class SourceMindscapeSynthesisModule(_AnalyzerModule):
    """Synthesize a source-level semantic frame from section summaries — needs strong reasoning."""

    _signature = SourceMindscapeSynthesisSignature
    _role = ModelRole.HEAVY


class BatchedExtractionModule(_AnalyzerModule):
    """Extract axioms, entities, and lore from multiple sections in one call."""

    _signature = BatchedExtractionSignature
    # HEAVY = Gemini 2.5 Flash: ~1000 tok/s, 1M context, handles 8-section batches fast.
    # This is the most token-intensive module (8 sections × 1500 words = ~16K tokens in)
    # and benefits the most from a high-throughput provider.
    # Crucially, its output can also be very large, so it must not fall back to
    # the provider default 4096-token cap.
    _role = ModelRole.HEAVY
    _max_tokens = 16384

    def forward(  # type: ignore[override]
        self,
        sections_context: str,
        source_name: str,
        known_graph_context: str = "",
        source_profile_context: str = "",
    ) -> dspy.Prediction:
        with dspy_context_for("analyzer", self._role, max_tokens=self._max_tokens):
            return self._chain(
                sections_context=sections_context,
                source_name=source_name,
                known_graph_context=known_graph_context,
                source_profile_context=source_profile_context,
            )


class ToneExtractionModule(_AnalyzerModule):
    """Extract narrative tone profiles from mood/style sections."""

    _signature = ToneExtractionSignature
    _role = ModelRole.HEAVY
    _max_tokens = 8192


class PlotThreadExtractionModule(_AnalyzerModule):
    """Extract dangling plot threads — unresolved promises, threats, mysteries."""

    _signature = PlotThreadExtractionSignature
    _role = ModelRole.HEAVY
    _max_tokens = 8192


class CharacterProfileExtractionModule(_AnalyzerModule):
    """Extract character/archetype narrative profiles."""

    _signature = CharacterProfileExtractionSignature
    _role = ModelRole.HEAVY
    _max_tokens = 16384


class GenerationTemplateExtractionModule(_AnalyzerModule):
    """Extract NPC generation recipes."""

    _signature = GenerationTemplateExtractionSignature
    _role = ModelRole.HEAVY
    _max_tokens = 8192


class CreationLogicSynthesizerModule(_AnalyzerModule):
    """Synthesize actionable logic from text creation steps."""

    _signature = CreationLogicSynthesizerSignature
    _role = ModelRole.HEAVY
    _max_tokens = 8192
