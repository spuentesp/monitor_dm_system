// Light RP (Phase 7) — Conversatory surfaces: one-click universe-character
// chats, streaming send, the "what this character remembers about you" view
// with delete, and graduating a light chat into a guided-start campaign.
// Endpoint handlers live in monitor_ui.routers.light_rp.

import { apiUrl, req } from "./api";

export interface UniverseCharacter {
  entity_id: string;
  name: string;
  description: string;
  universe_id: string;
}

export interface ConversationStartResult {
  conversation_id: string;
  character_id: string;
  entity_id: string;
  universe_id: string;
  version_id: string;
  opening: string;
  preset?: string;
}

export interface MemoryItem {
  id: string;
  text: string;
  importance: number;
  entity_id?: string;
  universe_id?: string;
  conversation_id?: string;
  created_at: string;
}

export interface GraduatePrepareResult {
  character_id: string;
  universe_id: string;
  entity_id: string;
  version_id: string;
  start_options: Array<Record<string, unknown>>;
  start_options_source: string;
  question: string;
  suggested_answers: string[];
}

export interface GraduateResult {
  character_id: string;
  universe_id: string;
  entity_id: string;
  version_id: string;
  chosen: {
    option_id: string | null;
    option_title: string | null;
    is_surprise: boolean;
    free_answer: string;
  };
  story_premise: string;
  memories_carried: number;
  session_create: Record<string, unknown>;
}

export interface ConversationTurn {
  turn_index: number;
  speaker_role: string;
  entity_name?: string | null;
  text: string;
  emotional_state?: string | null;
  timestamp?: string | null;
}

export interface ConversationTranscript {
  conversation_id: string;
  status: string;
  turns: ConversationTurn[];
}

export type StreamEvent =
  | { type: "token"; text: string }
  | {
      type: "done";
      conversation_id: string;
      text: string;
      emotional_state: string | null;
      relationship_snapshot: Record<string, unknown>;
    };

export const lightRpApi = {
  listUniverseCharacters: (universeId: string) =>
    req<UniverseCharacter[]>(`/entities/universes/${universeId}/characters`),

  startUniverseCharacterChat: (body: { entity_id: string; persona_character_id?: string | null }) =>
    req<ConversationStartResult>("/entities/universe-characters/start", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Stream one player line's reply as token/done events (SSE). */
  sendStream: async function* (
    characterId: string,
    conversationId: string,
    text: string,
    options?: { include_cross_incarnation?: boolean },
  ): AsyncGenerator<StreamEvent> {
    const res = await fetch(
      apiUrl(`/entities/characters/${characterId}/conversations/${conversationId}/send-stream`),
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({
          text,
          include_cross_incarnation: options?.include_cross_incarnation ?? false,
        }),
        // A reply can legitimately take a while (several LLM calls), but never
        // forever: without this the typing indicator spins indefinitely when a
        // stream dies silently (e.g. backend restart mid-reply).
        signal: AbortSignal.timeout(180_000),
      },
    );
    if (!res.ok) {
      const detail = await res.text().catch(() => res.statusText);
      throw new Error(`Reply failed (${res.status}): ${detail}`);
    }
    if (!res.body) throw new Error("Reply failed: no response body");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const line = block.split("\n").find((l) => l.startsWith("data: "));
        if (line) {
          const payload = line.slice("data: ".length).trim();
          if (payload === "[DONE]") return;
          try {
            yield JSON.parse(payload) as StreamEvent;
          } catch {
            // Skip malformed frames rather than killing the reply.
          }
        }
        sep = buffer.indexOf("\n\n");
      }
    }
  },

  /** Full transcript of a past conversation, oldest first — for reopening a chat. */
  getConversationTurns: (characterId: string, conversationId: string) =>
    req<ConversationTranscript>(
      `/entities/characters/${characterId}/conversations/${conversationId}/turns`,
    ),

  listMemoriesAboutYou: (characterId: string, params?: { universe_id?: string; limit?: number }) =>
    req<{ memories: MemoryItem[]; total: number }>(
      `/entities/characters/${characterId}/memories/about-you`,
      { query: params as Record<string, string | number | undefined> },
    ),

  deleteMemory: (characterId: string, memoryId: string) =>
    req<void>(`/entities/characters/${characterId}/memories/${memoryId}`, { method: "DELETE" }),

  graduatePrepare: (characterId: string, params?: { universe_id?: string; tone?: string }) =>
    req<GraduatePrepareResult>(`/entities/characters/${characterId}/graduate/prepare`, {
      query: params as Record<string, string | number | undefined>,
      timeout: 120_000,
    }),

  graduateToCampaign: (
    characterId: string,
    body: {
      universe_id?: string | null;
      persona_character_id?: string | null;
      start_answer?: string;
      start_options?: Array<Record<string, unknown>>;
      question_text?: string;
      tone?: string | null;
    },
  ) =>
    req<GraduateResult>(`/entities/characters/${characterId}/graduate`, {
      method: "POST",
      body: JSON.stringify(body),
      timeout: 120_000,
    }),
};
