"""
Semantic category → extraction layer mapping and configuration constants.

At ingest time each chunk is tagged with a ``semantic_category`` field by
``_classify_semantic_category()`` in ingest_tools.  The Analyzer reads
chunks directly by category filter instead of running broad semantic
vector searches.  This gives precise, zero-noise retrieval and works for
any game system because the category names are universal (ontological),
not game-system-specific vocabulary.

VtM "Disciplines"  → semantic_category = "power_system"
DiS "Mutations"    → semantic_category = "power_system"
VtM "Clans"        → semantic_category = "lineage"
DiS "Origins"      → semantic_category = "character_archetype"
etc.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Semantic category lists
# ---------------------------------------------------------------------------

# Which semantic_category values feed each extraction layer
CATEGORIES_AXIOMS = ["lore_history", "general"]
CATEGORIES_ENTITIES = [
    "power_system",  # disciplines / spells / mutations / feats
    "lineage",  # clans / bloodlines / races / species
    "character_archetype",  # classes / origins / backgrounds
    "factions",  # guilds / covenants / organizations
    "creatures_npc",  # bestiary / enemy types
    "items_equipment",  # weapon / gear types as entity archetypes
    "social_moral",  # paths / humanity / morality systems
]
CATEGORIES_LORE = ["lore_history", "factions", "general"]
CATEGORIES_GAME_DETECTION = [
    "game_mechanics",
    "character_archetype",
    "combat_rules",
    "power_system",
    "social_moral",
    "general",
]
CATEGORIES_RULES = [
    "game_mechanics",
    "combat_rules",
    "social_moral",
    "items_equipment",
    "power_system",
    "character_archetype",
]
CATEGORIES_CHARACTER_SHEET = [
    "game_mechanics",
    "character_archetype",
    "power_system",
    "social_moral",
    "combat_rules",
]
CATEGORIES_NPC = [
    "creatures_npc",
    "combat_rules",
    "character_archetype",
]
CATEGORIES_TABLES = [
    "items_equipment",
    "game_mechanics",
    "creatures_npc",
    "general",
]
CATEGORIES_TONE = [
    "narrative_style",
    "social_moral",
    "lore_history",
    "general",
]
CATEGORIES_CHARACTER_PROFILES = [
    "narrative_style",
    "character_archetype",
    "creatures_npc",
    "lineage",
    "social_moral",
]
CATEGORIES_GENERATION_TEMPLATES = [
    "character_archetype",
    "creatures_npc",
    "game_mechanics",
    "factions",
]

# ---------------------------------------------------------------------------
# Fallback semantic queries
# Used only when a chunk has no semantic_category
# (i.e. documents ingested before this feature was added).
# ---------------------------------------------------------------------------

FALLBACK_QUERIES_TABLES = [
    "random tables encounter tables loot tables treasure",
    "random outcomes dice results chart",
]
FALLBACK_QUERIES_NPC = [
    "bestiary monsters enemies antagonists NPC stat blocks",
    "villain brute minion creature opponent",
]
FALLBACK_QUERIES_AXIOMS = [
    "fundamental laws and truths of reality",
    "what is universally true in this setting",
]
FALLBACK_QUERIES_ENTITIES = [
    "character classes races species disciplines clans",
    "factions guilds organizations bloodlines",
    "creatures monsters bestiary enemy types",
]
FALLBACK_QUERIES_LORE = [
    "history timeline key historical events",
    "named characters rulers leaders heroes villains",
]
FALLBACK_QUERIES_GAME = [
    "ability scores attributes traits skills powers disciplines edges feats dice rolling",
    "hit points wounds stress hero points saving throws action economy ship combat",
]
FALLBACK_QUERIES_TONE = [
    "narrative style mood atmosphere voice tone theme",
    "how to narrate the game descriptive style narrative focus",
]
FALLBACK_QUERIES_CHARACTER_PROFILES = [
    "character psychology personality traits fears desires",
    "mannerisms speech styles values how to play this character",
]
FALLBACK_QUERIES_GENERATION_TEMPLATES = [
    "how to create NPCs antagonist generation villain archetypes",
    "typical member gear and personality recipe for NPCs",
]

# ---------------------------------------------------------------------------
# Configuration limits
# ---------------------------------------------------------------------------

MAX_REFERENCE_SECTIONS = 96

# Max chunks to sample in a single game system detection call
DETECTION_SAMPLE_SIZE = 48

# How many chunks to retrieve per category for extraction.
# Raised from 96 → 512 so large TTRPG rulebooks (VtM, D&D PHB, Pathfinder CRB)
# are not silently truncated at the chunk-retrieval stage (GAP-8 fix).
MAX_CATEGORY_CHUNKS = 512

# Max words per section body before trimming (≈ 2000 tokens per section).
MAX_SECTION_WORDS = 1500

# Max sections to pass into each extraction layer.
# Raised from 50 → 200 so books with many sub-sections are not silently capped
# before the LLM extraction batches see them (GAP-9 fix).
MAX_SECTIONS_PER_LAYER = 200

# Max sections per batched extraction LLM call.
# 8 sections × 1500 words ≈ 16K tokens — fine for Gemini Flash (HEAVY role)
BATCH_SIZE = 2

# Number of sections to process in one LLM call during the initial classification pass.
CLASSIFIER_BATCH_SIZE = 15

# Max concurrent batched-extraction LLM calls.
# Bumped from 5 → 8 after a 107 MB VtM 20th run showed ~8% of batches
# retrying on timeout: each retry held the section's slot for ~120s and
# starved 4 sibling slots. With 8 slots + tightened backoff, the worst-case
# retry still completes in ~125s without blocking the whole batch.
EXTRACTION_CONCURRENCY = 8

# Minimum confidence threshold — items below this are discarded
MIN_CONFIDENCE = 0.6

# Max sections to pass into a game-system schema extraction call.
SYSTEM_SCHEMA_SECTION_LIMIT = 30
