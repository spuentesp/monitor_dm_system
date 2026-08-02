import type {
  ActiveMode,
  AlertConfig,
  BatchVerdictResponse,
  CanonQueue,
  ChangeLogListResponse,
  DatabaseStatus,
  IngestJob,
  IngestJobReview,
  JobsHealthResponse,
  KnowledgePack,
  LLMConnection,
  LLMTaskAttempt,
  Message,
  ModeConfig,
  Multiverse,
  NPC,
  NodeAssignment,
  EntityDetail,
  EntityRelationship,
  NPCDetail,
  NPCProfile,
  NPCProfileUpsert,
  OntologyAxiom,
  OntologyEvent,
  OntologyFact,
  PaginatedNPCs,
  PerformanceAlert,
  PerformanceOverview,
  PerformanceReport,
  ProposalItem,
  PromptModuleDetail,
  PromptModuleSummary,
  PromptTestResult,
  RPGSystem,
  SceneReview,
  Session,
  SlowQuery,
  Source,
  Character,
  StandaloneCharacter,
  CharacterExpandResult,
  CharacterCardDraft,
  CharacterVersion,
  ConversationStart,
  CharacterReply,
  CharacterConversation,
  ChatSessionState,
  PlaytestBenchmark,
  TestResult,
  Universe,
  VerdictItem,
  VerdictByFilterRequest,
  VerdictByFilterResponse,
  WorldGraph,
  WorldGraphFilter,
  SemanticSearchResponse,
  ToneProfile,
  ToneLibrary,
  TagCategory,
  PromptCollection,
  PromptCollectionListResponse,
  PromptCollectionVersion,
  PromptCollectionVersionListResponse,
  TagDefinition,
  BinaryAsset,
  StoryResponse,
  StorySummary,
  StoryThread,
  SceneSummary,
  SceneTurn,
  PlotHook,
  Contradiction,
  CaptureInsight,
  SessionPrep,
  WrapUpDigest,
  Handout,
  EntityTemplate,
  EntityTemplateListResponse,
  InstantiateTemplateResponse,
  RandomTable,
  RandomTableListResponse,
  RollResult,
  WorldSnapshot,
  SnapshotComparison,
  WorldCoverage,
  LorebookScanConfig,
  GeneratedAsset,
  GeneratedAssetListFilter,
  AssetApprovalRequest,
  AssetRejectRequest,
  PortraitResponse,
  SceneResponse,
  TriggerSource,
  VisualIdentity,
  VisualIdentityStatus,
  VisualIdentityUpdate,
  ImageGenerationSettings,
} from "./types";

const RAW_API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";
const BASE = RAW_API_BASE.replace(/\/$/, "");
// Explicit WebSocket base. Defaults to deriving from NEXT_PUBLIC_API_URL,
// or — for same-origin deployments — from window.location. The Next.js App
// Router route handler at app/api/[...path]/route.ts does NOT proxy WebSocket
// upgrades, so non-localhost deploys MUST set NEXT_PUBLIC_WS_URL to a URL
// whose ingress (reverse proxy / CDN / load balancer) is configured to
// upgrade /api/chat/ws/* connections to the backend.
const RAW_WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "";

export function apiUrl(path: string): string {
  return `${BASE}/api${path}`;
}

export function websocketBase(): string {
  if (RAW_WS_BASE) return RAW_WS_BASE.replace(/\/$/, "");
  if (BASE) return BASE.replace(/^http/, "ws");
  if (typeof window === "undefined") return "ws://localhost:8000";

  const url = new URL(window.location.href);
  if (url.hostname === "localhost" || url.hostname === "127.0.0.1") {
    url.port = "8000";
    url.protocol = "ws:";
    return url.origin;
  }

  // Non-localhost without an explicit WS base. Same-origin will only work if
  // a reverse proxy in front of the Next.js server upgrades /api/chat/ws/*
  // to the backend. Surface a single console warning so deployers see it.
  if (typeof window !== "undefined" && !warnedAboutWsFallback) {
    warnedAboutWsFallback = true;
    // eslint-disable-next-line no-console
    console.warn(
      "[MONITOR] NEXT_PUBLIC_WS_URL is unset and the page is not on localhost. " +
        "Assuming a reverse proxy upgrades /api/chat/ws/* to the backend. " +
        "If chat fails to connect, set NEXT_PUBLIC_WS_URL to the backend's wss:// endpoint.",
    );
  }
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.origin;
}

let warnedAboutWsFallback = false;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Default request timeout in milliseconds (30 seconds). */
const DEFAULT_TIMEOUT_MS = 30_000;

export async function req<T>(
  path: string,
  opts?: RequestInit & { query?: Record<string, string | number | boolean | undefined>; timeout?: number },
): Promise<T> {
  let url = apiUrl(path);
  if (opts?.query) {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.query)) {
      if (v !== undefined) params.set(k, String(v));
    }
    const qs = params.toString();
    if (qs) url += `?${qs}`;
  }
  const { query: _q, timeout = DEFAULT_TIMEOUT_MS, ...fetchOpts } = opts ?? {};

  // AbortController for timeout + caller-provided signal
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);

  // If the caller already provided a signal, forward its abort too
  const callerSignal = fetchOpts.signal;
  if (callerSignal) {
    callerSignal.addEventListener("abort", () => controller.abort(), { once: true });
  }

  try {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...fetchOpts.headers },
      ...fetchOpts,
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new ApiError(res.status, text);
    }
    if (res.status === 204) return undefined as unknown as T;
    return res.json() as Promise<T>;
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError(408, `Request timed out after ${timeout}ms`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// ─── Chat ────────────────────────────────────────────────────

export const chatApi = {
  listSessions: () => req<Session[]>("/chat"),
  listBenchmarks: () => req<PlaytestBenchmark[]>("/chat/benchmarks"),
  getSessionState: (sessionId: string) => req<ChatSessionState>(`/chat/${sessionId}/state`),
  createSession: (data: {
    title?: string;
    mode?: string;
    multiverse_id?: string | null;
    multiverse_label?: string | null;
    universe_id?: string | null;
    universe_label?: string | null;
    world_id?: string | null;
    character_id?: string | null;
    speaker_character_id?: string | null;
    speaker_label?: string | null;
    persona_id?: string | null;
    controlled_character_ids?: string[];
    system_id?: string | null;
    pack_id?: string | null;
    system_source_type?: string | null;
    system_source_id?: string | null;
    system_label?: string | null;
    benchmark_id?: string | null;
    benchmark_label?: string | null;
    tone?: string;
    story_premise?: string | null;
    play_mode?: string;
    scene_id?: string | null;
    story_id?: string | null;
  }) =>
    req<Session>("/chat", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getMessages: (sessionId: string) =>
    req<Message[]>(`/chat/${sessionId}/messages`),
  sendMessage: (sessionId: string, content: string, options?: { chat_mode?: "ic" | "ooc"; character_id?: string; is_ooc_persona?: boolean }) =>
    // Narrated turns regularly take 15–60s (intent → resolution → narration),
    // so the default 30s timeout would abort real turns mid-flight (T-073).
    req<Message>(`/chat/${sessionId}/send`, {
      method: "POST",
      body: JSON.stringify({ content, ...options }),
      timeout: 180_000,
    }),
  patchSession: (
    sessionId: string,
    data: { title?: string; tone?: string; scene_id?: string; story_id?: string; roll_model?: string },
  ) =>
    req<Session>(`/chat/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteSession: (sessionId: string) =>
    req<void>(`/chat/${sessionId}`, { method: "DELETE" }),
  endScene: (sessionId: string) =>
    req<Message>(`/chat/${sessionId}/end-scene`, { method: "POST", timeout: 180_000 }),
  // P1.3 — guided wrap-up for gm_assistant recordings: canonize + recap +
  // canon tally + open threads + next-prep teaser in one call. Several LLM
  // calls run server-side, hence the 180s timeout (mirrors endScene).
  wrapUp: (sessionId: string) =>
    req<WrapUpDigest>(`/chat/${sessionId}/wrap-up`, { method: "POST", timeout: 180_000 }),
  // [G-1](c) Skip-preplay: jump from Session Zero / char creation straight
  // into active_play without waiting for the system prompts to wrap up.
  // 180s timeout mirrors endScene — both calls may invoke the LLM prologue path.
  skipPreplay: (sessionId: string) =>
    req<Message>(`/chat/${sessionId}/skip-preplay`, { method: "POST", timeout: 180_000 }),
  // [P-19] Begin Story — confirm Session Zero agreements and bootstrap the
  // opening narration once the player has accepted the agreement summary.
  beginStory: (sessionId: string) =>
    req<Message>(`/chat/${sessionId}/begin`, { method: "POST", timeout: 180_000 }),
  getRecap: (sessionId: string) =>
    req<{ recap: string; story_id: string | null; universe_id: string | null; persisted?: boolean }>(
      `/chat/${sessionId}/recap`,
      { timeout: 120_000 },
    ),
};

export function createChatWebSocket(sessionId: string): WebSocket {
  return new WebSocket(`${websocketBase()}/api/chat/ws/${sessionId}`);
}

// ─── Modes ────────────────────────────────────────────────── 

export const modesApi = {
  list: () => req<ModeConfig[]>("/modes"),
  getActive: () => req<ActiveMode>("/modes/active"),
  setActive: (data: Partial<ActiveMode>) =>
    req<ActiveMode>("/modes/active", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ─── Ingest ───────────────────────────────────────────────── 

export const ingestApi = {
  listSources: () => req<Source[]>("/ingest/sources"),
  getSource: (id: string) => req<Source>(`/ingest/sources/${id}`),
  deleteSource: (id: string) =>
    req<void>(`/ingest/sources/${id}`, { method: "DELETE" }),
  uploadSource: async (
    file: File,
    options: {
      scan_type?: string;
      analysis_layers?: string[];
      ingest_now?: boolean;
      new_setting_name?: string;
      new_setting_system?: string;
      multiverse_id?: string;
      title?: string;
    },
  ): Promise<Source> => {
    const form = new FormData();
    form.append("file", file);
    if (options.scan_type)          form.append("scan_type",           options.scan_type);
    if (options.analysis_layers?.length) {
      for (const layer of options.analysis_layers) form.append("analysis_layers", layer);
    }
    if (typeof options.ingest_now === "boolean") form.append("ingest_now", String(options.ingest_now));
    if (options.new_setting_name)   form.append("new_setting_name",    options.new_setting_name);
    if (options.new_setting_system) form.append("new_setting_system",  options.new_setting_system);
    if (options.multiverse_id)      form.append("multiverse_id",       options.multiverse_id);
    if (options.title)              form.append("title",               options.title);
    const res = await fetch(apiUrl("/ingest/sources/upload"), {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
  listJobs: () => req<IngestJob[]>("/ingest/jobs"),
  getJob: (id: string) => req<IngestJob>(`/ingest/jobs/${id}`),
  listJobAttempts: (
    id: string,
    query?: { stage?: string; batch_id?: string; provider_id?: string; limit?: number },
  ) => req<LLMTaskAttempt[]>(`/ingest/jobs/${id}/attempts`, { query }),
  /**
   * Open an SSE stream for real-time job progress.
   * Returns an EventSource instance — the caller must close it.
   */
  streamJob: (id: string): EventSource => {
    return new EventSource(apiUrl(`/ingest/jobs/${id}/stream`));
  },
  rescanSource: async (
    sourceId: string,
    options?: {
      scan_type?: string;
      analysis_layers?: string[];
    },
  ) => {
    const params = new URLSearchParams();
    if (options?.scan_type) params.append("scan_type", options.scan_type);
    for (const layer of options?.analysis_layers ?? []) {
      params.append("analysis_layers", layer);
    }
    const qs = params.toString();
    return req<{ status: string; source_id: string; source_title: string; message: string }>(
      `/ingest/sources/${sourceId}/rescan${qs ? `?${qs}` : ""}`,
      { method: "POST" },
    );
  },
  unlockQueue: () =>
    req<{
      unlocked: boolean;
      was_locked_by: string | null;
      cleared_pending: number;
      cleared_active: number;
      recovered_jobs: number;
    }>("/ingest/unlock", {
      method: "POST",
    }),
  listPacks: (status?: string) =>
    req<KnowledgePack[]>("/ingest/packs", {
      query: status ? { status } : undefined,
    }),
  getPack: (id: string) => req<KnowledgePack>(`/ingest/packs/${id}`),
  updatePack: (
    id: string,
    body: {
      name?: string;
      axioms?: KnowledgePack["axioms"];
      entity_archetypes?: KnowledgePack["entity_archetypes"];
      lore_facts?: KnowledgePack["lore_facts"];
      entity_relationships?: KnowledgePack["entity_relationships"];
      source_profile_data?: KnowledgePack["source_profile_data"];
      chunk_summaries?: KnowledgePack["chunk_summaries"];
      section_summaries?: KnowledgePack["section_summaries"];
      source_mindscape?: KnowledgePack["source_mindscape"];
      tags?: string[];
      status?: string;
      game_system_id?: string | null;
      source_document_ids?: string[];
    },
  ) =>
    req<KnowledgePack>(`/ingest/packs/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  mergePacks: (body: { pack_ids: string[]; name?: string; strategy?: string }) =>
    req<KnowledgePack>("/ingest/packs/merge", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createPack: (body: { name: string; description?: string; pack_type?: string; system_name?: string; tags?: string[] }) =>
    req<KnowledgePack>("/ingest/packs", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deletePack: (id: string, hard = false) =>
    req<{ pack_id: string; action: string }>(`/ingest/packs/${id}?hard=${hard}`, { method: "DELETE" }),
  exportPack: (id: string) =>
    fetch(apiUrl(`/ingest/packs/${id}/export`))
      .then(r => r.ok ? r.blob() : Promise.reject(new Error("Export failed"))),
  importPack: (envelope: { schema_version: string; exported_at: string; pack: object }) =>
    req<KnowledgePack>("/ingest/packs/import", {
      method: "POST",
      body: JSON.stringify(envelope),
    }),
  clonePack: (id: string, body: { name?: string; with_lineage?: boolean }) =>
    req<KnowledgePack>(`/ingest/packs/${id}/clone`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  slicePack: (id: string, body: { name: string; entity_indices: number[]; axiom_indices: number[]; lore_indices: number[]; with_lineage?: boolean }) =>
    req<KnowledgePack>(`/ingest/packs/${id}/slice`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  applyPackNewWorld: (id: string, body: { world_name: string; system_name?: string }) =>
    req<{ pack_id: string; multiverse_id: string; universe_id: string; world_name: string; committed: number; errors: string[]; status: string }>(
      `/ingest/packs/${id}/apply/new-world`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  applyPackExistingWorld: (packId: string, universeId: string, body: { mode?: string; auto_commit_llm?: boolean; entity_indices?: number[]; axiom_indices?: number[]; lore_indices?: number[]; resolved_conflicts?: object[] }) =>
    req<{ status: string; conflicts?: object[]; committed?: number; errors?: string[] }>(
      `/ingest/packs/${packId}/apply/${universeId}`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  // ─── Proposal Review (I-4) ────────────────────────────────
  listProposals: (packId: string, opts?: { status?: string; change_type?: string; page?: number; per_page?: number }) =>
    req<{
      pack_id: string;
      proposals: ProposalItem[];
      summary: { total: number; pending: number; accepted: number; rejected: number };
      total: number;
      page: number;
      per_page: number;
    }>(`/ingest/packs/${packId}/proposals`, {
      query: opts as Record<string, string | number | undefined>,
    }),
  reviewProposal: (proposalId: string, action: "accept" | "reject", reason?: string) =>
    req<{ proposal_id: string; status: string; decision_metadata: { decided_by: string; decided_at: string; reason: string } }>(
      `/ingest/proposals/${proposalId}`,
      { method: "PATCH", body: JSON.stringify({ action, reason: reason ?? "" }) },
    ),
  batchReview: (actions: Array<{ proposal_id: string; action: "accept" | "reject"; reason?: string }>) =>
    req<{ accepted: number; rejected: number; errors: Array<{ proposal_id: string; error: string }> }>(
      "/ingest/proposals/batch",
      { method: "POST", body: JSON.stringify({ actions }) },
    ),
  commitAccepted: (packId: string) =>
    req<{ pack_id: string; committed: number; errors: string[]; status: string }>(
      `/ingest/packs/${packId}/commit`,
      { method: "POST" },
    ),

  deleteJob: (id: string) =>
    req<void>(`/ingest/jobs/${id}`, { method: "DELETE" }),
  cancelJob: (id: string) =>
    req<{ job_id: string; status: string; message: string }>(`/ingest/jobs/${id}/cancel`, { method: "POST" }),
  purgeFailedJobs: () =>
    req<{ deleted: number }>("/ingest/jobs", { method: "DELETE" }),

  // ─── Binary Assets (I-6) ────────────────────────────────
  uploadAsset: async (
    file: File,
    options: {
      source_id?: string;
      universe_id?: string;
      asset_type?: string;
      label?: string;
    },
  ): Promise<BinaryAsset> => {
    const form = new FormData();
    form.append("file", file);
    if (options.source_id)  form.append("source_id", options.source_id);
    if (options.universe_id) form.append("universe_id", options.universe_id);
    if (options.asset_type) form.append("asset_type", options.asset_type);
    if (options.label) form.append("label", options.label);
    const res = await fetch(apiUrl("/ingest/assets/upload"), {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
  listAssets: (opts?: { source_id?: string; universe_id?: string; asset_type?: string; limit?: number; offset?: number }) =>
    req<{ items: BinaryAsset[]; total: number; limit: number; offset: number }>("/ingest/assets", {
      query: opts as Record<string, string | number | undefined>,
    }),
  getAsset: (id: string) => req<BinaryAsset>(`/ingest/assets/${id}`),
  deleteAsset: (id: string) =>
    req<{ id: string; status: string }>(`/ingest/assets/${id}`, { method: "DELETE" }),
  replaceAsset: async (id: string, file: File): Promise<BinaryAsset> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(apiUrl(`/ingest/assets/${id}/replace`), {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
};

// ─── Ingestion Jobs Health (F1-2) ────────────────────────────
// Read-only operator snapshot: watchdog state, per-status counts (only 7 of
// 13 statuses — see JobsHealthResponse) and currently-stale running jobs.

export const jobsHealthApi = {
  health: () => req<JobsHealthResponse>("/jobs/health"),
};

// ─── LLM ─────────────────────────────────────────────────────

export const llmApi = {
  listProviders: () => req<LLMConnection[]>("/llm/providers"),
  addProvider: (data: {
    name: string;
    provider: string;
    model: string;
    api_key?: string | null;
    base_url?: string | null;
    is_default?: boolean;
    role?: string;
  }) =>
    req<LLMConnection>("/llm/providers", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateProvider: (
    id: string,
    data: Partial<{
      name: string;
      model: string;
      api_key: string;
      base_url: string;
      is_default: boolean;
      role: string;
    }>,
  ) =>
    req<LLMConnection>(`/llm/providers/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteProvider: (id: string) =>
    req<void>(`/llm/providers/${id}`, { method: "DELETE" }),
  duplicateProvider: (id: string, overrides?: { name?: string; model?: string; role?: string }) =>
    req<LLMConnection>(`/llm/providers/${id}/duplicate`, {
      method: "POST",
      body: JSON.stringify(overrides ?? {}),
    }),
  testProvider: (id: string) =>
    req<TestResult>(`/llm/providers/${id}/test`, { method: "POST" }),
  listModels: (provider: string) =>
    req<string[]>(`/llm/models/${provider}`),
  // Node assignments
  listAssignments: () => req<NodeAssignment[]>("/llm/assignments"),
  setAssignment: (nodeName: string, data: { provider_id: string; param_overrides?: Record<string, number | string | null>; notes?: string | null }) =>
    req<NodeAssignment>(`/llm/assignments/${nodeName}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteAssignment: (nodeName: string) =>
    req<void>(`/llm/assignments/${nodeName}`, { method: "DELETE" }),
};

// ─── Databases ────────────────────────────────────────────── 

export const toneApi = {
  listProfiles: () =>
    req<{ profiles: ToneProfile[]; total: number }>("/tone/profiles"),
  createProfile: (body: Partial<ToneProfile>) =>
    req<ToneProfile>("/tone/profiles", { method: "POST", body: JSON.stringify(body) }),
  updateProfile: (profileId: string, body: Partial<ToneProfile>) =>
    req<ToneProfile>(`/tone/profiles/${profileId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteProfile: (profileId: string) =>
    req<void>(`/tone/profiles/${profileId}`, { method: "DELETE" }),
  listLibraries: () =>
    req<{ libraries: ToneLibrary[]; total: number }>("/tone/libraries"),
  getLibrary: (libraryId: string) =>
    req<ToneLibrary>(`/tone/libraries/${libraryId}`),
  getDefaultLibrary: () => req<ToneLibrary>("/tone/libraries/default"),
  createLibrary: (body: {
    name: string;
    description?: string;
    tone_profile_ids?: string[];
    pack_id?: string | null;
    universe_id?: string | null;
    priority?: number;
    is_default?: boolean;
  }) =>
    req<ToneLibrary>("/tone/libraries", { method: "POST", body: JSON.stringify(body) }),
  updateLibrary: (
    libraryId: string,
    body: Partial<{
      name: string;
      description: string;
      tone_profile_ids: string[];
      universe_id: string | null;
      priority: number;
      is_default: boolean;
    }>,
  ) =>
    req<ToneLibrary>(`/tone/libraries/${libraryId}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteLibrary: (libraryId: string) =>
    req<void>(`/tone/libraries/${libraryId}`, { method: "DELETE" }),
  // Tag definitions (F3-4.3)
  listTags: (opts?: { category?: TagCategory }) =>
    req<{ tags: TagDefinition[]; total: number }>("/tone/tags", {
      query: { category: opts?.category },
    }),
  suggestTags: (partial: string, opts?: { category?: TagCategory; limit?: number }) =>
    req<{ suggestions: TagDefinition[]; partial: string; total_found: number }>(
      "/tone/tags/suggest",
      { query: { partial, category: opts?.category, limit: opts?.limit } },
    ),
  getTag: (tag: string) =>
    req<TagDefinition>(`/tone/tags/${encodeURIComponent(tag)}`),
  createTag: (body: {
    tag: string;
    category: TagCategory;
    synonyms?: string[];
    description?: string;
    is_builtin?: boolean;
  }) =>
    req<TagDefinition>("/tone/tags", { method: "POST", body: JSON.stringify(body) }),
  updateTag: (
    tag: string,
    body: Partial<{ synonyms: string[]; description: string; example_tones: string[] }>,
  ) =>
    req<TagDefinition>(`/tone/tags/${encodeURIComponent(tag)}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteTag: (tag: string) =>
    req<void>(`/tone/tags/${encodeURIComponent(tag)}`, { method: "DELETE" }),
};

export const lorebookApi = {
  list: (characterId: string, sortBy = "priority", ascending = false) =>
    req<unknown[]>("/lorebook/entries", {
      query: {
        character_id: characterId,
        sort_by: sortBy,
        ascending: String(ascending),
      },
    }),
  stats: (characterId: string) =>
    req<{ total_entries: number; total_triggers: number; [key: string]: unknown }>("/lorebook/stats", {
      query: { character_id: characterId },
    }),
  create: (characterId: string, body: unknown) =>
    req<unknown>(`/lorebook/entries?character_id=${encodeURIComponent(characterId)}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (entryId: string, body: unknown) =>
    req<unknown>(`/lorebook/entries/${entryId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  remove: (entryId: string) =>
    req<void>(`/lorebook/entries/${entryId}`, { method: "DELETE" }),
  bulkCreate: (characterId: string, entries: unknown[]) =>
    req<unknown[]>(`/lorebook/bulk?character_id=${encodeURIComponent(characterId)}`, {
      method: "POST",
      body: JSON.stringify(entries),
    }),
  import: async (characterId: string, file: File) => {
    const form = new FormData();
    form.append("character_id", characterId);
    form.append("file", file);
    const res = await fetch(apiUrl("/lorebook/import"), {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new ApiError(res.status, text);
    }
    return (await res.json()) as { imported: number; errors: string[]; entries: unknown[] };
  },
  export: (characterId: string) => {
    const params = new URLSearchParams({ character_id: characterId });
    window.open(`${apiUrl("/lorebook/export")}?${params.toString()}`, "_blank");
  },
  getScanConfig: (characterId: string) =>
    req<LorebookScanConfig>("/lorebook/scan-config", { query: { character_id: characterId } }),
  updateScanConfig: (characterId: string, body: LorebookScanConfig) =>
    req<LorebookScanConfig>("/lorebook/scan-config", {
      method: "PUT",
      query: { character_id: characterId },
      body: JSON.stringify(body),
    }),
};

export const searchApi = {
  search: (
    q: string,
    opts?: {
      universe_id?: string;
      entity_type?: string;
      canon_level?: string;
      collections?: string;
      limit?: number;
    },
  ) =>
    req<SemanticSearchResponse>("/search/search", {
      query: { q, ...opts },
    }),
  universeSearch: (
    universeId: string,
    q: string,
    opts?: { entity_type?: string; canon_level?: string; limit?: number },
  ) =>
    req<SemanticSearchResponse>(`/search/universes/${universeId}/search`, {
      query: { q, ...opts },
    }),
};

export const dbApi = {
  allStatus: () => req<DatabaseStatus[]>("/databases"),
  getStatus: (dbType: string) =>
    req<DatabaseStatus>(`/databases/${dbType}`),
};

// ─── Entities ─────────────────────────────────────────────── 

export const entitiesApi = {
  listNPCs: (params?: { q?: string; entity_type?: string; limit?: number; offset?: number }) =>
    req<PaginatedNPCs>("/entities/npcs", { query: params as Record<string, string | number | undefined> }),
  batchDeleteEntities: (entity_ids: string[], opts?: { force?: boolean; continue_on_error?: boolean }) =>
    req<{ deleted_ids: string[]; deleted_count: number; errors: { entity_id: string; error: string }[] }>(
      "/entities/batch",
      {
        method: "DELETE",
        body: JSON.stringify({ entity_ids, force: opts?.force ?? false, continue_on_error: opts?.continue_on_error ?? true }),
      },
    ),
  getNPC: (id: string) => req<NPCDetail>(`/entities/npcs/${id}`),
  // ── Single-entity CRUD on the graph (M-36 / M-38) ──
  getEntity: (id: string) => req<EntityDetail>(`/entities/entities/${id}`),
  createEntity: (body: {
    universe_id: string;
    name: string;
    entity_type?: string;
    description?: string;
    properties?: Record<string, unknown>;
  }) =>
    req<EntityDetail>("/entities/entities", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateEntity: (
    id: string,
    body: Partial<{
      name: string;
      description: string;
      properties: Record<string, unknown>;
      tags: string[];
    }>,
  ) =>
    req<EntityDetail>(`/entities/entities/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  // ── Graph edges / relationships (M-37) ──
  createRelationship: (body: {
    from_id: string;
    to_id: string;
    rel_type?: string;
    category?: string;
    properties?: Record<string, unknown>;
  }) =>
    req<EntityRelationship>("/entities/entities/edges", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listRelationships: (entityId: string) =>
    req<{ relationships: EntityRelationship[]; total: number }>(
      `/entities/entities/${entityId}/edges`,
    ),
  // ── Relationship edit/delete (F2-2 phase 2) ──
  updateRelationship: (
    relationshipId: string,
    body: Partial<{
      category: string;
      subcategory: string | null;
      properties: Record<string, unknown>;
      tags: string[];
    }>,
  ) =>
    req<EntityRelationship>(`/entities/entities/relationships/${relationshipId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteRelationship: (relationshipId: string) =>
    req<{ deleted: boolean; relationship_id: string }>(
      `/entities/entities/relationships/${relationshipId}`,
      { method: "DELETE" },
    ),
  listUniverseRelationships: (
    universeId: string,
    filters?: { rel_type?: string; category?: string; limit?: number; offset?: number },
  ) =>
    req<{ relationships: EntityRelationship[]; total: number; limit: number; offset: number }>(
      `/entities/entities/universes/${universeId}/relationships`,
      { query: filters as Record<string, string | number | undefined> },
    ),
  // ── Ontology CRUD: facts / axioms / events (F2-2 phase 1) ──
  listFacts: (
    universeId: string,
    filters?: {
      fact_type?: string;
      canon_level?: string;
      status?: string;
      scope?: string;
      entity_id?: string;
      min_magnitude?: number;
      limit?: number;
      offset?: number;
    },
  ) =>
    req<{ facts: OntologyFact[]; count: number; limit: number; offset: number }>(
      `/entities/entities/${universeId}/facts`,
      { query: filters as Record<string, string | number | undefined> },
    ),
  createFact: (
    universeId: string,
    body: {
      statement: string;
      fact_type?: string;
      magnitude?: number;
      scope?: string;
      canon_level?: string;
      knowledge_scope?: string;
      confidence?: number;
      status?: string;
      entity_ids?: string[];
      properties?: Record<string, unknown>;
    },
  ) =>
    req<OntologyFact>(`/entities/entities/${universeId}/facts`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateFact: (
    factId: string,
    body: Partial<{
      statement: string;
      canon_level: string;
      knowledge_scope: string;
      confidence: number;
      status: string;
      properties: Record<string, unknown>;
    }>,
  ) =>
    req<OntologyFact>(`/entities/entities/facts/${factId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteFact: (factId: string, opts?: { force?: boolean }) =>
    req<{ deleted: boolean }>(`/entities/entities/facts/${factId}`, {
      method: "DELETE",
      query: opts?.force ? { force: "true" } : undefined,
    }),
  listAxioms: (
    universeId: string,
    filters?: {
      domain?: string;
      canon_level?: string;
      scope?: string;
      min_magnitude?: number;
      limit?: number;
      offset?: number;
    },
  ) =>
    req<{ axioms: OntologyAxiom[]; count: number; limit: number; offset: number }>(
      `/entities/entities/${universeId}/axioms`,
      { query: filters as Record<string, string | number | undefined> },
    ),
  createAxiom: (
    universeId: string,
    body: {
      statement: string;
      domain: string;
      magnitude?: number;
      scope?: string;
      canon_level?: string;
      confidence?: number;
      source_ref?: string;
      tags?: string[];
      properties?: Record<string, unknown>;
    },
  ) =>
    req<OntologyAxiom>(`/entities/entities/${universeId}/axioms`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateAxiom: (
    axiomId: string,
    body: Partial<{
      statement: string;
      domain: string;
      magnitude: number;
      scope: string;
      canon_level: string;
      confidence: number;
      tags: string[];
      properties: Record<string, unknown>;
    }>,
  ) =>
    req<OntologyAxiom>(`/entities/entities/axioms/${axiomId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteAxiom: (axiomId: string, opts?: { force?: boolean }) =>
    req<{ deleted: boolean }>(`/entities/entities/axioms/${axiomId}`, {
      method: "DELETE",
      query: opts?.force ? { force: "true" } : undefined,
    }),
  listEvents: (
    universeId: string,
    filters?: {
      scene_id?: string;
      entity_id?: string;
      canon_level?: string;
      scope?: string;
      start_after?: string;
      start_before?: string;
      min_magnitude?: number;
      limit?: number;
      offset?: number;
    },
  ) =>
    req<{ events: OntologyEvent[]; count: number; limit: number; offset: number }>(
      `/entities/entities/${universeId}/events`,
      { query: filters as Record<string, string | number | undefined> },
    ),
  createEvent: (
    universeId: string,
    body: {
      title: string;
      description?: string;
      start_time: string;
      end_time?: string | null;
      magnitude?: number;
      scope?: string;
      canon_level?: string;
      knowledge_scope?: string;
      confidence?: number;
      entity_ids?: string[];
      properties?: Record<string, unknown>;
    },
  ) =>
    req<OntologyEvent>(`/entities/entities/${universeId}/events`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateEvent: (
    eventId: string,
    body: Partial<{
      title: string;
      description: string | null;
      start_time: string;
      end_time: string | null;
      magnitude: number;
      scope: string;
      canon_level: string;
      knowledge_scope: string;
      confidence: number;
      properties: Record<string, unknown>;
    }>,
  ) =>
    req<OntologyEvent>(`/entities/entities/events/${eventId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteEvent: (eventId: string, opts?: { force?: boolean }) =>
    req<{ deleted: boolean }>(`/entities/entities/events/${eventId}`, {
      method: "DELETE",
      query: opts?.force ? { force: "true" } : undefined,
    }),
  // ── NPC profile editor (F2-2 phase 5) ──
  getNPCProfile: (npcId: string) => req<NPCProfile>(`/entities/npcs/${npcId}/profile`),
  updateNPCProfile: (npcId: string, body: NPCProfileUpsert) =>
    req<NPCProfile>(`/entities/npcs/${npcId}/profile`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  listSystems: () => req<RPGSystem[]>("/entities/systems"),
  getSystem: (id: string) => req<RPGSystem>(`/entities/systems/${id}`),
  updateSystem: (
    id: string,
    body: Partial<
      Pick<
        RPGSystem,
        "name" | "description" | "version" | "rules" | "attributes" | "skills" | "resources"
      >
    > & { core_mechanic?: RPGSystem["core_mechanic"]; character_creation?: Record<string, unknown> },
  ) =>
    req<RPGSystem>(`/entities/systems/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  createSystem: (body: {
    name: string;
    description?: string;
    version?: string;
    attributes?: RPGSystem["attributes"];
    skills?: RPGSystem["skills"];
    resources?: RPGSystem["resources"];
    core_mechanic?: RPGSystem["core_mechanic"];
    character_creation?: Record<string, unknown>;
  }) =>
    req<RPGSystem>("/entities/systems", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteSystem: (id: string) =>
    req<void>(`/entities/systems/${id}`, { method: "DELETE" }),
  testSystem: (id: string) =>
    req<{ system_name: string; sheet: string; attributes: Record<string, unknown>; resources?: Record<string, unknown>; preview?: Record<string, unknown> }>(
      `/entities/systems/${id}/test`,
      { method: "POST" },
    ),
  testSystemNpc: (id: string, body?: { name?: string; concept?: string; tier?: string }) =>
    req<{ system_name: string; sheet: string; attributes: Record<string, unknown>; resources?: Record<string, unknown>; preview?: Record<string, unknown> }>(
      `/entities/systems/${id}/test-npc`,
      { method: "POST", body: JSON.stringify(body ?? {}) },
    ),
  generateEntity: (body: {
    system_id?: string;
    pack_id?: string;
    universe_id?: string;
    kind?: "pc" | "npc";
    save?: boolean;
    name?: string;
    description?: string;
    concept?: string;
    tier?: string;
    state_tags?: string[];
  }) =>
    req<{ source: Record<string, unknown>; preview: Record<string, unknown>; saved: Record<string, unknown> | null }>(
      `/entities/generate`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  listCharacters: (systemId: string) =>
    req<Character[]>(`/entities/systems/${systemId}/characters`),
  search: (q: string, limit?: number) =>
    req<Array<{ id: string; name: string; type: string; description: string }>>(
      "/entities/search",
      { query: { q, limit } },
    ),
  // ── Standalone Characters (Roleplay UI) ──
  listStandaloneCharacters: (params?: { limit?: number; offset?: number }) =>
    req<StandaloneCharacter[]>("/entities/characters", { query: params as Record<string, string | number | undefined> }),
  getStandaloneCharacter: (id: string) =>
    req<StandaloneCharacter>(`/entities/characters/${id}`),
  createStandaloneCharacter: (data: {
    name: string;
    description?: string;
    avatar_url?: string | null;
    personality?: string;
    gm_notes?: string;
    first_message?: string;
    is_ooc_persona?: boolean;
  }) =>
    req<StandaloneCharacter>("/entities/characters", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateStandaloneCharacter: (id: string, data: Partial<Omit<StandaloneCharacter, "id" | "created_at" | "updated_at" | "memory_count">>) =>
    req<StandaloneCharacter>(`/entities/characters/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteStandaloneCharacter: (id: string) =>
    req<void>(`/entities/characters/${id}`, { method: "DELETE" }),
  getCharacterMemories: (id: string, params?: { min_importance?: number; limit?: number }) =>
    req<{ memories: Array<{ id: string; text: string; importance: number; created_at: string }>; total: number }>(
      `/entities/characters/${id}/memories`,
      { query: params as Record<string, string | number | undefined> },
    ),
  clearCharacterMemories: (id: string) =>
    req<void>(`/entities/characters/${id}/memories`, { method: "DELETE" }),
  // SillyTavern/Tavern card interop (chara_card_v2 JSON or PNG)
  importCharacterCard: async (file: File): Promise<StandaloneCharacter> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(apiUrl("/entities/characters/import-card"), {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
  exportCharacterCardUrl: (id: string) => apiUrl(`/entities/characters/${id}/export-card`),

  // ── LLM-assisted card drafting ──
  draftCharacterCard: (body: {
    concept: string;
    name?: string;
    description?: string;
    personality?: string;
  }) =>
    req<CharacterCardDraft>("/entities/characters/draft", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // ── Conversatory (MONITOR-backed chat) ──
  expandCharacter: (id: string, body?: { universe_id?: string }) =>
    req<CharacterExpandResult>(`/entities/characters/${id}/expand`, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),

  // ── Character Versions (per-universe incarnations) ──
  listCharacterVersions: (id: string) =>
    req<CharacterVersion[]>(`/entities/characters/${id}/versions`),
  createCharacterVersion: (
    id: string,
    body: { universe_id?: string } = {}
  ) =>
    req<CharacterExpandResult>(`/entities/characters/${id}/versions`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteCharacterVersion: (id: string, universeId: string) =>
    req<void>(
      `/entities/characters/${id}/versions/${universeId}`,
      { method: "DELETE" },
    ),

  startCharacterConversation: (
    id: string,
    body: { universe_id?: string } = {}
  ) =>
    req<ConversationStart>(`/entities/characters/${id}/conversations`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sendCharacterMessage: (
    id: string,
    conversationId: string,
    text: string,
    options?: { include_cross_incarnation?: boolean }
  ) =>
    req<CharacterReply>(
      `/entities/characters/${id}/conversations/${conversationId}/send`,
      {
        method: "POST",
        body: JSON.stringify({
          text,
          include_cross_incarnation: options?.include_cross_incarnation ?? false,
        }),
      },
    ),
  endCharacterConversation: (id: string, conversationId: string) =>
    req<{ ended: boolean; proposals: number }>(
      `/entities/characters/${id}/conversations/${conversationId}/end`,
      { method: "POST" },
    ),
  listCharacterConversations: (id: string, limit = 20) =>
    req<CharacterConversation[]>(`/entities/characters/${id}/conversations`, {
      query: { limit },
    }),
};

// ─── Image generation, asset approval & visual identities ─────
// Generation endpoints return PENDING assets — nothing becomes an avatar or
// reference until approved through the /image/assets endpoints below.

export const imageApi = {
  generatePortrait: (
    characterId: string,
    provenance?: { trigger?: TriggerSource; source_turn_id?: string },
  ) =>
    req<PortraitResponse>("/image/portrait", {
      method: "POST",
      body: JSON.stringify({ character_id: characterId, ...provenance }),
      timeout: 120_000, // image generation is slow — mirrors the chat timeouts
    }),
  generateScene: (data: {
    conversation_id?: string;
    session_id?: string;
    last_n?: number;
    trigger?: TriggerSource;
    source_turn_id?: string;
  }) =>
    req<SceneResponse>("/image/scene", {
      method: "POST",
      body: JSON.stringify(data),
      timeout: 120_000,
    }),
  // ── Asset gallery / approval (Task 6 endpoints) ──
  listAssets: (filter?: GeneratedAssetListFilter) =>
    req<GeneratedAsset[]>("/image/assets", {
      query: filter as Record<string, string | number | boolean | undefined>,
    }),
  getAsset: (assetId: string) => req<GeneratedAsset>(`/image/assets/${assetId}`),
  /** URL for <img> tags — the backend issues a fresh presigned redirect. */
  assetFileUrl: (assetId: string) => apiUrl(`/image/assets/${assetId}/file`),
  approveAsset: (assetId: string, body?: AssetApprovalRequest) =>
    req<GeneratedAsset>(`/image/assets/${assetId}/approve`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
  rejectAsset: (assetId: string, body?: AssetRejectRequest) =>
    req<GeneratedAsset>(`/image/assets/${assetId}/reject`, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
  // ── Visual identities ──
  getCurrentVisualIdentity: (anchor: {
    character_id?: string;
    entity_id?: string;
    universe_id?: string;
    status?: VisualIdentityStatus;
  }) =>
    req<VisualIdentity>("/image/visual-identities/current", {
      query: anchor as Record<string, string | undefined>,
    }),
  updateVisualIdentity: (body: VisualIdentityUpdate) =>
    req<VisualIdentity>("/image/visual-identities/current", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  // ── Image generation settings (Task 10) ──
  getImageGenerationSettings: () =>
    req<ImageGenerationSettings>("/image/settings"),
  updateImageGenerationSettings: (body: Partial<ImageGenerationSettings>) =>
    req<ImageGenerationSettings>("/image/settings", {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};

// ─── Universes ────────────────────────────────────────────────

/** Response of POST /universes/universes/{id}/fork (a summary dict, not a Universe). */
export interface ForkUniverseResult {
  source_universe_id: string;
  new_universe_id: string;
  name: string;
  entities_cloned: number;
  relationships_cloned: number;
  status: string;
}

export const universesApi = {
  listMultiverses: () => req<Multiverse[]>("/universes/multiverses"),
  createMultiverse: (data: { name: string; description?: string; tags?: string[] }) =>
    req<Multiverse>("/universes/multiverses", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateMultiverse: (id: string, data: {
    name?: string;
    description?: string;
    system_name?: string;
  }) =>
    req<Multiverse>(`/universes/multiverses/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteMultiverse: (id: string, opts?: { force?: boolean }) =>
    req<void>(`/universes/multiverses/${id}`, {
      method: "DELETE",
      query: opts?.force ? { force: "true" } : undefined,
    }),

  listUniverses: (multiverseId?: string) =>
    req<Universe[]>("/universes/universes", {
      query: multiverseId ? { multiverse_id: multiverseId } : undefined,
    }),
  getUniverse: (id: string) => req<Universe>(`/universes/universes/${id}`),
  createUniverse: (data: {
    name: string;
    multiverse_id: string;
    genre?: string;
    description?: string;
    tags?: string[];
    is_active?: boolean;
  }) =>
    req<Universe>("/universes/universes", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateUniverse: (id: string, data: Partial<{
    name: string;
    genre: string;
    tone: string;
    description: string;
    tags: string[];
    is_active: boolean;
  }>) =>
    req<Universe>(`/universes/universes/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  deleteUniverse: (id: string) =>
    req<void>(`/universes/universes/${id}`, { method: "DELETE" }),

  // ── Snapshots, Fork & Seed ────────────────────────────────
  seedUniverse: (universeId: string, data: {
    entity_count?: number;
    entity_types?: string[];
    use_tables?: boolean;
    table_ids?: string[];
    template_ids?: string[];
    name_pattern?: string;
  }) =>
    req<{ universe_id: string; entities_created: number; errors: string[] }>(
      `/universes/universes/${universeId}/seed`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  forkUniverse: (universeId: string, data: { name: string; description?: string }) =>
    req<ForkUniverseResult>(`/universes/universes/${universeId}/fork`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  createSnapshot: (universeId: string, data: { name: string; description?: string }) =>
    req<{ snapshot_id: string; name: string; created_at: string }>(
      `/universes/universes/${universeId}/snapshots`,
      { method: "POST", body: JSON.stringify(data) },
    ),

  listSnapshots: (universeId: string) =>
    req<WorldSnapshot[]>(`/universes/universes/${universeId}/snapshots`),

  restoreSnapshot: (universeId: string, snapshotId: string) =>
    req<{ universe_id: string; restored_from: string; status: string }>(
      `/universes/universes/${universeId}/snapshots/${snapshotId}/restore`,
      { method: "POST", body: JSON.stringify({ confirm: true }) },
    ),

  deleteSnapshot: (universeId: string, snapshotId: string) =>
    req<void>(`/universes/universes/${universeId}/snapshots/${snapshotId}`, { method: "DELETE" }),

  compareSnapshots: (universeId: string, snapshotA: string, snapshotB: string) =>
    req<SnapshotComparison>(`/universes/universes/${universeId}/snapshots/compare`, {
      query: { snapshot_a_id: snapshotA, snapshot_b_id: snapshotB },
    }),
};

// ─── World Graph ──────────────────────────────────────────────

export const graphApi = {
  getWorldGraph: (filter?: WorldGraphFilter) => {
    const query: Record<string, string | number | undefined> = {};
    if (filter?.multiverse_id) query.multiverse_id = filter.multiverse_id;
    if (filter?.universe_id) query.universe_id = filter.universe_id;
    if (filter?.entity_types?.length) query.entity_types = filter.entity_types.join(",");
    if (filter?.related_to) query.related_to = filter.related_to;
    return req<WorldGraph>("/graph/world", { query });
  },

  // ── Q-11: Universe-scoped + ego-graph explorer ────────────
  getUniverseGraph: (
    universeId: string,
    options?: {
      depth?: number;
      entity_types?: string[];
      rel_types?: string[];
      limit_per_depth?: number;
    },
  ) => {
    const query: Record<string, string | number | undefined> = {};
    if (options?.depth) query.depth = options.depth;
    if (options?.entity_types?.length) {
      query.entity_types = options.entity_types.join(",");
    }
    if (options?.rel_types?.length) {
      query.rel_types = options.rel_types.join(",");
    }
    if (options?.limit_per_depth) {
      query.limit_per_depth = options.limit_per_depth;
    }
    return req<WorldGraph>(`/graph/universes/${universeId}/graph`, { query });
  },

  getEgoGraph: (
    universeId: string,
    entityId: string,
    depth = 2,
  ) =>
    req<WorldGraph>(
      `/graph/universes/${universeId}/graph/entity/${entityId}`,
      { query: { depth } },
    ),
};

// ─── Prompts (DSPy modules) ───────────────────────────────────

export const promptsApi = {
  list: () => req<PromptModuleSummary[]>("/prompts"),
  getModule: (moduleId: string) => req<PromptModuleDetail>(`/prompts/${moduleId}`),
  updateInstructions: (moduleId: string, instructions: string) =>
    req<PromptModuleDetail>(`/prompts/${moduleId}`, {
      method: "PUT",
      body: JSON.stringify({ instructions }),
    }),
  resetOverride: (moduleId: string) =>
    req<void>(`/prompts/${moduleId}/overrides`, { method: "DELETE" }),
  test: (moduleId: string, inputs: Record<string, string>, useOverride = true) =>
    req<PromptTestResult>(`/prompts/${moduleId}/test`, {
      method: "POST",
      body: JSON.stringify({ inputs, use_override: useOverride }),
    }),
};

// ─── Stories (Phase 5) ────────────────────────────────────────

export const storiesApi = {
  getStory: (storyId: string) => req<StoryResponse>(`/stories/${storyId}`),
  listStories: (opts?: { universe_id?: string; status?: string; limit?: number; offset?: number }) =>
    req<{ stories: StorySummary[]; total: number }>("/stories", {
      query: opts as Record<string, string | number | undefined>,
    }),
  listScenes: (storyId: string) => req<SceneSummary[]>(`/stories/${storyId}/scenes`),
  listThreads: (storyId: string, onlyOpen = true) =>
    req<StoryThread[]>(`/stories/${storyId}/threads`, {
      query: { only_open: String(onlyOpen) },
    }),
  getSceneTurns: (sceneId: string, limit = 30) =>
    req<SceneTurn[]>(`/scenes/${sceneId}/turns`, { query: { limit } }),
  patchStory: (
    storyId: string,
    data: { arc_label?: string; tension_score?: number; active_threads?: string[] },
  ) =>
    req<StoryResponse>(`/stories/${storyId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};

// ─── GM Assistant (CF-4, CF-5, CF-6, CF-7) ──────────────────

export interface QuickWorldResult {
  multiverse_id: string;
  universe_id: string;
  world_name: string;
  world_description: string;
  axiom: string;
  opening_scene: string;
  pc_concept: string;
  entities: Array<{ name: string; type: string; description: string; want: string; tags: string[] }>;
  lore_facts: string[];
  committed: number;
  errors: string[];
  session_id: string | null;
}

export const forgeApi = {
  quickWorld: (body: {
    seed: string;
    genre?: string;
    tone?: string;
    name?: string;
    start_playing?: boolean;
  }) =>
    req<QuickWorldResult>("/forge/quick-world", {
      method: "POST",
      body: JSON.stringify(body),
      timeout: 180_000,
    }),
  demoWorld: (startPlaying = true) =>
    req<QuickWorldResult & { reused: boolean }>("/forge/demo-world", {
      method: "POST",
      query: { start_playing: String(startPlaying) },
      timeout: 60_000,
    }),
};

export const changeLogApi = {
  list: (params?: {
    subject_type?: string;
    subject_id?: string;
    change_type?: string;
    author?: string;
    limit?: number;
    offset?: number;
    sort_order?: "asc" | "desc";
  }) =>
    req<ChangeLogListResponse>("/change-log", {
      query: params as Record<string, string | number | undefined>,
    }),
};

export const gmApi = {
  suggestHooks: (universeId: string, storyId?: string, maxHooks = 5) =>
    req<{ hooks: PlotHook[] }>("/gm/hooks", {
      method: "POST",
      body: JSON.stringify({ universe_id: universeId, story_id: storyId, max_hooks: maxHooks }),
    }),

  detectContradictions: (universeId: string, focusEntityId?: string) =>
    req<{ contradictions: Contradiction[] }>("/gm/contradictions", {
      method: "POST",
      body: JSON.stringify({ universe_id: universeId, focus_entity_id: focusEntityId }),
    }),

  generateSessionPrep: (universeId: string, storyId: string, sessionNumber?: number) =>
    req<{ prep: SessionPrep }>("/gm/session-prep", {
      method: "POST",
      body: JSON.stringify({ universe_id: universeId, story_id: storyId, session_number: sessionNumber }),
    }),

  generateHandout: (
    universeId: string,
    options?: { handout_type?: string; focus_entity_id?: string; tone?: string; spoiler_level?: string },
  ) =>
    req<{ handout: Handout }>("/gm/handouts", {
      method: "POST",
      body: JSON.stringify({
        universe_id: universeId,
        handout_type: options?.handout_type ?? "letter",
        focus_entity_id: options?.focus_entity_id,
        tone: options?.tone ?? "mysterious",
        spoiler_level: options?.spoiler_level ?? "safe",
      }),
    }),

  rollDice: (expression: string) =>
    req<{ total: number; rolls: number[]; expression: string; kept_rolls: number[]; modifier: number }>(
      "/gm/roll",
      {
        method: "POST",
        body: JSON.stringify({ expression }),
      },
    ),

  checkEntryContradiction: (universeId: string, entryText: string) =>
    req<{ alert: Contradiction | null }>("/gm/capture/contradiction-check", {
      method: "POST",
      body: JSON.stringify({ universe_id: universeId, entry_text: entryText }),
    }),

  captureInsights: (universeId: string, entryText: string) =>
    req<CaptureInsight>("/gm/capture/insights", {
      method: "POST",
      body: JSON.stringify({ universe_id: universeId, entry_text: entryText }),
    }),

  // P2.3 — per-universe scratchpad (server-backed; replaces localStorage)
  getNotes: (universeId: string) =>
    req<{ universe_id: string; content: string; updated_at: string }>(
      `/gm/notes/${universeId}`,
    ),
  upsertNotes: (universeId: string, content: string) =>
    req<{ universe_id: string; content: string; updated_at: string }>(
      `/gm/notes/${universeId}`,
      { method: "PUT", body: JSON.stringify({ content }) },
    ),
};

// ─── Entity Templates (M-31, CF-2) ──────────────────────────

export const templatesApi = {
  list: (universeId?: string, entityType?: string, limit = 50, offset = 0) => {
    const query: Record<string, string | number | undefined> = { limit, offset };
    if (universeId) query.universe_id = universeId;
    if (entityType) query.entity_type = entityType;
    return req<EntityTemplateListResponse>("/templates", { query });
  },

  get: (templateId: string) => req<EntityTemplate>(`/templates/${templateId}`),

  create: (data: {
    universe_id: string;
    name: string;
    entity_type: string;
    description?: string;
    base_properties?: Record<string, unknown>;
    variable_properties?: unknown[];
    naming_pattern?: unknown;
    stat_generation?: unknown;
    default_state_tags?: string[];
    default_detail_level?: string;
    default_personality?: unknown;
    parent_template_id?: string;
  }) =>
    req<EntityTemplate>("/templates", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (templateId: string, data: Record<string, unknown>) =>
    req<EntityTemplate>(`/templates/${templateId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (templateId: string) =>
    req<void>(`/templates/${templateId}`, { method: "DELETE" }),

  /** Resolve a template into a populated entity create-payload (F3-2). Bumps usage_count. */
  instantiate: (
    templateId: string,
    body: {
      override_name?: string;
      override_properties?: Record<string, unknown>;
      provide_context?: string;
      scene_id?: string;
      story_id?: string;
    } = {},
  ) =>
    req<InstantiateTemplateResponse>(`/templates/${templateId}/instantiate`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  incrementUsage: (templateId: string) =>
    req<EntityTemplate>(`/templates/${templateId}/increment-usage`, {
      method: "POST",
    }),
};

// ─── Random Tables (M-33, DL-21) ────────────────────────────

export const randomTablesApi = {
  list: (universeId?: string, tableType?: string, limit = 50, offset = 0) => {
    const query: Record<string, string | number | undefined> = { limit, offset };
    if (universeId) query.universe_id = universeId;
    if (tableType) query.table_type = tableType;
    return req<RandomTableListResponse>("/random-tables", { query });
  },

  get: (tableId: string) => req<RandomTable>(`/random-tables/${tableId}`),

  create: (data: {
    name: string;
    table_type?: string;
    dice_formula?: string;
    weighted?: boolean;
    entries: Array<{ min_roll: number; max_roll: number; value: string; weight?: number | null; subtable_id?: string | null }>;
    universe_id?: string;
    description?: string;
  }) =>
    req<RandomTable>("/random-tables", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (tableId: string, data: Record<string, unknown>) =>
    req<RandomTable>(`/random-tables/${tableId}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  delete: (tableId: string) =>
    req<void>(`/random-tables/${tableId}`, { method: "DELETE" }),

  roll: (tableId: string, actorId?: string) => {
    const query: Record<string, string> = {};
    if (actorId) query.actor_id = actorId;
    return req<RollResult>(`/random-tables/${tableId}/roll`, {
      method: "POST",
      query,
    });
  },
};

// ─── Prompt Collections (Session Zero / char-creation curation) ──

export const promptCollectionsApi = {
  list: (params: { category?: string; system_id?: string; universe_id?: string; tag?: string; include_builtin?: boolean; limit?: number; offset?: number } = {}) => {
    const query: Record<string, string | number | boolean | undefined> = {
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    };
    if (params.category) query.category = params.category;
    if (params.system_id) query.system_id = params.system_id;
    if (params.universe_id) query.universe_id = params.universe_id;
    if (params.tag) query.tag = params.tag;
    if (params.include_builtin !== undefined) query.include_builtin = params.include_builtin;
    return req<PromptCollectionListResponse>("/prompt-collections", { query });
  },

  get: (collectionId: string) => req<PromptCollection>(`/prompt-collections/${collectionId}`),

  create: (data: {
    name: string;
    description?: string;
    category?: string;
    system_id?: string | null;
    universe_id?: string | null;
    tags?: string[];
    entries?: Array<{
      order?: number;
      category?: string;
      question_text: string;
      answer_options?: string[];
      guidance?: string | null;
      is_final?: boolean;
    }>;
    version?: string | null;
  }) =>
    req<PromptCollection>("/prompt-collections", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  update: (collectionId: string, data: Record<string, unknown>) =>
    req<PromptCollection>(`/prompt-collections/${collectionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  delete: (collectionId: string) =>
    req<void>(`/prompt-collections/${collectionId}`, { method: "DELETE" }),

  publish: (collectionId: string, body: { version?: string; note?: string } = {}) =>
    req<PromptCollectionVersion>(`/prompt-collections/${collectionId}/publish`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  listVersions: (collectionId: string) =>
    req<PromptCollectionVersionListResponse>(`/prompt-collections/${collectionId}/versions`),

  restore: (versionId: string) =>
    req<PromptCollection>(`/prompt-collections/versions/${versionId}/restore`, {
      method: "POST",
    }),
};

// ─── CanonKeeper Review (CF-8) ────────────────────────────────

export const canonApi = {
  /** Get all proposals for a scene, grouped by status. */
  sceneReview: (sceneId: string) =>
    req<SceneReview>(`/scenes/${sceneId}/canon-review`),

  /** Get the story-level queue: every scene with pending proposals. */
  storyQueue: (storyId: string, onlyPending = true) =>
    req<CanonQueue>(`/stories/${storyId}/canon-queue`, {
      query: { only_pending: onlyPending ? "true" : "false" },
    }),

  /** Accept a single proposal. */
  acceptProposal: (proposalId: string, reason: string) =>
    req<ProposalItem>(`/canon-review/${proposalId}/accept`, {
      method: "POST",
      query: { reason },
    }),

  /** Reject a single proposal. */
  rejectProposal: (proposalId: string, reason: string) =>
    req<ProposalItem>(`/canon-review/${proposalId}/reject`, {
      method: "POST",
      query: { reason },
    }),

  /** Apply a batch of accept/reject verdicts in one call. */
  batchVerdicts: (items: VerdictItem[], decidedBy = "GM") =>
    req<BatchVerdictResponse>("/canon-review/verdicts", {
      method: "POST",
      body: JSON.stringify({ decided_by: decidedBy, items }),
    }),

  /** Get every proposal produced by an ingestion job (F1-4 by-ingest scope). */
  byIngest: (jobId: string, statusFilter?: string) =>
    req<IngestJobReview>(`/canon-review/by-ingest/${jobId}`, {
      query: { status_filter: statusFilter },
    }),

  /**
   * Server-side "select all matching active filters" (F2-3c).
   * Call with dry_run=true for a preview (affected count + token), then
   * again with dry_run=false and the preview token to execute.
   */
  verdictsByFilter: (body: VerdictByFilterRequest) =>
    req<VerdictByFilterResponse>("/canon-review/verdicts/by-filter", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Commit all accepted proposals for an ingestion job to canon. */
  commitByIngest: (jobId: string) =>
    req<{ ingestion_job_id: string; committed: number; errors: string[]; status: string }>(
      `/canon-review/by-ingest/${jobId}/commit`,
      { method: "POST" },
    ),
};

// ─── Performance Monitoring ──────────────────────────────────

export const performanceApi = {
  /** High-level performance overview. */
  overview: () => req<PerformanceOverview>("/performance"),

  /** Recent slow query executions. */
  slowQueries: (limit = 20) =>
    req<SlowQuery[]>("/performance/slow", { query: { limit } }),

  /** Complete performance report. */
  report: () => req<PerformanceReport>("/performance/report"),

  /** Reset the performance tracker. */
  reset: () => req<void>("/performance/reset", { method: "POST" }),

  /** Alert history with filtering. */
  alerts: (opts?: { severity?: string; resolved?: boolean; limit?: number }) =>
    req<PerformanceAlert[]>("/performance/alerts", {
      query: opts as Record<string, string | number | undefined>,
    }),

  /** Get alert configuration. */
  getAlertConfig: () =>
    req<AlertConfig>("/performance/alerts/config"),

  /** Update alert configuration. */
  updateAlertConfig: (config: Partial<AlertConfig>) =>
    req<AlertConfig>("/performance/alerts/config", {
      method: "PUT",
      body: JSON.stringify(config),
    }),

  /** Trigger a health check. */
  checkHealth: () =>
    req<void>("/performance/alerts/check-health", { method: "POST" }),
};

// ─── World Architect (F2-1) ──────────────────────────────────

export const architectApi = {
  /** Structured world-coverage report — 8 dimensions, FORGE_EXPANSION.md §2. */
  coverage: (
    universeId: string,
    opts?: { require_mechanics?: boolean; require_random_tables?: boolean },
  ) =>
    req<WorldCoverage>(`/architect/${universeId}/coverage`, {
      query: {
        require_mechanics:
          opts?.require_mechanics === undefined ? undefined : String(opts.require_mechanics),
        require_random_tables:
          opts?.require_random_tables === undefined
            ? undefined
            : String(opts.require_random_tables),
      },
    }),
};

// ─── System ──────────────────────────────────────────────────

export interface HealthCheck {
  status: string;
  components?: Record<string, string>;
}

export const systemApi = {
  /** Get backend health status. */
  getHealth: () => req<HealthCheck>("/health", { query: { deep: "true" }, timeout: 8000 }),
};
