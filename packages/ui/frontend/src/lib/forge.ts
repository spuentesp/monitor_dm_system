import type { ElementType } from "react";
import {
  BookOpen,
  Globe2,
  Layers,
  MapPin,
  Package,
  Scan,
  Scroll,
  Sparkles,
  Users,
  Dice5,
  Copy,
} from "lucide-react";

export const ENTITY_TYPE_CONFIG: Record<
  string,
  { color: string; tag: string; icon: ElementType }
> = {
  character: { color: "text-cyan-400", tag: "tag-cyan", icon: Users },
  faction: { color: "text-purple-400", tag: "tag-purple", icon: Users },
  location: { color: "text-amber-400", tag: "tag-amber", icon: MapPin },
  object: { color: "text-emerald-400", tag: "tag-emerald", icon: Package },
  concept: { color: "text-blue-400", tag: "tag-dim", icon: Sparkles },
  organization: { color: "text-rose-400", tag: "tag-red", icon: Globe2 },
};

export const FORGE_TABS = [
  { id: "entities", label: "Entities", icon: Users, hint: "People, factions, places, creatures, and objects." },
  { id: "axioms", label: "Axioms", icon: Scroll, hint: "Foundational truths and laws of the world." },
  { id: "lore", label: "Lore", icon: BookOpen, hint: "Setting-specific facts, hazards, consequences, and world rules." },
  { id: "rules", label: "Core System", icon: Layers, hint: "Dice math, action procedures, and rulebook logic for the linked system." },
  { id: "templates", label: "Templates", icon: Copy, hint: "Entity templates for instantiating NPCs, creatures, and locations." },
  { id: "tables", label: "Tables", icon: Dice5, hint: "Random tables for encounters, loot, names, and more." },
  { id: "profile", label: "Profile", icon: Scan, hint: "Inferred source profile — genre, tone, taxonomy, vocabulary, and confidence." },
] as const;

export type ForgeTabId = (typeof FORGE_TABS)[number]["id"];

export const AXIOM_DOMAIN_OPTIONS = [
  "world",
  "cosmology",
  "magic",
  "society",
  "religion",
  "technology",
  "history",
  "rules",
  "game_system",
] as const;

export const FACT_TYPE_OPTIONS = [
  "state",
  "relationship",
  "attribute",
  "occurrence",
  "rule",
  "mechanic",
] as const;

export const RULE_TYPE_OPTIONS = [
  "mechanic",
  "economy",
  "action",
  "condition",
  "advancement",
  "combat",
  "social",
  "exploration",
  "custom",
] as const;
