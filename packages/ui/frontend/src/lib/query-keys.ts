/**
 * Centralized React Query Keys for the entire MONITOR UI.
 * Standardizing these prevents desync and refresh bugs.
 */

export const FORGE_KEYS = {
  jobs: ["forge-jobs"] as const,
  jobsHealth: ["forge-jobs-health"] as const,
  sources: ["forge-sources"] as const,
  packs: ["forge-packs"] as const,
  system: (systemId?: string | null) => ["forge-system", systemId] as const,
  assets: (opts?: { source_id?: string; universe_id?: string; asset_type?: string; limit?: number; offset?: number }) =>
    ["forge-assets", opts] as const,
  proposals: (packId: string) => ["forge-proposals", packId] as const,
  promptCollections: (params?: { category?: string; system_id?: string; universe_id?: string }) =>
    ["forge-prompt-collections", params ?? {}] as const,
  promptCollection: (id: string) => ["forge-prompt-collection", id] as const,
};

export const PLAY_KEYS = {
  sessions: ["play-sessions"] as const,
  benchmarks: ["play-benchmarks"] as const,
  messages: (sessionId: string | null) => ["play-messages", sessionId] as const,
  state: (sessionId: string | null) => ["play-session-state", sessionId] as const,
  universes: (multiverseId?: string) => ["play-universes", multiverseId] as const,
  characters: (systemId?: string) => ["play-characters", systemId] as const,
  personas: ["play-personas"] as const,
  recap: (sessionId: string) => ["session-recap", sessionId] as const,
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
  systemDetail: (id: string) => ["system-detail", id] as const,
  npcs: (params?: any) => ["npcs", params] as const,
  npc: (id: string) => ["npc", id] as const,
  characters: (systemId?: string) => ["play-characters", systemId] as const,
  standaloneCharacters: (params?: any) => ["standalone-characters", params] as const,
  standaloneCharacter: (id: string) => ["standalone-character", id] as const,
  characterMemories: (id: string) => ["character-memories", id] as const,
  characterConversations: (id: string) => ["character-conversations", id] as const,
  entities: (params?: Record<string, unknown>) => ["entities", params] as const,
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
  stories: (universeId: string) => ["universe-stories", universeId] as const,
  scenes: (id: string) => ["story-scenes", id] as const,
  turns: (sceneId: string) => ["scene-turns", sceneId] as const,
  threads: (storyId: string) => ["story-threads", storyId] as const,
};

export const ARCHITECT_KEYS = {
  graph: (mvId?: string | null, uvId?: string | null) =>
    ["architect-graph", mvId, uvId] as const,
  sessions: ["architect-sessions"] as const,
  coverage: (
    uvId?: string | null,
    opts?: { requireMechanics?: boolean; requireRandomTables?: boolean },
  ) => ["architect-coverage", uvId, opts] as const,
  coverageBase: ["architect-coverage"] as const,
};

export const BENCHMARK_KEYS = {
  sessions: ["benchmark-sessions"] as const,
  sessionState: (id?: string | null) => ["benchmark-session-state", id] as const,
  sessionMessages: (id?: string | null) => ["benchmark-session-messages", id] as const,
};

export const CANON_KEYS = {
  queue: ["canon-queue"] as const,
  review: (sceneId: string) => ["canon-review", sceneId] as const,
};

export const CHANGE_LOG_KEYS = {
  all: ["change-log"] as const,
  subject: (subjectType: string) => ["change-log", subjectType] as const,
};
