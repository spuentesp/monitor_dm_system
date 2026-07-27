"""
Canonical tag vocabulary for document ingestion.

TagPool is the single source of truth for translating surface vocabulary
(raw heading words, body-text keywords from any game system) into the
controlled set of semantic category tags used throughout the pipeline.

This prevents two failure modes:
  1. Duplicate tags — "equipment" and "gear" and "items" all → "items_equipment"
  2. System-specific leakage — no game-proper-nouns live here; only structural
     RPG vocabulary that appears across genres and systems.

Extending the pool
------------------
Call TagPool.register(surface, canonical) at runtime — e.g., when a
KnowledgePack is loaded and declares its own vocabulary mappings:

    TagPool.register("ki points", "power_system")
    TagPool.register("stress clock", "social_moral")

New canonical tags are accepted automatically (the canonical set grows).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical tag names
# ---------------------------------------------------------------------------
# These are the only values that should appear in chunk.metadata["semantic_category"].
# They are intentionally abstract — they describe ontological role, not game vocabulary.

SEMANTIC_CATEGORIES: frozenset[str] = frozenset(
    {
        "power_system",  # abilities, spells, mutations, gifts, techniques …
        "lineage",  # clans, tribes, species, bloodlines, races, ancestries …
        "character_archetype",  # classes, origins, backgrounds, callings, careers …
        "items_equipment",  # weapons, armor, gear, modules, price tables …
        "combat_rules",  # combat, attacks, damage, wounds, initiative …
        "social_moral",  # morality, virtue, stress, sanity, corruption tracks …
        "factions",  # guilds, orders, sects, corporations, alliances …
        "lore_history",  # history, legend, myth, timeline, cosmology …
        "creatures_npc",  # monsters, bestiary, antagonists, spirits, alien life …
        "game_mechanics",  # dice, rolls, difficulty, resolution, character sheet …
        "narrative_style",  # mood, theme, tone, atmosphere, narrative focus …
        "general",  # fallback
    }
)

# ---------------------------------------------------------------------------
# Synonym map  (surface term → canonical category)
# ---------------------------------------------------------------------------
# Rules:
#   - Lowercase only
#   - No proper nouns, no game-specific named entities
#   - Multi-word phrases go longest-first so they match before their sub-phrases
#   - When a word is genuinely ambiguous (e.g. "road") prefer the most common
#     RPG interpretation ("social_moral" for road/path moral systems)

_BASE_SYNONYMS: dict[str, str] = {
    # ── power_system ────────────────────────────────────────────────────────
    "special abilities": "power_system",
    "special ability": "power_system",
    "ability list": "power_system",
    "ability tree": "power_system",
    "spell list": "power_system",
    "spell lists": "power_system",
    "power list": "power_system",
    "power tree": "power_system",
    "gift and flaw": "power_system",
    "gifts and flaws": "power_system",
    "discipline": "power_system",
    "disciplines": "power_system",
    "mutation": "power_system",
    "mutations": "power_system",
    "ability": "power_system",
    "abilities": "power_system",
    "spell": "power_system",
    "spells": "power_system",
    "cantrip": "power_system",
    "cantrips": "power_system",
    "power": "power_system",
    "powers": "power_system",
    "feat": "power_system",
    "feats": "power_system",
    "gift": "power_system",
    "gifts": "power_system",
    "technique": "power_system",
    "techniques": "power_system",
    "art": "power_system",
    "arts": "power_system",
    "ritual": "power_system",
    "rituals": "power_system",
    "sorcery": "power_system",
    "witchcraft": "power_system",
    "thaumaturgy": "power_system",
    "necromancy": "power_system",
    "psychic": "power_system",
    "psionic": "power_system",
    "psionics": "power_system",
    "psi": "power_system",
    "talent": "power_system",
    "talents": "power_system",
    "invocation": "power_system",
    "invocations": "power_system",
    "charm": "power_system",
    "charms": "power_system",
    "knack": "power_system",
    "knacks": "power_system",
    # ── lineage ─────────────────────────────────────────────────────────────
    "sect and clan": "lineage",  # structural phrase
    "clan": "lineage",
    "clans": "lineage",
    "bloodline": "lineage",
    "bloodlines": "lineage",
    "tribe": "lineage",
    "tribes": "lineage",
    "species": "lineage",
    "race": "lineage",
    "races": "lineage",
    "breed": "lineage",
    "breeds": "lineage",
    "ancestry": "lineage",
    "ancestries": "lineage",
    "heritage": "lineage",
    "heritages": "lineage",
    "dynasty": "lineage",
    "dynasties": "lineage",
    "lineage": "lineage",
    "lineages": "lineage",
    "strain": "lineage",
    "strains": "lineage",
    # ── character_archetype ─────────────────────────────────────────────────
    "character creation": "character_archetype",
    "character type": "character_archetype",
    "character class": "character_archetype",
    "character classes": "character_archetype",
    "class": "character_archetype",
    "classes": "character_archetype",
    "archetype": "character_archetype",
    "archetypes": "character_archetype",
    "origin": "character_archetype",
    "origins": "character_archetype",
    "background": "character_archetype",
    "backgrounds": "character_archetype",
    "calling": "character_archetype",
    "callings": "character_archetype",
    "career": "character_archetype",
    "careers": "character_archetype",
    "template": "character_archetype",
    "templates": "character_archetype",
    "playbook": "character_archetype",
    "playbooks": "character_archetype",
    "vocation": "character_archetype",
    "vocations": "character_archetype",
    "role": "character_archetype",
    "roles": "character_archetype",
    # ── items_equipment ─────────────────────────────────────────────────────
    "buying and selling": "items_equipment",
    "price table": "items_equipment",
    "price list": "items_equipment",
    "ship module": "items_equipment",
    "ship modules": "items_equipment",
    "module list": "items_equipment",
    "equipment": "items_equipment",
    "gear": "items_equipment",
    "weapon": "items_equipment",
    "weapons": "items_equipment",
    "armor": "items_equipment",
    "armour": "items_equipment",
    "item": "items_equipment",
    "items": "items_equipment",
    "inventory": "items_equipment",
    "tools": "items_equipment",
    "vehicle": "items_equipment",
    "vehicles": "items_equipment",
    "drug": "items_equipment",
    "drugs": "items_equipment",
    "implant": "items_equipment",
    "implants": "items_equipment",
    "cybernetic": "items_equipment",
    "cybernetics": "items_equipment",
    "shop": "items_equipment",
    "market": "items_equipment",
    "crafting": "items_equipment",
    "ammunition": "items_equipment",
    "ammo": "items_equipment",
    # ── combat_rules ────────────────────────────────────────────────────────
    "ranged combat": "combat_rules",
    "close combat": "combat_rules",
    "health level": "combat_rules",
    "health levels": "combat_rules",
    "combat": "combat_rules",
    "attack": "combat_rules",
    "attacking": "combat_rules",
    "damage": "combat_rules",
    "initiative": "combat_rules",
    "defense": "combat_rules",
    "defence": "combat_rules",
    "wound": "combat_rules",
    "wounds": "combat_rules",
    "brawl": "combat_rules",
    "melee": "combat_rules",
    "firearms": "combat_rules",
    "ranged": "combat_rules",
    "chase": "combat_rules",
    "pursuit": "combat_rules",
    "ambush": "combat_rules",
    "maneuver": "combat_rules",
    "manoeuvre": "combat_rules",
    # ── social_moral ────────────────────────────────────────────────────────
    "path of enlightenment": "social_moral",
    "code of honor": "social_moral",
    "code of honour": "social_moral",
    "morality": "social_moral",
    "virtue": "social_moral",
    "virtues": "social_moral",
    "vice": "social_moral",
    "vices": "social_moral",
    "corruption": "social_moral",
    "sanity": "social_moral",
    "stress": "social_moral",
    "alignment": "social_moral",
    "derangement": "social_moral",
    "derangements": "social_moral",
    "willpower": "social_moral",
    "instinct": "social_moral",
    "road": "social_moral",
    "roads": "social_moral",
    "frenzy": "social_moral",
    "humanity": "social_moral",
    # ── factions ────────────────────────────────────────────────────────────
    "faction": "factions",
    "factions": "factions",
    "guild": "factions",
    "guilds": "factions",
    "order": "factions",
    "orders": "factions",
    "cult": "factions",
    "cults": "factions",
    "corporation": "factions",
    "corporations": "factions",
    "organization": "factions",
    "organizations": "factions",
    "sect": "factions",
    "sects": "factions",
    "covenant": "factions",
    "covenants": "factions",
    "council": "factions",
    "alliance": "factions",
    "alliances": "factions",
    "crew": "factions",
    "allegiance": "factions",
    "allegiances": "factions",
    "political": "factions",
    "government": "factions",
    # ── lore_history ────────────────────────────────────────────────────────
    "creation myth": "lore_history",
    "history": "lore_history",
    "historical": "lore_history",
    "legend": "lore_history",
    "legends": "lore_history",
    "myth": "lore_history",
    "myths": "lore_history",
    "chronicle": "lore_history",
    "chronicles": "lore_history",
    "lore": "lore_history",
    "setting": "lore_history",
    "cosmology": "lore_history",
    "timeline": "lore_history",
    # ── creatures_npc ───────────────────────────────────────────────────────
    "creature": "creatures_npc",
    "creatures": "creatures_npc",
    "monster": "creatures_npc",
    "monsters": "creatures_npc",
    "beast": "creatures_npc",
    "beasts": "creatures_npc",
    "bestiary": "creatures_npc",
    "npc": "creatures_npc",
    "npcs": "creatures_npc",
    "antagonist": "creatures_npc",
    "antagonists": "creatures_npc",
    "enemy": "creatures_npc",
    "enemies": "creatures_npc",
    "spirit": "creatures_npc",
    "spirits": "creatures_npc",
    "alien": "creatures_npc",
    "aliens": "creatures_npc",
    "undead": "creatures_npc",
    "animal": "creatures_npc",
    "animals": "creatures_npc",
    "demon": "creatures_npc",
    "demons": "creatures_npc",
    # ── game_mechanics ──────────────────────────────────────────────────────
    "character sheet": "game_mechanics",
    "action economy": "game_mechanics",
    "attribute check": "game_mechanics",
    "skill check": "game_mechanics",
    "saving throw": "game_mechanics",
    "ability score": "game_mechanics",
    "ability scores": "game_mechanics",
    "dice pool": "game_mechanics",
    "core mechanic": "game_mechanics",
    "extended action": "game_mechanics",
    "reflexive action": "game_mechanics",
    "turn structure": "game_mechanics",
    "dice": "game_mechanics",
    "roll": "game_mechanics",
    "rolls": "game_mechanics",
    "difficulty": "game_mechanics",
    "experience": "game_mechanics",
    "advancement": "game_mechanics",
    "resolution": "game_mechanics",
    "contest": "game_mechanics",
    "round": "game_mechanics",
    # ── narrative_style ─────────────────────────────────────────────────────
    "narrative style": "narrative_style",
    "narrative focus": "narrative_style",
    "how to narrate": "narrative_style",
    "atmosphere": "narrative_style",
    "mood": "narrative_style",
    "theme": "narrative_style",
    "themes": "narrative_style",
    "tone": "narrative_style",
    "voice": "narrative_style",
}

# Pre-sorted by phrase length (longest first) for greedy matching in classify
_SYNONYMS_BY_LENGTH: list[tuple[str, str]] = sorted(_BASE_SYNONYMS.items(), key=lambda kv: len(kv[0]), reverse=True)


class TagPool:
    """
    Canonical vocabulary for semantic category tagging.

    Translates any surface term to a canonical semantic category.  The pool is
    the single authoritative place for this mapping — no other file should
    hardcode game-specific vocabulary into classifier logic.

    Usage
    -----
    TagPool.normalize("spell list")   → "power_system"
    TagPool.normalize("discipline")   → "power_system"
    TagPool.normalize("unknown term") → None

    TagPool.register("ki point", "power_system")   # extend at runtime
    """

    _synonyms: dict[str, str] = dict(_BASE_SYNONYMS)
    _by_length: list[tuple[str, str]] = list(_SYNONYMS_BY_LENGTH)
    _canonical: frozenset[str] = SEMANTIC_CATEGORIES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def normalize(cls, term: str) -> str | None:
        """Exact-match lookup (case-insensitive).  Returns None if unknown."""
        return cls._synonyms.get(term.strip().lower())

    @classmethod
    def classify_text(cls, text: str) -> str | None:
        """
        Greedy longest-match scan of arbitrary text.

        Iterates synonym keys from longest to shortest so multi-word phrases
        ("spell list") win over single words ("spell").
        Returns the first matching canonical category, or None.
        """
        haystack = text.strip().lower()
        for surface, category in cls._by_length:
            if surface in haystack:
                return category
        return None

    @classmethod
    def register(cls, surface: str, canonical: str) -> None:
        """
        Add a synonym mapping at runtime.

        'canonical' need not be an existing category — the pool grows to
        accommodate new tags introduced by game packs.
        """
        key = surface.strip().lower()
        cls._synonyms[key] = canonical
        # Keep sorted list in sync
        cls._by_length = sorted(cls._synonyms.items(), key=lambda kv: len(kv[0]), reverse=True)
        if canonical not in cls._canonical:
            cls._canonical = cls._canonical | {canonical}

    @classmethod
    def canonical_tags(cls) -> frozenset[str]:
        """All currently known canonical category names."""
        return cls._canonical

    @classmethod
    def is_canonical(cls, tag: str) -> bool:
        return tag in cls._canonical

    @classmethod
    def synonyms_for(cls, canonical: str) -> list[str]:
        """All surface terms that map to a given canonical category."""
        return [s for s, c in cls._synonyms.items() if c == canonical]
