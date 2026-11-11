// Phase 7 Part B — GM assistant at a real table: API client.
// Separate from lib/api.ts (which serves every surface) so this flow can land
// without touching the shared client; reuses its `req` helper.

import { req } from "@/lib/api";
import type {
  ImproviseResponse,
  LastSessionResponse,
  NpcDossierResponse,
  PartyKnowledgeAnswer,
  PrepBundleGetResponse,
  PrepCommitResponse,
  PrepExtraction,
  PrepLocationItem,
  PrepNpcItem,
  PrepThreadItem,
  RulesAnswer,
  SessionLogProposeResponse,
  SessionLogProposalRetractResponse,
} from "./gm-table-types";

export const gmTableApi = {
  /** Task 2 — extract tonight's items from the GM's notes (review-only). */
  extractPrep: (universeId: string, notes: string, storyId?: string | null) =>
    req<PrepExtraction>("/gm/prep/extract", {
      method: "POST",
      body: JSON.stringify({ universe_id: universeId, story_id: storyId ?? null, notes }),
    }),

  /** Task 2 — save the reviewed bundle; stage threads + canon proposals. */
  commitPrep: (body: {
    universe_id: string;
    story_id: string;
    npcs: PrepNpcItem[];
    locations: PrepLocationItem[];
    threads: PrepThreadItem[];
  }) => req<PrepCommitResponse>("/gm/prep/commit", { method: "POST", body: JSON.stringify(body) }),

  /** Task 2 — the saved "tonight" bundle, if any. */
  getPrep: (universeId: string, storyId?: string | null) =>
    req<PrepBundleGetResponse>(`/gm/prep/${universeId}`, {
      query: { story_id: storyId ?? undefined },
    }),

  /** Task 3 — who is this NPC and what do they want. */
  lookupNpc: (universeId: string, query: { name?: string; entity_id?: string }) =>
    req<NpcDossierResponse>("/gm/lookup/npc", {
      method: "POST",
      body: JSON.stringify({
        universe_id: universeId,
        name: query.name ?? null,
        entity_id: query.entity_id ?? null,
      }),
    }),

  /** Task 3 — what does the party know about this. */
  lookupPartyKnowledge: (
    universeId: string,
    query: { party_id?: string | null; character_ids?: string[]; topic?: string | null },
  ) =>
    req<PartyKnowledgeAnswer>("/gm/lookup/party-knowledge", {
      method: "POST",
      body: JSON.stringify({
        universe_id: universeId,
        party_id: query.party_id ?? null,
        character_ids: query.character_ids ?? [],
        topic: query.topic ?? null,
      }),
    }),

  /** Task 3 — what happened / was said last session. */
  lookupLastSession: (universeId: string, storyId: string, transcriptLimit = 20) =>
    req<LastSessionResponse>("/gm/lookup/last-session", {
      method: "POST",
      body: JSON.stringify({
        universe_id: universeId,
        story_id: storyId,
        transcript_limit: transcriptLimit,
      }),
    }),

  /** Task 3 — a name or a complication on demand. */
  improvise: (body: {
    universe_id: string;
    story_id?: string | null;
    kind: "name" | "complication";
    context?: string;
    count?: number;
  }) => req<ImproviseResponse>("/gm/lookup/improvise", { method: "POST", body: JSON.stringify(body) }),

  /** Task 3 — a rules question answered with its source. */
  lookupRules: (body: { system_id?: string | null; universe_id?: string | null; question: string }) =>
    req<RulesAnswer>("/gm/lookup/rules", { method: "POST", body: JSON.stringify(body) }),

  /** Task 4 — paste what happened; propose canon changes + flags (G-9). */
  proposeSessionLog: (body: {
    universe_id: string;
    story_id?: string | null;
    scene_id?: string | null;
    log_text: string;
  }) =>
    req<SessionLogProposeResponse>("/gm/session-log/propose", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** G03 (CF-1) — retract a queued candidate proposal before wrap-up. */
  retractProposal: (proposalId: string, reason?: string) =>
    req<SessionLogProposalRetractResponse>(
      `/gm/session-log/proposals/${proposalId}/retract`,
      {
        method: "POST",
        body: JSON.stringify(reason ? { reason } : {}),
      },
    ),
};
