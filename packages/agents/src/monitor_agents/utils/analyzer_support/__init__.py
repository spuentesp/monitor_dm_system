"""analyzer_support — utility functions for the Analyzer agent.

This package was extracted from a single 1893-line module into focused
sub-modules for DRY/SOLID compliance.  Every public name is re-exported
here so that existing ``from monitor_agents.utils.analyzer_support import X``
statements continue to work without changes.

Sub-module layout
-----------------
_constants   – regex patterns, keyword sets, config values
_sections    – SectionDigest dataclass + builder functions
_profiles    – source profile building & formatting
_entities    – entity merging & alias mapping
_social      – social entity inference & materialization
_relationships – relationship dedup & graph snapshots
_game_filters  – NPC/stat/prompt filtering, section scoring
_summaries   – schema extraction, mindscape context, summary builders
_parsing     – source-profile & section-classification JSON parsing
"""

from __future__ import annotations

# ── Constants (re-exported for direct access) ──────────────────────────────
from monitor_agents.utils.analyzer_support._constants import (
    CONTAINER_TYPE_HINTS,
    GENERIC_CATEGORY_NAMES,
    INSTITUTION_ROLE_HINTS,
    PROFILE_DOMAIN_HINTS,
    REFERENCE_SECTION_KEYWORDS,
    REFERENCE_SECTION_RE,
    SOCIAL_RELATION_PROPERTY_KEYS,
    SYSTEM_SCHEMA_SECTION_LIMIT,
)

# ── Entities ───────────────────────────────────────────────────────────────
from monitor_agents.utils.analyzer_support._entities import (
    build_alias_map,
    infer_container_entity_type,
    merge_entity_archetypes,
    normalize_relationship_refs,
    split_semantic_values,
)

# ── Game filters ───────────────────────────────────────────────────────────
from monitor_agents.utils.analyzer_support._game_filters import (
    filter_player_attributes,
    filter_player_resources,
    filter_player_skills,
    is_category_header,
    is_npc_stat_name,
    is_prompt_echo,
)

# ── Parsing ────────────────────────────────────────────────────────────────
from monitor_agents.utils.analyzer_support._parsing import (
    parse_section_classifications,
    parse_source_profile,
)

# ── Profiles ───────────────────────────────────────────────────────────────
from monitor_agents.utils.analyzer_support._profiles import (
    build_source_profile_seed,
    extract_candidate_taxonomy_containers,
    extract_canon_signal_terms,
    extract_glossary_aliases,
    format_source_profile_context,
    infer_lore_domains,
    merge_source_profiles,
    rank_sections_with_profile,
    summarize_source_profile,
)

# ── Relationships ──────────────────────────────────────────────────────────
from monitor_agents.utils.analyzer_support._relationships import (
    build_graph_snapshot,
    dedupe_relationships,
)

# ── Sections ───────────────────────────────────────────────────────────────
from monitor_agents.utils.analyzer_support._sections import (
    SectionDigest,
    append_section_chunk,
    build_section_digests,
    format_section_context,
)

# ── Social ─────────────────────────────────────────────────────────────────
from monitor_agents.utils.analyzer_support._social import (
    annotate_entity_roles,
    derive_hierarchy_relationships,
    infer_social_entity_identity,
    materialize_container_entities,
    materialize_social_entities_and_relationships,
)

# ── Summaries / schema extraction ──────────────────────────────────────────
from monitor_agents.utils.analyzer_support._summaries import (
    build_chunk_summary_artifacts,
    build_section_summary_inputs,
    dedupe_named_items,
    format_mindscape_context,
    heuristic_extract_character_sheet_sections,
    persist_mindscape_artifacts,
    prioritize_schema_sections,
    system_section_score,
)

__all__ = [
    # Constants
    "CONTAINER_TYPE_HINTS",
    "GENERIC_CATEGORY_NAMES",
    "INSTITUTION_ROLE_HINTS",
    "PROFILE_DOMAIN_HINTS",
    "REFERENCE_SECTION_KEYWORDS",
    "REFERENCE_SECTION_RE",
    "SOCIAL_RELATION_PROPERTY_KEYS",
    "SYSTEM_SCHEMA_SECTION_LIMIT",
    # Sections
    "SectionDigest",
    "append_section_chunk",
    "build_section_digests",
    "format_section_context",
    # Profiles
    "build_source_profile_seed",
    "extract_canon_signal_terms",
    "extract_candidate_taxonomy_containers",
    "extract_glossary_aliases",
    "format_source_profile_context",
    "infer_lore_domains",
    "merge_source_profiles",
    "rank_sections_with_profile",
    "summarize_source_profile",
    # Entities
    "build_alias_map",
    "infer_container_entity_type",
    "merge_entity_archetypes",
    "normalize_relationship_refs",
    "split_semantic_values",
    # Social
    "annotate_entity_roles",
    "derive_hierarchy_relationships",
    "infer_social_entity_identity",
    "materialize_container_entities",
    "materialize_social_entities_and_relationships",
    # Relationships
    "build_graph_snapshot",
    "dedupe_relationships",
    # Game filters
    "filter_player_attributes",
    "filter_player_resources",
    "filter_player_skills",
    "is_category_header",
    "is_npc_stat_name",
    "is_prompt_echo",
    # Summaries / schema extraction
    "build_chunk_summary_artifacts",
    "build_section_summary_inputs",
    "dedupe_named_items",
    "format_mindscape_context",
    "heuristic_extract_character_sheet_sections",
    "persist_mindscape_artifacts",
    "prioritize_schema_sections",
    "system_section_score",
    # Parsing
    "parse_section_classifications",
    "parse_source_profile",
]
