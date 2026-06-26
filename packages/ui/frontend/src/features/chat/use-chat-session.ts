"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { chatApi } from "@/lib/api";
import { useChatWebSocket } from "@/hooks/use-chat-websocket";
import type { Message } from "@/lib/types";
import { PLAY_KEYS } from "@/lib/query-keys";
import type {
  ChatStatus,
  DiceRequest,
  SendOptions,
  StreamingMessage,
  TurnFailure,
  WsServerMsg,
} from "./types";

/** Default turn watchdog (matches the original PlayConsole.tsx). */
const TURN_WATCHDOG_MS = 240_000;

export interface UseChatSessionOptions {
  sessionId: string | null;
  /** Turn watchdog in ms; defaults to 240_000 (4 min). */
  watchdogMs?: number;
  /** Called whenever a turn completes (success OR failure) so callers can
   *  invalidate dependent queries. */
  onTurnSettled?: (sessionId: string) => void;
}

export interface UseChatSessionReturn {
  /** Ordered message list including the optimistic player echo. */
  messages: Message[];
  /** Currently streaming GM message, if any. */
  streamingMsg: StreamingMessage | null;
  /** True while we're waiting for the GM's first response or a finished turn. */
  isTyping: boolean;
  /** Last failure surfaced (network error, 4xx/5xx, timeout, WS error). */
  sendFailure: TurnFailure | null;
  /** Pending dice request surfaced by the GM. */
  pendingDiceRequest: DiceRequest | null;
  /** Underlying WS connection status. */
  status: ChatStatus;
  /** Send a player turn. No-op if there's no session. */
  send: (text: string, opts?: SendOptions) => void;
  /** Re-send the last turn (or the last failed send). */
  retry: () => void;
  /** Submit a dice result back to the GM. */
  submitDiceResult: (spec: string, value: number, rolls: number[], reason: string) => void;
  /** Stop the watchdog without sending. (For future use; cancel is not yet wired.) */
  stop: () => void;
  /** Externally clear the failure card (Dismiss button). */
  dismissFailure: () => void;
  /** Externally clear the pending dice request. */
  dismissDice: () => void;
  /** Surface a failure that wasn't caused by a player turn (e.g. end-scene
   *  request failed, world-build error). Use this for non-turn failures
   *  so the standard failure card can show them. */
  surfaceFailure: (detail: string) => void;
}

/**
 * Owns the streaming state machine for a single chat session.
 *
 * - WS lifecycle via useChatWebSocket
 * - REST fallback when WS is down (chatApi.sendMessage)
 * - Per-turn isolation: streaming buffer and final-message mapping are keyed
 *   by the server-issued message_id from the `start` frame. Late tokens for
 *   an earlier turn never pollute a later one.
 * - 4-minute watchdog on both WS and REST paths.
 * - Optimistic player-bubble echo (re-uses React Query cache).
 *
 * Used by both PlayConsole (game-master chat) and the World Architect page.
 */
export function useChatSession({
  sessionId,
  watchdogMs = TURN_WATCHDOG_MS,
  onTurnSettled,
}: UseChatSessionOptions): UseChatSessionReturn {
  const qc = useQueryClient();
  const [streamingMsg, setStreamingMsg] = useState<StreamingMessage | null>(null);
  const [isTyping, setIsTyping] = useState(false);
  const [sendFailure, setSendFailure] = useState<TurnFailure | null>(null);
  const [pendingDiceRequest, setPendingDiceRequest] = useState<DiceRequest | null>(null);

  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastSentRef = useRef<string | null>(null);
  const lastFailedTextRef = useRef<string | null>(null);
  // Tracks server message_ids currently being streamed. Late `token` /
  // `done` frames for an id not in this set are silently dropped (defends
  // against server-side replay after the player has already moved on).
  const liveTurnIdsRef = useRef<Set<string>>(new Set());
  // Accumulates thinking traces per message_id so we can persist them on
  // done. A Map keyed by message_id rather than a single ref because
  // multiple turns can theoretically interleave.
  const thinkingByMsgIdRef = useRef<Map<string, string>>(new Map());

  // ─── Watchdog helpers ──────────────────────────────────────────────

  const clearWatchdog = useCallback(() => {
    if (watchdogRef.current) {
      clearTimeout(watchdogRef.current);
      watchdogRef.current = null;
    }
  }, []);

  const armWatchdog = useCallback(
    (text: string) => {
      clearWatchdog();
      watchdogRef.current = setTimeout(() => {
        setIsTyping(false);
        setStreamingMsg(null);
        setSendFailure({ text, detail: "The GM didn't respond in time." });
      }, watchdogMs);
    },
    [clearWatchdog, watchdogMs],
  );

  // ─── Server messages ───────────────────────────────────────────────

  const handleWsMessage = useCallback(
    (data: Record<string, unknown>) => {
      const msg = data as WsServerMsg;
      if (msg.type === "start") {
        const id = (msg as { message_id: string }).message_id;
        if (!id || !sessionId) return;
        liveTurnIdsRef.current.add(id);
        setStreamingMsg({ id, text: "" });
        // Don't flip isTyping off here — the server emits a follow-up
        // `composing` event right after `start`, which is the canonical
        // signal that the model is actively generating.
        setIsTyping(true);
      } else if (msg.type === "composing") {
        const id = (msg as { message_id?: string }).message_id;
        if (!id) return;
        liveTurnIdsRef.current.add(id);
        // Composing = the model is actively generating. Show typing dots and
        // make sure the streaming bubble exists so a follow-up `thinking`
        // or `token` event lands somewhere.
        setIsTyping(true);
        setStreamingMsg((prev) => (prev?.id === id ? prev : { id, text: "" }));
      } else if (msg.type === "thinking") {
        const t = msg as { type: "thinking"; message_id?: string; delta?: string };
        const id = t.message_id;
        const delta = t.delta ?? "";
        if (!id || !delta) return;
        liveTurnIdsRef.current.add(id);
        thinkingByMsgIdRef.current.set(id, (thinkingByMsgIdRef.current.get(id) ?? "") + delta);
        setStreamingMsg((prev) => {
          const base: StreamingMessage = prev?.id === id ? prev : { id, text: "" };
          const thinking = base.thinking ?? { message_id: id, text: "", streaming: true };
          return { ...base, thinking: { ...thinking, text: thinking.text + delta } };
        });
      } else if (msg.type === "thinking_end") {
        const id = (msg as { message_id?: string }).message_id;
        if (!id) return;
        setStreamingMsg((prev) =>
          prev?.id === id && prev.thinking
            ? { ...prev, thinking: { ...prev.thinking, streaming: false } }
            : prev,
        );
      } else if (msg.type === "token") {
        const t = msg as { type: "token"; message_id?: string; token?: string };
        const id = t.message_id;
        const token = t.token ?? "";
        if (!id) return;
        liveTurnIdsRef.current.add(id);
        setStreamingMsg((prev) => {
          // P0.4: per-turn isolation. Only the currently-streaming turn
          // may append. Late tokens for an earlier turn are dropped
          // silently — they would otherwise overwrite the active bubble
          // and make messages disappear mid-read.
          if (prev?.id === id) return { ...prev, text: prev.text + token };
          // Backward compat: server emitted a token without a prior
          // `start` frame and we have no active stream — adopt the id
          // so the rest of the stream lands in one bubble.
          if (!prev) return { id, text: token };
          // Late token for a different, prior turn. Drop.
          return prev;
        });
        setIsTyping(false);
      } else if (msg.type === "tool_call") {
        // Reserved for Phase 2B (MCP tool-call surfacing). Currently the
        // backend doesn't emit these, but the type is in place so the
        // client is forward-compatible.
        return;
      } else if (msg.type === "tool_result") {
        return;
      } else if (msg.type === "done" || msg.type === "end") {
        const d = msg as { type: string; message_id?: string; metadata?: Record<string, unknown> };
        const id = d.message_id;
        const meta = d.metadata ?? {};
        if (id) liveTurnIdsRef.current.delete(id);
        clearWatchdog();
        setStreamingMsg(null);
        const thinkingText = id ? (thinkingByMsgIdRef.current.get(id) ?? "") : "";
        if (id) thinkingByMsgIdRef.current.delete(id);
        setSendFailure(null);
        // Mirror metadata + persisted thinking trace to local cache so the
        // next refetch sees the dice_request / thinking / etc. without an
        // extra round trip.
        if (id && sessionId) {
          qc.setQueryData<Message[]>(PLAY_KEYS.messages(sessionId), (prev) => {
            if (!prev) return prev;
            return prev.map((m) => {
              if (m.id !== id) return m;
              const nextMetadata = {
                ...(m.metadata ?? {}),
                ...meta,
                ...(thinkingText ? { thinking: thinkingText } : {}),
              };
              return Object.keys(meta).length > 0 || thinkingText
                ? { ...m, metadata: nextMetadata }
                : m;
            });
          });
        }
        if (sessionId) {
          qc.invalidateQueries({ queryKey: PLAY_KEYS.messages(sessionId) });
          qc.invalidateQueries({ queryKey: PLAY_KEYS.state(sessionId) });
          qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
          onTurnSettled?.(sessionId);
        }
        const dr = meta.dice_request as DiceRequest | undefined;
        if (dr?.spec) {
          setPendingDiceRequest({ spec: dr.spec, reason: dr.reason ?? dr.spec });
        } else {
          setPendingDiceRequest(null);
        }
        setIsTyping(false);
      } else if (msg.type === "error") {
        clearWatchdog();
        setIsTyping(false);
        setStreamingMsg(null);
        const detail = String(
          (data as { detail?: unknown; message?: unknown }).detail ??
            (data as { message?: unknown }).message ??
            "The GM hit an error.",
        );
        setSendFailure({ text: lastSentRef.current ?? "", detail });
      }
    },
    [sessionId, qc, clearWatchdog, onTurnSettled],
  );

  const { status: wsStatus, send: wsSend } = useChatWebSocket({
    sessionId,
    onMessage: handleWsMessage,
  });

  // ─── Server-backed message list ─────────────────────────────────────

  const messagesQuery = useMemo(() => PLAY_KEYS.messages(sessionId), [sessionId]);
  const { data: serverMessages = [] } = useMessagesQuery(messagesQuery, sessionId);

  // ─── Public actions ─────────────────────────────────────────────────

  const send = useCallback(
    (text: string, opts?: SendOptions) => {
      const trimmed = text.trim();
      if (!trimmed || !sessionId) return;

      setPendingDiceRequest(null);
      setSendFailure(null);
      setIsTyping(true);
      lastSentRef.current = trimmed;

      const sendOptions = { ...opts };
      delete (sendOptions as { skipEcho?: boolean }).skipEcho;

      if (!opts?.skipEcho) {
        const fake: Message = {
          id: crypto.randomUUID(),
          session_id: sessionId,
          role: "player",
          content: trimmed,
          timestamp: new Date().toISOString(),
          metadata: {},
        };
        qc.setQueryData<Message[]>(PLAY_KEYS.messages(sessionId), (prev) => [
          ...(prev ?? []),
          fake,
        ]);
      }

      if (wsStatus === "connected") {
        wsSend({ type: "message", content: trimmed, ...sendOptions });
        armWatchdog(trimmed);
      } else {
        // REST fallback. Arm watchdog too — backstop if the request never
        // starts (CORS preflight blocked, DNS failure, etc.).
        armWatchdog(trimmed);
        chatApi
          .sendMessage(sessionId, trimmed, sendOptions)
          .then(() => {
            clearWatchdog();
            setSendFailure(null);
            qc.invalidateQueries({ queryKey: PLAY_KEYS.messages(sessionId) });
            qc.invalidateQueries({ queryKey: PLAY_KEYS.state(sessionId) });
            qc.invalidateQueries({ queryKey: PLAY_KEYS.sessions });
            onTurnSettled?.(sessionId);
          })
          .catch((err: unknown) => {
            clearWatchdog();
            const detail = err instanceof Error ? err.message : "Request failed";
            lastFailedTextRef.current = trimmed;
            setSendFailure({ text: trimmed, detail });
          })
          .finally(() => setIsTyping(false));
      }
    },
    [sessionId, qc, wsStatus, wsSend, armWatchdog, clearWatchdog, onTurnSettled],
  );

  const submitDiceResult = useCallback(
    (spec: string, value: number, rolls: number[], reason: string) => {
      if (!sessionId) return;
      setPendingDiceRequest(null);
      const resultContent =
        rolls.length > 0
          ? `🎲 **${reason}** — rolled *${spec}*: [${rolls.join(", ")}] = **${value}**`
          : `🎲 **${reason}** — *${spec}* = **${value}** *(manual)*`;
      const playerMsg: Message = {
        id: crypto.randomUUID(),
        session_id: sessionId,
        role: "player",
        content: resultContent,
        timestamp: new Date().toISOString(),
        metadata: { type: "dice_result", spec, value, rolls, reason },
      };
      qc.setQueryData<Message[]>(PLAY_KEYS.messages(sessionId), (prev) => [...(prev ?? []), playerMsg]);
      if (wsStatus === "connected") {
        wsSend({ type: "dice_result", spec, value, rolls, reason });
        setIsTyping(true);
        armWatchdog(reason);
      }
    },
    [sessionId, qc, wsStatus, wsSend, armWatchdog],
  );

  const retry = useCallback(() => {
    const text = lastFailedTextRef.current ?? lastSentRef.current;
    if (!text) return;
    lastFailedTextRef.current = null;
    send(text, { skipEcho: true });
  }, [send]);

  const stop = useCallback(() => {
    clearWatchdog();
    setIsTyping(false);
    setStreamingMsg(null);
  }, [clearWatchdog]);

  const dismissFailure = useCallback(() => setSendFailure(null), []);
  const dismissDice = useCallback(() => setPendingDiceRequest(null), []);
  const surfaceFailure = useCallback((detail: string) => {
    setSendFailure({ text: "", detail });
  }, []);

  // Reset transient state when the session changes — drop the watchdog,
  // clear streaming/typing/failure/dice state so the next session starts
  // clean. The WS hook itself closes on sessionId=null.
  useEffect(() => {
    setSendFailure(null);
    setStreamingMsg(null);
    setIsTyping(false);
    setPendingDiceRequest(null);
    clearWatchdog();
    lastSentRef.current = null;
    lastFailedTextRef.current = null;
    liveTurnIdsRef.current.clear();
    thinkingByMsgIdRef.current.clear();
    return () => {
      clearWatchdog();
    };
  }, [sessionId, clearWatchdog]);

  return {
    messages: serverMessages,
    streamingMsg,
    isTyping,
    sendFailure,
    pendingDiceRequest,
    status: wsStatus as ChatStatus,
    send,
    retry,
    submitDiceResult,
    stop,
    dismissFailure,
    dismissDice,
    surfaceFailure,
  };
}

// Local wrapper so the messages query is co-located with the hook instead
// of scattered across components.
function useMessagesQuery(queryKey: readonly unknown[], sessionId: string | null) {
  return useQuery<Message[]>({
    queryKey,
    queryFn: () => (sessionId ? chatApi.getMessages(sessionId) : []),
    enabled: !!sessionId,
  });
}