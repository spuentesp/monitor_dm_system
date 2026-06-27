/**
 * Centralized React Query Keys for the entire MONITOR UI.
 * Standardizing these prevents desync and refresh bugs.
 */

export const FORGE_KEYS = {
  jobs: ["forge-jobs"] as const,
  sources: ["forge-sources"] as const,
  packs: ["forge-packs"] as const,
  system: (systemId?: string | null) => ["forge-system", systemId] as const,
  assets: (opts?: { source_id?: string; universe_id?: string; asset_type?: string; limit?: number; offset?: number }) =>
    ["forge-assets", opts] as const,
  proposals: (packId: string) => ["forge-proposals", packId] as const,
};

export const PLAY_KEYS = {
  sessions: ["play-sessions"] as const,
  benchmarks: ["play-benchmarks"] as const,
  messages: (sessionId: string | null) => ["play-messages", sessionId] as const,
  state: (sessionId: string | null) => ["play-session-state", sessionId] as const,
  universes: (multiverseId?: string) => ["play-universes", multiverseId] as const,
  characters: (systemId?: string) => ["play-characters", systemId] as const,
};

export const SETTINGS_KEYS = {
  providers: ["llm-providers"] as const,
  assignments: ["llm-assignments"] as const,
  modules: ["prompt-modules"] as const,
  module: (id: string) => ["prompt-module", id] as const,
  databases: ["databases"] as const,
};

export const ENTITY_KEYS = {
  systems: ["systems"] as const,
  system: (id: string) => ["system", id] as const,
  npcs: (params?: any) => ["npcs", params] as const,
  npc: (id: string) => ["npc", id] as const,
  characters: (systemId?: string) => ["play-characters", systemId] as const,
  standaloneCharacters: (params?: any) => ["standalone-characters", params] as const,
  standaloneCharacter: (id: string) => ["standalone-character", id] as const,
  characterMemories: (id: string) => ["character-memories", id] as const,
  characterConversations: (id: string) => ["character-conversations", id] as const,
};

export const WORLDS_KEYS = {
  graph: (filter?: unknown) => ["worldGraph", filter] as const,
  graphBase: ["worldGraph"] as const,
  entitySearch: (q: string) => ["entitySearch", q] as const,
};

export const UNIVERSE_KEYS = {
  multiverses: ["multiverses"] as const,
  universes: (mvId?: string) => ["universes", mvId] as const,
  universe: (id: string) => ["universe", id] as const,
};

export const STORY_KEYS = {
  story: (id: string) => ["story", id] as const,
  scenes: (id: string) => ["story-scenes", id] as const,
};
