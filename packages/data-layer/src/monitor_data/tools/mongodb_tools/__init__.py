"""
MongoDB MCP Tools for MONITOR Data Layer — Facade Package.

This package re-exports all MongoDB tool functions from domain-specific
sub-modules. The original single-file mongodb_tools.py (5910 lines) was
split into 16 modules following SRP.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: Agents (Layer 2) via MCP protocol

Sub-modules:
    scenes            — Scene + Turn CRUD
    proposals         — Proposed Change CRUD
    stories           — Story Outline CRUD + pacing
    combat            — Combat CRUD + participants + log
    resolutions       — Resolution CRUD
    memories          — Character Memory CRUD
    game_systems      — Game System + Rule Override CRUD + builtins
    party             — Party Inventory + Splits CRUD
    working_state     — Character Working State CRUD
    ingestion_jobs    — Ingestion Job CRUD
    knowledge_packs   — Knowledge Pack CRUD + apply
    character_sheets  — Character Sheet CRUD
    documents         — Document CRUD + verdicts
    npc_profiles      — NPC Profile CRUD
    conversations     — Conversation Session CRUD
    profiles          — World + GM Profile CRUD
    random_tables     — Random Table CRUD + rolling
    templates         — Entity Template CRUD
    snapshots         — World Snapshot CRUD
"""

# Backward-compatible re-exports for test mock patches
# Tests do @patch("monitor_data.tools.mongodb_tools.get_mongodb_client")
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.neo4j import get_neo4j_client

# Scene + Turn operations
from monitor_data.tools.mongodb_tools.scenes import (
    _convert_turn_dict_to_response,
    _convert_scene_doc_to_response,
    mongodb_create_scene,
    mongodb_get_scene,
    mongodb_get_recent_turns,
    mongodb_get_scene_summary,
    mongodb_update_scene,
    mongodb_list_scenes,
    mongodb_append_turn,
    mongodb_update_turn_resolution,
)

# Proposed Change operations
from monitor_data.tools.mongodb_tools.proposals import (
    _convert_proposed_change_doc_to_response,
    mongodb_create_proposed_change,
    mongodb_get_proposed_change,
    mongodb_list_proposed_changes,
    mongodb_update_proposed_change,
)
from monitor_data.tools.mongodb_tools.change_log import (
    make_change_log_entry,
    mongodb_append_change_log,
    mongodb_list_change_log,
)

# Story Outline operations
from monitor_data.tools.mongodb_tools.stories import (
    _convert_story_outline_doc_to_response,
    _calculate_pacing_metrics,
    mongodb_create_story_outline,
    mongodb_get_story_outline,
    mongodb_update_story_outline,
)

# Combat operations
from monitor_data.tools.mongodb_tools.combat import (
    _convert_combat_doc_to_response,
    mongodb_create_combat,
    mongodb_get_combat,
    mongodb_list_combats,
    mongodb_update_combat,
    mongodb_delete_combat,
    mongodb_add_combat_participant,
    mongodb_update_combat_participant,
    mongodb_remove_combat_participant,
    mongodb_add_combat_log_entry,
    mongodb_set_combat_outcome,
)

# Resolution operations
from monitor_data.tools.mongodb_tools.resolutions import (
    _convert_resolution_doc_to_response,
    mongodb_create_resolution,
    mongodb_get_resolution,
    mongodb_list_resolutions,
    mongodb_update_resolution,
    mongodb_delete_resolution,
)

# Memory operations
from monitor_data.tools.mongodb_tools.memories import (
    mongodb_create_memory,
    mongodb_get_memory,
    mongodb_list_memories,
    mongodb_update_memory,
    mongodb_delete_memory,
    mongodb_verify_memory,
)

# Game System + Rule Override operations
from monitor_data.tools.mongodb_tools.game_systems import (
    _load_builtin_game_systems,
    _ensure_builtin_systems_seeded,
    mongodb_create_game_system,
    mongodb_get_game_system,
    mongodb_list_game_systems,
    mongodb_update_game_system,
    mongodb_delete_game_system,
    mongodb_create_rule_override,
    mongodb_get_rule_override,
    mongodb_list_rule_overrides,
    mongodb_update_rule_override,
    mongodb_delete_rule_override,
)

# Party Inventory + Splits + Character Inventory operations
from monitor_data.tools.mongodb_tools.party import (
    mongodb_create_party_inventory,
    mongodb_get_party_inventory,
    mongodb_add_inventory_item,
    mongodb_remove_inventory_item,
    mongodb_update_party_gold,
    mongodb_transfer_item,
    mongodb_create_party_split,
    mongodb_get_active_splits,
    mongodb_resolve_party_split,
    mongodb_get_split_history,
    mongodb_create_character_inventory,
    mongodb_get_character_inventory,
    mongodb_add_character_item,
    mongodb_remove_character_item,
    mongodb_update_character_gold,
    mongodb_equip_item,
)

# Working State operations
from monitor_data.tools.mongodb_tools.working_state import (
    _convert_working_state_doc_to_response,
    mongodb_create_working_state,
    mongodb_get_working_state,
    mongodb_update_working_state,
    mongodb_add_modification,
    mongodb_list_working_states,
)

# Ingestion Job operations
from monitor_data.tools.mongodb_tools.ingestion_jobs import (
    _convert_ingestion_job_doc,
    mongodb_create_ingestion_job,
    mongodb_delete_ingestion_job,
    mongodb_get_ingestion_job,
    mongodb_update_ingestion_job,
    mongodb_list_ingestion_jobs,
)

# Knowledge Pack operations
from monitor_data.tools.mongodb_tools.knowledge_packs import (
    _convert_knowledge_pack_doc,
    mongodb_create_knowledge_pack,
    mongodb_get_knowledge_pack,
    mongodb_update_knowledge_pack,
    mongodb_list_knowledge_packs,
    mongodb_delete_knowledge_pack,
    mongodb_count_pack_dependents,
    mongodb_apply_knowledge_pack,
)

# Character Sheet operations
from monitor_data.tools.mongodb_tools.character_sheets import (
    _character_sheet_doc_to_response,
    mongodb_create_character_sheet,
    mongodb_get_character_sheet,
    mongodb_update_character_sheet,
    mongodb_list_character_sheets,
)

# Document + Verdict operations
from monitor_data.tools.mongodb_tools.documents import (
    mongodb_find_document_by_filename,
    mongodb_create_document,
    mongodb_get_document,
    mongodb_list_documents,
    mongodb_update_document,
    mongodb_record_verdict,
)

# NPC Profile operations
from monitor_data.tools.mongodb_tools.npc_profiles import (
    _npc_profile_doc_to_response,
    mongodb_create_npc_profile,
    mongodb_get_npc_profile,
    mongodb_update_npc_profile,
)

# Conversation operations
from monitor_data.tools.mongodb_tools.conversations import (
    _conversation_doc_to_response,
    mongodb_create_conversation,
    mongodb_get_conversation,
    mongodb_get_recent_conversation_turns,
    mongodb_append_conversation_turn,
    mongodb_update_conversation,
    mongodb_list_conversations,
)

# Character operations
from monitor_data.tools.mongodb_tools.characters import (
    mongodb_get_character,
    mongodb_resolve_character as mongodb_resolve_character,
)

# World + GM Profile operations
from monitor_data.tools.mongodb_tools.profiles import (
    _convert_gm_profile_doc,
    mongodb_upsert_world_profile,
    mongodb_get_world_profile,
    mongodb_create_gm_profile,
    mongodb_get_gm_profile,
    mongodb_update_gm_profile,
    mongodb_list_gm_profiles,
    mongodb_delete_gm_profile,
)

# Random Table operations
from monitor_data.tools.mongodb_tools.random_tables import (
    mongodb_create_random_table,
    mongodb_get_random_table,
    mongodb_list_random_tables,
    mongodb_update_random_table,
    mongodb_delete_random_table,
    mongodb_roll_on_table,
)

# Entity Template operations
from monitor_data.tools.mongodb_tools.templates import (
    mongodb_create_entity_template,
    mongodb_get_entity_template,
    mongodb_list_entity_templates,
    mongodb_update_entity_template,
    mongodb_delete_entity_template,
    mongodb_increment_template_usage,
)

# Lorebook operations
from monitor_data.tools.mongodb_tools.lorebook_tools import (
    mongodb_create_lorebook_entry,
    mongodb_get_lorebook_entry,
    mongodb_get_lorebook_entries,
    mongodb_get_lorebook_entries_by_tags,
    mongodb_list_lorebook_entries_by_ids,
    mongodb_update_lorebook_entry,
    mongodb_delete_lorebook_entry,
    mongodb_inject_lorebook_entries,
    mongodb_bulk_create_lorebook_entries,
    mongodb_get_lorebook_stats,
    mongodb_get_top_lorebook_entries,
)

# World Snapshot operations
from monitor_data.tools.mongodb_tools.snapshots import (
    mongodb_create_world_snapshot,
    mongodb_get_world_snapshot,
    mongodb_list_world_snapshots,
    mongodb_delete_world_snapshot,
    mongodb_restore_world_snapshot,
    mongodb_compare_snapshots,
)

# Tone Profile operations
from monitor_data.tools.mongodb_tools.tone_profiles import (
    mongodb_create_tone_profile,
    mongodb_get_tone_profile,
    mongodb_get_tone_profiles_batch,
    mongodb_list_tone_profiles,
    mongodb_update_tone_profile,
    mongodb_delete_tone_profile,
)

# Tone Library operations
from monitor_data.tools.mongodb_tools.tone_libraries import (
    mongodb_create_tone_library,
    mongodb_get_tone_library,
    mongodb_get_default_tone_library,
    mongodb_list_tone_libraries,
    mongodb_update_tone_library,
    mongodb_delete_tone_library,
)

# Tag Registry operations
from monitor_data.tools.mongodb_tools.tag_registry import (
    mongodb_create_tag_definition,
    mongodb_get_tag_definition,
    mongodb_list_tag_definitions,
    mongodb_update_tag_definition,
    mongodb_delete_tag_definition,
    mongodb_normalize_tag,
    mongodb_normalize_tags,
    mongodb_suggest_tags,
)

# PlaySession operations (P-15: Start Play Session)
from monitor_data.tools.mongodb_tools.play_sessions import (
    mongodb_create_play_session,
    mongodb_get_play_session,
    mongodb_list_play_sessions,
    mongodb_update_play_session,
    mongodb_add_scene_to_play_session,
    mongodb_get_latest_play_session,
    mongodb_list_recent_play_sessions,
)

# Merge Candidate operations (I-13: Cross-Source Synthesis)
from monitor_data.tools.mongodb_tools.merge_candidates import (
    mongodb_list_merge_candidates,
    mongodb_get_merge_candidate,
    mongodb_save_merge_candidate,
    mongodb_mark_candidate_reviewed,
    mongodb_delete_merge_candidate,
    mongodb_detect_merge_candidates,
    mongodb_create_merge_proposal,
    mongodb_get_merge_proposal,
    mongodb_list_merge_proposals,
    mongodb_update_merge_proposal_status,
)

__all__ = [
    # Scenes
    "get_mongodb_client",
    "get_neo4j_client",
    "_convert_turn_dict_to_response",
    "_convert_scene_doc_to_response",
    "mongodb_create_scene",
    "mongodb_get_scene",
    "mongodb_get_recent_turns",
    "mongodb_get_scene_summary",
    "mongodb_update_scene",
    "mongodb_list_scenes",
    "mongodb_append_turn",
    "mongodb_update_turn_resolution",
    # Change log (audit trail)
    "make_change_log_entry",
    "mongodb_append_change_log",
    "mongodb_list_change_log",
    # Proposals
    "_convert_proposed_change_doc_to_response",
    "mongodb_create_proposed_change",
    "mongodb_get_proposed_change",
    "mongodb_list_proposed_changes",
    "mongodb_update_proposed_change",
    # Stories
    "_convert_story_outline_doc_to_response",
    "_calculate_pacing_metrics",
    "mongodb_create_story_outline",
    "mongodb_get_story_outline",
    "mongodb_update_story_outline",
    # Combat
    "_convert_combat_doc_to_response",
    "mongodb_create_combat",
    "mongodb_get_combat",
    "mongodb_list_combats",
    "mongodb_update_combat",
    "mongodb_delete_combat",
    "mongodb_add_combat_participant",
    "mongodb_update_combat_participant",
    "mongodb_remove_combat_participant",
    "mongodb_add_combat_log_entry",
    "mongodb_set_combat_outcome",
    # Resolutions
    "_convert_resolution_doc_to_response",
    "mongodb_create_resolution",
    "mongodb_get_resolution",
    "mongodb_list_resolutions",
    "mongodb_update_resolution",
    "mongodb_delete_resolution",
    # Memories
    "mongodb_create_memory",
    "mongodb_get_memory",
    "mongodb_list_memories",
    "mongodb_update_memory",
    "mongodb_delete_memory",
    "mongodb_verify_memory",
    # Game Systems
    "_load_builtin_game_systems",
    "_ensure_builtin_systems_seeded",
    "mongodb_create_game_system",
    "mongodb_get_game_system",
    "mongodb_list_game_systems",
    "mongodb_update_game_system",
    "mongodb_delete_game_system",
    "mongodb_create_rule_override",
    "mongodb_get_rule_override",
    "mongodb_list_rule_overrides",
    "mongodb_update_rule_override",
    "mongodb_delete_rule_override",
    # Party + Character Inventory
    "mongodb_create_party_inventory",
    "mongodb_get_party_inventory",
    "mongodb_add_inventory_item",
    "mongodb_remove_inventory_item",
    "mongodb_update_party_gold",
    "mongodb_transfer_item",
    "mongodb_create_party_split",
    "mongodb_get_active_splits",
    "mongodb_resolve_party_split",
    "mongodb_get_split_history",
    "mongodb_create_character_inventory",
    "mongodb_get_character_inventory",
    "mongodb_add_character_item",
    "mongodb_remove_character_item",
    "mongodb_update_character_gold",
    "mongodb_equip_item",
    # Working State
    "_convert_working_state_doc_to_response",
    "mongodb_create_working_state",
    "mongodb_get_working_state",
    "mongodb_update_working_state",
    "mongodb_add_modification",
    "mongodb_list_working_states",
    # Ingestion Jobs
    "_convert_ingestion_job_doc",
    "mongodb_create_ingestion_job",
    "mongodb_delete_ingestion_job",
    "mongodb_get_ingestion_job",
    "mongodb_update_ingestion_job",
    "mongodb_list_ingestion_jobs",
    # Knowledge Packs
    "_convert_knowledge_pack_doc",
    "mongodb_create_knowledge_pack",
    "mongodb_get_knowledge_pack",
    "mongodb_update_knowledge_pack",
    "mongodb_list_knowledge_packs",
    "mongodb_delete_knowledge_pack",
    "mongodb_count_pack_dependents",
    "mongodb_apply_knowledge_pack",
    # Character Sheets
    "_character_sheet_doc_to_response",
    "mongodb_create_character_sheet",
    "mongodb_get_character_sheet",
    "mongodb_update_character_sheet",
    "mongodb_list_character_sheets",
    # Documents
    "mongodb_find_document_by_filename",
    "mongodb_create_document",
    "mongodb_get_document",
    "mongodb_list_documents",
    "mongodb_update_document",
    "mongodb_record_verdict",
    # NPC Profiles
    "_npc_profile_doc_to_response",
    "mongodb_create_npc_profile",
    "mongodb_get_npc_profile",
    "mongodb_update_npc_profile",
    # Character operations
    "mongodb_get_character",
    # Conversations
    "_conversation_doc_to_response",
    "mongodb_create_conversation",
    "mongodb_get_conversation",
    "mongodb_get_recent_conversation_turns",
    "mongodb_append_conversation_turn",
    "mongodb_update_conversation",
    "mongodb_list_conversations",
    # Profiles
    "_convert_gm_profile_doc",
    "mongodb_upsert_world_profile",
    "mongodb_get_world_profile",
    "mongodb_create_gm_profile",
    "mongodb_get_gm_profile",
    "mongodb_update_gm_profile",
    "mongodb_list_gm_profiles",
    "mongodb_delete_gm_profile",
    # Random Tables
    "mongodb_create_random_table",
    "mongodb_get_random_table",
    "mongodb_list_random_tables",
    "mongodb_update_random_table",
    "mongodb_delete_random_table",
    "mongodb_roll_on_table",
    # Entity Templates
    "mongodb_create_entity_template",
    "mongodb_get_entity_template",
    "mongodb_list_entity_templates",
    "mongodb_update_entity_template",
    "mongodb_delete_entity_template",
    "mongodb_increment_template_usage",
    # World Snapshots
    "mongodb_create_world_snapshot",
    "mongodb_get_world_snapshot",
    "mongodb_list_world_snapshots",
    "mongodb_delete_world_snapshot",
    "mongodb_restore_world_snapshot",
    "mongodb_compare_snapshots",
    # Tone Profiles
    "mongodb_create_tone_profile",
    "mongodb_get_tone_profile",
    "mongodb_get_tone_profiles_batch",
    "mongodb_list_tone_profiles",
    "mongodb_update_tone_profile",
    "mongodb_delete_tone_profile",
    # Tone Libraries
    "mongodb_create_tone_library",
    "mongodb_get_tone_library",
    "mongodb_get_default_tone_library",
    "mongodb_list_tone_libraries",
    "mongodb_update_tone_library",
    "mongodb_delete_tone_library",
    # Tag Registry
    "mongodb_create_tag_definition",
    "mongodb_get_tag_definition",
    "mongodb_list_tag_definitions",
    "mongodb_update_tag_definition",
    "mongodb_delete_tag_definition",
    "mongodb_normalize_tag",
    "mongodb_normalize_tags",
    "mongodb_suggest_tags",
    # Mlay Sessions (P-15)
    "mongodb_create_play_session",
    "mongodb_get_play_session",
    "mongodb_list_play_sessions",
    "mongodb_update_play_session",
    "mongodb_add_scene_to_play_session",
    "mongodb_get_latest_play_session",
    "mongodb_list_recent_play_sessions",
    # Perge Candidates (I-13)
    "mongodb_list_merge_candidates",
    "mongodb_get_merge_candidate",
    "mongodb_save_merge_candidate",
    "mongodb_mark_candidate_reviewed",
    "mongodb_delete_merge_candidate",
    "mongodb_detect_merge_candidates",
    "mongodb_create_merge_proposal",
    "mongodb_get_merge_proposal",
    "mongodb_list_merge_proposals",
    "mongodb_update_merge_proposal_status",
    # Party
    "mongodb_get_party_inventory",
    # Lorebook
    "mongodb_create_lorebook_entry",
    "mongodb_get_lorebook_entry",
    "mongodb_get_lorebook_entries",
    "mongodb_get_lorebook_entries_by_tags",
    "mongodb_list_lorebook_entries_by_ids",
    "mongodb_update_lorebook_entry",
    "mongodb_delete_lorebook_entry",
    "mongodb_inject_lorebook_entries",
    "mongodb_bulk_create_lorebook_entries",
    "mongodb_get_lorebook_stats",
    "mongodb_get_top_lorebook_entries",
]
