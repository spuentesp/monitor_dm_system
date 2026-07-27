// Chat feature — shared types
// Wire-format types mirror the FastAPI WebSocket payload at
// /api/chat/ws/{session_id} (packages/ui/backend/src/monitor_ui/routers/chat.py:901-1093).

import type { Message } from "@/lib/types";

/** WS frame types the client understands. Mirrors chat.py:969-1006 +
 *  the new composing / thinking / thinking_end events added in Phase 2. */
export type WsServerMsg =
  | { type: "start"; message_id: string }
  | { type: "composing"; message_id: string }
  | { type: "thinking"; message_id: string; delta: string }
  | { type: "thinking_end"; message_id: string }
  | { type: "token"; message_id: string; token: string }
  | { type: "done" | "end"; message_id: string; metadata?: Record<string, unknown> }
  | { type: "tool_call"; message_id: string; name: string; args?: Record<string, unknown>; id?: string }
  | { type: "tool_result"; message_id: string; tool_call_id?: string; result?: unknown; error?: string }
  | { type: "pong" }
  | { type: "error"; detail?: string; message?: string }
  | { type: string; [k: string]: unknown };

/** Thinking trace for a single message (assembled client-side from
 *  thinking + thinking_end events). Empty when the server did not emit
 *  CoT reasoning for that turn. */
export interface ThinkingTrace {
  /** Server-provided message id this trace belongs to. */
  message_id: string;
  /** Full reasoning text. */
  text: string;
  /** True while the server is still streaming thinking chunks. */
  streaming: boolean;
}

/** A single MCP tool invocation surfaced to the client (Phase 2B). Each
 *  tool_call frame starts an entry; the matching tool_result frame fills
 *  in the result or error. The client correlates via `id`. */
export interface ToolCall {
  /** Server-issued correlation id (uuid). */
  id: string;
  /** MCP tool name (e.g. "neo4j_search", "mongo_query"). */
  name: string;
  /** Tool arguments. */
  args: Record<string, unknown>;
  /** Truncated result preview (server caps at 2000 chars). */
  result_preview?: string;
  /** Error string if the tool failed. */
  error?: string;
  /** True while waiting for the matching tool_result. */
  pending: boolean;
}

/** WS frame types the client sends. */
export type WsClientMsg =
  | { type: "message"; content: string; chat_mode?: "ic" | "ooc"; character_id?: string; is_ooc_persona?: boolean }
  | { type: "dice_result"; spec: string; value: number; rolls: number[]; reason: string }
  | { type: "ping" };

/** A GM message currently being streamed — the bubble shows partial text. */
export interface StreamingMessage {
  /** Server-issued message id (from the `start` frame). */
  id: string;
  /** Accumulated narrative text so far. */
  text: string;
  /** Live thinking trace for this turn, if the server emits one. */
  thinking?: ThinkingTrace;
  /** Live tool-call list for this turn, populated as the agent invokes
   *  MCP tools. Persisted to metadata.tool_calls on `done`. */
  toolCalls?: ToolCall[];
}

/** A dice-roll request surfaced to the player. */
export interface DiceRequest {
  spec: string;
  reason: string;
}

/** A pending consequence choice surfaced by the GM. */
export interface ConsequenceChoice {
  options: string[];
  risk_preview?: string;
}

/** Options that ride on a player turn. */
export interface SendOptions {
  chat_mode?: "ic" | "ooc";
  character_id?: string;
  is_ooc_persona?: boolean;
  /** Skip optimistic echo (used by retry-after-failure so we don't double-bubble). */
  skipEcho?: boolean;
}

/** Surfaced failure state (last attempt failed). */
export interface TurnFailure {
  text: string;
  detail: string;
}

/** Connection status mirror of useChatWebSocket's WsStatus. */
export type ChatStatus = "connecting" | "connected" | "disconnected" | "reconnecting";

/** Re-export the Message type for chat consumers. */
export type { Message };