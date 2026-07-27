import { 
  Layers, 
  Scroll, 
  Swords, 
  FileText, 
  Wand2,
  BookOpen,
  Cpu,
  BrainCircuit,
  Settings2
} from "lucide-react";
import type { IngestJob } from "@/lib/types";

export const LIVE_JOB_STATUSES = new Set([
  "pending",
  "running",
  "retrying",
  "backing_off",
  "processing",
  "extracting",
  "canonizing"
]);

export const TERMINAL_JOB_STATUSES = new Set([
  "completed",
  "indexed",
  "done",
  "failed",
  "error",
  "cancelled",
  "killed"
]);

export const FAILED_JOB_STATUSES = new Set(["failed", "error", "killed"]);

export const SCAN_TYPES = [
  { value: "setting_supplement", label: "Lore & World",  icon: Layers,   color: "text-cyan-400"   },
  { value: "rulebook",           label: "Ruleset",       icon: Scroll,   color: "text-purple-400" },
  { value: "adventure_module",   label: "Adventure",     icon: Swords,   color: "text-amber-400"  },
  { value: "session_notes",      label: "Session Notes", icon: FileText, color: "text-emerald-400"},
  { value: "homebrew",           label: "Homebrew",      icon: Wand2,    color: "text-rose-400"   },
] as const;

export type ScanType = (typeof SCAN_TYPES)[number]["value"];

export const INGEST_TARGETS = [
  { id: "everything", label: "Everything", description: "Setting pack + system extraction" },
  { id: "setting", label: "Setting only", description: "World lore, entities, hazards, and setting rules" },
  { id: "system", label: "System only", description: "Dice math, attributes, and mechanical procedures" },
] as const;

export type IngestTarget = (typeof INGEST_TARGETS)[number]["id"];

export const PROCESSING_LAYERS = [
  { id: "axioms", label: "World laws", hint: "Foundational truths, magic laws, cosmic structure." },
  { id: "entities", label: "Entities", hint: "Characters, factions, places, creatures." },
  { id: "lore", label: "Lore & Rules", hint: "Setting facts, consequences, cultural norms." },
  { id: "game_system", label: "Core Math", hint: "Dice engine, stats, resolution math." },
  { id: "rules", label: "Procedures", hint: "Turn flow, combat steps, action handling." },
] as const;

export const DEFAULT_LAYERS_BY_SCAN_TYPE: Record<ScanType, string[]> = {
  setting_supplement: ["axioms", "entities", "lore", "game_system", "rules"],
  rulebook: ["game_system", "rules", "entities", "lore", "axioms"],
  adventure_module: ["entities", "lore", "axioms", "game_system", "rules"],
  session_notes: ["entities", "lore", "axioms", "game_system", "rules"],
  homebrew: ["axioms", "entities", "lore", "game_system", "rules"],
};

export function getLayersForTarget(target: IngestTarget, scanType: ScanType): string[] {
  if (target === "setting") return ["axioms", "entities", "lore"];
  if (target === "system") return ["game_system", "rules"];
  return DEFAULT_LAYERS_BY_SCAN_TYPE[scanType];
}

/**
 * Merges a new list of jobs into the existing cache safely.
 * Prevents newer SSE-driven progress from being overwritten by stale polling data.
 */
export function mergeJobsSafely(prev: IngestJob[] | undefined, incoming: IngestJob[]): IngestJob[] {
  if (!prev || !prev.length) return incoming;
  
  return incoming.map(newJob => {
    const existing = prev.find(j => j.id === newJob.id);
    if (!existing) return newJob;
    
    // If existing job in cache is already terminal, but incoming says it's running (stale poll), 
    // keep the terminal state.
    const existingIsTerminal = TERMINAL_JOB_STATUSES.has(existing.status);
    const incomingIsTerminal = TERMINAL_JOB_STATUSES.has(newJob.status);
    
    if (existingIsTerminal && !incomingIsTerminal) {
      return existing;
    }
    
    // If progress in cache is higher for the same status, keep the cache version
    if (existing.status === newJob.status && (existing.progress ?? 0) > (newJob.progress ?? 0)) {
      return existing;
    }
    
    return newJob;
  });
}
