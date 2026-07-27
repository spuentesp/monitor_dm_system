"""Constants, regex patterns, and config dicts for analyzer support utilities.

These are PRE-FILTERS, not gameplay decisions. They run during offline
document ingestion *before* an LLM extractor decides what's actually in the
text — they exist to skip chunks the LLM shouldn't even see.

The de-heuristic principle (see ``docs/architecture/DE_HEURISTIC_PRINCIPLE.md``)
bans keyword/regex tables from the *gameplay path*. Pre-filters and stop-lists
are a different tool: keyword matching at 1ms/chunk beats an embedding call
at 50ms/chunk by 50× for the same chunk-level recall. Replacing these with
semantics would be more expensive AND less accurate. We keep them and tag
them at the call site (``is_npc_stat_name``, ``system_section_score``,
``split_semantic_values``) so the intent is unambiguous.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Section / reference constants
# ---------------------------------------------------------------------------

REFERENCE_SECTION_KEYWORDS = (
    "table of contents",
    "contents",
    "index",
    "glossary",
    "appendix",
    "character creation",
    "traits",
    "attributes",
    "abilities",
    "skills",
    "knacks",
    "advantages",
    "virtues",
    "disciplines",
    "powers",
    "schools",
    "sorcery",
    "arcana",
    "maneuvers",
    "edges",
    "feats",
    "combat",
    "duel",
    "ship combat",
    "ship roles",
    "resources",
    "wounds",
    "stress",
    "hero points",
)

REFERENCE_SECTION_RE = re.compile(
    r"table of contents|\bcontents\b|\bindex\b|\bglossary\b|\bappendix\b|"
    r"\bchapter\s+\d+\b|\bbook\s+[ivx]+\b|\.{2,}\s*\d+",
    re.IGNORECASE,
)

SYSTEM_SCHEMA_SECTION_LIMIT = 12

# ---------------------------------------------------------------------------
# Container / entity type hints
# ---------------------------------------------------------------------------

CONTAINER_TYPE_HINTS: tuple[tuple[str, str], ...] = (
    # Character/creature categories (all systems)
    ("clan", "concept"),  # VtM bloodlines
    ("class", "concept"),  # D&D, Pathfinder
    ("species", "concept"),  # D&D races, sci-fi aliens
    ("ancestry", "concept"),  # PF2e, some PbtA
    ("archetype", "concept"),  # Generic
    ("background", "concept"),  # D&D, VtM
    ("playbook", "concept"),  # PbtA, Monster of the Week
    # Power/ability systems
    ("discipline", "concept"),  # VtM
    ("school", "concept"),  # D&D spell schools
    ("style", "concept"),  # 7th Sea dueling
    ("power", "concept"),  # Generic
    ("feat", "concept"),  # D&D, PF2e
    ("edge", "concept"),  # Savage Worlds
    ("merit", "concept"),  # VtM, nWoD
    ("advantage", "concept"),  # 7th Sea
    ("move", "concept"),  # PbtA, Monster of the Week, Dungeon World
    ("knack", "concept"),  # 7th Sea
    ("talent", "concept"),  # Various
    ("trait", "concept"),  # Death in Space, generic
    ("module", "concept"),  # Lancer mech modules
    ("system", "concept"),  # Lancer mech systems
    ("license", "concept"),  # Lancer licenses
    # Objects / equipment
    ("weapon", "object"),
    ("armor", "object"),
    ("item", "object"),
    ("ship", "object"),  # Death in Space, 7th Sea
    ("vehicle", "object"),
    ("mech", "object"),  # Lancer frames
    ("frame", "object"),  # Lancer frames
    # Social / political
    ("sect", "faction"),  # VtM
    ("faction", "faction"),
    ("guild", "organization"),
    ("order", "organization"),
    ("corp", "organization"),  # Lancer, cyberpunk
    ("corporation", "organization"),
    ("crew", "organization"),  # Death in Space
    # Locations
    ("city", "location"),
    ("region", "location"),
    ("plane", "location"),
    ("sector", "location"),  # Sci-fi
    ("station", "location"),  # Death in Space
)

SOCIAL_RELATION_PROPERTY_KEYS: dict[str, str] = {
    "sect": "member_of",
    "faction": "member_of",
    "organization": "member_of",
    "order": "member_of",
    "guild": "member_of",
    "union": "member_of",
    "church": "member_of",
    "house": "member_of",
    "crew": "member_of",
    "allegiance": "member_of",
    "member_of": "member_of",
    "belongs_to": "member_of",
    "part_of": "part_of",
    "subgroup_of": "subgroup_of",
    "affiliation": "affiliated_with",
    "affiliated_with": "affiliated_with",
}

GENERIC_CATEGORY_NAMES = {
    # VtM / WoD
    "clan",
    "discipline",
    "sect",
    # D&D / Pathfinder
    "class",
    "school",
    "schools",
    "feat",
    "feats",
    # 7th Sea
    "style",
    "styles",
    "knack",
    "knacks",
    "advantage",
    "advantages",
    # PbtA / Monster of the Week
    "move",
    "moves",
    "playbook",
    "playbooks",
    # Lancer
    "frame",
    "frames",
    "module",
    "modules",
    "license",
    "licenses",
    "system",
    "systems",
    # Savage Worlds / generic
    "edge",
    "edges",
    "merit",
    "merits",
    # Equipment categories
    "weapon",
    "armor",
    "item",
    "items",
    # Social categories
    "power",
    "powers",
    "faction",
    "organization",
    "guild",
    "order",
    "church",
    "house",
    "union",
    "crew",
    "corp",
    "corporation",
}

INSTITUTION_ROLE_HINTS = (
    "church",
    "house",
    "order",
    "guild",
    "union",
    "cult",
    "syndicate",
    "authority",
    "company",
    "corporation",
    "crew",
    "sect",
    "faction",
)

# ---------------------------------------------------------------------------
# Profile domain hints
# ---------------------------------------------------------------------------

PROFILE_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "cosmology": ("cosmology", "cosmos", "plane", "planes", "astral", "divine"),
    "history": ("history", "era", "age", "timeline", "war", "chronicle"),
    "religion": ("religion", "faith", "church", "god", "gods", "rite"),
    "geography": ("geography", "region", "city", "realm", "wilderness", "map"),
    "factions": ("faction", "sect", "clan", "guild", "house", "alliance"),
    "morality": ("morality", "humanity", "virtue", "vice", "ethic"),
    "metaphysics": ("metaphysics", "spirit", "soul", "curse", "reality", "magic"),
    "technology": ("technology", "ship", "mech", "cyber", "reactor", "engine"),
}

_ALIAS_SIGNAL_RE = re.compile(
    r"\b(?:also called|also known as|known as|aka|called)\b\s+([^.;]+)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Social entity inference constants
# ---------------------------------------------------------------------------

_FACTION_RELATION_KEYS = {"sect", "faction"}
_FACTION_TOKENS = {"sect", "faction", "coalition", "alliance", "rebellion"}
_ORG_RELATION_KEYS = {
    "guild",
    "order",
    "church",
    "house",
    "organization",
    "union",
    "crew",
    "corp",
    "corporation",
    "company",
}
_ORG_TOKENS = {
    "church",
    "house",
    "order",
    "guild",
    "union",
    "authority",
    "syndicate",
    "company",
    "crew",
    "corp",
    "corporation",
    "agency",
    "bureau",
    "collective",
    "legion",
}
_GENERIC_MEMBER_KEYS = {"member_of", "belongs_to", "affiliation", "affiliated_with", "allegiance"}

# ---------------------------------------------------------------------------
# Hierarchy subtype sets
# ---------------------------------------------------------------------------

_PART_OF_SUB_TYPES = frozenset(
    [
        # VtM / World of Darkness
        "discipline_power",
        "discipline_path",
        "gift",
        "rite",
        # D&D / Pathfinder
        "spell",
        "cantrip",
        "invocation",
        "feat_variant",
        # 7th Sea
        "maneuver",
        "knack",
        "dueling_maneuver",
        "sorcery_effect",
        # PbtA / Monster of the Week
        "move",
        "basic_move",
        "playbook_move",
        "hunter_move",
        # Lancer
        "mech_system",
        "mech_weapon",
        "mech_mod",
        "core_bonus",
        "talent_rank",
        # Death in Space
        "crew_ability",
        "ship_module",
        "void_ability",
        # Generic / cross-system
        "power_variant",
        "technique",
        "ritual",
        "ability",
        "sub_power",
        "feature",
        "class_feature",
        "subclass_feature",
    ]
)

# ---------------------------------------------------------------------------
# Game system schema filtering
# ---------------------------------------------------------------------------

_PLACEHOLDER_SCHEMA_NAMES = {
    "attribute",
    "attributes",
    "ability",
    "abilities",
    "skill",
    "skills",
    "resource",
    "resources",
    "power",
    "powers",
    "subsystem",
    "subsystems",
    "mechanic",
    "core mechanic",
    "stat",
    "stats",
}

_CATEGORY_HEADER_NAMES = {
    "physical attributes",
    "social attributes",
    "mental attributes",
    "physical",
    "social",
    "mental",
    "talents",
    "skills",
    "knowledges",
    "traits",
    "trait",
    "attributes",
    "generation",
}

_NPC_STAT_PATTERNS = re.compile(
    r"(?i)\b("
    r"biodrone|automaton|horror|creature|monster|enemy|minion|villain|brute|boss|"
    r"swarm|drone|sentinel|guardian|revenant|ghoul stat|plague|"
    r"morale|attack bonus|damage bonus|number appearing|hit dice|"
    r"threat level|threat rating|challenge rating|cr \d|xp value|"
    r"npc |npc$"
    r")\b"
)

_PROMPT_ECHO_PATTERN = re.compile(
    r"(?i)"
    r"^what\s|^how\s|^which\s|^does\s|^list\s|^are\s|^is\s"
    r"|\?$"
    r"|tracked on|character sheet|character have|ability scores"
    r"|competencies|in this system"
    r"|attributes used for"
)

# ---------------------------------------------------------------------------
# Heuristic extraction patterns
# ---------------------------------------------------------------------------

_EXPLICIT_ATTRIBUTE_RE = re.compile(
    r"(?P<name>[A-Z][A-Z ]{2,24})\s*\((?P<abbr>[A-Z]{2,5})\)\s*"
    r"(?P<desc>[^()]{8,180}?)(?=\s+[A-Z][A-Z ]{2,24}\s*\([A-Z]{2,5}\)|\s+GENERATING\b|\s+ABILITY VALUES\b|$)"
)

_RESOURCE_HINTS: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"\bdefense rating\b|\barmor class\b", re.IGNORECASE), "Defense Rating", "DR"),
    (re.compile(r"\bhit points?\b", re.IGNORECASE), "Hit Points", "HP"),
    (re.compile(r"\bmorale\b", re.IGNORECASE), "Morale", "ML"),
    (re.compile(r"\bvoid points?\b", re.IGNORECASE), "Void Points", "VP"),
    (re.compile(r"\bfuel\b", re.IGNORECASE), "Fuel", "FUEL"),
    (re.compile(r"\bstress\b", re.IGNORECASE), "Stress", "STR"),
    (re.compile(r"\bharm\b", re.IGNORECASE), "Harm", "HARM"),
)

# ---------------------------------------------------------------------------
# Mindscape / summary constants
# ---------------------------------------------------------------------------

_SECTION_TEXT_MAX_CHARS = 2000
