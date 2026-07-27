/**
 * Gap-code → composer prompt mapping (F2-1 gap-driven building).
 *
 * Each coverage gap emitted by the backend (`world_coverage.py`) maps to a
 * suggested next prompt for the World Architect. Clicking a gap in the
 * coverage panel pre-fills the composer with the mapped prompt; the user
 * edits or sends. Codes without an explicit entry fall back to the gap's
 * human-readable message.
 */

import type { CoverageGap } from "./types";

const GAP_PROMPTS: Record<string, string> = {
  // A. Identity
  no_world_name: "Give this world a name.",
  no_genre: "Define the genre of this world.",
  no_tone: "Define the tone of this world.",
  no_narrative_frame: "Describe the narrative frame — the playstyle perspective — of this world.",
  no_default_system: "Bind a default game system to this universe.",

  // B. Entity taxonomy
  no_entities: "Create the first entities of this world.",
  few_entities: "Add more entities to flesh out the world.",
  stub_only_entities: "Flesh out one of the stub entities with a full description.",

  // C. Fact taxonomy
  no_facts: "Record a lore fact about the world.",
  few_facts: "Add more lore facts about the world.",
  no_entity_refs: "Add a fact that references the existing entities.",
  no_current_conflict: "Introduce a current conflict or threat that is driving play right now.",

  // D. Axioms
  no_axioms: "Define a foundational axiom — a rule that is always true in this world.",

  // E. Relationships
  no_relationships: "Connect the entities with relationships.",
  isolated_entities: "Connect the isolated entities to the rest of the world.",
  factions_without_members: "Add a faction with members.",
  npcs_without_affiliations: "Give an NPC an affiliation with a faction.",

  // F. Mechanics
  system_not_linked: "Link the named game system to this universe.",
  no_linked_system: "Link a game system to this universe.",
  no_core_mechanic: "Define the core mechanic of the game system.",
  no_attributes: "Define the attributes of the game system.",
  no_skills: "Define the skills of the game system.",
  no_resolution_mechanics: "Define a resolution mechanic for the game system.",
  no_combat_rules: "Define combat rules for the game system.",
  no_social_rules: "Define social rules for the game system.",
  no_conditions: "Define conditions for the game system.",
  no_advancement: "Define an advancement model for the game system.",
  no_character_creation: "Define a character creation procedure for the game system.",

  // G. Random tables
  no_random_tables: "Create a random table for this world (e.g. encounters or loot).",
  unlinked_tables: "Link a random table to this universe or its system.",

  // H. Provenance
  no_source_refs: "Attach source references to the facts and axioms.",
  low_provenance: "Attach source references to more of the facts and axioms.",
  pending_review: "Review the pending proposals.",
};

/** Suggested next architect prompt for a coverage gap. */
export function promptForGap(gap: CoverageGap): string {
  return GAP_PROMPTS[gap.code] ?? `Help me address this gap: ${gap.message}`;
}
